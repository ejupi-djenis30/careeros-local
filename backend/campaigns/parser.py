"""Canonical campaign archive parser and reconciliation representation."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from backend.campaigns.archive_policy import (
    ArchivePolicyError,
    CampaignArchiveMember,
    inspect_and_validate_campaign_archive,
)
from backend.campaigns.parser_types import (
    ParsedApplication,
    ParsedArtifact,
    ParsedCampaign,
    freeze_value,
)
from backend.campaigns.reconciliation import (
    classify_artifact_category,
    reconcile_dossier_directory_name,
)
from backend.campaigns.tracker_sanitizer import sanitize_tracker_workbook
from backend.campaigns.vacancy_parser import parse_vacancy_markdown
from backend.campaigns.xlsx_reader import TrackerApplicationRow, read_campaign_workbook

__all__ = [
    "ParsedApplication",
    "ParsedArtifact",
    "ParsedCampaign",
    "classify_artifact_category",
    "parse_campaign_workspace",
    "reconcile_dossier_directory_name",
]


def _extract_profile_name_suggestion(profile_member: CampaignArchiveMember | None) -> str | None:
    if not profile_member:
        return None
    try:
        text = profile_member.raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("##"):
            cleaned = line[2:].strip()
            cleaned = re.sub(
                r"^(?:Profile|CV|Resume|Curriculum\s*Vitae)\s*[-:]?\s*", "", cleaned, flags=re.I
            ).strip()
            if cleaned:
                return cleaned
    return None


def parse_campaign_workspace(
    archive_bytes: bytes,
    archive_name: str = "campaign.zip",
) -> ParsedCampaign:
    """Parse, inspect, reconcile, sanitize, and bind a campaign workspace without side effects."""
    inspection = inspect_and_validate_campaign_archive(archive_bytes)
    members = inspection.members

    tracker_member = members.get("ApplicationTracker.xlsx")
    tracker_rows: tuple[TrackerApplicationRow, ...] = ()
    headers: tuple[str, ...] = ()
    credentials_count = 0
    tracker_sha256: str | None = None
    sanitized_tracker_bytes: bytes | None = None
    sanitized_tracker_sha256: str | None = None

    if tracker_member:
        tracker_sha256 = tracker_member.sha256
        wb_result = read_campaign_workbook(tracker_member.raw_bytes)
        tracker_rows = wb_result.rows
        credentials_count = wb_result.credentials_count
        headers = wb_result.headers
        sanitized_tracker_bytes = sanitize_tracker_workbook(headers, tracker_rows)
        sanitized_tracker_sha256 = hashlib.sha256(sanitized_tracker_bytes).hexdigest()

    dossier_files: dict[str, list[CampaignArchiveMember]] = {}
    for path, member in members.items():
        if path.startswith("application-packets/"):
            parts = path.split("/")
            if len(parts) >= 3:
                dossier_files.setdefault(parts[1], []).append(member)

    tracker_by_id = {row.source_application_id: row for row in tracker_rows}
    tracker_ids = set(tracker_by_id.keys())

    resolved_to_dirs: dict[str, list[str]] = {}
    for dir_name in sorted(dossier_files.keys()):
        res_id = reconcile_dossier_directory_name(dir_name, tracker_ids)
        resolved_to_dirs.setdefault(res_id, []).append(dir_name)

    for res_id, dirs in resolved_to_dirs.items():
        if len(dirs) > 1:
            raise ArchivePolicyError(
                f"Ambiguous packet directories resolve to the same source ID '{res_id}'"
            )

    resolved_dossier_files: dict[str, list[CampaignArchiveMember]] = {
        res_id: dossier_files[dirs[0]] for res_id, dirs in resolved_to_dirs.items()
    }
    dir_to_resolved: dict[str, str] = {
        dirs[0]: res_id for res_id, dirs in resolved_to_dirs.items()
    }

    resolved_dossier_ids = set(resolved_dossier_files.keys())
    matched_ids = sorted(tracker_ids & resolved_dossier_ids)
    tracker_only_ids = sorted(tracker_ids - resolved_dossier_ids)
    dossier_only_ids = sorted(resolved_dossier_ids - tracker_ids)

    applications: list[ParsedApplication] = []
    status_counts: dict[str, int] = {}

    # 1. Tracker applications
    for order_idx, row in enumerate(tracker_rows):
        has_dossier = row.source_application_id in resolved_dossier_files
        packet_dir = resolved_to_dirs.get(row.source_application_id, [None])[0]
        sources = ("tracker", "dossier") if has_dossier else ("tracker",)
        prov: dict[str, Any] = {"sources": sources}
        if packet_dir:
            prov["packet_dir"] = packet_dir
        status_key = row.status or "Saved"
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

        applications.append(
            ParsedApplication(
                source_application_id=row.source_application_id,
                source_order=order_idx,
                title=row.title,
                company=row.company,
                location=row.location,
                source_status=row.status,
                priority=row.priority,
                platform=row.platform,
                category=row.category,
                outcome=row.outcome,
                found_at=row.found_at,
                applied_at=row.applied_at,
                follow_up_at=row.follow_up_at,
                last_update_at=row.last_update_at,
                next_action=row.next_action,
                notes=row.notes,
                platform_url=row.platform_url,
                job_posting_url=row.job_posting_url,
                url=row.url,
                tracker_record=freeze_value(row.raw_record),
                provenance=freeze_value(prov),
                packet_dir_name=packet_dir,
            )
        )

    # 2. Dossier-only applications
    base_order = len(tracker_rows)
    for d_idx, d_id in enumerate(dossier_only_ids):
        art_list = resolved_dossier_files[d_id]
        vacancy_member = next((m for m in art_list if m.canonical_path.endswith("/vacancy.md")), None)
        title = "Untitled role"
        company = "Unknown company"
        if vacancy_member:
            try:
                parsed_v = parse_vacancy_markdown(vacancy_member.raw_bytes.decode("utf-8"))
                title = parsed_v.title
                company = parsed_v.company
            except (UnicodeDecodeError, ValueError):
                pass

        applications.append(
            ParsedApplication(
                source_application_id=d_id,
                source_order=base_order + d_idx,
                title=title,
                company=company,
                location=None,
                source_status=None,
                priority=None,
                platform=None,
                category=None,
                outcome=None,
                found_at=None,
                applied_at=None,
                follow_up_at=None,
                last_update_at=None,
                next_action=None,
                notes=None,
                platform_url=None,
                job_posting_url=None,
                url=None,
                tracker_record=freeze_value({}),
                provenance=freeze_value({"sources": ("dossier",), "packet_dir": d_id}),
                packet_dir_name=d_id,
            )
        )

    # 3. Artifact bindings
    artifacts: list[ParsedArtifact] = []
    sorted_members = sorted(members.items(), key=lambda kv: kv[0])
    for art_idx, (path, member) in enumerate(sorted_members):
        if path == "ApplicationTracker.xlsx" and sanitized_tracker_bytes is not None:
            artifacts.append(
                ParsedArtifact(
                    relative_path="ApplicationTracker.xlsx",
                    display_name="ApplicationTracker.xlsx",
                    category="tracker",
                    source_order=art_idx,
                    source_application_id=None,
                    raw_bytes=sanitized_tracker_bytes,
                    sha256=sanitized_tracker_sha256 or member.sha256,
                    byte_size=len(sanitized_tracker_bytes),
                )
            )
        elif path.startswith("application-packets/"):
            parts = path.split("/")
            bound_app_id = (
                dir_to_resolved.get(parts[1], parts[1])
                if len(parts) >= 3
                else None
            )
            artifacts.append(
                ParsedArtifact(
                    relative_path=path,
                    display_name=parts[-1],
                    category=classify_artifact_category(path),
                    source_order=art_idx,
                    source_application_id=bound_app_id,
                    raw_bytes=member.raw_bytes,
                    sha256=member.sha256,
                    byte_size=member.byte_size,
                )
            )
        else:
            artifacts.append(
                ParsedArtifact(
                    relative_path=path,
                    display_name=path.split("/")[-1],
                    category=classify_artifact_category(path),
                    source_order=art_idx,
                    source_application_id=None,
                    raw_bytes=member.raw_bytes,
                    sha256=member.sha256,
                    byte_size=member.byte_size,
                )
            )

    warnings: list[str] = []
    if credentials_count > 0:
        warnings.append(
            f"Platform Credentials worksheet was excluded from import; {credentials_count} credentials omitted."
        )

    profile_member = members.get("Profile.md")
    profile_suggestion = _extract_profile_name_suggestion(profile_member)
    logical_count = len(tracker_rows) + len(dossier_only_ids)

    return ParsedCampaign(
        fingerprint=inspection.fingerprint,
        inspection=inspection,
        headers=tuple(headers),
        tracker_rows=tuple(tracker_rows),
        tracker_sha256=tracker_sha256,
        sanitized_tracker_bytes=sanitized_tracker_bytes,
        sanitized_tracker_sha256=sanitized_tracker_sha256,
        applications=tuple(applications),
        artifacts=tuple(artifacts),
        dossier_count=len(dossier_files),
        matched_count=len(matched_ids),
        tracker_only_count=len(tracker_only_ids),
        dossier_only_count=len(dossier_only_ids),
        logical_application_count=logical_count,
        status_counts=freeze_value(status_counts),
        credentials_count=credentials_count,
        warnings=tuple(warnings),
        suggested_name="Legacy application campaign",
        suggested_profile_name=profile_suggestion,
    )
