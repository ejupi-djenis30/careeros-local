import logging
import asyncio
from typing import List, Any, Dict
from datetime import datetime
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.services.llm_service import llm_service
from backend.services.search.search_validator import build_search_request
from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
from backend.providers.jobs.adecco.client import AdeccoProvider
from backend.providers.jobs.localdb.client import LocalDbProvider
from backend.providers.jobs.models import JobSearchRequest, SortOrder, RadiusSearchRequest, Coordinates
from backend.models import Job
from backend.core.config import settings
from backend.providers.jobs.jobroom.avam_mapper import avam_mapper
from backend.services.search_status import (
    init_status, add_log, update_status, clear_status, get_status,
)
from backend.db.base import SessionLocal

logger = logging.getLogger(__name__)


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
    def __init__(self, job_repo: JobRepository, profile_repo: ProfileRepository):
        self.job_repo = job_repo
        self.profile_repo = profile_repo

    # ───────────────────────── public entry point ─────────────────────────

    async def run_search(self, profile_id: int):
        """Run the full search workflow for a saved profile."""
        from backend.services.search_status import register_task, unregister_task
        register_task(profile_id, asyncio.current_task())

        # Map available providers and their infos
        available_providers = {
            "job_room": JobRoomProvider(),
            "swissdevjobs": SwissDevJobsProvider(),
            "adecco": AdeccoProvider(),
            "local_db": LocalDbProvider(self.job_repo.db)
        }

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
            add_log(profile_id, "Generating search plan with AI…")

            provider_infos = {
                name: p.get_provider_info() for name, p in available_providers.items()
            }

            searches = await self._generate_plan(profile_id, profile_dict, profile, available_providers, provider_infos)
            if not searches:
                return

            # ── CV Summary (with caching) ──
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

            # ── Step 2: Execute searches with domain routing ──
            update_status(profile_id, state="searching")
            all_jobs = await self._execute_searches(profile_id, profile, searches, available_providers, provider_infos)
            if not all_jobs:
                return

            # ── Step 3: Deduplicate ──
            unique_jobs, duplicates = self._deduplicate(profile, all_jobs)
            add_log(profile_id, f"After dedup: {len(unique_jobs)} new, {duplicates} duplicates")

            # ── Step 3.5: Job Summary Generation (Feature 1 — opt-in) ──
            if llm_service.is_summary_step_configured():
                unique_jobs = await self._summarize_jobs(profile_id, unique_jobs)
            
            # ── Step 3.6: Relevance Pre-Filter (cheap LLM check) ──
            filtered_jobs = await self._relevance_filter(profile_id, profile_dict, unique_jobs)
            add_log(profile_id, f"Relevance filter: {len(filtered_jobs)} relevant out of {len(unique_jobs)}")
            
            skipped_by_relevance = len(unique_jobs) - len(filtered_jobs)
            unique_jobs = filtered_jobs

            update_status(
                profile_id,
                state="analyzing",
                jobs_found=len(all_jobs),
                jobs_new=len(unique_jobs),
                jobs_duplicates=duplicates,
                jobs_skipped=skipped_by_relevance,
            )

            # ── Step 4: Analyze & save each unique job (Parallel) ──
            saved_count, skipped_count = await self._analyze_and_save(profile_id, profile_dict, unique_jobs)

            add_log(profile_id, f"✓ Search complete – {saved_count} jobs saved, {skipped_count} skipped")
            update_status(
                profile_id,
                state="done",
                jobs_found=len(all_jobs),
                jobs_new=saved_count,
                jobs_duplicates=duplicates,
                jobs_skipped=skipped_count
            )
        except Exception as e:
            logger.error(f"Unexpected error in run_search for profile {profile_id}: {e}", exc_info=True)
            update_status(profile_id, state="error", error=f"Unexpected error: {e}")
        finally:
            # Close provider sessions to prevent connection leaks
            try:
                for provider in available_providers.values():
                    try:
                        if hasattr(provider, 'close'):
                            await provider.close()
                        elif hasattr(provider, '_session') and provider._session:
                            await provider._session.aclose()
                    except Exception:
                        pass
            except NameError:
                pass  # available_providers not yet defined
            unregister_task(profile_id)

    # ───────────────────────── helper methods ─────────────────────────

    async def _generate_plan(self, profile_id: int, profile_dict: dict, profile, available_providers, provider_infos) -> list:
        # Feature 3: check cached queries
        force_regen_q = profile_dict.get("force_regenerate_queries", False)
        
        if profile.cached_queries and not force_regen_q:
            searches = profile.cached_queries
            add_log(profile_id, f"✓ Using {len(searches)} cached queries")
        else:
            try:
                searches = await llm_service.generate_search_plan(
                    profile_dict, list(provider_infos.values()),
                    max_queries=profile.max_queries,
                    max_occupation_queries=getattr(profile, "max_occupation_queries", None),
                    max_keyword_queries=getattr(profile, "max_keyword_queries", None),
                )
            except Exception as e:
                logger.error(f"LLM keyword generation failed: {e}")
                update_status(profile_id, state="error", error=str(e))
                return []
            
            if not searches:
                add_log(profile_id, "No search keywords generated")
                update_status(profile_id, state="done", jobs_found=0, jobs_new=0)
                return []
            
            # Save queries to cache (Feature 3)
            try:
                self.profile_repo.update(profile, {"cached_queries": searches})
            except Exception as e:
                logger.warning(f"Failed to cache queries: {e}")

        def get_query_fingerprint(q: str) -> str:
            import re
            q = q.lower()
            noise_words = r'\b(m/w/d|f/m/d|m/f/d|100%|80%|80-100%)\\b'
            q = re.sub(noise_words, ' ', q)
            q = re.sub(r'[^\w\s+C#]', ' ', q) # keep +, # for C++, C#
            tokens = [t.strip() for t in q.split() if t.strip()]
            return " ".join(sorted(tokens))

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

        # Count total provider calls for progress tracking
        total_provider_calls = 0
        for s in unique_searches:
            domain = s.get("domain", "general")
            compatible = get_compatible_providers(domain, available_providers, provider_infos)
            total_provider_calls += len(compatible)

        # Update status with the actual plan details
        update_status(
            profile_id, 
            total_searches=total_provider_calls, 
            searches_generated=unique_searches
        )
        add_log(profile_id, f"Generated {len(searches)} queries → {len(unique_searches)} unique → {total_provider_calls} provider calls")
        return unique_searches

    async def _execute_searches(self, profile_id: int, profile, searches: list, available_providers, provider_infos) -> list:
        all_jobs: list = []

        # Limit the number of parallel query executions to avoid overwhelming providers
        semaphore = asyncio.Semaphore(settings.SEARCH_CONCURRENCY)

        async def execute_single_search(idx: int, search: dict):
            async with semaphore:
                # Real-time stop check using memory cache rather than DB reads
                status_data = get_status(profile_id)
                if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
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

                compatible = get_compatible_providers(domain, available_providers, provider_infos)
                if not compatible:
                    add_log(profile_id, f"⚠ No providers accept domain '{domain}' for «{query}»")
                    return []

                add_log(profile_id, f"[{idx+1}/{len(searches)}] «{query}» (domain={domain}) → {', '.join(compatible)}")

                request = build_search_request(profile, query, profession_codes)

                async def search_provider(provider_name: str, req: JobSearchRequest):
                    provider = available_providers[provider_name]
                    all_provider_jobs = []
                    max_pages = 100
                    try:
                        current_page = 0
                        while current_page < max_pages:
                            # Use model_copy to avoid concurrent modification bugs if providers run in parallel
                            page_size = provider.capabilities.max_page_size if hasattr(provider, "capabilities") and hasattr(provider.capabilities, "max_page_size") else 50
                            page_req = req.model_copy(update={"page": current_page, "page_size": page_size})
                            result = await provider.search(page_req)
                            all_provider_jobs.extend(result.items)
                            
                            total_pages = getattr(result, "total_pages", 1)
                            if current_page >= total_pages - 1:
                                break
                                
                            current_page += 1
                            
                            if provider_name == "adecco":
                                await asyncio.sleep(2.0)
                            
                            # Real-time abort check in between pages
                            status_data = get_status(profile_id)
                            if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
                                break
                                
                        return provider_name, all_provider_jobs, None
                    except Exception as e:
                        return provider_name, all_provider_jobs, e

                p_tasks = []
                for p_name in compatible:
                    if p_name == "job_room" and avam_fallback_keyword:
                        # JobRoom specifically: if occupation lookup failed, send keyword search
                        req_fallback = build_search_request(profile, query, [])
                        p_tasks.append(search_provider(p_name, req_fallback))
                    else:
                        # Standard request (with AVAM codes if they exist)
                        p_tasks.append(search_provider(p_name, request))

                p_results = await asyncio.gather(*p_tasks)

                found_jobs = []
                for p_name, items, error in p_results:
                    if error:
                        logger.warning(f"Search «{query}» on {p_name} failed: {error}")
                        add_log(profile_id, f"⚠ Search «{query}» on {p_name} failed: {error}")
                    else:
                        found_jobs.extend(items)
                        add_log(profile_id, f"  ↳ {p_name}: {len(items)} jobs  («{query}»)")
                
                return found_jobs

        # Execute all queries concurrently (bounded by semaphore)
        tasks = [execute_single_search(idx, search) for idx, search in enumerate(searches)]
        results = await asyncio.gather(*tasks)
        
        completed_calls = 0
        for batch in results:
            all_jobs.extend(batch)
            completed_calls += 1
            update_status(profile_id, current_search_index=completed_calls)

        if not all_jobs:
            add_log(profile_id, "No jobs found across all queries")
            update_status(profile_id, state="done", jobs_found=0, jobs_new=0)
            return []

        add_log(profile_id, f"Total raw results: {len(all_jobs)}")
        return all_jobs

    def _deduplicate(self, profile, all_jobs: list) -> tuple[list, int]:
        import re
        
        def get_fuzzy_key(title: str, company: str) -> str:
            t = re.sub(r'[^\w\s]', '', (title or "").lower()).strip()
            c = re.sub(r'[^\w\s]', '', (company or "").lower()).strip()
            return f"{t}::{c}"
            
        seen_keys: set = set()
        seen_fuzzy_keys: set = set()
        unique_jobs: list = []
        
        existing_identifiers = self.job_repo.get_profile_job_identifiers(profile.id)
        
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
            platform = getattr(listing, "source", "unknown")
            platform_id = str(getattr(listing, "id", ""))
            
            key = f"{platform}:{platform_id}"
            url = getattr(listing, "external_url", None) or getattr(listing, "url", None) or platform_id
            
            title = getattr(listing, "title", "Unknown")
            company = getattr(listing, "company").name if getattr(listing, "company", None) else "Unknown"
            fuzzy_key = get_fuzzy_key(title, company)
            
            # Match strictly by ID or URL
            if (platform and platform_id and (key in seen_keys or key in existing_keys)) or \
               (url and (url in existing_urls and key not in existing_keys)):
                   continue
            
            # Match fuzzily (same core title and same core company)
            if fuzzy_key and fuzzy_key != "::" and (fuzzy_key in existing_fuzzy_keys or fuzzy_key in seen_fuzzy_keys):
                continue
                   
            if platform and platform_id:
                seen_keys.add(key)
            if url:
                existing_urls.add(url)
            if fuzzy_key and fuzzy_key != "::":
                seen_fuzzy_keys.add(fuzzy_key)
                
            unique_jobs.append(listing)

        duplicates = len(all_jobs) - len(unique_jobs)
        return unique_jobs, duplicates

    async def _summarize_jobs(self, profile_id: int, jobs: list, batch_size: int = 10) -> list:
        """Feature 1: Generate and cache LLM summaries for jobs (opt-in step).
        
        Checks the DB for existing summaries on ScrapedJob. Only calls LLM for
        jobs without a cached summary. Saves new summaries back to ScrapedJob.
        Attaches the summary as a transient `_summary` attribute for downstream use.
        """
        add_log(profile_id, f"Summarizing job descriptions for {len(jobs)} jobs…")
        
        # Separate jobs that already have summaries from those that need generation
        jobs_needing_summary = []
        
        # Try to look up existing ScrapedJob summaries from DB
        from backend.models import ScrapedJob
        db_session = SessionLocal()
        try:
            job_ids = [str(getattr(job, "id", "")) for job in jobs]
            sources = [getattr(job, "source", "") for job in jobs]
            
            existing_scraped = db_session.query(ScrapedJob).filter(
                ScrapedJob.platform.in_(sources),
                ScrapedJob.platform_job_id.in_(job_ids)
            ).all()
            scraped_summary_map = {
                (sj.platform, sj.platform_job_id): sj.summary
                for sj in existing_scraped
                if sj.summary  # only those with summaries
            }
        except Exception as e:
            logger.warning(f"Could not load existing summaries: {e}")
            scraped_summary_map = {}
        finally:
            db_session.close()
        
        for job in jobs:
            source = getattr(job, "source", "")
            job_id = str(getattr(job, "id", ""))
            existing_summary = scraped_summary_map.get((source, job_id))
            if existing_summary:
                job._summary = existing_summary
            else:
                jobs_needing_summary.append(job)
        
        cached_count = len(jobs) - len(jobs_needing_summary)
        if cached_count > 0:
            add_log(profile_id, f"  ✓ {cached_count} jobs have cached summaries, generating {len(jobs_needing_summary)} new…")
        
        if not jobs_needing_summary:
            return jobs
        
        # Generate summaries for jobs that don't have them yet
        new_summaries: Dict[tuple, str] = {}
        
        for i in range(0, len(jobs_needing_summary), batch_size):
            batch = jobs_needing_summary[i:i + batch_size]
            job_data = []
            for j in batch:
                desc = ""
                if getattr(j, "descriptions", []):
                    desc = j.descriptions[0].description[:2000]
                job_data.append({
                    "title": getattr(j, "title", "Unknown"),
                    "company": getattr(j, "company").name if getattr(j, "company", None) else "Unknown",
                    "description": desc,
                })
            
            try:
                summaries = await llm_service.summarize_job_batch(job_data)
                for j, summary_text in zip(batch, summaries):
                    j._summary = summary_text
                    source = getattr(j, "source", "")
                    job_id = str(getattr(j, "id", ""))
                    new_summaries[(source, job_id)] = summary_text
            except Exception as e:
                logger.warning(f"Job summary batch failed: {e}. Using description snippets as fallback.")
                for j in batch:
                    desc = ""
                    if getattr(j, "descriptions", []):
                        desc = j.descriptions[0].description[:200]
                    j._summary = desc
        
        # Persist new summaries to DB
        if new_summaries:
            db_session = SessionLocal()
            try:
                for (source, job_id), summary_text in new_summaries.items():
                    db_session.query(ScrapedJob).filter(
                        ScrapedJob.platform == source,
                        ScrapedJob.platform_job_id == job_id,
                    ).update({"summary": summary_text}, synchronize_session=False)
                db_session.commit()
                add_log(profile_id, f"  ✓ Saved {len(new_summaries)} new job summaries to cache")
            except Exception as e:
                logger.warning(f"Failed to save job summaries to DB: {e}")
                db_session.rollback()
            finally:
                db_session.close()
        
        return jobs

    async def _relevance_filter(self, profile_id: int, profile_dict: dict, jobs: list, batch_size: int = 20) -> list:
        """Use cheap RELEVANCE LLM to filter obviously irrelevant jobs."""
        
        relevant_jobs = []
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            job_data = []
            for j in batch:
                # Use job summary if available (Feature 1), otherwise fall back to 150-char snippet
                summary = getattr(j, "_summary", None)
                if not summary and getattr(j, "descriptions", []) and j.descriptions:
                    summary = j.descriptions[0].description[:150]
                job_data.append({
                    "title": getattr(j, "title", "Unknown"),
                    "company": getattr(j, "company").name if getattr(j, "company", None) else "Unknown",
                    "description_snippet": summary or "",
                })
            try:
                results = await llm_service.check_relevance_batch(
                    job_data,
                    profile_dict.get("role_description", ""),
                    search_strategy=profile_dict.get("search_strategy", ""),
                )
                for j, is_relevant in zip(batch, results):
                    if is_relevant:
                        relevant_jobs.append(j)
                    else:
                        add_log(profile_id, f"  ✗ Filtered: {getattr(j, 'title', 'Unknown')}")
            except Exception as e:
                logger.warning(f"Relevance filter batch failed: {e}, keeping all jobs")
                relevant_jobs.extend(batch)
        
        return relevant_jobs

    async def _analyze_and_save(self, profile_id: int, profile_dict: dict, unique_jobs: list) -> tuple[int, int]:
        semaphore = asyncio.Semaphore(settings.ANALYSIS_CONCURRENCY)
        batch_size = settings.ANALYSIS_BATCH_SIZE

        # First, run the pure LLM analysis (batched)
        batches = [unique_jobs[i:i+batch_size] for i in range(0, len(unique_jobs), batch_size)]

        async def analyze_batch(batch, batch_idx, total_batches, start_idx):
            async with semaphore:
                status_data = get_status(profile_id)
                if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
                    return []
                    
                jobs_metadata = []
                for i, job in enumerate(batch):
                    title = getattr(job, "title", "Unknown")
                    add_log(profile_id, f"Analyzing {start_idx + i + 1}/{len(unique_jobs)}: {title}")
                    
                    # Always use the full description for analysis (not the summary)
                    desc_text = job.descriptions[0].description if getattr(job, "descriptions", []) else ""
                    if len(desc_text) > settings.MAX_DESCRIPTION_CHARS:
                        desc_text = desc_text[:settings.MAX_DESCRIPTION_CHARS] + "…"

                    education_info = []
                    for occ in getattr(job, "occupations", []):
                        if getattr(occ, "education_code", None):
                            education_info.append(f"Edu: {occ.education_code}")
                        if getattr(occ, "qualification_code", None):
                            education_info.append(f"Qual: {occ.qualification_code}")
                    education_str = ", ".join(education_info) if education_info else "None specified"

                    jobs_metadata.append({
                        "title": getattr(job, "title", "Unknown"),
                        "description": desc_text,  # Full description for deep analysis
                        "location": job.location.city if getattr(job, "location", None) else "Unknown",
                        "workload": f"{job.employment.workload_min}-{job.employment.workload_max}%" if getattr(job, "employment", None) else "Unknown",
                        "languages": [f"{s.language_code} ({s.spoken_level})" for s in getattr(job, "language_skills", [])] if getattr(job, "language_skills", None) else [],
                        "education": education_str,
                        "company": job.company.name if getattr(job, "company", None) else "Unknown",
                        "_original_desc": desc_text,
                    })
                
                try:
                    results = await llm_service.analyze_job_batch(
                        jobs_metadata, profile_dict
                    )
                    
                    valid = []
                    if len(results) != len(batch):
                        add_log(profile_id, f"⚠ Batch {batch_idx+1} result length mismatch (expect {len(batch)}, got {len(results)})")
                        return valid
                        
                    for job, meta, analysis in zip(batch, jobs_metadata, results):
                        if analysis.get("relevant", True):
                            valid.append((job, analysis, meta["_original_desc"]))
                    return valid
                except Exception as e:
                    add_log(profile_id, f"⚠ Failed analyzing batch {batch_idx+1}: {e}")
                    return []

        tasks = [analyze_batch(batch, i, len(batches), i * batch_size) for i, batch in enumerate(batches)]
        batch_results = await asyncio.gather(*tasks)
        
        # Flatten results and calculate jobs_analyzed progress
        analysis_results = []
        jobs_analyzed_count = 0
        for b_res in batch_results:
            analysis_results.extend(b_res)
            jobs_analyzed_count += settings.ANALYSIS_BATCH_SIZE
            update_status(profile_id, jobs_analyzed=min(jobs_analyzed_count, len(unique_jobs)), jobs_analyze_total=len(unique_jobs))
        
        # Now do the DB saving
        saved_count = 0
        skipped_count = len(unique_jobs) - len(analysis_results)
        
        # Pre-resolve geocoding for all valid jobs before entering synchronous DB block
        if profile_dict.get("latitude") is not None and profile_dict.get("longitude") is not None:
            from backend.services.utils import geocode_location
            
            cities_to_resolve = set()
            for job, analysis, desc_text in analysis_results:
                loc = getattr(job, "location", None)
                if loc and not loc.coordinates and loc.city:
                    cities_to_resolve.add(loc.city)
            
            if cities_to_resolve:
                import httpx
                async with httpx.AsyncClient() as shared_client:
                    resolved_coords = await asyncio.gather(*[geocode_location(c, shared_client) for c in cities_to_resolve])
                city_coords = dict(zip(cities_to_resolve, resolved_coords))
                
                for job, analysis, desc_text in analysis_results:
                    loc = getattr(job, "location", None)
                    if loc and not loc.coordinates and loc.city:
                        loc.coordinates = city_coords.get(loc.city)

        if analysis_results:
            from backend.models import ScrapedJob, Job
            from backend.services.utils import haversine_distance, clean_html_tags
            import datetime
            
            db_session = SessionLocal()
            try:
                # Pre-fetch existing ScrapedJobs
                job_ids = [str(job.id) for job, _, _ in analysis_results]
                sources = [job.source for job, _, _ in analysis_results]
                
                existing_scraped = db_session.query(ScrapedJob).filter(
                    ScrapedJob.platform.in_(sources),
                    ScrapedJob.platform_job_id.in_(job_ids)
                ).all()
                scraped_map = {(sj.platform, sj.platform_job_id): sj for sj in existing_scraped}

                new_scraped_jobs = []
                job_records = []

                for job, analysis, desc_text in analysis_results:
                    company = job.company.name if job.company else "Unknown"
                    location_str = job.location.city if getattr(job, "location", None) else ""
                    
                    workload_str = ""
                    if getattr(job, "employment", None):
                        wmin = job.employment.workload_min
                        wmax = job.employment.workload_max
                        workload_str = f"{wmin}-{wmax}%" if wmin != wmax else f"{wmin}%"

                    app_url = job.application.form_url if getattr(job, "application", None) else None
                    app_email = job.application.email if getattr(job, "application", None) else None

                    final_external_url = getattr(job, "external_url", None)
                    if not final_external_url and job.source == "job_room":
                        final_external_url = f"https://www.job-room.ch/job-search/{job.id}"

                    pub_date = None
                    if getattr(job, "publication", None) and job.publication.start_date:
                        try:
                            date_raw = job.publication.start_date
                            if "T" in date_raw:
                                date_str = date_raw.replace('Z', '+00:00')
                                pub_date = datetime.datetime.fromisoformat(date_str)
                            else:
                                pub_date = datetime.datetime.strptime(date_raw, "%Y-%m-%d")
                        except (ValueError, TypeError):
                            pass

                    distance_km = None
                    if (profile_dict.get("latitude") is not None and profile_dict.get("longitude") is not None and 
                        getattr(job, "location", None)):
                        
                        coords = job.location.coordinates
                        if coords:
                            distance_km = round(
                                haversine_distance(
                                    profile_dict["latitude"],
                                    profile_dict["longitude"],
                                    coords.lat,
                                    coords.lon,
                                ),
                                1,
                            )

                    key = (job.source, str(job.id))
                    scraped_job = scraped_map.get(key)

                    if not scraped_job:
                        scraped_job = ScrapedJob(
                            platform=job.source,
                            platform_job_id=str(job.id),
                            title=clean_html_tags(getattr(job, "title", "Unknown")),
                            company=company,
                            description=clean_html_tags(desc_text) if desc_text else None,
                            location=location_str,
                            external_url=final_external_url or str(job.id),
                            application_url=app_url or None,
                            application_email=app_email or None,
                            workload=workload_str or None,
                            publication_date=pub_date,
                            raw_metadata=getattr(job, "raw_data", None) or {},
                            source_query=getattr(job, "title", "Unknown"),
                            # Persist the summary generated in Step 3.5 if available
                            summary=getattr(job, "_summary", None),
                        )
                        new_scraped_jobs.append(scraped_job)
                        scraped_map[key] = scraped_job
                    elif getattr(job, "_summary", None) and not scraped_job.summary:
                        # Update summary on existing record if we just generated one
                        scraped_job.summary = job._summary

                    db_job = Job(
                        user_id=profile_dict["user_id"],
                        search_profile_id=profile_dict["id"],
                        scraped_job_id=None, # Will set after flush
                        is_scraped=True,
                        affinity_score=analysis.get("affinity_score", 0),
                        affinity_analysis=analysis.get("affinity_analysis", "") if analysis.get("affinity_analysis", "") else None,
                        worth_applying=analysis.get("worth_applying", False),
                        distance_km=distance_km,
                    )
                    # Use Python attribute so we can link it later
                    db_job._scraped_job_ref = scraped_job
                    job_records.append(db_job)

                if new_scraped_jobs:
                    db_session.add_all(new_scraped_jobs)
                    db_session.flush()

                for db_job in job_records:
                    db_job.scraped_job_id = db_job._scraped_job_ref.id
                    delattr(db_job, "_scraped_job_ref") # Cleanup

                db_session.add_all(job_records)
                db_session.commit()
                saved_count = len(job_records)
            except Exception as e:
                logger.error(f"Bulk DB save failed: {e}")
                db_session.rollback()
                skipped_count += len(analysis_results)
                saved_count = 0
            finally:
                db_session.close()
                
        return saved_count, skipped_count



def get_search_service(db) -> SearchService:
    """Factory — create a SearchService with proper repositories."""
    return SearchService(
        job_repo=JobRepository(db),
        profile_repo=ProfileRepository(db),
    )
