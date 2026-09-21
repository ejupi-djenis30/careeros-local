"""Flush-only integration into existing CV and application dossier drafts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.agent_work.errors import AgentWorkError
from backend.agent_work.models import AgentProposal, AgentWorkRequest
from backend.agent_work.schemas import MaterialsProposalPayload
from backend.applications.schemas import ApplicationDossierDraftPut
from backend.applications.service import (
    ApplicationConflictError,
    ApplicationNotFoundError,
    ApplicationService,
    ApplicationValidationError,
)
from backend.career.models import CandidateProfile
from backend.resumes.canvas_schemas import ResumeCanvasDocument
from backend.resumes.canvas_validation import validate_canvas_references
from backend.resumes.draft_mutations import apply_draft_data
from backend.resumes.draft_service import ResumeDraftService
from backend.resumes.exceptions import ResumeValidationError
from backend.resumes.models import ResumeDraft
from backend.resumes.schemas import ResumeDraftUpdate
from backend.resumes.templates import get_template_preset


def accept_materials_flush_only(
    db: Session, req: AgentWorkRequest, proposal: AgentProposal
) -> dict[str, Any]:
    """Caller reserves the work row and owns the complete commit/rollback boundary."""
    material = MaterialsProposalPayload.model_validate(proposal.payload)
    profile = db.query(CandidateProfile).populate_existing().filter_by(user_id=req.user_id).first()
    if profile is None or req.target_resume_id is None or req.target_application_id is None:
        raise AgentWorkError("work_not_found", "Material targets are unavailable")
    draft = (
        db.query(ResumeDraft)
        .populate_existing()
        .filter_by(id=req.target_resume_id, profile_id=profile.id)
        .first()
    )
    if draft is None:
        raise AgentWorkError("work_not_found", "Material targets are unavailable")
    expected = req.input_revisions.get("resume")
    changed = (
        db.query(ResumeDraft)
        .filter_by(id=draft.id, profile_id=profile.id, revision=expected)
        .update({ResumeDraft.revision: ResumeDraft.revision + 1}, synchronize_session=False)
    )
    if changed != 1:
        raise AgentWorkError("revision_conflict", "CV draft changed before acceptance")
    preset = get_template_preset(material.preset_id, material.preset_version)
    now = datetime.now(UTC).isoformat()
    provenance = {
        "source": "external-agent",
        "request_id": req.id,
        "grant_id": proposal.submitting_grant_id,
        "input_digest": req.input_digest,
        "payload_digest": proposal.payload_digest,
        "generated_at": now,
    }
    try:
        data = ResumeDraftUpdate.model_validate(
            {
                "expected_revision": expected,
                "title": draft.title,
                "template_kind": preset.template_kind,
                "template_id": preset.id,
                "template_version": preset.version,
                "locale": preset.locale,
                "selected_fact_ids": material.cv_selected_fact_ids,
                "section_config": draft.section_config,
                "content_overrides": draft.content_overrides,
                "canvas_document": draft.canvas_document or None,
                "photo_asset_id": draft.photo_asset_id
                if preset.photo_policy != "forbidden"
                else None,
            }
        )
        facts = ResumeDraftService(db).validate_selection(profile, data)
        apply_draft_data(draft, data, facts, profile)
        canvas = ResumeCanvasDocument.model_validate(draft.canvas_document)
        for override in material.cv_cited_overrides:
            matches = [
                block
                for section in canvas.sections
                for block in section.blocks
                if block.kind == "fact" and set(block.fact_ids) == set(override.fact_ids)
            ]
            if len(matches) != 1:
                raise AgentWorkError(
                    "invalid_result", "A CV override requires one unambiguous existing fact block"
                )
            block = matches[0]
            block.content.description = override.text
            block.manual_fields = list(dict.fromkeys([*block.manual_fields, "description"]))
        validate_canvas_references(canvas, set(material.cv_selected_fact_ids))
        draft.canvas_document = canvas.model_dump(mode="json")
        draft.profile_revision = profile.revision
        draft.revision = int(expected or 0) + 1
        draft.generation_context = {
            "mode": "external-agent",
            "source_profile_revision": profile.revision,
            "generated_at": now,
            "target_job_id": req.target_job_id,
            "target_snapshot": req.context_snapshot.get("target_job") or {},
            "claim_evidence_map": {
                block.id: block.fact_ids
                for section in canvas.sections
                for block in section.blocks
                if block.fact_ids
            },
            **{k: v for k, v in provenance.items() if k not in {"source", "generated_at"}},
        }
        db.flush()
        claims = [*material.cover_letter, *material.email.body, *material.questions_answers]
        if len({claim.id for claim in claims}) != len(claims):
            raise AgentWorkError("invalid_result", "Material claim identities must be unique")
        content = {
            "cover_letter": "\n\n".join(item.text for item in material.cover_letter) or None,
            "answers": [
                {"client_id": item.id, "question": item.question, "answer": item.text}
                for item in material.questions_answers
            ],
            "checklist": [],
            "requirement_matrix": [
                {
                    "client_id": f"agent-requirement-{index}",
                    "requirement": item.requirement,
                    "evidence_fact_ids": item.fact_ids,
                }
                for index, item in enumerate(material.requirements_to_evidence)
            ],
            "letter_options": {
                "preset_id": preset.id,
                "template_version": preset.version,
                "locale": preset.locale,
            },
            "email_draft": {
                "mode": material.email.mode,
                "subject": material.email.subject,
                "body": "\n\n".join(item.text for item in material.email.body),
                "attachment_names": material.email.attachment_names,
            },
            "generation_provenance": provenance,
            "evidence_claims": [
                {"id": item.id, "text": item.text, "fact_ids": item.fact_ids} for item in claims
            ],
        }
        dossier_data = ApplicationDossierDraftPut.model_validate(
            {
                "expected_revision": req.input_revisions.get("dossier"),
                "expected_application_revision": req.input_revisions["application"],
                "resume_draft_id": draft.id,
                "expected_resume_draft_revision": draft.revision,
                "content": content,
            }
        )
        dossier = ApplicationService(db).mutate_dossier_draft_flush_only(
            req.user_id, req.target_application_id, dossier_data
        )
    except ApplicationConflictError:
        raise AgentWorkError("revision_conflict", "Dossier changed before acceptance") from None
    except (
        ApplicationValidationError,
        ApplicationNotFoundError,
        ResumeValidationError,
        ValidationError,
        ValueError,
    ):
        raise AgentWorkError(
            "invalid_result", "Materials cannot be applied to the selected drafts"
        ) from None
    return {
        "resume_draft_id": draft.id,
        "resume_revision": draft.revision,
        "dossier_draft_id": dossier.id,
        "dossier_revision": dossier.revision,
        "application_id": req.target_application_id,
    }
