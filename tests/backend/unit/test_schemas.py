import pytest
from pydantic import ValidationError
from datetime import datetime
from backend.schemas.job import JobCreate, JobUpdate, JobPaginationResponse, JobResponse, NormalizedJobData
from backend.schemas.profile import SearchProfileCreate, ScheduleToggle

def test_job_create_schema_valid():
    payload = {
        "title": "Software Engineer",
        "company": "Tech Corp",
        "external_url": "https://example.com/job",
    }
    job = JobCreate(**payload)
    assert job.title == "Software Engineer"
    assert job.company == "Tech Corp"
    assert job.external_url == "https://example.com/job"
    # Default fields
    assert job.worth_applying is False
    assert job.affinity_score is None

def test_job_create_schema_missing_required():
    with pytest.raises(ValidationError):
        JobCreate(title="No Company or URL")

def test_job_update_schema():
    update = JobUpdate(applied=True)
    assert update.applied is True
    
    update = JobUpdate()
    assert update.applied is None

def test_profile_create_defaults():
    profile = SearchProfileCreate()
    assert profile.name == ""
    assert profile.posted_within_days == 30
    assert profile.max_distance == 50
    assert profile.scrape_mode == "sequential"
    assert profile.schedule_enabled is False
    assert profile.preferred_languages is None
    assert profile.preferred_domains is None
    assert profile.remote_only is False

def test_profile_create_custom():
    payload = {
        "name": "Custom Name",
        "role_description": "Data Scientist",
        "latitude": 47.0,
        "longitude": 8.0,
        "schedule_enabled": True,
        "schedule_interval_hours": 12,
        "preferred_languages": ["English", "DE"],
        "preferred_domains": ["it", "General"],
        "salary_min_chf": 90000,
        "workload_min": 80,
        "workload_max": 100,
        "hard_max_distance_km": 30,
    }
    profile = SearchProfileCreate(**payload)
    assert profile.name == "Custom Name"
    assert profile.role_description == "Data Scientist"
    assert profile.latitude == 47.0
    assert profile.schedule_interval_hours == 12
    assert profile.preferred_languages == ["en", "de"]
    assert profile.preferred_domains == ["it", "general"]
    assert profile.salary_min_chf == 90000
    assert profile.workload_min == 80
    assert profile.workload_max == 100
    assert profile.hard_max_distance_km == 30

def test_schedule_toggle_schema():
    toggle = ScheduleToggle(enabled=True, interval_hours=48)
    assert toggle.enabled is True
    assert toggle.interval_hours == 48

    with pytest.raises(ValidationError):
        ScheduleToggle() # missing 'enabled' boolean


def test_profile_create_invalid_workload_range():
    with pytest.raises(ValidationError):
        SearchProfileCreate(workload_min=90, workload_max=50)


def test_normalized_job_data_defaults():
    normalized = NormalizedJobData()
    assert normalized.required_languages == []
    assert normalized.required_skills == []
    assert normalized.education_levels == []
    assert normalized.key_requirements == []
    assert normalized.metadata == {}
