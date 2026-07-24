from __future__ import annotations

from sqlalchemy.orm import Session

from backend.desktop.lifecycle import VaultLockTimeout, desktop_vault_lock
from backend.portability.archive import ArchiveConflictError, _validated_members
from backend.portability.manifest import sha256
from backend.portability.restore import (
    _assert_decoded_ids_available,
    _assert_empty_vault,
    _decode_payload,
    _file_destinations_available,
    _prepare_file_writes,
)
from backend.portability.schemas import (
    ArchiveInspection,
    ArchiveVerificationCode,
    ArchiveWarningCode,
)

VERIFICATION_CODES: list[ArchiveVerificationCode] = [
    "manifest_verified",
    "members_verified",
    "records_verified",
    "relationships_verified",
    "file_bindings_verified",
]


def inspect_archive(
    db: Session,
    user_id: int,
    data: bytes,
) -> ArchiveInspection:
    """Validate a portable archive without changing the active vault."""

    try:
        with desktop_vault_lock():
            manifest, members = _validated_members(data)
            decoded, bindings, _preference_state, _projection_contract = _decode_payload(
                db,
                manifest,
                members,
                enforce_destination_ids=False,
            )
            writes = _prepare_file_writes(
                decoded,
                bindings,
                members,
                create_data_root=False,
            )

            warning_codes: list[ArchiveWarningCode] = [
                "archive_not_encrypted",
                "archive_not_authenticated",
            ]
            if any(
                manifest.record_counts.get(name, 0)
                for name in ("jobs", "coach_messages", "ai_executions")
            ):
                warning_codes.append("ai_output_requires_revalidation")

            restorable = True
            try:
                _assert_empty_vault(db, user_id, manifest.format_version)
            except ArchiveConflictError:
                restorable = False
                warning_codes.append("restore_requires_empty_vault")
            if restorable:
                try:
                    _assert_decoded_ids_available(db, decoded)
                except ArchiveConflictError:
                    restorable = False
                    warning_codes.append("restore_target_conflict")
            if restorable and not _file_destinations_available(writes):
                restorable = False
                warning_codes.append("restore_target_conflict")
    except VaultLockTimeout as exc:
        raise ArchiveConflictError(str(exc)) from exc

    record_counts = {name: manifest.record_counts[name] for name in sorted(manifest.record_counts)}
    return ArchiveInspection(
        archive_sha256=sha256(data),
        archive_bytes=len(data),
        format_version=manifest.format_version,
        created_at=manifest.created_at,
        record_counts=record_counts,
        total_records=sum(record_counts.values()),
        file_count=len(writes),
        file_bytes=sum(len(file_data) for _storage_path, file_data in writes),
        compatible=True,
        restorable=restorable,
        verification_codes=VERIFICATION_CODES,
        warning_codes=warning_codes,
    )
