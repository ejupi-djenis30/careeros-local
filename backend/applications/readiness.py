from __future__ import annotations

import re
from typing import Literal

from sqlalchemy.orm import Session

from backend.applications.models import Application
from backend.applications.readiness_export import canonical_fingerprint
from backend.applications.schemas import (
    ApplicationReadinessCheck,
    ApplicationReadinessReport,
    ReadinessEvidence,
)
from backend.career.completeness import analyze_profile
from backend.career.models import CandidateProfile
from backend.resumes.models import ResumeDraft, ResumeVersion
from backend.storage.atomic import read_verified

DESCRIPTION_MINIMUM = 120
REQUIRED_ARTIFACT_FORMATS = frozenset({"pdf", "docx"})


def _evidence(**values: object) -> list[ReadinessEvidence]:
    return [ReadinessEvidence(key=key, value=str(value)) for key, value in values.items()]


def _check(
    check_id: str,
    status: Literal["pass", "warning", "blocker"],
    weight: int,
    evidence: list[ReadinessEvidence],
    action: str | None = None,
) -> ApplicationReadinessCheck:
    awarded = weight if status == "pass" else weight // 2 if status == "warning" else 0
    return ApplicationReadinessCheck(
        id=check_id,
        status=status,
        points_awarded=awarded,
        points_available=weight,
        evidence=evidence,
        action=action,
    )


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _artifact_availability(
    version: ResumeVersion,
) -> tuple[set[str], set[str], set[str]]:
    recorded: set[str] = set()
    verified: set[str] = set()
    failed: set[str] = set()
    for artifact in version.artifacts:
        artifact_format = str(artifact.format).casefold()
        if artifact_format not in REQUIRED_ARTIFACT_FORMATS:
            continue
        recorded.add(artifact_format)
        try:
            data = read_verified(artifact.storage_path, artifact.sha256)
            if len(data) != artifact.byte_size:
                raise ValueError("Stored artifact length does not match its immutable record")
        except (OSError, ValueError):
            failed.add(artifact_format)
        else:
            verified.add(artifact_format)
    return recorded, verified, failed


