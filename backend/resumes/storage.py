import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from backend.storage.atomic import (
    StorageWriteError,
    atomic_write,
    durable_unlink,
    read_stable_bounded_file,
    resolve_data_path,
)

RESUME_DELETE_PENDING_KEY = "_careeros_resume_delete_pending_v1"
_PUBLICATION_JOURNAL_DIRECTORY = "resumes/.publication-journal"
_PUBLICATION_JOURNAL_VERSION = 1
_PUBLICATION_JOURNAL_SCAN_LIMIT = 10_000
_PUBLICATION_JOURNAL_MAX_BYTES = 16 * 1024


@dataclass(frozen=True)
class StoredArtifact:
    relative_path: str
    absolute_path: Path
    sha256: str
    byte_size: int
    created: bool


@dataclass(frozen=True)
class ResumePublicationJournal:
    draft_id: str
    version_id: str
    artifact_paths: tuple[str, ...]
    relative_path: str


def resume_artifact_path(*, profile_id: str, version_id: str, format: str, sha256: str) -> str:
    return (Path("resumes") / profile_id / version_id / f"{sha256}.{format}").as_posix()


def store_resume_artifact(
    *, profile_id: str, version_id: str, format: str, data: bytes
) -> StoredArtifact:
    if format not in {"pdf", "docx"}:
        raise ValueError("Unsupported resume artifact format")
    digest = hashlib.sha256(data).hexdigest()
    relative_path = resume_artifact_path(
        profile_id=profile_id,
        version_id=version_id,
        format=format,
        sha256=digest,
    )
    absolute_path, created = atomic_write(relative_path, data)
    return StoredArtifact(
        relative_path=relative_path,
        absolute_path=absolute_path,
        sha256=digest,
        byte_size=len(data),
        created=created,
    )


def is_resume_delete_pending(generation_context: object) -> bool:
    return isinstance(generation_context, dict) and generation_context.get(
        RESUME_DELETE_PENDING_KEY
    ) == {"version": 1}


def remove_stored_artifact(relative_path: str) -> bool:
    """Durably remove one artifact without recreating a missing data root."""

    return durable_unlink(resolve_data_path(relative_path, create_root=False))


def _publication_journal_path(version_id: str) -> str:
    if (
        not version_id
        or len(version_id) > 100
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
            for character in version_id
        )
    ):
        raise ValueError("Resume publication identifiers must be filesystem-safe")
    return f"{_PUBLICATION_JOURNAL_DIRECTORY}/{version_id}.json"


def _validate_journal_artifact_path(relative_path: str, version_id: str) -> None:
    resolved = resolve_data_path(relative_path, create_root=False)
    parts = Path(relative_path).parts
    if (
        len(parts) != 4
        or parts[0] != "resumes"
        or parts[2] != version_id
        or resolved.name != parts[3]
    ):
        raise ValueError("Invalid resume artifact recovery path")
    digest, separator, artifact_format = parts[3].partition(".")
    if (
        separator != "."
        or artifact_format not in {"pdf", "docx"}
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("Invalid resume artifact recovery path")


def write_resume_publication_journal(
    *, draft_id: str, version_id: str, artifact_paths: Iterable[str]
) -> str:
    """Durably own prospective artifact paths before any of them are published."""

    paths = tuple(sorted(set(artifact_paths)))
    if not isinstance(draft_id, str) or not draft_id or len(draft_id) > 100:
        raise ValueError("Invalid resume publication journal")
    if not paths or len(paths) > 4:
        raise ValueError("Invalid resume publication journal")
    for path in paths:
        _validate_journal_artifact_path(path, version_id)
    relative_path = _publication_journal_path(version_id)
    payload = json.dumps(
        {
            "artifact_paths": paths,
            "draft_id": draft_id,
            "schema_version": _PUBLICATION_JOURNAL_VERSION,
            "version_id": version_id,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    atomic_write(relative_path, payload)
    return relative_path


def _load_resume_publication_journal(path: Path) -> ResumePublicationJournal:
    try:
        payload = json.loads(
            read_stable_bounded_file(
                path,
                maximum_size=_PUBLICATION_JOURNAL_MAX_BYTES,
            ).decode("utf-8")
        )
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("Unsupported resume publication journal")
        draft_id = payload.get("draft_id")
        version_id = payload.get("version_id")
        artifact_paths = payload.get("artifact_paths")
        if (
            not isinstance(draft_id, str)
            or not draft_id
            or len(draft_id) > 100
            or not isinstance(version_id, str)
            or path.name != f"{version_id}.json"
            or not isinstance(artifact_paths, list)
            or not artifact_paths
            or len(artifact_paths) > 4
            or any(not isinstance(item, str) for item in artifact_paths)
        ):
            raise ValueError("Malformed resume publication journal")
        for artifact_path in artifact_paths:
            _validate_journal_artifact_path(artifact_path, version_id)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise StorageWriteError(
            "Resume publication recovery metadata is invalid; verify the local data directory."
        ) from exc
    return ResumePublicationJournal(
        draft_id=draft_id,
        version_id=version_id,
        artifact_paths=tuple(artifact_paths),
        relative_path=f"{_PUBLICATION_JOURNAL_DIRECTORY}/{path.name}",
    )


def all_resume_publication_journals() -> list[ResumePublicationJournal]:
    """Return every bounded, validated publication recovery record.

    Account erasure needs one coherent view of the journal namespace so it can
    distinguish records owned by the profile being removed from records owned
    by another local profile. Count every directory entry, not only ``.json``
    files, so unexpected crash residue cannot turn this into an unbounded scan.
    """

    directory = resolve_data_path(_PUBLICATION_JOURNAL_DIRECTORY, create_root=False)
    if not directory.exists():
        return []
    if not directory.is_dir() or directory.is_symlink():
        raise StorageWriteError(
            "Resume publication recovery metadata is invalid; verify the local data directory."
        )
    paths: list[Path] = []
    try:
        for entry_count, path in enumerate(directory.iterdir(), start=1):
            if entry_count > _PUBLICATION_JOURNAL_SCAN_LIMIT:
                raise StorageWriteError("Too many pending resume publication recovery records")
            if path.suffix == ".json":
                paths.append(path)
    except StorageWriteError:
        raise
    except OSError as exc:
        raise StorageWriteError(
            "Resume publication recovery metadata could not be scanned; "
            "verify the local data directory."
        ) from exc
    return [_load_resume_publication_journal(path) for path in sorted(paths)]


def resume_publication_journals(draft_id: str) -> list[ResumePublicationJournal]:
    return [
        journal for journal in all_resume_publication_journals() if journal.draft_id == draft_id
    ]


def reconcile_resume_publication_journals(*, draft_id: str, committed_version_ids: set[str]) -> int:
    """Resolve crash-left journals while the caller holds the draft writer lock."""

    reconciled = 0
    for journal in resume_publication_journals(draft_id):
        if journal.version_id not in committed_version_ids:
            for artifact_path in journal.artifact_paths:
                remove_stored_artifact(artifact_path)
        remove_resume_publication_journal(journal.relative_path)
        reconciled += 1
    return reconciled


def remove_resume_publication_journal(relative_path: str) -> bool:
    expected_parent = resolve_data_path(_PUBLICATION_JOURNAL_DIRECTORY, create_root=False)
    path = resolve_data_path(relative_path, create_root=False)
    if path.parent != expected_parent:
        raise ValueError("Invalid resume publication journal path")
    return durable_unlink(path)
