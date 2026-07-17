import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fitz
import pytest
from docx import Document
from PIL import Image

from backend.career.models import CareerAsset
from backend.resumes.models import ResumeVersion


def _profile_payload(expected_revision=0):
    return {
        "expected_revision": expected_revision,
        "display_name": "Ada Lovelace",
        "headline": "Analytical Engineer",
        "summary": "Builds rigorous, human-centered computing systems.",
        "email": "ada@example.test",
        "phone": "+41 79 000 00 00",
        "location": {"city": "Zurich", "country": "CH"},
        "website": "https://ada.example.test",
        "preferences": {},
        "facts": [
            {
                "fact_type": "experience",
                "position": 0,
                "verification_status": "confirmed",
                "payload": {
                    "role": "Analytical Engineer",
                    "organization": "Independent",
                    "start_date": "1842-01-01",
                    "end_date": "1843-12-31",
                    "description": "Designed methods for a general-purpose engine.",
                    "achievements": ["Published an algorithm grounded in machine operations."],
                },
            },
            {
                "fact_type": "skill",
                "position": 1,
                "verification_status": "confirmed",
                "payload": {"name": "Algorithm design", "level": "expert", "years": 4},
            },
            {
                "fact_type": "language",
                "position": 2,
                "verification_status": "confirmed",
                "payload": {"language": "English", "level": "native"},
            },
        ],
        "goals": [],
    }


def _create_profile(client, auth_headers):
    response = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


def _draft_payload(profile, *, template="ats", photo_asset_id=None):
    payload = {
        "title": "Analytical Engineer Resume",
        "template_kind": template,
        "selected_fact_ids": [fact["id"] for fact in profile["facts"]],
        "section_config": {
            "order": ["experience", "skill", "language"],
            "include_summary": True,
            "include_email": True,
            "include_phone": True,
            "include_location": True,
            "include_links": True,
        },
        "content_overrides": {},
    }
    if photo_asset_id:
        payload["photo_asset_id"] = photo_asset_id
    return payload


def test_ats_resume_publishes_text_extractable_immutable_artifacts(
    client, auth_headers, db_session, monkeypatch
):
    with TemporaryDirectory(dir="cmd_outputs") as directory:
        monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", directory)
        profile = _create_profile(client, auth_headers)
        created = client.post("/api/v1/resumes", json=_draft_payload(profile), headers=auth_headers)
        assert created.status_code == 201, created.text
        draft = created.json()

        stale_payload = _draft_payload(profile)
        stale_payload["expected_revision"] = 99
        stale = client.put(
            f"/api/v1/resumes/{draft['id']}", json=stale_payload, headers=auth_headers
        )
        assert stale.status_code == 409

        published = client.post(f"/api/v1/resumes/{draft['id']}/publish", headers=auth_headers)
        assert published.status_code == 201, published.text
        version = published.json()
        assert version["semantic_version"] == "1.0.0"
        assert version["quality_report"]["layout"] == "single-column"
        assert version["quality_report"]["pdf_image_count"] == 0
        assert {item["format"] for item in version["artifacts"]} == {"pdf", "docx"}

        artifacts = {item["format"]: item for item in version["artifacts"]}
        pdf_response = client.get(
            f"/api/v1/resume-artifacts/{artifacts['pdf']['id']}", headers=auth_headers
        )
        assert pdf_response.status_code == 200
        assert hashlib.sha256(pdf_response.content).hexdigest() == artifacts["pdf"]["sha256"]
        with fitz.open(stream=pdf_response.content, filetype="pdf") as pdf:
            text = "\n".join(page.get_text() for page in pdf)
            assert "Ada Lovelace" in text
            assert "EXPERIENCE" in text
            assert sum(len(page.get_images(full=True)) for page in pdf) == 0

        docx_response = client.get(
            f"/api/v1/resume-artifacts/{artifacts['docx']['id']}", headers=auth_headers
        )
        assert docx_response.status_code == 200
        document = Document(BytesIO(docx_response.content))
        assert "Algorithm design" in "\n".join(p.text for p in document.paragraphs)

        persisted = db_session.query(ResumeVersion).filter(ResumeVersion.id == version["id"]).one()
        original_hash = persisted.snapshot_sha256
        update = _profile_payload(expected_revision=profile["revision"])
        update["headline"] = "Changed after publication"
        for index, fact in enumerate(update["facts"]):
            fact["id"] = profile["facts"][index]["id"]
        assert (
            client.put("/api/v1/career-profile", json=update, headers=auth_headers).status_code
            == 200
        )
        db_session.expire_all()
        persisted = db_session.query(ResumeVersion).filter(ResumeVersion.id == version["id"]).one()
        assert persisted.snapshot_sha256 == original_hash
        assert persisted.snapshot["profile"]["headline"] == "Analytical Engineer"
        persisted.semantic_version = "9.9.9"
        with pytest.raises(ValueError, match="immutable"):
            db_session.commit()
        db_session.rollback()


