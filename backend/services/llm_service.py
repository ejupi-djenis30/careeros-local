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

    # ─── Step 1: Search Plan Generation ───────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_search_plan(
        self,
        profile: Dict[str, Any],
        providers_info: List[Any],
        max_queries: int | None = None,
    ) -> List[Dict[str, Any]]:
        provider = get_provider_for_step("plan")
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

        result = provider.generate_json(system_prompt, user_prompt)
        searches = result.get("searches", [])

        # Application-side enforcement of the limit just in case LLM goes over
        if max_queries is not None:
            searches = searches[:max_queries]

        return searches

    # ─── Step 3: Combined Title Relevance & Job Match Analysis ──────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def analyze_job_match(
        self,
        job_metadata: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        provider = get_provider_for_step("match")

        system_prompt = (
            "You are a strict and precise Career Coach AI. "
            "Your goal is to evaluate the match between a candidate's profile "
            "and a specific job listing. Be realistic and data-driven."
        )

        user_prompt = f"""Analyze the match between this profile and job.

PROFILE:
- Expected Role: {profile.get('role_description')}
- Experience Context: {profile.get('cv_content')}

JOB METADATA:
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

        return provider.generate_json(system_prompt, user_prompt)


llm_service = LLMService()
