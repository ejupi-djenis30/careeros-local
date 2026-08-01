"""Content-free failure diagnostics for logs and persisted user-visible status."""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from backend.core.logging import _seal_failure_diagnostic, redact_text

MAX_PERSISTED_DIAGNOSTIC_CHARS = 512


class FailureCode(StrEnum):
    AUTH_TOKEN_DECODE_FAILED = "auth_token_decode_failed"
    AI_CRITIQUE_FAILED = "ai_critique_failed"
    AI_RERANK_FAILED = "ai_rerank_failed"
    CATALOG_PERSISTENCE_FAILED = "catalog_persistence_failed"
    CV_SUMMARY_FAILED = "cv_summary_failed"
    HTTP_REQUEST_FAILED = "http_request_failed"
    JOB_PERSISTENCE_FAILED = "job_persistence_failed"
    JOB_NORMALIZATION_FAILED = "job_normalization_failed"
    LOCAL_ANALYSIS_FAILED = "local_analysis_failed"
    LOCAL_MODEL_REQUIRED = "local_model_required"
    LOCAL_RESOURCE_LOAD_FAILED = "local_resource_load_failed"
    NORMALIZATION_VALIDATOR_FAILED = "normalization_validator_failed"
    NO_PERSISTED_JOBS = "no_persisted_jobs"
    PIPELINE_PROCESSING_FAILED = "pipeline_processing_failed"
    PIPELINE_TIMEOUT = "pipeline_timeout"
    PLAN_CACHE_READ_FAILED = "plan_cache_read_failed"
    PLAN_CACHE_WRITE_FAILED = "plan_cache_write_failed"
    PROFILE_NORMALIZATION_FAILED = "profile_normalization_failed"
    PROGRESSIVE_SAVE_FAILED = "progressive_save_failed"
    PROVIDER_ALL_FAILED = "provider_all_failed"
    PROVIDER_CLEANUP_FAILED = "provider_cleanup_failed"
    PROVIDER_DETAIL_FAILED = "provider_detail_failed"
    PROVIDER_HEALTH_FAILED = "provider_health_failed"
    PROVIDER_REQUEST_FAILED = "provider_request_failed"
    PROVIDER_RETRY_HEADER_INVALID = "provider_retry_header_invalid"
    PROVIDER_SEARCH_FAILED = "provider_search_failed"
    PROVIDER_TRANSFORM_FAILED = "provider_transform_failed"
    REPOSITORY_INTEGRITY_FAILED = "repository_integrity_failed"
    REPOSITORY_OPERATION_FAILED = "repository_operation_failed"
    RUNTIME_POLICY_FALLBACK = "runtime_policy_fallback"
    SEARCH_STOPPED = "search_stopped"
    SEARCH_UNEXPECTED = "search_unexpected"
    SERVER_SHUTDOWN = "server_shutdown"
    UNCLASSIFIED_STATUS_ERROR = "unclassified_status_error"
    VAULT_FILE_CLEANUP_FAILED = "vault_file_cleanup_failed"
    VAULT_SANITIZATION_FAILED = "vault_sanitization_failed"


