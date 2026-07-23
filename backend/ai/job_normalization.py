"""Domain slice extracted from the local AI compatibility pipeline."""

# ruff: noqa: F401

import asyncio
import logging
from typing import Any, Dict, List, Optional

from tenacity import RetryError

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


class JobNormalizationMixin:
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
        """Build a deterministic compact description excerpt for LLM prompts.

        This replaces the old LLM-based compression pass. It keeps explicit
        requirement-heavy fragments locally so prompt size stays predictable even
        for small-context models and no extra tokens are spent on compression.
        """
        return compact_prompt_text(description, max_chars)

    async def normalize_job_batch(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize unstructured job payloads into deterministic filtering fields."""
        if not jobs:
            return []

        import asyncio as _asyncio

        provider = self._get_provider("normalize")
        runtime_policy = self.get_step_runtime_policy("normalize")
        normalize_desc_limit = max(
            500,
            int(runtime_policy.get("description_limit_chars") or 2400),
        )
        descriptions = await _asyncio.gather(
            *[
                self._compress_description_if_needed(
                    job.get("description") or "", normalize_desc_limit
                )
                for job in jobs
            ]
        )

        jobs_text = ""
        for i, (job, desc) in enumerate(zip(jobs, descriptions)):
            jobs_text += f"\n--- JOB {i + 1} ---\n"
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

        result = await self._call_provider_json(
            provider,
            "normalize",
            system_prompt,
            user_prompt,
            expected_rows=len(jobs),
        )
        rows = result.get("results", []) if isinstance(result, dict) else []
        normalized_rows: List[Dict[str, Any]] = []

        _valid_role_types = {
            "technical",
            "manual",
            "administrative",
            "creative",
            "managerial",
            "service",
            "professional",
        }

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
                    "role_family": str(
                        row.get("role_family") or row.get("title") or jobs[idx].get("title") or ""
                    ).strip()
                    or None,
                    "domain": self._normalize_job_domain_token(row.get("domain") or "general"),
                    "industry_sector": industry_sector,
                    "role_type": role_type,
                    "seniority": str(row.get("seniority") or "").strip().lower() or None,
                    "employment_mode": str(row.get("employment_mode") or "").strip().lower()
                    or None,
                    "contract_type": str(row.get("contract_type") or "").strip().lower() or None,
                    "qualification_level": str(row.get("qualification_level") or "").strip().lower()
                    or None,
                    "experience_min_years": self._coerce_nullable_int(
                        row.get("experience_min_years")
                    ),
                    "experience_max_years": self._coerce_nullable_int(
                        row.get("experience_max_years")
                    ),
                    "workload_min": self._coerce_nullable_int(row.get("workload_min")),
                    "workload_max": self._coerce_nullable_int(row.get("workload_max")),
                    "salary_min_chf": self._coerce_nullable_int(row.get("salary_min_chf")),
                    "salary_max_chf": self._coerce_nullable_int(row.get("salary_max_chf")),
                    "required_languages": self._normalize_required_languages(
                        row.get("required_languages")
                    ),
                    "required_skills": self._dedupe_string_list(row.get("required_skills")),
                    "preferred_skills": self._dedupe_string_list(row.get("preferred_skills")),
                    "soft_skills": self._dedupe_string_list(row.get("soft_skills")),
                    "physical_requirements": self._dedupe_string_list(
                        row.get("physical_requirements")
                    ),
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
                    len(indices_needing_review),
                    len(normalized_rows),
                    indices_needing_review,
                )
        except Exception as _ve:
            logger.warning("[NORMALIZE] normalization_validator call failed: %s", _ve)

        return normalized_rows
