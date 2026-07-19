"""
Preference Service — Phase 2: User Feedback Loop

Aggregates behavioral signals (applied / dismissed jobs) into a structured
``preference_signals`` dict stored on the User record.  This dict is then
injected as a soft tiebreaker into the MATCH prompt and used inside the
prescore gating step.

Usage
-----
    from backend.services.preference_service import compute_and_save_preferences

    signals = compute_and_save_preferences(user_id, db)

The function is idempotent and cheap (<100 ms for typical users); call it
after any job interaction (apply / dismiss) and on demand.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.job import Job
from backend.repositories.job_repository import JobRepository
from backend.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def compute_and_save_preferences(user_id: int, db: Session) -> Dict[str, Any]:
    """Compute preference signals from all of a user's jobs and persist them.

    Returns the freshly computed ``preference_signals`` dict.
    Does nothing and returns an empty dict if the computation meets an error.
    """
    try:
        signals = _compute(user_id, db)
        _persist(user_id, signals, db)
        return signals
    except Exception:
        # User identifiers and database exception text are deliberately excluded:
        # both can contain private data or control characters when this boundary is
        # called outside the typed API layer.
        logger.error("preference_service: failed to compute signals")
        return {}


def get_preference_signals(user_id: int, db: Session) -> Optional[Dict[str, Any]]:
    """Return cached preference_signals from the user row, or None if absent."""
    user = UserRepository(db).get(user_id)
    if not user:
        return None
    signals = user.preference_signals or {}
    if signals.get("signal_count", 0) < settings.PREFERENCE_MIN_SIGNAL_COUNT:
        return None
    return signals


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


def _compute(user_id: int, db: Session) -> Dict[str, Any]:
    jobs = JobRepository(db).get_jobs_with_scraped_job_for_user(user_id)

    applied_jobs = [j for j in jobs if j.applied]
    dismissed_jobs = [j for j in jobs if j.dismissed]
    signal_count = len(applied_jobs) + len(dismissed_jobs)

    # ── Domain preferences ────────────────────────────────────────────────────
    domain_apply: Counter = Counter()
    domain_dismiss: Counter = Counter()

    for j in applied_jobs:
        d = _norm(j, "normalized_domain")
        if d:
            domain_apply[d] += 1

    for j in dismissed_jobs:
        d = _norm(j, "normalized_domain")
        if d:
            domain_dismiss[d] += 1

    preferred_domains = [d for d, _ in domain_apply.most_common(5)]

    avoided_domains = [
        d for d in domain_dismiss if _dismiss_rate(domain_apply.get(d, 0), domain_dismiss[d]) > 0.75
    ]

    # ── Role-type preferences ─────────────────────────────────────────────────
    role_type_counts: Counter = Counter()
    for j in applied_jobs:
        rt = _norm(j, "normalized_role_type")
        if rt:
            role_type_counts[rt] += 1
    preferred_role_types = [rt for rt, _ in role_type_counts.most_common(3)]

    # ── Skill preferences (from required_skills of applied jobs) ──────────────
    skill_counts: Counter = Counter()
    for j in applied_jobs:
        sj = j.scraped_job
        if sj:
            for skill in sj.normalized_required_skills or []:
                if isinstance(skill, str) and skill.strip():
                    skill_counts[skill.strip().lower()] += 1
    preferred_skills = [s for s, _ in skill_counts.most_common(15)]

    # ── Seniority preferences ─────────────────────────────────────────────────
    seniority_counts: Counter = Counter()
    for j in applied_jobs:
        sen = _norm(j, "normalized_seniority")
        if sen:
            seniority_counts[sen] += 1
    preferred_seniority = [s for s, _ in seniority_counts.most_common(2)]

    # ── Typical salary range (from applied jobs) ──────────────────────────────
    salaries_min = [
        j.scraped_job.normalized_salary_min_chf
        for j in applied_jobs
        if j.scraped_job and j.scraped_job.normalized_salary_min_chf
    ]
    salaries_max = [
        j.scraped_job.normalized_salary_max_chf
        for j in applied_jobs
        if j.scraped_job and j.scraped_job.normalized_salary_max_chf
    ]
    typical_salary_range: Optional[Dict[str, Any]] = None
    if salaries_min or salaries_max:
        typical_salary_range = {
            "typical_min_chf": int(sum(salaries_min) / len(salaries_min)) if salaries_min else None,
            "typical_max_chf": int(sum(salaries_max) / len(salaries_max)) if salaries_max else None,
        }

    # ── Typical commute distance ───────────────────────────────────────────────
    distances = [j.distance_km for j in applied_jobs if j.distance_km is not None]
    typical_distance_km = int(sum(distances) / len(distances)) if distances else None

    # ── Dealbreaker patterns (feedback_signal frequencies from dismissed) ──────
    dealbreaker_patterns: Dict[str, int] = {}
    for j in dismissed_jobs:
        feedback_signal = str(j.feedback_signal or "")
        if feedback_signal:
            dealbreaker_patterns[feedback_signal] = dealbreaker_patterns.get(feedback_signal, 0) + 1

    return {
        "preferred_domains": preferred_domains,
        "avoided_domains": avoided_domains,
        "preferred_role_types": preferred_role_types,
        "preferred_skills": preferred_skills,
        "preferred_seniority": preferred_seniority,
        "typical_salary_range": typical_salary_range,
        "typical_distance_km": typical_distance_km,
        "dealbreaker_patterns": dealbreaker_patterns,
        "signal_count": signal_count,
        "last_computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _persist(user_id: int, signals: Dict[str, Any], db: Session) -> None:
    user_repo = UserRepository(db)
    user = user_repo.get(user_id)
    if not user:
        logger.warning("preference_service: user not found; skipping persist")
        return
    user_repo.update(
        user,
        {
            "preference_signals": signals,
            "preference_updated_at": datetime.now(timezone.utc),
        },
    )


def compute_salary_benchmark(
    domain: Optional[str],
    seniority: Optional[str],
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Return salary percentile statistics (P25 / median / P75) for a job domain+seniority.

    Queries normalized salary columns on ScrapedJob to compute statistics from
    the local catalog. Returns None when fewer than 5 data points are available
    (not enough data to make a reliable benchmark).

    Example return value::

        {"p25": 70000, "median": 85000, "p75": 100000, "n": 42}
    """

    if not domain:
        return None

    try:
        values = sorted(JobRepository(db).get_salary_benchmark_values(domain, seniority))

        if len(values) < 5:
            return None

        n = len(values)
        p25 = values[int(n * 0.25)]
        median = values[int(n * 0.5)]
        p75 = values[int(n * 0.75)]
        return {"p25": p25, "median": median, "p75": p75, "n": n}
    except Exception:
        # Domain, seniority and exception details may originate in imported job data.
        logger.error("compute_salary_benchmark: failed")
        return None


def _norm(job: Job, attr: str) -> Optional[str]:
    """Safe attribute access on the joined scraped_job."""
    sj = job.scraped_job
    if sj is None:
        return None
    return getattr(sj, attr, None)


def _dismiss_rate(apply_cnt: int, dismiss_cnt: int) -> float:
    total = apply_cnt + dismiss_cnt
    return dismiss_cnt / total if total > 0 else 0.0
