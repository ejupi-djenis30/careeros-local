import logging
from typing import Dict, Any, List
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

    # ─── New Phase 2 Helpers: CV Summary & Relevance Pre-filter ────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def summarize_cv(self, cv_content: str) -> str:
        """Produce a compact CV summary for downstream MATCH calls."""
        provider = self._get_provider("plan")
        
        system_prompt = "You are a CV summarizer. Distill a CV into key skills, experience, and qualifications."
        user_prompt = f"""Summarize this CV into a compact bullet-point format (max 200 words).
Focus on: job titles held, years of experience, core technical skills, languages spoken, education level.

CV:
{cv_content}

Return plain text, NOT JSON."""
        
        return await provider.generate_text_async(system_prompt, user_prompt)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def check_relevance_batch(
        self,
        jobs: List[Dict[str, str]],
        role_description: str,
    ) -> List[bool]:
        """Quick binary relevance check for a batch of job titles."""
        provider = self._get_provider("relevance")
        
        system_prompt = (
            "You are a job title relevance filter. Determine if each job title "
            "is relevant to the candidate's target role. Be inclusive — if there's "
            "a reasonable match, mark it relevant."
        )
        
        jobs_text = "\n".join(
            f'{i+1}. "{j["title"]}" at {j.get("company", "Unknown")}'
            for i, j in enumerate(jobs)
        )
        
        user_prompt = f"""TARGET ROLE: {role_description}

JOB TITLES:
{jobs_text}

Return ONLY JSON: {{"results": [true, false, true]}}
One boolean per job, in order. true = relevant, false = irrelevant."""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        return result.get("results", [True] * len(jobs))

    # ─── Step 1: Search Plan Generation ───────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_search_plan(
        self,
        profile: Dict[str, Any],
        providers_info: List[Any],
        max_queries: int | None = None,
    ) -> List[Dict[str, Any]]:
        provider = self._get_provider("plan")
        logger.info(f"[PLAN] Using {provider.model_id}")

        system_prompt = (
            "You are an expert Job Hunter AI specialized in the Swiss job market. "
            "You are fluent in English, German, French, and Italian. "
            "Your task is to generate HIGHLY DETAILED and COMPREHENSIVE search queries "
            "to find the best possible job matches for the user."
        )

        limit_instruction = (
            "Generate as MANY queries as needed to ensure comprehensive coverage. "
            "There is NO limit on the total number of queries."
            if max_queries is None
            else f"Generate at most {max_queries} queries total. "
                 "Prioritize the most relevant occupation queries first."
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
   - "keyword": A single specific skill or technology.
5. DIVERSITY & ACCURACY:
   - Use synonyms and different languages (DE, FR, EN) to maximize coverage.
   - Ensure queries are distinct and high-quality.

{limit_instruction}

Return ONLY pure JSON with a 'searches' list. Example:
{{
    "searches": [
        {{"domain": "it", "language": "en", "type": "occupation", "query": "Software Engineer"}},
        {{"domain": "it", "language": "de", "type": "keyword", "query": "React"}},
        {{"domain": "finance", "language": "en", "type": "occupation", "query": "Financial Analyst"}}
    ]
}}"""

        result = await provider.generate_json_async(system_prompt, user_prompt)
        searches = result.get("searches", [])

        # Application-side enforcement of the limit just in case LLM goes over
        if max_queries is not None:
            searches = searches[:max_queries]

        return searches

    # ─── Step 3: Combined Title Relevance & Job Match Analysis ──────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def analyze_job_match(
        self,
        job_metadata: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        provider = self._get_provider("match")

        system_prompt = (
            "You are a strict and precise Career Coach AI. "
            "Your goal is to evaluate the match between a candidate's profile "
            "and a specific job listing. Be realistic and data-driven."
        )

        user_prompt = f"""Analyze the match between this profile and job description.

PROFILE:
- Expected Role: {profile.get('role_description')}
- Experience Context: {profile.get('cv_summary') or profile.get('cv_content')}

JOB:
{job_metadata}

SCORING RULES:
1. RELEVANCE CHECK FIRST: Determine if the job title and general description are relevant to the requested role. If completely irrelevant, set "relevant" to false and you can skip detailed analysis.
2. SENIORITY MISMATCH: If the candidate is Junior/Entry-level and the job requires Senior/Lead/Staff/Principal (5+ years), the affinity_score MUST NOT exceed 50. You may still mark worth_applying as true if the candidate has most required skills.
3. MULTI-FACTOR: Consider title, full description, and all metadata (language requirements, workload) together.
4. STRICTNESS: Be realistic. Score 100 only for a perfect resume-to-job match.

Return ONLY JSON:
{{
    "relevant": true/false,
    "affinity_score": 0-100,
    "affinity_analysis": "Concise 2-3 sentence explanation focusing on why the score was given, mentioning seniority if applicable.",
    "worth_applying": true/false
}}"""

        return await provider.generate_json_async(system_prompt, user_prompt)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def analyze_job_batch(
        self,
        jobs_metadata: List[Dict[str, Any]],
        profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        provider = self._get_provider("match")

        system_prompt = (
            "You are a strict and precise Career Coach AI. "
            "Your goal is to evaluate the match between a candidate's profile "
            "and MULTIPLE job listings. Be realistic and data-driven. "
            "Return results in the EXACT SAME ORDER as the jobs were given."
        )

        jobs_text = ""
        for i, job in enumerate(jobs_metadata):
            jobs_text += f"\n--- JOB {i+1} ---\n"
            jobs_text += f"Title: {job.get('title')}\n"
            jobs_text += f"Company: {job.get('company')}\n"
            jobs_text += f"Location: {job.get('location')}\n"
            jobs_text += f"Workload: {job.get('workload')}\n"
            jobs_text += f"Description: {job.get('description')}\n"

        user_prompt = f"""Analyze the match between this profile and each job below.

PROFILE:
- Expected Role: {profile.get('role_description')}
- Experience Context: {profile.get('cv_summary') or profile.get('cv_content')}

{jobs_text}

SCORING RULES:
1. RELEVANCE CHECK FIRST: Check title and description. If altogether irrelevant, set "relevant" to false.
2. SENIORITY MISMATCH: Junior→Senior = cap at 50; Senior→Junior = cap at 70.
3. Score 0-100 realistically. Don't give 90+ unless it's a perfect match.
4. "worth_applying" should only be true if score >= 60 and relevant=true.

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
