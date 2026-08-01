import hashlib
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.career.deletion as deletion
from backend.ai.models import AIExecution
from backend.applications.models import Application
from backend.automation.grants import issue_grant
from backend.automation.models import AutomationGrant
from backend.career.deletion import (
    _sanitize_sqlite_storage,
    begin_vault_maintenance,
    delete_complete_vault,
)
from backend.career.models import CandidateProfile, CareerAsset
from backend.core.config import settings
from backend.models import Job, ScrapedJob, SearchProfile, User
from backend.models.auth_session import AuthSession
from backend.models.user import (
    VAULT_STATE_ERASURE_PENDING,
    VAULT_STATE_READY,
    VAULT_STATE_RESET_PENDING,
)
from backend.resumes.models import ResumeDraft
from backend.resumes.storage import (
    resume_artifact_path,
    store_resume_artifact,
    write_resume_publication_journal,
)
from backend.services.auth import ACCESS_PURPOSE_SESSION
from backend.services.auth_sessions import issue_auth_session, issue_maintenance_access

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


def test_reset_final_sweep_revokes_family_that_appeared_after_begin(
    client,
    db_session,
    test_user,
    deletion_root,
) -> None:
    authority = issue_auth_session(db_session, test_user)
    racing_login = issue_auth_session(db_session, test_user)
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.session_id,
        VAULT_STATE_RESET_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )

    # Reproduce the old login/reset interleaving: a family commits after begin's
    # first snapshot while reset is waiting to acquire the global writer.
    rogue = db_session.get(AuthSession, racing_login.session_id)
    assert rogue is not None
    rogue.revoked_at = None
    db_session.commit()

    delete_complete_vault(
        db_session,
        test_user.id,
        maintenance_session_id=authority.session_id,
    )

    db_session.expire_all()
    owner = db_session.get(User, test_user.id)
    assert owner is not None and owner.vault_lifecycle_state == VAULT_STATE_READY
    assert db_session.get(AuthSession, authority.session_id).revoked_at is None
    assert db_session.get(AuthSession, racing_login.session_id).revoked_at is not None
    response = client.get(
        "/api/v1/career-profile/summary",
        headers={"Authorization": f"Bearer {racing_login.access_token}"},
    )
    assert response.status_code == 401


def test_logout_invalidates_erasure_recovery_bearer_and_password_reauth_replaces_it(
    client,
    auth_headers,
    db_session,
    test_user,
    deletion_root,
) -> None:
    authority = db_session.query(AuthSession).filter_by(user_id=test_user.id).one()
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.id,
        VAULT_STATE_ERASURE_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )
    maintenance = issue_maintenance_access(db_session, test_user)
    old_session_id = maintenance.session_id
    logged_out = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {maintenance.access_token}"},
    )
    assert logged_out.status_code == 200, logged_out.text
    db_session.expire_all()
    assert db_session.get(AuthSession, old_session_id) is None

    rejected = client.delete(
        "/api/v1/portability/erase",
        headers={
            "Authorization": f"Bearer {maintenance.access_token}",
            "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA",
        },
    )
    assert rejected.status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["session_state"] == "erasure_pending"
    replacement_token = login.json()["access_token"]
    db_session.expire_all()
    replacement = db_session.query(AuthSession).filter_by(user_id=test_user.id).one()
    assert replacement.id != old_session_id

    completed = client.delete(
        "/api/v1/portability/erase",
        headers={
            "Authorization": f"Bearer {replacement_token}",
            "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA",
        },
    )
    assert completed.status_code == 200, completed.text


@pytest.fixture
def deletion_root(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", str(root))
        monkeypatch.setenv("CAREEROS_DESKTOP_DATA_DIR", str(root))
        yield root


def _reset_with_source_ready(
    client,
    auth_headers,
    db_session,
    test_user,
    *,
    content: bytes,
) -> tuple[str, str]:
    profile = client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers)
    assert profile.status_code == 200, profile.text
    source = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("deletion-receipt.txt", content, "text/plain")},
        headers=auth_headers,
    )
    assert source.status_code == 201, source.text
    db_session.expire_all()
    storage_path = db_session.query(CareerAsset).one().storage_path
    authority = db_session.query(AuthSession).filter_by(user_id=test_user.id).one()
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.id,
        VAULT_STATE_RESET_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )
    return authority.id, storage_path


