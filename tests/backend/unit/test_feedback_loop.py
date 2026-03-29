"""Tests for Phase 2: feedback loop features.

Covers:
- JobUpdate schema validation (dismissed, feedback_signal)
- JobService.update_job auto-timestamping for dismissed_at
- JobService.record_view idempotency
- JobService.delete_job soft-delete
- preference_service.compute_and_save_preferences
- listing_utils.infer_implicit_language
- listing_utils.compute_prescore with preference_signals
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.schemas.job import FEEDBACK_SIGNAL_VALUES, JobUpdate

# ─── JobUpdate schema ─────────────────────────────────────────────────────────


class TestJobUpdateSchema:
    def test_valid_applied_only(self):
        u = JobUpdate(applied=True)
        assert u.applied is True
        assert u.dismissed is None
        assert u.feedback_signal is None

    def test_valid_dismissed(self):
        u = JobUpdate(dismissed=True, feedback_signal="wrong_domain")
        assert u.dismissed is True
        assert u.feedback_signal == "wrong_domain"

    def test_invalid_feedback_signal_raises(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            JobUpdate(feedback_signal="flying_saucer")

    def test_all_allowed_feedback_signals(self):
        for sig in FEEDBACK_SIGNAL_VALUES:
            u = JobUpdate(feedback_signal=sig)
            assert u.feedback_signal == sig


# ─── JobService — dismissed_at auto-timestamping ─────────────────────────────


class TestJobServiceDismiss:
    @pytest.fixture
    def service(self):
        from backend.services.job_service import JobService

        svc = JobService(MagicMock())
        svc.repo = MagicMock()
        return svc

    def _make_job(self, user_id=1, dismissed=False):
        job = MagicMock()
        job.user_id = user_id
        job.dismissed = dismissed
        return job

    def test_dismiss_sets_dismissed_at(self, service):
        job = self._make_job(dismissed=False)
        service.repo.get.return_value = job

        updated_job = MagicMock()
        service.repo.update.return_value = updated_job

        with patch("backend.services.preference_service.compute_and_save_preferences"):
            service.update_job(1, 99, JobUpdate(dismissed=True))

        # repo.update must have been called with dismissed_at set
        call_kwargs = service.repo.update.call_args
        update_data = call_kwargs[0][1]  # second positional arg is the data dict
        assert update_data.get("dismissed") is True
        assert isinstance(update_data.get("dismissed_at"), datetime)

    def test_undismiss_clears_dismissed_at(self, service):
        job = self._make_job(dismissed=True)
        service.repo.get.return_value = job

        with patch("backend.services.preference_service.compute_and_save_preferences"):
            service.update_job(1, 99, JobUpdate(dismissed=False))

        call_kwargs = service.repo.update.call_args
        update_data = call_kwargs[0][1]
        assert update_data.get("dismissed") is False
        assert update_data.get("dismissed_at") is None

    def test_unauthorized_raises(self, service):
        from fastapi import HTTPException

        job = self._make_job(user_id=2)
        service.repo.get.return_value = job

        with pytest.raises(HTTPException) as exc_info:
            service.update_job(1, 99, JobUpdate(applied=True))
        assert exc_info.value.status_code == 403

    def test_not_found_raises(self, service):
        from fastapi import HTTPException

        service.repo.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.update_job(1, 99, JobUpdate(applied=True))
        assert exc_info.value.status_code == 404


class TestJobServiceRecordView:
    @pytest.fixture
    def service(self):
        from backend.services.job_service import JobService

        svc = JobService(MagicMock())
        svc.repo = MagicMock()
        return svc

    def test_record_view_sets_viewed_at_when_null(self):
        from backend.services.job_service import JobService

        svc = JobService(MagicMock())
        svc.repo = MagicMock()

        job = MagicMock()
        job.user_id = 1
        job.viewed_at = None
        svc.repo.get.return_value = job

        svc.record_view(1, 99)
        svc.repo.update.assert_called_once()
        call_data = svc.repo.update.call_args[0][1]
        assert "viewed_at" in call_data
        assert isinstance(call_data["viewed_at"], datetime)

    def test_record_view_idempotent_when_already_viewed(self):
        from backend.services.job_service import JobService

        svc = JobService(MagicMock())
        svc.repo = MagicMock()

        job = MagicMock()
        job.user_id = 1
        job.viewed_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        svc.repo.get.return_value = job

        svc.record_view(1, 99)
        svc.repo.update.assert_not_called()


class TestJobServiceSoftDelete:
    def test_delete_job_sets_dismissed(self):
        from backend.services.job_service import JobService

        svc = JobService(MagicMock())
        svc.repo = MagicMock()

        job = MagicMock()
        job.user_id = 1
        svc.repo.get.return_value = job

        svc.delete_job(1, 99)

        svc.repo.update.assert_called_once()
        update_data = svc.repo.update.call_args[0][1]
        assert update_data.get("dismissed") is True
        assert isinstance(update_data.get("dismissed_at"), datetime)
        # Hard delete must NOT be called
        svc.repo.delete.assert_not_called()


# ─── preference_service ───────────────────────────────────────────────────────


class TestPreferenceService:
    def _make_scraped_job(self, domain, seniority, salary_max=None, skills=None):
        sj = MagicMock()
        sj.normalized_domain = domain
        sj.normalized_seniority = seniority
        sj.normalized_salary_max_chf = salary_max
        sj.normalized_salary_min_chf = None
        sj.normalized_required_skills = skills or []
        sj.normalized_role_type = None
        return sj

    def _make_job(
        self, user_id, applied, dismissed, feedback_signal=None, scraped_job=None, distance_km=None
    ):
        j = MagicMock()
        j.user_id = user_id
        j.applied = applied
        j.dismissed = dismissed
        j.feedback_signal = feedback_signal
        j.scraped_job = scraped_job
        j.distance_km = distance_km
        return j

    def test_compute_preferred_domains(self):
        from backend.services.preference_service import _compute

        sj_it1 = self._make_scraped_job("it", "mid")
        sj_it2 = self._make_scraped_job("it", "junior")
        sj_hr = self._make_scraped_job("hr", "mid")

        jobs = [
            self._make_job(1, True, False, scraped_job=sj_it1),
            self._make_job(1, True, False, scraped_job=sj_it2),
            self._make_job(1, False, True, feedback_signal="wrong_domain", scraped_job=sj_hr),
        ]

        db_mock = MagicMock()
        db_mock.query.return_value.join.return_value.filter.return_value.all.return_value = jobs

        result = _compute(1, db_mock)

        assert "it" in result["preferred_domains"]
        assert result["signal_count"] == 3

    def test_avoided_domains_high_dismiss_rate(self):
        from backend.services.preference_service import _compute

        sj_bad = self._make_scraped_job("marketing", "mid")
        jobs = [
            self._make_job(1, False, True, scraped_job=sj_bad),
            self._make_job(1, False, True, scraped_job=sj_bad),
            self._make_job(1, False, True, scraped_job=sj_bad),
        ]

        db_mock = MagicMock()
        db_mock.query.return_value.join.return_value.filter.return_value.all.return_value = jobs

        result = _compute(1, db_mock)
        # marketing has 100% dismiss rate → should appear in avoided_domains
        assert "marketing" in result["avoided_domains"]

    def test_dealbreaker_patterns_counted(self):
        from backend.services.preference_service import _compute

        jobs = [
            self._make_job(1, False, True, feedback_signal="bad_salary"),
            self._make_job(1, False, True, feedback_signal="bad_salary"),
            self._make_job(1, False, True, feedback_signal="wrong_domain"),
        ]

        db_mock = MagicMock()
        db_mock.query.return_value.join.return_value.filter.return_value.all.return_value = jobs

        result = _compute(1, db_mock)
        assert result["dealbreaker_patterns"].get("bad_salary") == 2
        assert result["dealbreaker_patterns"].get("wrong_domain") == 1


# ─── listing_utils.infer_implicit_language ───────────────────────────────────


class TestInferImplicitLanguage:
    def _call(self, location):
        from backend.services.search.listing_utils import infer_implicit_language

        return infer_implicit_language(location)

    def test_zurich_returns_de(self):
        assert self._call("Zürich, Switzerland") == "de"

    def test_geneva_returns_fr(self):
        assert self._call("Geneva, CH") == "fr"
        assert self._call("Genève") == "fr"

    def test_lugano_returns_it(self):
        assert self._call("Lugano, Ticino") == "it"

    def test_canton_zurich_returns_de(self):
        assert self._call("Zurich canton") == "de"

    def test_unknown_location_returns_none(self):
        assert self._call("Berlin, Germany") is None

    def test_none_returns_none(self):
        assert self._call(None) is None

    def test_empty_string_returns_none(self):
        assert self._call("") is None


# ─── listing_utils.compute_prescore with preferences ─────────────────────────


class TestComputePrescoreWithPreferences:
    def _make_job_norm(self, domain="it", seniority="mid", skills=None):
        return {
            "normalized_domain": domain,
            "normalized_seniority": seniority,
            "normalized_required_skills": skills or ["python", "fastapi"],
        }

    def _make_profile_norm(self, domains=None, seniority="mid", skills=None):
        return {
            "target_domains": domains or ["it"],
            "seniority": seniority,
            "skills": skills or ["python"],
        }

    def test_preferred_domain_gives_bonus(self):
        from backend.services.search.listing_utils import compute_prescore

        pref_signals = {
            "signal_count": 15,
            "preferred_domains": ["it", "engineering"],
            "avoided_domains": [],
            "preferred_seniority": ["mid"],
            "preferred_skills": ["python"],
            "dealbreaker_patterns": {},
        }
        score_with = compute_prescore(
            self._make_job_norm(), self._make_profile_norm(), pref_signals
        )
        score_without = compute_prescore(self._make_job_norm(), self._make_profile_norm(), None)
        # Preferred domain should give a bonus
        assert score_with >= score_without

    def test_avoided_domain_gives_penalty(self):
        from backend.services.search.listing_utils import compute_prescore

        pref_signals = {
            "signal_count": 15,
            "preferred_domains": [],
            "avoided_domains": ["marketing"],
            "preferred_seniority": [],
            "preferred_skills": [],
            "dealbreaker_patterns": {},
        }
        score_avoided = compute_prescore(
            self._make_job_norm(domain="marketing"),
            self._make_profile_norm(domains=["marketing"]),
            pref_signals,
        )
        score_neutral = compute_prescore(
            self._make_job_norm(domain="marketing"),
            self._make_profile_norm(domains=["marketing"]),
            None,
        )
        assert score_avoided < score_neutral

    def test_below_signal_threshold_no_effect(self):
        from backend.services.search.listing_utils import compute_prescore

        # Only 3 signals — below threshold of 10
        pref_signals = {
            "signal_count": 3,
            "preferred_domains": ["it"],
            "avoided_domains": ["marketing"],
            "preferred_seniority": ["mid"],
            "preferred_skills": ["python"],
            "dealbreaker_patterns": {},
        }
        score_with = compute_prescore(
            self._make_job_norm(), self._make_profile_norm(), pref_signals
        )
        score_without = compute_prescore(self._make_job_norm(), self._make_profile_norm(), None)
        assert score_with == score_without
