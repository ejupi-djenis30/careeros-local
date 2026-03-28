"""Unit tests for backend/services/preference_service.py.

Covers:
- compute_and_save_preferences: signal aggregation, persistence
- get_preference_signals: returns None when below min signal count
- compute_salary_benchmark: not enough data returns None, statistics
- _persist: missing user is a no-op
"""
import pytest
from unittest.mock import MagicMock, patch, call
from collections import Counter

from backend.services.preference_service import (
    compute_and_save_preferences,
    get_preference_signals,
    compute_salary_benchmark,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_scraped_job(
    domain=None, role_type=None, seniority=None,
    salary_min=None, salary_max=None, required_skills=None
):
    sj = MagicMock()
    sj.normalized_domain = domain
    sj.normalized_role_type = role_type
    sj.normalized_seniority = seniority
    sj.normalized_salary_min_chf = salary_min
    sj.normalized_salary_max_chf = salary_max
    sj.normalized_required_skills = required_skills or []
    return sj


def _make_job(
    applied=False, dismissed=False,
    feedback_signal=None, distance_km=None, scraped_job=None,
):
    job = MagicMock()
    job.applied = applied
    job.dismissed = dismissed
    job.feedback_signal = feedback_signal
    job.distance_km = distance_km
    job.scraped_job = scraped_job
    return job


def _make_db(jobs=None, user=None):
    """Create a minimal mock DB session."""
    db = MagicMock()
    # Chain: db.query(Job).join(...).filter(...).all() → jobs
    query_chain = MagicMock()
    query_chain.join.return_value = query_chain
    query_chain.filter.return_value = query_chain
    query_chain.all.return_value = jobs or []
    db.query.return_value = query_chain

    # Override for User query
    user_query = MagicMock()
    user_query.filter.return_value = user_query
    user_query.first.return_value = user

    def _query_side_effect(model):
        from backend.models.job import Job
        from backend.models.user import User
        if model is User:
            return user_query
        return query_chain

    db.query.side_effect = _query_side_effect
    return db


# ─── compute_and_save_preferences ─────────────────────────────────────────────

class TestComputeAndSavePreferences:
    def test_returns_signals_dict(self):
        jobs = [
            _make_job(applied=True, scraped_job=_make_scraped_job(domain="it", seniority="senior")),
        ]
        user = MagicMock()
        db = _make_db(jobs=jobs, user=user)
        signals = compute_and_save_preferences(1, db)
        assert isinstance(signals, dict)
        assert "signal_count" in signals

    def test_applied_job_counted(self):
        jobs = [
            _make_job(applied=True, scraped_job=_make_scraped_job(domain="it")),
        ]
        user = MagicMock()
        db = _make_db(jobs=jobs, user=user)
        signals = compute_and_save_preferences(1, db)
        assert signals["signal_count"] == 1

    def test_dismissed_job_counted(self):
        jobs = [
            _make_job(dismissed=True, scraped_job=_make_scraped_job(domain="finance")),
        ]
        user = MagicMock()
        db = _make_db(jobs=jobs, user=user)
        signals = compute_and_save_preferences(1, db)
        assert signals["signal_count"] == 1

    def test_preferred_domain_from_applied_jobs(self):
        jobs = [
            _make_job(applied=True, scraped_job=_make_scraped_job(domain="it")),
            _make_job(applied=True, scraped_job=_make_scraped_job(domain="it")),
        ]
        user = MagicMock()
        db = _make_db(jobs=jobs, user=user)
        signals = compute_and_save_preferences(1, db)
        assert "it" in signals["preferred_domains"]

    def test_preferred_skills_extracted_from_applied_jobs(self):
        sj = _make_scraped_job(required_skills=["python", "fastapi"])
        jobs = [_make_job(applied=True, scraped_job=sj)]
        user = MagicMock()
        db = _make_db(jobs=jobs, user=user)
        signals = compute_and_save_preferences(1, db)
        assert "python" in signals["preferred_skills"]
        assert "fastapi" in signals["preferred_skills"]

    def test_dealbreaker_patterns_from_dismissed_jobs(self):
        jobs = [
            _make_job(dismissed=True, feedback_signal="bad_salary",
                      scraped_job=_make_scraped_job()),
        ]
        user = MagicMock()
        db = _make_db(jobs=jobs, user=user)
        signals = compute_and_save_preferences(1, db)
        assert signals["dealbreaker_patterns"].get("bad_salary", 0) >= 1

    def test_typical_distance_computed_from_applied(self):
        jobs = [
            _make_job(applied=True, distance_km=20.0, scraped_job=_make_scraped_job()),
            _make_job(applied=True, distance_km=40.0, scraped_job=_make_scraped_job()),
        ]
        user = MagicMock()
        db = _make_db(jobs=jobs, user=user)
        signals = compute_and_save_preferences(1, db)
        assert signals["typical_distance_km"] == 30

    def test_empty_jobs_returns_empty_aggregations(self):
        user = MagicMock()
        db = _make_db(jobs=[], user=user)
        signals = compute_and_save_preferences(1, db)
        assert signals["signal_count"] == 0
        assert signals["preferred_domains"] == []
        assert signals["preferred_skills"] == []

    def test_user_preference_signals_saved(self):
        jobs = [_make_job(applied=True, scraped_job=_make_scraped_job(domain="it"))]
        user = MagicMock()
        db = _make_db(jobs=jobs, user=user)
        compute_and_save_preferences(1, db)
        assert db.add.called
        assert db.commit.called

    def test_returns_empty_dict_on_exception(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("DB exploded")
        result = compute_and_save_preferences(1, db)
        assert result == {}


# ─── get_preference_signals ────────────────────────────────────────────────────

class TestGetPreferenceSignals:
    def test_returns_none_when_user_not_found(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = None
        db.query.return_value = q
        assert get_preference_signals(999, db) is None

    def test_returns_none_when_signal_count_below_min(self):
        from backend.core.config import settings
        user = MagicMock()
        user.preference_signals = {"signal_count": 0}
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = user
        db.query.return_value = q
        result = get_preference_signals(1, db)
        assert result is None

    def test_returns_signals_when_count_meets_min(self):
        from backend.core.config import settings
        user = MagicMock()
        min_count = settings.PREFERENCE_MIN_SIGNAL_COUNT
        user.preference_signals = {"signal_count": min_count, "preferred_domains": ["it"]}
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = user
        db.query.return_value = q
        result = get_preference_signals(1, db)
        assert result is not None
        assert "preferred_domains" in result


# ─── compute_salary_benchmark ─────────────────────────────────────────────────

class TestComputeSalaryBenchmark:
    def _make_db_with_salaries(self, salaries):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [(s,) for s in salaries]
        db.query.return_value = q
        return db

    def test_returns_none_when_no_domain(self):
        db = MagicMock()
        result = compute_salary_benchmark(None, "senior", db)
        assert result is None

    def test_returns_none_when_fewer_than_5_data_points(self):
        db = self._make_db_with_salaries([70000, 80000, 90000])
        result = compute_salary_benchmark("it", "senior", db)
        assert result is None

    def test_returns_percentiles_when_enough_data(self):
        salaries = [60000, 70000, 80000, 90000, 100000, 110000, 120000]
        db = self._make_db_with_salaries(salaries)
        result = compute_salary_benchmark("it", "senior", db)
        assert result is not None
        assert "p25" in result
        assert "median" in result
        assert "p75" in result
        assert result["n"] == 7

    def test_returns_none_on_db_exception(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("boom")
        result = compute_salary_benchmark("it", None, db)
        assert result is None
