# ═══════════════════════════════════════
# Scheduler Service
# ═══════════════════════════════════════
# Uses APScheduler to run periodic search workflows.
# Each SearchProfile with schedule_enabled=True gets its own recurring job.

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.base import SessionLocal
from backend.repositories.profile_repository import ProfileRepository
from backend.services.search_service import get_search_service
from backend.services.search_status import release_task, reserve_task

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: AsyncIOScheduler | None = None


def _validated_profile_id(value: object) -> int:
    """Return a positive integer profile identifier or reject the input.

    Scheduler entry points are also called from background jobs, so their runtime
    inputs cannot rely solely on API type validation.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("profile_id must be a positive integer")
    return value


def _normalized_interval_hours(value: object) -> int:
    """Preserve the 24-hour fallback for invalid scheduler intervals."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return 24
    return value


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def _run_scheduled_search(profile_id: int):
    """Execute a scheduled search for the given profile."""
    try:
        profile_id = _validated_profile_id(profile_id)
    except ValueError:
        logger.warning("[Scheduler] Rejected scheduled search with invalid profile id")
        return

    if settings.OFFLINE_MODE is True:
        logger.info("[Scheduler] Skipping scheduled search because offline mode is active")
        return
    logger.info("[Scheduler] Running scheduled search")

    # Respect the same reservation lifecycle as manual searches so that a
    # scheduled run cannot overlap with a manually-triggered run on any worker.
    reservation_token = reserve_task(profile_id, return_token=True)
    if not reservation_token:
        logger.info("[Scheduler] Skipping scheduled search because one is already running")
        return

    db: Session | None = None
    try:
        db = SessionLocal()
        profile_repo = ProfileRepository(db)
        profile = profile_repo.get(profile_id)
        if not profile:
            logger.warning("[Scheduler] Profile not found; removing schedule")
            release_task(profile_id, reservation_token)
            remove_schedule(profile_id)
            return

        if not profile.schedule_enabled:
            logger.info("[Scheduler] Schedule disabled; skipping scheduled search")
            release_task(profile_id, reservation_token)
            return

        # Update last run time
        profile_repo.update(profile, {"last_scheduled_run": datetime.now(timezone.utc)})

        # Run the search workflow — run_search calls register_task internally,
        # which moves the slot from reserved → active.
        search_service = get_search_service(db)
        await search_service.run_search(profile_id, reservation_token=reservation_token)

        logger.info("[Scheduler] Completed scheduled search")
    except Exception:
        # Safety net: release the reservation if run_search never registered the task.
        release_task(profile_id, reservation_token)
        # Exception messages may contain imported profile or provider data. The
        # event is sufficient for diagnostics without exposing exception details.
        logger.error("[Scheduler] Scheduled search failed")
    finally:
        if db is not None:
            db.close()


def add_schedule(profile_id: int, interval_hours: int):
    """Add or update a scheduled search job."""
    profile_id = _validated_profile_id(profile_id)
    interval_hours = _normalized_interval_hours(interval_hours)
    scheduler = get_scheduler()
    job_id = f"search_profile_{profile_id}"

    # Remove existing job if any
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)

    trigger = IntervalTrigger(hours=interval_hours)
    scheduler.add_job(
        _run_scheduled_search,
        trigger=trigger,
        args=[profile_id],
        id=job_id,
        name=f"Scheduled search: Profile {profile_id}",
        replace_existing=True,
    )
    logger.info("[Scheduler] Added schedule")


def remove_schedule(profile_id: int):
    """Remove a scheduled search job."""
    profile_id = _validated_profile_id(profile_id)
    scheduler = get_scheduler()
    job_id = f"search_profile_{profile_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)
        logger.info("[Scheduler] Removed schedule")


def get_all_schedules(user_id: int = None, db: Session = None) -> list[dict]:
    """Get info about all scheduled jobs."""
    scheduler = get_scheduler()
    jobs = []

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        profile_repo = ProfileRepository(db)
        valid_profile_ids = {p.id for p in profile_repo.get_scheduled_profiles(user_id=user_id)}
    finally:
        if close_db:
            db.close()

    for job in scheduler.get_jobs():
        if job.id.startswith("search_profile_"):
            try:
                pid = int(job.id.split("_")[-1])
                if pid not in valid_profile_ids:
                    continue
            except ValueError:
                continue

            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )
    return jobs


def start_scheduler():
    """Start the scheduler and load saved schedules from DB."""
    scheduler = get_scheduler()
    if scheduler.running:
        return

    # Load saved schedules from DB
    db: Session = SessionLocal()
    try:
        profile_repo = ProfileRepository(db)
        profiles = profile_repo.get_scheduled_profiles()

        for profile in profiles:
            profile_id = _validated_profile_id(profile.id)
            interval = _normalized_interval_hours(profile.schedule_interval_hours)
            add_schedule(profile_id, interval)
            logger.info("[Scheduler] Restored schedule")
    except Exception:
        logger.error("[Scheduler] Failed to load schedules")
    finally:
        db.close()

    scheduler.start()
    logger.info("[Scheduler] Started")


def stop_scheduler():
    """Stop the scheduler gracefully."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped")
