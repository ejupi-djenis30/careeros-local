"""Focused tests for campaign import planner (Phase 2B2 / C022)."""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from backend.campaigns.archive_policy import CampaignArchiveInspection
from backend.campaigns.import_planner import (
    CampaignPlanError,
    PlannedCampaign,
    build_stage_timeline,
    resolve_stage_path,
)
from backend.campaigns.import_planner import (
    plan_campaign_import as _raw_plan_campaign_import,
)
from backend.campaigns.models import ALLOWED_ARTIFACT_CATEGORIES
from backend.campaigns.parser import parse_campaign_workspace
from backend.campaigns.parser_types import (
    ParsedApplication,
    ParsedArtifact,
    ParsedCampaign,
    freeze_value,
)
from tests.backend.campaigns.fixture_builder import build_fictional_campaign_zip


def plan_campaign_import(
    parsed: ParsedCampaign,
    imported_at: datetime,
    *,
    identity_scope: str = "user:1",
    **kwargs: Any,
) -> PlannedCampaign:
    return _raw_plan_campaign_import(parsed, imported_at, identity_scope=identity_scope, **kwargs)


def _make_parsed_app(
    source_id: str = "APP-TEST",
    *,
    title: str = "Engineer",
    company: str = "Acme",
    status: str = "Applied",
    priority: str = "High",
    platform: str = "Direct",
    category: str = "Engineering",
    outcome: str | None = None,
    found_at: date | None = date(2026, 1, 10),
    applied_at: date | None = date(2026, 1, 12),
    follow_up_at: date | None = date(2026, 1, 26),
    last_update_at: date | None = date(2026, 1, 15),
    next_action: str | None = "Follow up with HR",
    sources: tuple[str, ...] = ("tracker",),
    platform_url: str | None = "https://example.com/job/1",
    job_posting_url: str | None = "https://company.example/careers/1",
    url: str | None = None,
    raw_record: dict[str, Any] | None = None,
) -> ParsedApplication:
    rec = raw_record or {
        "Application ID": source_id,
        "Role Title": title,
        "Company Name": company,
        "Status": status,
        "Requirements Summary": "Python, SQL",
    }
    return ParsedApplication(
        source_application_id=source_id,
        source_order=1,
        title=title,
        company=company,
        location="Zurich",
        source_status=status,
        priority=priority,
        platform=platform,
        category=category,
        outcome=outcome,
        found_at=found_at,
        applied_at=applied_at,
        follow_up_at=follow_up_at,
        last_update_at=last_update_at,
        next_action=next_action,
        notes=None,
        platform_url=platform_url,
        job_posting_url=job_posting_url,
        url=url,
        tracker_record=freeze_value(rec),
        provenance=freeze_value({"sources": list(sources), "warnings": []}),
        packet_dir_name=None,
    )


def _make_parsed_campaign(
    apps: list[ParsedApplication],
    artifacts: list[ParsedArtifact] | None = None,
    fingerprint: str = "a" * 64,
) -> ParsedCampaign:
    return ParsedCampaign(
        fingerprint=fingerprint,
        inspection=CampaignArchiveInspection(
            fingerprint=fingerprint,
            common_prefix="",
            members=MappingProxyType({}),
            total_byte_size=0,
            member_count=0,
        ),
        headers=("Application ID", "Role Title", "Company Name"),
        tracker_rows=(),
        tracker_sha256="b" * 64,
        sanitized_tracker_bytes=b"fake-sanitized-bytes",
        sanitized_tracker_sha256="c" * 64,
        applications=tuple(apps),
        artifacts=tuple(artifacts or []),
        dossier_count=0,
        matched_count=len(apps),
        tracker_only_count=0,
        dossier_only_count=0,
        logical_application_count=len(apps),
        status_counts=freeze_value({"applied": len(apps)}),
        credentials_count=0,
        warnings=(),
        suggested_name="Legacy application campaign",
        suggested_profile_name=None,
    )


def test_stage_paths_for_all_source_statuses() -> None:
    # 1. Saved -> [saved]
    app_saved = _make_parsed_app(status="Saved")
    assert resolve_stage_path(app_saved) == ["saved"]

    # 2. Preparing -> [saved, preparing]
    app_prep = _make_parsed_app(status="Preparing")
    assert resolve_stage_path(app_prep) == ["saved", "preparing"]

    # 3. Applied -> [saved, preparing, applied]
    app_applied = _make_parsed_app(status="Applied")
    assert resolve_stage_path(app_applied) == ["saved", "preparing", "applied"]

    # 4. Closed with applied_at -> [saved, preparing, applied, archived]
    app_closed_applied = _make_parsed_app(status="Closed", applied_at=date(2026, 1, 12))
    assert resolve_stage_path(app_closed_applied) == ["saved", "preparing", "applied", "archived"]

    # 5. Closed without applied_at -> [saved, archived]
    app_closed_no_applied = _make_parsed_app(status="Closed", applied_at=None)
    assert resolve_stage_path(app_closed_no_applied) == ["saved", "archived"]

    # 6. Dossier only -> [saved, preparing]
    app_dossier = _make_parsed_app(status="ArbitraryStatus", sources=("dossier",))
    assert resolve_stage_path(app_dossier) == ["saved", "preparing"]

    # 7. Unknown tracker status -> conservatively [saved]
    app_unknown = _make_parsed_app(status="Offer Received", sources=("tracker",))
    assert resolve_stage_path(app_unknown) == ["saved"]


