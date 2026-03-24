import logging
from typing import Dict, Any, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from backend.providers.llm.factory import get_provider_for_step
from backend.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Orchestrates all LLM calls for the job-hunting pipeline.

    Each method resolves its own provider via ``get_provider_for_step``
    so that different steps can transparently use different models/providers.
    """

    def __init__(self):
        self._provider_cache: Dict[str, Any] = {}

    def _get_provider(self, step: str):
        if step not in self._provider_cache:
            self._provider_cache[step] = get_provider_for_step(step)
        return self._provider_cache[step]

    def clear_provider_cache(self):
        """Force reload of all LLM providers (e.g. if config changes)."""
        self._provider_cache.clear()

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
        
        system_prompt = "You are an expert HR Analyst. Extract key information from a CV into a structured summary that downstream AI matchers will use to assess job fit."
        user_prompt = f"""Summarize this CV into a compact, clearly structured text (max 250 words).
CRITICAL: You MUST explicitly list the following details:
1. Highest Education Level (e.g., No Degree, Bachelor's, Master's, PhD)
2. Languages Spoken (with proficiency levels)
3. Total Years of Experience & Seniority Level (Junior, Mid, Senior, Lead)
4. Core Technical Skills & Tools
5. Past Job Titles Held

CV:
{cv_content}

Return plain text, NOT JSON. Use bullet points for readability."""
        
        return await provider.generate_text_async(system_prompt, user_prompt)

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
            "You are a permissive job relevance pre-filter. Your goal is to KEEP jobs "
            "that could potentially be relevant and ONLY discard jobs that are clearly "
            "and obviously unrelated to the candidate's target role. When in doubt, "
            "mark as relevant (true)."
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
- Mark as TRUE if the job is in a related field and could reasonably match the candidate's skills.
- Mark as FALSE ONLY if the job is clearly in a completely different field (e.g., "Nurse" for a "Software Developer").
- When in doubt, ALWAYS mark as TRUE — the next analysis step will do a deeper evaluation with the full description.

Return ONLY JSON: {{"results": [true, false, true]}}
One boolean per job, in order. true = relevant, false = irrelevant."""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        results = result.get("results", [])
        # Safety: pad if LLM returned too few, truncate if too many
        while len(results) < len(jobs):
            results.append(True)  # Default: keep when in doubt
        return results[:len(jobs)]

    # ─── Step 1: Search Plan Generation ───────────────────────────────────

    async def generate_search_plan(
        self,
        profile: Dict[str, Any],
        providers_info: List[Any],
        max_queries: Optional[int] = None,
        max_occupation_queries: Optional[int] = None,
        max_keyword_queries: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Generate the search plan with optional strict occupation/keyword count enforcement.
        
        When max_occupation_queries or max_keyword_queries are specified, the LLM
        is prompted to generate EXACTLY those counts. The result is validated and
        the LLM is called again up to 3 times if counts don't match. On 4th attempt
        (after 3 failures) the result is accepted as-is.
        """
        # Determine if we need strict type enforcement
        strict_types = (max_occupation_queries is not None) or (max_keyword_queries is not None)
        
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_generate_search_plan(
        self,
        profile: Dict[str, Any],
        providers_info: List[Any],
        max_queries: Optional[int] = None,
        max_occupation_queries: Optional[int] = None,
        max_keyword_queries: Optional[int] = None,
        attempt: int = 0,
    ) -> List[Dict[str, Any]]:
        """Internal method: single LLM call to generate the search plan."""
        provider = self._get_provider("plan")
        logger.info(f"[PLAN] Using {provider.model_id} (attempt {attempt + 1})")

        system_prompt = (
            "You are an expert Job Hunter AI specialized in the Swiss job market. "
            "You are fluent in English, German, French, and Italian. "
            "Your task is to generate HIGHLY DETAILED and COMPREHENSIVE search queries "
            "to find the best possible job matches for the user."
        )

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
                f"Generate at most {max_queries} queries total. "
                "Prioritize the most relevant occupation queries first."
            )

        retry_note = ""
        if attempt > 0:
            retry_note = (
                f"\n\nCRITICAL: This is retry attempt {attempt + 1}. "
                "Your previous response did NOT match the required query counts. "
                "You MUST strictly adhere to the count requirements this time."
            )

        user_prompt = f"""Analyze the user's profile and generate an optimal search plan.
You do NOT need to assign queries to specific job boards — the system routes them automatically.

PROFILE:
- Role / What they are looking for: {profile.get('role_description')}
- Strategy / AI Instructions: {profile.get('search_strategy')}
- CV Summary: {profile.get('cv_content')}

QUERY GENERATION RULES:
1. DOMAIN TAGGING: For each query, specify its professional domain (e.g. "it", "finance", "medical", "engineering", "hospitality", "general"). The system uses this to route queries to the right job boards.
2. NO "OR" OPERATORS: Never use "OR" or any other boolean operator in the query field.
3. ONE OCCUPATION PER QUERY: Each query must contain ONLY ONE specific job title/occupation.
4. QUERY TYPES:
   - "occupation": Exactly ONE occupation title, translated. No keywords in this type.
   - "keyword": A single specific skill, tool, action verb, or core competency (e.g. for IT: "React", for non-IT/general: "pulire", "trasportare", "customer service").
5. DIVERSITY & ACCURACY:
   - Use synonyms and different languages (DE, FR, EN, IT) to maximize coverage.
   - Ensure queries are distinct and high-quality.

{limit_instruction}{retry_note}

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
        searches = result.get("searches", [])

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
            "You are a strict, precise, and highly analytical Career Coach AI. "
            "Your goal is to evaluate the match between a candidate's profile "
            "and MULTIPLE job listings using data-driven hard constraints. "
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

Return ONLY JSON with a "results" array, one entry per job, IN ORDER:
{{
    "results": [
        {{"relevant": true, "affinity_score": 85, "affinity_analysis": "...", "worth_applying": true}},
        {{"relevant": false, "affinity_score": 10, "affinity_analysis": "...", "worth_applying": false}}
    ]
}}"""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        return result.get("results", [])


llm_service = LLMService()