def test_erasure_session_finalization_accepts_lost_commit_acknowledgement(
    db_session,
    test_user,
    deletion_root,
    monkeypatch,
) -> None:
    authority = issue_auth_session(db_session, test_user)
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.session_id,
        VAULT_STATE_ERASURE_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )
    real_commit = db_session.commit
    commit_calls = 0
    acknowledgement_lost = False

    def commit_then_raise_on_finalization() -> None:
        nonlocal acknowledgement_lost, commit_calls
        commit_calls += 1
        real_commit()
        if commit_calls == 2:
            acknowledgement_lost = True
            raise RuntimeError("synthetic lost session finalization acknowledgement")

    monkeypatch.setattr(db_session, "commit", commit_then_raise_on_finalization)
    counts = delete_complete_vault(
        db_session,
        test_user.id,
        erase_auth_sessions=True,
        erasure_session_id=authority.session_id,
    )

    assert acknowledgement_lost is True
    assert counts["auth_sessions"] == 1
    db_session.expire_all()
    owner = db_session.get(User, test_user.id)
    assert owner is not None
    assert owner.vault_lifecycle_state == VAULT_STATE_READY
    assert owner.vault_maintenance_fingerprint is None
    assert db_session.query(AuthSession).filter_by(user_id=test_user.id).count() == 0


def test_reset_commit_acknowledgement_error_finishes_committed_deletion_without_orphans(
    client,
    auth_headers,
    db_session,
    test_user,
    deletion_root,
    monkeypatch,
) -> None:
    authority_id, storage_path = _reset_with_source_ready(
        client,
        auth_headers,
        db_session,
        test_user,
        content=b"committed deletion acknowledgement evidence",
    )
    real_commit = db_session.commit
    acknowledgement_lost = False

    def commit_then_raise_once() -> None:
        nonlocal acknowledgement_lost
        real_commit()
        if not acknowledgement_lost:
            acknowledgement_lost = True
            raise RuntimeError("synthetic lost deletion commit acknowledgement")

    monkeypatch.setattr(db_session, "commit", commit_then_raise_once)
    counts = delete_complete_vault(
        db_session,
        test_user.id,
        maintenance_session_id=authority_id,
    )

    assert acknowledgement_lost is True
    assert counts["profiles"] == 1
    assert counts["files"] == 1
    db_session.expire_all()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    assert db_session.query(CareerAsset).count() == 0
    assert not (deletion_root / storage_path).exists()
    assert not (deletion_root / ".trash" / f"user-{test_user.id}").exists()
    owner = db_session.get(User, test_user.id)
    assert owner is not None and owner.vault_lifecycle_state == VAULT_STATE_READY

    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority_id,
        VAULT_STATE_RESET_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )
    retry = delete_complete_vault(
        db_session,
        test_user.id,
        maintenance_session_id=authority_id,
    )
    assert retry["profiles"] == 0
    assert retry["files"] == 0
    assert not (deletion_root / ".trash" / f"user-{test_user.id}").exists()


def test_reset_failure_before_commit_restores_staged_files_and_remains_retryable(
    client,
    auth_headers,
    db_session,
    test_user,
    deletion_root,
    monkeypatch,
) -> None:
    content = b"precommit deletion rollback evidence"
    authority_id, storage_path = _reset_with_source_ready(
        client,
        auth_headers,
        db_session,
        test_user,
        content=content,
    )
    real_commit = db_session.commit

    def fail_before_commit() -> None:
        raise RuntimeError("synthetic deletion precommit failure")

    monkeypatch.setattr(db_session, "commit", fail_before_commit)
    with pytest.raises(RuntimeError, match="precommit"):
        delete_complete_vault(
            db_session,
            test_user.id,
            maintenance_session_id=authority_id,
        )

    db_session.expire_all()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 1
    assert db_session.query(CareerAsset).count() == 1
    assert (deletion_root / storage_path).read_bytes() == content
    assert not [path for path in (deletion_root / ".trash").rglob("*") if path.is_file()]

    monkeypatch.setattr(db_session, "commit", real_commit)
    retry = delete_complete_vault(
        db_session,
        test_user.id,
        maintenance_session_id=authority_id,
    )
    assert retry["profiles"] == 1
    assert retry["files"] == 1
    assert not (deletion_root / storage_path).exists()


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