def test_resume_rejects_missing_fact_and_ats_photo(client, auth_headers):
    profile = _create_profile(client, auth_headers)
    missing = _draft_payload(profile)
    missing["selected_fact_ids"] = [str(uuid4())]
    response = client.post("/api/v1/resumes", json=missing, headers=auth_headers)
    assert response.status_code == 422
    assert "missing career facts" in response.text

    ats_with_photo = _draft_payload(profile, photo_asset_id=str(uuid4()))
    response = client.post("/api/v1/resumes", json=ats_with_photo, headers=auth_headers)
    assert response.status_code == 422
    assert "ATS resumes cannot reference a photo" in response.text


def test_photo_resume_strips_exif_and_embeds_only_normalized_photo(
    client, auth_headers, db_session, monkeypatch
):
    with TemporaryDirectory(dir="cmd_outputs") as directory:
        monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", directory)
        profile = _create_profile(client, auth_headers)
        source = Image.new("RGB", (1200, 800), (62, 89, 120))
        exif = Image.Exif()
        exif[0x010E] = "private description"
        original = BytesIO()
        source.save(original, format="JPEG", exif=exif)
        original_bytes = original.getvalue()

        uploaded = client.post(
            "/api/v1/career-profile/photo",
            files={"file": ("portrait.jpg", original_bytes, "image/jpeg")},
            headers=auth_headers,
        )
        assert uploaded.status_code == 201, uploaded.text
        photo = uploaded.json()
        asset = db_session.query(CareerAsset).filter(CareerAsset.id == photo["id"]).one()
        normalized_path = Path(directory) / asset.storage_path
        normalized_bytes = normalized_path.read_bytes()
        assert normalized_bytes != original_bytes
        with Image.open(BytesIO(normalized_bytes)) as image:
            assert not image.getexif()
            assert image.size == (720, 720)

        created = client.post(
            "/api/v1/resumes",
            json=_draft_payload(profile, template="photo", photo_asset_id=photo["id"]),
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        published = client.post(
            f"/api/v1/resumes/{created.json()['id']}/publish", headers=auth_headers
        )
        assert published.status_code == 201, published.text
        quality = published.json()["quality_report"]
        assert quality["pdf_image_count"] >= 1
        assert quality["docx_image_count"] >= 1


def test_resume_artifact_requires_owner(client, auth_headers):
    assert (
        client.get(f"/api/v1/resume-artifacts/{uuid4()}", headers=auth_headers).status_code == 404
    )


def test_generate_resume_endpoint_creates_goal_aware_canvas(
    client, auth_headers, saved_detailed_profile
):
    goal = saved_detailed_profile["goals"][0]
    response = client.post(
        "/api/v1/resumes/generate",
        json={
            "title": "Leadership resume",
            "template_kind": "ats",
            "career_goal_id": goal["id"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["profile_revision"] == saved_detailed_profile["revision"]
    assert draft["generation_context"]["mode"] == "deterministic"
    assert draft["generation_context"]["career_goal_id"] == goal["id"]
    assert draft["canvas_document"]["schema_version"] == 1
    assert draft["canvas_document"]["style"]["columns"] == 1
    assert {section["kind"] for section in draft["canvas_document"]["sections"]} >= {
        "identity",
        "summary",
        "experience",
        "education",
        "skill",
    }
    assert set(draft["selected_fact_ids"]) == {
        fact["id"]
        for fact in saved_detailed_profile["facts"]
        if fact["verification_status"] == "confirmed"
    }

    loaded = client.get(f"/api/v1/resumes/{draft['id']}", headers=auth_headers)
    assert loaded.status_code == 200
    assert loaded.json()["canvas_document"] == draft["canvas_document"]


def test_generate_resume_rejects_foreign_goal(client, auth_headers, saved_detailed_profile):
    response = client.post(
        "/api/v1/resumes/generate",
        json={
            "title": "Invalid target",
            "template_kind": "ats",
            "career_goal_id": str(uuid4()),
        },
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "career goal" in response.text.casefold()


def test_promote_claim_rejects_missing_block_without_mutating_profile(
    client, auth_headers, saved_detailed_profile
):
    created = client.post(
        "/api/v1/resumes/generate",
        json={"title": "Promotion guard", "template_kind": "ats"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    draft = created.json()

    response = client.post(
        f"/api/v1/resumes/{draft['id']}/claims/promote",
        json={
            "expected_revision": draft["revision"],
            "expected_profile_revision": saved_detailed_profile["revision"],
            "block_id": "manual-missing",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "not found" in response.text.casefold()
    profile = client.get("/api/v1/career-profile", headers=auth_headers)
    assert profile.status_code == 200
    assert profile.json()["revision"] == saved_detailed_profile["revision"]
