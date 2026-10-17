"""Malformed ZIP containers fail validation without leaving maintenance pending."""

import struct
import zipfile
from io import BytesIO

import pytest

from backend.career.models import CandidateProfile
from backend.core.config import settings
from backend.models import User
from backend.models.user import VAULT_STATE_READY
from backend.portability.archive import ArchiveError, _validated_members
from backend.portability.journal import read_restore_journal


@pytest.fixture
def compressed_archive_vault(client, auth_headers, db_session, test_user, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    created = client.put(
        "/api/v1/career-profile",
        headers=auth_headers,
        json={"expected_revision": 0, "display_name": "Synthetic Archive Account"},
    )
    assert created.status_code == 200
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200
    profile = db_session.query(CandidateProfile).filter_by(user_id=test_user.id).one()
    before = (profile.id, profile.revision, profile.display_name)
    return exported.content, before


def _corrupted_zip(archive_data: bytes, corruption: str) -> tuple[bytes, bytes]:
    compression = zipfile.ZIP_LZMA if corruption == "lzma" else zipfile.ZIP_DEFLATED
    output = BytesIO()
    with zipfile.ZipFile(BytesIO(archive_data)) as source:
        with zipfile.ZipFile(output, "w", compression=compression) as target:
            for name in source.namelist():
                target.writestr(name, source.read(name))
    valid = output.getvalue()
    damaged = bytearray(valid)
    if corruption == "utf8_metadata":
        central = valid.index(b"PK\x01\x02")
        flags = int.from_bytes(damaged[central + 8 : central + 10], "little") | 0x800
        damaged[central + 8 : central + 10] = flags.to_bytes(2, "little")
        damaged[central + 46] = 0xFF
    else:
        with zipfile.ZipFile(BytesIO(valid)) as source:
            info = source.getinfo("payload.json")
        name_length, extra_length = struct.unpack_from("<HH", valid, info.header_offset + 26)
        offset = info.header_offset + 30 + name_length + extra_length
        if corruption == "deflate":
            # BFINAL=1/BTYPE=3 is an invalid DEFLATE block, independent of its contents.
            damaged[offset] = 7
        else:
            # The first LZMA properties byte follows its four-byte ZIP framing header.
            damaged[offset + 4] ^= 0xFF
    return valid, bytes(damaged)


@pytest.mark.parametrize("corruption", ["deflate", "lzma", "utf8_metadata"])
def test_invalid_zip_codecs_and_metadata_raise_archive_errors(compressed_archive_vault, corruption):
    archive, _before = compressed_archive_vault
    valid, damaged = _corrupted_zip(archive, corruption)
    _validated_members(valid)
    with pytest.raises(ArchiveError):
        _validated_members(damaged)


@pytest.mark.parametrize("corruption", ["deflate", "lzma", "utf8_metadata"])
def test_inspection_rejects_zip_decoder_failures_without_private_details(
    client, auth_headers, db_session, test_user, compressed_archive_vault, corruption
):
    archive, before = compressed_archive_vault
    valid, damaged = _corrupted_zip(archive, corruption)
    control = client.post(
        "/api/v1/portability/inspect",
        headers=auth_headers,
        files={"file": ("synthetic-valid.zip", valid, "application/zip")},
    )
    assert control.status_code == 200
    assert control.json()["compatible"] is True
    inspected = client.post(
        "/api/v1/portability/inspect",
        headers=auth_headers,
        files={"file": ("PRIVATE-SYNTHETIC-FILENAME.zip", damaged, "application/zip")},
    )
    assert inspected.status_code == 422
    assert inspected.json() == {
        "detail": {"code": "archive_invalid", "message": "Backup verification failed."}
    }
    db_session.expire_all()
    owner = db_session.get(User, test_user.id)
    profile = db_session.query(CandidateProfile).filter_by(user_id=test_user.id).one()
    assert owner.vault_lifecycle_state == VAULT_STATE_READY
    assert owner.vault_maintenance_fingerprint is None
    assert (profile.id, profile.revision, profile.display_name) == before


@pytest.mark.parametrize("corruption", ["deflate", "lzma", "utf8_metadata"])
def test_restore_rejects_zip_decoder_failures_without_stranding_vault_or_session(
    client, auth_headers, db_session, test_user, compressed_archive_vault, corruption
):
    archive, before = compressed_archive_vault
    valid, damaged = _corrupted_zip(archive, corruption)
    _validated_members(valid)
    rejected = client.post(
        "/api/v1/portability/restore",
        headers=auth_headers,
        files={"file": ("PRIVATE-SYNTHETIC-FILENAME.zip", damaged, "application/zip")},
    )
    assert rejected.status_code == 422
    expected_error = (
        "The uploaded file is not a valid ZIP archive"
        if corruption == "utf8_metadata"
        else "The archive contains an unreadable member"
    )
    assert rejected.json() == {"detail": expected_error}
    assert "PRIVATE-SYNTHETIC" not in rejected.text
    assert "maintenance_access_token" not in rejected.text
    db_session.expire_all()
    owner = db_session.get(User, test_user.id)
    profile = db_session.query(CandidateProfile).filter_by(user_id=test_user.id).one()
    assert owner.vault_lifecycle_state == VAULT_STATE_READY
    assert owner.vault_maintenance_fingerprint is None
    assert (profile.id, profile.revision, profile.display_name) == before
    assert read_restore_journal(test_user.id) is None
    assert client.get("/api/v1/career-profile", headers=auth_headers).status_code == 200
