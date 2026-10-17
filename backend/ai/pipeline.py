"""Compatibility composition and dependency exports for the local AI pipeline.

The explicit re-exports preserve legacy import and monkeypatch paths. Focused
capabilities own their dependencies; assigning an exported dependency here still
forwards it to the capabilities that use it.
"""

import sys
import types
from typing import Any, Dict

from tenacity import RetryError

from backend.ai import (
    job_normalization,
    matching,
    planning,
    profile_normalization,
    reranking,
    runtime_policy,
)
from backend.ai.job_normalization import JobNormalizationMixin
from backend.ai.matching import MatchingMixin
from backend.ai.orchestrator import (
    LocalAIOrchestrator as LocalAIOrchestrator,
)
from backend.ai.orchestrator import (
    OrchestrationRequest as OrchestrationRequest,
)
from backend.ai.planning import PlanningMixin
from backend.ai.profile_normalization import ProfileNormalizationMixin
from backend.ai.reranking import RerankingMixin
from backend.ai.runtime_policy import RuntimePolicyMixin
from backend.core.config import settings as settings
from backend.providers.circuit_breaker import (
    CircuitOpenError as CircuitOpenError,
)
from backend.providers.circuit_breaker import (
    CircuitState as CircuitState,
)
from backend.providers.circuit_breaker import (
    circuit_registry as circuit_registry,
)
from backend.providers.llm.factory import get_provider_for_step as get_provider_for_step
from backend.services.search.prompt_compaction import compact_prompt_text as compact_prompt_text
from backend.services.search.query_contracts import (
    compute_plan_input_fingerprint as compute_plan_input_fingerprint,
)
from backend.services.search.query_contracts import (
    exact_query_fingerprint as exact_query_fingerprint,
)
from backend.services.search.query_contracts import (
    loose_query_fingerprint as loose_query_fingerprint,
)
from backend.services.search.query_contracts import (
    normalize_domain as normalize_domain,
)
from backend.services.search.query_contracts import (
    normalize_search_item as normalize_search_item,
)
from backend.services.search.query_contracts import (
    sanitize_prompt_text as sanitize_prompt_text,
)


def _unwrap_retry_error(exc: Exception) -> tuple[Exception, str]:
    """Extract the real cause from a tenacity RetryError and format a message.

    Returns (real_exception, formatted_message) where formatted_message
    includes the HTTP status code when the underlying error is an APIStatusError.
    """
    real_exc = exc
    if isinstance(exc, RetryError):
        try:
            candidate = exc.last_attempt.exception()
            if isinstance(candidate, Exception):
                real_exc = candidate
        except Exception:
            pass
    status_code = getattr(real_exc, "status_code", None)
    msg = str(real_exc)
    if status_code:
        msg = f"HTTP {status_code}: {msg}"
    return real_exc, msg


class LLMService(
    RuntimePolicyMixin,
    PlanningMixin,
    ProfileNormalizationMixin,
    JobNormalizationMixin,
    MatchingMixin,
    RerankingMixin,
):
    """Compatibility composition of the focused local-AI capabilities."""

    _STEP_PROMPT_TARGET_ATTRS = {
        "match": "MATCH_PROMPT_TARGET_CHARS",
        "normalize": "NORMALIZE_PROMPT_TARGET_CHARS",
    }
    _STEP_DESCRIPTION_TARGET_ATTRS = {
        "match": "MATCH_PROMPT_JOB_MAX_DESCRIPTION_CHARS",
        "normalize": "NORMALIZE_PROMPT_JOB_MAX_DESCRIPTION_CHARS",
    }
    _STEP_BATCH_ATTRS = {
        "match": "ANALYSIS_BATCH_SIZE",
        "normalize": "NORMALIZE_BATCH_SIZE",
    }

    def __init__(self):
        self._provider_cache: Dict[str, Any] = {}


_IMPLEMENTATION_MODULES = (
    runtime_policy,
    planning,
    profile_normalization,
    job_normalization,
    matching,
    reranking,
)


class _PipelineModule(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for module in _IMPLEMENTATION_MODULES:
            if hasattr(module, name):
                setattr(module, name, value)


sys.modules[__name__].__class__ = _PipelineModule

llm_service = LLMService()
