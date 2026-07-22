from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.career.deletion as deletion
from backend.ai.models import AIExecution
from backend.career.deletion import _sanitize_sqlite_storage
from backend.career.models import CareerAsset
from backend.core.config import settings
from backend.models import Job, ScrapedJob, SearchProfile, User

PROFILE = {
    "expected_revision": 0,
    "display_name": "Iris Arden",
    "headline": "Research mathematician",
    "summary": "Calculates reliable trajectories.",
    "email": "katherine@example.test",
    "location": {"city": "Hampton", "country": "US"},
    "preferences": {},
    "facts": [],
    "goals": [],
}


@pytest.fixture
def deletion_root(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", str(root))
        monkeypatch.setenv("CAREEROS_DESKTOP_DATA_DIR", str(root))
        yield root


def test_device_erasure_removes_owned_data_but_preserves_unrelated_files(
    client, auth_headers, db_session, test_user, deletion_root
):
    profile = client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers)
    assert profile.status_code == 200, profile.text
    source = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("proof.txt", b"verified", "text/plain")},
        headers=auth_headers,
    )
    assert source.status_code == 201, source.text

    execution = AIExecution(
        user_id=test_user.id,
        task="profile_analysis",
        contract_version="1.0.0",
        model_id="local-test",
        input_fingerprint="a" * 64,
        output_fingerprint=None,
        evidence_count=1,
        accepted=False,
        repair_count=1,
        validation_codes=["missing_citation"],
        duration_ms=10,
    )
    db_session.add(execution)
    db_session.commit()
    db_session.expire_all()
    asset_path = db_session.query(CareerAsset).one().storage_path

    owned_files = (
        deletion_root / "models" / "runtime" / "v1" / "llama-server.exe",
        deletion_root / "models" / "weights" / "model.gguf",
        deletion_root / "staging" / "local-model" / "partial.download",
    )
    for path in owned_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"owned")
    unrelated = (
        deletion_root / "unrelated.keep",
        deletion_root / "backups" / "manual-backup.zip",
        deletion_root / "staging" / "another-tool" / "keep.bin",
    )
    for path in unrelated:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"keep")

    denied = client.delete("/api/v1/portability/erase", headers=auth_headers)
    assert denied.status_code == 409
    erased = client.delete(
        "/api/v1/portability/erase",
        headers={**auth_headers, "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA"},
    )
    assert erased.status_code == 200, erased.text
    assert erased.json()["profiles"] == 1
    assert erased.json()["ai_executions"] == 1
    assert erased.json()["model_files"] == 3
    assert not (deletion_root / asset_path).exists()
    assert all(not path.exists() for path in owned_files)
    assert all(path.read_bytes() == b"keep" for path in unrelated)


