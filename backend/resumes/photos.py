import hashlib
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from backend.career.asset_publication import (
    begin_asset_publication_write,
    remove_asset_publication_journal,
    write_asset_publication_journal,
)
from backend.career.models import CandidateProfile, CareerAsset
from backend.career.repository import CareerProfileRepository
from backend.core.config import settings
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
        return asset, read_verified(
            asset.storage_path,
            asset.sha256,
            expected_size=asset.byte_size,
            maximum_size=settings.MAX_UPLOAD_FILE_SIZE,
        )
    except (OSError, ValueError) as exc:
        raise ResumeValidationError("The normalized photo failed its integrity check") from exc


def persist_normalized_profile_photo(
    db: Session,
    *,
    user_id: int,
    filename: str,
    normalized: bytes,
    width: int,
    height: int,
) -> PhotoAssetResponse:
    if (
        not normalized
        or width != settings.RESUME_PHOTO_EDGE_PX
        or height != settings.RESUME_PHOTO_EDGE_PX
        or len(normalized) > settings.MAX_UPLOAD_FILE_SIZE
    ):
        raise PhotoValidationError("The normalized photo does not satisfy the storage contract")
    digest = hashlib.sha256(normalized).hexdigest()
    begin_asset_publication_write(db)
    profile = CareerProfileRepository(db).get_by_user(user_id)
    if profile is None:
        db.rollback()
        raise PhotoValidationError("Create the career profile before uploading a photo")
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
        response = PhotoAssetResponse(
            id=existing.id,
            sha256=existing.sha256,
            byte_size=existing.byte_size,
            media_type="image/jpeg",
            width=width,
            height=height,
            profile_revision=profile.revision,
        )
        try:
            db.commit()
        except Exception as persist_error:
            db.rollback()
            try:
                begin_asset_publication_write(db)
                committed_profile = (
                    db.query(CandidateProfile)
                    .filter(
                        CandidateProfile.id == profile.id,
                        CandidateProfile.photo_asset_id == existing.id,
                    )
                    .one_or_none()
                )
                if committed_profile is not None:
                    recovered = PhotoAssetResponse(
                        id=existing.id,
                        sha256=existing.sha256,
                        byte_size=existing.byte_size,
                        media_type="image/jpeg",
                        width=width,
                        height=height,
                        profile_revision=committed_profile.revision,
                    )
                    db.rollback()
                    return recovered
            except Exception:
                db.rollback()
                raise persist_error
            db.rollback()
            raise persist_error
        return response

    relative_path = (Path("assets") / "photos" / digest[:2] / f"{digest}.jpg").as_posix()
    asset_id = str(uuid.uuid4())
    profile_id = profile.id
    journal_path: str | None = None
    safe_name = str(filename or "photo").replace("\\", "/").rsplit("/", 1)[-1]
    safe_name = (
        "".join(
            character for character in safe_name if ord(character) >= 32 and ord(character) != 127
        ).strip(" .")[:255]
        or "photo"
    )
    try:
        journal_path = write_asset_publication_journal(
            operation_id=asset_id,
            profile_id=profile_id,
            kind="profile_photo",
            storage_path=relative_path,
            sha256=digest,
            byte_size=len(normalized),
        )
        atomic_write(relative_path, normalized)
        asset = CareerAsset(
            id=asset_id,
            profile_id=profile_id,
            kind="profile_photo",
            original_name=safe_name,
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
        response = PhotoAssetResponse(
            id=asset.id,
            sha256=digest,
            byte_size=len(normalized),
            media_type="image/jpeg",
            width=width,
            height=height,
            profile_revision=profile.revision,
        )
        db.commit()
    except Exception as persist_error:
        db.rollback()
        try:
            begin_asset_publication_write(db)
            committed_asset = (
                db.query(CareerAsset)
                .filter(
                    CareerAsset.id == asset_id,
                    CareerAsset.profile_id == profile_id,
                    CareerAsset.kind == "profile_photo",
                    CareerAsset.storage_path == relative_path,
                    CareerAsset.sha256 == digest,
                    CareerAsset.byte_size == len(normalized),
                )
                .one_or_none()
            )
            committed_profile = db.get(CandidateProfile, profile_id)
            if (
                committed_asset is not None
                and committed_profile is not None
                and committed_profile.photo_asset_id == asset_id
            ):
                recovered = PhotoAssetResponse(
                    id=committed_asset.id,
                    sha256=committed_asset.sha256,
                    byte_size=committed_asset.byte_size,
                    media_type="image/jpeg",
                    width=width,
                    height=height,
                    profile_revision=committed_profile.revision,
                )
                db.rollback()
                return recovered
        except Exception:
            db.rollback()
            raise persist_error
        db.rollback()
        raise persist_error
    else:
        if journal_path is not None:
            try:
                remove_asset_publication_journal(journal_path)
            except Exception:
                # The committed row owns the bytes. A later locked reconcile
                # can remove this redundant recovery record.
                pass
        return response


def store_profile_photo(
    db: Session,
    *,
    user_id: int,
    filename: str,
    data: bytes,
) -> PhotoAssetResponse:
    normalized, width, height = normalize_photo(data)
    return persist_normalized_profile_photo(
        db,
        user_id=user_id,
        filename=filename,
        normalized=normalized,
        width=width,
        height=height,
    )
