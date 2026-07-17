from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from backend.ai.audit import (
    AIExecutionAudit,
    fingerprint_output,
    fingerprint_references,
    record_execution,
)
from backend.ai.contracts import ValidationCode
from backend.ai.grounding import GroundingIssue, validate_grounding, validate_semantics
from backend.ai.retrieval import EvidenceDocument, retrieve_evidence
from backend.ai.task_specs import TASK_SPECS
from backend.inference.ports import LocalInferencePort, StructuredInferenceRequest


class AIValidationError(RuntimeError):
    def __init__(self, task_id: str, issues: list[GroundingIssue]):
        self.task_id = task_id
        self.issues = issues
        super().__init__(
            f"Local AI output failed {task_id} validation: "
            + ", ".join(sorted({issue.code.value for issue in issues}))
        )


@dataclass(frozen=True, slots=True)
class OrchestrationRequest:
    task_id: str
    user_prompt: str
    evidence: tuple[EvidenceDocument, ...] = ()
    expected_rows: int | None = None
    user_id: int | None = None


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    output: BaseModel
    model_id: str
    repair_count: int
    evidence_ids: tuple[str, ...]
    usage: dict[str, int | None]


class LocalAIOrchestrator:
    def __init__(self, provider: LocalInferencePort, db: Session | None = None) -> None:
        self.provider = provider
        self.db = db

    async def execute(self, request: OrchestrationRequest) -> OrchestrationResult:
        spec = TASK_SPECS.get(request.task_id)
        if spec is None:
            raise KeyError(f"Unknown local AI task: {request.task_id}")
        bundle = retrieve_evidence(
            request.user_prompt,
            request.evidence,
            max_context_chars=spec.max_context_chars,
            limit=20,
        )
        schema_json = json.dumps(spec.schema(), ensure_ascii=False, separators=(",", ":"))
        user_prompt = (
            f"TASK_INPUT:\n{request.user_prompt.strip()}\n\n"
            f"OUTPUT_JSON_SCHEMA:\n{schema_json}\n\n{bundle.context}"
        )
        last_payload: dict[str, Any] | None = None
        issues: list[GroundingIssue] = []
        total_duration = 0
        usage_prompt = 0
        usage_completion = 0
        model_id = self.provider.model_id
        for attempt in range(spec.repair_attempts + 1):
            prompt = user_prompt
            if attempt:
                prompt = self._repair_prompt(user_prompt, last_payload, issues)
            try:
                generated = await self.provider.generate_structured_async(
                    StructuredInferenceRequest(
                        system_prompt=spec.system_instruction,
                        user_prompt=prompt,
                        json_schema=spec.schema(),
                        max_tokens=spec.max_output_tokens,
                        temperature=spec.temperature,
                        top_p=0.9,
                        seed=0,
                        task_id=spec.task_id,
                    )
                )
                model_id = generated.model_id
                total_duration += generated.duration_ms
                usage_prompt += generated.usage.prompt_tokens or 0
                usage_completion += generated.usage.completion_tokens or 0
                last_payload = generated.payload
            except Exception as exc:
                issues = [GroundingIssue(ValidationCode.RUNTIME_ERROR, type(exc).__name__)]
                if attempt >= spec.repair_attempts:
                    self._audit(
                        request,
                        spec.version,
                        model_id,
                        bundle.reference_ids,
                        None,
                        False,
                        attempt,
                        issues,
                        total_duration,
                        usage_prompt,
                        usage_completion,
                    )
                    raise
                continue
            try:
                output = spec.output_model.model_validate(last_payload)
                issues = validate_semantics(
                    spec.task_id,
                    output,
                    expected_rows=request.expected_rows,
                )
                if spec.evidence_required:
                    issues.extend(validate_grounding(output, bundle.documents))
            except ValidationError as exc:
                issues = [
                    GroundingIssue(
                        ValidationCode.SCHEMA_INVALID,
                        "; ".join(error["msg"] for error in exc.errors()[:8]),
                    )
                ]
            if not issues:
                self._audit(
                    request,
                    spec.version,
                    model_id,
                    bundle.reference_ids,
                    output,
                    True,
                    attempt,
                    issues,
                    total_duration,
                    usage_prompt,
                    usage_completion,
                )
                return OrchestrationResult(
                    output=output,
                    model_id=model_id,
                    repair_count=attempt,
                    evidence_ids=tuple(bundle.reference_ids),
                    usage={
                        "prompt_tokens": usage_prompt or None,
                        "completion_tokens": usage_completion or None,
                    },
                )
        self._audit(
            request,
            spec.version,
            model_id,
            bundle.reference_ids,
            last_payload,
            False,
            spec.repair_attempts,
            issues,
            total_duration,
            usage_prompt,
            usage_completion,
        )
        raise AIValidationError(spec.task_id, issues)

    @staticmethod
    def _repair_prompt(
        original_prompt: str,
        payload: dict[str, Any] | None,
        issues: list[GroundingIssue],
    ) -> str:
        failure_codes = sorted({issue.code.value for issue in issues})
        return (
            f"{original_prompt}\n\nREPAIR_ONCE:\n"
            f"Validation codes: {json.dumps(failure_codes)}\n"
            "Return a complete replacement JSON object. Do not add facts or citations.\n"
            f"INVALID_OUTPUT_JSON:\n{json.dumps(payload or {}, ensure_ascii=False)}"
        )

    def _audit(
        self,
        request: OrchestrationRequest,
        version: str,
        model_id: str,
        reference_ids: list[str],
        output: BaseModel | dict[str, Any] | None,
        accepted: bool,
        repair_count: int,
        issues: list[GroundingIssue],
        duration_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        if self.db is None:
            return
        record_execution(
            self.db,
            AIExecutionAudit(
                user_id=request.user_id,
                task=request.task_id,
                contract_version=version,
                model_id=model_id,
                input_fingerprint=fingerprint_references(
                    task=request.task_id,
                    reference_ids=reference_ids,
                    contract_version=version,
                ),
                output_fingerprint=fingerprint_output(output) if output is not None else None,
                evidence_count=len(reference_ids),
                accepted=accepted,
                repair_count=min(repair_count, 1),
                validation_codes=list(dict.fromkeys(issue.code for issue in issues)),
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens or None,
                completion_tokens=completion_tokens or None,
            ),
        )
