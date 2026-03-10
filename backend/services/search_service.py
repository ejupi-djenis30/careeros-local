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

            # ── Step 2: Execute searches with domain routing ──
            update_status(profile_id, state="searching")
            all_jobs = await self._execute_searches(profile_id, profile, searches, available_providers, provider_infos)
            if not all_jobs:
                return

            # ── Step 3: Deduplicate ──
            unique_jobs, duplicates = self._deduplicate(profile, all_jobs)
            add_log(profile_id, f"After dedup: {len(unique_jobs)} new, {duplicates} duplicates")
            update_status(
                profile_id,
                state="analyzing",
                jobs_found=len(all_jobs),
                jobs_new=len(unique_jobs),
                jobs_duplicates=duplicates,
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
        try:
            searches = await asyncio.to_thread(
                llm_service.generate_search_plan, profile_dict, list(provider_infos.values()), profile.max_queries
            )
        except Exception as e:
            logger.error(f"LLM keyword generation failed: {e}")
            update_status(profile_id, state="error", error=str(e))
            return []

        if not searches:
            add_log(profile_id, "No search keywords generated")
            update_status(profile_id, state="done", jobs_found=0, jobs_new=0)
            return []

        def get_query_fingerprint(q: str) -> str:
            import re
            q = q.lower()
            noise_words = r'\b(m/w/d|f/m/d|m/f/d|100%|80%|80-100%)\b'
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
        call_index = 0

        # Limit the number of parallel query executions to avoid overwhelming providers
        semaphore = asyncio.Semaphore(3)

        async def execute_single_search(idx: int, search: dict):
            nonlocal call_index
            async with semaphore:
                # Real-time stop check using memory cache rather than DB reads
                status_data = get_status(profile_id)
                if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
                    return []
                    
                query = search.get("query", "")
                domain = search.get("domain", "general")
                query_type = search.get("type", "keyword")
                
                profession_codes = []
                if query_type == "occupation":
                    profession_codes = await avam_mapper.resolve(query)

                compatible = get_compatible_providers(domain, available_providers, provider_infos)
                if not compatible:
                    add_log(profile_id, f"⚠ No providers accept domain '{domain}' for «{query}»")
                    return []

                add_log(profile_id, f"[{idx+1}/{len(searches)}] «{query}» (domain={domain}) → {', '.join(compatible)}")

                request = build_search_request(profile, query, profession_codes)

                async def search_provider(provider_name: str, req: JobSearchRequest):
                    provider = available_providers[provider_name]
                    all_provider_jobs = []
                    max_pages = 3  # Cap to 3 pages (max 60-150 jobs) per provider per query to prevent indefinite crawling
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
                            
                            # Real-time abort check in between pages
                            status_data = get_status(profile_id)
                            if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
                                break
                                
                        return provider_name, all_provider_jobs, None
                    except Exception as e:
                        return provider_name, all_provider_jobs, e

                p_tasks = [search_provider(p_name, request) for p_name in compatible]
                p_results = await asyncio.gather(*p_tasks)

                found_jobs = []
                for p_name, items, error in p_results:
                    call_index += 1
                    update_status(profile_id, current_search_index=call_index)
                    
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
        
        for batch in results:
            all_jobs.extend(batch)

        if not all_jobs:
            add_log(profile_id, "No jobs found across all queries")
            update_status(profile_id, state="done", jobs_found=0, jobs_new=0)
            return []

        add_log(profile_id, f"Total raw results: {len(all_jobs)}")
        return all_jobs

    def _deduplicate(self, profile, all_jobs: list) -> tuple[list, int]:
        seen_keys: set = set()
        unique_jobs: list = []
        
        # Use profile-specific identifiers instead of user-wide to allow re-analysis for different searches
        existing_identifiers = self.job_repo.get_profile_job_identifiers(profile.id)
        existing_keys = {
            f"{row.platform}:{row.platform_job_id}" for row in existing_identifiers
            if row.platform and row.platform_job_id
        }
        existing_urls = {row.external_url for row in existing_identifiers if row.external_url}

        for listing in all_jobs:
            platform = getattr(listing, "source", "unknown")
            platform_id = str(getattr(listing, "id", ""))
            
            key = f"{platform}:{platform_id}"
            url = getattr(listing, "external_url", None) or getattr(listing, "url", None) or platform_id
            
            if (platform and platform_id and (key in seen_keys or key in existing_keys)) or \
               (url and (url in existing_urls and key not in existing_keys)):
                   continue
                   
            if platform and platform_id:
                seen_keys.add(key)
            if url:
                existing_urls.add(url)
                
            unique_jobs.append(listing)

        duplicates = len(all_jobs) - len(unique_jobs)
        return unique_jobs, duplicates

    async def _analyze_and_save(self, profile_id: int, profile_dict: dict, unique_jobs: list) -> tuple[int, int]:
        semaphore = asyncio.Semaphore(15)

        # To fix the DB connection pool issue, we manage ONE session here and pass it,
        # but SQLAlchemy sessions are NOT thread-safe for async parallel writes.
        # So we split: 1. Deep LLM Analysis (Concurrent). 2. DB insertion (Sequential/Batch).

        # First, run the pure LLM analysis for all the jobs
        async def analyze_job_data(job, idx, total):
            async with semaphore:
                status_data = get_status(profile_id)
                if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
                    return None
                    
                add_log(profile_id, f"Analyzing {idx + 1}/{total}: {job.title}")
                from backend.services.llm_service import llm_service
                
                desc_text = job.descriptions[0].description if job.descriptions else ""
                job_metadata = {
                    "title": job.title,
                    "description": desc_text, 
                    "location": job.location.city if job.location else "Unknown",
                    "workload": f"{job.employment.workload_min}-{job.employment.workload_max}%" if job.employment else "Unknown",
                    "languages": [f"{s.language_code} ({s.spoken_level})" for s in job.language_skills] if getattr(job, "language_skills", None) else [],
                    "company": job.company.name if job.company else "Unknown",
                }
                
                try:
                    analysis = await asyncio.to_thread(llm_service.analyze_job_match, job_metadata, profile_dict)
                    if not analysis.get("relevant", True):
                        return None
                    return (job, analysis, desc_text)
                except Exception as e:
                    add_log(profile_id, f"⚠ Failed analyzing: {job.title} – {e}")
                    return None

        tasks = [analyze_job_data(job, idx, len(unique_jobs)) for idx, job in enumerate(unique_jobs)]
        analysis_results = await asyncio.gather(*tasks)
        
        # Now do the DB saving sequentially using ONE connection
        saved_count = 0
        skipped_count = len(unique_jobs)
        
        valid_results = [r for r in analysis_results if r is not None]
        skipped_count -= len(valid_results) # those skipped due to LLM irrelevance
        
        if valid_results:
            from backend.models import ScrapedJob, Job
            from backend.services.utils import haversine_distance, clean_html_tags
            import datetime
            
            db_session = SessionLocal()
            try:
                for job, analysis, desc_text in valid_results:
                    company = job.company.name if job.company else "Unknown"
                    location_str = job.location.city if job.location else ""
                    
                    workload_str = ""
                    if job.employment:
                        wmin = job.employment.workload_min
                        wmax = job.employment.workload_max
                        workload_str = f"{wmin}-{wmax}%" if wmin != wmax else f"{wmin}%"

                    app_url = job.application.form_url if job.application else None
                    app_email = job.application.email if job.application else None

                    final_external_url = job.external_url
                    if not final_external_url and job.source == "job_room":
                        final_external_url = f"https://www.job-room.ch/job-search/{job.id}"

                    pub_date = None
                    if job.publication and job.publication.start_date:
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
                        job.location and job.location.coordinates):
                        distance_km = round(
                            haversine_distance(
                                profile_dict["latitude"],
                                profile_dict["longitude"],
                                job.location.coordinates.lat,
                                job.location.coordinates.lon,
                            ),
                            1,
                        )

                    scraped_job = db_session.query(ScrapedJob).filter(
                        ScrapedJob.platform == job.source,
                        ScrapedJob.platform_job_id == str(job.id)
                    ).first()

                    if not scraped_job:
                        scraped_job = ScrapedJob(
                            platform=job.source,
                            platform_job_id=str(job.id),
                            title=clean_html_tags(job.title),
                            company=company,
                            description=clean_html_tags(desc_text) if desc_text else None,
                            location=location_str,
                            external_url=final_external_url or str(job.id),
                            application_url=app_url or None,
                            application_email=app_email or None,
                            workload=workload_str or None,
                            publication_date=pub_date,
                            raw_metadata=job.raw_data,
                            source_query=job.title,
                        )
                        db_session.add(scraped_job)
                        db_session.flush()

                    db_job = Job(
                        user_id=profile_dict["user_id"],
                        search_profile_id=profile_dict["id"],
                        scraped_job_id=scraped_job.id,
                        is_scraped=True,
                        affinity_score=analysis.get("affinity_score", 0),
                        affinity_analysis=analysis.get("affinity_analysis", "") if analysis.get("affinity_analysis", "") else None,
                        worth_applying=analysis.get("worth_applying", False),
                        distance_km=distance_km,
                    )

                    db_session.add(db_job)
                    saved_count += 1
                
                db_session.commit()
            except Exception as e:
                logger.error(f"Bulk DB save failed: {e}")
                db_session.rollback()
                skipped_count += saved_count
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