def test_deterministic_strictly_increasing_timeline() -> None:
    now = datetime(2026, 3, 1, 15, 0, 0, tzinfo=timezone.utc)

    # Normal ordered dates without task
    app1 = _make_parsed_app(
        status="Applied",
        found_at=date(2026, 1, 1),
        applied_at=date(2026, 1, 10),
    )
    timeline1 = build_stage_timeline(app1, ["saved", "preparing", "applied"], now, has_task=False)
    assert len(timeline1) == 3
    assert timeline1[0] < timeline1[1] < timeline1[2] <= now
    assert timeline1[0] == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert timeline1[2] == datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)

    # Equal dates -> microsecond walkback ensures strict order
    app2 = _make_parsed_app(
        status="Applied",
        found_at=date(2026, 1, 1),
        applied_at=date(2026, 1, 1),
    )
    timeline2 = build_stage_timeline(app2, ["saved", "preparing", "applied"], now, has_task=False)
    assert len(timeline2) == 3
    assert timeline2[0] < timeline2[1] < timeline2[2] <= now
    assert timeline2[2] == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert timeline2[1] == timeline2[2] - timedelta(microseconds=1)
    assert timeline2[0] == timeline2[1] - timedelta(microseconds=1)

    # Missing dates (None) -> anchored to imported_at with microsecond walkback
    app3 = _make_parsed_app(
        status="Applied",
        found_at=None,
        applied_at=None,
    )
    timeline3 = build_stage_timeline(app3, ["saved", "preparing", "applied"], now, has_task=False)
    assert len(timeline3) == 3
    assert timeline3[0] < timeline3[1] < timeline3[2] == now
    assert timeline3[1] == now - timedelta(microseconds=1)
    assert timeline3[0] == now - timedelta(microseconds=2)

    # Out-of-order dates: found_at is AFTER applied_at
    app4 = _make_parsed_app(
        status="Applied",
        found_at=date(2026, 1, 20),
        applied_at=date(2026, 1, 10),
    )
    timeline4 = build_stage_timeline(app4, ["saved", "preparing", "applied"], now, has_task=False)
    assert len(timeline4) == 3
    assert timeline4[0] < timeline4[1] < timeline4[2] <= now
    assert timeline4[2] == datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert timeline4[1] == timeline4[2] - timedelta(microseconds=1)
    assert timeline4[0] == timeline4[1] - timedelta(microseconds=1)

    # Future dates: capped at imported_at
    future_now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    app5 = _make_parsed_app(
        status="Applied",
        found_at=date(2026, 1, 10),
        applied_at=date(2026, 1, 12),
    )
    timeline5 = build_stage_timeline(app5, ["saved", "preparing", "applied"], future_now, has_task=False)
    assert len(timeline5) == 3
    assert timeline5[0] < timeline5[1] < timeline5[2] <= future_now


def test_preparing_anchor_expression() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    # In [saved, preparing], preparing uses last_update_at then found_at
    app1 = _make_parsed_app(
        status="Preparing",
        found_at=date(2026, 1, 5),
        last_update_at=date(2026, 1, 8),
    )
    timeline1 = build_stage_timeline(app1, ["saved", "preparing"], now)
    assert timeline1[0] == datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    assert timeline1[1] == datetime(2026, 1, 8, 12, 0, 0, tzinfo=timezone.utc)

    # In [saved, preparing], when last_update_at is missing, preparing falls back to found_at
    app2 = _make_parsed_app(
        status="Preparing",
        found_at=date(2026, 1, 5),
        last_update_at=None,
    )
    timeline2 = build_stage_timeline(app2, ["saved", "preparing"], now)
    assert timeline2[1] == datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    assert timeline2[0] == timeline2[1] - timedelta(microseconds=1)

    # In [saved, preparing, applied], preparing has no independent anchor (anchored between saved and applied)
    app3 = _make_parsed_app(
        status="Applied",
        found_at=date(2026, 1, 1),
        applied_at=date(2026, 1, 10),
        last_update_at=date(2026, 1, 8),
    )
    timeline3 = build_stage_timeline(app3, ["saved", "preparing", "applied"], now)
    assert timeline3[0] == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert timeline3[2] == datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert timeline3[1] == timeline3[2] - timedelta(microseconds=1)


