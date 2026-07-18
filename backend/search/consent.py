from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy.orm import Session

from backend.career.models import CandidateProfile

NETWORK_JOB_SOURCES: dict[str, tuple[str, str]] = {
    "job_room": ("Job-Room", "Portale pubblico svizzero del lavoro"),
    "swissdevjobs": ("SwissDevJobs", "Annunci tecnologici in Svizzera"),
    "adecco": ("Adecco", "Annunci pubblicati da Adecco"),
}
LOCAL_JOB_SOURCE = "local_db"


def load_job_source_consents(db: Session, user_id: int) -> dict[str, bool]:
    preferences = (
        db.query(CandidateProfile.preferences)
        .filter(CandidateProfile.user_id == user_id)
        .scalar()
    )
    raw = preferences.get("job_source_consents", {}) if isinstance(preferences, dict) else {}
    if not isinstance(raw, dict):
        return {}
    return {
        name: raw.get(name) is True
        for name in NETWORK_JOB_SOURCES
    }


def consented_job_providers(
    providers: Mapping[str, Any], consents: Mapping[str, bool]
) -> dict[str, Any]:
    return {
        name: provider
        for name, provider in providers.items()
        if name == LOCAL_JOB_SOURCE
        or (name in NETWORK_JOB_SOURCES and consents.get(name) is True)
    }


def consent_audit_record(
    configured_names: set[str], enabled_names: set[str]
) -> dict[str, list[str]]:
    """Return a content-free diagnostic record containing source identifiers only."""
    return {
        "enabled": sorted(enabled_names),
        "disabled": sorted(configured_names - enabled_names),
    }


def public_job_source_catalog(
    consents: Mapping[str, bool], *, available: set[str]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = [
        {
            "key": LOCAL_JOB_SOURCE,
            "label": "Archivio locale",
            "description": "Annunci già presenti nel Career Vault; nessun accesso di rete",
            "network": False,
            "available": True,
            "consented": True,
        }
    ]
    result.extend(
        {
            "key": key,
            "label": label,
            "description": description,
            "network": True,
            "available": key in available,
            "consented": consents.get(key) is True,
        }
        for key, (label, description) in NETWORK_JOB_SOURCES.items()
    )
    return result
