from backend.services.search.query_contracts import (
    build_plan_cache_payload,
    canonicalize_query_text,
    compute_plan_input_fingerprint,
    exact_query_fingerprint,
    is_cached_plan_compatible,
    normalize_language,
    normalize_search_item,
    route_provider_names,
    unpack_plan_cache_payload,
)


def test_normalize_search_item_infers_keyword_and_normalizes_language():
    item, reason = normalize_search_item(
        {"query": " Python 100% ", "type": "", "domain": "IT", "language": "English"}
    )

    assert reason == "ok"
    assert item == {
        "query": "Python",
        "type": "keyword",
        "domain": "it",
        "language": "en",
    }


def test_exact_query_fingerprint_preserves_order_distinctions():
    left = exact_query_fingerprint({"query": "React Developer", "type": "occupation", "domain": "it", "language": "en"})
    right = exact_query_fingerprint({"query": "Developer React", "type": "occupation", "domain": "it", "language": "en"})

    assert left != right


def test_cache_payload_roundtrip_and_compatibility():
    fingerprint = compute_plan_input_fingerprint(
        {"role_description": "Backend developer", "search_strategy": "", "cv_content": "Python"},
        max_queries=10,
        max_occupation_queries=None,
        max_keyword_queries=None,
    )
    payload = build_plan_cache_payload(
        [{"query": "Backend Engineer", "type": "occupation", "domain": "it", "language": "en"}],
        input_fingerprint=fingerprint,
        stats={"count": 1},
    )

    searches, meta = unpack_plan_cache_payload(payload)

    assert len(searches) == 1
    assert meta["version"] >= 2
    assert is_cached_plan_compatible(meta, fingerprint) is True
    assert is_cached_plan_compatible(meta, "other") is False


def test_route_provider_names_orders_it_sources_first():
    class Info:
        def __init__(self, accepted_domains):
            self.accepted_domains = accepted_domains

    providers = {
        "job_room": object(),
        "swissdevjobs": object(),
        "adecco": object(),
    }
    provider_infos = {
        "job_room": Info(["*"]),
        "swissdevjobs": Info(["it"]),
        "adecco": Info(["*"]),
    }

    ordered = route_provider_names(
        {"query": "Backend Engineer", "type": "occupation", "domain": "it", "language": "en"},
        providers,
        provider_infos,
    )

    assert ordered[:2] == ["swissdevjobs", "job_room"]


def test_normalize_language_supports_extended_aliases():
    assert normalize_language("Spanish") == "es"
    assert normalize_language("Português") == "pt"
    assert normalize_language("Polski") == "pl"
    assert normalize_language("Română") == "ro"