def test_event_timeline_strict_monotonicity_with_missing_dates_and_task() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Application with a task and completely missing source dates
    app_missing = _make_parsed_app(
        source_id="APP-MISSING",
        status="Applied",
        found_at=None,
        applied_at=None,
        last_update_at=None,
        follow_up_at=None,
        next_action="Active follow up action",
    )
    planned = plan_campaign_import(_make_parsed_campaign([app_missing]), now)
    p_app = planned.applications[0]

    assert len(p_app.events) == 4
    # task_created is strictly at imported_at
    task_ev = p_app.events[-1]
    assert task_ev.event_type == "task_created"
    assert task_ev.occurred_at == now

    # Final stage event is at most imported_at - 1 microsecond
    final_stage_ev = p_app.events[-2]
    assert final_stage_ev.event_type == "stage"
    assert final_stage_ev.occurred_at == now - timedelta(microseconds=1)
    assert p_app.events[-3].occurred_at == now - timedelta(microseconds=2)
    assert p_app.events[-4].occurred_at == now - timedelta(microseconds=3)

    # Every adjacent event timestamp is strictly increasing and all <= imported_at
    for i in range(len(p_app.events) - 1):
        assert p_app.events[i].occurred_at < p_app.events[i + 1].occurred_at
    assert p_app.events[-1].occurred_at <= now

    # Also test with equal/future dates and a task
    app_future = _make_parsed_app(
        source_id="APP-FUTURE",
        status="Applied",
        found_at=date(2026, 3, 5),  # future relative to now
        applied_at=date(2026, 3, 10),
        next_action="Action",
    )
    planned_f = plan_campaign_import(_make_parsed_campaign([app_future]), now)
    p_f = planned_f.applications[0]
    for i in range(len(p_f.events) - 1):
        assert p_f.events[i].occurred_at < p_f.events[i + 1].occurred_at
    assert p_f.events[-1].occurred_at == now
    assert p_f.events[-2].occurred_at <= now - timedelta(microseconds=1)


def test_timezone_validation_and_normalization() -> None:
    app = _make_parsed_app()
    campaign = _make_parsed_campaign([app])

    # Naive datetime raises CampaignPlanError
    naive_dt = datetime(2026, 3, 1, 12, 0, 0)
    with pytest.raises(CampaignPlanError, match="timezone-aware"):
        plan_campaign_import(campaign, naive_dt)

    # Non-UTC aware datetime is normalized to UTC
    tz_plus_2 = timezone(timedelta(hours=2))
    aware_dt = datetime(2026, 3, 1, 14, 0, 0, tzinfo=tz_plus_2)
    planned = plan_campaign_import(campaign, aware_dt)

    assert planned.imported_at == datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert planned.imported_at.tzinfo == timezone.utc


def test_tasks_rules_and_frozen_contract() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    fp = "f" * 64

    # 1. Non-Closed with non-empty Next Action -> task created
    app1 = _make_parsed_app(
        source_id="APP-001",
        status="Applied",
        priority="Urgent",
        follow_up_at=date(2026, 3, 15),
        next_action="  Send follow-up email to hiring lead  ",
    )
    # 2. Closed with Next Action -> NO task
    app2 = _make_parsed_app(
        source_id="APP-002",
        status="Closed",
        next_action="Archived action",
    )
    # 3. Dossier-only with Next Action -> NO task
    app3 = _make_parsed_app(
        source_id="dossier-app",
        status="Preparing",
        sources=("dossier",),
        next_action="Draft cover letter",
    )
    # 4. Non-Closed with empty/whitespace Next Action -> NO task
    app4 = _make_parsed_app(
        source_id="APP-004",
        status="Applied",
        next_action="   ",
    )

    campaign = _make_parsed_campaign([app1, app2, app3, app4], fingerprint=fp)
    planned = plan_campaign_import(campaign, now)

    p1, p2, p3, p4 = planned.applications

    # APP-001 has task
    assert p1.task is not None
    assert p1.task.title == "Send follow-up email to hiring lead"
    assert p1.task.priority == "urgent"
    assert p1.task.due_at == datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert p1.task.status == "pending"
    assert p1.task.revision == 1
    expected_task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:careeros:campaign:user:1:{fp}:APP-001:task"))
    assert p1.task.id == expected_task_id
    assert p1.next_action_task_id == expected_task_id
    assert p1.next_action_title == "Send follow-up email to hiring lead"
    assert p1.next_action_at == datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert p1.next_action_priority == "urgent"

    # Task response is frozen Mapping (not mutable Pydantic model)
    assert isinstance(p1.task.response, MappingProxyType)
    assert p1.task.response["id"] == expected_task_id
    assert p1.task.response["title"] == "Send follow-up email to hiring lead"
    assert p1.task.response["status"] == "pending"
    assert p1.task.response["priority"] == "urgent"
    assert p1.task.response["revision"] == 1

    # Task event verification
    task_ev = p1.task.event
    assert task_ev.event_type == "task_created"
    assert task_ev.occurred_at == now
    assert task_ev.note == "Send follow-up email to hiring lead"
    assert task_ev.payload["schema_version"] == "1.0"
    assert task_ev.payload["task"]["id"] == expected_task_id

    # APP-002 (Closed) -> No task
    assert p2.task is None
    assert p2.next_action_task_id is None

    # APP-003 (Dossier-only) -> No task
    assert p3.task is None
    assert p3.next_action_task_id is None

    # APP-004 (Empty next action) -> No task
    assert p4.task is None
    assert p4.next_action_task_id is None


