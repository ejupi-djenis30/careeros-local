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


class ProfileNormalizationMixin:
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

        return await self._call_provider_text(provider, "plan", system_prompt, user_prompt)

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

        result = await self._call_provider_json(
            provider, "normalize_profile", system_prompt, user_prompt
        )

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

        _valid_role_types = {
            "technical",
            "manual",
            "administrative",
            "creative",
            "managerial",
            "service",
            "professional",
        }
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
        intent_seniority = (
            intent_seniority_raw
            if intent_seniority_raw in {"junior", "mid", "senior"}
            else seniority
        )

        # Seniority range
        _all_seniorities = {"junior", "mid", "senior"}
        seniority_min_raw = str(si.get("target_seniority_min") or "").strip().lower()
        intent_seniority_min = (
            seniority_min_raw if seniority_min_raw in _all_seniorities else intent_seniority
        )

        seniority_max_raw = str(si.get("target_seniority_max") or "").strip().lower()
        intent_seniority_max = (
            seniority_max_raw if seniority_max_raw in _all_seniorities else intent_seniority
        )

        intent_role_family = str(si.get("target_role_family") or role_family or "").strip() or None

        intent_ql_raw = str(si.get("target_qualification_level") or "").strip().lower()
        intent_qualification_level = (
            intent_ql_raw if intent_ql_raw in ql_valid else qualification_level
        )

        intent_skills = self._dedupe_string_list(si.get("target_skills"))

        intent_role_type_raw = str(si.get("target_role_type") or "").strip().lower()
        intent_role_type = (
            intent_role_type_raw if intent_role_type_raw in _valid_role_types else None
        )

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
