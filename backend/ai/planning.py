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


class PlanningMixin:
    def _extract_searches_payload(self, result: Any) -> tuple[List[Dict[str, Any]], str, bool]:
        """Extract search list using strict-first parsing with legacy fallback.

        Strict path expects canonical payload ``{"searches": [...]}``.
        Legacy fallback accepts ``queries`` / ``results`` or a root list.
        """
        if isinstance(result, dict):
            if "searches" in result:
                value = result.get("searches")
                if isinstance(value, list):
                    return value, "searches", True
                if isinstance(value, dict):
                    return [value], "searches", True
                logger.warning(
                    "[PLAN] Canonical 'searches' key had invalid type: %s", type(value).__name__
                )

            for key in ("queries", "results"):
                if key not in result:
                    continue
                value = result.get(key)
                if isinstance(value, list):
                    return value, key, False
                if isinstance(value, dict):
                    return [value], key, False
                return [], f"invalid_{key}", False
            return [], "missing_keys", False

        if isinstance(result, list):
            return result, "root_list", False

        return [], "invalid_root", False

    async def generate_search_plan(
        self,
        profile: Dict[str, Any],
        providers_info: List[Any],
        max_queries: Optional[int] = None,
        max_occupation_queries: Optional[int] = None,
        max_keyword_queries: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Generate the search plan with exact-count enforcement and batched retries."""
        if max_queries is not None and max_queries <= 0:
            max_queries = None
        if max_occupation_queries is not None and max_occupation_queries < 0:
            max_occupation_queries = None
        if max_keyword_queries is not None and max_keyword_queries < 0:
            max_keyword_queries = None

        if max_queries is not None:
            if max_occupation_queries is not None and max_occupation_queries > max_queries:
                raise ValueError("max_occupation_queries cannot exceed max_queries")
            if max_keyword_queries is not None and max_keyword_queries > max_queries:
                raise ValueError("max_keyword_queries cannot exceed max_queries")
            if (
                max_occupation_queries is not None
                and max_keyword_queries is not None
                and (max_occupation_queries + max_keyword_queries) > max_queries
            ):
                raise ValueError(
                    "The sum of occupation and keyword query limits cannot exceed max_queries"
                )

        searches = await self._call_generate_search_plan(
            profile,
            providers_info,
            max_queries=max_queries,
            max_occupation_queries=max_occupation_queries,
            max_keyword_queries=max_keyword_queries,
        )
        return searches

    def _normalize_searches(
        self,
        searches: List[Dict[str, Any]],
        seen_fingerprints: Optional[set] = None,
        seen_loose_fingerprints: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        local_seen = set(seen_fingerprints or set())
        local_seen_loose = set(seen_loose_fingerprints or set())
        enable_loose_dedup = bool(getattr(settings, "SEARCH_PLAN_ENABLE_LOOSE_DEDUP", True))
        dropped_non_dict = 0
        dropped_empty_query = 0
        dropped_duplicates = 0
        dropped_soft_duplicates = 0
        normalized_type_count = 0

        for search in searches:
            candidate, reason = normalize_search_item(search)
            if not candidate:
                if reason == "non_dict":
                    dropped_non_dict += 1
                elif reason == "empty_query":
                    dropped_empty_query += 1
                continue
            original_type = (
                str(search.get("type", "")).strip().lower() if isinstance(search, dict) else ""
            )
            if original_type not in {"occupation", "keyword"}:
                normalized_type_count += 1
            fingerprint = _query_fingerprint(candidate)
            if fingerprint in local_seen:
                dropped_duplicates += 1
                continue

            if enable_loose_dedup:
                loose_fingerprint = loose_query_fingerprint(candidate)
                if loose_fingerprint in local_seen_loose:
                    dropped_soft_duplicates += 1
                    continue
                if loose_fingerprint:
                    local_seen_loose.add(loose_fingerprint)

            local_seen.add(fingerprint)
            normalized.append(candidate)

        if searches and not normalized:
            logger.warning(
                "[PLAN] All candidate queries were filtered out (non_dict=%s empty_query=%s duplicates=%s soft_duplicates=%s)",
                dropped_non_dict,
                dropped_empty_query,
                dropped_duplicates,
                dropped_soft_duplicates,
            )
        elif (
            dropped_non_dict or dropped_empty_query or dropped_duplicates or dropped_soft_duplicates
        ):
            logger.info(
                "[PLAN] Query normalization dropped entries (non_dict=%s empty_query=%s duplicates=%s soft_duplicates=%s type_inferred=%s kept=%s)",
                dropped_non_dict,
                dropped_empty_query,
                dropped_duplicates,
                dropped_soft_duplicates,
                normalized_type_count,
                len(normalized),
            )

        return normalized

    @retry(
        retry=retry_if_exception(_is_retryable_plan_error),
        stop=stop_after_attempt(max(1, int(getattr(settings, "LLM_PLAN_RETRY_ATTEMPTS", 2)))),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    async def _call_generate_search_plan(
        self,
        profile: Dict[str, Any],
        providers_info: List[Any],
        max_queries: Optional[int] = None,
        max_occupation_queries: Optional[int] = None,
        max_keyword_queries: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Internal method: single LLM call to generate the search plan."""
        provider = self._get_provider("plan")
        logger.info("[PLAN] Using %s", provider.model_id)

        role_description = sanitize_prompt_text(profile.get("role_description"), max_chars=3000)
        search_strategy = sanitize_prompt_text(profile.get("search_strategy"), max_chars=3000)
        cv_content = sanitize_prompt_text(profile.get("cv_content"), max_chars=20000)
        input_fingerprint = compute_plan_input_fingerprint(
            {
                "role_description": role_description,
                "search_strategy": search_strategy,
                "cv_content": cv_content,
            },
            max_queries=max_queries,
            max_occupation_queries=max_occupation_queries,
            max_keyword_queries=max_keyword_queries,
        )

        system_prompt = (
            "You are CareerOS Local's career-search assistant specialized in the Swiss job market. "
            "You are fluent in English, German, French, and Italian. "
            "Your task is to generate HIGH-QUALITY, DIVERSE, and EXECUTABLE search queries "
            "that maximize precision first, then coverage, without wasting slots on duplicates or vague terms. "
            "Return only concrete queries that a Swiss job board can execute directly."
        )

        provider_lines = []
        for info in providers_info:
            name = getattr(info, "name", None) if not isinstance(info, dict) else info.get("name")
            description = (
                getattr(info, "description", None)
                if not isinstance(info, dict)
                else info.get("description")
            )
            accepted_domains = (
                getattr(info, "accepted_domains", None)
                if not isinstance(info, dict)
                else info.get("accepted_domains")
            )
            if name:
                domains = ", ".join(accepted_domains or ["*"])
                provider_lines.append(
                    f"- {name}: domains [{domains}] | {description or 'No description'}"
                )

        providers_block = (
            "\n".join(provider_lines)
            if provider_lines
            else "- General routing handles provider selection automatically."
        )

        # Build count instructions
        if max_occupation_queries is not None and max_keyword_queries is not None:
            limit_instruction = (
                f'You MUST generate EXACTLY {max_occupation_queries} queries of type "occupation" '
                f'and EXACTLY {max_keyword_queries} queries of type "keyword". '
                f"Total: {max_occupation_queries + max_keyword_queries} queries. "
                "Each query MUST be unique. Do NOT generate more or fewer of either type. "
                "This requirement is MANDATORY and non-negotiable."
            )
        elif max_occupation_queries is not None:
            total_info = f" (total: at most {max_queries})" if max_queries else ""
            limit_instruction = (
                f'You MUST generate EXACTLY {max_occupation_queries} queries of type "occupation"{total_info}. '
                "Keywords can be generated freely. Each query MUST be unique."
            )
        elif max_keyword_queries is not None:
            total_info = f" (total: at most {max_queries})" if max_queries else ""
            limit_instruction = (
                f'You MUST generate EXACTLY {max_keyword_queries} queries of type "keyword"{total_info}. '
                "Occupations can be generated freely. Each query MUST be unique."
            )
        elif max_queries is None:
            limit_instruction = (
                "Generate as MANY queries as needed to ensure comprehensive coverage. "
                "There is NO limit on the total number of queries."
            )
        else:
            limit_instruction = (
                f"You MUST generate EXACTLY {max_queries} queries total. "
                "Use a strong mix of occupation and keyword queries. "
                "Every query must be materially different from the others."
            )

        user_prompt = f"""Analyze the user's profile and generate an optimal search plan.
You do NOT need to assign queries to specific job boards — the system routes them automatically.

PROFILE:
- Role / What they are looking for: {role_description or "Unknown"}
- Strategy / AI Instructions: {search_strategy or "None"}
- CV Evidence Extract: {cv_content or "Unavailable"}

AVAILABLE PROVIDERS:
{providers_block}

QUERY GENERATION RULES:
1. DOMAIN TAGGING: For each query, specify its professional domain (e.g. "it", "finance", "medical", "engineering", "hospitality", "general"). The system uses this to route queries to the right job boards.
2. NO "OR" OPERATORS: Never use "OR" or any other boolean operator in the query field.
3. ONE OCCUPATION PER QUERY: Each query must contain ONLY ONE specific job title/occupation.
4. QUERY TYPES:
   - "occupation": Exactly ONE occupation title, translated. No keywords in this type.
   - "keyword": A single specific skill, tool, action verb, or core competency (e.g. for IT: "React", for non-IT/general: "pulire", "trasportare", "customer service").
5. DIVERSITY & ACCURACY:
   - Use synonyms and different languages (DE, FR, EN, IT) to maximize coverage.
    - Ensure queries are distinct, high-quality, and not cosmetic variants of each other.
    - Prefer concrete, searchable terms actually used in job titles and skill filters.
    - Cover nearby seniority labels, role variants, and stack-specific wording when relevant.
6. DETERMINISM:
    - Avoid commentary, uncertainty markers, or meta text.
    - Prefer canonical Swiss/European job title wording over creative paraphrases.
    - If type is unclear, choose the most executable form.

{limit_instruction}

INTERNAL PLAN FINGERPRINT: {input_fingerprint}

Return ONLY pure JSON with a 'searches' list. Example:
{{
    "searches": [
        {{"domain": "it", "language": "en", "type": "occupation", "query": "Software Engineer"}},
        {{"domain": "it", "language": "de", "type": "keyword", "query": "React"}},
        {{"domain": "finance", "language": "en", "type": "occupation", "query": "Financial Analyst"}},
        {{"domain": "general", "language": "it", "type": "keyword", "query": "pulire"}}
    ]
}}"""

        result = await self._call_provider_json(provider, "plan", system_prompt, user_prompt)
        searches, payload_source, used_strict_payload = self._extract_searches_payload(result)
        if payload_source.startswith("invalid") or payload_source == "missing_keys":
            if isinstance(result, dict):
                result_keys = list(result.keys())
            else:
                result_keys = [type(result).__name__]
            raise ValueError(
                f"LLM plan payload missing valid query list (source={payload_source}, keys={result_keys})"
            )

        if not used_strict_payload:
            logger.warning("[PLAN] Legacy payload fallback engaged: %s", payload_source)

        normalized_searches = self._normalize_searches(searches)
        if searches and not normalized_searches:
            raise ValueError(
                "LLM plan payload had candidates but all were invalid after normalization"
            )

        if searches:
            logger.info(
                "[PLAN] Payload parse summary: source=%s strict=%s raw=%s normalized=%s",
                payload_source,
                used_strict_payload,
                len(searches),
                len(normalized_searches),
            )

        searches = normalized_searches

        # Application-side cap just in case the LLM produces too many total queries
        if max_queries is not None:
            searches = searches[:max_queries]

        return searches