def test_priority_mapping() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    priorities = [
        ("Urgent", "urgent"),
        ("HIGH", "high"),
        ("Medium", "normal"),
        ("low", "low"),
        ("NonStandardPriority", "normal"),
        ("", "normal"),
        (None, "normal"),
    ]
    for idx, (p_in, p_expected) in enumerate(priorities):
        app = _make_parsed_app(
            source_id=f"APP-P-{idx}",
            status="Preparing",
            priority=p_in or "",
            next_action="Action",
        )
        planned = plan_campaign_import(_make_parsed_campaign([app]), now)
        p_app = planned.applications[0]
        assert p_app.task is not None
        assert p_app.task.priority == p_expected
        assert p_app.next_action_priority == p_expected


def test_application_revisions_and_bounded_event_payloads() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Saved with task: 1 stage event + 1 task event = 2 events -> revision 2
    app_saved_task = _make_parsed_app(status="Saved", next_action="Review posting")
    # Applied without task: 3 stage events = 3 events -> revision 3
    app_applied_no_task = _make_parsed_app(status="Applied", next_action=None)
    # Applied with task: 3 stage events + 1 task event = 4 events -> revision 4
    app_applied_task = _make_parsed_app(status="Applied", next_action="Follow up")
    # Closed with applied_at (no task): 4 stage events = 4 events -> revision 4
    app_closed = _make_parsed_app(status="Closed", applied_at=date(2026, 1, 1), next_action="Ignored")

    campaign = _make_parsed_campaign([app_saved_task, app_applied_no_task, app_applied_task, app_closed])
    planned = plan_campaign_import(campaign, now)

    p_saved, p_applied_nt, p_applied_t, p_closed = planned.applications

    assert p_saved.revision == 2
    assert len(p_saved.events) == 2
    assert p_applied_nt.revision == 3
    assert len(p_applied_nt.events) == 3
    assert p_applied_t.revision == 4
    assert len(p_applied_t.events) == 4
    assert p_closed.revision == 4
    assert len(p_closed.events) == 4

    # Check stage event payloads are strictly bounded to import flag and source ID
    for p_app in planned.applications:
        for ev in p_app.events:
            if ev.event_type == "stage":
                assert dict(ev.payload) == {
                    "import": True,
                    "source_application_id": p_app.source_application_id,
                }