class ActivityCode(StrEnum):
    ANALYSIS_DISCARDED = "analysis_discarded"
    ANALYSIS_REFINEMENT_SAVED = "analysis_refinement_saved"
    CATALOG_PERSISTED = "catalog_persisted"
    CATALOG_ROWS_SKIPPED = "catalog_rows_skipped"
    CRITIQUE_COMPLETE = "critique_complete"
    CV_SUMMARY_CACHE_HIT = "cv_summary_cache_hit"
    CV_SUMMARY_CREATED = "cv_summary_created"
    DEDUPLICATION_COMPLETE = "deduplication_complete"
    FILTER_DROPPED = "filter_dropped"
    FILTER_KEPT = "filter_kept"
    JOBS_NOT_PERSISTED = "jobs_not_persisted"
    LOCAL_ANALYSIS_FAILED = "local_analysis_failed"
    LOCAL_ANALYSIS_UNAVAILABLE = "local_analysis_unavailable"
    MODEL_READINESS_FAILED = "model_readiness_failed"
    NO_EXPLICIT_PLAN = "no_explicit_plan"
    NO_PROVIDER_FOR_TARGET = "no_provider_for_target"
    NO_RESULTS = "no_results"
    NORMALIZED_ROWS = "normalized_rows"
    OBSERVATIONS_REPROCESSING = "observations_reprocessing"
    OCCUPATION_FALLBACK = "occupation_fallback"
    PIPELINE_PROCESSING_FAILED = "pipeline_processing_failed"
    PIPELINE_STREAMING = "pipeline_streaming"
    PIPELINE_TIMEOUT = "pipeline_timeout"
    PLAN_BELOW_REQUESTED = "plan_below_requested"
    PLAN_BUILT = "plan_built"
    PLAN_CACHE_HIT = "plan_cache_hit"
    PLAN_CACHE_REJECTED = "plan_cache_rejected"
    PLAN_GENERATING = "plan_generating"
    PLAN_PREFERENCE_FILTERED = "plan_preference_filtered"
    PLAN_READY = "plan_ready"
    PLAN_VALIDATED = "plan_validated"
    PROFILE_NORMALIZATION_CACHE_HIT = "profile_normalization_cache_hit"
    PROFILE_NORMALIZATION_SAVED = "profile_normalization_saved"
    PROFILE_SNAPSHOT_CACHE_HIT = "profile_snapshot_cache_hit"
    PROGRESS_HEARTBEAT = "progress_heartbeat"
    PROVIDER_ALL_FAILED = "provider_all_failed"
    PROVIDER_EXECUTION_STARTED = "provider_execution_started"
    PROVIDER_RESULTS = "provider_results"
    QUERY_INVALID = "query_invalid"
    QUERY_RUNNING = "query_running"
    REFINEMENT_STARTED = "refinement_started"
    RERANK_COMPLETE = "rerank_complete"
    SEARCH_COMPLETE = "search_complete"
    SEARCH_HISTORY_ONLY = "search_history_only"
    SEARCH_RUNTIME_DEDUP_ONLY = "search_runtime_dedup_only"
    STALE_RESULT_SKIPPED = "stale_result_skipped"
    STRUCTURED_NO_RESULTS = "structured_no_results"


