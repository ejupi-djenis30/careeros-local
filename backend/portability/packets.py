"""Verify immutable packet archives, including their nested bounded manifest."""

from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Any

from backend.applications.exports import (
    MAX_DOSSIER_ARTIFACT_BYTES,
    MAX_DOSSIER_BUNDLE_BYTES,
    MAX_DOSSIER_EVENT_BYTES,
    MAX_DOSSIER_MANIFEST_BYTES,
)
from backend.applications.packet_storage import packet_artifact_path
from backend.applications.schemas import EmailDraft, GenerationProvenance, LetterOptions
from backend.core.json_safety import strict_json_loads
from backend.portability.manifest import canonical_json, sha256

_MEMBER_NAMES = frozenset(
    {
        "application.json",
        "answers.json",
        "checklist.json",
        "requirement-evidence.json",
        "cover-letter.txt",
        "resume.pdf",
        "resume.docx",
        "cover_letter.pdf",
        "cover_letter.docx",
        "email_draft.eml",
        "email_checklist.txt",
        "source_advert.json",
        "material-evidence.json",
        "manifest.json",
    }
)


def packet_dossier(
    record: dict[str, Any], tables: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    events = [row for row in tables["application_events"] if row["id"] == record["dossier_id"]]
    if len(events) != 1:
        raise ValueError("Packet publication event is missing")
    event = events[0]
    payload = event.get("payload")
    dossier = payload.get("dossier") if isinstance(payload, dict) else None
    if (
        event.get("application_id") != record.get("application_id")
        or event.get("event_type") != "dossier_published"
        or not isinstance(dossier, dict)
        or dossier.get("schema_version") != "3.0"
        or dossier.get("resume_version_id") not in {row["id"] for row in tables["resume_versions"]}
        or record.get("media_type") != "application/zip"
        or record.get("storage_path")
        != packet_artifact_path(
            application_id=record["application_id"],
            dossier_id=record["dossier_id"],
            sha256=record["sha256"],
        )
    ):
        raise ValueError("Packet publication relationship is invalid")
    manifest = dossier.get("manifest")
    if not isinstance(manifest, dict) or len(canonical_json(payload)) > MAX_DOSSIER_EVENT_BYTES:
        raise ValueError("Packet publication metadata is invalid")
    for field, schema in (
        ("generation_provenance", GenerationProvenance),
        ("letter_options", LetterOptions),
        ("email_draft", EmailDraft),
    ):
        if manifest.get(field) != dossier.get(field):
            raise ValueError("Packet metadata disagrees with its manifest")
        if dossier.get(field) is not None:
            schema.model_validate(dossier[field])
    return dossier


def validate_packet_records(tables: dict[str, list[dict[str, Any]]]) -> None:
    claimed = set()
    for record in tables["application_packet_artifacts"]:
        packet_dossier(record, tables)
        key = (record["application_id"], record["dossier_id"])
        if key in claimed:
            raise ValueError("Duplicate packet publication")
        claimed.add(key)
    for event in tables["application_events"]:
        payload = event.get("payload")
        dossier = payload.get("dossier") if isinstance(payload, dict) else None
        if (
            event.get("event_type") == "dossier_published"
            and isinstance(dossier, dict)
            and dossier.get("schema_version") == "3.0"
            and (event["application_id"], event["id"]) not in claimed
        ):
            raise ValueError("Published packet bytes are missing")


def validate_packet_bytes(
    record: dict[str, Any], data: bytes, tables: dict[str, list[dict[str, Any]]]
) -> None:
    dossier = packet_dossier(record, tables)
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (
                not set(names).issubset(_MEMBER_NAMES)
                or not {
                    "application.json",
                    "answers.json",
                    "checklist.json",
                    "requirement-evidence.json",
                    "manifest.json",
                }.issubset(names)
                or not {"resume.pdf", "resume.docx"}.intersection(names)
            ):
                raise ValueError("Packet artifact set is invalid")
            if (
                len(infos) > 32
                or len(names) != len(set(names))
                or sum(info.file_size for info in infos) > MAX_DOSSIER_BUNDLE_BYTES
            ):
                raise ValueError("Packet member bounds are invalid")
            for info in infos:
                if (
                    "/" in info.filename
                    or "\\" in info.filename
                    or ":" in info.filename
                    or info.filename in {"", ".", ".."}
                    or info.flag_bits & 1
                    or info.is_dir()
                    or (info.external_attr >> 16) & 0o170000 == 0o120000
                    or info.file_size > MAX_DOSSIER_ARTIFACT_BYTES
                ):
                    raise ValueError("Unsafe packet member")
            info = archive.getinfo("manifest.json")
            if info.file_size > MAX_DOSSIER_MANIFEST_BYTES:
                raise ValueError("Packet manifest exceeds its limit")
            raw = archive.read(info)
            manifest = strict_json_loads(raw)
            if (
                not isinstance(manifest, dict)
                or manifest != dossier.get("manifest")
                or sha256(raw) != dossier.get("manifest_sha256")
                or manifest.get("kind") != "careeros_application_dossier"
                or manifest.get("schema_version") != "3.0"
                or manifest.get("dossier_id") != record["dossier_id"]
                or manifest.get("application_id") != record["application_id"]
                or manifest.get("resume_version_id") != dossier.get("resume_version_id")
            ):
                raise ValueError("Packet manifest identity is inconsistent")
            entries = manifest.get("entries")
            if not isinstance(entries, list) or len(entries) != len(infos) - 1:
                raise ValueError("Packet manifest entries are invalid")
            bound = set()
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {
                    "path",
                    "sha256",
                    "byte_size",
                    "media_type",
                }:
                    raise ValueError("Packet manifest entry is invalid")
                name = entry["path"]
                if not isinstance(name, str) or name == "manifest.json" or name in bound:
                    raise ValueError("Packet member binding is invalid")
                content = archive.read(name)
                if (
                    type(entry["byte_size"]) is not int
                    or len(content) != entry["byte_size"]
                    or sha256(content) != entry["sha256"]
                ):
                    raise ValueError("Packet member checksum is invalid")
                bound.add(name)
            if bound != set(names) - {"manifest.json"}:
                raise ValueError("Packet contains unbound members")
    except (zipfile.BadZipFile, KeyError, TypeError, UnicodeDecodeError, RuntimeError) as exc:
        raise ValueError("Invalid packet archive") from exc