def test_device_erasure_removes_legacy_search_data_and_preserves_shared_jobs(
    client, auth_headers, db_session, test_user, deletion_root
):
    other_user = User(username="other-user", hashed_password="not-used")
    target_profiles = [
        SearchProfile(user_id=test_user.id, name="Private search one", cv_content="private cv"),
        SearchProfile(user_id=test_user.id, name="Private search two", cv_content="private cv"),
    ]
    other_profile = SearchProfile(
        user=other_user,
        name="Other user's search",
        cv_content="other cv",
    )
    exclusive_scraped_job = ScrapedJob(
        platform="test",
        platform_job_id="exclusive",
        title="Exclusive role",
        company="Private employer",
        description="target-only description",
        external_url="https://example.test/exclusive",
    )
    shared_scraped_job = ScrapedJob(
        platform="test",
        platform_job_id="shared",
        title="Shared role",
        company="Shared employer",
        description="shared description",
        external_url="https://example.test/shared",
    )
    unrelated_scraped_job = ScrapedJob(
        platform="test",
        platform_job_id="unrelated",
        title="Unrelated role",
        company="Other employer",
        description="unrelated description",
        external_url="https://example.test/unrelated",
    )
    db_session.add_all(
        [
            other_user,
            *target_profiles,
            other_profile,
            exclusive_scraped_job,
            shared_scraped_job,
            unrelated_scraped_job,
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            Job(
                user_id=test_user.id,
                search_profile_id=target_profiles[0].id,
                scraped_job_id=exclusive_scraped_job.id,
            ),
            Job(
                user_id=test_user.id,
                search_profile_id=target_profiles[1].id,
                scraped_job_id=exclusive_scraped_job.id,
            ),
            Job(
                user_id=test_user.id,
                search_profile_id=target_profiles[0].id,
                scraped_job_id=shared_scraped_job.id,
            ),
            Job(
                user_id=other_user.id,
                search_profile_id=other_profile.id,
                scraped_job_id=shared_scraped_job.id,
            ),
            Job(
                user_id=other_user.id,
                search_profile_id=other_profile.id,
                scraped_job_id=unrelated_scraped_job.id,
            ),
        ]
    )
    test_user.preference_signals = {"preferred_skills": ["private-skill"], "signal_count": 1}
    test_user.preference_updated_at = datetime.now(timezone.utc)
    db_session.commit()
    exclusive_scraped_job_id = exclusive_scraped_job.id
    shared_scraped_job_id = shared_scraped_job.id
    unrelated_scraped_job_id = unrelated_scraped_job.id
    other_profile_id = other_profile.id

    erased = client.delete(
        "/api/v1/portability/erase",
        headers={**auth_headers, "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA"},
    )

    assert erased.status_code == 200, erased.text
    assert erased.json()["search_profiles"] == 2
    assert erased.json()["jobs"] == 3
    assert erased.json()["scraped_jobs"] == 1
    assert erased.json()["preference_signals"] == 1

    db_session.expire_all()
    refreshed_user = db_session.get(User, test_user.id)
    assert refreshed_user is not None
    assert refreshed_user.preference_signals is None
    assert refreshed_user.preference_updated_at is None
    assert (
        db_session.query(SearchProfile).filter(SearchProfile.user_id == test_user.id).count() == 0
    )
    assert db_session.query(Job).filter(Job.user_id == test_user.id).count() == 0
    assert db_session.get(ScrapedJob, exclusive_scraped_job_id) is None
    assert db_session.get(ScrapedJob, shared_scraped_job_id) is not None
    assert db_session.get(ScrapedJob, unrelated_scraped_job_id) is not None
    assert db_session.get(SearchProfile, other_profile_id) is not None
    assert db_session.query(Job).filter(Job.user_id == other_user.id).count() == 2


def test_device_erasure_sanitizes_sqlite_and_retries_staged_file_cleanup(
    client, auth_headers, db_session, test_user, deletion_root, monkeypatch
):
    profile = client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers)
    assert profile.status_code == 200, profile.text
    source = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("private-proof.txt", b"private", "text/plain")},
        headers=auth_headers,
    )
    assert source.status_code == 201, source.text

    other_user_trash = deletion_root / ".trash" / "user-999" / "pending"
    other_user_trash.mkdir(parents=True)
    other_user_file = other_user_trash / "keep.bin"
    other_user_file.write_bytes(b"other-account")

    db_session.expire_all()
    asset_path = db_session.query(CareerAsset).one().storage_path
    real_rmtree = deletion.shutil.rmtree
    real_sanitize = deletion._sanitize_sqlite_storage
    cleanup_attempts = 0
    sanitization_attempts = 0

    def fail_first_trash_cleanup(path, *args, **kwargs):
        nonlocal cleanup_attempts
        if Path(path).name == f"user-{test_user.id}":
            cleanup_attempts += 1
            if cleanup_attempts == 1:
                raise OSError("simulated locked trash")
        return real_rmtree(path, *args, **kwargs)

    def track_sanitization(session):
        nonlocal sanitization_attempts
        sanitization_attempts += 1
        real_sanitize(session)

    monkeypatch.setattr(deletion.shutil, "rmtree", fail_first_trash_cleanup)
    monkeypatch.setattr(deletion, "_sanitize_sqlite_storage", track_sanitization)

    first = client.delete(
        "/api/v1/portability/erase",
        headers={**auth_headers, "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA"},
    )

    assert first.status_code == 500
    assert "private files remain" in first.json()["detail"]
    assert sanitization_attempts == 1
    assert not (deletion_root / asset_path).exists()
    user_trash = deletion_root / ".trash" / f"user-{test_user.id}"
    assert [path for path in user_trash.rglob("*") if path.is_file()]

    retried = client.delete(
        "/api/v1/portability/erase",
        headers={**auth_headers, "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA"},
    )

    assert retried.status_code == 200, retried.text
    assert retried.json()["profiles"] == 0
    assert sanitization_attempts == 2
    assert cleanup_attempts == 2
    assert not user_trash.exists()
    assert other_user_file.read_bytes() == b"other-account"


