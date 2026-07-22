"""Domain slice extracted from the local AI compatibility pipeline."""

# ruff: noqa: F401

import asyncio
import logging
from typing import Any, Dict, List, Optional

from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.ai.orchestrator import LocalAIOrchestrator, OrchestrationRequest
from backend.core.config import settings
from backend.providers.circuit_breaker import CircuitOpenError, CircuitState, circuit_registry
from backend.providers.llm.factory import get_provider_for_step
from backend.services.search.prompt_compaction import compact_prompt_text
from backend.services.search.query_contracts import (
    compute_plan_input_fingerprint,
    exact_query_fingerprint,
    loose_query_fingerprint,
    normalize_domain,
    normalize_search_item,
    sanitize_prompt_text,
)

logger = logging.getLogger(__name__)


def _is_retryable_plan_error(exc: Exception) -> bool:
    """Return True for transient PLAN-step failures worth retrying."""
    real_exc = exc
    if isinstance(exc, RetryError):
        try:
            candidate = exc.last_attempt.exception()
            if isinstance(candidate, Exception):
                real_exc = candidate
        except Exception:
            pass

    if isinstance(real_exc, (asyncio.TimeoutError, TimeoutError, CircuitOpenError)):
        return True

    error_text = str(real_exc).lower()
    retryable_fragments = (
        "rate limit",
        "timeout",
        "timed out",
        "temporar",
        "connection reset",
        "connection aborted",
        "connection error",
        "502",
        "503",
        "504",
    )
    return any(fragment in error_text for fragment in retryable_fragments)


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


def _query_fingerprint(search: Dict[str, Any]) -> str:
    return exact_query_fingerprint(search)


class RerankingMixin:
    async def rerank_top_jobs(
        self,
        top_jobs: List[Dict[str, Any]],
        profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Comparative re-ranking pass on the top-N jobs.

        Instead of scoring each job in isolation (which biases scores up),
        this pass gives the LLM ALL top jobs at once and asks it to
        produce a relative ranking with final calibrated scores.

        ``top_jobs`` is a list of dicts, each with keys:
        "job_index" (original 0-based index), "job_metadata" (full job dict),
        "current_score" (current affinity_score).

        Returns a list of dicts {job_index, final_score, rank_notes} in the
        same order as ``top_jobs``.
        """
        if not top_jobs:
            return []

        provider = self._get_provider("rerank")
        profile_norm = profile.get("profile_normalization") or {}

        candidate_block = (
            f"Role: {profile.get('role_description')}\n"
            f"CV: {sanitize_prompt_text(profile.get('cv_summary') or '', max_chars=600)}\n"
            f"Intent domain: {profile_norm.get('intent_domain')} | Skills: {profile_norm.get('skills')}\n"
        )

        jobs_text = ""
        for i, entry in enumerate(top_jobs):
            job = entry.get("job_metadata") or {}
            jobs_text += f"\n--- JOB {i + 1} (current score: {entry.get('current_score')}) ---\n"
            jobs_text += f"Title: {job.get('title')} @ {job.get('company')}\n"
            jobs_text += f"Description: {sanitize_prompt_text(job.get('description') or '', max_chars=2000)}\n"
            job_norm = job.get("normalized_data") or {}
            if job_norm:
                jobs_text += (
                    f"[Normalized] Domain: {job_norm.get('domain')} | Seniority: {job_norm.get('seniority')}"
                    f" | Required skills: {job_norm.get('required_skills')}\n"
                )

        system_prompt = (
            "You are a calibrated career advisor. You have already scored each job individually. "
            "Now compare them ALL together and produce final calibrated scores. "
            "Eliminate score compression: the best job should actually score highest, worst should score lowest. "
            "Maintain relative ordering unless you find a strong reason to swap. "
            "Small adjustments (±5) are fine for calibration. Large changes require specific justification."
        )
        user_prompt = f"""Calibrate final scores for these pre-scored jobs by comparing them against each other.

CANDIDATE:
{candidate_block}

JOBS TO COMPARE (already individually scored):
{jobs_text}

RERANKING RULES:
1. Compare jobs HEAD-TO-HEAD to find which is genuinely a better fit.
2. Spread scores: if jobs scored 82, 83, 84, they should not all be 83 — differentiate them.
3. The best job overall gets the highest score (but still ≤ the original ± 10).
4. If a job was over-scored relative to others, down-adjust with justification.
5. Keep original_score as reference; only adjust when comparative evidence supports it.

Return ONLY JSON with a "results" array, one entry per job, IN ORDER:
{{
    "results": [
        {{
            "final_score": 85,
            "rank": 1,
            "rank_notes": "Best domain fit; outperforms other jobs on skill match."
        }}
    ]
}}"""

        try:
            result = await self._call_provider_json(
                provider,
                "rerank",
                system_prompt,
                user_prompt,
                expected_rows=len(top_jobs),
            )
        except Exception as exc:
            logger.warning("[RERANK] LLM rerank call failed: %s. Returning original scores.", exc)
            return [
                {"job_index": e.get("job_index", i), "final_score": e.get("current_score", 0)}
                for i, e in enumerate(top_jobs)
            ]

        rerank_rows = result.get("results", []) if isinstance(result, dict) else []
        output: List[Dict[str, Any]] = []

        for i, entry in enumerate(top_jobs):
            row = (
                rerank_rows[i] if i < len(rerank_rows) and isinstance(rerank_rows[i], dict) else {}
            )
            orig_score = entry.get("current_score", 0)
            try:
                final_score = max(0, min(100, int(row.get("final_score", orig_score))))
            except Exception:
                final_score = orig_score

            # Cap adjustment at ±15 to prevent drastic changes
            adjustment = final_score - orig_score
            if abs(adjustment) > 15:
                final_score = orig_score + (15 if adjustment > 0 else -15)
                final_score = max(0, min(100, final_score))

            output.append(
                {
                    "job_index": entry.get("job_index", i),
                    "final_score": final_score,
                    "rank_notes": sanitize_prompt_text(
                        str(row.get("rank_notes") or ""), max_chars=300
                    ),
                }
            )

        # Pad missing entries
        while len(output) < len(top_jobs):
            entry = top_jobs[len(output)]
            output.append(
                {
                    "job_index": entry.get("job_index", len(output)),
                    "final_score": entry.get("current_score", 0),
                }
            )

        return output
