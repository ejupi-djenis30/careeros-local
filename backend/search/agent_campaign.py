"""Synchronous, typed search campaign used by authorized automation clients."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from backend.career.service import CareerProfileService, CareerSearchSnapshotError
from backend.repositories.profile_repository import ProfileRepository
from backend.schemas.job import JobPaginationResponse
from backend.schemas.search import AgentSearchRunRequest, AgentSearchRunView
from backend.search.orchestrator import SearchService
from backend.services.job_service import JobService
from backend.services.search_status import get_status, release_task, reserve_task


class AgentSearchError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def run_agent_search(
    db: Session,
    *,
    user_id: int,
    request: AgentSearchRunRequest,
) -> AgentSearchRunView:
    try:
        snapshot = CareerProfileService(db).search_snapshot(user_id)
    except CareerSearchSnapshotError as exc:
        raise AgentSearchError("career_profile_required", str(exc)) from exc

    advanced_preferences = {
        "profile_source": "career_vault",
        "career_profile_id": snapshot.profile_id,
        "career_profile_revision": snapshot.profile_revision,
        "career_fact_ids": list(snapshot.fact_ids),
        "source_snapshot_sha256": snapshot.sha256,
        "preferred_languages": request.preferred_languages,
        "preferred_domains": request.preferred_domains,
    }
    if hashlib.sha256(snapshot.text.encode("utf-8")).hexdigest() != snapshot.sha256:
        raise AgentSearchError("search_snapshot_invalid", "Career Vault search snapshot is invalid")
    profile = ProfileRepository(db).create(
        {
            "user_id": user_id,
            "name": request.name,
            "cv_content": snapshot.text,
            "role_description": request.query,
            "search_strategy": request.search_strategy,
            "location_filter": request.location,
            "posted_within_days": request.posted_within_days,
            "max_queries": request.max_queries,
            "max_keyword_queries": request.max_queries,
            "max_occupation_queries": 0,
            "is_history": True,
            "is_stopped": False,
            "schedule_enabled": False,
            "advanced_preferences": advanced_preferences,
        }
    )
    reservation_token = reserve_task(
        profile.id,
        return_token=True,
        user_id=user_id,
    )
    if not reservation_token:
        raise AgentSearchError("search_conflict", "A search is already running")
    try:
        await SearchService(db).run_search(
            profile.id,
            reservation_token=reservation_token,
        )
    except Exception:
        release_task(profile.id, reservation_token)
        raise
    status = get_status(profile.id) or {}
    page = JobPaginationResponse.model_validate(
        JobService(db).get_jobs_by_user(
            user_id,
            1,
            request.page_size,
            {
                "search_profile_id": profile.id,
                "sort_by": "affinity_score",
                "sort_order": "desc",
                "include_dismissed": False,
            },
        )
    )
    return AgentSearchRunView(
        profile_id=profile.id,
        state=str(status.get("state") or "unknown")[:32],
        terminal_reason=(
            str(status["terminal_reason"])[:80] if status.get("terminal_reason") else None
        ),
        returned_jobs=len(page.items),
        jobs=page.items,
    )