_PUBLIC_MESSAGES: dict[FailureCode, str] = {
    FailureCode.AUTH_TOKEN_DECODE_FAILED: "Local authentication token validation failed.",
    FailureCode.AI_CRITIQUE_FAILED: (
        "The optional critique pass was unavailable; validated base results were retained."
    ),
    FailureCode.AI_RERANK_FAILED: (
        "Comparative reranking was unavailable; the original validated scores were retained."
    ),
    FailureCode.CATALOG_PERSISTENCE_FAILED: (
        "A fetched batch could not be saved to the local catalog."
    ),
    FailureCode.CV_SUMMARY_FAILED: (
        "CV summarization was unavailable; CareerOS continued with a bounded local fallback."
    ),
    FailureCode.HTTP_REQUEST_FAILED: "A job-source HTTP request failed.",
    FailureCode.JOB_PERSISTENCE_FAILED: "A verified result could not be saved locally.",
    FailureCode.JOB_NORMALIZATION_FAILED: (
        "Job normalization was unavailable; the batch continued without field-level filters."
    ),
    FailureCode.LOCAL_ANALYSIS_FAILED: (
        "The required local-model analysis failed. Check model readiness and retry; "
        "no heuristic analysis was saved."
    ),
    FailureCode.LOCAL_MODEL_REQUIRED: (
        "Local analysis is not ready. Complete the model readiness checks and retry."
    ),
    FailureCode.LOCAL_RESOURCE_LOAD_FAILED: "A bundled local resource could not be loaded.",
    FailureCode.NORMALIZATION_VALIDATOR_FAILED: (
        "Normalization validation was unavailable for this batch."
    ),
    FailureCode.NO_PERSISTED_JOBS: "Jobs were analyzed but none could be persisted.",
    FailureCode.PIPELINE_PROCESSING_FAILED: (
        "Jobs were fetched but pipeline processing failed before analysis completed."
    ),
    FailureCode.PIPELINE_TIMEOUT: "The search exceeded its local processing time limit.",
    FailureCode.PLAN_CACHE_READ_FAILED: (
        "Cached search instructions could not be read; CareerOS rebuilt them."
    ),
    FailureCode.PLAN_CACHE_WRITE_FAILED: (
        "Search instructions could not be cached; the current run can continue."
    ),
    FailureCode.PROFILE_NORMALIZATION_FAILED: (
        "Profile normalization was unavailable; normalization filters were skipped for this search."
    ),
    FailureCode.PROGRESSIVE_SAVE_FAILED: "An analyzed listing could not be saved.",
    FailureCode.PROVIDER_ALL_FAILED: (
        "All provider searches failed before any jobs could be processed."
    ),
    FailureCode.PROVIDER_CLEANUP_FAILED: ("A job-source session could not be closed cleanly."),
    FailureCode.PROVIDER_DETAIL_FAILED: "Job details were unavailable from a job source.",
    FailureCode.PROVIDER_HEALTH_FAILED: "The job-source health check failed.",
    FailureCode.PROVIDER_REQUEST_FAILED: "A job-source request failed.",
    FailureCode.PROVIDER_RETRY_HEADER_INVALID: (
        "A job source returned an invalid retry instruction."
    ),
    FailureCode.PROVIDER_SEARCH_FAILED: "A job source could not complete this query.",
    FailureCode.PROVIDER_TRANSFORM_FAILED: (
        "A provider listing could not be converted to the local contract."
    ),
    FailureCode.REPOSITORY_INTEGRITY_FAILED: (
        "A local database constraint rejected the operation."
    ),
    FailureCode.REPOSITORY_OPERATION_FAILED: "A local database operation failed.",
    FailureCode.RUNTIME_POLICY_FALLBACK: (
        "The local runtime policy used its validated default configuration."
    ),
    FailureCode.SEARCH_STOPPED: "Search stopped by user.",
    FailureCode.SEARCH_UNEXPECTED: (
        "Search stopped because an internal processing step failed. Retry the search."
    ),
    FailureCode.SERVER_SHUTDOWN: "Server shutdown",
    FailureCode.UNCLASSIFIED_STATUS_ERROR: (
        "An unclassified internal error detail was suppressed."
    ),
    FailureCode.VAULT_FILE_CLEANUP_FAILED: "Staged local vault files could not be removed.",
    FailureCode.VAULT_SANITIZATION_FAILED: "Local vault storage sanitization failed.",
}