def test_reset_removes_owned_crash_journal_and_orphan_artifact_only(
    client,
    auth_headers,
    db_session,
    test_user,
    deletion_root,
) -> None:
    response = client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers)
    assert response.status_code == 200, response.text
    db_session.expire_all()
    target_profile = db_session.query(CandidateProfile).filter_by(user_id=test_user.id).one()

    other_user = User(username="journal-isolation-owner", hashed_password="not-used")
    db_session.add(other_user)
    db_session.flush()
    other_profile = CandidateProfile(
        user_id=other_user.id,
        display_name="Other journal owner",
    )
    db_session.add(other_profile)
    db_session.flush()
    target_draft = ResumeDraft(
        id="11111111-1111-4111-8111-111111111111",
        profile_id=target_profile.id,
        revision=1,
        profile_revision=target_profile.revision,
        title="Interrupted target publication",
        template_kind="ats",
        section_config={},
        selected_fact_ids=[],
        content_overrides={},
        canvas_document={},
        generation_context={},
    )
    other_draft = ResumeDraft(
        id="22222222-2222-4222-8222-222222222222",
        profile_id=other_profile.id,
        revision=1,
        profile_revision=other_profile.revision,
        title="Unrelated publication",
        template_kind="ats",
        section_config={},
        selected_fact_ids=[],
        content_overrides={},
        canvas_document={},
        generation_context={},
    )
    db_session.add_all([target_draft, other_draft])
    db_session.commit()
    target_draft_id = target_draft.id
    other_draft_id = other_draft.id

    target_version_id = "33333333-3333-4333-8333-333333333333"
    target_bytes = b"target resume bytes left by a stopped publisher"
    target_path = resume_artifact_path(
        profile_id=target_profile.id,
        version_id=target_version_id,
        format="pdf",
        sha256=hashlib.sha256(target_bytes).hexdigest(),
    )
    target_journal = write_resume_publication_journal(
        draft_id=target_draft_id,
        version_id=target_version_id,
        artifact_paths=[target_path],
    )
    target_artifact = store_resume_artifact(
        profile_id=target_profile.id,
        version_id=target_version_id,
        format="pdf",
        data=target_bytes,
    )

    other_version_id = "44444444-4444-4444-8444-444444444444"
    other_bytes = b"unrelated resume bytes"
    other_path = resume_artifact_path(
        profile_id=other_profile.id,
        version_id=other_version_id,
        format="pdf",
        sha256=hashlib.sha256(other_bytes).hexdigest(),
    )
    other_journal = write_resume_publication_journal(
        draft_id=other_draft_id,
        version_id=other_version_id,
        artifact_paths=[other_path],
    )
    other_artifact = store_resume_artifact(
        profile_id=other_profile.id,
        version_id=other_version_id,
        format="pdf",
        data=other_bytes,
    )

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )

    assert deleted.status_code == 204, deleted.text
    assert not target_artifact.absolute_path.exists()
    assert not (deletion_root / target_journal).exists()
    assert other_artifact.absolute_path.read_bytes() == other_bytes
    assert (deletion_root / other_journal).is_file()
    db_session.expire_all()
    assert db_session.get(ResumeDraft, target_draft_id) is None
    assert db_session.get(ResumeDraft, other_draft_id) is not None


