from __future__ import annotations

import hashlib
import json

import pytest

from backend.career.models import CandidateProfile, CareerAsset, SourceDocument
from backend.career.sources import import_source_document
from backend.models import User
from backend.storage.atomic import read_verified

CONTENT = b"PRIVATE_SOURCE_SENTINEL: synthetic engineering evidence."
INTEGRITY_ERROR = "The stored source document failed its integrity check"


def _upload(client, headers, role="profile"):
    return client.post(
        "/api/v1/career-profile/sources",
        headers=headers,
        files={"file": ("synthetic.txt", CONTENT, "text/plain")},
        data={"source_role": role},
    )


def _rows_fingerprint(db):
    db.expire_all()
    rows = {
        model.__tablename__: [
            {column.name: getattr(row, column.name) for column in model.__table__.columns}
            for row in db.query(model).order_by(model.id).all()
        ]
        for model in (CandidateProfile, CareerAsset, SourceDocument)
    }
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def _stored_files(vault):
    assets = vault / "assets"
    return {
        path.relative_to(vault).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in assets.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def source_reuse(client, auth_headers, db_session, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    monkeypatch.setattr("backend.career.sources.settings.DATA_DIR", str(vault))
    profile_response = client.put(
        "/api/v1/career-profile",
        headers=auth_headers,
        json={
            "expected_revision": 0,
            "display_name": "Synthetic source owner",
            "facts": [],
            "goals": [],
        },
    )
    assert profile_response.status_code == 200
    initial = _upload(client, auth_headers)
    assert initial.status_code == 201
    payload = initial.json()
    asset = db_session.get(CareerAsset, payload["asset_id"])
    source = db_session.get(SourceDocument, payload["id"])
    other_user = User(username="source-reuse-other", hashed_password="not-used")
    db_session.add(other_user)
    db_session.flush()
    other_profile = CandidateProfile(user_id=other_user.id, display_name="Other synthetic owner")
    db_session.add(other_profile)
    db_session.commit()
    return vault, source, asset, other_profile


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "corrupt",
        "wrong_size",
        "zero_size",
        "normalized",
        "wrong_media",
        "wrong_document_type",
        "wrong_name",
        "text_digest",
        "wrong_sha",
        "noncanonical_path",
        "escaped_path",
        "foreign_source",
        "foreign_asset",
        "orphan_source",
    ],
)
def test_duplicate_source_rejects_invalid_storage_without_mutation(
    damage, source_reuse, client, auth_headers, db_session, tmp_path
):
    vault, source, asset, other_profile = source_reuse
    target = (vault / asset.storage_path).resolve()
    target.relative_to(vault.resolve())
    outside = tmp_path / "private-path-sentinel.txt"
    outside.write_bytes(CONTENT)
    if damage == "missing":
        target.unlink()
    elif damage == "corrupt":
        target.write_bytes(b"X" * len(CONTENT))
    elif damage == "wrong_size":
        asset.byte_size += 1
    elif damage == "zero_size":
        asset.byte_size = 0
    elif damage == "normalized":
        asset.normalized = True
    elif damage == "wrong_media":
        asset.media_type = "application/x-private-metadata-sentinel"
    elif damage == "wrong_document_type":
        source.document_type = "private-type-sentinel"
    elif damage == "wrong_name":
        asset.original_name = "private-name-sentinel.exe"
    elif damage == "text_digest":
        source.extracted_text_sha256 = "0" * 64
    elif damage == "wrong_sha":
        asset.sha256 = "0" * 64
    elif damage == "noncanonical_path":
        asset.storage_path = f"assets/{asset.sha256[:2]}/../{asset.sha256[:2]}/{asset.sha256}"
    elif damage == "escaped_path":
        asset.storage_path = str(outside)
    elif damage == "foreign_source":
        source.profile_id = other_profile.id
    elif damage == "foreign_asset":
        asset.profile_id = other_profile.id
    elif damage == "orphan_source":
        db_session.delete(source)
    db_session.commit()
    before_rows = _rows_fingerprint(db_session)
    before_files = _stored_files(vault)
    outside_hash = hashlib.sha256(outside.read_bytes()).hexdigest()

    response = _upload(client, auth_headers)

    assert response.status_code == 422
    assert response.json() == {"detail": INTEGRITY_ERROR}
    assert _rows_fingerprint(db_session) == before_rows
    assert _stored_files(vault) == before_files
    assert hashlib.sha256(outside.read_bytes()).hexdigest() == outside_hash
    assert client.get("/api/v1/career-profile", headers=auth_headers).status_code == 200


def test_healthy_duplicate_source_preserves_rows_bytes_and_revisions(
    source_reuse, client, auth_headers, db_session
):
    vault, source, asset, _other_profile = source_reuse
    source_id = source.id
    before_rows = _rows_fingerprint(db_session)
    before_files = _stored_files(vault)

    response = _upload(client, auth_headers)

    assert response.status_code == 201
    assert response.json()["id"] == source_id
    assert _rows_fingerprint(db_session) == before_rows
    assert _stored_files(vault) == before_files
    assert (
        read_verified(
            asset.storage_path,
            asset.sha256,
            expected_size=asset.byte_size,
            maximum_size=len(CONTENT),
        )
        == CONTENT
    )


def test_healthy_duplicate_role_conflict_still_returns_conflict(
    source_reuse, client, auth_headers, db_session
):
    vault, _source, _asset, _other_profile = source_reuse
    before_rows = _rows_fingerprint(db_session)
    before_files = _stored_files(vault)

    response = _upload(client, auth_headers, role="narrative")

    assert response.status_code == 409
    assert _rows_fingerprint(db_session) == before_rows
    assert _stored_files(vault) == before_files


def test_shared_source_bytes_keep_distinct_owned_records_and_validate_reuse(
    source_reuse, client, auth_headers, db_session
):
    vault, source, asset, other_profile = source_reuse
    original_source_id, original_asset_id = source.id, asset.id
    original_path = asset.storage_path
    other = import_source_document(
        db_session,
        user_id=other_profile.user_id,
        filename="other.txt",
        media_type="text/plain",
        data=CONTENT,
    )
    assert other.id != original_source_id
    assert other.asset_id != original_asset_id
    assert db_session.get(CareerAsset, other.asset_id).storage_path == original_path
    assert len(_stored_files(vault)) == 1
    before_rows = _rows_fingerprint(db_session)
    before_files = _stored_files(vault)

    response = _upload(client, auth_headers)

    assert response.status_code == 201
    assert response.json()["id"] == original_source_id
    assert _rows_fingerprint(db_session) == before_rows
    assert _stored_files(vault) == before_files
