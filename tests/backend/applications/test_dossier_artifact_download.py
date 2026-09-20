import copy
import hashlib
import io
import json
import zipfile

import pytest
from sqlalchemy import update

from backend.applications.dossier_download import DossierDownloadService
from backend.applications.exceptions import ApplicationValidationError
from backend.applications.exports import DossierBundle, build_dossier_bundle
from backend.applications.models import Application, ApplicationEvent, ApplicationPacketArtifact
from backend.applications.packet_storage import packet_artifact_path
from backend.models.user import User
from backend.resumes.models import ResumeVersion
from backend.resumes.schemas import ResumeVersionResponse
from backend.storage.atomic import resolve_data_path
from tests.backend.applications.test_application_api import (
    _complete_application_pack,
    _ready_application,
)
from tests.backend.applications.test_application_api import readiness_storage as _readiness_storage
from tests.backend.applications.test_packet_publication import packet_input

readiness_storage = _readiness_storage


@pytest.fixture
def published_packet(client, auth_headers, db_session, test_user, readiness_storage):
    version_id = _complete_application_pack(db_session, test_user)
    app_id = _ready_application(client, auth_headers, version_id)
    version = db_session.get(ResumeVersion, version_id)
    response = client.post(
        f"/api/v1/applications/{app_id}/dossiers",
        headers=auth_headers,
        json=packet_input(
            version,
            letter_options={"date": "2026-09-13"},
            email_draft={
                "subject": "Application",
                "body": "Please find my selected documents.",
                "attachment_names": ["resume.pdf", "cover_letter.pdf"],
            },
        ),
    )
    assert response.status_code == 201, response.text
    artifact = db_session.query(ApplicationPacketArtifact).one()
    raw = resolve_data_path(artifact.storage_path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    return app_id, artifact.dossier_id, artifact, files


@pytest.mark.parametrize(
    "filename",
    [
        "resume.pdf",
        "resume.docx",
        "cover_letter.pdf",
        "cover_letter.docx",
        "email_draft.eml",
        "email_checklist.txt",
    ],
)
def test_owned_artifact_download_matches_original_bytes_and_safe_headers(
    client, auth_headers, published_packet, filename
):
    app_id, dossier_id, _, files = published_packet
    response = client.get(
        f"/api/v1/applications/{app_id}/dossiers/{dossier_id}/artifacts/{filename}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.content == files[filename]
    assert response.headers["x-content-sha256"] == hashlib.sha256(files[filename]).hexdigest()
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="careeros-{dossier_id}-{filename}"'
    )
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"
    expected = (
        "application/pdf"
        if filename.endswith("pdf")
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if filename.endswith("docx")
        else "message/rfc822"
        if filename.endswith("eml")
        else "text/plain"
    )
    assert response.headers["content-type"].startswith(expected)


@pytest.mark.parametrize(
    "name",
    [
        "unknown.pdf",
        "manifest.json",
        "..%2Fresume.pdf",
        "..%5Cresume.pdf",
        "resume.pdf%0D%0AX-Test:yes",
    ],
)
def test_unselected_or_pathlike_artifact_names_are_not_downloadable(
    client, auth_headers, published_packet, name
):
    app_id, dossier_id, _, _ = published_packet
    response = client.get(
        f"/api/v1/applications/{app_id}/dossiers/{dossier_id}/artifacts/{name}",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.parametrize("damage", ["manifest", "bytes", "owner"])
def test_artifact_route_rejects_corruption_and_other_owners(
    client, auth_headers, db_session, published_packet, damage
):
    app_id, dossier_id, artifact, _ = published_packet
    if damage == "manifest":
        event = db_session.get(ApplicationEvent, dossier_id)
        payload = copy.deepcopy(event.payload)
        payload["dossier"]["manifest"]["entries"][0]["sha256"] = "0" * 64
        db_session.execute(
            update(ApplicationEvent)
            .where(ApplicationEvent.id == dossier_id)
            .values(payload=payload)
        )
        db_session.commit()
    elif damage == "bytes":
        path = resolve_data_path(artifact.storage_path)
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    else:
        user = User(username="other-artifact-owner", hashed_password="unused")
        db_session.add(user)
        db_session.flush()
        db_session.execute(
            update(Application).where(Application.id == app_id).values(user_id=user.id)
        )
        db_session.commit()
    response = client.get(
        f"/api/v1/applications/{app_id}/dossiers/{dossier_id}/artifacts/resume.pdf",
        headers=auth_headers,
    )
    assert response.status_code == (404 if damage == "owner" else 422)


def test_packet_download_rejects_duplicate_manifest_keys_even_with_matching_digests(
    client, auth_headers, db_session, published_packet, monkeypatch
):
    app_id, dossier_id, artifact, files = published_packet
    manifest = json.loads(files["manifest.json"])
    duplicate_manifest = (
        '{"application_id":'
        + json.dumps(manifest["application_id"], separators=(",", ":"))
        + ","
        + files["manifest.json"].decode("utf-8").lstrip()[1:]
    ).encode("utf-8")
    assert json.loads(duplicate_manifest) == manifest
    files["manifest.json"] = duplicate_manifest
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    packet_bytes = output.getvalue()
    digest = hashlib.sha256(packet_bytes).hexdigest()

    storage_path = packet_artifact_path(
        application_id=app_id,
        dossier_id=dossier_id,
        sha256=digest,
    )
    event = db_session.get(ApplicationEvent, dossier_id)
    payload = copy.deepcopy(event.payload)
    payload["dossier"]["manifest_sha256"] = hashlib.sha256(duplicate_manifest).hexdigest()
    db_session.execute(
        update(ApplicationPacketArtifact)
        .where(ApplicationPacketArtifact.id == artifact.id)
        .values(sha256=digest, byte_size=len(packet_bytes), storage_path=storage_path)
    )
    db_session.execute(
        update(ApplicationEvent).where(ApplicationEvent.id == dossier_id).values(payload=payload)
    )
    db_session.commit()
    monkeypatch.setattr(
        "backend.applications.dossier_download.read_verified_packet_artifact",
        lambda *_args, **_kwargs: packet_bytes,
    )

    response = client.get(
        f"/api/v1/applications/{app_id}/dossiers/{dossier_id}/download",
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_historical_packet_uses_only_its_original_declared_files(
    client, auth_headers, db_session, published_packet
):
    app_id, dossier_id, _, files = published_packet
    event = db_session.get(ApplicationEvent, dossier_id)
    payload = copy.deepcopy(event.payload)
    dossier = payload["dossier"]
    bundle = build_dossier_bundle(
        dossier_id=dossier_id,
        application_id=app_id,
        **{
            key: dossier[key]
            for key in [
                "version_number",
                "application_revision",
                "created_at",
                "role",
                "resume_version_id",
                "readiness",
                "cover_letter",
                "answers",
                "checklist",
                "requirement_matrix",
                "evidence_catalog",
            ]
        },
        resume_artifacts={
            "pdf": (files["resume.pdf"], "application/pdf"),
            "docx": (
                files["resume.docx"],
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
    )
    dossier.update(
        schema_version="2.0", manifest=bundle.manifest, manifest_sha256=bundle.manifest_sha256
    )
    db_session.execute(
        update(ApplicationEvent).where(ApplicationEvent.id == dossier_id).values(payload=payload)
    )
    db_session.commit()
    url = f"/api/v1/applications/{app_id}/dossiers/{dossier_id}/artifacts/"
    assert client.get(url + "resume.pdf", headers=auth_headers).content == files["resume.pdf"]
    assert client.get(url + "cover_letter.pdf", headers=auth_headers).status_code == 404


def test_member_digest_is_verified_even_when_zip_digest_matches(monkeypatch):
    data = b"changed member"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("resume.pdf", data)
    bundle = DossierBundle(
        output.getvalue(),
        "a" * 64,
        {
            "entries": [
                {
                    "path": "resume.pdf",
                    "media_type": "application/pdf",
                    "byte_size": len(data),
                    "sha256": "0" * 64,
                }
            ]
        },
        "b" * 64,
    )
    service = DossierDownloadService(None)
    monkeypatch.setattr(service, "dossier_bundle", lambda *args: bundle)
    with pytest.raises(ApplicationValidationError, match="could not be verified"):
        service.dossier_artifact(1, "application", "dossier", "resume.pdf", None)


@pytest.mark.parametrize("snapshot, expected", [({}, None), ({"resume": {"draft_revision": 7}}, 7)])
def test_version_response_revision_comes_only_from_snapshot(
    db_session, test_user, readiness_storage, snapshot, expected
):
    version_id = _complete_application_pack(db_session, test_user)
    version = db_session.get(ResumeVersion, version_id)
    version.snapshot = snapshot
    result = ResumeVersionResponse.model_validate(version)
    assert result.draft_revision == expected
    assert result.profile_revision == 3
    assert result.model_dump()["draft_revision"] == expected
    db_session.rollback()
