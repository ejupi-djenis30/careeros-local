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


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def _run_scheduled_search(profile_id: int):
    """Execute a scheduled search for the given profile."""
    if settings.OFFLINE_MODE is True:
        logger.info("[Scheduler] Skipping scheduled search because offline mode is active")
        return
    logger.info(f"[Scheduler] Running scheduled search for profile {profile_id}")

    # Respect the same reservation lifecycle as manual searches so that a
    # scheduled run cannot overlap with a manually-triggered run on any worker.
    reservation_token = reserve_task(profile_id, return_token=True)
    if not reservation_token:
        logger.info(
            "[Scheduler] Skipping scheduled search for profile %d — a search is already running",
            profile_id,
        )
        return

    db: Session | None = None
    try:
        db = SessionLocal()
        profile_repo = ProfileRepository(db)
        profile = profile_repo.get(profile_id)
        if not profile:
            logger.warning(f"[Scheduler] Profile {profile_id} not found, removing job")
            release_task(profile_id, reservation_token)
            remove_schedule(profile_id)
            return

        if not profile.schedule_enabled:
            logger.info(f"[Scheduler] Profile {profile_id} schedule disabled, skipping")
            release_task(profile_id, reservation_token)
            return

        # Update last run time
        profile_repo.update(profile, {"last_scheduled_run": datetime.now(timezone.utc)})

        # Run the search workflow — run_search calls register_task internally,
        # which moves the slot from reserved → active.
        search_service = get_search_service(db)
        await search_service.run_search(profile_id, reservation_token=reservation_token)

        logger.info(f"[Scheduler] Completed scheduled search for profile {profile_id}")
    except Exception as e:
        # Safety net: release the reservation if run_search never registered the task.
        release_task(profile_id, reservation_token)
        logger.error(f"[Scheduler] Error running scheduled search for profile {profile_id}: {e}")
    finally:
        if db is not None:
            db.close()


def add_schedule(profile_id: int, interval_hours: int):
    """Add or update a scheduled search job."""
    if not interval_hours or interval_hours < 1:
        interval_hours = 24
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
    logger.info(f"[Scheduler] Added schedule for profile {profile_id}: every {interval_hours}h")


def remove_schedule(profile_id: int):
    """Remove a scheduled search job."""
    scheduler = get_scheduler()
    job_id = f"search_profile_{profile_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)
        logger.info(f"[Scheduler] Removed schedule for profile {profile_id}")


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
            interval = profile.schedule_interval_hours or 24
            add_schedule(profile.id, interval)
            logger.info(
                f"[Scheduler] Restored schedule for profile {profile.id} (every {interval}h)"
            )
    except Exception as e:
        logger.error(f"[Scheduler] Error loading schedules: {e}")
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
