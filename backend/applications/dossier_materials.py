"""Orchestration service for application dossiers, draft bindings, and enhanced packets."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from backend.applications.dossier_queries import DossierQueryService
from backend.applications.email import generate_email_artifacts, validate_email_draft
from backend.applications.exceptions import (
    ApplicationValidationError,
)
from backend.applications.exports import (
    MAX_DOSSIER_EVENT_BYTES,
    DossierBundle,
    DossierSizeError,
    build_dossier_bundle,
    canonical_json,
)
from backend.applications.letters import generate_letter_artifacts, validate_letter_text
from backend.applications.models import Application
from backend.applications.schemas import ApplicationDossierCreate, ApplicationReadinessReport
from backend.applications.snapshots import sanitize_application_snapshot
from backend.resumes.content import build_content
from backend.resumes.models import ResumeVersion

if TYPE_CHECKING:
    from backend.applications.service import ApplicationService


def _letter_sender(snapshot: dict[str, Any]) -> tuple[str, list[str]]:
    """Reuse only the identity actually selected in the approved CV."""
    try:
        content = build_content(snapshot)
    except (KeyError, TypeError, ValueError) as exc:
        raise ApplicationValidationError("The approved resume identity is invalid") from exc
    return content.display_name, content.contact_line.splitlines()


def build_packet_materials(
    queries: DossierQueryService,
    *,
    application: Application,
    data: ApplicationDossierCreate,
    version: ResumeVersion,
    readiness: ApplicationReadinessReport,
    application_service_helper: ApplicationService,
) -> tuple[str, datetime, DossierBundle, dict[str, Any]]:
    # Validate confirmed evidence facts
    selected_ids = {str(value) for value in (version.selected_fact_ids or [])}
    snapshot_facts = (version.snapshot or {}).get("facts") or []
    facts_by_id = {
        str(fact.get("id")): fact
        for fact in snapshot_facts
        if isinstance(fact, dict)
        and fact.get("verification_status") == "confirmed"
        and str(fact.get("id")) in selected_ids
    }
    requirement_matrix: list[dict] = []
    all_evidence_ids = [
        str(fact_id) for row in data.requirement_matrix for fact_id in row.evidence_fact_ids
    ]
    material_text = " ".join(
        " ".join(value.split())
        for value in [
            data.cover_letter or "",
            data.email_draft.body if data.email_draft else "",
            *[answer.answer for answer in data.answers],
        ]
    )
    for claim in data.evidence_claims:
        if " ".join(claim.text.split()) not in material_text:
            raise ApplicationValidationError(
                "A cited material claim is absent from the approved text"
            )
        all_evidence_ids.extend(str(fact_id) for fact_id in claim.fact_ids)
    missing = [fact_id for fact_id in set(all_evidence_ids) if fact_id not in facts_by_id]
    if missing:
        raise ApplicationValidationError(
            "Every dossier evidence reference must be a confirmed fact in the linked resume"
        )
    for row in data.requirement_matrix:
        evidence_fact_ids = [str(fact_id) for fact_id in row.evidence_fact_ids]
        requirement_matrix.append(
            {
                "requirement": row.requirement.strip(),
                "evidence_fact_ids": evidence_fact_ids,
            }
        )

    try:
        evidence_catalog = {
            fact_id: {
                "fact_id": fact_id,
                "fact_type": facts_by_id[fact_id].get("fact_type"),
                "verification_status": "confirmed",
                "snapshot": facts_by_id[fact_id],
                "sha256": hashlib.sha256(canonical_json(facts_by_id[fact_id])).hexdigest(),
            }
            for fact_id in sorted(set(all_evidence_ids))
        }
    except (TypeError, ValueError) as exc:
        raise ApplicationValidationError(
            "A selected evidence fact cannot be serialized safely"
        ) from exc

    # Generate Letter Artifacts (PDF / DOCX)
    snapshot = application.job_snapshot or {}
    role_title = str(snapshot.get("title") or "Untitled role")
    company_name = str(snapshot.get("company") or "Unknown company")
    job_location = snapshot.get("location")

    recipient_lines = [line for line in [company_name, job_location] if line]
    if data.letter_options and data.letter_options.recipient:
        recipient_lines.insert(0, data.letter_options.recipient)

    letter_artifacts: dict[str, tuple[bytes, str]] = {}
    try:
        validate_letter_text(data.cover_letter)
        for answer in data.answers:
            validate_letter_text(answer.answer, field_name="Application answer")
    except ValueError as exc:
        raise ApplicationValidationError(str(exc)) from exc
    if data.letter_options:
        applicant_name, applicant_contact = _letter_sender(version.snapshot or {})
        try:
            letter_artifacts = generate_letter_artifacts(
                cover_letter=data.cover_letter,
                options=data.letter_options,
                applicant_name=applicant_name,
                applicant_contact=applicant_contact,
                recipient_lines=recipient_lines,
                subject=data.letter_options.subject
                or (
                    f"Bewerbung als {role_title}"
                    if data.letter_options.locale == "de"
                    else f"Application for {role_title}"
                ),
            )
        except ValueError as exc:
            raise ApplicationValidationError(str(exc)) from exc

    # Verified resume artifacts
    resume_artifacts = queries._verified_resume_artifacts(version)

    # Available filenames for email attachment validation
    available_attachment_files = set(letter_artifacts.keys())
    for fmt in resume_artifacts:
        available_attachment_files.add(f"resume.{fmt}")
    if data.cover_letter:
        available_attachment_files.add("cover-letter.txt")

    # Generate Email Artifacts (.eml, checklist)
    email_artifacts: dict[str, tuple[bytes, str]] = {}
    if data.email_draft:
        try:
            validate_email_draft(
                data.email_draft,
                available_packet_files=available_attachment_files,
                require_complete=True,
            )
            email_artifacts = generate_email_artifacts(data.email_draft)
        except ValueError as exc:
            raise ApplicationValidationError(str(exc)) from exc

    now = datetime.now(timezone.utc)
    dossier_id = str(uuid.uuid4())
    version_number = len(application_service_helper._dossier_summaries(application)) + 1

    dossier: dict[str, Any] = {
        "schema_version": "3.0",
        "version_number": version_number,
        "application_revision": data.expected_revision + 1,
        "resume_version_id": version.id,
        "created_at": now.isoformat(),
        "readiness_fingerprint": readiness.fingerprint,
        "role": {
            "title": role_title,
            "company": company_name,
            "location": job_location,
        },
        "readiness": {
            "score_kind": readiness.score_kind,
            "status": readiness.status,
            "completeness_score": readiness.completeness_score,
            "fingerprint": readiness.fingerprint,
        },
        "cover_letter": data.cover_letter,
        "answers": [answer.model_dump(mode="json") for answer in data.answers],
        "checklist": [item.model_dump(mode="json") for item in data.checklist],
        "requirement_matrix": requirement_matrix,
        "evidence_catalog": evidence_catalog,
        "letter_options": data.letter_options.model_dump(mode="json")
        if data.letter_options
        else None,
        "email_draft": data.email_draft.model_dump(mode="json") if data.email_draft else None,
        "generation_provenance": data.generation_provenance.model_dump(mode="json")
        if data.generation_provenance
        else None,
        "evidence_claims": [claim.model_dump(mode="json") for claim in data.evidence_claims],
    }

    # Build Enhanced 3.0 ZIP bundle
    sanitized_source_advert = sanitize_application_snapshot(
        snapshot, quarantine_reason="packet_snapshot_requires_revalidation"
    )
    try:
        bundle = build_dossier_bundle(
            dossier_id=dossier_id,
            version_number=version_number,
            application_revision=data.expected_revision + 1,
            application_id=application.id,
            created_at=dossier["created_at"],
            role=dossier["role"],
            resume_version_id=version.id,
            readiness=dossier["readiness"],
            cover_letter=dossier["cover_letter"],
            answers=dossier["answers"],
            checklist=dossier["checklist"],
            requirement_matrix=dossier["requirement_matrix"],
            evidence_catalog=dossier["evidence_catalog"],
            resume_artifacts=resume_artifacts,
            schema_version="3.0",
            letter_artifacts=letter_artifacts,
            email_artifacts=email_artifacts,
            source_advert=sanitized_source_advert,
            letter_options=dossier["letter_options"],
            email_draft_metadata=dossier["email_draft"],
            generation_provenance=dossier["generation_provenance"],
            evidence_claims=dossier["evidence_claims"],
        )
    except (DossierSizeError, TypeError, ValueError) as exc:
        raise ApplicationValidationError(str(exc)) from exc

    dossier["manifest"] = bundle.manifest
    dossier["manifest_sha256"] = bundle.manifest_sha256
    event_payload = {"schema_version": "3.0", "dossier": dossier}

    try:
        event_size = len(canonical_json(event_payload))
    except (TypeError, ValueError) as exc:
        raise ApplicationValidationError("Dossier event is not valid JSON") from exc
    if event_size > MAX_DOSSIER_EVENT_BYTES:
        raise ApplicationValidationError(
            f"Dossier event exceeds the {MAX_DOSSIER_EVENT_BYTES}-byte limit"
        )

    return dossier_id, now, bundle, event_payload
