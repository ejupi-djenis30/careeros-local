"""Validation of campaign workspace portability records (v8+)."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import PurePosixPath
from typing import Any, TypeGuard
from uuid import UUID

from backend.campaigns.models import ALLOWED_ARTIFACT_CATEGORIES, XLSX_MAX_CELL_CHARS

CANONICAL_PROVENANCE_SOURCES: tuple[list[str], ...] = (
    ["tracker"],
    ["dossier"],
    ["tracker", "dossier"],
)
ALLOWED_PROVENANCE_KEYS = frozenset({"sources", "packet_dir", "warnings"})
ALLOWED_SUMMARY_KEYS = frozenset({
    "application_count", "artifact_count", "source_document_count", "task_count",
    "tracker_rows", "dossier_count", "matched_count", "tracker_only_count",
    "dossier_only_count", "status_counts", "omitted_credential_count", "warning_count",
})



def _is_uuid(value: Any) -> TypeGuard[str]:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, TypeError):
        return False


def _is_hex64(value: Any) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _validate_provenance(prov: Any) -> list[str]:
    if not isinstance(prov, dict):
        raise ValueError("provenance must be an object")
    if not set(prov.keys()).issubset(ALLOWED_PROVENANCE_KEYS):
        raise ValueError("Invalid keys in provenance")
    sources = prov.get("sources")
    if sources not in CANONICAL_PROVENANCE_SOURCES:
        raise ValueError("provenance.sources must be a canonical sequence")
    if "dossier" in sources:
        pdir = prov.get("packet_dir")
        if not isinstance(pdir, str) or not pdir.strip() or len(pdir) > 120 or not unicodedata.is_normalized("NFC", pdir):
            raise ValueError("packet_dir must be bounded non-empty NFC string when dossier in sources")
    elif "packet_dir" in prov:
        raise ValueError("packet_dir must be absent when dossier not in sources")
    if "warnings" in prov:
        warns = prov["warnings"]
        if not isinstance(warns, list) or len(warns) > 100 or not all(isinstance(w, str) and len(w) <= 500 for w in warns):
            raise ValueError("provenance.warnings must be a list of strings <= 500 chars")
    return list(sources)


def validate_campaign_records(tables: dict[str, list[dict[str, Any]]], version: int) -> None:
    """Validate campaigns, campaign applications and campaign artifacts before writes."""
    if version < 8:
        return

    campaigns = tables.get("campaigns", [])
    campaign_apps = tables.get("campaign_applications", [])
    campaign_artifacts = tables.get("campaign_artifacts", [])
    applications = tables.get("applications", [])
    career_assets = tables.get("career_assets", [])

    valid_app_ids = {row["id"] for row in applications if "id" in row}
    apps_by_id = {row["id"]: row for row in applications if "id" in row}
    assets_by_id = {row["id"]: row for row in career_assets if "id" in row}

    campaign_ids: set[str] = set()

    for campaign in campaigns:
        cid = campaign.get("id")
        if not _is_uuid(cid):
            raise ValueError(f"Invalid campaign id: {cid}")
        if cid in campaign_ids:
            raise ValueError(f"Duplicate campaign id: {cid}")
        campaign_ids.add(cid)

        name = campaign.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 160:
            raise ValueError("Campaign name must be non-empty string <= 160 chars")

        fingerprint = campaign.get("source_fingerprint")
        if not _is_hex64(fingerprint):
            raise ValueError("Campaign source_fingerprint must be 64-char lowercase hex digest")

        name_integrity = campaign.get("name_integrity")
        expected_integrity = _sha256(name.encode("utf-8"))
        if name_integrity != expected_integrity:
            raise ValueError("Campaign name_integrity does not match sha256(name)")

        tracker_sha = campaign.get("tracker_sha256")
        if tracker_sha is not None and not _is_hex64(tracker_sha):
            raise ValueError("Campaign tracker_sha256 must be 64-char lowercase hex digest")

        summary = campaign.get("summary")
        if not isinstance(summary, dict):
            raise ValueError("Campaign summary must be an object")
        if len(_canonical_json(summary)) > 64_000:
            raise ValueError("Campaign summary exceeds size limit")
        if set(summary.keys()) != ALLOWED_SUMMARY_KEYS:
            raise ValueError("Campaign summary keys mismatch")

        for k in ALLOWED_SUMMARY_KEYS - {"status_counts"}:
            val = summary.get(k)
            if type(val) is not int or val < 0:
                raise ValueError(f"Campaign summary {k} must be non-negative integer")

        this_apps = [a for a in campaign_apps if a.get("campaign_id") == cid]
        this_arts = [a for a in campaign_artifacts if a.get("campaign_id") == cid]

        app_orders = [a.get("source_order") for a in this_apps]
        if any(type(o) is not int for o in app_orders) or set(app_orders) != set(range(len(this_apps))):
            raise ValueError("campaign_applications source_order must be contiguous 0..n-1 per campaign")

        art_orders = [a.get("source_order") for a in this_arts]
        if any(type(o) is not int for o in art_orders) or set(art_orders) != set(range(len(this_arts))):
            raise ValueError("campaign_artifacts source_order must be contiguous 0..n-1 per campaign")

        if summary["application_count"] != len(this_apps):
            raise ValueError("Campaign summary application_count mismatch")
        if summary["artifact_count"] != len(this_arts):
            raise ValueError("Campaign summary artifact_count mismatch")

        expected_task_count = sum(
            1 for a in this_apps
            if apps_by_id.get(a.get("application_id"), {}).get("next_action_task_id") is not None
        )
        if summary["task_count"] != expected_task_count:
            raise ValueError("Campaign summary task_count mismatch")

        sources_by_app = [_validate_provenance(a.get("provenance")) for a in this_apps]
        if summary["tracker_rows"] != sum(1 for s in sources_by_app if "tracker" in s):
            raise ValueError("Campaign summary tracker_rows mismatch")
        if summary["dossier_count"] != sum(1 for s in sources_by_app if "dossier" in s):
            raise ValueError("Campaign summary dossier_count mismatch")
        if summary["matched_count"] != sum(1 for s in sources_by_app if set(s) >= {"tracker", "dossier"}):
            raise ValueError("Campaign summary matched_count mismatch")
        if summary["tracker_only_count"] != sum(1 for s in sources_by_app if s == ["tracker"]):
            raise ValueError("Campaign summary tracker_only_count mismatch")
        if summary["dossier_only_count"] != sum(1 for s in sources_by_app if s == ["dossier"]):
            raise ValueError("Campaign summary dossier_only_count mismatch")

        status_counts = summary["status_counts"]
        if not isinstance(status_counts, dict):
            raise ValueError("Campaign summary status_counts must be an object")
        for k, v in status_counts.items():
            if not isinstance(k, str) or not k.strip() or len(k) > 60:
                raise ValueError("Campaign summary status_counts keys must be non-empty strings <= 60 chars")
            if type(v) is not int or v <= 0:
                raise ValueError("Campaign summary status_counts values must be positive integers")
        exp_sc: dict[str, int] = {}
        for a, s in zip(this_apps, sources_by_app):
            if "tracker" in s:
                st = a.get("source_status") or "Saved"
                exp_sc[st] = exp_sc.get(st, 0) + 1
        if status_counts != exp_sc:
            raise ValueError("Campaign summary status_counts mismatch")

    # Validate campaign applications
    app_ids: set[str] = set()
    source_app_keys: set[tuple[str, str]] = set()
    campaign_app_links: set[tuple[str, str]] = set()

    for app in campaign_apps:
        aid = app.get("id")
        if not _is_uuid(aid):
            raise ValueError(f"Invalid campaign_application id: {aid}")
        if aid in app_ids:
            raise ValueError(f"Duplicate campaign_application id: {aid}")
        app_ids.add(aid)

        cid = app.get("campaign_id")
        if not isinstance(cid, str) or cid not in campaign_ids:
            raise ValueError(f"campaign_application references missing campaign_id: {cid}")

        target_aid = app.get("application_id")
        if not isinstance(target_aid, str) or target_aid not in valid_app_ids:
            raise ValueError(f"campaign_application references missing application_id: {target_aid}")

        app_link_key = (cid, target_aid)
        if app_link_key in campaign_app_links:
            raise ValueError("Duplicate (campaign_id, application_id) in campaign_applications")
        campaign_app_links.add(app_link_key)

        source_id = app.get("source_application_id")
        if not isinstance(source_id, str) or not source_id.strip() or len(source_id) > 120:
            raise ValueError("source_application_id must be non-empty string <= 120 chars")

        source_key = (cid, source_id)
        if source_key in source_app_keys:
            raise ValueError("Duplicate (campaign_id, source_application_id) in campaign_applications")
        source_app_keys.add(source_key)

        for fld, max_len in (("source_status", 60), ("priority", 60), ("platform", 120), ("category", 120), ("outcome", 120)):
            val = app.get(fld)
            if val is not None and (not isinstance(val, str) or len(val) > max_len):
                raise ValueError(f"Invalid {fld} in campaign_application")

        tracker_record = app.get("tracker_record")
        if not isinstance(tracker_record, dict):
            raise ValueError("tracker_record must be an object")
        for k, v in tracker_record.items():
            if not isinstance(k, str) or len(k) > 120:
                raise ValueError("tracker_record key must be string <= 120 chars")
            if v is not None and not isinstance(v, (str, int, float, bool)):
                raise ValueError("tracker_record value must be scalar primitive")
            if isinstance(v, str) and len(v) > XLSX_MAX_CELL_CHARS:
                raise ValueError("tracker_record string value exceeds max length")

        _validate_provenance(app.get("provenance"))

    # Validate campaign artifacts
    art_ids: set[str] = set()
    art_paths: set[tuple[str, str]] = set()

    for art in campaign_artifacts:
        art_id = art.get("id")
        if not _is_uuid(art_id):
            raise ValueError(f"Invalid campaign_artifact id: {art_id}")
        if art_id in art_ids:
            raise ValueError(f"Duplicate campaign_artifact id: {art_id}")
        art_ids.add(art_id)

        cid = art.get("campaign_id")
        if cid not in campaign_ids:
            raise ValueError(f"campaign_artifact references missing campaign_id: {cid}")

        target_aid = art.get("application_id")
        if target_aid is not None:
            if target_aid not in valid_app_ids:
                raise ValueError(f"campaign_artifact references missing application_id: {target_aid}")
            if (cid, target_aid) not in campaign_app_links:
                raise ValueError("campaign_artifact application_id does not belong to the same campaign")

        asset_id = art.get("asset_id")
        if asset_id not in assets_by_id:
            raise ValueError(f"campaign_artifact references missing asset_id: {asset_id}")

        asset = assets_by_id[asset_id]
        if asset.get("kind") != "campaign_document" or asset.get("normalized") is not False:
            raise ValueError("campaign_artifact asset must be unnormalized campaign_document")
        asset_sha = asset.get("sha256")
        if not _is_hex64(asset_sha):
            raise ValueError("campaign_artifact asset sha256 must be valid hex digest")
        if asset.get("storage_path") != f"assets/campaign/{asset_sha[:2]}/{asset_sha}":
            raise ValueError("campaign_artifact asset storage_path does not match canonical campaign path")

        category = art.get("category")
        if category not in ALLOWED_ARTIFACT_CATEGORIES:
            raise ValueError(f"Invalid campaign_artifact category: {category}")

        rel_path = art.get("relative_path")
        if not isinstance(rel_path, str) or not rel_path.strip() or len(rel_path) > 500:
            raise ValueError("relative_path must be non-empty string <= 500 chars")
        if not unicodedata.is_normalized("NFC", rel_path):
            raise ValueError("relative_path must be NFC normalized")
        if "\\" in rel_path or rel_path.startswith("/") or ":" in rel_path or any(unicodedata.category(c).startswith("C") for c in rel_path):
            raise ValueError("relative_path cannot contain backslashes, colons, or control characters")

        posix = PurePosixPath(rel_path)
        if posix.is_absolute() or ".." in posix.parts or "." in posix.parts or posix.as_posix() != rel_path:
            raise ValueError("relative_path must be canonical POSIX path without traversal")

        norm_path = unicodedata.normalize("NFC", rel_path).casefold()
        path_key = (cid, norm_path)
        if path_key in art_paths:
            raise ValueError(f"Duplicate relative_path under NFC+casefolding in campaign_artifacts: {rel_path}")
        art_paths.add(path_key)

        display_name = art.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 255:
            raise ValueError("display_name must be non-empty string <= 255 chars")
        if not unicodedata.is_normalized("NFC", display_name):
            raise ValueError("display_name must be NFC normalized")
        if "/" in display_name or "\\" in display_name or ":" in display_name or any(unicodedata.category(c).startswith("C") for c in display_name) or posix.name != display_name:
            raise ValueError("display_name must match relative_path basename without control characters or colons")