class ApplicationReadinessService:
    def __init__(self, db: Session):
        self.db = db

    def _profile(self, user_id: int) -> CandidateProfile | None:
        return (
            self.db.query(CandidateProfile)
            .filter(CandidateProfile.user_id == user_id)
            .first()
        )

    def _resume_version(
        self, user_id: int, version_id: str | None
    ) -> ResumeVersion | None:
        if version_id is None:
            return None
        return (
            self.db.query(ResumeVersion)
            .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
            .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
            .filter(
                ResumeVersion.id == version_id,
                CandidateProfile.user_id == user_id,
            )
            .first()
        )

    def build(self, user_id: int, application: Application) -> ApplicationReadinessReport:
        snapshot = application.job_snapshot if isinstance(application.job_snapshot, dict) else {}
        title = _clean_text(snapshot.get("title"))
        company = _clean_text(snapshot.get("company"))
        description = _clean_text(snapshot.get("description"))
        routes = sorted(
            key
            for key in ("application_url", "application_email", "external_url")
            if _clean_text(snapshot.get(key))
        )
        profile = self._profile(user_id)
        version = self._resume_version(user_id, application.resume_version_id)

        checks = [
            _check(
                "role_identity",
                "pass" if title and company else "blocker",
                10,
                _evidence(title_present=bool(title), company_present=bool(company)),
                None if title and company else "capture_role_identity",
            ),
            _check(
                "role_description",
                "pass" if len(description) >= DESCRIPTION_MINIMUM else "blocker",
                14,
                _evidence(
                    description_characters=len(description),
                    minimum_characters=DESCRIPTION_MINIMUM,
                ),
                None if len(description) >= DESCRIPTION_MINIMUM else "capture_role_description",
            ),
            _check(
                "application_route",
                "pass" if routes else "blocker",
                10,
                _evidence(route_types=", ".join(routes) or "none"),
                None if routes else "capture_application_route",
            ),
        ]

        profile_score = analyze_profile(profile).completeness_score if profile else 0
        profile_status: Literal["pass", "warning", "blocker"]
        if profile is None:
            profile_status = "blocker"
        elif profile_score >= 60:
            profile_status = "pass"
        else:
            profile_status = "warning"
        checks.append(
            _check(
                "career_profile",
                profile_status,
                14,
                _evidence(
                    profile_revision=profile.revision if profile else "none",
                    profile_completeness=f"{profile_score}/100",
                ),
                (
                    None
                    if profile_status == "pass"
                    else "complete_career_profile"
                    if profile is None
                    else "strengthen_career_profile"
                ),
            )
        )

        checks.extend(self._resume_checks(profile, version))
        blockers = sum(check.status == "blocker" for check in checks)
        warnings = sum(check.status == "warning" for check in checks)
        status: Literal["ready", "action_needed", "blocked"] = (
            "blocked" if blockers else "action_needed" if warnings else "ready"
        )
        report = ApplicationReadinessReport(
            application_id=application.id,
            application_revision=application.revision,
            role_title=title or "Untitled role",
            company=company or "Unknown company",
            status=status,
            completeness_score=sum(check.points_awarded for check in checks),
            blocker_count=blockers,
            warning_count=warnings,
            checks=checks,
            fingerprint="0" * 64,
        )
        return report.model_copy(
            update={"fingerprint": canonical_fingerprint(report)}
        )

    @staticmethod
    def _resume_checks(
        profile: CandidateProfile | None, version: ResumeVersion | None
    ) -> list[ApplicationReadinessCheck]:
        if version is None:
            return [
                _check(
                    "resume_linked",
                    "blocker",
                    16,
                    _evidence(resume_version="none"),
                    "link_published_resume",
                ),
                _check(
                    "resume_artifacts",
                    "blocker",
                    10,
                    _evidence(
                        recorded_formats="none",
                        verified_formats="none",
                        unavailable_formats=", ".join(sorted(REQUIRED_ARTIFACT_FORMATS)),
                    ),
                    "export_resume_files",
                ),
                _check(
                    "resume_quality",
                    "blocker",
                    10,
                    _evidence(quality_passed=False, renderer_version="none"),
                    "republish_valid_resume",
                ),
                _check(
                    "resume_freshness",
                    "blocker",
                    6,
                    _evidence(
                        resume_profile_revision="none",
                        current_profile_revision=profile.revision if profile else "none",
                    ),
                    "refresh_resume",
                ),
                _check(
                    "fact_verification",
                    "blocker",
                    10,
                    _evidence(selected_facts=0, verified_facts=0),
                    "verify_resume_facts",
                ),
            ]

        recorded_formats, verified_formats, failed_formats = _artifact_availability(version)
        unavailable_formats = REQUIRED_ARTIFACT_FORMATS.difference(verified_formats)
        artifact_status: Literal["pass", "warning", "blocker"] = (
            "pass"
            if verified_formats == REQUIRED_ARTIFACT_FORMATS and not failed_formats
            else "warning"
            if verified_formats and not failed_formats
            else "blocker"
        )
        quality_passed = bool((version.quality_report or {}).get("passed"))
        profile_current = profile is not None and version.profile_revision == profile.revision
        selected = set(version.selected_fact_ids or [])
        snapshot_facts = (version.snapshot or {}).get("facts", [])
        verified_fact_ids = {
            str(fact.get("id"))
            for fact in snapshot_facts
            if isinstance(fact, dict)
            and str(fact.get("id")) in selected
            and fact.get("verification_status") == "confirmed"
        }
        evidence_status: Literal["pass", "warning", "blocker"] = (
            "pass"
            if selected and len(verified_fact_ids) == len(selected)
            else "warning"
            if verified_fact_ids
            else "blocker"
        )
        return [
            _check(
                "resume_linked",
                "pass",
                16,
                _evidence(resume_version=version.semantic_version),
            ),
            _check(
                "resume_artifacts",
                artifact_status,
                10,
                _evidence(
                    recorded_formats=", ".join(sorted(recorded_formats)) or "none",
                    verified_formats=", ".join(sorted(verified_formats)) or "none",
                    unavailable_formats=", ".join(sorted(unavailable_formats)) or "none",
                ),
                (
                    None
                    if artifact_status == "pass"
                    else "republish_resume_artifacts"
                    if failed_formats
                    else "export_resume_files"
                ),
            ),
            _check(
                "resume_quality",
                "pass" if quality_passed else "blocker",
                10,
                _evidence(
                    quality_passed=quality_passed,
                    renderer_version=version.renderer_version,
                ),
                None if quality_passed else "republish_valid_resume",
            ),
            _check(
                "resume_freshness",
                "pass" if profile_current else "warning",
                6,
                _evidence(
                    resume_profile_revision=version.profile_revision,
                    current_profile_revision=profile.revision if profile else "none",
                ),
                None if profile_current else "refresh_resume",
            ),
            _check(
                "fact_verification",
                evidence_status,
                10,
                _evidence(
                    selected_facts=len(selected),
                    verified_facts=len(verified_fact_ids),
                ),
                None if evidence_status == "pass" else "verify_resume_facts",
            ),
        ]
