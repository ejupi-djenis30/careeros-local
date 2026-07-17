from backend.search.consent import (
    consent_audit_record,
    consented_job_providers,
)


def test_network_job_sources_are_denied_by_default() -> None:
    providers = {
        "local_db": object(),
        "job_room": object(),
        "swissdevjobs": object(),
        "future_network_source": object(),
    }

    allowed = consented_job_providers(providers, {})

    assert set(allowed) == {"local_db"}


def test_only_explicitly_consented_known_sources_are_enabled() -> None:
    providers = {
        "local_db": object(),
        "job_room": object(),
        "swissdevjobs": object(),
        "adecco": object(),
    }

    allowed = consented_job_providers(
        providers,
        {"job_room": True, "swissdevjobs": False, "adecco": True},
    )

    assert set(allowed) == {"local_db", "job_room", "adecco"}


def test_consent_audit_record_contains_source_names_only() -> None:
    record = consent_audit_record(
        {"local_db", "job_room", "swissdevjobs"},
        {"local_db", "job_room"},
    )

    assert record == {
        "enabled": ["job_room", "local_db"],
        "disabled": ["swissdevjobs"],
    }
    assert "query" not in record
    assert "profile" not in record
