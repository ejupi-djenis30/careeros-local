import logging
from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from backend.core.config import settings
from backend.providers.circuit_breaker import circuit_registry
from backend.providers.llm.factory import get_provider_for_step
from backend.services.search.query_contracts import (
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

    def _get_provider(self, step: str):
        # asyncio is single-threaded; no lock needed for dict access
        if step not in self._provider_cache:
            self._provider_cache[step] = get_provider_for_step(step)
        return self._provider_cache[step]

    def clear_provider_cache(self):
        """Force reload of all LLM providers (e.g. if config changes)."""
        self._provider_cache.clear()

    async def _call_provider_json(
        self,
        provider,
        step: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Invoke provider.generate_json_async with per-step timeout + circuit breaker.

        Uses the circuit breaker keyed on the provider's model_id so that
        repeated failures trip the breaker and subsequent calls fail fast
        (raising CircuitOpenError) rather than blocking for the full timeout.
        """
        cb = circuit_registry.get(
            provider.model_id,
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_seconds=float(settings.CIRCUIT_BREAKER_RECOVERY_SECONDS),
        )

        async def _do_call() -> Dict[str, Any]:
            return await provider.generate_json_async_with_timeout(
                system_prompt,
                user_prompt,
                max_tokens,
                step=step,
            )

        return await cb.call(_do_call())


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
            f"\n\nSEARCH STRATEGY / EXTRA INSTRUCTIONS:\n{sanitize_prompt_text(search_strategy, max_chars=3000)}"
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
        user_prompt = f"""Extract the candidate's dual-signal normalized profile (V2 enhanced format).

OUTPUT — one JSON object with TWO nested blocks:

"candidate_profile" — what the CV says the person IS:
  - seniority              : "junior" | "mid" | "senior"  (from CV experience level)
  - domain                 : EXACTLY one of: general, it, finance, medical, engineering, hospitality, sales, logistics, administration, legal, education, marketing, consulting, pharma, construction
  - role_family            : normalized job-title family from the CV (e.g. "Software Engineer")
  - role_type              : "technical" | "manual" | "administrative" | "creative" | "managerial" | "service" | "professional" — the TYPE of work the person has done
  - qualification_level    : "none" | "vocational" | "bachelor" | "master" | "phd"
  - experience_years       : integer (total years of relevant professional experience; 0 if none)
  - languages              : list of {{code (ISO 639-1), level (CEFR A1-C2 or "native")}}
  - skills                 : concrete technical/domain skills from CV (max 20); no soft-skills
  - industry_sectors       : list of industries/sectors the candidate has worked in (e.g. ["web development", "e-commerce", "banking"]); max 5
  - transferable_skills    : domain-agnostic competencies from CV that apply across sectors (e.g. ["project management", "team leadership", "data analysis", "process optimization", "customer relations"]); max 10, no overlap with skills
  - confidence             : 0.0–1.0

"search_intent" — what the role_description + strategy say the person WANTS:
  - target_domain              : EXACTLY one of the same domain allowlist above — the domain they are SEARCHING IN
  - target_role_type           : "technical" | "manual" | "administrative" | "creative" | "managerial" | "service" | "professional" | null — the TYPE of work they want
  - target_seniority           : "junior" | "mid" | "senior" | null — the level they are TARGETING
  - target_seniority_min       : "junior" | "mid" | "senior" | null — lowest acceptable seniority level
  - target_seniority_max       : "junior" | "mid" | "senior" | null — highest acceptable seniority level
  - target_role_family         : the role/title family they want (may differ from CV)
  - target_qualification_level : "none" | "vocational" | "bachelor" | "master" | "phd" | null — max qualification requirement they can meet
  - target_skills              : skills relevant to the TARGET role (not necessarily from CV; max 15)
  - open_to_unrelated          : true if the user is EXPLICITLY searching OUTSIDE their CV domain (e.g. IT professional searching for warehouse/cleaning/hospitality work)
  - intent_keywords            : list of free-form keywords capturing what the user wants (e.g. ["manual work", "no qualifications required", "warehouse", "physical labor"])
  - dealbreakers               : list of absolute constraints the user will NOT accept (extract from strategy/instructions, e.g. ["night shifts", "requires German C2", "unpaid overtime", "relocation required"]); empty list if none stated
  - flexibility                : object indicating which dimensions the user is flexible on: {{"domain": bool, "seniority": bool, "qualification": bool, "location": bool}}
  - confidence                 : 0.0–1.0

DOMAIN RULE: Use "general" only when the domain is truly ambiguous.
OPEN_TO_UNRELATED RULE: Set to true ONLY when the role_description clearly targets a domain
  unrelated to the CV (e.g. programmer searching for cleaning jobs, lawyer searching for delivery work).
  If the search is within or adjacent to the CV domain, set to false.
SENIORITY RANGE RULE: target_seniority_min/max capture the acceptable range (e.g. if someone wants "junior or mid level", set min="junior" max="mid"). Set both equal if only one level is acceptable.
ROLE_TYPE RULE: "manual" for physical/hands-on work (warehouse, cleaning, construction, delivery). "technical" for IT, engineering, lab roles. "administrative" for office, HR, reception. "service" for customer-facing. Use the role_description to determine target_role_type.
TRANSFERABLE SKILLS RULE: These are competencies that cross domain boundaries — project management, team leadership, communication, data analysis, problem solving, customer relations, etc. Distinct from domain-specific technical skills.
DEALBREAKER RULE: Extract explicit negative constraints from the strategy/instructions only. Do not infer dealbreakers.
FLEXIBILITY RULE: domain=true if the user is explicitly open to different domains. seniority=true if they express openness to a range. qualification=true if they say qualifications don't matter. location=true if they mention remote/any location.

CV:
{sanitize_prompt_text(cv_content, max_chars=20000)}

ROLE DESCRIPTION (what the user is looking for):
{sanitize_prompt_text(role_description, max_chars=3000)}{strategy_block}

Return ONLY JSON — no markdown, no explanations:
{{
  "candidate_profile": {{
    "seniority": "mid",
    "domain": "it",
    "role_family": "Software Engineer",
    "role_type": "technical",
    "qualification_level": "bachelor",
    "experience_years": 4,
    "languages": [{{"code": "en", "level": "C2"}}, {{"code": "de", "level": "B2"}}],
    "skills": ["Python", "FastAPI", "React", "PostgreSQL"],
    "industry_sectors": ["web development", "e-commerce"],
    "transferable_skills": ["project management", "agile methodology", "team collaboration"],
    "confidence": 0.85
  }},
  "search_intent": {{
    "target_domain": "logistics",
    "target_role_type": "manual",
    "target_seniority": "junior",
    "target_seniority_min": "junior",
    "target_seniority_max": "mid",
    "target_role_family": "Warehouse Worker",
    "target_qualification_level": "none",
    "target_skills": ["forklift operation", "physical fitness"],
    "open_to_unrelated": true,
    "intent_keywords": ["manual work", "warehouse", "no degree required", "physical labor"],
    "dealbreakers": ["night shifts"],
    "flexibility": {{"domain": true, "seniority": true, "qualification": true, "location": false}},
    "confidence": 0.90
  }}
}}"""

        result = await self._call_provider_json(provider, "normalize_profile", system_prompt, user_prompt)

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

        _valid_role_types = {"technical", "manual", "administrative", "creative", "managerial", "service", "professional"}
        role_type_raw = str(cp.get("role_type") or "").strip().lower()
        role_type = role_type_raw if role_type_raw in _valid_role_types else None

        ql_valid = {"none", "vocational", "bachelor", "master", "phd"}
        ql_raw = str(cp.get("qualification_level") or "").strip().lower()
        qualification_level = ql_raw if ql_raw in ql_valid else None

        experience_years = self._coerce_nullable_int(cp.get("experience_years"))
        if experience_years is not None:
            experience_years = max(0, experience_years)

        languages = self._normalize_required_languages(cp.get("languages"))
        skills = self._dedupe_string_list(cp.get("skills"))
        industry_sectors = self._dedupe_string_list(cp.get("industry_sectors"))
        transferable_skills = self._dedupe_string_list(cp.get("transferable_skills"))

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

        # Seniority range
        _all_seniorities = {"junior", "mid", "senior"}
        seniority_min_raw = str(si.get("target_seniority_min") or "").strip().lower()
        intent_seniority_min = seniority_min_raw if seniority_min_raw in _all_seniorities else intent_seniority

        seniority_max_raw = str(si.get("target_seniority_max") or "").strip().lower()
        intent_seniority_max = seniority_max_raw if seniority_max_raw in _all_seniorities else intent_seniority

        intent_role_family = str(si.get("target_role_family") or role_family or "").strip() or None

        intent_ql_raw = str(si.get("target_qualification_level") or "").strip().lower()
        intent_qualification_level = intent_ql_raw if intent_ql_raw in ql_valid else qualification_level

        intent_skills = self._dedupe_string_list(si.get("target_skills"))

        intent_role_type_raw = str(si.get("target_role_type") or "").strip().lower()
        intent_role_type = intent_role_type_raw if intent_role_type_raw in _valid_role_types else None

        open_to_unrelated = bool(si.get("open_to_unrelated", False))
        # Safety: only accept open_to_unrelated=True when intent domain actually differs from candidate domain
        if open_to_unrelated and intent_domain == domain and intent_domain != "general":
            open_to_unrelated = False

        intent_keywords = self._dedupe_string_list(si.get("intent_keywords"))
        dealbreakers = self._dedupe_string_list(si.get("dealbreakers"))

        # Flexibility object — validate each key is a boolean
        flexibility_raw = si.get("flexibility")
        flexibility: dict = {}
        if isinstance(flexibility_raw, dict):
            for dim in ("domain", "seniority", "qualification", "location"):
                val = flexibility_raw.get(dim)
                if isinstance(val, bool):
                    flexibility[dim] = val
                elif isinstance(val, str):
                    flexibility[dim] = val.lower() in {"true", "1", "yes"}
        if not flexibility:
            # Derive sensible defaults from other signals
            flexibility = {
                "domain": open_to_unrelated,
                "seniority": intent_seniority_min != intent_seniority_max,
                "qualification": False,
                "location": False,
            }

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
            "role_type": role_type,
            "qualification_level": qualification_level,
            "experience_years": experience_years,
            "languages": languages,
            "skills": skills,
            "industry_sectors": industry_sectors,
            "transferable_skills": transferable_skills,
            # Search intent — what the user is looking for
            "intent_domain": intent_domain,
            "intent_role_type": intent_role_type,
            "intent_seniority": intent_seniority,
            "intent_seniority_min": intent_seniority_min,
            "intent_seniority_max": intent_seniority_max,
            "intent_role_family": intent_role_family,
            "intent_qualification_level": intent_qualification_level,
            "intent_skills": intent_skills,
            "open_to_unrelated": open_to_unrelated,
            "intent_keywords": intent_keywords,
            "dealbreakers": dealbreakers,
            "flexibility": flexibility,
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
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
            "For cross-domain candidates, assess transferable skills explicitly. "
            "Cite the main reasons, never invent qualifications. "
            "Return results in the EXACT SAME ORDER as the jobs were given."
        )

        import asyncio as _asyncio

        MATCH_DESC_LIMIT = 6000
        # Compress descriptions that exceed the limit before building the batch prompt.
        # Keeps the MATCH step within context limits while preserving all explicit requirements.
        descriptions = await _asyncio.gather(*[
            self._compress_description_if_needed(job.get("description") or "", MATCH_DESC_LIMIT)
            for job in jobs_metadata
        ])

        jobs_text = ""
        for i, (job, desc) in enumerate(zip(jobs_metadata, descriptions)):
            jobs_text += f"\n--- JOB {i+1} ---\n"
            jobs_text += f"Title: {job.get('title')}\n"
            jobs_text += f"Company: {job.get('company')}\n"
            jobs_text += f"Location: {job.get('location')}\n"
            jobs_text += f"Workload: {job.get('workload')}\n"
            jobs_text += f"Languages Required: {job.get('languages')}\n"
            jobs_text += f"Education Required: {job.get('education')}\n"
            jobs_text += f"Description: {desc}\n"
            # Include pre-computed normalized job facts for the LLM to use directly
            job_norm = job.get("normalized_data") or {}
            if job_norm:
                jobs_text += (
                    f"[Normalized] Domain: {job_norm.get('domain')} | Role type: {job_norm.get('role_type')}"
                    f" | Sector: {job_norm.get('industry_sector')} | Seniority: {job_norm.get('seniority')}"
                    f" | Qualification: {job_norm.get('qualification_level')}"
                    f" | Entry barrier: {job_norm.get('entry_barrier')}"
                    f" | Career-changer friendly: {job_norm.get('career_changer_friendly')}\n"
                    f" | Required skills: {job_norm.get('required_skills')}"
                    f" | Preferred skills: {job_norm.get('preferred_skills')}"
                    f" | Physical requirements: {job_norm.get('physical_requirements')}"
                    f" | Hard blockers: {job_norm.get('hard_blockers')}\n"
                )
            # Phase 3.1: Swiss implicit language hint when no explicit lang requirements
            if not job.get("languages"):
                try:
                    from backend.services.search.listing_utils import infer_implicit_language
                    implicit_lang = infer_implicit_language(job.get("location"))
                    if implicit_lang:
                        jobs_text += f"[Implicit Language Hint] Location suggests primary language: {implicit_lang} — consider this when scoring language fit.\n"
                except Exception:
                    pass

        strategy = profile.get('search_strategy')
        strategy_block = f"\n- Extra AI Instructions / Preferences: {strategy}" if strategy else ""

        # Build structured profile context from normalized data
        profile_norm = profile.get("profile_normalization") or {}
        candidate_structured = ""
        if profile_norm:
            candidate_structured = (
                f"\n- CV Domain: {profile_norm.get('domain')} | CV Role Type: {profile_norm.get('role_type')}"
                f" | Role Family: {profile_norm.get('role_family')}"
                f" | Seniority: {profile_norm.get('seniority')} | Experience: {profile_norm.get('experience_years')} yrs"
                f" | Qualification: {profile_norm.get('qualification_level')}"
                f"\n- CV Skills: {profile_norm.get('skills')}"
                f"\n- Transferable Skills: {profile_norm.get('transferable_skills')}"
                f"\n- Industry Sectors (CV): {profile_norm.get('industry_sectors')}"
                f"\n- CV Languages: {profile_norm.get('languages')}"
            )
            dealbreakers = profile_norm.get('dealbreakers') or []
            flexibility = profile_norm.get('flexibility') or {}
            intent_structured = (
                f"\n- Target Domain: {profile_norm.get('intent_domain')}"
                f" | Target Role Type: {profile_norm.get('intent_role_type')}"
                f" | Target Role: {profile_norm.get('intent_role_family')}"
                f" | Seniority Range: {profile_norm.get('intent_seniority_min')}-{profile_norm.get('intent_seniority_max')}"
                f" | Target Qualification: {profile_norm.get('intent_qualification_level')}"
                f"\n- Intent Skills: {profile_norm.get('intent_skills')}"
                f"\n- Open to unrelated domain: {profile_norm.get('open_to_unrelated')}"
                f"\n- Intent Keywords: {profile_norm.get('intent_keywords')}"
                f"\n- Dealbreakers (ABSOLUTE NOs): {dealbreakers if dealbreakers else 'None stated'}"
                f"\n- Flexibility: domain={flexibility.get('domain')}, seniority={flexibility.get('seniority')}"
                f", qualification={flexibility.get('qualification')}, location={flexibility.get('location')}"
            )
        else:
            intent_structured = ""

        # ── Phase 2: Behavioural preference injection ─────────────────────────
        # Injects aggregated apply/dismiss signals as a SOFT tiebreaker. This
        # block is only activated once the user has enough interaction history
        # (PREFERENCE_MIN_SIGNAL_COUNT) and is never allowed to override hard
        # constraints (dealbreakers, language caps, etc.).
        preference_block = ""
        try:
            pref_signals = profile.get("preference_signals") or {}
            if (
                settings.MATCH_ENABLE_PREFERENCE_INJECTION
                and pref_signals.get("signal_count", 0) >= settings.PREFERENCE_MIN_SIGNAL_COUNT
            ):
                preferred_domains = pref_signals.get("preferred_domains") or []
                avoided_domains = pref_signals.get("avoided_domains") or []
                preferred_skills = (pref_signals.get("preferred_skills") or [])[:10]
                preferred_role_types = pref_signals.get("preferred_role_types") or []
                dealbreaker_patterns = pref_signals.get("dealbreaker_patterns") or {}
                typical_salary = pref_signals.get("typical_salary_range") or {}

                signal_lines = []
                if preferred_domains:
                    signal_lines.append(f"- Preferred domains (user has applied to): {', '.join(preferred_domains[:3])}")
                if avoided_domains:
                    signal_lines.append(f"- Domains user consistently dismisses (treat as soft negative): {', '.join(avoided_domains[:3])}")
                if preferred_role_types:
                    signal_lines.append(f"- Preferred role types: {', '.join(preferred_role_types)}")
                if preferred_skills:
                    signal_lines.append(f"- Skills the user actively engages with: {', '.join(preferred_skills)}")
                if dealbreaker_patterns:
                    top_reasons = sorted(dealbreaker_patterns.items(), key=lambda x: -x[1])[:3]
                    signal_lines.append(f"- Frequent dismissal reasons: {', '.join(f'{r}({c})' for r, c in top_reasons)}")
                if typical_salary.get("typical_min_chf"):
                    signal_lines.append(
                        f"- Typical salary bracket the user applies to: "
                        f"{typical_salary.get('typical_min_chf'):,}–{typical_salary.get('typical_max_chf') or '?'} CHF/yr"
                    )

                if signal_lines:
                    preference_block = (
                        "\n\nUSER BEHAVIOURAL SIGNALS (soft tiebreaker — do NOT override hard constraints above):\n"
                        + "\n".join(signal_lines)
                        + "\nUse these only to gently adjust scores when two jobs are otherwise similar."
                    )
        except Exception:
            preference_block = ""  # Never let preference injection break the prompt

        user_prompt = f"""Analyze the match between this candidate and each job below.

CANDIDATE PROFILE:
- Expected Role: {profile.get('role_description')}{strategy_block}
- Experience Context: {profile.get('cv_summary') or profile.get('cv_content')}{candidate_structured}

SEARCH INTENT:{intent_structured if intent_structured else " (use role description above)"}{preference_block}

{jobs_text}

SCORING RULES (STRICT CONSTRAINTS):
1. INTENT-FIRST SCORING: If the candidate is OPEN TO UNRELATED work (open_to_unrelated=true), score based on their INTENT fit to the job, NOT their CV domain. A developer applying for warehouse work should get a high score if the job matches what they said they want.
2. TRANSFERABILITY RULE: For cross-domain candidates, explicitly assess which transferable skills (project management, leadership, communication, data analysis, logistics coordination, etc.) apply to the job. A career-changer_friendly job with entry_barrier=none/low may be a good match even with zero domain overlap.
3. DEALBREAKER PENALTY: If the candidate has stated DEALBREAKERS and the job triggers one, cap `affinity_score` at 20 and set `worth_applying` to false. State which dealbreaker was hit.
4. LANGUAGE MISMATCH PENALTY: If the job EXPLICITLY requires a language the candidate DOES NOT speak, cap `affinity_score` at 30 and set `worth_applying` to false.
5. EDUCATION MISMATCH PENALTY: If the job explicitly requires a University Degree (Bachelor/Master/PhD) and the candidate has no degree, cap `affinity_score` at 40 and set `worth_applying` to false. However, entry_barrier=none/low jobs should NOT apply this penalty.
6. SENIORITY RANGE: If the candidate has a seniority range (min-max), score is not penalized if the job falls within that range. Only penalize extreme mismatches.
7. USER INSTRUCTIONS PENALTY: If the job explicitly violates a constraint stated in instructions/strategy, cap `affinity_score` at 20 and set `worth_applying` to false.
8. ENTRY BARRIER BONUS: If the candidate is flexible (open_to_unrelated=true) and the job has entry_barrier=none or career_changer_friendly=true, BOOST the intent_match_score — these jobs are easier to get into for career changers.
9. BASE SCORING: Score 0-100 realistically. Score 90-100 ONLY for a virtually perfect match to WHAT THE CANDIDATE WANTS.
10. `worth_applying` MUST ONLY be true if `affinity_score` >= 65.
11. `affinity_analysis` must be factual and detailed: mention fit factors, transferable skills relevance, gaps, language requirements, certifications/hard blockers, and dealbreaker hits. Max 1,500 chars.

DIMENSIONAL SCORING: Also produce sub-scores (0-100 each):
- `skill_match_score`: How well candidate skills (CV + transferable + intent_skills) align with job required+preferred skills
- `experience_match_score`: Experience level fit (years, seniority) — use seniority range for tolerance
- `intent_match_score`: How well the job matches what the candidate WANTS (role description + intent keywords + role_type match)
- `language_match_score`: Language requirements fit
- `location_match_score`: Location / remote preference fit
- `transferability_score`: How well candidate's transferable skills + cross-domain experience apply to this specific job (0=no overlap, 100=perfect transferable fit)
- `qualification_gap_score`: How relevant candidate's qualification is for THIS job — consider domain relevance (a CS bachelor for warehouse work = low relevance but high accessibility if entry_barrier=none)

EVIDENCE-GROUNDED STRUCTURED ANALYSIS:
For each job also produce `analysis_structured` with:
- `strengths`: list of ≤5 concrete advantages, EACH backed by a verbatim excerpt from the job text in parentheses e.g. "Skill X matches (job requires 'exact phrase')"
- `weaknesses`: list of ≤5 genuine mismatches backed by job evidence
- `gaps`: list of skills/qualifications the candidate lacks that job explicitly requires
- `verdict`: one-sentence summary (max 200 chars)
- `evidence_citations`: list of ≤4 objects {{type, job_evidence (exact quote ≤80 chars), candidate_evidence}}

HARD-TO-MISS SIGNAL — RED FLAGS: For each job also detect `red_flags` — list warning signals:
- Very high workload with no salary transparency → "no_salary_disclosed"
- Vague role with no real requirements → "vague_requirements"
- Unrealistic experience/education combo → "unrealistic_requirements"
- Job requires skills not aligned with listed domain → "domain_skills_mismatch"
- Mass-hiring / temporary placement language → "temp_agency"
- Signs of discriminatory language → "discriminatory_language"
Leave empty list [] if none detected.

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
            "location_match_score": 75,
            "transferability_score": 70,
            "qualification_gap_score": 50,
            "analysis_structured": {{
                "strengths": ["Python expertise matches (job requires 'proficiency in Python')"],
                "weaknesses": ["No AWS experience (job requires 'AWS certification')"],
                "gaps": ["AWS certification", "Docker experience"],
                "verdict": "Strong backend fit, cloud gap is manageable.",
                "evidence_citations": [
                    {{"type": "skill_match", "job_evidence": "proficiency in Python", "candidate_evidence": "5 years Python"}}
                ]
            }},
            "red_flags": []
        }}
    ]
}}"""

        result = await self._call_provider_json(provider, "match", system_prompt, user_prompt)
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
                        "transferability_score": None,
                        "qualification_gap_score": None,
                        "analysis_structured": None,
                        "red_flags": None,
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

            # Extract evidence-grounded structured analysis
            raw_structured = item.get("analysis_structured")
            analysis_structured: Optional[Dict[str, Any]] = None
            if isinstance(raw_structured, dict):
                analysis_structured = {
                    "strengths": raw_structured.get("strengths") or [],
                    "weaknesses": raw_structured.get("weaknesses") or [],
                    "gaps": raw_structured.get("gaps") or [],
                    "verdict": sanitize_prompt_text(str(raw_structured.get("verdict") or ""), max_chars=250),
                    "evidence_citations": raw_structured.get("evidence_citations") or [],
                }

            # Extract red flags
            raw_red_flags = item.get("red_flags")
            red_flags: Optional[List[str]] = None
            if isinstance(raw_red_flags, list):
                red_flags = [str(f).strip() for f in raw_red_flags if f and str(f).strip()]
                if not red_flags:
                    red_flags = None

            normalized_results.append(
                {
                    "affinity_score": score,
                    "affinity_analysis": sanitize_prompt_text(item.get("affinity_analysis", ""), max_chars=1500) or "No analysis returned.",
                    "worth_applying": worth_applying,
                    "skill_match_score": _coerce_sub_score(item.get("skill_match_score")),
                    "experience_match_score": _coerce_sub_score(item.get("experience_match_score")),
                    "intent_match_score": _coerce_sub_score(item.get("intent_match_score")),
                    "language_match_score": _coerce_sub_score(item.get("language_match_score")),
                    "location_match_score": _coerce_sub_score(item.get("location_match_score")),
                    "transferability_score": _coerce_sub_score(item.get("transferability_score")),
                    "qualification_gap_score": _coerce_sub_score(item.get("qualification_gap_score")),
                    "analysis_structured": analysis_structured,
                    "red_flags": red_flags,
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
                    "transferability_score": None,
                    "qualification_gap_score": None,
                    "analysis_structured": None,
                    "red_flags": None,
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

    async def _compress_description_if_needed(self, description: str, max_chars: int) -> str:
        """Compress a job description with the LLM when it exceeds max_chars.

        This is a lossless operation: the compressor preserves ALL explicit factual
        requirements (language levels, certifications, skills, experience minimums,
        qualifications, hard blockers, work permits) and removes only marketing filler,
        repeated sentences, and generic company introductions.

        Falls back to hard truncation if the LLM call fails, so the caller always
        gets a usable string within the limit.
        """
        if not description or len(description) <= max_chars:
            return description

        logger.info(
            "[COMPRESS] Description (%d chars) exceeds %d — compressing with LLM",
            len(description), max_chars,
        )
        provider = self._get_provider("compress")
        system_prompt = (
            "You are a lossless job-description compressor. "
            "Your task: compress a job posting to fit within a character limit while preserving "
            "EVERY explicit factual requirement without exception. "
            "MUST preserve: language requirements with CEFR levels (e.g. 'German C2 required'), "
            "certifications, licenses, work permits, required and preferred skills, "
            "minimum/maximum experience years, education requirements, salary ranges, "
            "workload percentages, employment mode, contract type, hard blockers, "
            "physical requirements, and all qualification constraints. "
            "REMOVE ONLY: company marketing language, mission/vision statements, "
            "repeated sentences, redundant 'we offer' filler, and generic introductions. "
            "Never soften, paraphrase away, or omit any stated factual requirement. "
            "Output plain text only — no JSON, no bullet points, no headers unless the original had them."
        )
        user_prompt = (
            f"Compress the following job description to under {max_chars} characters. "
            "PRESERVE ALL explicit requirements (language levels, certifications, skills, "
            "experience, qualifications, hard blockers). "
            "REMOVE ONLY marketing fluff and repetition.\n\n"
            f"{description}"
        )
        try:
            compressed = await provider.generate_text_async(system_prompt, user_prompt)
            if compressed and len(compressed.strip()) > 50:
                result = compressed.strip()
                logger.info("[COMPRESS] Compressed %d → %d chars", len(description), len(result))
                return result
        except Exception as exc:
            logger.warning("[COMPRESS] LLM compression failed (%s); falling back to hard truncation", exc)
        return description[:max_chars]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def normalize_job_batch(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize unstructured job payloads into deterministic filtering fields."""
        if not jobs:
            return []

        import asyncio as _asyncio

        provider = self._get_provider("normalize")
        NORMALIZE_DESC_LIMIT = 8000
        # Compress descriptions that exceed the limit in parallel before building the batch text.
        # Lossless: the compressor preserves all factual requirements, removes only marketing filler.
        descriptions = await _asyncio.gather(*[
            self._compress_description_if_needed(job.get("description") or "", NORMALIZE_DESC_LIMIT)
            for job in jobs
        ])

        jobs_text = ""
        for i, (job, desc) in enumerate(zip(jobs, descriptions)):
            jobs_text += f"\n--- JOB {i+1} ---\n"
            jobs_text += f"Title: {sanitize_prompt_text(job.get('title'), max_chars=180)}\n"
            jobs_text += f"Company: {sanitize_prompt_text(job.get('company'), max_chars=120)}\n"
            jobs_text += f"Location: {sanitize_prompt_text(job.get('location'), max_chars=120)}\n"
            jobs_text += f"Workload: {sanitize_prompt_text(job.get('workload'), max_chars=80)}\n"
            jobs_text += f"Description: {sanitize_prompt_text(desc, max_chars=8000)}\n"

        system_prompt = (
            "You are a strict job-posting normalizer. "
            "Extract only explicit evidence from each posting and return compact structured JSON in the same order. "
            "Do not infer or invent requirements that are not stated."
        )
        user_prompt = f"""Normalize each job below. Extract structured fields for precise job-candidate matching.

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
- required_skills : list of MUST-HAVE concrete technical/domain skills (strings) — max 15, no soft-skills; these are non-negotiable requirements
- preferred_skills : list of NICE-TO-HAVE skills — mentioned as \"ideally\", \"von Vorteil\", \"a plus\", \"preferred\" — max 10
- soft_skills     : interpersonal/organizational skills explicitly mentioned (e.g. \"team player\", \"communication\", \"problem solving\") — max 8
- physical_requirements : list of physical demands EXPLICITLY stated (e.g. [\"heavy lifting\", \"standing 8+ hours\", \"forklift operation\", \"outdoor work\"]) — null/empty if none or non-manual job
- entry_barrier   : \"none\" | \"low\" | \"medium\" | \"high\" — overall accessibility of the role:
    - \"none\": no qualifications/experience required, welcomes complete beginners
    - \"low\": vocational training or 1-2 years experience expected
    - \"medium\": bachelor degree or 3-5 years experience required
    - \"high\": master/PhD or 7+ years of specialized experience required
- career_changer_friendly : true if the posting EXPLICITLY says any of: \"Quereinsteiger willkommen\", \"career changers welcome\", \"training provided\", \"no prior experience required\", \"we train you\", \"Einarbeitung wird geboten\" — false otherwise
- education_levels : list of education degree strings explicitly required
- key_requirements : list of important general requirements not covered above (e.g. \"Swiss work permit\", \"clean driving licence\", \"physical fitness\")
- hard_blockers   : list of ABSOLUTE non-negotiable requirements; certifications/permits that make the role impossible without (e.g. [\"valid Swiss work permit B/C\", \"type B driving license\", \"forklift operator certificate\"])
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

REQUIRED vs PREFERRED SKILLS RULE: Only list in required_skills if the posting uses mandatory language (\"you must have\", \"Voraussetzung\", \"required\", \"Kenntnisse\", \"zwingend\"). Use preferred_skills for optional language (\"ideally\", \"nice to have\", \"von Vorteil\", \"ein Plus\", \"preferred\").

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
      \"preferred_skills\": [\"warehouse management system\"],
      \"soft_skills\": [\"team player\", \"reliable\"],
      \"physical_requirements\": [\"heavy lifting\", \"standing 8+ hours\"],
      \"entry_barrier\": \"low\",
      \"career_changer_friendly\": false,
      \"education_levels\": [],
      \"key_requirements\": [\"Swiss permit\"],
      \"hard_blockers\": [\"valid Swiss work permit\"],
      \"confidence\": 0.75
    }}
  ]
}}"""

        result = await self._call_provider_json(provider, "normalize", system_prompt, user_prompt)
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

            # career_changer_friendly: only accept explicit True; default to False
            ccf_raw = row.get("career_changer_friendly")
            career_changer_friendly = bool(ccf_raw) if isinstance(ccf_raw, bool) else False

            _valid_barriers = {"none", "low", "medium", "high"}
            barrier_raw = str(row.get("entry_barrier") or "").strip().lower()
            entry_barrier = barrier_raw if barrier_raw in _valid_barriers else None

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
                    "preferred_skills": self._dedupe_string_list(row.get("preferred_skills")),
                    "soft_skills": self._dedupe_string_list(row.get("soft_skills")),
                    "physical_requirements": self._dedupe_string_list(row.get("physical_requirements")),
                    "entry_barrier": entry_barrier,
                    "career_changer_friendly": career_changer_friendly,
                    "education_levels": self._dedupe_string_list(row.get("education_levels")),
                    "key_requirements": self._dedupe_string_list(row.get("key_requirements")),
                    "hard_blockers": self._dedupe_string_list(row.get("hard_blockers")),
                    "confidence": confidence,
                }
            )

        # ── Phase 1.1: Post-LLM validation: catch hallucinated enum values ────
        try:
            from backend.services.search.normalization_validator import validate_normalized_batch
            normalized_rows, indices_needing_review = validate_normalized_batch(normalized_rows)
            if indices_needing_review:
                logger.debug(
                    "[NORMALIZE] Validator corrected %d/%d rows (indices: %s)",
                    len(indices_needing_review), len(normalized_rows), indices_needing_review,
                )
        except Exception as _ve:
            logger.warning("[NORMALIZE] normalization_validator call failed: %s", _ve)

        return normalized_rows


    # ─── Phase 3.2: Two-pass critique for borderline scores ──────────────────

    async def critique_job_batch(
        self,
        jobs_metadata: List[Dict[str, Any]],
        initial_results: List[Dict[str, Any]],
        profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Second-pass critique pass for jobs with uncertain borderline scores.

        Takes jobs that fell in the configured CRITIQUE_SCORE_RANGE (default 40-80)
        and re-evaluates them with a challenger prompt that looks for over-scoring
        (missed hard blockers, optimism bias in first pass) or under-scoring
        (missed transferable skills, missed career-changer signals).

        Returns only the updated results for the passed-in jobs.
        Input ``jobs_metadata`` and ``initial_results`` must be the SAME length.
        """
        if not jobs_metadata or not initial_results:
            return initial_results

        provider = self._get_provider("critique")

        jobs_text = ""
        initial_text = ""
        for i, (job, init) in enumerate(zip(jobs_metadata, initial_results)):
            jobs_text += f"\n--- JOB {i+1} ---\n"
            jobs_text += f"Title: {job.get('title')}\n"
            jobs_text += f"Company: {job.get('company')}\n"
            jobs_text += f"Description: {sanitize_prompt_text(job.get('description') or '', max_chars=4000)}\n"
            job_norm = job.get("normalized_data") or {}
            if job_norm:
                jobs_text += (
                    f"[Normalized] Domain: {job_norm.get('domain')} | Seniority: {job_norm.get('seniority')}"
                    f" | Entry barrier: {job_norm.get('entry_barrier')}"
                    f" | Career-changer friendly: {job_norm.get('career_changer_friendly')}"
                    f" | Hard blockers: {job_norm.get('hard_blockers')}\n"
                )
            initial_text += (
                f"\nJOB {i+1} INITIAL SCORE: {init.get('affinity_score')}\n"
                f"Initial analysis: {init.get('affinity_analysis', '')[:500]}\n"
            )

        profile_norm = profile.get("profile_normalization") or {}
        candidate_block = (
            f"Role: {profile.get('role_description')}\n"
            f"CV summary: {sanitize_prompt_text(profile.get('cv_summary') or '', max_chars=800)}\n"
            f"Domain: {profile_norm.get('domain')} | Skills: {profile_norm.get('skills')}\n"
            f"Intent domain: {profile_norm.get('intent_domain')} | Open to unrelated: {profile_norm.get('open_to_unrelated')}\n"
            f"Dealbreakers: {profile_norm.get('dealbreakers') or 'None'}\n"
        )

        system_prompt = (
            "You are a second-opinion career coach reviewing initial job-fit scores. "
            "Your job is to CHALLENGE the initial assessment: look for over-scoring (optimism bias, "
            "ignored hard blockers, missed language gaps) AND under-scoring (missed transferable skills, "
            "missed career-changer signals, underestimated adaptability). "
            "Be calibrated: only change the score if you have concrete evidence for it. "
            "If the initial score seems correct, keep it. Never adjust by more than ±20 without strong evidence."
        )
        user_prompt = f"""Review and potentially correct these initial job-match scores.

CANDIDATE:
{candidate_block}

INITIAL SCORES:
{initial_text}

JOB DETAILS:
{jobs_text}

CRITIQUE RULES:
1. Check for MISSED HARD BLOCKERS: did the first pass miss a language requirement, work permit, or mandatory certification?
2. Check for OPTIMISM BIAS: was the first pass too generous about transferable skills or entry barriers?
3. Check for PESSIMISM BIAS: was the first pass too strict about domain match when the job is career-changer friendly?
4. Check for DEALBREAKER MISSES: re-verify all stated candidate dealbreakers against each job.
5. Sub-score CONSISTENCY: does the overall affinity_score make sense given the sub-scores? Fix inconsistencies.
6. If the initial score is justified, set the revised score to the same value.

Return ONLY JSON with a "results" array, one entry per job, IN ORDER:
{{
    "results": [
        {{
            "affinity_score": 72,
            "worth_applying": true,
            "critique_notes": "Initial score was correct. No missed blockers found.",
            "score_changed": false
        }}
    ]
}}"""

        try:
            result = await self._call_provider_json(provider, "critique", system_prompt, user_prompt)
        except Exception as exc:
            logger.warning("[CRITIQUE] LLM critique call failed: %s. Returning initial results.", exc)
            return initial_results

        critique_rows = result.get("results", []) if isinstance(result, dict) else []
        updated_results: List[Dict[str, Any]] = []

        for i, init in enumerate(initial_results):
            critique = critique_rows[i] if i < len(critique_rows) and isinstance(critique_rows[i], dict) else {}
            if not critique:
                updated_results.append(init)
                continue

            try:
                new_score = max(0, min(100, int(critique.get("affinity_score", init["affinity_score"]))))
            except Exception:
                new_score = init["affinity_score"]

            # Only accept score changes that are within ±20; otherwise keep original
            score_delta = abs(new_score - init["affinity_score"])
            if score_delta > 20:
                logger.debug("[CRITIQUE] Job %d: score change %d→%d exceeds ±20 cap; clamping.", i+1, init["affinity_score"], new_score)
                if new_score > init["affinity_score"]:
                    new_score = init["affinity_score"] + 20
                else:
                    new_score = init["affinity_score"] - 20
                new_score = max(0, min(100, new_score))

            critique_notes = sanitize_prompt_text(str(critique.get("critique_notes") or ""), max_chars=500)
            updated = dict(init)
            updated["affinity_score"] = new_score
            updated["worth_applying"] = bool(critique.get("worth_applying", False)) and new_score >= 65
            if critique_notes:
                # Append critique notes to the existing analysis (truncated to keep total under limit)
                existing_analysis = updated.get("affinity_analysis", "")
                if critique_notes and critique_notes.lower() not in existing_analysis.lower():
                    combined = f"{existing_analysis}\n\n[Critique] {critique_notes}"
                    updated["affinity_analysis"] = combined[:2000]
            updated_results.append(updated)

        # Pad if model returned fewer rows
        while len(updated_results) < len(initial_results):
            updated_results.append(initial_results[len(updated_results)])

        return updated_results

    # ─── Phase 3.4: Comparative re-ranking of top-N jobs ─────────────────────

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
            jobs_text += f"\n--- JOB {i+1} (current score: {entry.get('current_score')}) ---\n"
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
            result = await self._call_provider_json(provider, "rerank", system_prompt, user_prompt)
        except Exception as exc:
            logger.warning("[RERANK] LLM rerank call failed: %s. Returning original scores.", exc)
            return [
                {"job_index": e.get("job_index", i), "final_score": e.get("current_score", 0)}
                for i, e in enumerate(top_jobs)
            ]

        rerank_rows = result.get("results", []) if isinstance(result, dict) else []
        output: List[Dict[str, Any]] = []

        for i, entry in enumerate(top_jobs):
            row = rerank_rows[i] if i < len(rerank_rows) and isinstance(rerank_rows[i], dict) else {}
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

            output.append({
                "job_index": entry.get("job_index", i),
                "final_score": final_score,
                "rank_notes": sanitize_prompt_text(str(row.get("rank_notes") or ""), max_chars=300),
            })

        # Pad missing entries
        while len(output) < len(top_jobs):
            entry = top_jobs[len(output)]
            output.append({"job_index": entry.get("job_index", len(output)), "final_score": entry.get("current_score", 0)})

        return output


llm_service = LLMService()
