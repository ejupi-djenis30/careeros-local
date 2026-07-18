from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from backend.ai.grounding import validate_grounding, validate_semantics
from backend.ai.models import AIEvaluationRun
from backend.ai.orchestrator import LocalAIOrchestrator, OrchestrationRequest
from backend.ai.repository import AIRepository
from backend.ai.retrieval import EvidenceDocument
from backend.ai.task_specs import TASK_SPECS
from backend.inference.ports import LocalInferencePort


class EvaluationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    kind: Literal["fact", "job", "profile", "document"]
    text: str = Field(min_length=1, max_length=16_000)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class FieldExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(pattern=r"^[A-Za-z0-9_.]+$", max_length=160)
    operator: Literal["equals", "contains", "gte", "lte"]
    value: Any


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$", max_length=80)
    task_id: str
    user_prompt: str = Field(min_length=1, max_length=16_000)
    evidence: list[EvaluationEvidence] = Field(default_factory=list, max_length=24)
    expected_rows: int | None = Field(default=None, ge=1, le=12)
    expected_output: dict[str, Any]
    expectations: list[FieldExpectation] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def known_task(self) -> "GoldenCase":
        if self.task_id not in TASK_SPECS:
            raise ValueError(f"unknown evaluation task: {self.task_id}")
        return self


class GoldenDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    synthetic_only: Literal[True]
    cases: list[GoldenCase] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_cases(self) -> "GoldenDataset":
        ids = [item.id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation case identifiers must be unique")
        return self


class CaseMetrics(BaseModel):
    case_id: str
    task_id: str
    schema_valid: bool
    semantic_valid: bool
    grounding_valid: bool
    assertions_passed: int
    assertions_total: int
    repair_count: int = Field(ge=0, le=1)
    duration_ms: int = Field(ge=0)
    error_codes: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.schema_valid
            and self.semantic_valid
            and self.grounding_valid
            and self.assertions_passed == self.assertions_total
        )


class EvaluationReport(BaseModel):
    dataset_version: str
    model_id: str
    runtime: str
    case_count: int
    passed_cases: int
    schema_pass_rate: float
    semantic_pass_rate: float
    grounding_pass_rate: float
    assertion_pass_rate: float
    repair_rate: float
    duration_ms: int
    peak_memory_bytes: int | None = Field(default=None, ge=0)
    model_profile: dict[str, Any] = Field(default_factory=dict)
    passed: bool
    result_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[CaseMetrics]

    def aggregate_metrics(self) -> dict[str, Any]:
        return {
            "passed_cases": self.passed_cases,
            "schema_pass_rate": self.schema_pass_rate,
            "semantic_pass_rate": self.semantic_pass_rate,
            "grounding_pass_rate": self.grounding_pass_rate,
            "assertion_pass_rate": self.assertion_pass_rate,
            "repair_rate": self.repair_rate,
            "peak_memory_bytes": self.peak_memory_bytes,
            "model_profile": self.model_profile,
        }


class EvaluationRunSummary(BaseModel):
    id: str
    dataset_version: str
    application_version: str
    model_id: str
    runtime_version: str
    case_count: int
    metrics: dict[str, Any]
    passed: bool
    duration_ms: int
    peak_memory_bytes: int | None
    result_fingerprint: str
    created_at: Any


def fixture_path(version: str = "1.0.0") -> Path:
    return Path(__file__).with_name("fixtures") / f"golden-{version}.json"


def load_dataset(path: Path | None = None) -> GoldenDataset:
    selected = path or fixture_path()
    return GoldenDataset.model_validate_json(selected.read_text(encoding="utf-8"))


def _resolve_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _assertion_passes(payload: dict[str, Any], assertion: FieldExpectation) -> bool:
    try:
        actual = _resolve_path(payload, assertion.path)
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    if assertion.operator == "equals":
        return bool(actual == assertion.value)
    if assertion.operator == "contains":
        return bool(assertion.value in actual)
    if assertion.operator == "gte":
        return bool(actual >= assertion.value)
    return bool(actual <= assertion.value)


