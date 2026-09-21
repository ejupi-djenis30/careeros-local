"""Version-seven workspace record validation, without reviving agent authority."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter

from backend.agent_work.schemas import (
    MAX_CONTEXT_BYTES,
    MAX_RESULT_BYTES,
    ProposalPayload,
    WorkContextPayload,
)
from backend.applications.schemas import (
    MAX_DOSSIER_INPUT_BYTES,
    ApplicationTaskResponse,
    ManualJobSnapshot,
    validate_application_event_payload,
)
from backend.applications.snapshots import (
    APPLICATION_SNAPSHOT_SAFE_FIELDS,
    APPLICATION_SNAPSHOT_SCHEMA_VERSION,
)
from backend.career.goal_schemas import CareerGoalPayload
from backend.career.payloads import PAYLOAD_SCHEMAS, CareerPreferences, safe_url
from backend.career.schemas import CareerProfileWrite
from backend.portability.manifest import canonical_json, sha256
from backend.resumes.canvas_schemas import GenerationContext, ResumeCanvasDocument
from backend.resumes.canvas_validation import validate_canvas_references
from backend.resumes.schemas import FactContentOverride, ResumeSectionConfig
from backend.resumes.templates import get_template_preset


def _positive(value: Any) -> bool:
    return type(value) is int and value >= 1


def _uuid(value: Any) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def _timestamp(value: Any) -> bool:
    if isinstance(value, datetime):
        return True
    try:
        return isinstance(value, str) and bool(datetime.fromisoformat(value))
    except ValueError:
        return False


def _uuid_list(value: Any, *, label: str, maximum: int) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > maximum
        or any(not _uuid(item) for item in value)
        or len(value) != len(set(value))
    ):
        raise ValueError(f"Invalid {label}")
    return value


def _validate_profile_domain(tables: dict[str, list[dict[str, Any]]], version: int) -> None:
    if version < 7:
        return
    for row in tables["candidate_profiles"]:
        if not isinstance(row.get("preferences"), dict):
            raise ValueError("Candidate preferences must be an object")
        CareerPreferences.model_validate_json(canonical_json(row["preferences"]), strict=True)
        if not isinstance(row.get("location"), dict):
            raise ValueError("Candidate location must be an object")
        authorization = row.get("work_authorization")
        if (
            not isinstance(authorization, list)
            or len(authorization) > 100
            or any(not isinstance(item, str) or not item.strip() for item in authorization)
            or len({item.strip().casefold() for item in authorization}) != len(authorization)
        ):
            raise ValueError("Candidate work authorization is invalid")
        if not isinstance(row.get("display_name"), str) or not row["display_name"].strip():
            raise ValueError("Candidate display name is invalid")
        for field in ("website", "linkedin", "github"):
            safe_url(row.get(field))

    for row in tables["career_facts"]:
        fact_type = row.get("fact_type")
        schema = PAYLOAD_SCHEMAS.get(fact_type) if isinstance(fact_type, str) else None
        if schema is None or not isinstance(row.get("payload"), dict):
            raise ValueError("Career fact payload is invalid")
        schema.model_validate_json(canonical_json(row["payload"]), strict=True)
        status = row.get("verification_status")
        confidence = row.get("confidence")
        position = row.get("position")
        if (
            status not in {"draft", "confirmed", "imported"}
            or type(position) is not int
            or not 0 <= position <= 10_000
            or (
                confidence is not None
                and (type(confidence) not in {int, float} or not 0 <= confidence <= 1)
            )
            or (
                status == "imported"
                and (row.get("source_document_id") is None or confidence is None)
            )
        ):
            raise ValueError("Career fact verification metadata is invalid")

    for row in tables["career_goals"]:
        if not isinstance(row.get("payload"), dict):
            raise ValueError("Career goal payload is invalid")
        CareerGoalPayload.model_validate_json(canonical_json(row["payload"]), strict=True)

    if len(tables["candidate_profiles"]) == 1:
        profile = tables["candidate_profiles"][0]
        CareerProfileWrite.model_validate(
            {
                "expected_revision": profile.get("revision"),
                **{
                    field: profile.get(field)
                    for field in CareerProfileWrite.model_fields
                    if field not in {"expected_revision", "facts", "goals"}
                },
                "facts": tables["career_facts"],
                "goals": tables["career_goals"],
            }
        )


def _validate_application_match(value: Any) -> None:
    if not isinstance(value, dict) or type(value.get("receipt_verified")) is not bool:
        raise ValueError("Application match projection is invalid")
    if value["receipt_verified"]:
        expected = {
            "score",
            "analysis",
            "worth_applying",
            "receipt_verified",
            "execution_id",
            "row_fingerprint",
        }
        score = value.get("score")
        if (
            set(value) != expected
            or (score is not None and (type(score) is not int or not 0 <= score <= 100))
            or (value.get("analysis") is not None and not isinstance(value["analysis"], str))
            or (
                value.get("worth_applying") is not None
                and type(value["worth_applying"]) is not bool
            )
            or not _uuid(value.get("execution_id"))
            or re.fullmatch(r"[0-9a-f]{64}", str(value.get("row_fingerprint") or "")) is None
        ):
            raise ValueError("Verified application match projection is invalid")
        return
    expected = {
        "score",
        "analysis",
        "worth_applying",
        "receipt_verified",
        "quarantine_reason",
    }
    if (
        set(value) != expected
        or any(value.get(field) is not None for field in ("score", "analysis", "worth_applying"))
        or not isinstance(value.get("quarantine_reason"), str)
        or not value["quarantine_reason"].strip()
    ):
        raise ValueError("Quarantined application match projection is invalid")


def _validate_resume_domain(tables: dict[str, list[dict[str, Any]]], version: int) -> None:
    if version < 7:
        return
    for row in tables["resume_drafts"]:
        selected = _uuid_list(
            row.get("selected_fact_ids"), label="resume selected facts", maximum=300
        )
        ResumeSectionConfig.model_validate_json(
            canonical_json(row.get("section_config")), strict=True
        )
        overrides = row.get("content_overrides")
        if not isinstance(overrides, dict):
            raise ValueError("Resume content overrides must be an object")
        if any(not _uuid(key) for key in overrides) or set(overrides) - set(selected):
            raise ValueError("Resume content overrides must reference selected facts")
        for override in overrides.values():
            FactContentOverride.model_validate_json(canonical_json(override), strict=True)
        canvas_value = row.get("canvas_document")
        if not isinstance(canvas_value, dict):
            raise ValueError("Resume canvas must be an object")
        if canvas_value:
            canvas = ResumeCanvasDocument.model_validate_json(
                canonical_json(canvas_value), strict=True
            )
            validate_canvas_references(canvas, set(selected))
            if row.get("template_kind") == "ats" and canvas.style.columns != 1:
                raise ValueError("ATS resumes must use a single-column canvas")
        generation = row.get("generation_context")
        if not isinstance(generation, dict):
            raise ValueError("Resume generation context must be an object")
        if generation:
            GenerationContext.model_validate_json(canonical_json(generation), strict=True)

    for row in tables["resume_versions"]:
        selected = _uuid_list(
            row.get("selected_fact_ids"), label="published resume selected facts", maximum=300
        )
        if not isinstance(row.get("snapshot"), dict) or not isinstance(
            row.get("quality_report"), dict
        ):
            raise ValueError("Published resume metadata must be objects")
        snapshot = row["snapshot"]
        if snapshot.get("schema_version") == 3:
            snapshot_selected = _uuid_list(
                snapshot.get("selected_fact_ids"),
                label="published resume snapshot selected facts",
                maximum=300,
            )
            facts = snapshot.get("facts")
            if not isinstance(facts, list) or any(not isinstance(fact, dict) for fact in facts):
                raise ValueError("Published resume snapshot facts are invalid")
            snapshot_fact_ids = [fact.get("id") for fact in facts]
            if snapshot_selected != selected or set(snapshot_fact_ids) != set(selected):
                raise ValueError("Published resume snapshot evidence is inconsistent")
            for fact in facts:
                fact_type = fact.get("fact_type")
                schema = PAYLOAD_SCHEMAS.get(fact_type) if isinstance(fact_type, str) else None
                if schema is None or not isinstance(fact.get("payload"), dict):
                    raise ValueError("Published resume snapshot fact is invalid")
                schema.model_validate_json(canonical_json(fact["payload"]), strict=True)
        resume_snapshot = snapshot.get("resume")
        if resume_snapshot is not None and not isinstance(resume_snapshot, dict):
            raise ValueError("Published resume snapshot layout is invalid")
        canvas_value = (resume_snapshot or {}).get("canvas_document")
        if canvas_value:
            canvas = ResumeCanvasDocument.model_validate_json(
                canonical_json(canvas_value), strict=True
            )
            validate_canvas_references(canvas, set(selected))


def _validate_application_domain(
    tables: dict[str, list[dict[str, Any]]], version: int
) -> None:
    if version < 7:
        return
    stages = {
        "saved",
        "preparing",
        "applied",
        "screening",
        "interview",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        "archived",
    }
    event_types = {
        "stage",
        "note",
        "task",
        "contact",
        "interview",
        "preparation",
        "task_created",
        "task_updated",
        "task_completed",
        "task_reopened",
        "task_cancelled",
        "dossier_published",
    }
    for row in tables["applications"]:
        snapshot = row.get("job_snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("Application snapshot must be an object")
        if (
            set(snapshot) - (APPLICATION_SNAPSHOT_SAFE_FIELDS | {"schema_version", "match"})
            or snapshot.get("schema_version") != APPLICATION_SNAPSHOT_SCHEMA_VERSION
        ):
            raise ValueError("Application snapshot shape is invalid")
        title = snapshot.get("title")
        company = snapshot.get("company")
        if (
            row.get("current_stage") not in stages
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(company, str)
            or not company.strip()
        ):
            raise ValueError("Application snapshot identity is invalid")
        ManualJobSnapshot.model_validate_json(
            canonical_json(
                {
                    field: snapshot[field]
                    for field in ManualJobSnapshot.model_fields
                    if field in snapshot
                }
            ),
            strict=True,
        )
        publication_date = snapshot.get("publication_date")
        if publication_date is not None:
            if not isinstance(publication_date, str):
                raise ValueError("Application publication date is invalid")
            date.fromisoformat(publication_date)
        for field, maximum in (("platform", 40), ("platform_job_id", 255)):
            value = snapshot.get(field)
            if value is not None and (
                not isinstance(value, str) or not value.strip() or len(value) > maximum
            ):
                raise ValueError("Application source identity is invalid")
        _validate_application_match(snapshot.get("match"))
    for row in tables["application_events"]:
        event_type = row.get("event_type")
        stage = row.get("stage")
        payload = row.get("payload")
        if (
            event_type not in event_types
            or (event_type == "stage" and stage not in stages)
            or (event_type != "stage" and stage is not None)
            or not isinstance(payload, dict)
            or (
                event_type in {"note", "contact", "interview"}
                and (not isinstance(row.get("note"), str) or not row["note"].strip())
            )
        ):
            raise ValueError("Application event is invalid")
        if event_type == "dossier_published":
            if len(canonical_json(payload)) > MAX_DOSSIER_INPUT_BYTES:
                raise ValueError("Published dossier event is too large")
        else:
            validate_application_event_payload(payload)
        if event_type in {
            "task_created",
            "task_updated",
            "task_completed",
            "task_reopened",
            "task_cancelled",
        }:
            task = payload.get("task")
            if (
                set(payload) != {"schema_version", "task"}
                or payload.get("schema_version") != "1.0"
                or not isinstance(task, dict)
                or set(task) != set(ApplicationTaskResponse.model_fields)
            ):
                raise ValueError("Application task event payload is invalid")
            ApplicationTaskResponse.model_validate_json(canonical_json(task), strict=True)
        if event_type == "preparation":
            changed = payload.get("changed_fields")
            allowed_fields = {
                "title",
                "company",
                "description",
                "application_url",
                "application_email",
                "resume_version_id",
            }
            if (
                set(payload) != {"changed_fields"}
                or not isinstance(changed, list)
                or not changed
                or any(not isinstance(field, str) for field in changed)
                or len(changed) != len(set(changed))
                or set(changed) - allowed_fields
            ):
                raise ValueError("Application preparation event payload is invalid")


def validate_workspace_records(tables: dict[str, list[dict[str, Any]]], version: int) -> None:
    """Validate bounded historical records. Only legacy metadata is backfilled."""
    _validate_profile_domain(tables, version)
    _validate_resume_domain(tables, version)
    _validate_application_domain(tables, version)
    for name in ("resume_drafts", "resume_versions"):
        for row in tables[name]:
            fields = {"template_id", "template_version", "locale"}
            if version < 7 and not fields.intersection(row):
                row.update(
                    template_id="swiss-software-en"
                    if row.get("template_kind") == "photo"
                    else "software-en",
                    template_version=1,
                    locale="en",
                )
            if not fields.issubset(row) or not _positive(row["template_version"]):
                raise ValueError("Invalid resume template metadata")
            preset = get_template_preset(row["template_id"], row["template_version"])
            if (
                row["locale"] not in {"en", "de"}
                or row.get("template_kind") != preset.template_kind
            ):
                raise ValueError("Inconsistent resume template metadata")
    for row in tables["source_documents"]:
        if version < 7:
            row.setdefault("source_role", "profile")
        if row.get("source_role") not in {"profile", "narrative", "goals", "template_reference"}:
            raise ValueError("Invalid source document role")

    requests = {row["id"]: row for row in tables["agent_work_requests"]}
    proposal_requests: set[str] = set()
    for row in requests.values():
        context = row.get("context_snapshot")
        if not isinstance(context, dict) or len(canonical_json(context)) > MAX_CONTEXT_BYTES:
            raise ValueError("Invalid agent context size")
        WorkContextPayload.model_validate_json(canonical_json(context), strict=True)
        digest_context = {**context, "input_digest": "0" * 64}
        if (
            not _positive(row.get("revision"))
            or row.get("work_kind") not in {"discover", "analyze", "materials"}
            or row.get("state")
            not in {"queued", "returned", "accepted", "rejected", "canceled", "expired"}
            or not isinstance(row.get("instruction"), str)
            or not 1 <= len(row["instruction"]) <= 4000
            or context.get("request_id") != row["id"]
            or context.get("work_kind") != row["work_kind"]
            or context.get("input_digest") != row.get("input_digest")
            or sha256(canonical_json(digest_context)) != row.get("input_digest")
            or context.get("input_revisions") != row.get("input_revisions")
            or row.get("bound_grant_id") is not None
            or any(
                not _timestamp(row.get(field))
                for field in ("created_at", "updated_at", "expires_at")
            )
            or (
                row.get("error_code") is not None
                and (not isinstance(row["error_code"], str) or len(row["error_code"]) > 64)
            )
        ):
            raise ValueError("Invalid agent work history")
        preset_fields = (row.get("preset_id"), row.get("preset_version"), row.get("locale"))
        if any(value is not None for value in preset_fields):
            if (
                not isinstance(preset_fields[0], str)
                or not _positive(preset_fields[1])
                or preset_fields[2] not in {"en", "de"}
            ):
                raise ValueError("Invalid agent template selection")
            get_template_preset(preset_fields[0], preset_fields[1])
        revisions = row["input_revisions"]
        if set(revisions) - {"profile", "job", "application", "resume", "dossier"} or any(
            value is not None and not _positive(value) for value in revisions.values()
        ):
            raise ValueError("Invalid agent input revisions")
        selected = row.get("selected_fact_ids")
        if selected is not None and (
            not isinstance(selected, list)
            or len(selected) > 100
            or any(not _uuid(value) for value in selected)
            or len(set(selected)) != len(selected)
        ):
            raise ValueError("Invalid agent selected evidence")
        if row.get("target_job_id") is not None and not _positive(row["target_job_id"]):
            raise ValueError("Invalid agent target")
        receipt = row.get("accepted_receipt")
        if receipt is not None and (
            not isinstance(receipt, dict)
            or len(canonical_json(receipt)) > MAX_CONTEXT_BYTES
            or receipt.get("request_id") != row["id"]
        ):
            raise ValueError("Invalid agent acceptance history")
        if row["state"] == "accepted" and receipt is None:
            raise ValueError("Accepted work is missing its historical receipt")
    for row in tables["agent_proposals"]:
        request_id = row.get("request_id")
        if (
            not isinstance(request_id, str)
            or request_id not in requests
            or request_id in proposal_requests
        ):
            raise ValueError("Invalid proposal relationship")
        proposal_requests.add(request_id)
        payload = row.get("payload")
        if not isinstance(payload, dict) or len(canonical_json(payload)) > MAX_RESULT_BYTES:
            raise ValueError("Invalid proposal size")
        TypeAdapter(ProposalPayload).validate_json(canonical_json(payload), strict=True)
        if (
            row.get("contract_version") != 1
            or type(row.get("contract_version")) is not int
            or row.get("submitting_grant_id") is not None
            or type(row.get("review_required")) is not bool
            or not _timestamp(row.get("created_at"))
            or not isinstance(row.get("client_label"), str)
            or not 1 <= len(row["client_label"]) <= 120
            or (
                row.get("model_label") is not None
                and (not isinstance(row["model_label"], str) or len(row["model_label"]) > 120)
            )
            or not isinstance(row.get("idempotency_key"), str)
            or re.fullmatch(r"[!-~]{1,100}", row["idempotency_key"]) is None
            or payload.get("kind") != requests[request_id]["work_kind"]
            or sha256(canonical_json(payload)) != row.get("payload_digest")
        ):
            raise ValueError("Invalid agent proposal history")
        receipt = requests[request_id].get("accepted_receipt")
        if receipt is not None and receipt.get("proposal_id") != row["id"]:
            raise ValueError("Invalid accepted proposal relationship")
    for row in requests.values():
        if row["state"] in {"accepted", "returned"} and row["id"] not in proposal_requests:
            raise ValueError("Agent result history is incomplete")
