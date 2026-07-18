import hashlib
from dataclasses import dataclass
from pathlib import Path

from backend.storage.atomic import atomic_write, resolve_data_path


@dataclass(frozen=True)
class StoredArtifact:
    relative_path: str
    absolute_path: Path
    sha256: str
    byte_size: int
    created: bool


def store_resume_artifact(
    *, profile_id: str, version_id: str, format: str, data: bytes
) -> StoredArtifact:
    if format not in {"pdf", "docx"}:
        raise ValueError("Unsupported resume artifact format")
    digest = hashlib.sha256(data).hexdigest()
    relative_path = (Path("resumes") / profile_id / version_id / f"{digest}.{format}").as_posix()
    absolute_path, created = atomic_write(relative_path, data)
    return StoredArtifact(
        relative_path=relative_path,
        absolute_path=absolute_path,
        sha256=digest,
        byte_size=len(data),
        created=created,
    )


def remove_stored_artifact(relative_path: str) -> None:
    resolve_data_path(relative_path).unlink(missing_ok=True)
