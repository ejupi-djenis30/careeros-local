from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from backend.ai.audit import (
    AIExecutionAudit,
    fingerprint_evidence_text,
    fingerprint_output,
    fingerprint_references,
    fingerprint_result_rows,
    record_execution,
)
from backend.ai.contracts import CoachResult, ValidationCode
from backend.ai.grounding import GroundingIssue, validate_grounding, validate_semantics
from backend.ai.match_evidence import fingerprint_match_input_rows
from backend.ai.match_policy import enforce_match_score_policy
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
    attempt_timeout_seconds: float | None = None
    total_timeout_seconds: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    output: BaseModel
    model_id: str
    repair_count: int
    evidence_ids: tuple[str, ...]
    usage: dict[str, int | None]
    execution_id: str | None
    output_fingerprint: str
    row_fingerprints: tuple[str, ...]
    row_input_fingerprints: tuple[str, ...]


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
            require_all=request.task_id == "job_match",
        )
        output_schema = copy.deepcopy(spec.schema())
        if request.task_id == "job_match" and request.expected_rows is not None:
            results_schema = output_schema.get("properties", {}).get("results")
            if isinstance(results_schema, dict):
                results_schema["minItems"] = request.expected_rows
                results_schema["maxItems"] = request.expected_rows
        schema_json = json.dumps(output_schema, ensure_ascii=False, separators=(",", ":"))
        row_constraint = (
            f"\nROW_COUNT_CONSTRAINT: Return exactly {request.expected_rows} result object(s). "
            "Each result object contains seven score fields; do not repeat rows.\n"
            if request.task_id == "job_match" and request.expected_rows is not None
            else ""
        )
        user_prompt = (
            f"TASK_INPUT:\n{request.user_prompt.strip()}\n\n"
            f"{row_constraint}OUTPUT_JSON_SCHEMA:\n{schema_json}\n\n{bundle.context}"
        )
        last_payload: dict[str, Any] | None = None
        issues: list[GroundingIssue] = []
        total_duration = 0
        usage_prompt = 0
        usage_completion = 0
        model_id = self.provider.model_id
        loop = asyncio.get_running_loop()
        deadline = (
            loop.time() + request.total_timeout_seconds
            if request.total_timeout_seconds is not None
            else None
        )
        for attempt in range(spec.repair_attempts + 1):
            prompt = user_prompt
            if attempt:
                prompt = self._repair_prompt(user_prompt, last_payload, issues)
            try:
                timeout = request.attempt_timeout_seconds
                if deadline is not None:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise TimeoutError
                    timeout = remaining if timeout is None else min(timeout, remaining)
                generated = await asyncio.wait_for(
                    self.provider.generate_structured_async(
                        StructuredInferenceRequest(
                            system_prompt=spec.system_instruction,
                            user_prompt=prompt,
                            json_schema=output_schema,
                            max_tokens=min(
                                spec.max_output_tokens,
                                request.max_output_tokens or spec.max_output_tokens,
                            ),
                            temperature=spec.temperature,
                            top_p=0.9,
                            seed=0,
                            task_id=spec.task_id,
                        )
                    ),
                    timeout=timeout,
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
                if request.task_id == "job_match":
                    # The local model is mandatory, but it only proposes scores.
                    # Mandatory requirements, polarity and conservative caps are
                    # deterministic server policy and therefore part of the audited row.
                    output = spec.output_model.model_validate(
                        enforce_match_score_policy(
                            output.model_dump(mode="json"),
                            bundle.documents,
                        )
                    )
                if request.task_id == "coach" and isinstance(output, CoachResult):
                    # The model selects narrow, cited propositions; the server owns the
                    # displayed answer. This prevents uncited prose from surviving beside
                    # otherwise-valid claims.
                    output = CoachResult.model_validate(
                        {
                            **output.model_dump(mode="json"),
                            "answer": "\n".join(claim.text.strip() for claim in output.claims),
                        }
                    )
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
                output_fingerprint = fingerprint_output(output)
                row_fingerprints = fingerprint_result_rows(output)
                execution_id = self._audit(
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
                    execution_id=execution_id,
                    output_fingerprint=output_fingerprint,
                    row_fingerprints=tuple(row_fingerprints),
                    row_input_fingerprints=tuple(
                        fingerprint_match_input_rows(request.evidence)
                        if request.task_id == "job_match"
                        else []
                    ),
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
    ) -> str | None:
        if self.db is None:
            return None
        execution = record_execution(
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
                    evidence_digests={
                        item.id: fingerprint_evidence_text(item.text) for item in request.evidence
                    },
                    input_digest=fingerprint_evidence_text(request.user_prompt),
                ),
                output_fingerprint=fingerprint_output(output) if output is not None else None,
                row_fingerprints=fingerprint_result_rows(output) if output is not None else [],
                row_input_fingerprints=(
                    fingerprint_match_input_rows(request.evidence)
                    if request.task_id == "job_match"
                    else []
                ),
                evidence_count=len(reference_ids),
                accepted=accepted,
                repair_count=min(repair_count, 1),
                validation_codes=list(dict.fromkeys(issue.code for issue in issues)),
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens or None,
                completion_tokens=completion_tokens or None,
            ),
        )
        return execution.id
