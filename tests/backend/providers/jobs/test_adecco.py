from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.providers.jobs.adecco import AdeccoProvider
from backend.providers.jobs.adecco.filters import build_query_string
from backend.providers.jobs.adecco.transformer import transform_job_data
from backend.providers.jobs.models import ContractType, JobSearchRequest, ProviderStatus, WorkForm

# Setup sample data from what we reverse-engineered
SAMPLE_SUMMARIZED_RESPONSE = {
    "jobs": [
        {
            "jobTitle": "Software Engineer",
            "jobId": "TEST-123",
            "contractTypeId": "PERM",
            "cityName": "Zurich",
            "stateName": "Zh",
            "countryId": "CHE",
            "isRemote": True,
            "postedDate": "2026-03-11T10:00:00Z",
            "language": "en-US",
        }
    ],
    "pagination": {"total": 1, "pageCount": 1},
}

SAMPLE_DETAIL_RESPONSE = {
    "jobName": "Software Engineer Detail",
    "jobDescription": "<p>My Job Description</p>",
    "recruiterName": "John Doe",
    "applyUri": "https://apply.adecco/123",
    "companyName": "Tech Corp",
}


@pytest.fixture
def adept_provider():
    return AdeccoProvider(include_raw_data=False)


@pytest.mark.asyncio
async def test_adecco_health_check_success(adept_provider):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        health = await adept_provider.health_check()
        assert health.status == ProviderStatus.HEALTHY
        assert health.provider == "adecco"


@pytest.mark.asyncio
async def test_adecco_health_check_failure(adept_provider):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        health = await adept_provider.health_check()
        assert health.status == ProviderStatus.DEGRADED


@pytest.mark.asyncio
async def test_adecco_search_success(adept_provider):
    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        # Mock Summarized POST
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = SAMPLE_SUMMARIZED_RESPONSE
        mock_post.return_value = mock_post_resp

        # Mock Detail GET
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = SAMPLE_DETAIL_RESPONSE
        mock_get.return_value = mock_get_resp

        request = JobSearchRequest(query="Software", location="Zurich", page=0)
        response = await adept_provider.search(request)

        assert response.total_count == 1
        assert len(response.items) == 1

        job = response.items[0]
        assert job.id == "TEST-123"
        assert job.title == "Software Engineer Detail"
        # Since isRemote went into work_forms
        assert "remote" in job.employment.work_forms
        assert job.location.city == "Zurich"
        assert job.location.canton_code == "Zh"
        assert job.descriptions[0].description == "<p>My Job Description</p>"
        assert job.contact.first_name == "John"
        assert job.contact.last_name == "Doe"
        assert job.external_url == "https://apply.adecco/123"


@pytest.mark.asyncio
async def test_adecco_search_without_details(adept_provider):
    # Tests that it falls back to summary data gracefully if detail fails (e.g. 404)
    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = SAMPLE_SUMMARIZED_RESPONSE
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 404
        mock_get_resp.raise_for_status.side_effect = Exception("Not Found")
        mock_get.return_value = mock_get_resp

        request = JobSearchRequest(query="Software", location="Zurich", page=0)
        response = await adept_provider.search(request)

        assert response.total_count == 1
        assert len(response.items) == 1

        job = response.items[0]
        # Should fallback to light title
        assert job.title == "Software Engineer"
        assert job.id == "TEST-123"
        assert not job.descriptions  # No description since detail failed


@pytest.mark.asyncio
async def test_adecco_search_empty_results(adept_provider):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"jobs": [], "pagination": {"total": 0, "pageCount": 0}}
        mock_post.return_value = mock_post_resp

        request = JobSearchRequest(query="Nobody", location="Nowhere")
        response = await adept_provider.search(request)

        assert response.total_count == 0
        assert len(response.items) == 0


@pytest.mark.asyncio
async def test_adecco_search_pagination_page_2(adept_provider):
    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = SAMPLE_SUMMARIZED_RESPONSE
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = SAMPLE_DETAIL_RESPONSE
        mock_get.return_value = mock_get_resp

        request = JobSearchRequest(query="Software", page=1)  # Page 1 = second page (0-indexed)
        _ = await adept_provider.search(request)

        # Check the payload sent to POST
        call_args = mock_post.call_args[1].get("json")
        assert call_args is not None
        assert call_args["range"] == 10  # 1 * 10


