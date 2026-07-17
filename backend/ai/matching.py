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


class MatchingMixin:
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def analyze_job_batch(
        self,
        jobs_metadata: List[Dict[str, Any]],
        profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        provider = self._get_provider("match")
        runtime_policy = self.get_step_runtime_policy("match")

        system_prompt = (
            "You are a strict, evidence-driven career coach AI. "
            "Evaluate candidate-job fit conservatively using BOTH the candidate's CV profile AND their stated search intent. "
            "The candidate may intentionally search outside their CV domain — score based on the INTENT, not just the CV. "
            "For cross-domain candidates, assess transferable skills explicitly. "
            "Cite the main reasons, never invent qualifications. "
            "Return results in the EXACT SAME ORDER as the jobs were given."
        )

        import asyncio as _asyncio

        match_desc_limit = max(400, int(runtime_policy.get("description_limit_chars") or 1800))
        descriptions = await _asyncio.gather(
            *[
                self._compress_description_if_needed(job.get("description") or "", match_desc_limit)
                for job in jobs_metadata
            ]
        )

        jobs_text = ""
        for i, (job, desc) in enumerate(zip(jobs_metadata, descriptions)):
            jobs_text += f"\n--- JOB {i + 1} ---\n"
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
                    from backend.search.normalization.listings import infer_implicit_language

                    implicit_lang = infer_implicit_language(job.get("location"))
                    if implicit_lang:
                        jobs_text += f"[Implicit Language Hint] Location suggests primary language: {implicit_lang} — consider this when scoring language fit.\n"
                except Exception:
                    pass

        strategy = profile.get("search_strategy")
        strategy_block = f"\n- Extra AI Instructions / Preferences: {strategy}" if strategy else ""
        compact_profile_snapshot = sanitize_prompt_text(
            profile.get("match_profile_snapshot") or "",
            max_chars=(
                int(
                    getattr(
                        settings,
                        "SEARCH_LOW_CONTEXT_PROFILE_SNAPSHOT_MAX_CHARS",
                        700,
                    )
                    or 700
                )
                if runtime_policy.get("low_context")
                else int(getattr(settings, "SEARCH_PROFILE_SNAPSHOT_MAX_CHARS", 1000) or 1000)
            ),
        )

        # Build structured profile context from normalized data
        profile_norm = profile.get("profile_normalization") or {}
        candidate_structured = ""
        intent_structured = ""
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
            dealbreakers = profile_norm.get("dealbreakers") or []
            flexibility = profile_norm.get("flexibility") or {}
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

        if compact_profile_snapshot:
            strategy_block = ""
            candidate_structured = ""
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
                    signal_lines.append(
                        f"- Preferred domains (user has applied to): {', '.join(preferred_domains[:3])}"
                    )
                if avoided_domains:
                    signal_lines.append(
                        f"- Domains user consistently dismisses (treat as soft negative): {', '.join(avoided_domains[:3])}"
                    )
                if preferred_role_types:
                    signal_lines.append(
                        f"- Preferred role types: {', '.join(preferred_role_types)}"
                    )
                if preferred_skills:
                    signal_lines.append(
                        f"- Skills the user actively engages with: {', '.join(preferred_skills)}"
                    )
                if dealbreaker_patterns:
                    top_reasons = sorted(dealbreaker_patterns.items(), key=lambda x: -x[1])[:3]
                    signal_lines.append(
                        f"- Frequent dismissal reasons: {', '.join(f'{r}({c})' for r, c in top_reasons)}"
                    )
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

        candidate_context = compact_profile_snapshot or sanitize_prompt_text(
            profile.get("cv_summary") or profile.get("cv_content") or "",
            max_chars=1400,
        )

        user_prompt = f"""Analyze the match between this candidate and each job below.

CANDIDATE PROFILE:
- Expected Role: {profile.get("role_description")}{strategy_block}
    - Experience Context: {candidate_context}{candidate_structured}

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
12. PENALTY PRIORITY CHAIN: When multiple caps apply simultaneously, use the LOWEST (most restrictive) cap. Priority order from most to least restrictive: DEALBREAKER (cap 20) → USER INSTRUCTIONS (cap 20) → LANGUAGE MISMATCH (cap 30) → EDUCATION MISMATCH (cap 40). Never average caps — always take the strictest.
13. RED FLAG SCORE IMPACT: Each CRITICAL red flag (unrealistic_requirements, discriminatory_language) reduces `affinity_score` by 5 pts AFTER all other caps are applied.

DIMENSIONAL SCORING RUBRICS (0–100 each):
- `skill_match_score`: 85–100 = ≥80% required skills covered; 60–84 = 50–79% covered; 30–59 = 25–49% covered; 0–29 = <25% covered. For manual/service roles with no listed technical skills, default to 70 if candidate has general relevant experience.
- `experience_match_score`: 90–100 = experience years within job's stated range; 65–89 = within ±2 yrs of job minimum; 40–64 = 3–5 yr gap; 0–39 = >5 yr gap or completely wrong seniority.
- `intent_match_score`: 90–100 = job role title + domain + seniority ALL match stated intent; 65–89 = 2/3 match; 40–64 = 1/3 match or partial; 0–39 = job contradicts stated intent.
- `language_match_score`: 100 = all required languages covered; 60–99 = most languages covered but minor gap; 0–59 = a required language is missing entirely.
- `location_match_score`: 100 = remote or within preferred location; 60–99 = hybrid or commutable; 0–59 = on-site only far from candidate or contradicts remote preference.
- `transferability_score`: 90–100 = multiple high-value transferable skills explicitly apply; 60–89 = some transferable skills apply; 30–59 = weak transferability; 0–29 = no transferable skills apply.
- `qualification_gap_score`: 100 = candidate's qualification is relevant and sufficient; 60–99 = slight over/under-qualification; 0–59 = major qualification mismatch for THIS specific job.

DIMENSIONAL SCORING: Produce sub-scores (0-100 each) following the rubrics above:
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

        result = await self._call_provider_json(
            provider,
            "match",
            system_prompt,
            user_prompt,
            expected_rows=len(jobs_metadata),
        )
        results = result.get("results", []) if isinstance(result, dict) else []
        normalized_results: List[Dict[str, Any]] = []

        for item in results[: len(jobs_metadata)]:
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
                    "verdict": sanitize_prompt_text(
                        str(raw_structured.get("verdict") or ""), max_chars=250
                    ),
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
                    "affinity_analysis": sanitize_prompt_text(
                        item.get("affinity_analysis", ""), max_chars=1500
                    )
                    or "No analysis returned.",
                    "worth_applying": worth_applying,
                    "skill_match_score": _coerce_sub_score(item.get("skill_match_score")),
                    "experience_match_score": _coerce_sub_score(item.get("experience_match_score")),
                    "intent_match_score": _coerce_sub_score(item.get("intent_match_score")),
                    "language_match_score": _coerce_sub_score(item.get("language_match_score")),
                    "location_match_score": _coerce_sub_score(item.get("location_match_score")),
                    "transferability_score": _coerce_sub_score(item.get("transferability_score")),
                    "qualification_gap_score": _coerce_sub_score(
                        item.get("qualification_gap_score")
                    ),
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
            jobs_text += f"\n--- JOB {i + 1} ---\n"
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
                f"\nJOB {i + 1} INITIAL SCORE: {init.get('affinity_score')}\n"
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
            result = await self._call_provider_json(
                provider,
                "critique",
                system_prompt,
                user_prompt,
                expected_rows=len(jobs_metadata),
            )
        except Exception as exc:
            logger.warning(
                "[CRITIQUE] LLM critique call failed: %s. Returning initial results.", exc
            )
            return initial_results

        critique_rows = result.get("results", []) if isinstance(result, dict) else []
        updated_results: List[Dict[str, Any]] = []

        for i, init in enumerate(initial_results):
            critique = (
                critique_rows[i]
                if i < len(critique_rows) and isinstance(critique_rows[i], dict)
                else {}
            )
            if not critique:
                updated_results.append(init)
                continue

            try:
                new_score = max(
                    0, min(100, int(critique.get("affinity_score", init["affinity_score"])))
                )
            except Exception:
                new_score = init["affinity_score"]

            # Only accept score changes that are within ±20; otherwise keep original
            score_delta = abs(new_score - init["affinity_score"])
            if score_delta > 20:
                logger.debug(
                    "[CRITIQUE] Job %d: score change %d→%d exceeds ±20 cap; clamping.",
                    i + 1,
                    init["affinity_score"],
                    new_score,
                )
                if new_score > init["affinity_score"]:
                    new_score = init["affinity_score"] + 20
                else:
                    new_score = init["affinity_score"] - 20
                new_score = max(0, min(100, new_score))

            critique_notes = sanitize_prompt_text(
                str(critique.get("critique_notes") or ""), max_chars=500
            )
            updated = dict(init)
            updated["affinity_score"] = new_score
            updated["worth_applying"] = (
                bool(critique.get("worth_applying", False)) and new_score >= 65
            )
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
