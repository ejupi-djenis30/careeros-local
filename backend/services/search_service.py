import logging
import asyncio
from typing import List, Any, Dict
from datetime import datetime
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.services.llm_service import llm_service
from backend.services.search.search_validator import build_search_request
from backend.services.search.search_executor import process_job_listing
from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
from backend.providers.jobs.localdb.client import LocalDbProvider
from backend.providers.jobs.models import JobSearchRequest, SortOrder, RadiusSearchRequest, Coordinates
from backend.models import Job
from backend.core.config import settings
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

            # We don't initialize status here anymore, wait until we have the search plan

            # Map available providers and their infos
            available_providers = {
                "job_room": JobRoomProvider(),
                "swissdevjobs": SwissDevJobsProvider(),
                "local_db": LocalDbProvider(self.job_repo.db)
            }
            
            provider_infos = {
                name: p.get_provider_info() for name, p in available_providers.items()
            }

            # ── Step 1: Generate search plan using LLM ──
            add_log(profile_id, "Generating search plan with AI…")

            try:
                searches = await asyncio.to_thread(
                    llm_service.generate_search_plan, profile_dict, list(provider_infos.values()), profile.max_queries
                )
            except Exception as e:
                logger.error(f"LLM keyword generation failed: {e}")
                update_status(profile_id, state="error", error=str(e))
                return

            if not searches:
                add_log(profile_id, "No search keywords generated")
                update_status(profile_id, state="done", jobs_found=0, jobs_new=0)
                return

            # Deduplicate searches based on query string (domain-agnostic dedup)
            unique_searches = []
            seen_queries = set()
            for s in searches:
                q_str = s.get("query", "").lower().strip()
                key = q_str
                if q_str and key not in seen_queries:
                    seen_queries.add(key)
                    unique_searches.append(s)

            # Count total provider calls for progress tracking
            total_provider_calls = 0
            for s in unique_searches:
                domain = s.get("domain", "general")
                compatible = get_compatible_providers(domain, available_providers, provider_infos)
                total_provider_calls += len(compatible)

            init_status(profile_id, total_searches=total_provider_calls, searches=unique_searches, user_id=user_id)
            add_log(profile_id, f"Generated {len(searches)} queries → {len(unique_searches)} unique → {total_provider_calls} provider calls")
            
            searches = unique_searches

            # ── Step 2: Execute searches with domain routing ──
            update_status(profile_id, state="searching")
            
            all_jobs: list = []
            call_index = 0

            for idx, search in enumerate(searches):
                query = search.get("query", "")
                domain = search.get("domain", "general")
                
                # Check if stopped
                profile = self.profile_repo.get(profile_id)
                if profile and profile.is_stopped:
                    logger.info(f"Search profile {profile_id} was stopped by user.")
                    update_status(profile_id, state="stopped", error="Search stopped by user.")
                    break

                # Find compatible providers for this query's domain
                compatible = get_compatible_providers(domain, available_providers, provider_infos)
                
                if not compatible:
                    add_log(profile_id, f"⚠ No providers accept domain '{domain}' for «{query}»")
                    continue

                add_log(profile_id, f"[{idx+1}/{len(searches)}] «{query}» (domain={domain}) → {', '.join(compatible)}")

                # Build search request once, reuse for all providers
                request = build_search_request(profile, query)

                # Execute on all compatible providers in parallel
                async def search_provider(provider_name: str, req: JobSearchRequest):
                    provider = available_providers[provider_name]
                    try:
                        result = await provider.search(req)
                        return provider_name, result.items, None
                    except Exception as e:
                        return provider_name, [], e

                tasks = [
                    search_provider(p_name, request)
                    for p_name in compatible
                ]

                results = await asyncio.gather(*tasks)

                for p_name, items, error in results:
                    call_index += 1
                    update_status(profile_id, current_search_index=call_index)
                    
                    if error:
                        logger.warning(f"Search «{query}» on {p_name} failed: {error}")
                        add_log(profile_id, f"⚠ Search «{query}» on {p_name} failed: {error}")
                    else:
                        all_jobs.extend(items)
                        add_log(profile_id, f"  ↳ {p_name}: {len(items)} jobs")

            if not all_jobs:
                add_log(profile_id, "No jobs found across all queries")
                update_status(profile_id, state="done", jobs_found=0, jobs_new=0)
                return

            add_log(profile_id, f"Total raw results: {len(all_jobs)}")

            # ── Step 3: Deduplicate ──
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
            add_log(
                profile_id,
                f"After dedup: {len(unique_jobs)} new, {duplicates} duplicates",
            )
            update_status(
                profile_id,
                state="analyzing",
                jobs_found=len(all_jobs),
                jobs_new=len(unique_jobs),
                jobs_duplicates=duplicates,
            )

            # ── Step 4: Analyze & save each unique job (Parallel) ──
            semaphore = asyncio.Semaphore(10)

            async def process_with_limit(job, idx, total):
                async with semaphore:
                    db_session = SessionLocal()
                    try:
                        status_data = get_status(profile_id)
                        if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
                            logger.info(f"Skipping job analysis for {job.id} as search was stopped.")
                            return False
                            
                        add_log(profile_id, f"Analyzing {idx + 1}/{total}: {job.title}")
                        try:
                            return await process_job_listing(job, profile_dict, db_session)
                        except Exception as e:
                            logger.warning(f"Failed to process job {job.id}: {e}")
                            add_log(profile_id, f"⚠ Failed: {job.title} – {e}")
                            return False
                    finally:
                        db_session.close()

            tasks = [
                process_with_limit(job, idx, len(unique_jobs))
                for idx, job in enumerate(unique_jobs)
            ]
            
            results = await asyncio.gather(*tasks)
            saved_count = sum(1 for r in results if r is True)
            skipped_count = sum(1 for r in results if r is False)

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



def get_search_service(db) -> SearchService:
    """Factory — create a SearchService with proper repositories."""
    return SearchService(
        job_repo=JobRepository(db),
        profile_repo=ProfileRepository(db),
    )
