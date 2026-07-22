"""Deterministic, local exports for application tasks and dossiers."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.applications.schemas import ApplicationTaskResponse

MAX_DOSSIER_EVENT_BYTES = 512 * 1024
MAX_DOSSIER_BUNDLE_BYTES = 32 * 1024 * 1024
MAX_DOSSIER_ARTIFACT_BYTES = 16 * 1024 * 1024


class DossierSizeError(ValueError):
    """Raised before an oversized dossier is persisted or returned."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_entry(archive: zipfile.ZipFile, path: str, data: bytes) -> None:
    info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    info.create_system = 3
    archive.writestr(info, data)


@dataclass(frozen=True)
class DossierBundle:
    data: bytes
    sha256: str
    manifest: dict[str, Any]
    manifest_sha256: str


def build_dossier_bundle(
    *,
    dossier_id: str,
    version_number: int,
    application_revision: int,
    application_id: str,
    created_at: str,
    role: dict[str, Any],
    resume_version_id: str,
    readiness: dict[str, Any],
    cover_letter: str | None,
    answers: list[dict[str, Any]],
    checklist: list[dict[str, Any]],
    requirement_matrix: list[dict[str, Any]],
    evidence_catalog: dict[str, dict[str, Any]] | None = None,
    resume_artifacts: dict[str, tuple[bytes, str]],
) -> DossierBundle:
    """Build a byte-stable application dossier and its canonical manifest."""

    files: dict[str, tuple[bytes, str]] = {
        "application.json": (
            canonical_json(
                {
                    "application_id": application_id,
                    "application_revision": application_revision,
                    "role": role,
                    "readiness": readiness,
                }
            ),
            "application/json",
        ),
        "answers.json": (canonical_json(answers), "application/json"),
        "checklist.json": (canonical_json(checklist), "application/json"),
        "requirement-evidence.json": (
            canonical_json(
                {
                    "schema_version": "2.0",
                    "requirements": requirement_matrix,
                    "evidence_catalog": evidence_catalog,
                }
                if evidence_catalog is not None
                else requirement_matrix
            ),
            "application/json",
        ),
    }
    if cover_letter:
        files["cover-letter.txt"] = (cover_letter.encode("utf-8"), "text/plain; charset=utf-8")
    for artifact_format, (data, media_type) in sorted(resume_artifacts.items()):
        if len(data) > MAX_DOSSIER_ARTIFACT_BYTES:
            raise DossierSizeError(
                f"The {artifact_format.upper()} resume artifact exceeds "
                f"{MAX_DOSSIER_ARTIFACT_BYTES} bytes"
            )
        files[f"resume.{artifact_format}"] = (data, media_type)

    raw_file_bytes = sum(len(data) for data, _media_type in files.values())
    if raw_file_bytes > MAX_DOSSIER_BUNDLE_BYTES:
        raise DossierSizeError(
            f"Dossier files exceed the {MAX_DOSSIER_BUNDLE_BYTES}-byte bundle limit"
        )

    entries = [
        {
            "path": path,
            "media_type": media_type,
            "byte_size": len(data),
            "sha256": _sha256(data),
        }
        for path, (data, media_type) in sorted(files.items())
    ]
    manifest = {
        "schema_version": "2.0" if evidence_catalog is not None else "1.0",
        "kind": "careeros_application_dossier",
        "dossier_id": dossier_id,
        "version_number": version_number,
        "application_id": application_id,
        "application_revision": application_revision,
        "resume_version_id": resume_version_id,
        "created_at": created_at,
        "entries": entries,
    }
    manifest_data = canonical_json(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, (data, _media_type) in sorted(files.items()):
            _zip_entry(archive, path, data)
        _zip_entry(archive, "manifest.json", manifest_data)
    bundle = output.getvalue()
    if len(bundle) > MAX_DOSSIER_BUNDLE_BYTES:
        raise DossierSizeError(
            f"Dossier archive exceeds the {MAX_DOSSIER_BUNDLE_BYTES}-byte bundle limit"
        )
    return DossierBundle(
        data=bundle,
        sha256=_sha256(bundle),
        manifest=manifest,
        manifest_sha256=_sha256(manifest_data),
    )


def _ics_escape(value: object) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _ics_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fold_ics_line(line: str) -> str:
    """Fold one content line without splitting a UTF-8 code point."""

    chunks: list[str] = []
    current = ""
    limit = 75
    for character in line:
        if current and len(f"{current}{character}".encode("utf-8")) > limit:
            chunks.append(current)
            current = character
            limit = 74  # Continuation lines begin with one required space.
        else:
            current += character
    chunks.append(current)
    return "\r\n ".join(chunks)


def export_task_calendar(
    application_id: str,
    role_title: str,
    company: str,
    tasks: list[ApplicationTaskResponse],
) -> bytes:
    """Export pending dated tasks as a portable RFC 5545 calendar."""

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CareerOS Local//Application Tasks 1.0//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(role_title)} · {_ics_escape(company)}",
    ]
    for task in tasks:
        if task.status != "pending" or task.due_at is None:
            continue
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{task.id}@careeros.local",
                f"DTSTAMP:{_ics_timestamp(task.updated_at)}",
                f"DTSTART:{_ics_timestamp(task.due_at)}",
                f"SUMMARY:{_ics_escape(task.title)}",
                f"DESCRIPTION:{_ics_escape(role_title)} at {_ics_escape(company)}",
                f"CATEGORIES:CAREEROS,{task.priority.upper()}",
            ]
        )
        if task.reminder_at is not None:
            seconds = max(0, int((task.due_at - task.reminder_at).total_seconds()))
            lines.extend(
                [
                    "BEGIN:VALARM",
                    f"TRIGGER:-PT{seconds}S",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_ics_escape(task.title)}",
                    "END:VALARM",
                ]
            )
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return ("\r\n".join(_fold_ics_line(line) for line in lines) + "\r\n").encode("utf-8")
