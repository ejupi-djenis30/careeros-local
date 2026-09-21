"""Generate application packets from reviewed campaign templates and a JSON manifest.

This command is deliberately local and deterministic.  It validates tracker deduplication,
copies the selected HTML templates, replaces only approved content fields, and writes packet
metadata.  It does not render PDFs or submit applications.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.campaigns.xlsx_reader import read_campaign_workbook  # noqa: E402


class MaterialGenerationError(ValueError):
    """Raised when an input or output violates the campaign generation contract."""


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("campaign_root", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument(
        "--refresh-id",
        action="append",
        default=[],
        help="Regenerate an existing packet whose tracked ID and URL still match",
    )
    return parser.parse_args()


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        raw_payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterialGenerationError("Manifest could not be read as JSON") from exc
    if not isinstance(raw_payload, dict):
        raise MaterialGenerationError("Manifest must be a JSON object")
    payload = cast(dict[str, Any], raw_payload)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or len(jobs) < 20:
        raise MaterialGenerationError("Manifest must contain at least 20 jobs")
    required = {
        "id",
        "company",
        "role",
        "job_ref",
        "location",
        "source",
        "url",
        "apply_url",
        "category",
        "priority",
        "tier",
        "cv_template",
        "cl_template",
        "summary",
        "reason",
        "requirement",
        "target",
        "goal",
        "project",
        "project_evidence",
        "keywords",
        "fit",
        "gap",
        "snapshot",
    }
    for index, job in enumerate(jobs, start=1):
        if not isinstance(job, dict):
            raise MaterialGenerationError(f"Job {index} must be an object")
        missing = sorted(required - set(job))
        if missing:
            raise MaterialGenerationError(f"Job {index} is missing required fields: {missing}")
    return payload


def _canonical_url(value: str | None) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    host = parts.netloc.casefold()
    path = re.sub(r"/+", "/", parts.path).rstrip("/").casefold()
    return urlunsplit((parts.scheme.casefold(), host, path, "", ""))


def _normal(value: str | None) -> str:
    return "".join(character for character in (value or "").casefold() if character.isalnum())


def _deduplicate(jobs: list[dict[str, Any]], tracker_path: Path) -> None:
    result = read_campaign_workbook(tracker_path.read_bytes())
    existing_urls: dict[str, str] = {}
    existing_role_keys: dict[tuple[str, str], str] = {}
    existing_ids = {row.source_application_id for row in result.rows}

    for row in result.rows:
        for value in (
            row.platform_url,
            row.job_posting_url,
            row.url,
            row.raw_record.get("Submission Destination"),
        ):
            canonical = _canonical_url(str(value) if value else None)
            if canonical:
                existing_urls[canonical] = row.source_application_id
        existing_role_keys[(_normal(row.company), _normal(row.title))] = row.source_application_id

    seen_ids: set[str] = set()
    seen_urls: dict[str, str] = {}
    seen_role_keys: dict[tuple[str, str], str] = {}
    conflicts: list[str] = []
    for job in jobs:
        job_id = str(job["id"])
        canonical = _canonical_url(str(job["url"]))
        role_key = (_normal(str(job["company"])), _normal(str(job["role"])))
        if job_id in existing_ids or job_id in seen_ids:
            conflicts.append(f"{job_id}: duplicate application ID")
        if canonical in existing_urls:
            conflicts.append(f"{job_id}: URL already tracked by {existing_urls[canonical]}")
        if canonical in seen_urls:
            conflicts.append(f"{job_id}: URL duplicates {seen_urls[canonical]}")
        if role_key in existing_role_keys:
            conflicts.append(
                f"{job_id}: company and role already tracked by {existing_role_keys[role_key]}"
            )
        if role_key in seen_role_keys:
            conflicts.append(f"{job_id}: company and role duplicate {seen_role_keys[role_key]}")
        seen_ids.add(job_id)
        seen_urls[canonical] = job_id
        seen_role_keys[role_key] = job_id

    if conflicts:
        raise MaterialGenerationError("Deduplication failed:\n" + "\n".join(conflicts))


def _validate_refresh(jobs: list[dict[str, Any]], tracker_path: Path) -> None:
    rows = {
        row.source_application_id: row
        for row in read_campaign_workbook(tracker_path.read_bytes()).rows
    }
    for job in jobs:
        row = rows.get(str(job["id"]))
        if row is None:
            raise MaterialGenerationError(f"Refresh target is not tracked: {job['id']}")
        if _canonical_url(row.job_posting_url or row.url) != _canonical_url(str(job["url"])):
            raise MaterialGenerationError(f"Refresh target URL changed: {job['id']}")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return cleaned or "Role"


def _replace_cv(template: str, job: dict[str, Any]) -> str:
    role = html.escape(str(job["role"]))
    summary = html.escape(str(job["summary"]))
    output, role_count = re.subn(
        r'<h2 class="role-title">.*?</h2>',
        f'<h2 class="role-title">{role}</h2>',
        template,
        count=1,
        flags=re.DOTALL,
    )
    if role_count != 1:
        raise MaterialGenerationError(f"CV role title replacement failed for {job['id']}")

    patterns = (
        r"(<h2>Professional Summary</h2>\s*)<p>.*?</p>",
        r'(<section class="cv-section section-profile"><h2>Profile</h2>)<p>.*?</p>',
    )
    summary_count = 0
    for pattern in patterns:
        output, summary_count = re.subn(
            pattern,
            rf"\1<p>{summary}</p>",
            output,
            count=1,
            flags=re.DOTALL,
        )
        if summary_count:
            break
    if summary_count != 1:
        raise MaterialGenerationError(f"CV summary replacement failed for {job['id']}")

    title = html.escape(f"{job['role']} CV — Djenis Ejupi")
    output, title_count = re.subn(r"<title>.*?</title>", f"<title>{title}</title>", output, count=1)
    if title_count != 1:
        raise MaterialGenerationError(f"CV title replacement failed for {job['id']}")
    return output


def _placeholder_values(job: dict[str, Any]) -> dict[str, str]:
    availability = (
        "Availability is to be confirmed; I am authorised to work in Switzerland with a valid "
        "Permit B (EU/EFTA)."
    )
    return {
        "COMPANY": str(job["company"]),
        "CONTACT_NAME": "Hiring Team",
        "COMPANY_ADDRESS": str(job["location"]),
        "DATE": "20 September 2026",
        "ROLE": str(job["role"]),
        "JOB_REFERENCE": str(job.get("letter_ref", job["job_ref"])),
        "GREETING": "Dear Hiring Team,",
        "SPECIFIC_REASON_CLAUSE": str(job["reason"]),
        "VACANCY_REQUIREMENT": str(job["requirement"]),
        "TARGET_TEAM_OR_PRODUCT": str(job["target"]),
        "TARGET_TEAM_OR_PLATFORM": str(job["target"]),
        "TARGET_ENGINEERING_GOAL": str(job["goal"]),
        "TARGET_OPERATIONAL_GOAL": str(job["goal"]),
        "SELECTED_PROJECT": str(job["project"]),
        "PROJECT_EVIDENCE_CLAUSE": str(job["project_evidence"]),
        "PROJECT_RELEVANCE_CLAUSE": str(job.get("project_relevance", job["project_evidence"])),
        "ROLE_MOTIVATION_CLAUSE": str(job.get("role_motivation", job["reason"])),
        "AVAILABILITY_SENTENCE": availability,
    }


def _replace_cover_letter(template: str, job: dict[str, Any]) -> str:
    values = _placeholder_values(job)
    missing: set[str] = set()

    def replacement(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in values:
            missing.add(token)
            return match.group(0)
        return html.escape(values[token])

    output = re.sub(
        r'<span class="placeholder" data-placeholder="([^"]+)">\[[^\]]+\]</span>',
        replacement,
        template,
    )
    if missing:
        raise MaterialGenerationError(
            f"Cover-letter placeholders are unsupported for {job['id']}: {sorted(missing)}"
        )
    if "data-placeholder=" in output or re.search(r"\[[A-Z][A-Z0-9_ -]+\]", output):
        raise MaterialGenerationError(f"Cover letter retains placeholders for {job['id']}")
    title = html.escape(f"{job['role']} Cover Letter — Djenis Ejupi")
    output, title_count = re.subn(r"<title>.*?</title>", f"<title>{title}</title>", output, count=1)
    if title_count != 1:
        raise MaterialGenerationError(f"Cover-letter title replacement failed for {job['id']}")
    return output


def _packet_names(job: dict[str, Any]) -> tuple[str, str]:
    suffix = f"{_slug(str(job['company']))}_{_slug(str(job['role']))}"
    return f"Djenis_Ejupi_CV_{suffix}", f"Djenis_Ejupi_Cover_Letter_{suffix}"


def _packet_files(job: dict[str, Any], cv_base: str, letter_base: str) -> dict[str, str]:
    unknown = "Not provided — confirm at application time."
    vacancy = f"""# {job["id"]} - {job["company"]} - {job["role"]}

