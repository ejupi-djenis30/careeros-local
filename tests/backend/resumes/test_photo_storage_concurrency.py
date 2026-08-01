from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.career.deletion import _exclusive_storage_paths
from backend.career.models import CandidateProfile, CareerAsset
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.models import User
from backend.resumes.photos import store_profile_photo


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (96, 128), (33, 54, 81)).save(output, format="JPEG")
    return output.getvalue()


def test_concurrent_cross_profile_photos_share_normalized_bytes_safely(
    tmp_path, monkeypatch
) -> None:
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", str(data_directory))
    database_path = (tmp_path / "concurrent-photo-vault.db").as_posix()
    ensure_sqlite_parent(f"sqlite:///{database_path}")
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", configure_sqlite_connection)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    try:
        with session_factory() as setup:
            users = [
                User(username=f"photo-{index}", hashed_password="not-used-in-this-test")
                for index in range(2)
            ]
            setup.add_all(users)
            setup.flush()
            profiles = [
                CandidateProfile(user_id=user.id, display_name=f"Photo profile {index}")
                for index, user in enumerate(users)
            ]
            setup.add_all(profiles)
            setup.commit()
            user_ids = [user.id for user in users]
            profile_ids = [profile.id for profile in profiles]

        content = _jpeg()

        def upload_for(user_id: int) -> str:
            with session_factory() as session:
                return store_profile_photo(
                    session,
                    user_id=user_id,
                    filename="portrait.jpg",
                    data=content,
                ).id

        with ThreadPoolExecutor(max_workers=8) as executor:
            asset_ids = list(
                executor.map(
                    lambda index: upload_for(user_ids[index % len(user_ids)]),
                    range(16),
                )
            )

        assert len(set(asset_ids)) == 2
        with session_factory() as verification:
            assets = verification.query(CareerAsset).all()
            profiles = verification.query(CandidateProfile).all()
            assert len(assets) == 2
            assert len({asset.storage_path for asset in assets}) == 1
            assert all(profile.revision == 2 for profile in profiles)
            assert {profile.photo_asset_id for profile in profiles} == set(asset_ids)
            assert _exclusive_storage_paths(verification, profile_ids[0]) == set()
            assert _exclusive_storage_paths(verification, profile_ids[1]) == set()
            storage_path = assets[0].storage_path

        with Image.open(data_directory / storage_path) as stored:
            assert stored.size == (720, 720)
            assert not stored.getexif()
        assert list(data_directory.rglob(".write-*")) == []
    finally:
        engine.dispose()
