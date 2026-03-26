import logging
import threading
from collections import Counter
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

    # ─── CV Summary Helper ──────────────────────────────────────────────

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
        """Extract a dual-signal candidate profile combining CV facts with search intent.

        Produces TWO complementary blocks:
        - ``candidate_profile``: What the CV says the person IS (education, skills, experience).
        - ``search_intent``: What the role_description says the person WANTS to find.

        The two signals are kept separate so that the filtering layer can use the intent as
        the primary comparison axis (e.g. a developer intentionally searching for manual-labor
        jobs will have ``intent.target_domain="logistics"`` while ``candidate.domain="it"``).

        Returns a flat dict with both ``candidate_*`` and ``intent_*`` keys that map directly
        to the ``SearchProfile.profile_normalized_*`` and ``profile_search_intent_*`` columns.
        """
        provider = self._get_provider("normalize_profile")

        strategy_block = (
            f"\n\nSEARCH STRATEGY / EXTRA INSTRUCTIONS:\n{sanitize_prompt_text(search_strategy, max_chars=800)}"
            if search_strategy.strip()
            else ""
        )

        system_prompt = (
            "You are a strict dual-signal candidate-profile normalizer for job-matching. "
            "Extract TWO separate blocks: what the CV says the candidate IS, and what the search "
            "request says they WANT to find. Keep these as distinct signals — the candidate may be "
            "a senior IT professional WANTING an entry-level manual-labor job, and that is valid. "
            "Use only information explicitly present in the inputs — do NOT invent. "
            "All domain, seniority, and qualification_level values MUST come from the allowlists. "
            "Return compact structured JSON."
        )
        user_prompt = f"""Extract the candidate's dual-signal normalized profile.

OUTPUT — one JSON object with TWO nested blocks:

"candidate_profile" — what the CV says the person IS:
  - seniority         : "junior" | "mid" | "senior"  (from CV experience level)
  - domain            : EXACTLY one of: general, it, finance, medical, engineering, hospitality, sales, logistics, administration, legal, education, marketing, consulting, pharma, construction
  - role_family       : normalized job-title family from the CV (e.g. "Software Engineer")
  - qualification_level: "none" | "vocational" | "bachelor" | "master" | "phd"
  - experience_years  : integer (total years of relevant professional experience; 0 if none)
  - languages         : list of {{code (ISO 639-1), level (CEFR A1-C2 or "native")}}
  - skills            : concrete technical/domain skills from CV (max 20); no soft-skills
  - confidence        : 0.0–1.0

"search_intent" — what the role_description + strategy say the person WANTS:
  - target_domain     : EXACTLY one of the same domain allowlist above — the domain they are SEARCHING IN
  - target_seniority  : "junior" | "mid" | "senior" | null — the level they are TARGETING
  - target_role_family: the role/title family they want (may differ from CV)
  - target_qualification_level: "none" | "vocational" | "bachelor" | "master" | "phd" | null — acceptable qualification requirements
  - target_skills     : skills relevant to the TARGET role (not necessarily from CV; max 15)
  - open_to_unrelated : true if the user is EXPLICITLY searching OUTSIDE their CV domain (e.g. IT professional searching for warehouse/cleaning/hospitality work)
  - intent_keywords   : list of free-form keywords capturing what the user wants (e.g. ["manual work", "no qualifications required", "warehouse", "physical labor"])
  - confidence        : 0.0–1.0

DOMAIN RULE: Use "general" only when the domain is truly ambiguous.
OPEN_TO_UNRELATED RULE: Set to true ONLY when the role_description clearly targets a domain
  unrelated to the CV (e.g. programmer searching for cleaning jobs, lawyer searching for delivery work).
  If the search is within or adjacent to the CV domain, set to false.
SENIORITY RULE: For candidate_profile, derive from CV facts.
  For search_intent, derive from what level of job the role_description targets.

CV (truncated to 5000 chars):
{sanitize_prompt_text(cv_content, max_chars=5000)}

ROLE DESCRIPTION (what the user is looking for):
{sanitize_prompt_text(role_description, max_chars=800)}{strategy_block}

Return ONLY JSON — no markdown, no explanations:
{{
  "candidate_profile": {{
    "seniority": "mid",
    "domain": "it",
    "role_family": "Software Engineer",
    "qualification_level": "bachelor",
    "experience_years": 4,
    "languages": [{{"code": "en", "level": "C2"}}, {{"code": "de", "level": "B2"}}],
    "skills": ["Python", "FastAPI", "React", "PostgreSQL"],
    "confidence": 0.85
  }},
  "search_intent": {{
    "target_domain": "it",
    "target_seniority": "mid",
    "target_role_family": "Backend Developer",
    "target_qualification_level": "bachelor",
    "target_skills": ["Python", "REST APIs", "Docker"],
    "open_to_unrelated": false,
    "intent_keywords": ["backend development", "remote work"],
    "confidence": 0.90
  }}
}}"""

        result = await provider.generate_json_async(system_prompt, user_prompt)

        if not isinstance(result, dict):
            return {}

        # ── Parse candidate_profile block ─────────────────────────────────
        cp = result.get("candidate_profile") or {}
        # Fall back to top-level keys for backward compat with old single-block responses
        if not cp and any(k in result for k in ("seniority", "domain", "skills")):
            cp = result

        seniority_raw = str(cp.get("seniority") or "").strip().lower()
        seniority = seniority_raw if seniority_raw in {"junior", "mid", "senior"} else None

        domain_raw = self._normalize_job_domain_token(cp.get("domain") or "general")
        domain = domain_raw or "general"

        role_family = str(cp.get("role_family") or "").strip() or None

        ql_valid = {"none", "vocational", "bachelor", "master", "phd"}
        ql_raw = str(cp.get("qualification_level") or "").strip().lower()
        qualification_level = ql_raw if ql_raw in ql_valid else None

        experience_years = self._coerce_nullable_int(cp.get("experience_years"))
        if experience_years is not None:
            experience_years = max(0, experience_years)

        languages = self._normalize_required_languages(cp.get("languages"))
        skills = self._dedupe_string_list(cp.get("skills"))

        cp_confidence = 0.0
        try:
            cp_confidence = float(cp.get("confidence", 0.0))
        except (TypeError, ValueError):
            pass
        cp_confidence = max(0.0, min(1.0, cp_confidence))

        # ── Parse search_intent block ─────────────────────────────────────
        si = result.get("search_intent") or {}

        intent_domain_raw = self._normalize_job_domain_token(si.get("target_domain") or domain)
        intent_domain = intent_domain_raw or domain

        intent_seniority_raw = str(si.get("target_seniority") or "").strip().lower()
        intent_seniority = intent_seniority_raw if intent_seniority_raw in {"junior", "mid", "senior"} else seniority

        intent_role_family = str(si.get("target_role_family") or role_family or "").strip() or None

        intent_ql_raw = str(si.get("target_qualification_level") or "").strip().lower()
        intent_qualification_level = intent_ql_raw if intent_ql_raw in ql_valid else qualification_level

        intent_skills = self._dedupe_string_list(si.get("target_skills"))

        open_to_unrelated = bool(si.get("open_to_unrelated", False))
        # Safety: only accept open_to_unrelated=True when intent domain actually differs from candidate domain
        if open_to_unrelated and intent_domain == domain and intent_domain != "general":
            open_to_unrelated = False

        intent_keywords = self._dedupe_string_list(si.get("intent_keywords"))

        si_confidence = 0.0
        try:
            si_confidence = float(si.get("confidence", 0.0))
        except (TypeError, ValueError):
            pass
        si_confidence = max(0.0, min(1.0, si_confidence))

        return {
            # Candidate profile — what the CV says
            "seniority": seniority,
            "domain": domain,
            "role_family": role_family,
            "qualification_level": qualification_level,
            "experience_years": experience_years,
            "languages": languages,
            "skills": skills,
            # Search intent — what the user is looking for
            "intent_domain": intent_domain,
            "intent_seniority": intent_seniority,
            "intent_role_family": intent_role_family,
            "intent_qualification_level": intent_qualification_level,
            "intent_skills": intent_skills,
            "open_to_unrelated": open_to_unrelated,
            "intent_keywords": intent_keywords,
        }

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

        searches = await self._call_generate_search_plan(
            profile,
            providers_info,
            max_queries=max_queries,
            max_occupation_queries=max_occupation_queries,
            max_keyword_queries=max_keyword_queries,
        )
        return searches

    @staticmethod
    def _build_coverage_report(
        collected: List[Dict[str, Any]],
        remaining_occupations: Optional[int] = None,
        remaining_keywords: Optional[int] = None,
    ) -> str:
        """Build a structured coverage report for progressive context injection.

        Returns an empty string when no queries have been collected yet (first batch).
        For subsequent batches, provides distribution stats, gap hints, and the full
        structured query list so the LLM can intelligently fill coverage gaps.
        The structured list is capped at 100 entries to keep token usage predictable.
        """
        if not collected:
            return ""

        domain_counts: Counter = Counter()
        language_counts: Counter = Counter()
        type_counts: Counter = Counter()

        for item in collected:
            domain_counts[item.get("domain", "general")] += 1
            language_counts[item.get("language", "en")] += 1
            type_counts[item.get("type", "keyword")] += 1

        occ_count = type_counts.get("occupation", 0)
        kw_count = type_counts.get("keyword", 0)
        total_queries = len(collected)

        # Cap structured list at 100 entries to keep token budget predictable
        _MAX_LIST_ENTRIES = 100
        display_list = collected[-_MAX_LIST_ENTRIES:]
        omitted = total_queries - len(display_list)

        query_lines = [
            f"  [{item.get('type', '?')}] [{item.get('domain', 'general')}] [{item.get('language', '?')}] {item.get('query', '')}"
            for item in display_list
        ]
        if omitted > 0:
            query_lines.insert(0, f"  (... {omitted} earlier queries omitted for brevity ...)")
        query_list_str = "\n".join(query_lines)

        domain_str = ", ".join(
            f"{d}={c}" for d, c in sorted(domain_counts.items(), key=lambda x: -x[1])
        )
        language_str = ", ".join(
            f"{lang}={c}" for lang, c in sorted(language_counts.items(), key=lambda x: -x[1])
        )

        gap_hints: List[str] = []
        core_langs = {"en", "de", "fr", "it"}
        missing_langs = core_langs - set(language_counts.keys())
        if missing_langs:
            gap_hints.append(f"Missing languages: {', '.join(sorted(missing_langs))}")
        else:
            under_langs = sorted(
                lang for lang in core_langs
                if language_counts.get(lang, 0) / total_queries < 0.15
            )
            if under_langs:
                gap_hints.append(f"Underrepresented languages: {', '.join(under_langs)}")

        remaining_str = ""
        if remaining_occupations is not None and remaining_keywords is not None:
            remaining_str = (
                f"\n  STILL NEEDED: {remaining_occupations} more occupation"
                f" + {remaining_keywords} more keyword queries"
            )

        gap_str = ""
        if gap_hints:
            gap_str = "\n  GAP HINTS: " + "; ".join(gap_hints)

        return (
            f"COVERAGE SO FAR ({total_queries} queries already generated):\n"
            f"  Distribution — types: occupation={occ_count}, keyword={kw_count}"
            f" | domains: {domain_str} | languages: {language_str}"
            f"{remaining_str}"
            f"{gap_str}\n"
            f"  FULL LIST (do NOT repeat any of these):\n"
            f"{query_list_str}\n"
            f"  Focus your new queries on dimensions not yet covered"
            f" (new domains, missing/underrepresented languages, role variants, different skills)."
        )

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

        while len(collected) < total_target:
            remaining_total = total_target - len(collected)
            batch_size = min(batch_size_limit, remaining_total)
            batch_occ, batch_kw = self._plan_batch_targets(
                batch_size,
                remaining_total,
                remaining_occupations,
                remaining_keywords,
            )

            try:
                batch_searches = await self._call_generate_search_plan(
                    profile,
                    providers_info,
                    max_queries=batch_size,
                    max_occupation_queries=batch_occ,
                    max_keyword_queries=batch_kw,
                    coverage_context=self._build_coverage_report(
                        collected, remaining_occupations, remaining_keywords
                    ),
                )
            except Exception as batch_error:
                if collected:
                    logger.warning(
                        "[PLAN] Batch call failed, returning partial plan %s/%s: %s",
                        len(collected),
                        total_target,
                        batch_error,
                    )
                    return collected[:total_target]
                raise

            best_batch = self._normalize_searches(
                batch_searches,
                seen_fingerprints,
                seen_loose_fingerprints,
            )

            if not best_batch:
                logger.warning("[PLAN] Batch generation stalled with no new unique queries; terminating early.")
                break

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
                    "[PLAN] Batch under-filled (%s/%s unique queries); continuing with another batch",
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
        coverage_context: str = "",
    ) -> List[Dict[str, Any]]:
        """Internal method: single LLM call to generate the search plan."""
        provider = self._get_provider("plan")
        logger.info("[PLAN] Using %s", provider.model_id)

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

        coverage_block = f"\n{coverage_context}\n" if coverage_context else ""

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

