import pytest
from unittest.mock import MagicMock
from backend.providers.jobs.localdb.client import LocalDbProvider
from backend.providers.jobs.models import JobSearchRequest, JobLocation
from backend.models import ScrapedJob

@pytest.fixture
def mock_db_session():
    return MagicMock()

@pytest.fixture
def local_db_provider(mock_db_session):
    return LocalDbProvider(db=mock_db_session)

def test_provider_info(local_db_provider):
    info = local_db_provider.get_provider_info()
    assert info.name == "local_db"
    assert "local" in info.description.lower()

@pytest.mark.asyncio
async def test_search_builds_query_correctly(local_db_provider, mock_db_session):
    # Setup mock query chain
    mock_query = MagicMock()
    mock_db_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.count.return_value = 1
    
    # Mock data exactly one row
    mock_scraped_job = ScrapedJob(
        platform="job_room",
        platform_job_id="123",
        title="Software Engineer",
        company="Tech Corp",
        location="Zurich",
        external_url="http://example.com/123",
        workload="80-100%"
    )
    mock_query.all.return_value = [mock_scraped_job]

    req = JobSearchRequest(
        query="Software Engineer",
        location="Zurich",
        page_size=10,
    )

    result = await local_db_provider.search(req)
    results = result.items

    assert len(results) == 1
    listing = results[0]
    assert listing.id == "123"
    assert listing.title == "Software Engineer"
    assert listing.company.name == "Tech Corp"
    assert listing.source == "job_room"
    assert listing.location.city == "Zurich"
    assert listing.employment.workload_min == 80
    assert listing.employment.workload_max == 100
    assert listing.external_url == "http://example.com/123"
    
    # Verify response metadata
    assert result.source == "local_db"
    assert result.total_count == 1

    # Verify db calls
    mock_db_session.query.assert_called_once()
    assert mock_query.filter.call_count >= 1 # Keyword filter and Location filter
    mock_query.limit.assert_called_once_with(10)
    mock_query.all.assert_called_once()

def test_db_job_to_listing_parsing(local_db_provider):
    # Verify different workload parsing
    job1 = ScrapedJob(platform="x", platform_job_id="1", title="A", external_url="a", workload="100%")
    listing1 = local_db_provider._db_job_to_listing(job1)
    assert listing1.employment.workload_min == 100
    assert listing1.employment.workload_max == 100

    job2 = ScrapedJob(platform="x", platform_job_id="2", title="B", external_url="b", workload="50-80")
    listing2 = local_db_provider._db_job_to_listing(job2)
    assert listing2.employment.workload_min == 50
    assert listing2.employment.workload_max == 80

    job3 = ScrapedJob(platform="x", platform_job_id="3", title="C", external_url="c", workload=None, company="Cmp")
    listing3 = local_db_provider._db_job_to_listing(job3)
    assert listing3.employment is None
    assert listing3.company.name == "Cmp"