def evaluate_case(
    case: GoldenCase,
    payload: dict[str, Any],
    *,
    repair_count: int = 0,
    duration_ms: int = 0,
) -> CaseMetrics:
    spec = TASK_SPECS[case.task_id]
    schema_valid = True
    semantic_valid = False
    grounding_valid = False
    error_codes: list[str] = []
    assertions_passed = 0
    try:
        output = spec.output_model.model_validate(payload)
    except Exception:
        schema_valid = False
        output = None
        error_codes.append("schema_invalid")
    if output is not None:
        semantic_issues = validate_semantics(
            case.task_id,
            output,
            expected_rows=case.expected_rows,
        )
        semantic_valid = not semantic_issues
        error_codes.extend(item.code.value for item in semantic_issues)
        grounding_issues = (
            validate_grounding(
                output,
                [EvidenceDocument(**item.model_dump()) for item in case.evidence],
            )
            if spec.evidence_required
            else []
        )
        grounding_valid = not grounding_issues
        error_codes.extend(item.code.value for item in grounding_issues)
        normalized = output.model_dump(mode="json")
        assertions_passed = sum(
            _assertion_passes(normalized, assertion) for assertion in case.expectations
        )
    return CaseMetrics(
        case_id=case.id,
        task_id=case.task_id,
        schema_valid=schema_valid,
        semantic_valid=semantic_valid,
        grounding_valid=grounding_valid,
        assertions_passed=assertions_passed,
        assertions_total=len(case.expectations),
        repair_count=repair_count,
        duration_ms=duration_ms,
        error_codes=list(dict.fromkeys(error_codes)),
    )


def _report(
    dataset: GoldenDataset,
    cases: list[CaseMetrics],
    *,
    model_id: str,
    runtime: str,
    duration_ms: int,
    peak_memory_bytes: int | None,
    model_profile: dict[str, Any],
) -> EvaluationReport:
    count = len(cases)
    assertions = sum(item.assertions_total for item in cases)
    assertion_passes = sum(item.assertions_passed for item in cases)
    raw = {
        "dataset_version": dataset.dataset_version,
        "model_id": model_id,
        "runtime": runtime,
        "cases": [item.model_dump(mode="json") for item in cases],
    }
    fingerprint = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    passed_cases = sum(item.passed for item in cases)
    return EvaluationReport(
        dataset_version=dataset.dataset_version,
        model_id=model_id,
        runtime=runtime,
        case_count=count,
        passed_cases=passed_cases,
        schema_pass_rate=sum(item.schema_valid for item in cases) / count,
        semantic_pass_rate=sum(item.semantic_valid for item in cases) / count,
        grounding_pass_rate=sum(item.grounding_valid for item in cases) / count,
        assertion_pass_rate=assertion_passes / assertions if assertions else 1.0,
        repair_rate=sum(item.repair_count for item in cases) / count,
        duration_ms=duration_ms,
        peak_memory_bytes=peak_memory_bytes,
        model_profile=model_profile,
        passed=passed_cases == count,
        result_fingerprint=fingerprint,
        cases=cases,
    )


def validate_offline_dataset(path: Path | None = None) -> EvaluationReport:
    started = time.monotonic()
    dataset = load_dataset(path)
    cases = [evaluate_case(case, case.expected_output) for case in dataset.cases]
    return _report(
        dataset,
        cases,
        model_id="fixture",
        runtime="offline-contract",
        duration_ms=round((time.monotonic() - started) * 1000),
        peak_memory_bytes=None,
        model_profile={
            "provider": "fixture",
            "model_id": "fixture",
            "runtime_capabilities": ["offline-contract"],
            "contract_versions": {
                task_id: spec.version for task_id, spec in sorted(TASK_SPECS.items())
            },
            "memory_scope": "not-measured",
        },
    )


def _resident_memory_bytes(process_id: int) -> int | None:
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(0x0410, False, process_id)
            if not handle:
                return None
            try:
                counters = ProcessMemoryCounters()
                counters.cb = ctypes.sizeof(counters)
                if not psapi.GetProcessMemoryInfo(
                    handle, ctypes.byref(counters), counters.cb
                ):
                    return None
                return int(counters.WorkingSetSize)
            finally:
                kernel32.CloseHandle(handle)
        if sys.platform.startswith("linux"):
            statm = Path(f"/proc/{process_id}/statm").read_text(encoding="ascii").split()
            return int(statm[1]) * int(os.sysconf("SC_PAGE_SIZE"))
        completed = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(process_id)],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return int(completed.stdout.strip()) * 1024
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