_ACTIVITY_TEMPLATES: dict[ActivityCode, tuple[str, tuple[str, ...]]] = {
    ActivityCode.ANALYSIS_DISCARDED: (
        "Search stopped during analysis; incomplete results were discarded.",
        (),
    ),
    ActivityCode.ANALYSIS_REFINEMENT_SAVED: (
        "Validated local-model analysis was saved without score mutation.",
        (),
    ),
    ActivityCode.CATALOG_PERSISTED: (
        "Shared catalog updated: {created} created, {updated} refreshed, "
        "{failed} failed, {recovered} conflicts recovered.",
        ("created", "updated", "failed", "recovered"),
    ),
    ActivityCode.CATALOG_ROWS_SKIPPED: (
        "{count} catalog row(s) were skipped before analysis.",
        ("count",),
    ),
    ActivityCode.CRITIQUE_COMPLETE: (
        "Critique refined {count} borderline result(s).",
        ("count",),
    ),
    ActivityCode.CV_SUMMARY_CACHE_HIT: ("Using the cached CV summary.", ()),
    ActivityCode.CV_SUMMARY_CREATED: ("CV summary prepared for local analysis.", ()),
    ActivityCode.DEDUPLICATION_COMPLETE: (
        "Deduplication completed: {found} found, {duplicates} duplicates, {unique} unique.",
        ("found", "duplicates", "unique"),
    ),
    ActivityCode.FILTER_DROPPED: (
        "Structured filters removed {dropped}/{total} result(s) across "
        "{reason_count} deterministic reason type(s).",
        ("dropped", "total", "reason_count"),
    ),
    ActivityCode.FILTER_KEPT: (
        "Structured filters retained {kept}/{total} result(s).",
        ("kept", "total"),
    ),
    ActivityCode.JOBS_NOT_PERSISTED: (
        "Analyzed results could not be saved to the local catalog.",
        (),
    ),
    ActivityCode.LOCAL_ANALYSIS_FAILED: (
        "Required local-model analysis failed; no heuristic result was saved.",
        (),
    ),
    ActivityCode.LOCAL_ANALYSIS_UNAVAILABLE: (
        "Required local-model analysis is unavailable; {count} result(s) were not saved.",
        ("count",),
    ),
    ActivityCode.MODEL_READINESS_FAILED: (
        "Local-model readiness failed before any provider request.",
        (),
    ),
    ActivityCode.NO_EXPLICIT_PLAN: (
        "No provider target was produced; add explicit search instructions.",
        (),
    ),
    ActivityCode.NO_PROVIDER_FOR_TARGET: (
        "No enabled provider accepted a normalized target.",
        (),
    ),
    ActivityCode.NO_RESULTS: ("No provider returned a result.", ()),
    ActivityCode.NORMALIZED_ROWS: (
        "Structured extraction normalized {count} persisted result(s).",
        ("count",),
    ),
    ActivityCode.OBSERVATIONS_REPROCESSING: (
        "Reprocessing {count} changed catalog observation(s).",
        ("count",),
    ),
    ActivityCode.OCCUPATION_FALLBACK: (
        "No occupation code was available; the keyword fallback was used.",
        (),
    ),
    ActivityCode.PIPELINE_PROCESSING_FAILED: (
        "Provider results were fetched, but pipeline processing did not complete.",
        (),
    ),
    ActivityCode.PIPELINE_STREAMING: (
        "Streaming provider results through normalization and local analysis.",
        (),
    ),
    ActivityCode.PIPELINE_TIMEOUT: (
        "The local search pipeline exceeded its {seconds}-second limit.",
        ("seconds",),
    ),
    ActivityCode.PLAN_BELOW_REQUESTED: (
        "The validated plan contains {available} of {requested} requested target(s).",
        ("available", "requested"),
    ),
    ActivityCode.PLAN_BUILT: (
        "Built {count} provider target(s) from explicit instructions.",
        ("count",),
    ),
    ActivityCode.PLAN_CACHE_HIT: (
        "Using {count} cached deterministic provider target(s).",
        ("count",),
    ),
    ActivityCode.PLAN_CACHE_REJECTED: (
        "Cached provider targets were incompatible and were rebuilt.",
        (),
    ),
    ActivityCode.PLAN_GENERATING: (
        "Building the deterministic explicit-input provider plan.",
        (),
    ),
    ActivityCode.PLAN_PREFERENCE_FILTERED: (
        "Plan preferences retained {kept} and removed {dropped} target(s).",
        ("kept", "dropped"),
    ),
    ActivityCode.PLAN_READY: (
        "Provider plan contains {count} validated explicit target(s).",
        ("count",),
    ),
    ActivityCode.PLAN_VALIDATED: (
        "Plan validation processed {input} target(s), retained {kept}, removed "
        "{invalid} invalid and {duplicate} duplicate target(s).",
        ("input", "kept", "invalid", "duplicate"),
    ),
    ActivityCode.PROFILE_NORMALIZATION_CACHE_HIT: (
        "Using cached candidate profile normalization.",
        (),
    ),
    ActivityCode.PROFILE_NORMALIZATION_SAVED: (
        "Candidate profile normalization completed and was stored locally.",
        (),
    ),
    ActivityCode.PROFILE_SNAPSHOT_CACHE_HIT: (
        "Using the cached compact profile snapshot.",
        (),
    ),
    ActivityCode.PROGRESS_HEARTBEAT: (
        "Search activity checkpoint {sequence}.",
        ("sequence",),
    ),
    ActivityCode.PROVIDER_ALL_FAILED: (
        "All provider requests failed before results could be processed.",
        (),
    ),
    ActivityCode.PROVIDER_EXECUTION_STARTED: (
        "Provider execution started.",
        (),
    ),
    ActivityCode.PROVIDER_RESULTS: (
        "A provider returned {count} result(s).",
        ("count",),
    ),
    ActivityCode.QUERY_INVALID: (
        "Skipped invalid provider target {index}.",
        ("index",),
    ),
    ActivityCode.QUERY_RUNNING: (
        "Running provider target {index}/{total} across {providers} provider(s).",
        ("index", "total", "providers"),
    ),
    ActivityCode.REFINEMENT_STARTED: (
        "Starting final refinement for {count} validated result(s).",
        ("count",),
    ),
    ActivityCode.RERANK_COMPLETE: (
        "Comparative calibration processed {count} result(s).",
        ("count",),
    ),
    ActivityCode.SEARCH_COMPLETE: (
        "Search complete: {saved} saved, {skipped} skipped.",
        ("saved", "skipped"),
    ),
    ActivityCode.SEARCH_HISTORY_ONLY: (
        "Every provider result was already present in profile history.",
        (),
    ),
    ActivityCode.SEARCH_RUNTIME_DEDUP_ONLY: (
        "All provider results collapsed during in-run deduplication.",
        (),
    ),
    ActivityCode.STALE_RESULT_SKIPPED: (
        "An analyzed result was skipped because a newer provider revision arrived.",
        (),
    ),
    ActivityCode.STRUCTURED_NO_RESULTS: (
        "No result passed structured filtering and verified analysis.",
        (),
    ),
}