@pytest.mark.asyncio
async def test_adecco_search_429_retry(adept_provider):
    import httpx

    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        patch(
            "backend.providers.jobs.adecco.client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep,
    ):
        # Simulate 429 Too Many Requests on the first try, then 200 on the second try
        error_resp = MagicMock()
        error_resp.status_code = 429
        error_resp.headers = {"Retry-After": "2"}
        error_resp.request = MagicMock()
        error_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429 Too Many Requests", request=error_resp.request, response=error_resp
        )

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = SAMPLE_SUMMARIZED_RESPONSE

        mock_post.side_effect = [error_resp, success_resp]

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = SAMPLE_DETAIL_RESPONSE
        mock_get.return_value = mock_get_resp

        request = JobSearchRequest(query="Software", page=0)
        response = await adept_provider.search(request)

        # It should have called POST twice (once failed, once success)
        assert mock_post.call_count == 2
        # It should have called sleep for Retry-After = 2 seconds
        # Actually it might call sleep(2) for 429, plus random.uniform(1.0, 2.5) for the detail request delay
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert 2.0 in sleep_calls
        assert response.total_count == 1
        assert len(response.items) == 1


@pytest.mark.asyncio
async def test_adecco_search_429_invalid_retry_after_logs_warning(adept_provider, caplog):
    import httpx

    caplog.set_level("WARNING")

    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        patch("backend.providers.jobs.adecco.client.asyncio.sleep", new_callable=AsyncMock),
        patch("backend.providers.jobs.adecco.client.random.uniform", return_value=4.5),
    ):
        error_resp = MagicMock()
        error_resp.status_code = 429
        error_resp.headers = {"Retry-After": "not-a-date"}
        error_resp.request = MagicMock()
        error_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429 Too Many Requests", request=error_resp.request, response=error_resp
        )

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = SAMPLE_SUMMARIZED_RESPONSE

        mock_post.side_effect = [error_resp, success_resp]

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = SAMPLE_DETAIL_RESPONSE
        mock_get.return_value = mock_get_resp

        response = await adept_provider.search(JobSearchRequest(query="Software", page=0))

        assert response.total_count == 1
        assert "Adecco Retry-After header 'not-a-date' is invalid" in caplog.text


