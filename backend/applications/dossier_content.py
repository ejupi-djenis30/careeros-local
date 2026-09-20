"""Orchestration service for application dossiers, draft bindings, and enhanced packets."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from backend.applications.exceptions import (
    ApplicationValidationError,
)
from backend.applications.schemas import (
    ApplicationDossierCreate,
    ApplicationDossierDraftContent,
)


def _publishable_draft_content(
    content: dict[str, Any],
) -> dict[str, Any]:
    try:
        draft = ApplicationDossierDraftContent.model_validate(content)
    except ValidationError as exc:
        raise ApplicationValidationError("The stored dossier draft is invalid") from exc

    answers: list[dict[str, str]] = []
    for answer_row in draft.answers:
        question = answer_row.question.strip()
        answer = answer_row.answer.strip()
        if bool(question) != bool(answer):
            raise ApplicationValidationError(
                "Complete both fields in every dossier answer before publishing"
            )
        if question:
            answers.append({"question": question, "answer": answer})

    checklist: list[dict[str, Any]] = []
    for checklist_row in draft.checklist:
        label = checklist_row.label.strip()
        if checklist_row.completed and not label:
            raise ApplicationValidationError("Completed dossier checklist items require a label")
        if label:
            checklist.append({"label": label, "completed": checklist_row.completed})

    requirement_matrix: list[dict[str, Any]] = []
    for requirement_row in draft.requirement_matrix:
        requirement = requirement_row.requirement.strip()
        if not requirement or not requirement_row.evidence_fact_ids:
            raise ApplicationValidationError(
                "Every dossier requirement needs text and confirmed evidence"
            )
        requirement_matrix.append(
            {
                "requirement": requirement,
                "evidence_fact_ids": [
                    str(fact_id) for fact_id in requirement_row.evidence_fact_ids
                ],
            }
        )
    return {
        "cover_letter": (draft.cover_letter or "").strip() or None,
        "answers": answers,
        "checklist": checklist,
        "requirement_matrix": requirement_matrix,
        "letter_options": draft.letter_options.model_dump(mode="json")
        if draft.letter_options
        else None,
        "email_draft": draft.email_draft.model_dump(mode="json") if draft.email_draft else None,
        "generation_provenance": draft.generation_provenance.model_dump(mode="json")
        if draft.generation_provenance
        else None,
        "evidence_claims": [claim.model_dump(mode="json") for claim in draft.evidence_claims],
    }


def _requested_dossier_content(data: ApplicationDossierCreate) -> dict[str, Any]:
    return {
        "cover_letter": (data.cover_letter or "").strip() or None,
        "answers": [item.model_dump(mode="json") for item in data.answers],
        "checklist": [item.model_dump(mode="json") for item in data.checklist],
        "requirement_matrix": [item.model_dump(mode="json") for item in data.requirement_matrix],
        "letter_options": data.letter_options.model_dump(mode="json")
        if data.letter_options
        else None,
        "email_draft": data.email_draft.model_dump(mode="json") if data.email_draft else None,
        "generation_provenance": data.generation_provenance.model_dump(mode="json")
        if data.generation_provenance
        else None,
        "evidence_claims": [claim.model_dump(mode="json") for claim in data.evidence_claims],
    }