def _compile_activity_pattern(
    template: str,
    parameter_names: tuple[str, ...],
) -> re.Pattern[str]:
    pattern = re.escape(template)
    for name in parameter_names:
        placeholder = re.escape("{" + name + "}")
        pattern = pattern.replace(
            placeholder,
            rf"(?P<{name}>0|[1-9][0-9]{{0,9}})",
        )
    return re.compile("^" + pattern + "$")


_ACTIVITY_PATTERNS = {
    code: _compile_activity_pattern(template, parameter_names)
    for code, (template, parameter_names) in _ACTIVITY_TEMPLATES.items()
}

_TRUSTED_EXCEPTION_MODULES = {
    "asyncio",
    "backend",
    "builtins",
    "concurrent",
    "httpcore",
    "httpx",
    "pydantic",
    "sqlalchemy",
    "tenacity",
}
_SAFE_EXCEPTION_TYPES = frozenset(
    {
        "CancelledError",
        "CircuitOpenError",
        "ConnectError",
        "Exception",
        "HTTPStatusError",
        "IntegrityError",
        "JSONDecodeError",
        "OSError",
        "OperationalError",
        "ProgrammingError",
        "ProviderError",
        "ReadTimeout",
        "RequestError",
        "RuntimeError",
        "TimeoutError",
        "TypeError",
        "ValidationError",
        "ValueError",
    }
)
_PUBLIC_VALUE_FACTORY = object()
_FAILURE_DIAGNOSTIC_FACTORY = object()
_CORRELATION_ID = re.compile(r"^[0-9a-f]{16}$")
_PROGRESS_LABEL = re.compile(r"^Query ([1-9][0-9]?|100)/([1-9][0-9]?|100)$")
_REFERENCED_MESSAGE = re.compile(
    r"^(?P<message>.+) Failure code: (?P<code>[a-z][a-z0-9_]{2,63})\. "
    r"Reference: (?P<reference>[0-9a-f]{16})\.$"
)


class PublicDiagnosticMessage(str):
    """Content-free status text produced only by the closed registry."""

    _registry_seal: object

    def __new__(
        cls,
        value: str,
        *,
        _factory: object | None = None,
    ) -> PublicDiagnosticMessage:
        if _factory is not _PUBLIC_VALUE_FACTORY:
            raise TypeError("Public diagnostic messages must come from the registry")
        if value not in _PUBLIC_MESSAGES.values():
            referenced = _REFERENCED_MESSAGE.fullmatch(value)
            if referenced is None:
                raise ValueError("Public diagnostic message is outside the registry")
            try:
                code = FailureCode(referenced.group("code"))
            except ValueError as error:
                raise ValueError("Public diagnostic code is outside the registry") from error
            if referenced.group("message") != _PUBLIC_MESSAGES[code]:
                raise ValueError("Public diagnostic message does not match its registry code")
        instance = super().__new__(cls, value)
        instance._registry_seal = _PUBLIC_VALUE_FACTORY
        return instance

    def __copy__(self) -> PublicDiagnosticMessage:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> PublicDiagnosticMessage:
        del memo
        return self


