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
        
        # Mock SessionLocal to raise error on commit
        with patch("backend.services.search_service.SessionLocal") as mock_session_factory:
            mock_session = MagicMock()
            mock_session_factory.return_value = mock_session
            mock_session.commit.side_effect = Exception("DB Crash")
            
            saved, skipped = await service._analyze_and_save(1, profile_dict, unique_jobs)
            
            assert saved == 0
            assert skipped == 1
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()

@pytest.mark.asyncio
async def test_relevance_filter_exception_handling():
    """Test that relevance_filter falls back to keeping all jobs if LLM fails."""
    service = SearchService(MagicMock(), MagicMock())
    jobs = [MagicMock(), MagicMock()]
    
    with patch("backend.services.llm_service.llm_service.check_relevance_batch", new_callable=AsyncMock) as mock_check:
        mock_check.side_effect = Exception("LLM Down")
        
        filtered = await service._relevance_filter(1, {}, jobs)
        
        assert len(filtered) == 2
        assert filtered == jobs
