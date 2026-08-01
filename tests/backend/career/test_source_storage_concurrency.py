from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.career.deletion import _exclusive_storage_paths
from backend.career.models import CandidateProfile, CareerAsset, SourceDocument
from backend.career.sources import import_source_document
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.models import User


def test_concurrent_cross_profile_imports_share_bytes_without_losing_ownership(
    tmp_path, monkeypatch
) -> None:
    data_directory = tmp_path / "private-data"
    monkeypatch.setattr("backend.career.sources.settings.DATA_DIR", str(data_directory))
    database_path = (tmp_path / "concurrent-vault.db").as_posix()
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
                User(username=f"concurrent-{index}", hashed_password="not-used-in-this-test")
                for index in range(2)
            ]
            setup.add_all(users)
            setup.flush()
            profiles = [
                CandidateProfile(
                    user_id=user.id,
                    display_name=f"Concurrent profile {index}",
                )
                for index, user in enumerate(users)
            ]
            setup.add_all(profiles)
            setup.commit()
            user_ids = [user.id for user in users]
            profile_ids = [profile.id for profile in profiles]

        content = b"One immutable source shared by concurrent local profiles."

        def import_for(user_id: int) -> str:
            with session_factory() as session:
                return import_source_document(
                    session,
                    user_id=user_id,
                    filename="evidence.txt",
                    media_type="text/plain",
                    data=content,
                ).id

        with ThreadPoolExecutor(max_workers=8) as executor:
            document_ids = list(
                executor.map(
                    lambda index: import_for(user_ids[index % len(user_ids)]),
                    range(32),
                )
            )

        assert len(set(document_ids)) == 2
        with session_factory() as verification:
            assert verification.query(SourceDocument).count() == 2
            assets = verification.query(CareerAsset).all()
            assert len(assets) == 2
            assert len({asset.storage_path for asset in assets}) == 1
            assert _exclusive_storage_paths(verification, profile_ids[0]) == set()
            assert _exclusive_storage_paths(verification, profile_ids[1]) == set()
            storage_path = assets[0].storage_path

        stored = data_directory / storage_path
        assert stored.read_bytes() == content
        assert list(data_directory.rglob(".write-*")) == []
    finally:
        engine.dispose()