@pytest.mark.parametrize("unsafe_user_id", [0, -1, True, "../other-user"])
def test_vault_deletion_rejects_invalid_user_id_before_resolving_storage(
    db_session, monkeypatch, unsafe_user_id
):
    path_resolution_attempted = False

    def fail_if_resolved(_relative_path):
        nonlocal path_resolution_attempted
        path_resolution_attempted = True
        raise AssertionError("Invalid user IDs must not reach path resolution")

    monkeypatch.setattr(deletion, "resolve_data_path", fail_if_resolved)

    with pytest.raises(deletion.VaultDeletionError, match="Invalid user identifier"):
        deletion.delete_complete_vault(db_session, cast(Any, unsafe_user_id))

    assert path_resolution_attempted is False


def test_sqlite_vault_sanitization_truncates_wal_without_session_transaction():
    with TemporaryDirectory() as directory:
        database_path = Path(directory) / "vault.db"
        engine = create_engine(f"sqlite:///{database_path.as_posix()}")
        sentinel = "VAULT-DELETION-SENTINEL-7f386ace-7e2a-4ce6-a728-bef9ef5698bc" * 8
        sentinel_bytes = sentinel.encode()
        try:
            with engine.connect() as connection:
                assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one() == "wal"
                connection.exec_driver_sql("PRAGMA wal_autocheckpoint=0")
                connection.exec_driver_sql("PRAGMA secure_delete=OFF")
                connection.exec_driver_sql("CREATE TABLE private_rows (value TEXT NOT NULL)")
                connection.exec_driver_sql(
                    "INSERT INTO private_rows (value) VALUES (?)", (sentinel,)
                )
                connection.commit()
                connection.exec_driver_sql("DELETE FROM private_rows")
                connection.commit()

            wal_path = Path(f"{database_path}-wal")
            shm_path = Path(f"{database_path}-shm")
            assert wal_path.exists()
            assert wal_path.stat().st_size > 0
            sentinel_was_visible_before = any(
                sentinel_bytes in path.read_bytes()
                for path in (database_path, wal_path, shm_path)
                if path.exists()
            )

            session = Session(engine)
            try:
                _sanitize_sqlite_storage(session)
                assert not session.in_transaction()
            finally:
                session.close()

            assert not wal_path.exists() or wal_path.stat().st_size == 0
            with engine.connect() as connection:
                assert (
                    connection.exec_driver_sql("SELECT COUNT(*) FROM private_rows").scalar_one()
                    == 0
                )
            files_with_sentinel = [
                path.name
                for path in (database_path, wal_path, shm_path)
                if path.exists() and sentinel_bytes in path.read_bytes()
            ]
            assert not files_with_sentinel, (
                "Deleted sentinel remained in SQLite storage; "
                f"visible before sanitization={sentinel_was_visible_before}, "
                f"files={files_with_sentinel}"
            )
        finally:
            engine.dispose()
