import io
import json
import uuid
import zipfile

import pytest
from sqlalchemy import text

from backend.applications.models import Application, ApplicationEvent, ApplicationPacketArtifact
from backend.applications.packet_storage import all_packet_journals, reconcile_packet_journals
from backend.career.models import CandidateProfile
from backend.resumes.draft_service import ResumeDraftService
from backend.resumes.models import ResumeVersion
from backend.resumes.publication_service import ResumePublicationService
from backend.storage.atomic import resolve_data_path
from tests.backend.applications.test_application_api import (
    _complete_application_pack,
    _dossier_draft_body,
    _ready_application,
)
from tests.backend.applications.test_application_api import (
    readiness_storage as _readiness_storage,
)

readiness_storage = _readiness_storage


def packet_input(version, **extra):
    return (
        dict(
            expected_revision=1,
            cover_letter="I build dependable local systems.",
            requirement_matrix=[
                dict(
                    requirement="Operate systems", evidence_fact_ids=[version.selected_fact_ids[0]]
                )
            ],
        )
        | extra
    )


@pytest.mark.parametrize(
    "invalid", ["letter_placeholder", "answer_placeholder", "missing_claim", "unknown_fact"]
)
def test_invalid_materials_fail_closed_as_validation_errors_without_publication(
    client, auth_headers, db_session, test_user, readiness_storage, invalid
):
    version_id = _complete_application_pack(db_session, test_user)
    app_id = _ready_application(client, auth_headers, version_id)
    version = db_session.get(ResumeVersion, version_id)
    body = packet_input(version)
    if invalid == "letter_placeholder":
        body["cover_letter"] = "Dear [COMPANY]"
    elif invalid == "answer_placeholder":
        body["answers"] = [dict(question="Why this job?", answer="[INSERT ANSWER]")]
    else:
        body["evidence_claims"] = [
            dict(
                id="claim",
                text=(
                    "Absent from reviewed material"
                    if invalid == "missing_claim"
                    else body["cover_letter"]
                ),
                fact_ids=[
                    str(uuid.uuid4()) if invalid == "unknown_fact" else version.selected_fact_ids[0]
                ],
            )
        ]
    response = client.post(
        f"/api/v1/applications/{app_id}/dossiers", json=body, headers=auth_headers
    )
    assert response.status_code == 422, response.text
    assert db_session.query(ApplicationPacketArtifact).count() == 0
    assert db_session.query(ApplicationEvent).filter_by(event_type="dossier_published").count() == 0
    assert db_session.get(Application, app_id).revision == 1
    assert not all_packet_journals()


@pytest.mark.parametrize("failure", ["journal_cleanup", "commit_acknowledgement"])
def test_publication_preserves_committed_bytes_on_cleanup_or_ack_error(
    client, auth_headers, db_session, test_user, readiness_storage, monkeypatch, failure
):
    version_id = _complete_application_pack(db_session, test_user)
    app_id = _ready_application(client, auth_headers, version_id)
    version = db_session.get(ResumeVersion, version_id)
    if failure == "journal_cleanup":

        def fail_cleanup(_):
            raise OSError("synthetic cleanup failure")

        monkeypatch.setattr(
            "backend.applications.dossier_publication.remove_packet_journal", fail_cleanup
        )
    else:
        real_commit = db_session.commit

        def lose_ack():
            real_commit()
            raise OSError("synthetic lost acknowledgement")

        monkeypatch.setattr(db_session, "commit", lose_ack)
    response = client.post(
        f"/api/v1/applications/{app_id}/dossiers", json=packet_input(version), headers=auth_headers
    )
    assert response.status_code == 201, response.text
    artifact = db_session.query(ApplicationPacketArtifact).one()
    original = resolve_data_path(artifact.storage_path).read_bytes()
    download = client.get(
        f"/api/v1/applications/{app_id}/dossiers/{artifact.dossier_id}/download",
        headers=auth_headers,
    )
    assert download.status_code == 200 and download.content == original
    assert db_session.query(ApplicationEvent).filter_by(event_type="dossier_published").count() == 1
    if failure == "journal_cleanup":
        assert len(all_packet_journals()) == 1
        db_session.rollback()
        db_session.execute(text("BEGIN IMMEDIATE"))
        reconcile_packet_journals(db_session)
        db_session.rollback()
        assert not all_packet_journals()
        assert resolve_data_path(artifact.storage_path).read_bytes() == original


