import math

import pytest
from pydantic import ValidationError

from backend.providers.jobs.models import (
    Coordinates,
    JobSearchRequest,
    RadiusSearchRequest,
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("page", -1),
        ("page_size", 0),
        ("page_size", 101),
        ("workload_min", -1),
        ("workload_max", 101),
        ("posted_within_days", 0),
        ("radius", -1),
    ],
)
def test_job_search_request_rejects_unsafe_numeric_bounds(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        JobSearchRequest(**{field: value})


def test_job_search_request_rejects_inverted_workload_range() -> None:
    with pytest.raises(ValidationError, match="workload_min cannot be greater"):
        JobSearchRequest(workload_min=90, workload_max=50)


@pytest.mark.parametrize(
    "coordinates",
    [
        {"lat": 91, "lon": 8.54},
        {"lat": -91, "lon": 8.54},
        {"lat": 47.37, "lon": 181},
        {"lat": 47.37, "lon": -181},
        {"lat": math.inf, "lon": 8.54},
        {"lat": 47.37, "lon": math.nan},
    ],
)
def test_coordinates_reject_values_outside_the_earth(coordinates) -> None:
    with pytest.raises(ValidationError):
        Coordinates(**coordinates)


def test_radius_search_rejects_negative_distance() -> None:
    with pytest.raises(ValidationError):
        RadiusSearchRequest(
            geo_point=Coordinates(lat=47.37, lon=8.54),
            distance=-1,
        )


def test_search_collection_limits_bound_provider_request_fanout() -> None:
    with pytest.raises(ValidationError):
        JobSearchRequest(keywords=[f"keyword-{index}" for index in range(101)])

    with pytest.raises(ValidationError):
        JobSearchRequest(communal_codes=[str(index) for index in range(501)])
