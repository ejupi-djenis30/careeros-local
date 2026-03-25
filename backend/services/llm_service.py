import logging
import threading
from typing import Dict, Any, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from backend.providers.llm.factory import get_provider_for_step
from backend.core.config import settings
from backend.services.search.query_contracts import (
    canonicalize_query_text,
    compute_plan_input_fingerprint,
    exact_query_fingerprint,
    loose_query_fingerprint,
    normalize_domain,
    normalize_search_item,
    sanitize_prompt_text,
)

logger = logging.getLogger(__name__)


def _query_fingerprint(search: Dict[str, Any]) -> str:
    return exact_query_fingerprint(search)


class LLMService:
    """Orchestrates all LLM calls for the job-hunting pipeline.

    Each method resolves its own provider via ``get_provider_for_step``
    so that different steps can transparently use different models/providers.
    """

    def __init__(self):
        self._provider_cache: Dict[str, Any] = {}
        self._provider_cache_lock = threading.RLock()

    def _get_provider(self, step: str):
        with self._provider_cache_lock:
            if step not in self._provider_cache:
                self._provider_cache[step] = get_provider_for_step(step)
            return self._provider_cache[step]

    def clear_provider_cache(self):
        """Force reload of all LLM providers (e.g. if config changes)."""
        with self._provider_cache_lock:
            self._provider_cache.clear()

    @staticmethod
    def _build_retry_feedback(attempt: int) -> str:
        if attempt <= 0:
            return ""

        hints = {
            1: "Retry policy: prioritize domain-faithful, concrete Swiss job-title wording. Avoid cosmetic variants.",
            2: "Retry policy: increase language diversity (EN/DE/FR/IT) and vary role-family synonyms materially.",
            3: "Retry policy: maximize uniqueness and executability. Avoid reordered-token duplicates and broad generic terms.",
        }
        return hints.get(
            attempt,
            "Retry policy: maintain strict count compliance while maximizing unique, executable query intent.",
        )

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
                logger.warning("[PLAN] Canonical 'searches' key had invalid type: %s", type(value).__name__)

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

    def is_summary_step_configured(self) -> bool:
        """Return True only if LLM_SUMMARY_* env vars are explicitly configured.
        
        If not configured the job-summary step is skipped entirely (opt-in behavior).
        The step is considered configured when either a dedicated provider OR a
        dedicated API key is set for the 'summary' step.
        """
        return bool(
            settings.LLM_SUMMARY_PROVIDER
            or settings.LLM_SUMMARY_API_KEY
            or settings.LLM_SUMMARY_MODEL
        )

    # ─── New Phase 2 Helpers: CV Summary & Relevance Pre-filter ────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def summarize_cv(self, cv_content: str) -> str:
        """Produce a compact CV summary for downstream MATCH calls."""
        provider = self._get_provider("plan")
        
        system_prompt = (
            "You are an expert HR analyst producing factual candidate summaries for job matching. "
            "Extract only information supported by the CV. Never invent skills, degrees, or languages."
        )
        user_prompt = f"""Summarize this CV into a compact, clearly structured profile for downstream job matching.

Output requirements:
- Maximum 220 words.
- Use short bullet points.
- If a detail is missing, write "Unknown" instead of guessing.
- Focus on facts that help match jobs accurately.

You MUST include these sections in this order:
1. Education
2. Languages
3. Experience & Seniority
4. Core Skills & Tools
5. Roles Held
6. Industries / Domains

CV:
{cv_content}

Return plain text, NOT JSON."""
        
        return await provider.generate_text_async(system_prompt, user_prompt)

    # ─── Step 1.5: User / Candidate Profile Normalization ─────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def normalize_user_profile(
        self,
        cv_content: str,
        role_description: str,
        search_strategy: str = "",
    ) -> Dict[str, Any]:
        """Extract structured candidate facts from the CV cross-referenced with the role intent.

        This is the user-side mirror of ``normalize_job_batch``: it produces a minimal
        deterministic profile that can be compared field-for-field against normalized
        ``ScrapedJob`` columns during structured filtering.

        The extraction is *intent-aware* — it combines what the CV says the candidate IS
        with what the ``role_description`` says the candidate WANTS.  For example, a senior
        engineer explicitly targeting junior roles will get ``seniority="junior"`` so that
        junior job listings are not filtered out.

        Returns a dict with keys matching ``SearchProfile.profile_normalized_*`` columns.
        """
        provider = self._get_provider("normalize_profile")

        strategy_block = (
            f"\n\nSEARCH STRATEGY / EXTRA INSTRUCTIONS:\n{sanitize_prompt_text(search_strategy, max_chars=800)}"
            if search_strategy.strip()
            else ""
        )

        system_prompt = (
            "You are a strict candidate-profile normalizer for job-matching. "
            "Cross-reference the CV facts with the user's role-description intent to extract a "
            "compact deterministic profile. "
            "Use only information explicitly present in the inputs — do NOT invent. "
            "The 'seniority', 'domain', and 'qualification_level' values MUST come from the "
            "allowlists below. Return compact structured JSON."
        )
        user_prompt = f"""Extract the candidate's normalized profile from the CV and role intent below.

OUTPUT — one JSON object with ALL keys:
- seniority         : "junior" | "mid" | "senior"  (infer from CV experience + role intent)
- domain            : one of EXACTLY: general, it, finance, medical, engineering, hospitality, sales, logistics, administration
- role_family       : normalised job-title family (e.g. "Software Engineer", "Financial Analyst")
- qualification_level: "none" | "vocational" | "bachelor" | "master" | "phd"
- experience_years  : integer (total years of relevant professional experience; 0 if unknown/none)
- languages         : list of {{code (ISO 639-1 2-letter), level (CEFR A1-C2 or "native")}}
- skills            : list of concrete technical/domain skills (max 20 strings); exclude generic soft-skills
- confidence        : 0.0–1.0

SENIORITY RULE: if the role_description explicitly targets a seniority DIFFERENT from the CV,
use the TARGETED seniority (the user knows what they want to apply for).

DOMAIN RULE: pick the single best-fit domain from the allowlist.
Use "general" only if the domain is genuinely unclear.

CV (truncated to 5000 chars):
{sanitize_prompt_text(cv_content, max_chars=5000)}

ROLE DESCRIPTION (what the user is looking for):
{sanitize_prompt_text(role_description, max_chars=800)}{strategy_block}

Return ONLY JSON — no markdown, no explanations:
{{
  "seniority": "mid",
  "domain": "it",
  "role_family": "Software Engineer",
  "qualification_level": "bachelor",
  "experience_years": 4,
  "languages": [{{"code": "en", "level": "C2"}}, {{"code": "de", "level": "B2"}}],
  "skills": ["Python", "FastAPI", "React", "PostgreSQL"],
  "confidence": 0.85
}}"""

        result = await provider.generate_json_async(system_prompt, user_prompt)

        if not isinstance(result, dict):
            return {}

        # ── normalise / validate each field ──────────────────────────────
        seniority_raw = str(result.get("seniority") or "").strip().lower()
        seniority = seniority_raw if seniority_raw in {"junior", "mid", "senior"} else None

        domain_raw = self._normalize_job_domain_token(result.get("domain") or "general")
        domain = domain_raw or "general"

        role_family = str(result.get("role_family") or "").strip() or None

        ql_raw = str(result.get("qualification_level") or "").strip().lower()
        ql_valid = {"none", "vocational", "bachelor", "master", "phd"}
        qualification_level = ql_raw if ql_raw in ql_valid else None

        experience_years = self._coerce_nullable_int(result.get("experience_years"))
        if experience_years is not None:
            experience_years = max(0, experience_years)

        languages = self._normalize_required_languages(result.get("languages"))
        skills = self._dedupe_string_list(result.get("skills"))

        confidence = 0.0
        try:
            confidence = float(result.get("confidence", 0.0))
        except (TypeError, ValueError):
            pass
        confidence = max(0.0, min(1.0, confidence))

        return {
            "seniority": seniority,
            "domain": domain,
            "role_family": role_family,
            "qualification_level": qualification_level,
            "experience_years": experience_years,
            "languages": languages,
            "skills": skills,
        }

    # ─── Feature 1: Job Summary Step ──────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def summarize_job_batch(
        self,
        jobs: List[Dict[str, str]],
    ) -> List[str]:
        """Generate concise summaries for a batch of jobs.
        
        Each summary (~80 words) captures: required skills, responsibilities,
        seniority, and language requirements. Used by the relevance filter step.
        
        Args:
            jobs: List of {title, company, description} dicts.
            
        Returns:
            List of summary strings, one per job, in the same order.
        """
        provider = self._get_provider("summary")
        
        jobs_text = ""
        for i, job in enumerate(jobs):
            desc = (job.get("description") or "")[:800]  # limit per-job input
            jobs_text += f"\n--- JOB {i+1} ---\n"
            jobs_text += f"Title: {job.get('title', 'Unknown')}\n"
            jobs_text += f"Company: {job.get('company', 'Unknown')}\n"
            jobs_text += f"Description: {desc}\n"

        system_prompt = (
            "You are a job description analyst. For each job, extract a compact factual summary "
            "that highlights: required skills, main responsibilities, seniority level, and any "
            "explicit language requirements. Be objective. Do NOT invent information."
        )
        user_prompt = f"""Summarize each job below in ~80 words each. Focus on: required skills, main tasks, seniority, and language requirements.

{jobs_text}

Return ONLY JSON with a "summaries" array, one string per job, in the same order as the input:
{{
    "summaries": [
        "Summary for job 1...",
        "Summary for job 2..."
    ]
}}"""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        summaries = result.get("summaries", [])
        
        # Safety: if LLM returns wrong count, pad with empty strings
        while len(summaries) < len(jobs):
            summaries.append("")
            
        return summaries[:len(jobs)]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def check_relevance_batch(
        self,
        jobs: List[Dict[str, str]],
        role_description: str,
        search_strategy: str = "",
    ) -> List[bool]:
        """Quick binary relevance check for a batch of jobs."""
        provider = self._get_provider("relevance")
        
        system_prompt = (
            "You are a permissive relevance gate for job discovery. "
            "Keep borderline matches, translations, adjacent roles, and likely career moves. "
            "Reject only roles that are clearly in a different profession."
        )
        
        jobs_text = "\n".join(
            f'{i+1}. "{j["title"]}" at {j.get("company", "Unknown")}'
            + (f' — {j["description_snippet"]}' if j.get("description_snippet") else '')
            for i, j in enumerate(jobs)
        )
        
        strategy_block = f"\nEXTRA INSTRUCTIONS/PREFERENCES: {search_strategy}" if search_strategy else ""
        
        user_prompt = f"""TARGET ROLE: {role_description}{strategy_block}

JOB TITLES:
{jobs_text}

FILTERING RULES:
- Mark as TRUE (relevant) if the job title is the same role, a synonym, a translation (DE/FR/IT/EN), or a closely related role.
- Mark as TRUE if the job is in a related field, specialization, or seniority band that could still fit the candidate.
- Mark as FALSE ONLY if the job is clearly in a completely different field (e.g., "Nurse" for a "Software Developer").
- When in doubt, ALWAYS mark as TRUE — the next analysis step will do a deeper evaluation with the full description.

Return ONLY JSON: {{"results": [true, false, true]}}
One boolean per job, in order. true = relevant, false = irrelevant."""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        results = result.get("results", []) if isinstance(result, dict) else []
        fallback_keep = (settings.SEARCH_RELEVANCE_FALLBACK_MODE or "conservative").strip().lower() == "keep"
        normalized_results: List[bool] = []

        for item in results[:len(jobs)]:
            if isinstance(item, bool):
                normalized_results.append(item)
            elif isinstance(item, dict):
                normalized_results.append(bool(item.get("relevant", fallback_keep)))
            else:
                normalized_results.append(fallback_keep)

        while len(normalized_results) < len(jobs):
            normalized_results.append(fallback_keep)

        return normalized_results

    # ─── Step 1: Search Plan Generation ───────────────────────────────────

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
                raise ValueError("The sum of occupation and keyword query limits cannot exceed max_queries")

        total_target = max_queries
        if total_target is None and max_occupation_queries is not None and max_keyword_queries is not None:
            total_target = max_occupation_queries + max_keyword_queries

        if total_target is not None:
            return await self._generate_search_plan_in_batches(
                profile,
                providers_info,
                total_target=total_target,
                max_occupation_queries=max_occupation_queries,
                max_keyword_queries=max_keyword_queries,
            )

        strict_types = (max_occupation_queries is not None) or (max_keyword_queries is not None)
        searches: List[Dict[str, Any]] = []

        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES + 1):
            searches = await self._call_generate_search_plan(
                profile,
                providers_info,
                max_queries=max_queries,
                max_occupation_queries=max_occupation_queries,
                max_keyword_queries=max_keyword_queries,
                attempt=attempt,
            )
            
            if not strict_types:
                break  # No enforcement needed
            
            # Validate counts
            occupation_count = sum(1 for s in searches if s.get("type") == "occupation")
            keyword_count = sum(1 for s in searches if s.get("type") == "keyword")
            
            occ_ok = (max_occupation_queries is None) or (occupation_count == max_occupation_queries)
            kw_ok = (max_keyword_queries is None) or (keyword_count == max_keyword_queries)
            
            if occ_ok and kw_ok:
                logger.info(f"[PLAN] Query counts validated on attempt {attempt + 1}: {occupation_count} occupations, {keyword_count} keywords")
                break
            
            if attempt < MAX_RETRIES:
                logger.warning(
                    f"[PLAN] Attempt {attempt + 1}/{MAX_RETRIES}: "
                    f"got {occupation_count} occupations (wanted {max_occupation_queries}), "
                    f"{keyword_count} keywords (wanted {max_keyword_queries}). Retrying..."
                )
            else:
                logger.warning(
                    f"[PLAN] Max retries ({MAX_RETRIES}) reached. "
                    f"Accepting {occupation_count} occupations, {keyword_count} keywords as-is."
                )
        
        return searches

    async def _generate_search_plan_in_batches(
        self,
        profile: Dict[str, Any],
        providers_info: List[Any],
        total_target: int,
        max_occupation_queries: Optional[int] = None,
        max_keyword_queries: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        seen_fingerprints = set()
        seen_loose_fingerprints = set()
        remaining_occupations = max_occupation_queries
        remaining_keywords = max_keyword_queries
        batch_size_limit = max(1, settings.SEARCH_PLAN_BATCH_SIZE)
        max_stall_batches = max(1, int(getattr(settings, "SEARCH_PLAN_STALL_MAX_BATCHES", 2)))
        stall_count = 0

        while len(collected) < total_target:
            remaining_total = total_target - len(collected)
            batch_size = min(batch_size_limit, remaining_total)
            batch_occ, batch_kw = self._plan_batch_targets(
                batch_size,
                remaining_total,
                remaining_occupations,
                remaining_keywords,
            )

            best_batch: List[Dict[str, Any]] = []
            MAX_RETRIES = 3
            for attempt in range(MAX_RETRIES + 1):
                retry_feedback = self._build_retry_feedback(attempt)
                feedback = (
                    f"This batch must contribute EXACTLY {batch_size} NEW UNIQUE queries. "
                    f"Remaining total target after this batch: {remaining_total - batch_size}."
                )
                if retry_feedback:
                    feedback = f"{feedback}\n{retry_feedback}"
                try:
                    batch_searches = await self._call_generate_search_plan(
                        profile,
                        providers_info,
                        max_queries=batch_size,
                        max_occupation_queries=batch_occ,
                        max_keyword_queries=batch_kw,
                        attempt=attempt,
                        existing_queries=[item.get("query", "") for item in collected[-120:]],
                        feedback=feedback,
                    )
                except Exception as batch_error:
                    logger.warning(
                        "[PLAN] Batch call failed on attempt %s/%s: %s",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        batch_error,
                    )
                    if best_batch:
                        logger.warning(
                            "[PLAN] Using best partial batch (%s queries) after LLM failure",
                            len(best_batch),
                        )
                        break

                    if collected:
                        logger.warning(
                            "[PLAN] Returning partial collected plan %s/%s due to LLM failure",
                            len(collected),
                            total_target,
                        )
                        return collected[:total_target]

                    raise

                unique_batch = self._normalize_searches(
                    batch_searches,
                    seen_fingerprints,
                    seen_loose_fingerprints,
                )
                if len(unique_batch) > len(best_batch):
                    best_batch = unique_batch

                occupation_count = sum(1 for item in unique_batch if item.get("type") == "occupation")
                keyword_count = sum(1 for item in unique_batch if item.get("type") == "keyword")
                counts_ok = (
                    len(unique_batch) == batch_size
                    and (batch_occ is None or occupation_count == batch_occ)
                    and (batch_kw is None or keyword_count == batch_kw)
                )

                if counts_ok:
                    best_batch = unique_batch
                    break

                logger.warning(
                    "[PLAN] Batch retry %s/%s returned %s unique queries (%s occupations, %s keywords) for target %s",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    len(unique_batch),
                    occupation_count,
                    keyword_count,
                    batch_size,
                )

            if not best_batch:
                stall_count += 1
                logger.warning("[PLAN] Batch generation stalled with no new unique queries")
                should_continue = True
                if stall_count >= max_stall_batches:
                    logger.warning(
                        "[PLAN] Repeated stalls reached threshold; attempting rescue batch without strict type split"
                    )
                    rescue_searches = await self._call_generate_search_plan(
                        profile,
                        providers_info,
                        max_queries=min(batch_size_limit, total_target),
                        max_occupation_queries=None,
                        max_keyword_queries=None,
                        existing_queries=[item.get("query", "") for item in collected[-120:]],
                        feedback="Recovery mode: produce any high-quality, unique executable queries.",
                    )
                    best_batch = self._normalize_searches(
                        rescue_searches,
                        seen_fingerprints,
                        seen_loose_fingerprints,
                    )
                    if not best_batch:
                        if collected:
                            logger.warning(
                                "[PLAN] Rescue batch produced no unique queries; returning partial plan %s/%s",
                                len(collected),
                                total_target,
                            )
                            break
                        break
                    stall_count = 0
                    should_continue = False
                if should_continue:
                    continue

            stall_count = 0
            batch_to_add = best_batch[:batch_size]
            for item in batch_to_add:
                fingerprint = _query_fingerprint(item)
                if fingerprint in seen_fingerprints:
                    continue
                seen_fingerprints.add(fingerprint)
                loose_fingerprint = loose_query_fingerprint(item)
                if loose_fingerprint:
                    seen_loose_fingerprints.add(loose_fingerprint)
                collected.append(item)

            if remaining_occupations is not None:
                remaining_occupations = max(0, remaining_occupations - sum(1 for item in batch_to_add if item.get("type") == "occupation"))
            if remaining_keywords is not None:
                remaining_keywords = max(0, remaining_keywords - sum(1 for item in batch_to_add if item.get("type") == "keyword"))

            logger.info("[PLAN] Collected %s/%s search queries", len(collected), total_target)

            if len(batch_to_add) < batch_size and len(collected) < total_target:
                logger.warning(
                    "[PLAN] Batch under-filled after retries (%s/%s unique queries); continuing with another batch",
                    len(batch_to_add),
                    batch_size,
                )

        return collected[:total_target]

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
            original_type = str(search.get("type", "")).strip().lower() if isinstance(search, dict) else ""
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
        elif dropped_non_dict or dropped_empty_query or dropped_duplicates or dropped_soft_duplicates:
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

    def _plan_batch_targets(
        self,
        batch_size: int,
        remaining_total: int,
        remaining_occupations: Optional[int],
        remaining_keywords: Optional[int],
    ) -> tuple[int, int]:
        if remaining_occupations is not None and remaining_keywords is not None:
            strict_total = remaining_occupations + remaining_keywords
            if strict_total <= 0:
                return batch_size, 0
            occupation_target = round(batch_size * (remaining_occupations / strict_total))
            occupation_target = min(remaining_occupations, max(0, occupation_target))
            keyword_target = batch_size - occupation_target
            if keyword_target > remaining_keywords:
                keyword_target = remaining_keywords
                occupation_target = batch_size - keyword_target
            if occupation_target > remaining_occupations:
                occupation_target = remaining_occupations
                keyword_target = batch_size - occupation_target
            return occupation_target, keyword_target

        if remaining_occupations is not None:
            occupation_target = min(batch_size, remaining_occupations)
            keyword_target = batch_size - occupation_target
            return occupation_target, keyword_target

        if remaining_keywords is not None:
            keyword_target = min(batch_size, remaining_keywords)
            occupation_target = batch_size - keyword_target
            return occupation_target, keyword_target

        if batch_size == 1:
            return 1, 0

        occupation_target = max(1, int(round(batch_size * 0.6)))
        keyword_target = batch_size - occupation_target
        if keyword_target == 0:
            keyword_target = 1
            occupation_target = batch_size - 1
        return occupation_target, keyword_target

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_generate_search_plan(
        self,
        profile: Dict[str, Any],
        providers_info: List[Any],
        max_queries: Optional[int] = None,
        max_occupation_queries: Optional[int] = None,
        max_keyword_queries: Optional[int] = None,
        attempt: int = 0,
        existing_queries: Optional[List[str]] = None,
        feedback: str = "",
    ) -> List[Dict[str, Any]]:
        """Internal method: single LLM call to generate the search plan."""
        provider = self._get_provider("plan")
        logger.info(f"[PLAN] Using {provider.model_id} (attempt {attempt + 1})")

        role_description = sanitize_prompt_text(profile.get("role_description"), max_chars=1200)
        search_strategy = sanitize_prompt_text(profile.get("search_strategy"), max_chars=1200)
        cv_content = sanitize_prompt_text(profile.get("cv_content"), max_chars=6000)
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
            "You are an expert Job Hunter AI specialized in the Swiss job market. "
            "You are fluent in English, German, French, and Italian. "
            "Your task is to generate HIGH-QUALITY, DIVERSE, and EXECUTABLE search queries "
            "that maximize precision first, then coverage, without wasting slots on duplicates or vague terms. "
            "Return only concrete queries that a Swiss job board can execute directly."
        )

        provider_lines = []
        for info in providers_info:
            name = getattr(info, "name", None) if not isinstance(info, dict) else info.get("name")
            description = getattr(info, "description", None) if not isinstance(info, dict) else info.get("description")
            accepted_domains = getattr(info, "accepted_domains", None) if not isinstance(info, dict) else info.get("accepted_domains")
            if name:
                domains = ", ".join(accepted_domains or ["*"])
                provider_lines.append(f"- {name}: domains [{domains}] | {description or 'No description'}")

        providers_block = "\n".join(provider_lines) if provider_lines else "- General routing handles provider selection automatically."

        # Build count instructions
        if max_occupation_queries is not None and max_keyword_queries is not None:
            limit_instruction = (
                f"You MUST generate EXACTLY {max_occupation_queries} queries of type \"occupation\" "
                f"and EXACTLY {max_keyword_queries} queries of type \"keyword\". "
                f"Total: {max_occupation_queries + max_keyword_queries} queries. "
                "Each query MUST be unique. Do NOT generate more or fewer of either type. "
                "This requirement is MANDATORY and non-negotiable."
            )
        elif max_occupation_queries is not None:
            total_info = f" (total: at most {max_queries})" if max_queries else ""
            limit_instruction = (
                f"You MUST generate EXACTLY {max_occupation_queries} queries of type \"occupation\"{total_info}. "
                "Keywords can be generated freely. Each query MUST be unique."
            )
        elif max_keyword_queries is not None:
            total_info = f" (total: at most {max_queries})" if max_queries else ""
            limit_instruction = (
                f"You MUST generate EXACTLY {max_keyword_queries} queries of type \"keyword\"{total_info}. "
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

        retry_note = ""
        if attempt > 0:
            retry_note = (
                f"\n\nCRITICAL: This is retry attempt {attempt + 1}. "
                "Your previous response did NOT match the required query counts. "
                "You MUST strictly adhere to the count requirements this time."
            )

        exclusion_block = ""
        if existing_queries:
            formatted_queries = "\n".join(f"- {query}" for query in existing_queries if query)
            exclusion_block = (
                "\nEXISTING QUERIES TO AVOID REPEATING:\n"
                f"{formatted_queries}\n"
                "Do NOT repeat or trivially rephrase the existing queries above."
            )

        feedback_block = f"\nADDITIONAL BATCH FEEDBACK:\n{feedback}\n" if feedback else ""

        user_prompt = f"""Analyze the user's profile and generate an optimal search plan.
You do NOT need to assign queries to specific job boards — the system routes them automatically.

PROFILE:
- Role / What they are looking for: {role_description or 'Unknown'}
- Strategy / AI Instructions: {search_strategy or 'None'}
- CV Evidence Extract: {cv_content or 'Unavailable'}

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

{limit_instruction}{retry_note}{feedback_block}{exclusion_block}

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

        result = await provider.generate_json_async(system_prompt, user_prompt)
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
            raise ValueError("LLM plan payload had candidates but all were invalid after normalization")

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

    # ─── Step 3: Combined Title Relevance & Job Match Analysis ──────────────


    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def analyze_job_batch(
        self,
        jobs_metadata: List[Dict[str, Any]],
        profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        provider = self._get_provider("match")

        system_prompt = (
            "You are a strict, evidence-driven career coach AI. "
            "Evaluate candidate-job fit conservatively, cite the main reasons, and never invent qualifications. "
            "Return results in the EXACT SAME ORDER as the jobs were given."
        )

        jobs_text = ""
        for i, job in enumerate(jobs_metadata):
            jobs_text += f"\n--- JOB {i+1} ---\n"
            jobs_text += f"Title: {job.get('title')}\n"
            jobs_text += f"Company: {job.get('company')}\n"
            jobs_text += f"Location: {job.get('location')}\n"
            jobs_text += f"Workload: {job.get('workload')}\n"
            jobs_text += f"Languages Required: {job.get('languages')}\n"
            jobs_text += f"Education Required: {job.get('education')}\n"
            jobs_text += f"Description: {job.get('description')}\n"

        strategy = profile.get('search_strategy')
        strategy_block = f"\n- Extra AI Instructions / Preferences: {strategy}" if strategy else ""

        user_prompt = f"""Analyze the match between this profile and each job below.

PROFILE:
- Expected Role: {profile.get('role_description')}{strategy_block}
- Experience Context: {profile.get('cv_summary') or profile.get('cv_content')}

{jobs_text}

SCORING RULES (STRICT CONSTRAINTS):
1. RELEVANCE CHECK: Determine if the job title and description are relevant to the requested role. Check Extra AI Instructions. If completely irrelevant or violating strict user instructions, set "relevant" to false.
2. LANGUAGE MISMATCH PENALTY: If the job EXPLICITLY requires a language (e.g., German, French) that the candidate DOES NOT speak, cap `affinity_score` at 30 and set `worth_applying` to false.
3. EDUCATION MISMATCH PENALTY: If the job explicitly requires a University Degree (Bachelor/Master/PhD) and the candidate has no degree, cap `affinity_score` at 40 and set `worth_applying` to false. 
4. SENIORITY MISMATCH: If the candidate is Junior/Entry-level and the job requires Senior/Lead (5+ years), cap `affinity_score` at 35. (Senior applying to Junior cap at 70).
5. BASE SCORING: For remaining cases, score 0-100 realistically. Score 90-100 ONLY for a virtually perfect resume-to-job match.
6. "worth_applying" MUST ONLY be true if `affinity_score` >= 65 and `relevant` is true.
7. `affinity_analysis` must be concise and factual: mention the top fit factors, the top gaps, and any hard blockers.

Return ONLY JSON with a "results" array, one entry per job, IN ORDER:
{{
    "results": [
        {{"relevant": true, "affinity_score": 85, "affinity_analysis": "...", "worth_applying": true}},
        {{"relevant": false, "affinity_score": 10, "affinity_analysis": "...", "worth_applying": false}}
    ]
}}"""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        results = result.get("results", []) if isinstance(result, dict) else []
        normalized_results: List[Dict[str, Any]] = []

        for item in results[:len(jobs_metadata)]:
            if not isinstance(item, dict):
                normalized_results.append(
                    {
                        "relevant": False,
                        "affinity_score": 0,
                        "affinity_analysis": "Invalid analysis payload returned by model.",
                        "worth_applying": False,
                    }
                )
                continue

            score = item.get("affinity_score", 0)
            try:
                score = max(0, min(100, int(score)))
            except Exception:
                score = 0

            relevant = bool(item.get("relevant", False))
            worth_applying = bool(item.get("worth_applying", False)) and relevant and score >= 65
            normalized_results.append(
                {
                    "relevant": relevant,
                    "affinity_score": score,
                    "affinity_analysis": sanitize_prompt_text(item.get("affinity_analysis", ""), max_chars=600) or "No analysis returned.",
                    "worth_applying": worth_applying,
                }
            )

        while len(normalized_results) < len(jobs_metadata):
            normalized_results.append(
                {
                    "relevant": False,
                    "affinity_score": 0,
                    "affinity_analysis": "Model returned too few analysis rows.",
                    "worth_applying": False,
                }
            )

        return normalized_results

    # ─── Step 2.5: Shared Job Normalization ───────────────────────────────

    @staticmethod
    def _normalize_job_domain_token(value: Any) -> str:
        token = str(value or "").strip().lower()
        if token in {"tech", "software", "information technology", "it/tech"}:
            token = "it"
        return normalize_domain(token)

    @staticmethod
    def _coerce_nullable_int(value: Any) -> Optional[int]:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(float(text))
            except ValueError:
                return None
        return None

    @staticmethod
    def _dedupe_string_list(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        out: List[str] = []
        seen = set()
        for item in values:
            token = str(item or "").strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
        return out

    @staticmethod
    def _normalize_required_languages(values: Any) -> List[Dict[str, Optional[str]]]:
        if not isinstance(values, list):
            return []
        out: List[Dict[str, Optional[str]]] = []
        seen = set()
        for item in values:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code", "") or "").strip().lower()
            level = str(item.get("level", "") or "").strip().upper()
            if not code:
                continue
            key = f"{code}:{level}"
            if key in seen:
                continue
            seen.add(key)
            out.append({"code": code, "level": level or None})
        return out

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def normalize_job_batch(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize unstructured job payloads into deterministic filtering fields."""
        if not jobs:
            return []

        provider = self._get_provider("normalize")
        jobs_text = ""
        for i, job in enumerate(jobs):
            jobs_text += f"\n--- JOB {i+1} ---\n"
            jobs_text += f"Title: {sanitize_prompt_text(job.get('title'), max_chars=180)}\n"
            jobs_text += f"Company: {sanitize_prompt_text(job.get('company'), max_chars=120)}\n"
            jobs_text += f"Location: {sanitize_prompt_text(job.get('location'), max_chars=120)}\n"
            jobs_text += f"Workload: {sanitize_prompt_text(job.get('workload'), max_chars=80)}\n"
            jobs_text += f"Description: {sanitize_prompt_text(job.get('description'), max_chars=1200)}\n"

        system_prompt = (
            "You are a strict job-posting normalizer. "
            "Extract only explicit evidence and return compact structured JSON in the same order. "
            "Do not infer unsupported requirements."
        )
        user_prompt = f"""Normalize each job below.

Output one object per job with keys:
- title, role_family, domain, seniority, employment_mode, contract_type, qualification_level
- experience_min_years, experience_max_years
- workload_min, workload_max
- salary_min_chf, salary_max_chf
- required_languages (list of {{code, level}})
- required_skills (list of strings)
- education_levels (list of strings)
- key_requirements (list of strings)
- confidence (0.0-1.0)

Domain must be one of: general, it, finance, medical, engineering, hospitality, sales, logistics, administration.
Employment mode must be one of: remote, hybrid, on-site.

{jobs_text}

Return ONLY JSON:
{{
  "results": [
    {{
      "title": "...",
      "role_family": "...",
      "domain": "general",
      "seniority": "mid",
      "employment_mode": "on-site",
      "contract_type": "permanent",
      "qualification_level": "vocational",
      "experience_min_years": 2,
      "experience_max_years": 5,
      "workload_min": 80,
      "workload_max": 100,
      "salary_min_chf": null,
      "salary_max_chf": null,
      "required_languages": [{{"code": "de", "level": "B2"}}],
      "required_skills": ["Python"],
      "education_levels": ["bachelor"],
      "key_requirements": ["Swiss permit"],
      "confidence": 0.75
    }}
  ]
}}"""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        rows = result.get("results", []) if isinstance(result, dict) else []
        normalized_rows: List[Dict[str, Any]] = []

        for idx in range(len(jobs)):
            row = rows[idx] if idx < len(rows) and isinstance(rows[idx], dict) else {}
            confidence = row.get("confidence", 0.0)
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))

            normalized_rows.append(
                {
                    "title": str(row.get("title") or jobs[idx].get("title") or "").strip() or None,
                    "role_family": str(row.get("role_family") or row.get("title") or jobs[idx].get("title") or "").strip() or None,
                    "domain": self._normalize_job_domain_token(row.get("domain") or "general"),
                    "seniority": str(row.get("seniority") or "").strip().lower() or None,
                    "employment_mode": str(row.get("employment_mode") or "").strip().lower() or None,
                    "contract_type": str(row.get("contract_type") or "").strip().lower() or None,
                    "qualification_level": str(row.get("qualification_level") or "").strip().lower() or None,
                    "experience_min_years": self._coerce_nullable_int(row.get("experience_min_years")),
                    "experience_max_years": self._coerce_nullable_int(row.get("experience_max_years")),
                    "workload_min": self._coerce_nullable_int(row.get("workload_min")),
                    "workload_max": self._coerce_nullable_int(row.get("workload_max")),
                    "salary_min_chf": self._coerce_nullable_int(row.get("salary_min_chf")),
                    "salary_max_chf": self._coerce_nullable_int(row.get("salary_max_chf")),
                    "required_languages": self._normalize_required_languages(row.get("required_languages")),
                    "required_skills": self._dedupe_string_list(row.get("required_skills")),
                    "education_levels": self._dedupe_string_list(row.get("education_levels")),
                    "key_requirements": self._dedupe_string_list(row.get("key_requirements")),
                    "confidence": confidence,
                }
            )

        return normalized_rows


llm_service = LLMService()
