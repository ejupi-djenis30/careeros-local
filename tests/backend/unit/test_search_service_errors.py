import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from backend.services.search_service import SearchService
from backend.models import ScrapedJob, Job

@pytest.mark.asyncio
async def test_analyze_and_save_db_failure(db_session):
    """Test that analyze_and_save handles DB bulk save failure with rollback."""
    mock_job_repo = MagicMock()
    mock_profile_repo = MagicMock()
    service = SearchService(mock_job_repo, mock_profile_repo)
    
    profile_dict = {"id": 1, "user_id": 1, "latitude": 47.0, "longitude": 8.0}
    
    mock_job = MagicMock()
    mock_job.source = "test"
    mock_job.id = "123"
    mock_job.title = "Broken Job"
    mock_job.location = MagicMock(city="Zurich", coordinates=None)
    mock_job.company = MagicMock(name="Tech")
    
    unique_jobs = [mock_job]
    
    # Mock LLM analysis success
    with patch("backend.services.llm_service.llm_service.analyze_job_batch", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = [{"relevant": True, "affinity_score": 90, "affinity_analysis": "OK", "worth_applying": True}]
        
        # Use the repository's DB session (mocked)
        mock_session = mock_job_repo.db
        mock_session.commit.side_effect = Exception("DB Crash")
        
        with patch("backend.services.search_service.get_status", return_value={"state": "searching"}):
            saved, skipped = await service._analyze_and_save(1, profile_dict, unique_jobs)
        
        assert saved == 0
        assert skipped == 1
        # Per-job commits: rollback is not called explicitly when individual jobs fail