def test_snapshot_creation_urls_email_and_vacancy_fallback() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Application 1: Valid URLs (external_url prefers job_posting_url, application_url prefers platform_url)
    # Valid email normalized to lowercase domain. Valid vacancy.md artifact.
    art_vacancy1 = ParsedArtifact(
        relative_path="application-packets/APP-V1/vacancy.md",
        display_name="vacancy.md",
        category="vacancy",
        source_order=1,
        source_application_id="APP-V1",
        raw_bytes=b"# Senior Cloud Engineer\n\nMust know Kubernetes and Go.",
        sha256="d" * 64,
        byte_size=55,
    )

    app1 = _make_parsed_app(
        source_id="APP-V1",
        platform_url="https://platform.example.org/jobs/view/100",
        job_posting_url="https://company.example.org/careers/posting/100",
        url="https://fallback.example.org/jobs/100",
        raw_record={
            "Application ID": "APP-V1",
            "Role Title": "Cloud Engineer",
            "Company Name": "CloudNet",
            "Requirements Summary": "Tracker summary fallback",
            "Contact Email": "Recruiter.Name@Company.EXAMPLE.COM",
        },
    )

    # Application 2: Unsafe URLs, invalid email, and invalid non-UTF-8 vacancy bytes
    art_vacancy2_bad_utf8 = ParsedArtifact(
        relative_path="application-packets/APP-V2/vacancy.md",
        display_name="vacancy.md",
        category="vacancy",
        source_order=2,
        source_application_id="APP-V2",
        raw_bytes=b"\xff\xfe\x00\x80\x99 invalid non utf8 binary bytes",
        sha256="e" * 64,
        byte_size=32,
    )

    app2 = _make_parsed_app(
        source_id="APP-V2",
        platform_url="javascript:alert(document.cookie)",
        job_posting_url="file:///etc/passwd",
        url="ftp://unsafe-protocol.example.com",
        raw_record={
            "Application ID": "APP-V2",
            "Role Title": "Security Analyst",
            "Company Name": "SecCorp",
            "Requirements Summary": "Fallback from corrupt vacancy file",
            "Contact Email": "not-an-email-at-all",
        },
    )

    campaign = _make_parsed_campaign([app1, app2], artifacts=[art_vacancy1, art_vacancy2_bad_utf8])
    planned = plan_campaign_import(campaign, now)

    # App 1 assertions
    p1 = planned.applications[0]
    snap1 = p1.job_snapshot
    assert snap1["schema_version"] == 2
    assert snap1["description"] == "# Senior Cloud Engineer\n\nMust know Kubernetes and Go."
    # external_url prefers job_posting_url over url
    assert snap1["external_url"] == "https://company.example.org/careers/posting/100"
    # application_url prefers platform_url over url
    assert snap1["application_url"] == "https://platform.example.org/jobs/view/100"
    # Email normalized to lowercase domain
    assert snap1["application_email"] == "Recruiter.Name@company.example.com"
    assert snap1["match"]["quarantine_reason"] == "manual_snapshot_has_no_model_analysis"
    assert snap1["match"]["receipt_verified"] is False

    # App 2 assertions: fallback to Requirements Summary on UnicodeDecodeError (never replacement chars)
    p2 = planned.applications[1]
    snap2 = p2.job_snapshot
    assert snap2["description"] == "Fallback from corrupt vacancy file"
    assert "\ufffd" not in snap2["description"]
    # Key absence: unsafe URLs and invalid email omitted entirely from snapshot (not set to None)
    assert "external_url" not in snap2
    assert "application_url" not in snap2
    assert "application_email" not in snap2
    # Raw source metadata retains original verbatim strings
    assert p2.source.platform_url == "javascript:alert(document.cookie)"
    assert p2.source.tracker_record["Contact Email"] == "not-an-email-at-all"


def test_snapshot_whitespace_title_company_fallback() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    app = _make_parsed_app(
        source_id="APP-BLANK-ID",
        title="   \t\n  ",
        company="   ",
    )
    campaign = _make_parsed_campaign([app])
    planned = plan_campaign_import(campaign, now)
    p_app = planned.applications[0]

    assert p_app.job_snapshot["title"] == "Untitled role"
    assert p_app.job_snapshot["company"] == "Unknown company"
    assert p_app.job_title == "Untitled role"
    assert p_app.job_company == "Unknown company"


def test_snapshot_platform_projection_is_bounded_without_losing_campaign_source() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    source_platform = "Synthetic source platform " + ("x" * 43)
    assert 40 < len(source_platform) <= 120

    planned = plan_campaign_import(
        _make_parsed_campaign([_make_parsed_app(platform=source_platform)]),
        now,
    )
    application = planned.applications[0]

    assert application.source.platform == source_platform
    assert application.job_snapshot["platform"] == source_platform[:40]


