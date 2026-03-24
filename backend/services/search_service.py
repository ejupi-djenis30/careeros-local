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
from backend.services.utils import geocode_location, calculate_distance, haversine_distance, clean_html_tags
from backend.core.config import settings

from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
try:
    from backend.providers.jobs.adecco.client import AdeccoProvider
except ImportError:
    AdeccoProvider = None
from backend.providers.jobs.localdb.client import LocalDbProvider
from backend.providers.jobs.models import JobSearchRequest, SortOrder, RadiusSearchRequest, Coordinates
from backend.providers.jobs.jobroom.avam_mapper import avam_mapper
from backend.services.search_status import (
    init_status, add_log, update_status, clear_status, get_status, register_task, unregister_task
)

logger = logging.getLogger(__name__)


STOP_STATES = {"stopped", "cancelled", "finished", "failed"}


def get_query_fingerprint(query: str) -> str:
    import re

    query = query.lower()
    noise_words = r'\b(m/w/d|f/m/d|m/f/d|100%|80%|80-100%)\b'
    query = re.sub(noise_words, ' ', query)
    query = re.sub(r'[^\w\s+C#]', ' ', query)
    tokens = [token.strip() for token in query.split() if token.strip()]
    return " ".join(sorted(tokens))


# ─────────────────────── Domain Router ───────────────────────

def get_compatible_providers(
    query_domain: str,
    providers: Dict[str, Any],
    provider_infos: Dict[str, Any],
) -> List[str]:
    """Return provider names whose accepted_domains match the query domain.
    
    Rules:
    - "*" in accepted_domains → accepts everything (generalist)
    - query_domain in accepted_domains → exact domain match
    - query_domain == "general" → only generalist providers
    """
    compatible = []
    for name, info in provider_infos.items():
        domains = info.accepted_domains
        if "*" in domains or query_domain in domains:
            compatible.append(name)
    return compatible