{limit_instruction}{coverage_block}

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

    # ─── Step 3: Job Match Analysis ───────────────────────────────────────


    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def analyze_job_batch(
        self,
        jobs_metadata: List[Dict[str, Any]],
        profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        provider = self._get_provider("match")

        system_prompt = (
            "You are a strict, evidence-driven career coach AI. "
            "Evaluate candidate-job fit conservatively using BOTH the candidate's CV profile AND their stated search intent. "
            "The candidate may intentionally search outside their CV domain — score based on the INTENT, not just the CV. "
            "Cite the main reasons, never invent qualifications. "
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
            # Include pre-computed normalized job facts for the LLM to use directly
            job_norm = job.get("normalized_data") or {}
            if job_norm:
                jobs_text += f"[Normalized] Domain: {job_norm.get('domain')} | Role type: {job_norm.get('role_type')} | Sector: {job_norm.get('industry_sector')} | Seniority: {job_norm.get('seniority')} | Qualification: {job_norm.get('qualification_level')} | Skills: {job_norm.get('required_skills')}\n"

        strategy = profile.get('search_strategy')
        strategy_block = f"\n- Extra AI Instructions / Preferences: {strategy}" if strategy else ""

        # Build structured profile context from normalized data
        profile_norm = profile.get("profile_normalization") or {}
        candidate_structured = ""
        if profile_norm:
            candidate_structured = (
                f"\n- CV Domain: {profile_norm.get('domain')} | Role Family: {profile_norm.get('role_family')}"
                f" | Seniority: {profile_norm.get('seniority')} | Experience: {profile_norm.get('experience_years')} yrs"
                f" | Qualification: {profile_norm.get('qualification_level')}"
                f"\n- CV Skills: {profile_norm.get('skills')}"
                f"\n- CV Languages: {profile_norm.get('languages')}"
            )
            intent_structured = (
                f"\n- Search Target Domain: {profile_norm.get('intent_domain')}"
                f" | Target Role: {profile_norm.get('intent_role_family')}"
                f" | Target Seniority: {profile_norm.get('intent_seniority')}"
                f" | Target Qualification: {profile_norm.get('intent_qualification_level')}"
                f"\n- Intent Skills: {profile_norm.get('intent_skills')}"
                f"\n- Open to unrelated domain: {profile_norm.get('open_to_unrelated')}"
                f"\n- Intent Keywords: {profile_norm.get('intent_keywords')}"
            )
        else:
            intent_structured = ""

        user_prompt = f"""Analyze the match between this candidate and each job below.

CANDIDATE PROFILE:
- Expected Role: {profile.get('role_description')}{strategy_block}
- Experience Context: {profile.get('cv_summary') or profile.get('cv_content')}{candidate_structured}

SEARCH INTENT:{intent_structured if intent_structured else " (use role description above)"}

{jobs_text}

SCORING RULES (STRICT CONSTRAINTS):
1. INTENT-FIRST SCORING: If the candidate is OPEN TO UNRELATED work (open_to_unrelated=true), score based on their INTENT fit to the job, NOT their CV domain. A developer applying for warehouse work should get a high score if the job matches what they said they want.
2. LANGUAGE MISMATCH PENALTY: If the job EXPLICITLY requires a language the candidate DOES NOT speak, cap `affinity_score` at 30 and set `worth_applying` to false.
3. EDUCATION MISMATCH PENALTY: If the job explicitly requires a University Degree (Bachelor/Master/PhD) and the candidate has no degree, cap `affinity_score` at 40 and set `worth_applying` to false.
4. SENIORITY MISMATCH: If the candidate targets junior roles and job requires Senior/Lead (5+ years), cap at 35. (Senior targeting Junior cap at 70).
5. USER INSTRUCTIONS PENALTY: If the job explicitly violates a constraint stated in instructions/strategy, cap `affinity_score` at 20 and set `worth_applying` to false.
6. BASE SCORING: Score 0-100 realistically. Score 90-100 ONLY for a virtually perfect match to WHAT THE CANDIDATE WANTS.
7. `worth_applying` MUST ONLY be true if `affinity_score` >= 65.
8. `affinity_analysis` must be concise and factual: mention fit factors, gaps, and any hard blockers.

DIMENSIONAL SCORING: Also produce sub-scores (0-100 each):
- `skill_match_score`: How well candidate skills (CV + intent_skills) align with job requirements
- `experience_match_score`: Experience level fit (years, seniority)
- `intent_match_score`: How well the job matches what the candidate WANTS (role_description + intent keywords)
- `language_match_score`: Language requirements fit
- `location_match_score`: Location / remote preference fit

Return ONLY JSON with a "results" array, one entry per job, IN ORDER:
{{
    "results": [
        {{
            "affinity_score": 85,
            "affinity_analysis": "...",
            "worth_applying": true,
            "skill_match_score": 80,
            "experience_match_score": 90,
            "intent_match_score": 88,
            "language_match_score": 100,
            "location_match_score": 75
        }}
    ]
}}"""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        results = result.get("results", []) if isinstance(result, dict) else []
        normalized_results: List[Dict[str, Any]] = []

        for item in results[:len(jobs_metadata)]:
            if not isinstance(item, dict):
                normalized_results.append(
                    {
                        "affinity_score": 0,
                        "affinity_analysis": "Invalid analysis payload returned by model.",
                        "worth_applying": False,
                        "skill_match_score": None,
                        "experience_match_score": None,
                        "intent_match_score": None,
                        "language_match_score": None,
                        "location_match_score": None,
                    }
                )
                continue

            score = item.get("affinity_score", 0)
            try:
                score = max(0, min(100, int(score)))
            except Exception:
                score = 0

            def _coerce_sub_score(val) -> Optional[int]:
                if val is None:
                    return None
                try:
                    return max(0, min(100, int(val)))
                except Exception:
                    return None

            worth_applying = bool(item.get("worth_applying", False)) and score >= 65
            normalized_results.append(
                {
                    "affinity_score": score,
                    "affinity_analysis": sanitize_prompt_text(item.get("affinity_analysis", ""), max_chars=600) or "No analysis returned.",
                    "worth_applying": worth_applying,
                    "skill_match_score": _coerce_sub_score(item.get("skill_match_score")),
                    "experience_match_score": _coerce_sub_score(item.get("experience_match_score")),
                    "intent_match_score": _coerce_sub_score(item.get("intent_match_score")),
                    "language_match_score": _coerce_sub_score(item.get("language_match_score")),
                    "location_match_score": _coerce_sub_score(item.get("location_match_score")),
                }
            )

        while len(normalized_results) < len(jobs_metadata):
            normalized_results.append(
                {
                    "affinity_score": 0,
                    "affinity_analysis": "Model returned too few analysis rows.",
                    "worth_applying": False,
                    "skill_match_score": None,
                    "experience_match_score": None,
                    "intent_match_score": None,
                    "language_match_score": None,
                    "location_match_score": None,
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
            jobs_text += f"Description: {sanitize_prompt_text(job.get('description'), max_chars=2400)}\n"

        system_prompt = (
            "You are a strict job-posting normalizer. "
            "Extract only explicit evidence from each posting and return compact structured JSON in the same order. "
            "Do not infer or invent requirements that are not stated."
        )
        user_prompt = f"""Normalize each job below.

Output one object per job with ALL keys below:
- title           : normalized job title (string)
- role_family     : broader role family (e.g. \"Software Engineer\", \"Accountant\", \"Nurse\", \"Warehouse Worker\")
- domain          : MUST be exactly one of: general, it, finance, medical, engineering, hospitality, sales, logistics, administration, legal, education, marketing, consulting, pharma, construction
- industry_sector : granular sector within the domain (e.g. \"web development\", \"warehouse logistics\", \"hospitality cleaning\", \"retail sales\") — null if unclear
- role_type       : \"technical\" | \"manual\" | \"administrative\" | \"creative\" | \"managerial\" | \"service\" | \"professional\"
- seniority       : \"junior\" (0-2 yrs typical) | \"mid\" (3-6 yrs) | \"senior\" (7+ yrs) — null if genuinely unclear
- employment_mode : \"remote\" | \"hybrid\" | \"on-site\" — null if not stated
- contract_type   : \"permanent\" | \"temporary\" | \"internship\" | \"freelance\" — null if not stated
- qualification_level : \"none\" | \"vocational\" | \"bachelor\" | \"master\" | \"phd\" — null if not stated
- experience_min_years : integer minimum years required, or null if not explicitly stated
- experience_max_years : integer maximum years stated, or null
- workload_min    : integer % (e.g. 80). If workload not stated assume 100.
- workload_max    : integer % (e.g. 100)
- salary_min_chf  : integer CHF/year minimum or null
- salary_max_chf  : integer CHF/year maximum or null
- required_languages : list of {{code (ISO 639-1 2-letter lowercase), level (CEFR A1-C2 or \"native\")}} — only languages EXPLICITLY required
- required_skills : list of concrete technical/domain skills (strings) — max 15, no soft-skills
- education_levels : list of education degree strings explicitly required
- key_requirements : list of important hard requirements not covered above (e.g. \"Swiss work permit\", \"clean driving licence\", \"physical fitness\")
- confidence      : 0.0-1.0 reflecting how much explicit data supported the extraction (>0.7 only when most fields are explicitly stated)

DOMAIN RULES:
- Use \"it\" for software, data, devops, cybersecurity, IT infrastructure
- Use \"engineering\" for mechanical, electrical, civil, chemical engineering
- Use \"finance\" for banking, accounting, controlling, investment
- Use \"pharma\" for pharmaceutical research, drug development, regulatory affairs
- Use \"consulting\" for management consulting, strategy, advisory
- Use \"logistics\" for warehouse, shipping, delivery, supply chain, transportation
- Use \"hospitality\" for cleaning, housekeeping, kitchen, hotel, restaurant
- Use \"general\" ONLY when the role truly spans multiple unrelated domains

ROLE_TYPE RULES:
- \"manual\" for physical/hands-on work: warehouse, cleaning, construction, delivery, manufacturing
- \"technical\" for IT, engineering, lab roles requiring specialized technical knowledge
- \"administrative\" for office, HR, reception, data entry
- \"service\" for customer service, hospitality, retail
- \"professional\" for law, medicine, finance, specialized non-technical expertise
- \"creative\" for design, marketing, content, media
- \"managerial\" for team leads, managers, directors

{jobs_text}

Return ONLY JSON:
{{
  \"results\": [
    {{
      \"title\": \"...\",
      \"role_family\": \"...\",
      \"domain\": \"general\",
      \"industry_sector\": null,
      \"role_type\": \"manual\",
      \"seniority\": \"mid\",
      \"employment_mode\": \"on-site\",
      \"contract_type\": \"permanent\",
      \"qualification_level\": \"vocational\",
      \"experience_min_years\": 2,
      \"experience_max_years\": 5,
      \"workload_min\": 80,
      \"workload_max\": 100,
      \"salary_min_chf\": null,
      \"salary_max_chf\": null,
      \"required_languages\": [{{\"code\": \"de\", \"level\": \"B2\"}}],
      \"required_skills\": [\"forklift license\"],
      \"education_levels\": [],
      \"key_requirements\": [\"Swiss permit\"],
      \"confidence\": 0.75
    }}
  ]
}}"""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        rows = result.get("results", []) if isinstance(result, dict) else []
        normalized_rows: List[Dict[str, Any]] = []

        _valid_role_types = {"technical", "manual", "administrative", "creative", "managerial", "service", "professional"}

        for idx in range(len(jobs)):
            row = rows[idx] if idx < len(rows) and isinstance(rows[idx], dict) else {}
            confidence = row.get("confidence", 0.0)
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))

            role_type_raw = str(row.get("role_type") or "").strip().lower()
            role_type = role_type_raw if role_type_raw in _valid_role_types else None

            industry_sector = str(row.get("industry_sector") or "").strip() or None

            normalized_rows.append(
                {
                    "title": str(row.get("title") or jobs[idx].get("title") or "").strip() or None,
                    "role_family": str(row.get("role_family") or row.get("title") or jobs[idx].get("title") or "").strip() or None,
                    "domain": self._normalize_job_domain_token(row.get("domain") or "general"),
                    "industry_sector": industry_sector,
                    "role_type": role_type,
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