def test_published_packet_binding_is_immutable(
    client, auth_headers, db_session, test_user, readiness_storage
):
    version_id = _complete_application_pack(db_session, test_user)
    app_id = _ready_application(client, auth_headers, version_id)
    response = client.post(
        f"/api/v1/applications/{app_id}/dossiers",
        json=packet_input(db_session.get(ResumeVersion, version_id)),
        headers=auth_headers,
    )
    assert response.status_code == 201
    artifact = db_session.query(ApplicationPacketArtifact).one()
    original = artifact.sha256
    artifact.sha256 = "0" * 64
    with pytest.raises(ValueError, match="immutable"):
        db_session.flush()
    db_session.rollback()
    assert artifact.sha256 == original


def test_schema3_download_fails_on_missing_row_and_never_rebuilds(
    client, auth_headers, db_session, test_user, readiness_storage, monkeypatch
):
    version_id = _complete_application_pack(db_session, test_user)
    app_id = _ready_application(client, auth_headers, version_id)
    published = client.post(
        f"/api/v1/applications/{app_id}/dossiers",
        json=packet_input(db_session.get(ResumeVersion, version_id)),
        headers=auth_headers,
    )
    assert published.status_code == 201
    dossier_id = published.json()["dossiers"][0]["id"]
    db_session.query(ApplicationPacketArtifact).delete()
    db_session.commit()

    def forbidden(**_):
        pytest.fail("immutable packet was reconstructed")

    monkeypatch.setattr("backend.applications.dossier_download.build_dossier_bundle", forbidden)
    response = client.get(
        f"/api/v1/applications/{app_id}/dossiers/{dossier_id}/download", headers=auth_headers
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field", ["email_draft", "letter_options", "generation_provenance", "evidence_claims"]
)
def test_complete_saved_material_payload_must_match_publication(
    client, auth_headers, db_session, test_user, readiness_storage, field
):
    version_id = _complete_application_pack(db_session, test_user)
    app_id = _ready_application(client, auth_headers, version_id)
    version = db_session.get(ResumeVersion, version_id)
    draft = _dossier_draft_body(
        application_revision=1,
        resume_version_id=version_id,
        evidence_fact_id=version.selected_fact_ids[0],
    )
    saved = client.put(
        f"/api/v1/applications/{app_id}/dossier-draft", json=draft, headers=auth_headers
    )
    assert saved.status_code == 200
    content = draft["content"]
    body = dict(
        expected_revision=1,
        expected_draft_revision=1,
        cover_letter=content["cover_letter"],
        answers=[{k: v for k, v in row.items() if k != "client_id"} for row in content["answers"]],
        checklist=[
            {k: v for k, v in row.items() if k != "client_id"} for row in content["checklist"]
        ],
        requirement_matrix=[
            {k: v for k, v in row.items() if k != "client_id"}
            for row in content["requirement_matrix"]
        ],
    )
    body[field] = {
        "email_draft": dict(subject="Changed after save", body="Unreviewed text"),
        "letter_options": dict(date="2026-09-13"),
        "generation_provenance": dict(source="manual"),
        "evidence_claims": [
            dict(
                id="new-claim",
                text=content["cover_letter"],
                fact_ids=[version.selected_fact_ids[0]],
            )
        ],
    }[field]
    rejected = client.post(
        f"/api/v1/applications/{app_id}/dossiers", json=body, headers=auth_headers
    )
    assert rejected.status_code == 409
    assert db_session.query(ApplicationPacketArtifact).count() == 0
    assert db_session.get(Application, app_id).revision == 1