def test_preflight_validation_limits_without_leaking_values() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Blank campaign name
    camp_blank = _make_parsed_campaign([_make_parsed_app()])
    with pytest.raises(CampaignPlanError) as exc_blank:
        plan_campaign_import(camp_blank, now, campaign_name="   ")
    assert "campaign name must not be blank" in str(exc_blank.value)

    # 2. Campaign name exceeds 160 (exact model limit)
    long_campaign_name = "X" * 161
    camp1 = _make_parsed_campaign([_make_parsed_app()])
    with pytest.raises(CampaignPlanError) as exc1:
        plan_campaign_import(camp1, now, campaign_name=long_campaign_name)
    assert "campaign name exceeds 160" in str(exc1.value)
    assert "X" * 50 not in str(exc1.value)

    # 3. Blank source application ID
    app_blank_id = _make_parsed_app(source_id="   ")
    with pytest.raises(CampaignPlanError) as exc_bid:
        plan_campaign_import(_make_parsed_campaign([app_blank_id]), now)
    assert "source ID must not be blank" in str(exc_bid.value)

    # 4. Source application ID exceeds 120
    private_secret_id = "SECRET_" + ("Y" * 120)
    app2 = _make_parsed_app(source_id=private_secret_id)
    with pytest.raises(CampaignPlanError) as exc2:
        plan_campaign_import(_make_parsed_campaign([app2]), now)
    assert "source ID exceeds 120" in str(exc2.value)
    assert "SECRET" not in str(exc2.value)

    # 5. Status exceeds 60
    app3 = _make_parsed_app(status="S" * 61)
    with pytest.raises(CampaignPlanError) as exc3:
        plan_campaign_import(_make_parsed_campaign([app3]), now)
    assert "status exceeds 60" in str(exc3.value)

    # 6. Priority exceeds 60
    app_p = _make_parsed_app(priority="P" * 61)
    with pytest.raises(CampaignPlanError) as exc_p:
        plan_campaign_import(_make_parsed_campaign([app_p]), now)
    assert "priority exceeds 60" in str(exc_p.value)

    # 7. Platform exceeds 120
    app_plat = _make_parsed_app(platform="L" * 121)
    with pytest.raises(CampaignPlanError) as exc_plat:
        plan_campaign_import(_make_parsed_campaign([app_plat]), now)
    assert "platform exceeds 120" in str(exc_plat.value)

    # 8. Category exceeds 120
    app_cat = _make_parsed_app(category="C" * 121)
    with pytest.raises(CampaignPlanError) as exc_cat:
        plan_campaign_import(_make_parsed_campaign([app_cat]), now)
    assert "category exceeds 120" in str(exc_cat.value)

    # 9. Outcome exceeds 120
    app_out = _make_parsed_app(outcome="O" * 121)
    with pytest.raises(CampaignPlanError) as exc_out:
        plan_campaign_import(_make_parsed_campaign([app_out]), now)
    assert "outcome exceeds 120" in str(exc_out.value)

    # 10. Relative path blank or exceeds 500 (exact model limit)
    art_blank_path = ParsedArtifact(
        relative_path="   ",
        display_name="art.txt",
        category="vacancy",
        source_order=1,
        source_application_id=None,
        raw_bytes=b"123",
        sha256="e" * 64,
        byte_size=3,
    )
    with pytest.raises(CampaignPlanError) as exc_bp:
        plan_campaign_import(_make_parsed_campaign([_make_parsed_app()], artifacts=[art_blank_path]), now)
    assert "relative_path must not be blank" in str(exc_bp.value)

    art_long_path = ParsedArtifact(
        relative_path="a/" * 251,
        display_name="art.txt",
        category="vacancy",
        source_order=1,
        source_application_id=None,
        raw_bytes=b"123",
        sha256="e" * 64,
        byte_size=3,
    )
    with pytest.raises(CampaignPlanError) as exc4:
        plan_campaign_import(_make_parsed_campaign([_make_parsed_app()], artifacts=[art_long_path]), now)
    assert "relative_path exceeds 500" in str(exc4.value)

    # 11. Display name blank or exceeds 255 (exact model limit)
    art_blank_name = ParsedArtifact(
        relative_path="valid/path.txt",
        display_name="   ",
        category="vacancy",
        source_order=1,
        source_application_id=None,
        raw_bytes=b"123",
        sha256="e" * 64,
        byte_size=3,
    )
    with pytest.raises(CampaignPlanError) as exc_bn:
        plan_campaign_import(_make_parsed_campaign([_make_parsed_app()], artifacts=[art_blank_name]), now)
    assert "display_name must not be blank" in str(exc_bn.value)

    art_long_name = ParsedArtifact(
        relative_path="valid/path.txt",
        display_name="N" * 256,
        category="vacancy",
        source_order=1,
        source_application_id=None,
        raw_bytes=b"123",
        sha256="e" * 64,
        byte_size=3,
    )
    with pytest.raises(CampaignPlanError) as exc_ln:
        plan_campaign_import(_make_parsed_campaign([_make_parsed_app()], artifacts=[art_long_name]), now)
    assert "display_name exceeds 255" in str(exc_ln.value)

    # 12. Artifact category must be in ALLOWED_ARTIFACT_CATEGORIES and not credential
    art_credential = ParsedArtifact(
        relative_path="valid/cred.txt",
        display_name="cred.txt",
        category="credential",  # type: ignore[arg-type]
        source_order=1,
        source_application_id=None,
        raw_bytes=b"123",
        sha256="e" * 64,
        byte_size=3,
    )
    with pytest.raises(CampaignPlanError) as exc_cat_cred:
        plan_campaign_import(_make_parsed_campaign([_make_parsed_app()], artifacts=[art_credential]), now)
    assert "invalid artifact category" in str(exc_cat_cred.value)

    art_invalid_cat = ParsedArtifact(
        relative_path="valid/other.txt",
        display_name="other.txt",
        category="unrecognized_cat",  # type: ignore[arg-type]
        source_order=1,
        source_application_id=None,
        raw_bytes=b"123",
        sha256="e" * 64,
        byte_size=3,
    )
    with pytest.raises(CampaignPlanError) as exc_cat_inv:
        plan_campaign_import(_make_parsed_campaign([_make_parsed_app()], artifacts=[art_invalid_cat]), now)
    assert "invalid artifact category" in str(exc_cat_inv.value)