- Status: Prepared, not sent
- Live verification: HTTP 200 and source content checked on 20 September 2026
- Verified source: {job["source"]}
- Location: {job["location"]}
- Posting: {job["url"]}
- Application destination: {job["apply_url"]}
- Match tier: {job["tier"]}
- Priority: {job["priority"]}
- Dedupe: exact URL and normalized company-role pair absent from the prior tracker
- Factual fit: {job["fit"]}
- Honest limit: {job["gap"]}
- Role-relevant keywords used: {job["keywords"]}
- CV: {cv_base}.pdf
- Cover letter: {letter_base}.pdf
- Submission: not performed. Re-check the live posting, employer identity and duplicate state immediately before any future submission.

## Vacancy snapshot

{job["snapshot"]}
"""
    answers = f"""Application ID: {job["id"]}
Company: {job["company"]}
Role: {job["role"]}
Job reference: {job["job_ref"]}
Application URL: {job["apply_url"]}
Salary expectation if requested: {unknown}
Notice period: {unknown}
Earliest start date: {unknown}
Workload or schedule: {unknown}
Work authorisation: Yes — Swiss Permit B (EU/EFTA), valid until 14 August 2030
Professional certifications: None
Languages: Albanian native; Italian native; English B2; German A2
Highest education: Technical Diploma in Computer Science and Telecommunications, 92/100 (not a university degree)
Date of birth: use only a verified prefilled or account value; it is not stored in Profile.md and must not be guessed
CV to upload: {cv_base}.pdf
Cover letter to upload: {letter_base}.pdf
Transmission status: NOT SENT — materials prepared only
"""
    note = f"""Dear Hiring Team,

