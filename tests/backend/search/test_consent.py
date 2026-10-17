from types import SimpleNamespace

from backend.search.consent import consent_audit_record, public_job_source_catalog


def test_fresh_catalog_contains_only_the_local_vault() -> None:
    assert public_job_source_catalog() == [
        {
            "key": "local_db",
            "label": "Archivio locale",
            "description": "Annunci già presenti nel Career Vault; nessun accesso di rete",
            "network": False,
            "available": True,
            "consented": True,
        }
    ]


def test_catalog_reflects_only_installed_provider_state() -> None:
    sources = public_job_source_catalog(
        [
            SimpleNamespace(
                key="job_room",
                display_name="Job-Room",
                description="Swiss public jobs",
                enabled=False,
            ),
            SimpleNamespace(
                key="example_jobs",
                display_name="Example Jobs",
                description="Configured source",
                enabled=True,
            ),
        ]
    )

    assert [(source["key"], source["consented"]) for source in sources] == [
        ("local_db", True),
        ("job_room", False),
        ("example_jobs", True),
    ]


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