def test_reset_retry_removes_staged_publication_recovery_residue(
    client,
    auth_headers,
    db_session,
    test_user,
    deletion_root,
    monkeypatch,
) -> None:
    response = client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers)
    assert response.status_code == 200, response.text
    db_session.expire_all()
    profile = db_session.query(CandidateProfile).filter_by(user_id=test_user.id).one()
    draft = ResumeDraft(
        id="55555555-5555-4555-8555-555555555555",
        profile_id=profile.id,
        revision=1,
        profile_revision=profile.revision,
        title="Retryable interrupted publication",
        template_kind="ats",
        section_config={},
        selected_fact_ids=[],
        content_overrides={},
        canvas_document={},
        generation_context={},
    )
    db_session.add(draft)
    db_session.commit()
    version_id = "66666666-6666-4666-8666-666666666666"
    artifact_bytes = b"private publication recovery residue"
    artifact_path = resume_artifact_path(
        profile_id=profile.id,
        version_id=version_id,
        format="pdf",
        sha256=hashlib.sha256(artifact_bytes).hexdigest(),
    )
    journal_path = write_resume_publication_journal(
        draft_id=draft.id,
        version_id=version_id,
        artifact_paths=[artifact_path],
    )
    stored = store_resume_artifact(
        profile_id=profile.id,
        version_id=version_id,
        format="pdf",
        data=artifact_bytes,
    )

    authority = db_session.query(AuthSession).filter_by(user_id=test_user.id).one()
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.id,
        VAULT_STATE_RESET_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )
    real_rmtree = deletion.shutil.rmtree
    cleanup_attempts = 0

    def fail_first_cleanup(path, *args, **kwargs):
        nonlocal cleanup_attempts
        if Path(path).name == f"user-{test_user.id}" and cleanup_attempts == 0:
            cleanup_attempts += 1
            raise OSError("simulated publication recovery cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(deletion.shutil, "rmtree", fail_first_cleanup)
    with pytest.raises(deletion.VaultDeletionError, match="private files remain"):
        delete_complete_vault(
            db_session,
            test_user.id,
            maintenance_session_id=authority.id,
        )

    user_trash = deletion_root / ".trash" / f"user-{test_user.id}"
    assert not stored.absolute_path.exists()
    assert not (deletion_root / journal_path).exists()
    assert sorted(path.suffix for path in user_trash.rglob("*") if path.is_file()) == [
        ".json",
        ".pdf",
    ]

    delete_complete_vault(
        db_session,
        test_user.id,
        maintenance_session_id=authority.id,
    )

    assert cleanup_attempts == 1
    assert not user_trash.exists()
    db_session.expire_all()
    owner = db_session.get(User, test_user.id)
    assert owner is not None and owner.vault_lifecycle_state == VAULT_STATE_READY


def test_device_erasure_reports_and_removes_only_owned_automation_grants(
    client, auth_headers, db_session, test_user, deletion_root
):
    other_user = User(username="other-automation-user", hashed_password="not-used")
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    owned_first, _ = issue_grant(
        db_session,
        user_id=test_user.id,
        label="codex",
        scopes=["system:read"],
    )
    owned_second, _ = issue_grant(
        db_session,
        user_id=test_user.id,
        label="claude-code",
        scopes=["career:read"],
    )
    preserved, _ = issue_grant(
        db_session,
        user_id=other_user.id,
        label="other-agent",
        scopes=["system:read"],
    )
    owned_auth_session_ids = {
        session_id
        for (session_id,) in db_session.query(AuthSession.id)
        .filter(AuthSession.user_id == test_user.id)
        .all()
    }
    assert owned_auth_session_ids
    other_tokens = issue_auth_session(db_session, other_user)
    other_auth_session = (
        db_session.query(AuthSession).filter(AuthSession.user_id == other_user.id).one()
    )
    assert other_tokens.refresh_token

    erased = client.delete(
        "/api/v1/portability/erase",
        headers={**auth_headers, "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA"},
    )

    assert erased.status_code == 200, erased.text
    assert erased.json()["automation_grants"] == 2
    assert erased.json()["auth_sessions"] == len(owned_auth_session_ids)
    db_session.expire_all()
    assert (
        db_session.query(AutomationGrant)
        .filter(AutomationGrant.id.in_([owned_first.id, owned_second.id]))
        .count()
        == 0
    )
    other_grant = db_session.get(AutomationGrant, preserved.id)
    assert other_grant is not None
    assert other_grant.user_id == other_user.id
    assert other_grant.revoked_at is None
    assert (
        db_session.query(AuthSession).filter(AuthSession.id.in_(owned_auth_session_ids)).count()
        == 0
    )
    preserved_auth_session = db_session.get(AuthSession, other_auth_session.id)
    assert preserved_auth_session is not None
    assert preserved_auth_session.user_id == other_user.id
    assert preserved_auth_session.revoked_at is None
    erased_access = client.get(
        "/api/v1/career-profile/summary",
        headers=auth_headers,
    )
    assert erased_access.status_code == 401
    neighboring_access = client.get(
        "/api/v1/career-profile/summary",
        headers={"Authorization": f"Bearer {other_tokens.access_token}"},
    )
    assert neighboring_access.status_code == 404


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


def test_device_erasure_removes_application_only_scraped_job(
    client, auth_headers, db_session, test_user, deletion_root
):
    listing = ScrapedJob(
        platform="test",
        platform_job_id="application-only-exclusive",
        title="Application-only role",
        company="Private employer",
        external_url="https://example.test/application-only-exclusive",
    )
    db_session.add(listing)
    db_session.flush()
    application = Application(
        user_id=test_user.id,
        job_id=None,
        scraped_job_id=listing.id,
        current_stage="saved",
        job_snapshot={"title": listing.title, "company": listing.company},
        job_title=listing.title,
        job_company=listing.company,
    )
    db_session.add(application)
    db_session.commit()
    listing_id = listing.id
    application_id = application.id

    erased = client.delete(
        "/api/v1/portability/erase",
        headers={**auth_headers, "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA"},
    )

    assert erased.status_code == 200, erased.text
    assert erased.json()["applications"] == 1
    assert erased.json()["jobs"] == 0
    assert erased.json()["scraped_jobs"] == 1
    db_session.expire_all()
    assert db_session.get(Application, application_id) is None
    assert db_session.get(ScrapedJob, listing_id) is None


def test_device_erasure_preserves_application_only_listing_used_by_another_user(
    client, auth_headers, db_session, test_user, deletion_root
):
    other_user = User(username="application-only-owner", hashed_password="not-used")
    listing = ScrapedJob(
        platform="test",
        platform_job_id="application-only-shared",
        title="Shared application-only role",
        company="Shared employer",
        external_url="https://example.test/application-only-shared",
    )
    db_session.add_all([other_user, listing])
    db_session.flush()
    target_application = Application(
        user_id=test_user.id,
        scraped_job_id=listing.id,
        current_stage="saved",
        job_snapshot={"title": listing.title, "company": listing.company},
        job_title=listing.title,
        job_company=listing.company,
    )
    other_application = Application(
        user_id=other_user.id,
        scraped_job_id=listing.id,
        current_stage="saved",
        job_snapshot={"title": listing.title, "company": listing.company},
        job_title=listing.title,
        job_company=listing.company,
    )
    db_session.add_all([target_application, other_application])
    db_session.commit()
    listing_id = listing.id
    target_application_id = target_application.id
    other_application_id = other_application.id

    erased = client.delete(
        "/api/v1/portability/erase",
        headers={**auth_headers, "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA"},
    )

    assert erased.status_code == 200, erased.text
    assert erased.json()["applications"] == 1
    assert erased.json()["scraped_jobs"] == 0
    db_session.expire_all()
    assert db_session.get(Application, target_application_id) is None
    assert db_session.get(Application, other_application_id) is not None
    assert db_session.get(ScrapedJob, listing_id) is not None


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
        if Path(path).name == f"user-{test_user.id}" and Path(path).parent.name == ".trash":
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
    failure_detail = first.json()["detail"]
    assert failure_detail["code"] == "erasure_cleanup_pending"
    assert failure_detail["session_state"] == "erasure_pending"
    maintenance_headers = {"Authorization": f"Bearer {failure_detail['maintenance_access_token']}"}
    assert sanitization_attempts == 1
    assert not (deletion_root / asset_path).exists()
    user_trash = deletion_root / ".trash" / f"user-{test_user.id}"
    assert [path for path in user_trash.rglob("*") if path.is_file()]
    # Ordinary workspace authority is gone; only the purpose-bound maintenance
    # bearer returned by the failed operation can retry cleanup.
    assert client.get("/api/v1/career-profile/summary", headers=auth_headers).status_code == 401

    retried = client.delete(
        "/api/v1/portability/erase",
        headers={
            **maintenance_headers,
            "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA",
        },
    )

    assert retried.status_code == 200, retried.text
    assert retried.json()["profiles"] == 0
    assert sanitization_attempts == 2
    assert cleanup_attempts == 2
    assert not user_trash.exists()
    assert other_user_file.read_bytes() == b"other-account"
    assert client.get("/api/v1/career-profile/summary", headers=auth_headers).status_code == 401


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
