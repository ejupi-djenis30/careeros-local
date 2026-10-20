"""Pure application snapshot projection for campaign import planning."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from backend.applications.schemas import normalize_application_email
from backend.applications.snapshots import sanitize_application_snapshot
from backend.campaigns.parser_types import ParsedApplication, freeze_value
from backend.campaigns.xlsx_cells import find_field
from backend.jobs.urls import UnsafeJobUrlError, normalize_job_url


def _build_snapshot(
    app: ParsedApplication,
    vacancies_by_id: Mapping[str, bytes],
) -> Mapping[str, Any]:
    clean_title = (app.title or "").strip()
    job_title = clean_title[:240] if clean_title else "Untitled role"

    clean_company = (app.company or "").strip()
    job_company = clean_company[:240] if clean_company else "Unknown company"
    job_loc = app.location.strip()[:500] if app.location and app.location.strip() else None

    # Description: dossier vacancy.md decoded as UTF-8 first, else Requirements Summary
    desc_raw: str | None = None
    if app.source_application_id in vacancies_by_id:
        try:
            desc_raw = vacancies_by_id[app.source_application_id].decode("utf-8")
        except UnicodeDecodeError:
            desc_raw = None
    if not desc_raw:
        req = app.tracker_record.get("Requirements Summary")
        desc_raw = str(req) if req is not None else None
    desc = desc_raw.strip()[:100000] if desc_raw and desc_raw.strip() else None

    # external_url prefers Job Posting URL, then generic URL
    ext_url: str | None = None
    for cand in (app.job_posting_url, app.url):
        if cand:
            try:
                ext_url = normalize_job_url(cand, required=False)
                if ext_url:
                    break
            except UnsafeJobUrlError:
                pass

    # application_url prefers Platform URL, then generic URL
    app_url: str | None = None
    for cand in (app.platform_url, app.url):
        if cand:
            try:
                app_url = normalize_job_url(cand, required=False)
                if app_url:
                    break
            except UnsafeJobUrlError:
                pass

    raw_email = find_field(app.tracker_record, ("contact email", "email"))
    app_email: str | None = None
    if raw_email:
        try:
            app_email = normalize_application_email(str(raw_email))
        except ValueError:
            app_email = None

    raw_workload = find_field(app.tracker_record, ("workplace type", "contract type", "workload"))
    workload = (
        str(raw_workload).strip()[:120] if raw_workload and str(raw_workload).strip() else None
    )

    pub_date = app.found_at.isoformat() if app.found_at else None
    platform = app.platform[:40] if app.platform else None
    job_id = app.source_application_id[:120]

    raw_snapshot: dict[str, Any] = {
        "title": job_title,
        "company": job_company,
        "platform_job_id": job_id,
    }
    if desc:
        raw_snapshot["description"] = desc
    if job_loc:
        raw_snapshot["location"] = job_loc
    if ext_url:
        raw_snapshot["external_url"] = ext_url
    if app_url:
        raw_snapshot["application_url"] = app_url
    if app_email:
        raw_snapshot["application_email"] = app_email
    if workload:
        raw_snapshot["workload"] = workload
    if pub_date:
        raw_snapshot["publication_date"] = pub_date
    if platform:
        raw_snapshot["platform"] = platform

    sanitized = sanitize_application_snapshot(
        raw_snapshot,
        quarantine_reason="manual_snapshot_has_no_model_analysis",
    )
    return cast(Mapping[str, Any], freeze_value(sanitized))
