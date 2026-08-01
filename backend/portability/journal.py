"""Restart-durable ownership journal for files published during restore."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal, Mapping, TypedDict, cast

from backend.core.config import settings
from backend.storage.atomic import (
    StorageWriteError,
    durable_mkdir,
    durable_replace,
    fsync_directory,
    read_stable_bounded_file,
    resolve_data_path,
)

_JOURNAL_VERSION = 1
_JOURNAL_PATH_MAX_CHARACTERS = 1024
_JOURNAL_FIXED_OVERHEAD_BYTES = 4 * 1024
_JOURNAL_MAX_ENCODED_BYTES_PER_PATH = _JOURNAL_PATH_MAX_CHARACTERS * 12 + 3


class JournalPayload(TypedDict):
    version: int
    generation: int
    user_id: int
    archive_fingerprint: str
    paths: list[str]


class RestoreJournal(JournalPayload):
    checksum: str


JournalCopyState = Literal["valid", "missing", "invalid"]


class RestoreJournalError(RuntimeError):
    pass


def _validated_user_id(user_id: int) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise RestoreJournalError("Invalid restore journal owner")
    return int(user_id)


def _journal_directory(user_id: int) -> Path:
    return resolve_data_path(f".restore/user-{_validated_user_id(user_id)}")


def _journal_path(user_id: int) -> Path:
    return _journal_directory(user_id) / "journal.json"


def _journal_backup_path(user_id: int) -> Path:
    return _journal_directory(user_id) / "journal.backup.json"


def _staging_directory(user_id: int) -> Path:
    return _journal_directory(user_id) / "staging"


def _normalized_paths(paths: list[str] | tuple[str, ...]) -> list[str]:
    if len(paths) > settings.PORTABLE_ARCHIVE_MAX_MEMBERS or any(
        not isinstance(path, str) or not path or len(path) > _JOURNAL_PATH_MAX_CHARACTERS
        for path in paths
    ):
        raise RestoreJournalError("Restore journal paths are invalid")
    normalized = sorted(set(paths))
    for path in normalized:
        if not (path.startswith("assets/") or path.startswith("resumes/")):
            raise RestoreJournalError("Restore journal path is outside managed file namespaces")
        try:
            resolve_data_path(path, create_root=False)
        except ValueError as exc:
            raise RestoreJournalError("Restore journal path escapes managed storage") from exc
    return normalized


def _journal_maximum_bytes() -> int:
    """Bound JSON allocation from the configured member and path ceilings."""

    return _JOURNAL_FIXED_OVERHEAD_BYTES + (
        settings.PORTABLE_ARCHIVE_MAX_MEMBERS * _JOURNAL_MAX_ENCODED_BYTES_PER_PATH
    )


def _canonical_payload_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _payload_checksum(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_payload_bytes(payload)).hexdigest()


def _decode_journal(user_id: int, raw: object) -> RestoreJournal:
    if not isinstance(raw, dict):
        raise RestoreJournalError("Restore journal is invalid")
    fingerprint = raw.get("archive_fingerprint")
    paths = raw.get("paths")
    checksum = raw.get("checksum")
    if (
        set(raw)
        != {
            "version",
            "generation",
            "user_id",
            "archive_fingerprint",
            "paths",
            "checksum",
        }
        or raw.get("version") != _JOURNAL_VERSION
        or isinstance(raw.get("generation"), bool)
        or not isinstance(raw.get("generation"), int)
        or raw["generation"] < 1
        or raw.get("user_id") != _validated_user_id(user_id)
        or not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint)
        or not isinstance(paths, list)
        or not isinstance(checksum, str)
    ):
        raise RestoreJournalError("Restore journal is invalid")
    payload = JournalPayload(
        version=_JOURNAL_VERSION,
        generation=raw["generation"],
        user_id=_validated_user_id(user_id),
        archive_fingerprint=fingerprint,
        paths=_normalized_paths(cast(list[str], paths)),
    )
    if not hmac.compare_digest(checksum, _payload_checksum(payload)):
        raise RestoreJournalError("Restore journal checksum is invalid")
    return RestoreJournal(**payload, checksum=checksum)


def _read_journal_copy(
    user_id: int,
    path: Path,
) -> tuple[JournalCopyState, RestoreJournal | BaseException]:
    try:
        raw = json.loads(
            read_stable_bounded_file(
                path,
                maximum_size=_journal_maximum_bytes(),
            ).decode("utf-8")
        )
        return "valid", _decode_journal(user_id, raw)
    except FileNotFoundError as exc:
        return "missing", exc
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        RestoreJournalError,
    ) as exc:
        return "invalid", exc


def read_restore_journal(user_id: int) -> RestoreJournal | None:
    copies = [
        _read_journal_copy(user_id, _journal_path(user_id)),
        _read_journal_copy(user_id, _journal_backup_path(user_id)),
    ]
    valid = [cast(RestoreJournal, value) for state, value in copies if state == "valid"]
    if len(valid) == 2:
        primary, backup = valid
        if primary == backup:
            return primary
        if (
            primary["archive_fingerprint"] != backup["archive_fingerprint"]
            or primary["user_id"] != backup["user_id"]
            or primary["generation"] == backup["generation"]
        ):
            raise RestoreJournalError("Restore journal copies disagree")
        newer, older = sorted(
            (primary, backup),
            key=lambda journal: journal["generation"],
            reverse=True,
        )
        if not set(older["paths"]).issubset(set(newer["paths"])):
            raise RestoreJournalError("Restore journal copies are not monotonic")
        return newer
    if len(valid) == 1:
        return valid[0]
    if all(state == "missing" for state, _value in copies):
        return None
    failure = next(value for state, value in copies if state == "invalid")
    assert isinstance(failure, BaseException)
    raise RestoreJournalError("Both restore journal copies are unavailable or invalid") from failure


def _clear_staging(user_id: int) -> None:
    staging = _staging_directory(user_id)
    try:
        shutil.rmtree(staging)
        fsync_directory(staging.parent)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RestoreJournalError("Restore staging could not be cleared") from exc


def _with_checksum(payload: Mapping[str, object]) -> RestoreJournal:
    canonical = JournalPayload(
        version=cast(int, payload["version"]),
        generation=cast(int, payload["generation"]),
        user_id=cast(int, payload["user_id"]),
        archive_fingerprint=cast(str, payload["archive_fingerprint"]),
        paths=cast(list[str], payload["paths"]),
    )
    return RestoreJournal(**canonical, checksum=_payload_checksum(canonical))


def prepare_restore_journal(
    user_id: int,
    archive_fingerprint: str,
    paths: list[str] | tuple[str, ...],
) -> None:
    archive_paths = _normalized_paths(paths)
    existing = read_restore_journal(user_id)
    if existing is not None:
        if existing["archive_fingerprint"] != archive_fingerprint or not set(
            existing["paths"]
        ).issubset(archive_paths):
            raise RestoreJournalError("A different restore operation owns the file journal")
        missing_paths = {path for path in archive_paths if not resolve_data_path(path).exists()}
        next_paths = sorted(set(existing["paths"]) | missing_paths)
        _clear_staging(user_id)
        payload = _with_checksum(
            JournalPayload(
                version=existing["version"],
                generation=existing["generation"] + 1,
                user_id=existing["user_id"],
                archive_fingerprint=existing["archive_fingerprint"],
                paths=next_paths,
            )
        )
    else:
        # Record only paths that this restore can create. The journal is durable
        # before the first atomic write, so erasure never removes an identical file
        # that predated this restore and no file-before-journal crash window exists.
        created_paths = [path for path in archive_paths if not resolve_data_path(path).exists()]
        if not created_paths:
            return
        payload = _with_checksum(
            JournalPayload(
                version=_JOURNAL_VERSION,
                generation=1,
                user_id=_validated_user_id(user_id),
                archive_fingerprint=archive_fingerprint,
                paths=_normalized_paths(created_paths),
            )
        )
    directory = _journal_directory(user_id)
    try:
        durable_mkdir(directory)
        for destination in (_journal_path(user_id), _journal_backup_path(user_id)):
            temporary_path: str | None = None
            try:
                handle, temporary_path = tempfile.mkstemp(prefix=".journal-", dir=directory)
                with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temporary:
                    json.dump(payload, temporary, sort_keys=True, separators=(",", ":"))
                    temporary.write("\n")
                    temporary.flush()
                    os.fsync(temporary.fileno())
                durable_replace(temporary_path, destination)
                fsync_directory(directory)
            except OSError:
                if temporary_path is not None:
                    Path(temporary_path).unlink(missing_ok=True)
                raise
    except OSError as exc:
        raise RestoreJournalError("Restore journal could not be persisted") from exc


def atomic_restore_write(
    user_id: int,
    relative_path: str,
    data: bytes,
) -> tuple[Path, bool]:
    """Publish restore-owned bytes from the per-user recoverable staging tree."""

    destination = resolve_data_path(relative_path)
    try:
        existing = read_stable_bounded_file(
            destination,
            expected_size=len(data),
            maximum_size=len(data),
        )
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        raise ValueError("Existing stored file does not match the requested content") from exc
    else:
        if not hmac.compare_digest(
            hashlib.sha256(existing).digest(),
            hashlib.sha256(data).digest(),
        ):
            raise ValueError("Existing stored file does not match the requested content")
        return destination, False

    journal = read_restore_journal(user_id)
    if journal is None or relative_path not in journal["paths"]:
        raise RestoreJournalError("Restore destination is not owned by the durable journal")

    temporary_path: str | None = None
    staging = _staging_directory(user_id)
    try:
        durable_mkdir(destination.parent)
        durable_mkdir(staging)
        handle, temporary_path = tempfile.mkstemp(
            prefix=f".write-{destination.name}-",
            dir=staging,
        )
        with os.fdopen(handle, "wb") as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        durable_replace(temporary_path, destination)
        fsync_directory(destination.parent)
        fsync_directory(staging)
        return destination, True
    except OSError as exc:
        try:
            if temporary_path is not None:
                Path(temporary_path).unlink(missing_ok=True)
                fsync_directory(staging)
        except OSError:
            pass
        raise StorageWriteError(
            "Local storage write failed; verify free disk space and folder access, then retry."
        ) from exc


def restore_journal_paths(user_id: int) -> set[str]:
    journal = read_restore_journal(user_id)
    if journal is None:
        return set()
    return set(journal["paths"])


def clear_restore_journal(user_id: int) -> None:
    directory = _journal_directory(user_id)
    try:
        shutil.rmtree(directory)
        fsync_directory(directory.parent)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RestoreJournalError("Restore journal could not be removed") from exc
    parent = directory.parent
    try:
        if not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass
