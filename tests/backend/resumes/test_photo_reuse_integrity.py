"""Reusing a photo must not select unavailable or unverified stored bytes."""

from io import BytesIO

import pytest
from PIL import Image

from backend.career.models import CandidateProfile, CareerAsset
from backend.core.config import settings
from backend.resumes.photos import load_profile_photo, store_profile_photo
from backend.resumes.renderers.photo import PhotoValidationError


def _jpeg(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (48, 64), color).save(output, format="JPEG")
    return output.getvalue()


@pytest.fixture
def photo_catalog(db_session, test_user, tmp_path, monkeypatch):
    root = tmp_path / "vault"
    monkeypatch.setattr(settings, "DATA_DIR", str(root))
    profile = CandidateProfile(user_id=test_user.id, display_name="Photo integrity fixture")
    db_session.add(profile)
    db_session.commit()
    original = _jpeg((28, 53, 79))
    first = store_profile_photo(
        db_session, user_id=test_user.id, filename="first.jpg", data=original
    )
    selected = store_profile_photo(
        db_session,
        user_id=test_user.id,
        filename="selected.jpg",
        data=_jpeg((81, 62, 43)),
    )
    asset = db_session.get(CareerAsset, first.id)
    return {
        "root": root,
        "original": original,
        "asset": asset,
        "path": root / asset.storage_path,
        "profile_id": profile.id,
        "selected_id": selected.id,
        "revision": selected.profile_revision,
    }


@pytest.mark.parametrize(
    "damage", ["missing", "corrupt", "wrong_size", "not_normalized", "escaped_path"]
)
def test_unverified_photo_reuse_preserves_selected_photo(
    db_session, test_user, photo_catalog, damage
):
    asset = photo_catalog["asset"]
    path = photo_catalog["path"]
    if damage == "missing":
        path.unlink()
    elif damage == "corrupt":
        path.write_bytes(b"x" * path.stat().st_size)
    elif damage == "wrong_size":
        asset.byte_size += 1
        db_session.commit()
    elif damage == "not_normalized":
        asset.normalized = False
        db_session.commit()
    else:
        outside = photo_catalog["root"].parent / "outside.jpg"
        outside.write_bytes(path.read_bytes())
        asset.storage_path = "../outside.jpg"
        db_session.commit()

    with pytest.raises(PhotoValidationError, match="integrity check"):
        store_profile_photo(
            db_session,
            user_id=test_user.id,
            filename="retry.jpg",
            data=photo_catalog["original"],
        )

    assert not db_session.in_transaction()
    db_session.expire_all()
    profile = db_session.get(CandidateProfile, photo_catalog["profile_id"])
    assert profile.photo_asset_id == photo_catalog["selected_id"]
    assert profile.revision == photo_catalog["revision"]
    assert db_session.query(CareerAsset).count() == 2
    if damage == "corrupt":
        assert path.read_bytes() == b"x" * path.stat().st_size
    elif damage == "missing":
        assert not path.exists()


def test_valid_photo_reuse_selects_existing_asset_then_stays_idempotent(
    db_session, test_user, photo_catalog
):
    selected = store_profile_photo(
        db_session,
        user_id=test_user.id,
        filename="retry.jpg",
        data=photo_catalog["original"],
    )
    assert selected.id == photo_catalog["asset"].id
    assert selected.profile_revision == photo_catalog["revision"] + 1
    repeated = store_profile_photo(
        db_session,
        user_id=test_user.id,
        filename="again.jpg",
        data=photo_catalog["original"],
    )
    assert repeated.id == selected.id
    assert repeated.profile_revision == selected.profile_revision
    assert db_session.query(CareerAsset).count() == 2
    loaded, content = load_profile_photo(db_session, user_id=test_user.id, asset_id=repeated.id)
    assert loaded.id == selected.id
    assert content == photo_catalog["path"].read_bytes()


def test_photo_reuse_api_rejects_corruption_without_mutation(
    client, auth_headers, db_session, photo_catalog
):
    photo_catalog["path"].write_bytes(b"x" * photo_catalog["path"].stat().st_size)
    response = client.post(
        "/api/v1/career-profile/photo",
        headers=auth_headers,
        files={"file": ("retry.jpg", photo_catalog["original"], "image/jpeg")},
    )
    assert response.status_code == 422
    assert "integrity check" in response.json()["detail"]
    db_session.expire_all()
    profile = db_session.get(CandidateProfile, photo_catalog["profile_id"])
    assert profile.photo_asset_id == photo_catalog["selected_id"]
    assert profile.revision == photo_catalog["revision"]