class PublicProgressLabel(str):
    """Content-free search progress label produced only by its bounded factory."""

    _registry_seal: object

    def __new__(
        cls,
        value: str,
        *,
        _factory: object | None = None,
    ) -> PublicProgressLabel:
        if _factory is not _PUBLIC_VALUE_FACTORY:
            raise TypeError("Progress labels must come from the bounded factory")
        match = _PROGRESS_LABEL.fullmatch(value)
        if match is None or int(match.group(1)) > int(match.group(2)):
            raise ValueError("Progress label is outside the bounded plan")
        instance = super().__new__(cls, value)
        instance._registry_seal = _PUBLIC_VALUE_FACTORY
        return instance

    def __copy__(self) -> PublicProgressLabel:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> PublicProgressLabel:
        del memo
        return self


class PublicActivityMessage(str):
    """Persistable search activity created only from numeric registry templates."""

    _registry_seal: object

    def __new__(
        cls,
        value: str,
        *,
        _factory: object | None = None,
    ) -> PublicActivityMessage:
        if _factory is not _PUBLIC_VALUE_FACTORY:
            raise TypeError("Activity messages must come from the registry")
        instance = super().__new__(cls, value)
        instance._registry_seal = _PUBLIC_VALUE_FACTORY
        return instance

    def __copy__(self) -> PublicActivityMessage:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> PublicActivityMessage:
        del memo
        return self


def is_public_diagnostic_message(value: object) -> bool:
    return (
        type(value) is PublicDiagnosticMessage
        and getattr(value, "_registry_seal", None) is _PUBLIC_VALUE_FACTORY
    )


def is_public_progress_label(value: object) -> bool:
    return (
        type(value) is PublicProgressLabel
        and getattr(value, "_registry_seal", None) is _PUBLIC_VALUE_FACTORY
    )


def is_public_activity_message(value: object) -> bool:
    return (
        type(value) is PublicActivityMessage
        and getattr(value, "_registry_seal", None) is _PUBLIC_VALUE_FACTORY
    )


@dataclass(frozen=True, slots=True, init=False)
class FailureDiagnostic:
    code: FailureCode
    exception_type: str
    correlation_id: str
    _diagnostic_seal: object = field(init=False, repr=False, compare=False)

    def __init__(
        self,
        code: FailureCode,
        exception_type: str,
        correlation_id: str,
        *,
        _factory: object | None = None,
    ) -> None:
        if _factory is not _FAILURE_DIAGNOSTIC_FACTORY:
            raise TypeError("Failure diagnostics must come from diagnose_failure")
        if not isinstance(code, FailureCode):
            raise TypeError("Failure diagnostic code is outside the registry")
        if exception_type not in _SAFE_EXCEPTION_TYPES:
            raise ValueError("Exception type is outside the diagnostic allowlist")
        if not _CORRELATION_ID.fullmatch(correlation_id):
            raise ValueError("Correlation ID is not a generated diagnostic reference")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "exception_type", exception_type)
        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "_diagnostic_seal", _FAILURE_DIAGNOSTIC_FACTORY)

    @property
    def public_message(self) -> PublicDiagnosticMessage:
        if not is_failure_diagnostic(self):
            raise TypeError("Failure diagnostic is not registry-sealed")
        return PublicDiagnosticMessage(
            f"{_PUBLIC_MESSAGES[self.code]} "
            f"Failure code: {self.code.value}. Reference: {self.correlation_id}.",
            _factory=_PUBLIC_VALUE_FACTORY,
        )


def is_failure_diagnostic(value: object) -> bool:
    try:
        return (
            type(value) is FailureDiagnostic
            and value._diagnostic_seal is _FAILURE_DIAGNOSTIC_FACTORY
            and isinstance(value.code, FailureCode)
            and value.exception_type in _SAFE_EXCEPTION_TYPES
            and _CORRELATION_ID.fullmatch(value.correlation_id) is not None
        )
    except (AttributeError, TypeError):
        return False