@pytest.mark.parametrize("preset", ["software-en", "swiss-software-de"])
def test_material_evidence_and_sender_survive_packet_and_download_without_rendering(
    client, auth_headers, db_session, test_user, readiness_storage, monkeypatch, preset
):
    version_id = _complete_application_pack(db_session, test_user)
    app_id = _ready_application(client, auth_headers, version_id)
    version = db_session.get(ResumeVersion, version_id)
    body = packet_input(
        version,
        letter_options={"preset_id": preset, "date": "2026-09-13"},
        generation_provenance={
            "source": "external-agent",
            "request_id": str(uuid.uuid4()),
            "grant_id": str(uuid.uuid4()),
            "input_digest": "a" * 64,
            "payload_digest": "b" * 64,
            "generated_at": "2026-09-13T12:00:00Z",
        },
        evidence_claims=[
            dict(
                id="letter-1",
                text="I build dependable local systems.",
                fact_ids=[version.selected_fact_ids[0]],
            )
        ],
    )
    published = client.post(
        f"/api/v1/applications/{app_id}/dossiers", json=body, headers=auth_headers
    )
    assert published.status_code == 201, published.text
    artifact = db_session.query(ApplicationPacketArtifact).one()

    def forbidden(**_):
        pytest.fail("download rendered a new letter")

    monkeypatch.setattr(
        "backend.applications.dossier_materials.generate_letter_artifacts", forbidden
    )
    download = client.get(
        f"/api/v1/applications/{app_id}/dossiers/{artifact.dossier_id}/download",
        headers=auth_headers,
    )
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert json.loads(archive.read("material-evidence.json")) == body["evidence_claims"]
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["generation_provenance"] == body["generation_provenance"]
        assert "material-evidence.json" in {item["path"] for item in manifest["entries"]}
        from pypdf import PdfReader

        letter = PdfReader(io.BytesIO(archive.read("cover_letter.pdf"))).pages[0].extract_text()
        assert version.snapshot["profile"]["display_name"] in letter
        assert version.snapshot["profile"]["email"] in letter
        assert ("Bewerbung als" if preset.endswith("-de") else "Application for") in letter


@pytest.mark.parametrize("profile_changed", [False, True])
def test_unpublished_binding_requires_explicit_current_cv_and_uses_its_readiness(
    client, auth_headers, db_session, test_user, readiness_storage, profile_changed
):
    old_id = _complete_application_pack(db_session, test_user)
    version = db_session.get(ResumeVersion, old_id)
    resume_id = version.draft_id
    app_id = _ready_application(client, auth_headers, None)
    content = dict(
        cover_letter="I build dependable local systems.",
        requirement_matrix=[
            dict(
                client_id="requirement-1",
                requirement="Operate systems",
                evidence_fact_ids=[version.selected_fact_ids[0]],
            )
        ],
    )
    saved = client.put(
        f"/api/v1/applications/{app_id}/dossier-draft",
        headers=auth_headers,
        json=dict(
            expected_application_revision=1,
            resume_draft_id=resume_id,
            expected_resume_draft_revision=1,
            content=content,
        ),
    )
    assert saved.status_code == 200, saved.text
    body = packet_input(version, expected_draft_revision=1)
    missing = client.post(
        f"/api/v1/applications/{app_id}/dossiers", json=body, headers=auth_headers
    )
    assert missing.status_code == 422
    old = client.post(
        f"/api/v1/applications/{app_id}/dossiers",
        json=body | {"resume_version_id": old_id},
        headers=auth_headers,
    )
    assert old.status_code == 409
    if profile_changed:
        profile = db_session.query(CandidateProfile).filter_by(user_id=test_user.id).one()
        profile.revision += 1
        profile.headline = "Updated approved headline"
        db_session.commit()
    current = ResumePublicationService(db_session, ResumeDraftService(db_session)).publish(
        test_user.id, resume_id
    )
    assert db_session.get(ResumeVersion, current.id).snapshot["resume"]["draft_revision"] == 1
    published = client.post(
        f"/api/v1/applications/{app_id}/dossiers",
        json=body | {"resume_version_id": current.id},
        headers=auth_headers,
    )
    if profile_changed:
        assert published.status_code == 409, published.text
        assert db_session.query(ApplicationPacketArtifact).count() == 0
        assert db_session.get(Application, app_id).revision == 1
        return
    assert published.status_code == 201, published.text
    response = published.json()
    assert response["resume_version_id"] == current.id
    assert response["dossiers"][0]["resume_version_id"] == current.id
