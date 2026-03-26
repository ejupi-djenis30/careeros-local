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

from backend.db.base import SessionLocal
from backend.models import SearchProfile
from backend.services.search_service import get_search_service

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
    logger.info(f"[Scheduler] Running scheduled search for profile {profile_id}")
    db: Session = SessionLocal()
    try:
        profile = db.query(SearchProfile).filter(SearchProfile.id == profile_id).first()
        if not profile:
            logger.warning(f"[Scheduler] Profile {profile_id} not found, removing job")
            remove_schedule(profile_id)
            return

        if not profile.schedule_enabled:
            logger.info(f"[Scheduler] Profile {profile_id} schedule disabled, skipping")
            return

        # Update last run time
        profile.last_scheduled_run = datetime.now(timezone.utc)
        db.commit()

        # Run the search workflow
        search_service = get_search_service(db)
        await search_service.run_search(profile_id)

        logger.info(f"[Scheduler] Completed scheduled search for profile {profile_id}")
    except Exception as e:
        logger.error(f"[Scheduler] Error running scheduled search for profile {profile_id}: {e}")
    finally:
        db.close()


def add_schedule(profile_id: int, interval_hours: int):
    """Add or update a scheduled search job."""
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
        query = db.query(SearchProfile).filter(SearchProfile.schedule_enabled.is_(True))
        if user_id is not None:
            query = query.filter(SearchProfile.user_id == user_id)
        valid_profile_ids = {p.id for p in query.all()}
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

            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
    return jobs


def start_scheduler():
    """Start the scheduler and load saved schedules from DB."""
    scheduler = get_scheduler()
    if scheduler.running:
        return

    # Load saved schedules from DB
    db: Session = SessionLocal()
    try:
        profiles = db.query(SearchProfile).filter(
            SearchProfile.schedule_enabled.is_(True)
        ).all()

        for profile in profiles:
            interval = profile.schedule_interval_hours or 24
            add_schedule(profile.id, interval)
            logger.info(f"[Scheduler] Restored schedule for profile {profile.id} (every {interval}h)")
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
