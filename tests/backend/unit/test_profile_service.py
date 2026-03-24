import pytest
from unittest.mock import MagicMock
from backend.services.profile_service import ProfileService
from backend.schemas import SearchProfileCreate, SearchProfileUpdate, ScheduleToggle

@pytest.fixture
def mock_repo():
    return MagicMock()

@pytest.fixture
def profile_service(mock_repo):
    service = ProfileService(MagicMock())
    service.repo = mock_repo
    return service

def test_get_profiles_by_user(profile_service, mock_repo):
    mock_repo.get_by_user.return_value = ["p1", "p2"]
    res = profile_service.get_profiles_by_user(1)
    assert len(res) == 2
    mock_repo.get_by_user.assert_called_once_with(1, skip=0, limit=100)

def test_create_profile(profile_service, mock_repo):
    profile_in = SearchProfileCreate(name="New Profile", role_description="Dev")
    profile_service.create_profile(1, profile_in)
    mock_repo.create.assert_called_once()
    args = mock_repo.create.call_args[0][0]
    assert args["user_id"] == 1

def test_update_profile_success(profile_service, mock_repo):
    mock_profile = MagicMock()
    mock_profile.user_id = 1
    mock_repo.get.return_value = mock_profile
    
    updates = SearchProfileUpdate(name="Updated")
    profile_service.update_profile(1, 10, updates)
    mock_repo.update.assert_called_once_with(mock_profile, updates)

def test_update_profile_forbidden(profile_service, mock_repo):
    mock_profile = MagicMock()
    mock_profile.user_id = 2
    mock_repo.get.return_value = mock_profile
    
    with pytest.raises(Exception) as exc:
        profile_service.update_profile(1, 10, SearchProfileUpdate())
    assert "403" in str(exc.value)

def test_toggle_schedule(profile_service, mock_repo):
    mock_profile = MagicMock()
    mock_profile.user_id = 1
    mock_repo.get.return_value = mock_profile
    
    toggle = ScheduleToggle(enabled=True, interval_hours=12)
    profile_service.toggle_schedule(1, 10, toggle)
    mock_repo.update.assert_called_once()
    args = mock_repo.update.call_args[0][1]
    assert args["schedule_enabled"] is True
    assert args["schedule_interval_hours"] == 12