def _safe_exception_type(error: BaseException) -> str:
    error_type = type(error)
    module_root = error_type.__module__.split(".", 1)[0]
    name = error_type.__name__
    if module_root not in _TRUSTED_EXCEPTION_MODULES or name not in _SAFE_EXCEPTION_TYPES:
        return "Exception"
    return name


def diagnose_failure(
    error: BaseException,
    code: FailureCode,
) -> FailureDiagnostic:
    existing = getattr(error, "diagnostic", None)
    if is_failure_diagnostic(existing):
        return cast(FailureDiagnostic, existing)
    return FailureDiagnostic(
        code=code,
        exception_type=_safe_exception_type(error),
        correlation_id=secrets.token_hex(8),
        _factory=_FAILURE_DIAGNOSTIC_FACTORY,
    )


def public_status_message(code: FailureCode) -> PublicDiagnosticMessage:
    return PublicDiagnosticMessage(_PUBLIC_MESSAGES[code], _factory=_PUBLIC_VALUE_FACTORY)


def public_activity_message(
    code: ActivityCode,
    **metrics: int,
) -> PublicActivityMessage:
    if not isinstance(code, ActivityCode):
        raise TypeError("Activity code is outside the registry")
    template, parameter_names = _ACTIVITY_TEMPLATES[code]
    if set(metrics) != set(parameter_names):
        raise ValueError("Activity metrics do not match the registry template")
    normalized: dict[str, int] = {}
    for name in parameter_names:
        value = metrics[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("Activity metrics must be integers")
        if value < 0 or value > 1_000_000_000:
            raise ValueError("Activity metric is outside the bounded range")
        normalized[name] = value
    return PublicActivityMessage(
        template.format(**normalized),
        _factory=_PUBLIC_VALUE_FACTORY,
    )


def restore_public_activity_message(value: object) -> PublicActivityMessage:
    """Re-seal an exact numeric activity template after JSON persistence."""
    text = str(value)
    for pattern in _ACTIVITY_PATTERNS.values():
        match = pattern.fullmatch(text)
        if match is None:
            continue
        if any(int(metric) > 1_000_000_000 for metric in match.groupdict().values()):
            break
        return PublicActivityMessage(text, _factory=_PUBLIC_VALUE_FACTORY)
    raise ValueError("Persisted activity is outside the registry")


def restore_public_diagnostic_message(value: object) -> PublicDiagnosticMessage:
    """Re-seal an exact registry value after JSON persistence."""
    return PublicDiagnosticMessage(str(value), _factory=_PUBLIC_VALUE_FACTORY)


def public_progress_label(index: int, total: int) -> PublicProgressLabel:
    if index < 1 or total < 1 or index > total:
        raise ValueError("Search progress indices are outside their bounded plan")
    return PublicProgressLabel(
        f"Query {index}/{total}",
        _factory=_PUBLIC_VALUE_FACTORY,
    )


def restore_public_progress_label(value: object) -> PublicProgressLabel:
    """Re-seal an exact bounded progress label after JSON persistence."""
    return PublicProgressLabel(str(value), _factory=_PUBLIC_VALUE_FACTORY)


def public_progress_targets(total: int) -> list[dict[str, int]]:
    if total < 0 or total > 100:
        raise ValueError("Search progress target count is outside its bounded plan")
    return [{"index": index} for index in range(1, total + 1)]


def unclassified_status_error() -> FailureDiagnostic:
    return diagnose_failure(RuntimeError(), FailureCode.UNCLASSIFIED_STATUS_ERROR)


def log_failure(
    target: logging.Logger,
    diagnostic: FailureDiagnostic,
    *,
    level: int = logging.ERROR,
) -> None:
    if not is_failure_diagnostic(diagnostic):
        raise TypeError("Failure diagnostic is not registry-sealed")
    target.log(
        level,
        _seal_failure_diagnostic(
            diagnostic.code,
            diagnostic.exception_type,
            diagnostic.correlation_id,
        ),
    )


def sanitize_persisted_message(
    value: object,
    *,
    max_chars: int = MAX_PERSISTED_DIAGNOSTIC_CHARS,
) -> str:
    """Apply the logging redactor and a hard bound before local status persistence."""
    if max_chars < 32:
        raise ValueError("Persisted diagnostic bound is too small")
    text = redact_text(value).replace("\x00", "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
