import pytest
from pydantic import ValidationError
from datetime import datetime
from backend.schemas.job import JobCreate, JobUpdate, JobPaginationResponse, Job
from backend.schemas.profile import SearchProfileCreate, ScheduleToggle

def test_job_create_schema_valid():
    payload = {
        "title": "Software Engineer",
        "company": "Tech Corp",
        "external_url": "https://example.com/job",
        "is_scraped": True
    }
    job = JobCreate(**payload)
    assert job.title == "Software Engineer"
    assert job.company == "Tech Corp"
    assert job.external_url == "https://example.com/job"
    assert job.is_scraped is True
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
    assert profile.name == "Default Profile"
    assert profile.posted_within_days == 30
    assert profile.max_distance == 50
    assert profile.scrape_mode == "sequential"
    assert profile.schedule_enabled is False

def test_profile_create_custom():
    payload = {
        "name": "Custom Name",
        "role_description": "Data Scientist",
        "latitude": 47.0,
        "longitude": 8.0,
        "schedule_enabled": True,
        "schedule_interval_hours": 12
    }
    profile = SearchProfileCreate(**payload)
    assert profile.name == "Custom Name"
    assert profile.role_description == "Data Scientist"
    assert profile.latitude == 47.0
    assert profile.schedule_interval_hours == 12

def test_schedule_toggle_schema():
    toggle = ScheduleToggle(enabled=True, interval_hours=48)
    assert toggle.enabled is True
    assert toggle.interval_hours == 48

    with pytest.raises(ValidationError):
        ScheduleToggle() # missing 'enabled' boolean
