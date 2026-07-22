from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from typing import Literal

from backend.applications.schemas import ApplicationReadinessReport

CHECK_TITLES = {
    "role_identity": "Role identity",
    "role_description": "Role description",
    "application_route": "Application route",
    "career_profile": "Career profile",
    "resume_linked": "Published resume",
    "resume_artifacts": "Resume files",
    "resume_quality": "Resume validation",
    "resume_freshness": "Profile freshness",
    "fact_verification": "Resume evidence",
}
ACTION_TEXT = {
    "capture_role_identity": "Add both the role title and company.",
    "capture_role_description": "Capture enough of the role description to prepare against it.",
    "capture_application_route": "Add an application URL, source URL or application email.",
    "complete_career_profile": "Create a career profile before preparing this application.",
    "strengthen_career_profile": "Complete the missing profile sections and evidence.",
    "link_published_resume": "Link an owned published resume version to this application.",
    "export_resume_files": "Publish both PDF and DOCX resume artifacts.",
    "republish_resume_artifacts": "Republish the resume to restore verified local PDF and DOCX files.",
    "republish_valid_resume": "Publish a resume that passes local document validation.",
    "refresh_resume": "Publish a resume from the current profile revision.",
    "verify_resume_facts": "Use confirmed career facts in the published resume.",
}
EVIDENCE_LABELS = {
    "title_present": "Title present",
    "company_present": "Company present",
    "description_characters": "Description characters",
    "minimum_characters": "Minimum characters",
    "route_types": "Available routes",
    "profile_revision": "Profile revision",
    "profile_completeness": "Profile completeness",
    "resume_version": "Resume version",
    "recorded_formats": "Recorded formats",
    "verified_formats": "Verified local formats",
    "unavailable_formats": "Unavailable formats",
    "quality_passed": "Quality report passed",
    "renderer_version": "Renderer version",
    "resume_profile_revision": "Resume profile revision",
    "current_profile_revision": "Current profile revision",
    "selected_facts": "Selected facts",
    "verified_facts": "Verified in published snapshot",
}


@dataclass(frozen=True)
class ReadinessExport:
    data: bytes
    filename: str
    media_type: str
    sha256: str


def _json_bytes(report: ApplicationReadinessReport, *, include_fingerprint: bool) -> bytes:
    payload = report.model_dump(mode="json")
    if not include_fingerprint:
        payload.pop("fingerprint", None)
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_fingerprint(report: ApplicationReadinessReport) -> str:
    return hashlib.sha256(_json_bytes(report, include_fingerprint=False)).hexdigest()


def canonical_json(report: ApplicationReadinessReport) -> bytes:
    return _json_bytes(report, include_fingerprint=True) + b"\n"


def _markdown(value: object) -> str:
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    escaped_html = html.escape(clean, quote=False)
    return re.sub(r"([\\`*_\[\]{}()#+!|~])", r"\\\1", escaped_html)


def canonical_markdown(report: ApplicationReadinessReport) -> bytes:
    state = report.status.replace("_", " ").title()
    lines = [
        "# CareerOS Application Readiness Pack",
        "",
        "> This is a preflight completeness index, not a hiring probability or a rating of the candidate.",
        "",
        f"- Role: {_markdown(report.role_title)}",
        f"- Company: {_markdown(report.company)}",
        f"- Application revision: {report.application_revision}",
        f"- Readiness: {state}",
        f"- Completeness: {report.completeness_score}/100",
        f"- Report fingerprint: `{report.fingerprint}`",
        "",
        "| Check | State | Points | Evidence | Next action |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for check in report.checks:
        evidence = "; ".join(
            f"{EVIDENCE_LABELS.get(item.key, item.key)}: {item.value}"
            for item in check.evidence
        )
        action = ACTION_TEXT.get(check.action or "", "None")
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown(CHECK_TITLES.get(check.id, check.id)),
                    check.status.title(),
                    f"{check.points_awarded}/{check.points_available}",
                    _markdown(evidence),
                    _markdown(action),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "All checks were calculated from records in the local CareerOS vault. No model or external network service was used.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def export_readiness(
    report: ApplicationReadinessReport,
    export_format: Literal["json", "markdown"],
) -> ReadinessExport:
    if export_format == "json":
        data = canonical_json(report)
        extension = "json"
        media_type = "application/json"
    else:
        data = canonical_markdown(report)
        extension = "md"
        media_type = "text/markdown; charset=utf-8"
    return ReadinessExport(
        data=data,
        filename=f"careeros-application-{report.application_id}-readiness.{extension}",
        media_type=media_type,
        sha256=hashlib.sha256(data).hexdigest(),
    )
