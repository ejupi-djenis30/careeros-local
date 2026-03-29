from types import SimpleNamespace

from backend.services.search.search_validator import build_search_request


def test_build_search_request_workload_and_distance():
    profile = SimpleNamespace(
        workload_filter="80-100%",
        latitude=40.0,
        longitude=8.0,
        max_distance="20",
        contract_type="temporary",
        location_filter="Bern",
        posted_within_days=7,
    )
    req = build_search_request(profile, "dev", ["123"])
    assert req.workload_min == 80
    assert req.workload_max == 100
    assert req.radius_search.distance == 20
    assert req.contract_type.value == "temporary"


def test_build_search_request_workload_single_and_no_max_distance():
    profile = SimpleNamespace(
        workload_filter="50",
        latitude=40.0,
        longitude=8.0,
        contract_type="unknown",
        location_filter=None,
        posted_within_days=None,
    )
    # Simulate missing max_distance
    # Profile created without max_distance

    req = build_search_request(profile, "dev")
    assert req.workload_min == 50
    assert req.workload_max == 50
    assert req.radius_search.distance == 50  # default
    assert req.contract_type.value == "any"


def test_build_search_request_workload_value_error():
    profile = SimpleNamespace(
        workload_filter="invalid-string",
        latitude=None,
        longitude=None,
        contract_type=None,
        location_filter=None,
        posted_within_days=None,
        max_distance=None,
    )
    req = build_search_request(profile, "dev")
    assert req.workload_min == 0  # Default fallback


def test_build_search_request_hard_preferences_override_defaults():
    profile = SimpleNamespace(
        workload_filter="50-60%",
        latitude=46.0,
        longitude=8.0,
        contract_type="any",
        location_filter="Zurich",
        posted_within_days=14,
        max_distance=100,
        advanced_preferences={
            "workload_min": 80,
            "workload_max": 100,
            "hard_max_distance_km": 20,
        },
    )

    req = build_search_request(profile, "python")
    assert req.workload_min == 80
    assert req.workload_max == 100
    assert req.radius_search.distance == 20
