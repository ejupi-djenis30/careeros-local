import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.applications.packet_storage import (
    all_packet_journals,
    reconcile_packet_journals,
    store_packet_artifact,
)
from backend.career.models import CandidateProfile, CareerAsset
from backend.core.config import settings
from backend.desktop.lifecycle import desktop_vault_lock
from backend.resumes.models import ResumeArtifact
from backend.storage.atomic import StorageWriteError, resolve_data_path
from tests.backend.applications.test_material_migration import (
    migrated_material_db as _migrated_material_db,
)
from tests.backend.applications.test_material_migration import seed_material_binding

migrated_material_db = _migrated_material_db


@pytest.fixture
def packet_root(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="careeros-packet-recovery-") as folder:
        monkeypatch.setattr(settings, "DATA_DIR", folder)
        yield Path(folder)


def test_packet_recovery_retains_journal_until_failed_unlink_can_be_retried(
    migrated_material_db, packet_root, monkeypatch
):
    engine, _ = migrated_material_db
    stored = store_packet_artifact(
        application_id=str(uuid.uuid4()),
        dossier_id=str(uuid.uuid4()),
        data=b"synthetic immutable packet",
    )
    real_unlink = __import__(
        "backend.applications.packet_storage", fromlist=["durable_unlink"]
    ).durable_unlink

    def fail_packet(path):
        if path.suffix == ".zip":
            raise OSError("synthetic locked packet")
        return real_unlink(path)

    monkeypatch.setattr("backend.applications.packet_storage.durable_unlink", fail_packet)
    with desktop_vault_lock(), Session(engine) as db:
        db.execute(text("BEGIN IMMEDIATE"))
        with pytest.raises(OSError):
            reconcile_packet_journals(db)
        assert len(all_packet_journals()) == 1
        assert stored.absolute_path.exists()
        monkeypatch.setattr("backend.applications.packet_storage.durable_unlink", real_unlink)
        assert reconcile_packet_journals(db) == 1
        assert not stored.absolute_path.exists() and not all_packet_journals()


def test_restart_recovers_a_packet_left_by_a_real_process_exit(migrated_material_db, packet_root):
    engine, _ = migrated_material_db
    application_id, dossier_id = str(uuid.uuid4()), str(uuid.uuid4())
    source = (
        "import os,sys; from backend.applications.packet_storage import store_packet_artifact; "
        "store_packet_artifact(application_id=sys.argv[1],dossier_id=sys.argv[2],"
        "data=b'synthetic crash packet'); os._exit(17)"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", source, application_id, dossier_id],
        env={**os.environ, "DATA_DIR": str(packet_root)},
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 17, result.stderr.decode(errors="replace")
    journal = all_packet_journals()[0]
    assert resolve_data_path(journal.storage_path).read_bytes() == b"synthetic crash packet"
    with desktop_vault_lock(), Session(engine) as db:
        db.execute(text("BEGIN IMMEDIATE"))
        assert reconcile_packet_journals(db) == 1
    assert not resolve_data_path(journal.storage_path).exists() and not all_packet_journals()


def test_partial_storage_failure_leaves_recoverable_journal(
    migrated_material_db, packet_root, monkeypatch
):
    engine, _ = migrated_material_db
    from backend.applications import packet_storage

    real_write = packet_storage.atomic_write

    def fail_zip(path, data):
        if path.endswith(".zip"):
            raise OSError("synthetic full disk")
        return real_write(path, data)

    monkeypatch.setattr(packet_storage, "atomic_write", fail_zip)
    with pytest.raises(OSError):
        store_packet_artifact(
            application_id=str(uuid.uuid4()), dossier_id=str(uuid.uuid4()), data=b"packet"
        )
    assert len(all_packet_journals()) == 1
    with desktop_vault_lock(), Session(engine) as db:
        db.execute(text("BEGIN IMMEDIATE"))
        assert reconcile_packet_journals(db) == 1
    assert not all_packet_journals()


def test_recovery_validates_every_journal_before_deleting_any_orphan(
    migrated_material_db, packet_root
):
    engine, _ = migrated_material_db
    stored = [
        store_packet_artifact(
            application_id=str(uuid.uuid4()), dossier_id=str(uuid.uuid4()), data=b"synthetic packet"
        )
        for _ in range(2)
    ]
    journals = all_packet_journals()
    corrupt = resolve_data_path(f"applications/.packet-journal/{journals[1].dossier_id}.json")
    raw = json.loads(corrupt.read_bytes())
    raw["application_id"] = 123
    corrupt.write_text(json.dumps(raw), encoding="utf-8")
    with desktop_vault_lock(), Session(engine) as db:
        db.execute(text("BEGIN IMMEDIATE"))
        with pytest.raises(StorageWriteError, match="metadata is invalid"):
            reconcile_packet_journals(db)
    assert all(artifact.absolute_path.exists() for artifact in stored)
    assert len(list(corrupt.parent.glob("*.json"))) == 2


@pytest.mark.parametrize("family", ["asset", "resume"])
def test_recovery_preserves_paths_claimed_by_another_document_family(
    migrated_material_db, packet_root, family
):
    engine, _ = migrated_material_db
    stored = store_packet_artifact(
        application_id=str(uuid.uuid4()), dossier_id=str(uuid.uuid4()), data=b"claimed document"
    )
    with Session(engine) as db:
        user_id, _, _, version_id, _ = seed_material_binding(db)
        shared = dict(
            storage_path=stored.relative_path,
            sha256=stored.sha256,
            byte_size=stored.byte_size,
            media_type="application/pdf",
        )
        row = (
            CareerAsset(
                profile_id=db.query(CandidateProfile.id).filter_by(user_id=user_id).scalar(),
                kind="document",
                original_name="private.pdf",
                **shared,
            )
            if family == "asset"
            else ResumeArtifact(
                version_id=version_id, format="pdf", created_at=datetime.now(timezone.utc), **shared
            )
        )
        db.add(row)
        db.commit()
    with desktop_vault_lock(), Session(engine) as db:
        db.execute(text("BEGIN IMMEDIATE"))
        with pytest.raises(StorageWriteError, match="another stored document"):
            reconcile_packet_journals(db)
    assert stored.absolute_path.read_bytes() == b"claimed document"
    assert len(all_packet_journals()) == 1