class SearchService:
    """Orchestrates the entire multi-step job search pipeline (Feature 1 & 4)."""

    def __init__(self, db: Session = None, job_repo=None, profile_repo=None):
        if db is not None and not isinstance(db, Session) and job_repo is not None and profile_repo is None:
            profile_repo = job_repo
            job_repo = db
            db = None

        self.db = db or getattr(job_repo, "db", None) or getattr(profile_repo, "db", None)
        self.job_repo = job_repo or (JobRepository(db) if db else None)
        self.profile_repo = profile_repo or (ProfileRepository(db) if db else None)
        # Providers (registered by domain)
        self.providers = {
            "job_room": JobRoomProvider(),
            "swissdevjobs": SwissDevJobsProvider(),
            "local_db": LocalDbProvider(self.db) if self.db else None
        }
        if AdeccoProvider:
            self.providers["adecco"] = AdeccoProvider()

    async def run_search(self, profile_id: int):
        """Run the full search workflow for a saved profile."""
        register_task(profile_id, asyncio.current_task())
        
        # Ensure fresh LLM providers (reload config)
        llm_service.clear_provider_cache()

        try:
            profile = self.profile_repo.get(profile_id)
            if not profile:
                logger.error(f"Profile {profile_id} not found")
                return

            profile_dict = {
                "id": profile.id,
                "user_id": profile.user_id,
                "cv_content": profile.cv_content or "",
                "role_description": profile.role_description or "",
                "search_strategy": profile.search_strategy or "",
                "latitude": profile.latitude,
                "longitude": profile.longitude,
                # Feature 3: force-regeneration flags (propagated from the HTTP request)
                "force_regenerate_cv_summary": getattr(profile, "_force_regenerate_cv_summary", False),
                "force_regenerate_queries": getattr(profile, "_force_regenerate_queries", False),
            }
            user_id = profile.user_id

            # ── Step 1: Initialize status immediately ──
            init_status(profile_id, user_id=user_id)
            add_log(profile_id, "Step 1: Generating/Retrieving search plan...")

            provider_infos = {
                name: p.get_provider_info() for name, p in self.providers.items() if p
            }

            searches = await self._generate_plan(profile_id, profile_dict, profile, provider_infos)
            if not searches:
                update_status(profile_id, state="done")
                return

            # ── CV Summary (with caching Feature 3) ──
            cv_summary = ""
            if profile_dict.get("cv_content"):
                force_regen_cv = profile_dict.get("force_regenerate_cv_summary", False)
                if profile.cached_cv_summary and not force_regen_cv:
                    cv_summary = profile.cached_cv_summary
                    add_log(profile_id, "✓ Using cached CV summary")
                else:
                    try:
                        cv_summary = await llm_service.summarize_cv(profile_dict["cv_content"])
                        add_log(profile_id, "CV summary generated for efficient analysis")
                        # Save to cache
                        self.profile_repo.update(profile, {"cached_cv_summary": cv_summary})
                    except Exception as e:
                        logger.warning(f"CV summarization failed: {e}")
                        cv_summary = profile_dict["cv_content"]
            profile_dict["cv_summary"] = cv_summary

            # ── Step 2: Execute searches with domain routing (Feature 4) ──
            update_status(profile_id, state="searching")
            add_log(profile_id, f"Step 2: Executing scraper queries...")
            all_jobs = await self._execute_searches(profile_id, profile, searches, provider_infos)
            if not all_jobs:
                add_log(profile_id, "No jobs found across all queries.")
                update_status(profile_id, state="done")
                return

            # ── Step 3: Deduplication & Feature 2 (Cross-Profile Applied) ──
            add_log(profile_id, "Step 3: Deduplicating and checking cross-profile status...")
            unique_jobs, duplicates = self._deduplicate(profile, all_jobs)
            add_log(profile_id, f"After dedup: {len(unique_jobs)} new, {duplicates} duplicates")
            
            if not unique_jobs:
                add_log(profile_id, "All found jobs are already in profile history.")
                update_status(profile_id, state="done")
                return

            # ── Step 3.5: Job Summary Generation (Feature 1 — opt-in) ──
            if llm_service.is_summary_step_configured():
                unique_jobs = await self._summarize_jobs(profile_id, unique_jobs)
            
            # ── Step 3.6: Relevance Pre-Filter (cheap LLM check Feature 1) ──
            add_log(profile_id, f"Step 4: Phase 1 Relevance Filter ({len(unique_jobs)} jobs)...")
            filtered_jobs = await self._relevance_filter(profile_id, profile_dict, unique_jobs)
            add_log(profile_id, f"Relevance filter: {len(filtered_jobs)} relevant out of {len(unique_jobs)}")
            
            skipped_by_relevance = len(unique_jobs) - len(filtered_jobs)
            unique_jobs = filtered_jobs

            if not unique_jobs:
                add_log(profile_id, "No relevant jobs passed Phase 1 filter.")
                update_status(profile_id, state="done")
                return

            update_status(
                profile_id,
                state="analyzing",
                jobs_found=len(all_jobs),
                jobs_new=len(unique_jobs),
                jobs_duplicates=duplicates,
                jobs_skipped=skipped_by_relevance,
            )

            # ── Step 4: Analyze & save each unique job (Parallel) ──
            add_log(profile_id, f"Step 5: Phase 2 Detailed Analysis and Match ({len(unique_jobs)} jobs)...")
            saved_count, skipped_count = await self._analyze_and_save(profile_id, profile_dict, unique_jobs)

            add_log(profile_id, f"✓ Search complete – {saved_count} jobs saved, {skipped_count} skipped")
            update_status(
                profile_id,
                state="done",
                finished_at=datetime.now(timezone.utc).isoformat(),
                jobs_found=len(all_jobs),
                jobs_new=saved_count,
                jobs_duplicates=duplicates,
                jobs_skipped=skipped_count
            )
        except Exception as e:
            logger.error(f"Unexpected error in run_search for profile {profile_id}: {e}", exc_info=True)
            update_status(profile_id, state="error", error=f"Unexpected error: {e}")
        finally:
            for provider_name, provider in self.providers.items():
                if not provider:
                    continue

                try:
                    if hasattr(provider, "close"):
                        close_result = provider.close()
                        if asyncio.iscoroutine(close_result):
                            await close_result
                        continue

                    session = getattr(provider, "_session", None)
                    if session and hasattr(session, "aclose"):
                        close_result = session.aclose()
                        if asyncio.iscoroutine(close_result):
                            await close_result
                except Exception as close_error:
                    logger.warning("Failed to close provider %s cleanly: %s", provider_name, close_error)

            unregister_task(profile_id)

    # ───────────────────────── helper methods ─────────────────────────

    async def _generate_plan(self, profile_id: int, profile_dict: dict, profile, provider_infos) -> list:
        # Feature 3: check cached queries
        force_regen_q = profile_dict.get("force_regenerate_queries", False)
        
        if profile.cached_queries and not force_regen_q:
            try:
                if isinstance(profile.cached_queries, str):
                    searches = json.loads(profile.cached_queries)
                else:
                    searches = profile.cached_queries
                add_log(profile_id, f"✓ Using {len(searches)} cached queries")
            except Exception as e:
                logger.error(f"Failed to parse cached queries: {e}")
                searches = []
        else:
            searches = []

        if not searches:
            try:
                searches = await llm_service.generate_search_plan(
                    profile_dict, list(provider_infos.values()),
                    max_queries=profile.max_queries,
                    max_occupation_queries=profile.max_occupation_queries,
                    max_keyword_queries=profile.max_keyword_queries,
                )
            except Exception as e:
                logger.error(f"LLM keyword generation failed: {e}")
                update_status(profile_id, state="error", error=str(e))
                return []
            
            if not searches:
                return []
            
            # Save queries to cache (Feature 3)
            try:
                self.profile_repo.update(profile, {"cached_queries": json.dumps(searches)})
            except Exception as e:
                logger.warning(f"Failed to cache queries: {e}")

        unique_searches = []
        seen_queries = set()
        for s in searches:
            q_str = s.get("query", "").strip()
            if not q_str:
                continue
                
            fingerprint = get_query_fingerprint(q_str)
            if fingerprint not in seen_queries:
                seen_queries.add(fingerprint)
                unique_searches.append(s)

        # Update status with the actual plan details
        update_status(
            profile_id,
            total_searches=len(unique_searches),
            searches_generated=unique_searches
        )
        add_log(profile_id, f"Generated {len(searches)} queries → {len(unique_searches)} unique")
        if profile.max_queries and len(unique_searches) < profile.max_queries:
            add_log(
                profile_id,
                f"⚠ Requested {profile.max_queries} queries but only {len(unique_searches)} unique queries were available after validation/deduplication",
            )
        return unique_searches

    async def _execute_searches(self, profile_id: int, profile, searches: list, provider_infos) -> list:
        all_jobs: list = []
        execution_mode = (settings.SEARCH_EXECUTION_MODE or "sequential").strip().lower()
        query_concurrency = settings.SEARCH_CONCURRENCY if execution_mode == "immediate" else 1
        semaphore = asyncio.Semaphore(max(1, query_concurrency))
        provider_parallel = execution_mode == "immediate"
        add_log(profile_id, f"Execution mode: {execution_mode}")

        async def execute_single_search(idx: int, search: dict):
            async with semaphore:
                # Real-time stop check
                status_data = get_status(profile_id)
                if status_data.get("state") in STOP_STATES:
                    return []
                    
                query = search.get("query", "")
                domain = search.get("domain", "general")
                query_type = search.get("type", "keyword")
                
                profession_codes = []
                avam_fallback_keyword = False
                if query_type == "occupation":
                    profession_codes = await avam_mapper.resolve(query)
                    if not profession_codes:
                        avam_fallback_keyword = True
                        add_log(profile_id, f"  ℹ AVAM found no codes for «{query}», JobRoom will use keyword fallback")

                compatible = get_compatible_providers(domain, self.providers, provider_infos)
                if not compatible:
                    add_log(profile_id, f"⚠ No providers accept domain '{domain}' for «{query}»")
                    return []

                # Update status
                update_status(profile_id, current_search_index=idx + 1, current_query=f"«{query}» ({domain})")
                add_log(profile_id, f"Running query {idx+1}/{len(searches)}: «{query}» on {', '.join(compatible)}")

                request = build_search_request(profile, query, profession_codes)

                async def search_provider(provider_name: str, req: JobSearchRequest):
                    provider = self.providers[provider_name]
                    if not provider: return provider_name, [], None
                    
                    provider_jobs = []
                    try:
                        current_page = 0
                        while True:
                            page_size = 50
                            if hasattr(provider, "capabilities") and hasattr(provider.capabilities, "max_page_size"):
                                page_size = provider.capabilities.max_page_size
                                
                            page_req = req.model_copy(update={"page": current_page, "page_size": page_size})
                            result = await provider.search(page_req)
                            page_items = list(getattr(result, "items", []) or [])
                            
                            for item in page_items:
                                # Mark the source query for tracking
                                if hasattr(item, "_source_query"):
                                    item._source_query = query
                                else:
                                    setattr(item, "_source_query", query)
                            
                            provider_jobs.extend(page_items)

                            if not page_items:
                                break
                            
                            total_pages = getattr(result, "total_pages", 1)
                            total_count = getattr(result, "total_count", None)
                            if total_pages and current_page >= total_pages - 1:
                                break
                            if total_count is not None and total_count >= 0 and len(provider_jobs) >= total_count:
                                break
                                
                            current_page += 1
                            
                            if provider_name == "adecco":
                                await asyncio.sleep(1.0) # Throttling
                                
                            # Abort check
                            status_data = get_status(profile_id)
                            if status_data.get("state") in STOP_STATES:
                                break
                                
                        return provider_name, provider_jobs, None
                    except Exception as e:
                        return provider_name, provider_jobs, e

                p_tasks = []
                for p_name in compatible:
                    if p_name == "job_room" and avam_fallback_keyword:
                        req_fallback = build_search_request(profile, query, [])
                        p_tasks.append(search_provider(p_name, req_fallback))
                    else:
                        p_tasks.append(search_provider(p_name, request))

                if provider_parallel:
                    p_results = await asyncio.gather(*p_tasks)
                else:
                    p_results = []
                    for task in p_tasks:
                        p_results.append(await task)

                found_jobs = []
                for p_name, items, error in p_results:
                    if error:
                        add_log(profile_id, f"  ⚠ {p_name} failed: {str(error)[:100]}")
                    else:
                        found_jobs.extend(items)
                        add_log(profile_id, f"  ↳ {p_name}: {len(items)} jobs")
                
                return found_jobs

        results = await asyncio.gather(*(execute_single_search(i, q) for i, q in enumerate(searches)))
        
        seen_urls = set()
        for batch in results:
            for job in batch:
                url = getattr(job, "external_url", None) or getattr(job, "url", None) or str(getattr(job, "id", ""))
                if url and url not in seen_urls:
                    all_jobs.append(job)
                    seen_urls.add(url)
                    
        return all_jobs

    def _deduplicate(self, profile, all_jobs: list) -> tuple[list, int]:
        import re

        profile_id = getattr(profile, "id", profile)
        
        def get_fuzzy_key(title: str, company: str) -> str:
            t = re.sub(r'[^\w\s]', '', (title or "").lower()).strip()
            c = re.sub(r'[^\w\s]', '', (company or "").lower()).strip()
            return f"{t}::{c}"
            
        seen_keys: set = set()
        seen_fuzzy_keys: set = set()
        unique_jobs: list = []
        
        existing_identifiers = self.job_repo.get_profile_job_identifiers(profile_id)
        profile_user_id = getattr(profile, "user_id", None)
        applied_scraped_ids = (
            self.job_repo.get_applied_scraped_job_ids(profile_user_id)
            if profile_user_id is not None
            else set()
        )
        
        existing_keys = {
            f"{row.platform}:{row.platform_job_id}" for row in existing_identifiers
            if row.platform and row.platform_job_id
        }
        existing_urls = {row.external_url for row in existing_identifiers if row.external_url}
        existing_fuzzy_keys = {
            get_fuzzy_key(row.title, row.company) for row in existing_identifiers
            if getattr(row, "title", None) and getattr(row, "company", None)
        }

        for listing in all_jobs:
            platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
            platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))
            
            key = f"{platform}:{platform_id}"
            url = getattr(listing, "external_url", None) or getattr(listing, "url", None) or platform_id
            
            title = getattr(listing, "title", "Unknown")
            company_obj = getattr(listing, "company", None)
            company_name = company_obj.name if hasattr(company_obj, "name") else (company_obj if isinstance(company_obj, str) else "Unknown")
            
            fuzzy_key = get_fuzzy_key(title, company_name)
            
            if (platform and platform_id and (key in seen_keys or key in existing_keys)) or \
               (url and (url in existing_urls and key not in existing_keys)):
                   continue
            
            if fuzzy_key and fuzzy_key != "::" and (fuzzy_key in existing_fuzzy_keys or fuzzy_key in seen_fuzzy_keys):
                continue
                   
            if platform and platform_id:
                seen_keys.add(key)
            if url:
                existing_urls.add(url)
            if fuzzy_key and fuzzy_key != "::":
                seen_fuzzy_keys.add(fuzzy_key)
            
            # Feature 2 check: applied elsewhere
            applied_elsewhere = False
            # We don't have scraped_job_id yet for new jobs, so we check by platform_id
            from backend.models import ScrapedJob
            existing_sj = self.db.query(ScrapedJob).filter(
                ScrapedJob.platform == platform,
                ScrapedJob.platform_job_id == platform_id
            ).first()
            if existing_sj and existing_sj.id in applied_scraped_ids:
                applied_elsewhere = True
            
            setattr(listing, "_applied_elsewhere", applied_elsewhere)
            unique_jobs.append(listing)
                
        duplicates = len(all_jobs) - len(unique_jobs)
        return unique_jobs, duplicates

    async def _summarize_jobs(self, profile_id: int, jobs: list, batch_size: int = 10) -> list:
        add_log(profile_id, f"Summarizing job descriptions for {len(jobs)} jobs…")
        
        jobs_needing_summary = []
        from backend.models import ScrapedJob
        
        for job in jobs:
            platform = getattr(job, "source", None) or getattr(job, "platform", "")
            job_id = str(getattr(job, "id", "") or getattr(job, "platform_job_id", ""))
            
            existing_sj = self.db.query(ScrapedJob).filter(
                ScrapedJob.platform == platform,
                ScrapedJob.platform_job_id == job_id
            ).first()
            
            if existing_sj and existing_sj.summary:
                setattr(job, "_summary", existing_sj.summary)
            else:
                jobs_needing_summary.append(job)
        
        if not jobs_needing_summary:
            return jobs
        
        add_log(profile_id, f"  Generating {len(jobs_needing_summary)} new summaries…")
        
        for i in range(0, len(jobs_needing_summary), batch_size):
            batch = jobs_needing_summary[i:i + batch_size]
            batch_data = []
            for j in batch:
                desc = ""
                descs = getattr(j, "descriptions", [])
                if descs:
                    desc = descs[0].description if hasattr(descs[0], "description") else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")
                
                batch_data.append({
                    "title": getattr(j, "title", "Unknown"),
                    "company": getattr(j, "company").name if hasattr(getattr(j, "company", None), "name") else "Unknown",
                    "description": desc[:2000],
                })
            
            try:
                summaries = await llm_service.summarize_job_batch(batch_data)
                for j, summary_text in zip(batch, summaries):
                    setattr(j, "_summary", summary_text)
            except Exception as e:
                logger.warning(f"Job summary batch failed: {e}")
        
        return jobs

    async def _relevance_filter(self, profile_id: int, profile_dict: dict, jobs: list, batch_size: int = 20) -> list:
        relevant_jobs = []
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            batch_data = []
            for j in batch:
                summary = getattr(j, "_summary", None)
                if not summary:
                    descs = getattr(j, "descriptions", [])
                    if descs:
                        summary = descs[0].description[:150] if hasattr(descs[0], "description") else (descs[0].get("description", "")[:150] if isinstance(descs[0], dict) else "")
                
                batch_data.append({
                    "title": getattr(j, "title", "Unknown"),
                    "company": getattr(j, "company").name if hasattr(getattr(j, "company", None), "name") else "Unknown",
                    "description_snippet": summary or "",
                })
            try:
                results = await llm_service.check_relevance_batch(
                    batch_data,
                    profile_dict.get("role_description", ""),
                    search_strategy=profile_dict.get("search_strategy", ""),
                )
                for j, is_relevant in zip(batch, results):
                    if is_relevant:
                        relevant_jobs.append(j)
            except Exception as e:
                logger.warning(f"Relevance filter failed: {e}")
                relevant_jobs.extend(batch)
        
        return relevant_jobs

    async def _analyze_and_save(self, profile_id: int, profile_dict: dict, unique_jobs: list) -> tuple[int, int]:
        semaphore = asyncio.Semaphore(settings.ANALYSIS_CONCURRENCY)
        batch_size = settings.ANALYSIS_BATCH_SIZE
        batches = [unique_jobs[i:i+batch_size] for i in range(0, len(unique_jobs), batch_size)]

        origin_coords = None
        if profile_dict.get("latitude") and profile_dict.get("longitude"):
             origin_coords = (profile_dict["latitude"], profile_dict["longitude"])

        async def analyze_batch(batch):
            async with semaphore:
                status_data = get_status(profile_id)
                if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
                    return 0
                    
                jobs_metadata = []
                for job in batch:
                    desc_text = ""
                    descs = getattr(job, "descriptions", [])
                    if descs:
                        desc_text = descs[0].description if hasattr(descs[0], "description") else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")

                    education_info = []
                    for occ in getattr(job, "occupations", []):
                        if getattr(occ, "education_code", None):
                            education_info.append(f"Edu: {occ.education_code}")
                            
                    company_obj = getattr(job, "company", None)
                    company_name = company_obj.name if hasattr(company_obj, "name") else "Unknown"

                    jobs_metadata.append({
                        "title": getattr(job, "title", "Unknown"),
                        "description": desc_text[:settings.MAX_DESCRIPTION_CHARS],
                        "location": job.location.city if getattr(job, "location", None) else "Unknown",
                        "workload": f"{job.employment.workload_min}-{job.employment.workload_max}%" if getattr(job, "employment", None) else "Unknown",
                        "languages": [f"{s.language_code} ({s.spoken_level})" for s in getattr(job, "language_skills", [])] if getattr(job, "language_skills", None) else [],
                        "education": ", ".join(education_info) if education_info else "None specified",
                        "company": company_name,
                    })
                
                try:
                    results = await llm_service.analyze_job_batch(jobs_metadata, profile_dict)
                    
                    saved = 0
                    for job, analysis in zip(batch, results):
                        if analysis.get("relevant", True):
                            await self._save_single_job(job, analysis, profile_dict, origin_coords)
                            saved += 1
                    return saved
                except Exception as e:
                    logger.error(f"Analysis batch failed: {e}")
                    return 0

        tasks = [analyze_batch(batch) for batch in batches]
        results = await asyncio.gather(*tasks)
        
        saved_count = sum(results)
        skipped_count = len(unique_jobs) - saved_count
        return saved_count, skipped_count

    async def _save_single_job(self, listing, analysis, profile_dict, origin_coords):
        platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
        platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))
        
        # 1. ScrapedJob (or fetch existing)
        existing_sj = self.db.query(ScrapedJob).filter(
            ScrapedJob.platform == platform,
            ScrapedJob.platform_job_id == platform_id
        ).first()

        desc_text = ""
        descs = getattr(listing, "descriptions", [])
        if descs:
            desc_text = descs[0].description if hasattr(descs[0], "description") else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")

        company_obj = getattr(listing, "company", None)
        company_name = company_obj.name if hasattr(company_obj, "name") else "Unknown"
        location_str = listing.location.city if getattr(listing, "location", None) else ""
        
        workload_str = ""
        if getattr(listing, "employment", None):
            wmin = listing.employment.workload_min
            wmax = listing.employment.workload_max
            workload_str = f"{wmin}-{wmax}%" if wmin != wmax else f"{wmin}%"

        pub_date = None
        if getattr(listing, "publication", None) and listing.publication.start_date:
            try:
                date_raw = listing.publication.start_date
                if "T" in date_raw:
                    pub_date = datetime.fromisoformat(date_raw.replace('Z', '+00:00'))
                else:
                    pub_date = datetime.strptime(date_raw, "%Y-%m-%d")
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Failed to parse publication date %r for %s/%s: %s",
                    listing.publication.start_date,
                    platform,
                    platform_id,
                    exc,
                )

        if not existing_sj:
            existing_sj = ScrapedJob(
                platform=platform,
                platform_job_id=platform_id,
                title=clean_html_tags(getattr(listing, "title", "Unknown")),
                company=company_name,
                description=clean_html_tags(desc_text) if desc_text else None,
                location=location_str,
                external_url=getattr(listing, "external_url", None) or getattr(listing, "url", None) or platform_id,
                application_url=getattr(listing, "application", None).form_url if getattr(listing, "application", None) else None,
                application_email=getattr(listing, "application", None).email if getattr(listing, "application", None) else None,
                workload=workload_str or None,
                publication_date=pub_date,
                source_query=getattr(listing, "_source_query", "Unknown"),
                summary=getattr(listing, "_summary", None),
            )
            self.db.add(existing_sj)
            self.db.flush()
        elif getattr(listing, "_summary", None) and not existing_sj.summary:
            existing_sj.summary = getattr(listing, "_summary", None)

        # 2. Distance
        distance_km = None
        if origin_coords and getattr(listing, "location", None):
            # Try to geocode if no coords
            coords = getattr(listing.location, "coordinates", None)
            if not coords and location_str:
                coords = await geocode_location(location_str)
                if coords:
                    logger.info("Resolved missing coordinates for %s via geocoding fallback", location_str)
                else:
                    logger.warning(
                        "Could not resolve coordinates for %s/%s with location %r",
                        platform,
                        platform_id,
                        location_str,
                    )
            
            if coords:
                distance_km = haversine_distance(
                    origin_coords[0], origin_coords[1],
                    coords.lat, coords.lon
                )

        # 3. Job (Link)
        new_job = Job(
            user_id=profile_dict["user_id"],
            search_profile_id=profile_dict["id"],
            scraped_job_id=existing_sj.id,
            is_scraped=True,
            affinity_score=analysis.get("affinity_score", 0),
            affinity_analysis=analysis.get("affinity_analysis", ""),
            worth_applying=analysis.get("worth_applying", False),
            distance_km=distance_km,
            applied=getattr(listing, "_applied_elsewhere", False)
        )
        self.db.add(new_job)
        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.error(
                "Failed to persist job %s/%s for profile %s: %s",
                platform,
                platform_id,
                profile_dict.get("id"),
                exc,
            )
            raise


def get_search_service(db: Session) -> SearchService:
    return SearchService(db)
