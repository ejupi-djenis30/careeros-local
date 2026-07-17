import pytest

from backend.applications.models import ApplicationEvent
from backend.models import Job, ScrapedJob


def _job(db_session, test_user):
    scraped = ScrapedJob(
        platform="fixture",
        platform_job_id="application-job",
        title="Local Platform Engineer",
        company="Local Systems AG",
        description="Build reliable local infrastructure.",
        location="Zurich",
        external_url="https://example.test/jobs/local-platform",
        normalization_status="provider_bootstrap",
        normalized_domain="it",
        normalized_required_skills=["python", "sqlite"],
    )
    db_session.add(scraped)
    db_session.flush()
    job = Job(
        user_id=test_user.id,
        scraped_job_id=scraped.id,
        affinity_score=82,
        affinity_analysis="Deterministic local match",
        worth_applying=True,
        applied=False,
        dismissed=False,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_application_timeline_is_append_only_and_revisioned(
    client, auth_headers, db_session, test_user
):
    job = _job(db_session, test_user)
    created = client.post(
        "/api/v1/applications",
        json={"job_id": job.id, "initial_stage": "saved", "note": "Promising role"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    application = created.json()
    assert application["revision"] == 1
    assert application["current_stage"] == "saved"
    assert application["job_snapshot"]["title"] == "Local Platform Engineer"
    assert application["job_snapshot"]["description"] == "Build reliable local infrastructure."
    assert len(application["events"]) == 1

    preparing = client.post(
        f"/api/v1/applications/{application['id']}/events",
        json={
            "expected_revision": 1,
            "event_type": "stage",
            "stage": "preparing",
            "note": "Tailoring the resume",
        },
        headers=auth_headers,
    )
    assert preparing.status_code == 201, preparing.text
    assert preparing.json()["revision"] == 2
    assert preparing.json()["current_stage"] == "preparing"

    note = client.post(
        f"/api/v1/applications/{application['id']}/events",
        json={
            "expected_revision": 2,
            "event_type": "note",
            "note": "Research hiring manager",
        },
        headers=auth_headers,
    )
    assert note.status_code == 201, note.text
    assert note.json()["revision"] == 3
    assert note.json()["current_stage"] == "preparing"
    assert [event["event_type"] for event in note.json()["events"]] == [
        "stage",
        "stage",
        "note",
    ]

    stale = client.post(
        f"/api/v1/applications/{application['id']}/events",
        json={"expected_revision": 1, "event_type": "stage", "stage": "applied"},
        headers=auth_headers,
    )
    assert stale.status_code == 409
    invalid = client.post(
        f"/api/v1/applications/{application['id']}/events",
        json={"expected_revision": 3, "event_type": "stage", "stage": "accepted"},
        headers=auth_headers,
    )
    assert invalid.status_code == 409

    listing = client.get("/api/v1/applications", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()[0]["title"] == "Local Platform Engineer"
    assert "job_snapshot" not in listing.json()[0]

    assert client.get(
        "/api/v1/applications?offset=1&limit=1", headers=auth_headers
    ).json() == []
    assert client.get(
        "/api/v1/applications?limit=0", headers=auth_headers
    ).status_code == 422

    event = db_session.query(ApplicationEvent).filter(ApplicationEvent.event_type == "note").one()
    event.note = "Attempted edit"
    with pytest.raises(ValueError, match="append-only"):
        db_session.commit()
    db_session.rollback()


def test_application_rejects_unowned_or_duplicate_job(client, auth_headers, db_session, test_user):
    job = _job(db_session, test_user)
    first = client.post("/api/v1/applications", json={"job_id": job.id}, headers=auth_headers)
    assert first.status_code == 201
    duplicate = client.post("/api/v1/applications", json={"job_id": job.id}, headers=auth_headers)
    assert duplicate.status_code == 409
    missing = client.post("/api/v1/applications", json={"job_id": 999999}, headers=auth_headers)
    assert missing.status_code == 422


def test_application_accepts_a_safe_manual_job_snapshot(client, auth_headers):
    created = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Platform Engineer",
                "company": "Private Local Company",
                "description": "A posting captured manually after the source disappeared.",
                "location": "Bern",
                "external_url": "HTTPS://EXAMPLE.TEST/jobs/../jobs/platform#apply",
            },
            "initial_stage": "applied",
            "note": "Applied outside the discovery workflow",
        },
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["job_id"] is None
    assert body["job_snapshot"]["platform"] == "manual"
    assert body["job_snapshot"]["title"] == "Platform Engineer"
    assert body["job_snapshot"]["external_url"] == "https://example.test/jobs/platform"
    assert body["events"][0]["stage"] == "applied"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///private/cv.txt"])
def test_application_rejects_unsafe_manual_job_urls(client, auth_headers, url):
    response = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Unsafe role",
                "company": "Unknown",
                "external_url": url,
            }
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_application_requires_authentication(client):
    assert client.get("/api/v1/applications").status_code == 401
