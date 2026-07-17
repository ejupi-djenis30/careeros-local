from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.ai.contracts import ValidationCode
from backend.ai.models import AIExecution
from backend.ai.repository import AIRepository


class AIExecutionAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int | None = None
    task: str = Field(min_length=1, max_length=40)
    contract_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    model_id: str = Field(min_length=1, max_length=240)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_count: int = Field(ge=0)
    accepted: bool
    repair_count: int = Field(ge=0, le=1)
    validation_codes: list[ValidationCode] = Field(default_factory=list, max_length=12)
    duration_ms: int = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)


def fingerprint_references(
    *, task: str, reference_ids: list[str], contract_version: str
) -> str:
    canonical = json.dumps(
        {
            "contract_version": contract_version,
            "reference_ids": sorted(set(reference_ids)),
            "task": task,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_output(payload: BaseModel | dict[str, object]) -> str:
    value = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    canonical = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_execution(db: Session, audit: AIExecutionAudit) -> AIExecution:
    data = audit.model_dump(mode="json")
    data["validation_codes"] = [str(code) for code in audit.validation_codes]
    return AIRepository(db).add_execution(AIExecution(**data))