@pytest.mark.asyncio
async def test_adecco_search_logs_when_fallback_transform_fails(adept_provider, caplog):
    caplog.set_level("WARNING")

    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        patch("backend.providers.jobs.adecco.client.transform_job_data") as mock_transform,
        patch("backend.providers.jobs.adecco.client.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = SAMPLE_SUMMARIZED_RESPONSE
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 500
        mock_get_resp.raise_for_status.side_effect = Exception("detail failed")
        mock_get.return_value = mock_get_resp

        mock_transform.side_effect = [
            Exception("primary transform failed"),
            Exception("fallback transform failed"),
        ]

        response = await adept_provider.search(JobSearchRequest(query="Software", page=0))

        assert response.total_count == 1
        assert len(response.items) == 0
        assert "Failed to transform Adecco job TEST-123 without details" in caplog.text


def test_build_query_string_basic():
    req = JobSearchRequest(query="Developer", location="Bern")
    qs = build_query_string(req)
    assert "&location:Bern" in qs
    assert "&q=Developer" in qs
    assert "&sort=date desc" in qs


def test_build_query_string_contract_type():
    req = JobSearchRequest(query="Dev", contract_type=ContractType.TEMPORARY)
    qs = build_query_string(req)
    # contractType should NOT be in query string anymore
    assert "&contractType=" not in qs

    req_remote = JobSearchRequest(query="Dev", work_forms=[WorkForm.HOME_OFFICE])
    qs_remote = build_query_string(req_remote)
    # workType should NOT be in query string anymore
    assert "&workType=" not in qs_remote


def test_filter_jobs_contract_type():
    from backend.providers.jobs.adecco.filters import filter_jobs
    from backend.providers.jobs.models import EmploymentDetails, JobListing

    jobs = [
        JobListing(
            id="1", title="Perm", source="adecco", employment=EmploymentDetails(is_permanent=True)
        ),
        JobListing(
            id="2", title="Temp", source="adecco", employment=EmploymentDetails(is_permanent=False)
        ),
    ]

    req_perm = JobSearchRequest(contract_type=ContractType.PERMANENT)
    filtered_perm = filter_jobs(jobs, req_perm)
    assert len(filtered_perm) == 1
    assert filtered_perm[0].id == "1"

    req_temp = JobSearchRequest(contract_type=ContractType.TEMPORARY)
    filtered_temp = filter_jobs(jobs, req_temp)
    assert len(filtered_temp) == 1
    assert filtered_temp[0].id == "2"


def test_filter_jobs_workload():
    from backend.providers.jobs.adecco.filters import filter_jobs
    from backend.providers.jobs.models import EmploymentDetails, JobListing

    jobs = [
        JobListing(
            id="1",
            title="FT",
            source="adecco",
            employment=EmploymentDetails(workload_min=80, workload_max=100),
        ),
        JobListing(
            id="2",
            title="PT",
            source="adecco",
            employment=EmploymentDetails(workload_min=20, workload_max=50),
        ),
    ]

    # Looking for FT (min 90)
    req_ft = JobSearchRequest(workload_min=90)
    filtered_ft = filter_jobs(jobs, req_ft)
    assert len(filtered_ft) == 1
    assert filtered_ft[0].id == "1"

    # Looking for PT (max 60)
    req_pt = JobSearchRequest(workload_max=60)
    filtered_pt = filter_jobs(jobs, req_pt)
    assert len(filtered_pt) == 1
    assert filtered_pt[0].id == "2"


def test_transform_job_data_workload_mapping():
    light_job_ft = {"jobId": "1", "employmentTypeId": "FULLTIME"}
    job_ft = transform_job_data(light_job_ft, None, "adecco")
    assert job_ft.employment.workload_min == 80
    assert job_ft.employment.workload_max == 100

    light_job_pt = {"jobId": "2", "employmentTypeId": "PARTTIME"}
    job_pt = transform_job_data(light_job_pt, None, "adecco")
    assert job_pt.employment.workload_min == 20
    assert job_pt.employment.workload_max == 80

    light_job_hours = {
        "jobId": "3",
        "employmentTypeId": "PARTTIME",
        "workMinHours": 40,
        "workMaxHours": 60,
    }
    job_hours = transform_job_data(light_job_hours, None, "adecco")
    assert job_hours.employment.workload_min == 40
    assert job_hours.employment.workload_max == 60


def test_transform_country_code_normalization():
    light_job_ch = {"jobId": "1", "countryId": "CHE"}
    job_ch = transform_job_data(light_job_ch, None, "adecco")
    assert job_ch.location.country_code == "CH"

    light_job_de = {"jobId": "2", "countryId": "DEU"}
    job_de = transform_job_data(light_job_de, None, "adecco")
    assert job_de.location.country_code == "DE"


def test_transform_job_data_missing_job_id_returns_none(caplog):
    caplog.set_level("WARNING")

    listing = transform_job_data({"jobTitle": "Software Engineer"}, None, "adecco")

    assert listing is None
    assert "Skipping Adecco listing with missing jobId" in caplog.text


@pytest.mark.asyncio
async def test_adecco_search_with_radius(adept_provider):
    """Test Adecco search with location and radius filter."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        request = JobSearchRequest(query="Developer", location="Zurich", radius=20)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"jobs": [], "pagination": {"total": 0}}
        mock_post.return_value = mock_resp

        await adept_provider.search(request)

        # Verify the payload contains &location:Zurich and &d=20
        args, kwargs = mock_post.call_args
        payload = kwargs.get("json", {})
        query_string = payload.get("queryString", "")

        assert "&location:Zurich" in query_string
        assert "&d=20" in query_string
        assert "&q=Developer" in query_string
