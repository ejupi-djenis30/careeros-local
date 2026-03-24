import asyncio
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from backend.models import ScrapedJob, Job, SearchProfile
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.services.llm_service import llm_service
from backend.services.search.search_validator import build_search_request
from backend.services.utils import geocode_location, calculate_distance
from backend.core.config import settings
from backend.services.search_status import (
    init_status, add_log, update_status,
)

# Providers imports for 9b540b5 structure
from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
try:
    from backend.providers.jobs.adecco.client import AdeccoProvider
except ImportError:
    AdeccoProvider = None

logger = logging.getLogger(__name__)


class SearchService:
    """Orchestrates the entire multi-step job search pipeline (Feature 1 & 4)."""

    def __init__(self, db: Session = None, job_repo=None, profile_repo=None):
        self.db = db
        self.job_repo = job_repo or (JobRepository(db) if db else None)
        self.profile_repo = profile_repo or (ProfileRepository(db) if db else None)
        # Providers (registered by domain)
        self.providers = {
            "job_room": JobRoomProvider(),
            "swissdevjobs": SwissDevJobsProvider(),
        }
        if AdeccoProvider:
            self.providers["adecco"] = AdeccoProvider()

    async def run_search(self, profile_id: int):
        """High-level entry point to execute a search for a specific profile (Feature 1)."""
        profile = self.profile_repo.get(profile_id)
        if not profile:
            logger.error(f"[SEARCH] Profile {profile_id} not found.")
            return

        logger.info(f"[SEARCH] Starting run for profile {profile_id}: '{profile.name}'")
        init_status(profile_id)
        add_log(profile_id, f"Starting search for profile: {profile.name}")
        
        # 1. Generate Search Plan (Feature 4 + Caching Layer Feature 3)
        add_log(profile_id, "Step 1: Generating/Retrieving search plan...")
        searches = await self._get_search_plan(profile)
        if not searches:
            add_log(profile_id, "No search queries generated. Skipping.")
            update_status(profile_id, state="done")
            return

        update_status(profile_id, total_searches=len(searches), searches_generated=searches)

        # 2. Execute Scrapers
        add_log(profile_id, f"Step 2: Executing {len(searches)} scraper queries...")
        raw_jobs = await self._execute_scrapers(searches, profile, profile_id)
        if not raw_jobs:
             add_log(profile_id, "No new jobs found.")
             update_status(profile_id, state="done")
             return

        # 3. Deduplication & Cross-Profile Match (Feature 2)
        add_log(profile_id, "Step 3: Deduplicating and checking cross-profile status...")
        new_jobs = await self._deduplicate_and_filter(raw_jobs, profile)
        if not new_jobs:
            add_log(profile_id, "All found jobs are already in profile history.")
            update_status(profile_id, state="done")
            return

        update_status(profile_id, jobs_found=len(raw_jobs), jobs_new=len(new_jobs))

        # 4. Phase 1: Relevance Pre-filter (LLM)
        add_log(profile_id, f"Step 4: Phase 1 Relevance Filter ({len(new_jobs)} jobs)...")
        relevant_jobs = await self._filter_relevance(new_jobs, profile, profile_id)
        if not relevant_jobs:
            add_log(profile_id, "No relevant jobs passed Phase 1 filter.")
            update_status(profile_id, state="done")
            return

        # 5. Phase 2: Detailed Analysis & Job Match (LLM)
        add_log(profile_id, f"Step 5: Phase 2 Detailed Analysis and Match ({len(relevant_jobs)} jobs)...")
        update_status(profile_id, state="analyzing")
        await self._analyze_and_save(relevant_jobs, profile, profile_id)

        add_log(profile_id, f"Search completed. Found {len(relevant_jobs)} relevant jobs.")
        update_status(profile_id, state="done", finished_at=datetime.now(timezone.utc).isoformat())

    # --- Step 1: Search Plan (Feature 4 & 3) ---

    async def _get_search_plan(self, profile: SearchProfile) -> List[Dict[str, Any]]:
        if profile.cached_queries:
            try:
                queries = json.loads(profile.cached_queries)
                logger.info(f"[SEARCH] Using cached plan for profile {profile.id}")
                return queries
            except Exception as e:
                logger.error(f"[SEARCH] Failed to parse cached queries: {e}")

        plan = await llm_service.generate_search_plan(
            profile={
                "role_description": profile.role_description,
                "search_strategy": profile.search_strategy,
                "cv_content": profile.cv_content,
            },
            providers_info=[p.get_provider_info() for p in self.providers.values()],
            max_queries=profile.max_queries,
            max_occupation_queries=profile.max_occupation_queries,
            max_keyword_queries=profile.max_keyword_queries,
        )

        try:
             self.profile_repo.update(profile, {"cached_queries": json.dumps(plan)})
        except Exception as e:
             logger.error(f"[SEARCH] Failed to update query cache: {e}")

        return plan

    # --- Step 2: Scrapers ---

    async def _execute_scrapers(self, searches: List[Dict[str, Any]], profile: SearchProfile, profile_id: int) -> List[Dict[str, Any]]:
        all_jobs = []
        seen_urls = set()
        
        semaphore = asyncio.Semaphore(settings.SEARCH_CONCURRENCY)

        async def run_query(idx: int, query_cfg: Dict[str, Any]):
            async with semaphore:
                query = query_cfg.get("query")
                provider_name = query_cfg.get("provider", "job_room").lower()
                if provider_name == "swissdevjobs": provider_name = "swissdevjobs" # ensure exact key
                
                update_status(profile_id, current_search_index=idx + 1, current_query=f"{provider_name}: {query}")
                add_log(profile_id, f"Running query {idx+1}: {query} on {provider_name}")
                
                p = self.providers.get(provider_name)
                if not p:
                    add_log(profile_id, f"Provider {provider_name} not available. Skipping.")
                    return []
                
                try:
                    request = build_search_request(profile, query)
                    # SwissDevJobs and others use 'search' method
                    result = await p.search(request)
                    
                    found = []
                    for it in result.items:
                        # Convert JobListing pydantic to dict
                        found.append(it.model_dump() if hasattr(it, 'model_dump') else it.__dict__)
                    
                    add_log(profile_id, f"Found {len(found)} results for query {idx+1}")
                    return found
                except Exception as e:
                    logger.error(f"[SEARCH] Provider error for query {query!r}: {e}")
                    add_log(profile_id, f"Error on query {idx+1}: {str(e)}")
                    return []

        results = await asyncio.gather(*(run_query(i, q) for i, q in enumerate(searches)))
        
        for batch in results:
            for job in batch:
                url = job.get("external_url") or job.get("url")
                if url and url not in seen_urls:
                    # Feature 4: Tracking source query
                    # job is a dict now
                    job["_source_query"] = "unknown" # will be set properly if needed
                    all_jobs.append(job)
                    seen_urls.add(url)
                    
        return all_jobs

    # --- Step 3: Deduplication & Feature 2 (Cross-Profile Applied) ---

    async def _deduplicate_and_filter(self, raw_jobs: List[Dict[str, Any]], profile: SearchProfile) -> List[Dict[str, Any]]:
        user_id = profile.user_id
        user_known_jobs = self.job_repo.get_user_job_identifiers(user_id)
        
        # identifiers: (platform, platform_job_id, external_url, title, company)
        applied_scraped_ids = self.job_repo.get_applied_scraped_job_ids(user_id)
        profile_known_urls = {j[2] for j in self.job_repo.get_profile_job_identifiers(profile.id)}

        to_process = []
        for rj in raw_jobs:
            url = rj.get("external_url") or rj.get("url")
            if url in profile_known_urls:
                continue

            platform = rj.get("source") or rj.get("platform")
            pid = str(rj.get("id") or rj.get("platform_job_id"))

            db_job = self.job_repo.get_by_platform_id(platform, pid)
            if not db_job:
                 db_job = self.job_repo.get_by_external_url(url)
            
            scraped_job_id = None
            applied_elsewhere = False
            
            if db_job and db_job.scraped_job_id:
                scraped_job_id = db_job.scraped_job_id
                if scraped_job_id in applied_scraped_ids:
                    applied_elsewhere = True

            rj["_scraped_job_id"] = scraped_job_id
            rj["_applied_elsewhere"] = applied_elsewhere
            to_process.append(rj)

        return to_process

    # --- Step 4: Phase 1 Relevance (Feature 1) ---

    async def _filter_relevance(self, jobs: List[Dict[str, Any]], profile: SearchProfile, profile_id: int) -> List[Dict[str, Any]]:
        if not jobs: return []

        BATCH_SIZE = 20
        relevant_jobs = []

        for i in range(0, len(jobs), BATCH_SIZE):
            batch = jobs[i : i + BATCH_SIZE]
            llm_batch = []
            for j in batch:
                title = j.get("title")
                company = j.get("company")
                if isinstance(company, dict): company = company.get("name")
                
                desc = ""
                descs = j.get("descriptions", [])
                if descs and isinstance(descs, list):
                    desc = descs[0].get("description", "") if isinstance(descs[0], dict) else getattr(descs[0], 'description', "")
                
                llm_batch.append({
                    "title": title,
                    "company": company,
                    "description_snippet": desc[:300]
                })
            
            try:
                results = await llm_service.check_relevance_batch(
                    llm_batch,
                    role_description=profile.role_description,
                    search_strategy=profile.search_strategy
                )
                
                for job, is_relevant in zip(batch, results):
                    if is_relevant:
                        relevant_jobs.append(job)
            except Exception as e:
                logger.error(f"[SEARCH] Relevance filter error: {e}")
                relevant_jobs.extend(batch)

        return relevant_jobs

    # --- Step 5: Phase 2 Analysis & Save ---

    async def _analyze_and_save(self, jobs: List[Dict[str, Any]], profile: SearchProfile, profile_id: int):
        if llm_service.is_summary_step_configured():
             await self._perform_summarization(jobs, profile_id)

        BATCH_SIZE = settings.ANALYSIS_BATCH_SIZE
        semaphore = asyncio.Semaphore(settings.ANALYSIS_CONCURRENCY)

        origin_coords = None
        if profile.latitude and profile.longitude:
             origin_coords = (profile.latitude, profile.longitude)

        async def process_batch(idx: int, batch: List[Dict[str, Any]]):
            async with semaphore:
                for j in batch:
                    # Distance calculation
                    dist = None
                    try:
                        loc = j.get("location")
                        lat, lon = None, None
                        if loc and isinstance(loc, dict):
                            lat, lon = loc.get("latitude"), loc.get("longitude")
                        
                        if (not lat or not lon) and loc:
                            loc_str = loc.get("city") if isinstance(loc, dict) else str(loc)
                            if loc_str:
                                coords = await geocode_location(loc_str)
                                if coords:
                                    lat, lon = coords.lat, coords.lon
                        
                        if lat and lon and origin_coords:
                             dist = calculate_distance(origin_coords, (lat, lon))
                    except: pass
                    j["_distance_km"] = dist

                # LLM Match Analysis
                try:
                    llm_batch = []
                    for j in batch:
                        comp_name = j.get("company")
                        if isinstance(comp_name, dict): comp_name = comp_name.get("name")
                        
                        full_desc = ""
                        descs = j.get("descriptions", [])
                        if descs:
                            full_desc = "\n".join([d.get("description") if isinstance(d, dict) else d.description for d in descs])
                        
                        llm_batch.append({
                            "title": j.get("title"),
                            "company": comp_name,
                            "description": full_desc
                        })

                    results = await llm_service.analyze_job_batch(
                        jobs_metadata=llm_batch,
                        profile={
                            "role_description": profile.role_description,
                            "cv_summary": profile.cached_cv_summary,
                            "cv_content": profile.cv_content,
                            "search_strategy": profile.search_strategy
                        }
                    )
                    
                    for job_data, result in zip(batch, results):
                        self._save_job_result(job_data, result, profile)
                except Exception as e:
                    logger.error(f"[SEARCH] Analysis batch error: {e}")

        tasks = [process_batch(i, jobs[i : i + BATCH_SIZE]) for i in range(0, len(jobs), BATCH_SIZE)]
        await asyncio.gather(*tasks)

    async def _perform_summarization(self, jobs: List[Dict[str, Any]], profile_id: int):
        add_log(profile_id, "Enriching jobs with AI summaries...")
        BATCH_SIZE = 5
        for i in range(0, len(jobs), BATCH_SIZE):
            batch = jobs[i : i + BATCH_SIZE]
            llm_batch = []
            for j in batch:
                full_desc = ""
                descs = j.get("descriptions", [])
                if descs:
                     full_desc = "\n".join([d.get("description") if isinstance(d, dict) else d.description for d in descs])
                llm_batch.append({"title": j.get("title"), "description": full_desc})
            
            try:
                summaries = await llm_service.summarize_job_batch(llm_batch)
                for job, summary in zip(batch, summaries):
                    job["_summary"] = summary
            except Exception as e:
                logger.error(f"[SEARCH] Job summarization error: {e}")

    def _save_job_result(self, job_data: Dict[str, Any], analysis: Dict[str, Any], profile: SearchProfile):
        scraped_job_id = job_data.get("_scraped_job_id")
        platform = job_data.get("source") or job_data.get("platform")
        platform_job_id = str(job_data.get("id") or job_data.get("platform_job_id"))

        if not scraped_job_id:
            existing = self.db.query(ScrapedJob).filter(
                ScrapedJob.platform == platform,
                ScrapedJob.platform_job_id == platform_job_id
            ).first()
            
            if existing:
                scraped_job_id = existing.id
            else:
                comp_name = job_data.get("company")
                if isinstance(comp_name, dict): comp_name = comp_name.get("name")
                
                loc = job_data.get("location")
                loc_str = loc.get("city") if isinstance(loc, dict) else str(loc)
                
                full_desc = ""
                descs = job_data.get("descriptions", [])
                if descs:
                     full_desc = "\n".join([d.get("description") if isinstance(d, dict) else d.description for d in descs])

                new_scraped = ScrapedJob(
                    platform=platform,
                    platform_job_id=platform_job_id,
                    title=job_data.get("title"),
                    company=comp_name or "Unknown",
                    description=full_desc,
                    location=loc_str,
                    external_url=job_data.get("external_url") or job_data.get("url"),
                    workload=job_data.get("workload"),
                    publication_date=job_data.get("created_at") or job_data.get("publication_date"),
                    summary=job_data.get("_summary"),
                    source_query=job_data.get("_source_query")
                )
                self.db.add(new_scraped)
                self.db.flush()
                scraped_job_id = new_scraped.id

        new_job = Job(
            user_id=profile.user_id,
            search_profile_id=profile.id,
            scraped_job_id=scraped_job_id,
            is_scraped=True,
            affinity_score=analysis.get("affinity_score", 0),
            affinity_analysis=analysis.get("affinity_analysis", ""),
            worth_applying=analysis.get("worth_applying", False),
            distance_km=job_data.get("_distance_km"),
            applied=job_data.get("_applied_elsewhere", False)
        )
        self.db.add(new_job)
        self.db.commit()


def get_search_service(db: Session) -> SearchService:
    return SearchService(db)