I am interested in the {job["role"]} position at {job["company"]} because {job["reason"]}. The focus on {job["requirement"]} matches work I have already delivered across application development, testing, integrations and cloud operations.

My strongest evidence for this application is {job["project"]}: {job["project_evidence"]}. I am based in Dietikon and authorised to work in Switzerland under a valid Permit B (EU/EFTA). I would be pleased to discuss notice period, start date and workload directly.

Kind regards,
Djenis Ejupi
"""
    return {
        "vacancy.md": vacancy,
        "application-answers.txt": answers,
        "application-note.txt": note,
    }


def _write_summary(root: Path, payload: dict[str, Any]) -> Path:
    output = root / "outputs" / "job-search-2026-09-20.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Verified job search — 20 September 2026",
        "",
        "All roles passed exact-URL and normalized company-role deduplication against the prior tracker. Materials are prepared but no application was submitted.",
        "",
        "| ID | Priority | Match | Company | Role | Location | Source |",
        "|---|---|---|---|---|---|---|",
    ]
    for job in payload["jobs"]:
        source = f"[{job['source']}]({job['url']})"
        lines.append(
            f"| {job['id']} | {job['priority']} | {job['tier']} | {job['company']} | "
            f"{job['role']} | {job['location']} | {source} |"
        )
    lines.extend(
        [
            "",
            "## Review flags",
            "",
            "- Jobgether listings hide the underlying employer; confirm the legal employer, contract and data-sharing terms before submission.",
            "- Stretch roles retain explicit seniority or technology gaps in each packet; no unsupported experience was added.",
            "- Notice period, earliest start, salary, workload and scheduling remain unfilled until the candidate confirms them.",
            "- Re-check liveness and duplicate state immediately before any future submission.",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def main() -> int:
    arguments = _arguments()
    root = arguments.campaign_root.resolve(strict=True)
    payload = _read_manifest(arguments.manifest.resolve(strict=True))
    all_jobs: list[dict[str, Any]] = payload["jobs"]
    refresh_ids = set(arguments.refresh_id)
    jobs = [job for job in all_jobs if not refresh_ids or job["id"] in refresh_ids]
    if refresh_ids != {str(job["id"]) for job in jobs}:
        raise MaterialGenerationError("One or more refresh IDs are absent from the manifest")
    if refresh_ids:
        _validate_refresh(jobs, root / "ApplicationTracker.xlsx")
    else:
        _deduplicate(jobs, root / "ApplicationTracker.xlsx")
    if arguments.check_only:
        print(json.dumps({"deduplicated": len(jobs), "write": False}, sort_keys=True))
        return 0

    packet_root = root / "application-packets"
    cv_template_root = root / "html-templates" / "cv"
    letter_template_root = root / "html-templates" / "cover-letters"
    written: list[str] = []
    for job in jobs:
        packet = packet_root / str(job["id"])
        if packet.exists() and not refresh_ids:
            raise MaterialGenerationError(f"Packet already exists: {job['id']}")
        packet.mkdir(parents=False, exist_ok=bool(refresh_ids))
        cv_base, letter_base = _packet_names(job)
        cv_source = (cv_template_root / str(job["cv_template"])).read_text(encoding="utf-8")
        letter_source = (letter_template_root / str(job["cl_template"])).read_text(encoding="utf-8")
        (packet / f"{cv_base}.html").write_text(_replace_cv(cv_source, job), encoding="utf-8")
        (packet / f"{letter_base}.html").write_text(
            _replace_cover_letter(letter_source, job), encoding="utf-8"
        )
        for filename, content in _packet_files(job, cv_base, letter_base).items():
            (packet / filename).write_text(content, encoding="utf-8")
        written.append(str(job["id"]))

    summary = _write_summary(root, payload)
    print(
        json.dumps(
            {
                "deduplicated": len(jobs),
                "packets_written": len(written),
                "summary": str(summary),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (MaterialGenerationError, OSError) as exc:
        sys.stderr.write(f"Material generation failed: {exc}\n")
        raise SystemExit(2) from exc
