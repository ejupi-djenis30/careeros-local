"""Bounded owned packet storage and restart recovery under the vault writer lock."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from backend.applications.exports import MAX_DOSSIER_BUNDLE_BYTES
from backend.applications.models import ApplicationPacketArtifact
from backend.career.models import CareerAsset
from backend.core.config import settings
from backend.resumes.models import ResumeArtifact
from backend.storage.atomic import (
    StorageWriteError,
    atomic_write,
    durable_unlink,
    read_stable_bounded_file,
    resolve_data_path,
)

_PACKET_JOURNAL_DIRECTORY = "applications/.packet-journal"
MAX_PACKET_JOURNALS = 1000


@dataclass(frozen=True)
class StoredPacketArtifact:
    relative_path: str
    absolute_path: Path
    sha256: str
    byte_size: int
    created: bool


@dataclass(frozen=True)
class PacketJournal:
    application_id: str
    dossier_id: str
    storage_path: str
    sha256: str
    byte_size: int


def _uuid(value: str) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Packet identity is not a canonical UUID")
    return value


def packet_artifact_path(*, application_id: str, dossier_id: str, sha256: str) -> str:
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(c not in "0123456789abcdef" for c in sha256)
    ):
        raise ValueError("Packet digest is invalid")
    return f"applications/{_uuid(application_id)}/packets/{_uuid(dossier_id)}/{sha256}.zip"


def _packet_journal_path(dossier_id: str) -> str:
    return f"{_PACKET_JOURNAL_DIRECTORY}/{_uuid(dossier_id)}.json"


def write_packet_journal(
    *, application_id: str, dossier_id: str, relative_path: str, sha256: str, byte_size: int
) -> str:
    if relative_path != packet_artifact_path(
        application_id=application_id, dossier_id=dossier_id, sha256=sha256
    ):
        raise ValueError("Packet storage identity is inconsistent")
    if isinstance(byte_size, bool) or not 0 < byte_size <= MAX_DOSSIER_BUNDLE_BYTES:
        raise ValueError("Packet size is invalid")
    payload = dict(
        version=1,
        application_id=application_id,
        dossier_id=dossier_id,
        storage_path=relative_path,
        sha256=sha256,
        byte_size=byte_size,
    )
    relative = _packet_journal_path(dossier_id)
    atomic_write(relative, json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return relative


def remove_packet_journal(dossier_id: str) -> bool:
    return durable_unlink(resolve_data_path(_packet_journal_path(dossier_id), create_root=False))


def all_packet_journals() -> list[PacketJournal]:
    directory = resolve_data_path(_PACKET_JOURNAL_DIRECTORY, create_root=False)
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise StorageWriteError("Packet recovery directory is invalid")
    result = []
    for count, path in enumerate(directory.iterdir(), 1):
        if count > MAX_PACKET_JOURNALS:
            raise StorageWriteError("Too many pending packet recovery records")
        if path.suffix != ".json":
            continue
        try:
            raw = json.loads(read_stable_bounded_file(path, maximum_size=4096))
            if (
                set(raw)
                != {
                    "version",
                    "application_id",
                    "dossier_id",
                    "storage_path",
                    "sha256",
                    "byte_size",
                }
                or type(raw["version"]) is not int
                or raw["version"] != 1
            ):
                raise ValueError("Invalid journal fields")
            journal = PacketJournal(**{k: v for k, v in raw.items() if k != "version"})
            expected = packet_artifact_path(
                application_id=journal.application_id,
                dossier_id=journal.dossier_id,
                sha256=journal.sha256,
            )
            if (
                journal.storage_path != expected
                or path.name != f"{journal.dossier_id}.json"
                or isinstance(journal.byte_size, bool)
                or not isinstance(journal.byte_size, int)
                or not 0 < journal.byte_size <= MAX_DOSSIER_BUNDLE_BYTES
            ):
                raise ValueError("Invalid journal metadata")
            result.append(journal)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise StorageWriteError("Packet recovery metadata is invalid") from exc
    return result


def read_verified_packet_artifact(
    relative_path: str, *, expected_sha256: str, expected_size: int
) -> bytes:
    if isinstance(expected_size, bool) or not 0 < expected_size <= MAX_DOSSIER_BUNDLE_BYTES:
        raise ValueError("Packet size is invalid")
    data = read_stable_bounded_file(
        resolve_data_path(relative_path, create_root=False),
        maximum_size=MAX_DOSSIER_BUNDLE_BYTES,
        expected_size=expected_size,
    )
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Stored packet artifact digest verification failed")
    return data


def reconcile_packet_journals(db: Session) -> int:
    """Caller holds desktop_vault_lock and a database writer reservation.

    Never delete a path claimed by any committed record. Validate the complete
    recovery set before touching files, and retain each journal if cleanup fails.
    """
    if not db.in_transaction():
        raise StorageWriteError("Packet recovery requires the vault writer transaction")
    journals = all_packet_journals()
    if (
        sum(journal.byte_size for journal in journals)
        > settings.PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES
    ):
        raise StorageWriteError("Packet recovery bytes exceed the configured safety limit")
    validated = []
    for journal in journals:
        if any(
            db.query(model.id).filter(model.storage_path == journal.storage_path).first()
            for model in (CareerAsset, ResumeArtifact)
        ):
            raise StorageWriteError("Packet recovery conflicts with another stored document")
        rows = (
            db.query(ApplicationPacketArtifact)
            .filter(ApplicationPacketArtifact.storage_path == journal.storage_path)
            .all()
        )
        for row in rows:
            if (
                row.application_id != journal.application_id
                or row.dossier_id != journal.dossier_id
                or row.sha256 != journal.sha256
                or row.byte_size != journal.byte_size
            ):
                raise StorageWriteError("Packet recovery conflicts with committed ownership")
        try:
            read_verified_packet_artifact(
                journal.storage_path,
                expected_sha256=journal.sha256,
                expected_size=journal.byte_size,
            )
            exists = True
        except FileNotFoundError:
            if rows:
                raise StorageWriteError("Committed packet bytes are missing") from None
            exists = False
        validated.append((journal, bool(rows), exists))
    for journal, committed, exists in validated:
        if not committed and exists:
            durable_unlink(resolve_data_path(journal.storage_path, create_root=False))
        remove_packet_journal(journal.dossier_id)
    return len(journals)


def rollback_packet_artifact(relative_path: str, dossier_id: str, *, db: Session) -> None:
    """Recover an uncommitted write only through validated journal ownership."""
    journals = [j for j in all_packet_journals() if j.dossier_id == dossier_id]
    if any(j.storage_path != relative_path for j in journals):
        raise StorageWriteError("Packet rollback identity is inconsistent")
    reconcile_packet_journals(db)


def store_packet_artifact(
    *, application_id: str, dossier_id: str, data: bytes
) -> StoredPacketArtifact:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_DOSSIER_BUNDLE_BYTES:
        raise ValueError("Packet artifact has an invalid byte size")
    digest = hashlib.sha256(data).hexdigest()
    relative_path = packet_artifact_path(
        application_id=application_id, dossier_id=dossier_id, sha256=digest
    )
    write_packet_journal(
        application_id=application_id,
        dossier_id=dossier_id,
        relative_path=relative_path,
        sha256=digest,
        byte_size=len(data),
    )
    absolute_path, created = atomic_write(relative_path, data)
    return StoredPacketArtifact(relative_path, absolute_path, digest, len(data), created)
