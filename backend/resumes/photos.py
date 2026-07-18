import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from backend.career.models import CareerAsset
from backend.career.repository import CareerProfileRepository
from backend.resumes.exceptions import ResumeNotFoundError, ResumeValidationError
from backend.resumes.renderers.photo import PhotoValidationError, normalize_photo
from backend.resumes.schemas import PhotoAssetResponse
from backend.storage.atomic import atomic_write, read_verified


def load_profile_photo(
    db: Session,
    *,
    user_id: int,
    asset_id: str,
) -> tuple[CareerAsset, bytes]:
    profile = CareerProfileRepository(db).get_by_user(user_id)
    if profile is None:
        raise ResumeNotFoundError("Profile photo not found")
    asset = (
        db.query(CareerAsset)
        .filter(
            CareerAsset.id == asset_id,
            CareerAsset.profile_id == profile.id,
            CareerAsset.kind == "profile_photo",
            CareerAsset.normalized.is_(True),
        )
        .first()
    )
    if asset is None:
        raise ResumeNotFoundError("Profile photo not found")
    try:
        return asset, read_verified(asset.storage_path, asset.sha256)
    except (OSError, ValueError) as exc:
        raise ResumeValidationError("The normalized photo failed its integrity check") from exc


def store_profile_photo(
    db: Session,
    *,
    user_id: int,
    filename: str,
    data: bytes,
) -> PhotoAssetResponse:
    profile = CareerProfileRepository(db).get_by_user(user_id)
    if profile is None:
        raise PhotoValidationError("Create the career profile before uploading a photo")
    normalized, width, height = normalize_photo(data)
    digest = hashlib.sha256(normalized).hexdigest()
    existing = (
        db.query(CareerAsset)
        .filter(
            CareerAsset.profile_id == profile.id,
            CareerAsset.sha256 == digest,
            CareerAsset.kind == "profile_photo",
        )
        .first()
    )
    if existing is not None:
        if profile.photo_asset_id != existing.id:
            profile.photo_asset_id = existing.id
            profile.revision += 1
            db.commit()
        return PhotoAssetResponse(
            id=existing.id,
            sha256=existing.sha256,
            byte_size=existing.byte_size,
            media_type="image/jpeg",
            width=width,
            height=height,
            profile_revision=profile.revision,
        )

    relative_path = (Path("assets") / "photos" / digest[:2] / f"{digest}.jpg").as_posix()
    absolute_path, created = atomic_write(relative_path, normalized)
    try:
        asset = CareerAsset(
            profile_id=profile.id,
            kind="profile_photo",
            original_name=Path(filename or "photo").name[:255],
            media_type="image/jpeg",
            sha256=digest,
            byte_size=len(normalized),
            storage_path=relative_path,
            normalized=True,
        )
        db.add(asset)
        db.flush()
        profile.photo_asset_id = asset.id
        profile.revision += 1
        db.commit()
        db.refresh(asset)
        return PhotoAssetResponse(
            id=asset.id,
            sha256=digest,
            byte_size=len(normalized),
            media_type="image/jpeg",
            width=width,
            height=height,
            profile_revision=profile.revision,
        )
    except Exception:
        db.rollback()
        if created:
            absolute_path.unlink(missing_ok=True)
        raise