def test_preflight_validation_exact_maxima_accepted() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Exact boundary maxima:
    # Campaign.name: exactly 160 characters
    name_160 = "C" * 160
    assert len(name_160) == 160

    # CampaignApplication fields:
    # source_application_id: exactly 120 characters
    id_120 = "ID_" + ("A" * 117)
    assert len(id_120) == 120
    # source_status: exactly 60 characters
    status_60 = "S" * 60
    assert len(status_60) == 60
    # priority: exactly 60 characters
    priority_60 = "P" * 60
    assert len(priority_60) == 60
    # platform: exactly 120 characters
    platform_120 = "L" * 120
    assert len(platform_120) == 120
    # category: exactly 120 characters
    category_120 = "T" * 120
    assert len(category_120) == 120
    # outcome: exactly 120 characters
    outcome_120 = "O" * 120
    assert len(outcome_120) == 120

    app = _make_parsed_app(
        source_id=id_120,
        status=status_60,
        priority=priority_60,
        platform=platform_120,
        category=category_120,
        outcome=outcome_120,
    )

    # CampaignArtifact fields:
    # relative_path: exactly 500 characters
    path_500 = "dir/" + ("x" * 492) + ".txt"
    assert len(path_500) == 500
    # display_name: exactly 255 characters
    disp_255 = ("y" * 251) + ".txt"
    assert len(disp_255) == 255

    artifacts = [
        ParsedArtifact(
            relative_path=path_500,
            display_name=disp_255,
            category="vacancy",
            source_order=1,
            source_application_id=id_120,
            raw_bytes=b"# Vacancy description",
            sha256="0" * 64,
            byte_size=21,
        )
    ]

    campaign = _make_parsed_campaign([app], artifacts=artifacts)
    planned = plan_campaign_import(campaign, now, campaign_name=name_160)

    assert planned.campaign_name == name_160
    assert planned.applications[0].source_application_id == id_120
    assert planned.artifacts[0].relative_path == path_500
    assert planned.artifacts[0].display_name == disp_255

    # Verify every allowed category domain and length (<= 40) is accepted
    for idx, cat in enumerate(ALLOWED_ARTIFACT_CATEGORIES):
        assert len(cat) <= 40
        art_cat = ParsedArtifact(
            relative_path=f"packet/file_{idx}.txt",
            display_name=f"file_{idx}.txt",
            category=cat,
            source_order=idx + 1,
            source_application_id=None,
            raw_bytes=b"sample",
            sha256="1" * 64,
            byte_size=6,
        )
        cat_camp = _make_parsed_campaign([_make_parsed_app()], artifacts=[art_cat])
        cat_planned = plan_campaign_import(cat_camp, now)
        assert cat_planned.artifacts[0].category == cat


def test_preflight_tracker_record_enforces_exact_xlsx_cell_limit() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    accepted_value = "A" * 32_767
    accepted = _make_parsed_app(raw_record={"Application ID": "APP-LIMIT", "Notes": accepted_value})

    planned = plan_campaign_import(_make_parsed_campaign([accepted]), now)

    assert planned.applications[0].source.tracker_record["Notes"] == accepted_value

    rejected_value = "PRIVATE_SENTINEL_" + ("B" * (32_768 - len("PRIVATE_SENTINEL_")))
    rejected = _make_parsed_app(raw_record={"Application ID": "APP-LIMIT", "Notes": rejected_value})
    with pytest.raises(CampaignPlanError) as exc_info:
        plan_campaign_import(_make_parsed_campaign([rejected]), now)

    assert "tracker record" in str(exc_info.value).lower()
    assert "PRIVATE_SENTINEL" not in str(exc_info.value)


