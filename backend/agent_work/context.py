"""Explicit, bounded snapshots of owned evidence for external agents."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from backend.agent_work.errors import AgentWorkError
from backend.agent_work.schemas import (
    MAX_CONTEXT_BYTES,
    MAX_FACTS_PER_CONTEXT,
    ContextFact,
    ContextJobSnapshot,
    ProposalPayload,
    WorkContextPayload,
    WorkKind,
)
from backend.applications.models import Application, ApplicationDossierDraft
from backend.career.models import CandidateProfile, CareerFact
from backend.career.payloads import PAYLOAD_SCHEMAS, CareerPreferences
from backend.models.job import Job
from backend.resumes.models import ResumeDraft
from backend.resumes.templates import get_template_preset

_EMAIL_LOCAL_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._%+-"
)
_EMAIL_DOMAIN_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-"
)
# Match explicit international/delimited phone syntax, never dates or plain metrics.
_PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:"
    r"\+\d{1,3}[ .()/-]*(?:\d[ .()/-]*){7,12}\d"
    r"|0(?:[ .()/-]*\d){9}"
    r"|\(\d{2,4}\)[ .-]*\d{3}[ .-]*\d{2,4}(?:[ .-]*\d{2,4})?"
    r")(?!\w)"
)
_PRIVATE_KEYS = frozenset(
    {
        "email",
        "phone",
        "telephone",
        "address",
        "street",
        "postal_code",
        "contact",
        "contacts",
        "contact_name",
        "contact_email",
        "contact_phone",
        "private_notes",
        "reference",
        "references",
    }
)


def _valid_email_domain(domain: str) -> bool:
    labels = domain.split(".")
    return (
        len(labels) >= 2
        and len(labels[-1]) >= 2
        and labels[-1].isascii()
        and labels[-1].isalpha()
        and all(
            label
            and not label.startswith("-")
            and not label.endswith("-")
            and all(character.isascii() and (character.isalnum() or character == "-") for character in label)
            for label in labels
        )
    )


def _redact_emails(text: str) -> str:
    pieces: list[str] = []
    cursor = 0
    search_from = 0
    while (at_index := text.find("@", search_from)) >= 0:
        start = at_index
        while start > cursor and text[start - 1] in _EMAIL_LOCAL_CHARACTERS:
            start -= 1
        end = at_index + 1
        while end < len(text) and text[end] in _EMAIL_DOMAIN_CHARACTERS:
            end += 1
        while end > at_index + 1 and text[end - 1] == ".":
            end -= 1
        local = text[start:at_index]
        domain = text[at_index + 1 : end]
        if local and _valid_email_domain(domain):
            pieces.extend((text[cursor:start], "[REDACTED_EMAIL]"))
            cursor = end
            search_from = end
        else:
            search_from = at_index + 1
    pieces.append(text[cursor:])
    return "".join(pieces)


def redact_contacts(text: str | None) -> str:
    return _PHONE_PATTERN.sub("[REDACTED_PHONE]", _redact_emails(text or ""))


def canonical_json_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def compute_payload_digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def _sanitize_attributes(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        raise AgentWorkError("invalid_result", "Evidence nesting exceeds the context limit")
    if isinstance(value, str):
        return redact_contacts(value)
    if isinstance(value, dict):
        return {
            str(k): _sanitize_attributes(v, depth + 1)
            for k, v in value.items()
            if str(k).casefold() not in _PRIVATE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_attributes(v, depth + 1) for v in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise AgentWorkError("invalid_result", "Evidence has an unsupported value")


def build_context_snapshot(
    db: Session,
    *,
    user_id: int,
    request_id: str,
    work_kind: WorkKind,
    instruction: str,
    target_job_id: int | None = None,
    target_application_id: str | None = None,
    target_resume_id: str | None = None,
    selected_fact_ids: list[str] | None = None,
    preset: dict[str, Any] | None = None,
    historical_grant_id: str | None = None,
) -> tuple[WorkContextPayload, str, dict[str, int | None]]:
    profile = db.query(CandidateProfile).populate_existing().filter_by(user_id=user_id).first()
    profile_id = profile.id if profile else ""
    revisions: dict[str, int | None] = {
        "profile": profile.revision if profile else None,
        "job": None,
        "application": None,
        "resume": None,
        "dossier": None,
    }
    query = (
        db.query(CareerFact)
        .populate_existing()
        .filter(
            CareerFact.profile_id == profile_id,
            CareerFact.verification_status == "confirmed",
            CareerFact.archived_at.is_(None),
            CareerFact.fact_type != "reference",
        )
    )
    if selected_fact_ids is not None:
        query = query.filter(CareerFact.id.in_(selected_fact_ids))
    models = (
        query.order_by(CareerFact.position, CareerFact.created_at, CareerFact.id)
        .limit(MAX_FACTS_PER_CONTEXT + 1)
        .all()
    )
    if len(models) > MAX_FACTS_PER_CONTEXT:
        raise AgentWorkError("invalid_result", "Select fewer confirmed facts for this request")
    if selected_fact_ids is not None and {f.id for f in models} != set(selected_fact_ids):
        raise AgentWorkError(
            "evidence_invalid", "Selected evidence is not available for this request"
        )
    facts: list[ContextFact] = []
    try:
        for fact in models:
            schema = PAYLOAD_SCHEMAS.get(fact.fact_type)
            if schema is None:
                raise ValueError("unknown fact type")
            # Only approved, documented fields cross the disclosure boundary.
            normalized = schema.model_validate(fact.payload).model_dump(
                mode="json", exclude_none=True
            )
            payload = _sanitize_attributes(
                {k: v for k, v in normalized.items() if k in schema.model_fields}
            )
            title = str(
                payload.get("title")
                or payload.get("role")
                or payload.get("name")
                or payload.get("qualification")
                or fact.fact_type
            )
            description = str(payload.get("description") or payload.get("summary") or "")
            facts.append(
                ContextFact(
                    id=fact.id,
                    kind=fact.fact_type,
                    title=title,
                    description=description,
                    attributes={
                        k: v
                        for k, v in payload.items()
                        if k not in {"title", "description", "summary"}
                    },
                    revision=profile.revision if profile else 1,
                )
            )
        preferences = (
            {}
            if profile is None
            else CareerPreferences.model_validate(profile.preferences or {}).model_dump(
                mode="json", exclude_none=True
            )
        )
        preferences = _sanitize_attributes(
            {
                k: v
                for k, v in preferences.items()
                if k in CareerPreferences.model_fields and k != "job_source_consents"
            }
        )
        if preset is not None:
            definition = get_template_preset(preset["id"], preset["version"])
            if definition.locale != preset.get("locale"):
                raise ValueError("template locale mismatch")
            preset = {
                "id": definition.id,
                "version": definition.version,
                "locale": definition.locale,
                "layout": definition.layout,
                "photo_policy": definition.photo_policy,
            }
    except (ValueError, KeyError, TypeError, ValidationError):
        raise AgentWorkError(
            "invalid_result", "Stored evidence or template selection is invalid for agent context"
        ) from None

    target: ContextJobSnapshot | None = None
    if target_job_id is not None:
        job = db.query(Job).populate_existing().filter_by(id=target_job_id, user_id=user_id).first()
        if job is None or job.scraped_job is None:
            raise AgentWorkError("work_not_found", "Target is unavailable")
        listing = job.scraped_job
        db.refresh(listing)
        revisions["job"] = job.content_revision
        try:
            target = ContextJobSnapshot(
                id=str(job.id),
                title=redact_contacts(listing.title),
                company=redact_contacts(listing.company),
                location=redact_contacts(listing.location) or None,
                url=listing.external_url,
                description=redact_contacts(listing.description),
                observed_at=listing.last_seen_at,
                revision=job.content_revision,
            )
        except (ValidationError, ValueError, TypeError):
            raise AgentWorkError(
                "invalid_result", "Target advert exceeds the context bounds"
            ) from None
    if target_application_id is not None:
        application = (
            db.query(Application)
            .populate_existing()
            .filter_by(id=target_application_id, user_id=user_id)
            .first()
        )
        if application is None:
            raise AgentWorkError("work_not_found", "Target is unavailable")
        if target_job_id is not None and application.job_id != target_job_id:
            raise AgentWorkError("invalid_result", "Application and job targets differ")
        revisions["application"] = application.revision
        dossier = (
            db.query(ApplicationDossierDraft)
            .populate_existing()
            .filter_by(application_id=application.id)
            .first()
        )
        revisions["dossier"] = dossier.revision if dossier else None
        if target is None:
            snapshot = application.job_snapshot or {}
            try:
                target = ContextJobSnapshot(
                    id=application.id,
                    title=redact_contacts(snapshot.get("title")),
                    company=redact_contacts(snapshot.get("company")),
                    location=redact_contacts(snapshot.get("location")) or None,
                    url=snapshot.get("external_url"),
                    description=redact_contacts(snapshot.get("description")),
                    revision=application.revision,
                )
            except (ValidationError, ValueError, TypeError):
                raise AgentWorkError(
                    "invalid_result", "Application advert is invalid for context"
                ) from None
    if target_resume_id is not None:
        resume = (
            db.query(ResumeDraft)
            .populate_existing()
            .filter_by(id=target_resume_id, profile_id=profile_id)
            .first()
        )
        if resume is None:
            raise AgentWorkError("work_not_found", "Target is unavailable")
        revisions["resume"] = resume.revision
    if work_kind == "analyze" and target_job_id is None:
        raise AgentWorkError("invalid_result", "Analysis requires exactly one owned job")
    context = WorkContextPayload(
        request_id=request_id,
        work_kind=work_kind,
        historical_grant_id=historical_grant_id,
        instruction=redact_contacts(instruction),
        input_digest="0" * 64,
        input_revisions=revisions,
        facts=facts,
        target_job=target,
        preferences=preferences,
        preset=preset,
        proposal_schema=TypeAdapter(ProposalPayload).json_schema(),
    )
    try:
        encoded = canonical_json_bytes(context.model_dump(mode="json"))
    except (ValueError, TypeError):
        raise AgentWorkError("invalid_result", "Context cannot be encoded safely") from None
    if len(encoded) > MAX_CONTEXT_BYTES:
        raise AgentWorkError("invalid_result", "Context exceeds 64 KiB; select less evidence")
    digest = hashlib.sha256(encoded).hexdigest()
    context.input_digest = digest
    return context, digest, revisions
