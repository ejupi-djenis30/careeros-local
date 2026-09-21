"""Flush-only acceptance handler for reviewed discovery proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.agent_work.errors import AgentWorkError
from backend.agent_work.models import AgentProposal, AgentWorkRequest
from backend.agent_work.schemas import DiscoveryProposalPayload, DiscoveryVacancy
from backend.applications.models import Application, ApplicationEvent
from backend.applications.snapshots import sanitize_application_snapshot
from backend.core.config import settings
from backend.jobs.catalog_observation import (
    apply_catalog_observation,
    aware_utc,
    catalog_content_changed,
    clear_catalog_normalization,
)
from backend.jobs.manual_identity import stable_manual_platform_job_id
from backend.jobs.urls import normalize_job_url
from backend.models.job import Job, ScrapedJob
from backend.services.search.prompt_compaction import (
    build_scraped_job_content_fingerprint,
    compact_prompt_text,
)


@dataclass(frozen=True)
class DiscoveryAcceptanceResult:
    job_ids: list[int]
    application_ids: list[str]


def _canonical_fields(vacancy: DiscoveryVacancy, *, accepted_at: datetime) -> dict[str, Any]:
    external_url = normalize_job_url(vacancy.external_url, required=True)
    if external_url is None:  # pragma: no cover - required URL guard
        raise AgentWorkError("invalid_result", "Discovery vacancy URL is missing")
    description = vacancy.source_text.strip()
    location = vacancy.location.strip() if vacancy.location else None
    return {
        "title": vacancy.title.strip(),
        "company": vacancy.company.strip(),
        "description": description,
        "location": location,
        "external_url": external_url,
        "application_url": None,
        "application_email": None,
        "workload": None,
        "publication_date": None,
        "raw_metadata": {
            "source": "external_agent",
            "source_platform": vacancy.source_platform,
            "observed_at": vacancy.observed_at.isoformat(),
            "accepted_at": accepted_at.isoformat(),
        },
        "compact_description": compact_prompt_text(
            description,
            int(getattr(settings, "SEARCH_COMPACT_DESCRIPTION_CACHE_MAX_CHARS", 1400) or 1400),
        )
        or None,
    }


def _content_fingerprint(fields: dict[str, Any]) -> str:
    return build_scraped_job_content_fingerprint(
        title=fields["title"],
        company=fields["company"],
        location=fields["location"] or "",
        workload=fields["workload"] or "",
        description=fields["description"] or "",
    )


def _load_catalog_row(db: Session, platform_job_id: str) -> ScrapedJob | None:
    return (
        db.query(ScrapedJob)
        .populate_existing()
        .filter_by(platform="manual", platform_job_id=platform_job_id)
        .with_for_update()
        .first()
    )


def _create_catalog_row(
    db: Session,
    *,
    platform_job_id: str,
    vacancy: DiscoveryVacancy,
    fields: dict[str, Any],
    fingerprint: str,
) -> tuple[ScrapedJob, bool]:
    observed_at = aware_utc(vacancy.observed_at)
    row = ScrapedJob(
        platform="manual",
        platform_job_id=platform_job_id,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        last_changed_at=observed_at,
        content_revision=1,
        content_fingerprint=fingerprint,
        normalization_status="pending",
        **fields,
    )
    savepoint = db.begin_nested()
    try:
        db.add(row)
        db.flush()
        savepoint.commit()
        return row, True
    except IntegrityError:
        savepoint.rollback()
        recovered = _load_catalog_row(db, platform_job_id)
        if recovered is None:
            raise
        return recovered, False


def _upsert_catalog_row(
    db: Session,
    *,
    user_id: int,
    vacancy: DiscoveryVacancy,
    accepted_at: datetime,
) -> tuple[ScrapedJob, bool]:
    fields = _canonical_fields(vacancy, accepted_at=accepted_at)
    platform_job_id = stable_manual_platform_job_id(
        user_id,
        title=fields["title"],
        company=fields["company"],
        external_url=fields["external_url"],
    )
    fingerprint = _content_fingerprint(fields)
    row = _load_catalog_row(db, platform_job_id)
    created = False
    if row is None:
        row, created = _create_catalog_row(
            db,
            platform_job_id=platform_job_id,
            vacancy=vacancy,
            fields=fields,
            fingerprint=fingerprint,
        )
    if created:
        return row, False

    observed_at = aware_utc(vacancy.observed_at)
    changed = catalog_content_changed(
        row,
        refresh_fields=fields,
        content_fingerprint=fingerprint,
    )
    previous_seen = getattr(row, "last_seen_at", None)
    if changed and isinstance(previous_seen, datetime) and observed_at < aware_utc(previous_seen):
        raise AgentWorkError("stale_input", "A newer observation of this vacancy is already stored")
    if (
        not changed
        and isinstance(previous_seen, datetime)
        and observed_at < aware_utc(previous_seen)
    ):
        return row, False
    changed = apply_catalog_observation(
        row,
        seen_at=observed_at,
        refresh_fields=fields,
        content_fingerprint=fingerprint,
        normalized_bootstrap={"normalization_status": "pending"},
        clear_normalization=clear_catalog_normalization,
    )
    db.flush()
    return row, changed


def _get_or_create_job(db: Session, *, user_id: int, scraped_job_id: int) -> Job:
    row = (
        db.query(Job)
        .filter_by(user_id=user_id, scraped_job_id=scraped_job_id)
        .order_by(Job.search_profile_id.is_(None).desc(), Job.id.asc())
        .first()
    )
    if row is None:
        row = Job(user_id=user_id, scraped_job_id=scraped_job_id, search_profile_id=None)
        db.add(row)
        db.flush()
    return row


def _snapshot(
    vacancy: DiscoveryVacancy,
    *,
    external_url: str,
    platform_job_id: str,
) -> dict[str, Any]:
    return sanitize_application_snapshot(
        {
            "schema_version": 2,
            "title": vacancy.title,
            "company": vacancy.company,
            "description": vacancy.source_text,
            "location": vacancy.location,
            "external_url": external_url,
            "application_url": None,
            "application_email": None,
            "workload": None,
            "publication_date": None,
            "platform": "manual",
            "platform_job_id": platform_job_id,
            "match": {},
        },
        quarantine_reason="external_agent_discovery",
    )


def _record_application(
    db: Session,
    *,
    user_id: int,
    req: AgentWorkRequest,
    proposal: AgentProposal,
    vacancy: DiscoveryVacancy,
    job: Job,
    catalog: ScrapedJob,
    content_changed: bool,
    now: datetime,
) -> Application:
    application = (
        db.query(Application)
        .populate_existing()
        .filter_by(user_id=user_id, scraped_job_id=catalog.id)
        .first()
    )
    event_payload = {
        "agent_request_id": req.id,
        "agent_proposal_id": proposal.id,
        "source": "external_agent",
        "source_platform": vacancy.source_platform,
        "observed_at": vacancy.observed_at.isoformat(),
        "content_revision": catalog.content_revision,
        "content_changed": content_changed,
        "gates": [gate.model_dump(mode="json") for gate in vacancy.gates],
        "scores": vacancy.scores.model_dump(mode="json"),
    }
    if application is None:
        application = Application(
            user_id=user_id,
            job_id=job.id,
            scraped_job_id=catalog.id,
            revision=1,
            current_stage="saved",
            job_snapshot=_snapshot(
                vacancy,
                external_url=str(catalog.external_url),
                platform_job_id=str(catalog.platform_job_id),
            ),
            job_title=vacancy.title[:240],
            job_company=vacancy.company[:240],
            job_location=vacancy.location[:500] if vacancy.location else None,
            latest_event_at=now,
        )
        db.add(application)
        db.flush()
        event_type = "stage"
        stage = "saved"
        note = "Created from reviewed external-agent discovery"
        event_payload["initial"] = True
    else:
        application.revision += 1
        application.latest_event_at = now
        event_type = "note"
        stage = None
        note = "Vacancy observed again in a reviewed external-agent discovery"
    db.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=event_type,
            stage=stage,
            occurred_at=now,
            note=note,
            payload=event_payload,
            created_at=now,
        )
    )
    db.flush()
    return application


def accept_discovery_flush_only(
    db: Session,
    *,
    user_id: int,
    req: AgentWorkRequest,
    proposal: AgentProposal,
    payload: DiscoveryProposalPayload,
    now: datetime,
) -> DiscoveryAcceptanceResult:
    """Apply reviewed vacancies while leaving commit and rollback to the caller."""

    job_ids: list[int] = []
    application_ids: list[str] = []
    seen: dict[str, str] = {}
    for vacancy in payload.listings:
        platform_job_id = stable_manual_platform_job_id(
            user_id,
            title=vacancy.title,
            company=vacancy.company,
            external_url=vacancy.external_url,
        )
        fields = _canonical_fields(vacancy, accepted_at=now)
        fingerprint = _content_fingerprint(fields)
        previous = seen.get(platform_job_id)
        if previous is not None:
            if previous != fingerprint:
                raise AgentWorkError(
                    "result_conflict", "The proposal contains conflicting copies of one vacancy"
                )
            continue
        seen[platform_job_id] = fingerprint

        catalog, changed = _upsert_catalog_row(
            db,
            user_id=user_id,
            vacancy=vacancy,
            accepted_at=now,
        )
        job = _get_or_create_job(db, user_id=user_id, scraped_job_id=catalog.id)
        application = _record_application(
            db,
            user_id=user_id,
            req=req,
            proposal=proposal,
            vacancy=vacancy,
            job=job,
            catalog=catalog,
            content_changed=changed,
            now=now,
        )
        job_ids.append(int(job.id))
        application_ids.append(str(application.id))
    return DiscoveryAcceptanceResult(job_ids=job_ids, application_ids=application_ids)