def test_transitive_immutability_including_task_and_events() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    app = _make_parsed_app(status="Applied", next_action="Review posting")
    campaign = _make_parsed_campaign([app])
    planned = plan_campaign_import(campaign, now)

    # 1. PlannedCampaign is frozen
    with pytest.raises(FrozenInstanceError):
        planned.campaign_name = "New name"  # type: ignore[misc]

    # 2. PlannedApplication is frozen
    p_app = planned.applications[0]
    with pytest.raises(FrozenInstanceError):
        p_app.job_title = "Changed"  # type: ignore[misc]

    # 3. PlannedEvent is frozen
    ev = p_app.events[0]
    with pytest.raises(FrozenInstanceError):
        ev.stage = "tampered"  # type: ignore[misc]

    # 4. Event payload is MappingProxyType
    assert isinstance(ev.payload, MappingProxyType)
    with pytest.raises(TypeError):
        ev.payload["import"] = False  # type: ignore[index]

    # 5. Job snapshot is MappingProxyType
    assert isinstance(p_app.job_snapshot, MappingProxyType)
    with pytest.raises(TypeError):
        p_app.job_snapshot["title"] = "Tampered"  # type: ignore[index]

    # 6. Collections are tuples
    assert isinstance(planned.applications, tuple)
    assert isinstance(p_app.events, tuple)

    # 7. PlannedTask is frozen dataclass
    assert p_app.task is not None
    with pytest.raises(FrozenInstanceError):
        p_app.task.status = "completed"  # type: ignore[misc]

    # 8. Task response is MappingProxyType: nested mutation fails
    assert isinstance(p_app.task.response, MappingProxyType)
    with pytest.raises(TypeError):
        p_app.task.response["status"] = "completed"  # type: ignore[index]

    # 9. Task event payload['task'] is MappingProxyType: nested mutation fails
    assert isinstance(p_app.task.event.payload, MappingProxyType)
    assert isinstance(p_app.task.event.payload["task"], MappingProxyType)
    with pytest.raises(TypeError):
        p_app.task.event.payload["task"]["status"] = "completed"  # type: ignore[index]


def test_pure_and_side_effect_free_with_real_archive_parsing(tmp_path: Path) -> None:
    # Snapshot directory state before planning
    repo_files_before = set(Path(".").rglob("*.db"))
    tmp_files_before = set(tmp_path.rglob("*"))

    zip_bytes = build_fictional_campaign_zip()
    parsed = parse_campaign_workspace(zip_bytes)

    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    plan1 = plan_campaign_import(parsed, now)
    plan2 = plan_campaign_import(parsed, now)

    # Pure idempotence: identical fields across runs
    assert len(plan1.applications) == len(plan2.applications) == 5
    for a1, a2 in zip(plan1.applications, plan2.applications):
        assert a1.source_application_id == a2.source_application_id
        assert a1.current_stage == a2.current_stage
        assert a1.revision == a2.revision
        assert a1.latest_event_at == a2.latest_event_at
        assert len(a1.events) == len(a2.events)
        assert (a1.task is None) == (a2.task is None)
        if a1.task and a2.task:
            assert a1.task.id == a2.task.id
            assert a1.task.title == a2.task.title
            assert a1.task.due_at == a2.task.due_at
            assert a1.task.priority == a2.task.priority
            assert dict(a1.task.response) == dict(a2.task.response)

    # Prove zero database or filesystem side effects
    repo_files_after = set(Path(".").rglob("*.db"))
    tmp_files_after = set(tmp_path.rglob("*"))
    assert repo_files_after == repo_files_before
    assert tmp_files_after == tmp_files_before


def test_identity_scope_validation_and_user_isolation() -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    app = _make_parsed_app(status="Applied", next_action="Review contract")
    campaign = _make_parsed_campaign([app])

    # Rejection of empty or whitespace identity_scope
    with pytest.raises(CampaignPlanError, match="identity_scope must be a non-empty string"):
        _raw_plan_campaign_import(campaign, now, identity_scope="")

    with pytest.raises(CampaignPlanError, match="identity_scope must be a non-empty string"):
        _raw_plan_campaign_import(campaign, now, identity_scope="   \t  ")

    # Cross-user isolation: distinct owners importing identical data get distinct deterministic IDs
    plan_user1 = _raw_plan_campaign_import(campaign, now, identity_scope="user:1")
    plan_user2 = _raw_plan_campaign_import(campaign, now, identity_scope="user:2")

    assert plan_user1.identity_scope == "user:1"
    assert plan_user2.identity_scope == "user:2"

    app1 = plan_user1.applications[0]
    app2 = plan_user2.applications[0]

    # Event IDs must be distinct across owners
    assert len(app1.events) == len(app2.events)
    for ev1, ev2 in zip(app1.events, app2.events):
        assert ev1.id != ev2.id
        assert ev1.event_type == ev2.event_type

    # Task and task_created event IDs must be distinct across owners
    assert app1.task is not None and app2.task is not None
    assert app1.task.id != app2.task.id
    assert app1.task.event.id != app2.task.event.id
    assert app1.next_action_task_id != app2.next_action_task_id