async def _sample_peak_memory(
    process_ids: tuple[int, ...], stop: asyncio.Event
) -> int:
    peak = 0
    while True:
        readings = [_resident_memory_bytes(process_id) for process_id in process_ids]
        peak = max(peak, sum(value for value in readings if value is not None))
        if stop.is_set():
            return peak
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.1)
        except TimeoutError:
            pass


async def run_live_evaluation(
    provider: LocalInferencePort,
    path: Path | None = None,
) -> EvaluationReport:
    started = time.monotonic()
    dataset = load_dataset(path)
    orchestrator = LocalAIOrchestrator(provider)
    results: list[CaseMetrics] = []
    provider_process_id = getattr(provider, "process_id", None)
    process_ids = (os.getpid(),) + (
        (provider_process_id,)
        if isinstance(provider_process_id, int) and provider_process_id != os.getpid()
        else ()
    )
    stop_sampling = asyncio.Event()
    memory_sampler = asyncio.create_task(_sample_peak_memory(process_ids, stop_sampling))
    try:
        for case in dataset.cases:
            case_started = time.monotonic()
            try:
                result = await orchestrator.execute(
                    OrchestrationRequest(
                        task_id=case.task_id,
                        user_prompt=case.user_prompt,
                        evidence=tuple(
                            EvidenceDocument(**item.model_dump()) for item in case.evidence
                        ),
                        expected_rows=case.expected_rows,
                    )
                )
                results.append(
                    evaluate_case(
                        case,
                        result.output.model_dump(mode="json"),
                        repair_count=result.repair_count,
                        duration_ms=round((time.monotonic() - case_started) * 1000),
                    )
                )
            except Exception as exc:
                results.append(
                    CaseMetrics(
                        case_id=case.id,
                        task_id=case.task_id,
                        schema_valid=False,
                        semantic_valid=False,
                        grounding_valid=False,
                        assertions_passed=0,
                        assertions_total=len(case.expectations),
                        repair_count=0,
                        duration_ms=round((time.monotonic() - case_started) * 1000),
                        error_codes=[type(exc).__name__],
                    )
                )
    finally:
        stop_sampling.set()
        peak_memory_bytes = await memory_sampler
    runtime_value: object = getattr(provider, "runtime_capabilities", frozenset())
    runtime: frozenset[str] = runtime_value if isinstance(runtime_value, frozenset) else frozenset()
    model_profile = {
        "provider": type(provider).__name__,
        "model_id": provider.model_id,
        "runtime_capabilities": sorted(runtime),
        "contract_versions": {
            task_id: spec.version for task_id, spec in sorted(TASK_SPECS.items())
        },
        "memory_scope": (
            "api-and-model-process-rss" if len(process_ids) > 1 else "evaluator-process-rss"
        ),
    }
    return _report(
        dataset,
        results,
        model_id=provider.model_id,
        runtime="local:" + ",".join(sorted(runtime)),
        duration_ms=round((time.monotonic() - started) * 1000),
        peak_memory_bytes=peak_memory_bytes,
        model_profile=model_profile,
    )


def _application_version() -> str:
    try:
        return importlib.metadata.version("careeros-local")
    except importlib.metadata.PackageNotFoundError:
        return "1.0.0"


def persist_report(db: Session, report: EvaluationReport) -> EvaluationRunSummary:
    evaluation = AIRepository(db).add_evaluation(
        AIEvaluationRun(
            dataset_version=report.dataset_version,
            application_version=_application_version(),
            model_id=report.model_id,
            runtime_version=report.runtime[:80],
            case_count=report.case_count,
            metrics=report.aggregate_metrics(),
            passed=report.passed,
            duration_ms=report.duration_ms,
            peak_memory_bytes=report.peak_memory_bytes,
            result_fingerprint=report.result_fingerprint,
        )
    )
    return EvaluationRunSummary.model_validate(evaluation, from_attributes=True)


def list_reports(db: Session, *, limit: int = 50) -> list[EvaluationRunSummary]:
    return [
        EvaluationRunSummary.model_validate(item, from_attributes=True)
        for item in AIRepository(db).list_evaluations(limit=limit)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CareerOS Local AI golden cases")
    parser.add_argument("--live", action="store_true", help="run the installed compact model")
    arguments = parser.parse_args()
    if arguments.live:
        from backend.providers.llm.factory import get_provider_for_step

        report = asyncio.run(run_live_evaluation(get_provider_for_step("default")))
    else:
        report = validate_offline_dataset()
    print(report.model_dump_json(indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
