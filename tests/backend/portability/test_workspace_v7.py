"""File-SQLite portability regressions for the MCP/material workspace."""

import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.agent_work.models import AgentProposal, AgentWorkRequest
from backend.agent_work.schemas import AnalysisProposalPayload, WorkContextPayload
from backend.ai.models import AIExecution
from backend.applications.exports import MAX_DOSSIER_BUNDLE_BYTES, build_dossier_bundle
from backend.applications.models import (
    Application,
    ApplicationDossierDraft,
    ApplicationEvent,
    ApplicationPacketArtifact,
)
from backend.applications.packet_storage import all_packet_journals, store_packet_artifact
from backend.automation.models import AutomationGrant
from backend.career.deletion import begin_vault_maintenance, delete_complete_vault
from backend.career.models import CandidateProfile, CareerAsset, CareerFact, SourceDocument
from backend.core.config import settings
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.models import Job, ScrapedJob, User
from backend.models.auth_session import AuthSession
from backend.models.user import VAULT_STATE_ERASURE_PENDING, VAULT_STATE_RESET_PENDING
from backend.portability import archive as archive_module
from backend.portability import restore as restore_module
from backend.portability.archive import ArchiveConflictError, ArchiveError, export_archive
from backend.portability.inspection import inspect_archive
from backend.portability.manifest import canonical_json, expected_tables, sha256
from backend.portability.restore import RestoreRolledBackError, restore_archive
from backend.resumes.models import ResumeDraft, ResumeVersion
from backend.services.auth import ACCESS_PURPOSE_SESSION
from backend.services.auth_sessions import issue_auth_session
from backend.storage.atomic import atomic_write, resolve_data_path
from tests.backend.portability.test_portable_archive import _seed_related_records


@pytest.fixture
def workspace_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path / "vault"))
    database_url = f"sqlite:///{(tmp_path / 'vault.sqlite').as_posix()}"
    ensure_sqlite_parent(database_url)
    engine = create_engine(database_url)
    event.listen(engine, "connect", configure_sqlite_connection)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = User(username="workspace-owner", hashed_password="synthetic")
        foreign = User(username="foreign-owner", hashed_password="synthetic")
        db.add_all([owner, foreign])
        db.commit()
        yield db, owner, foreign
    engine.dispose()


def seed_workspace(db, owner):
    now = datetime.now(UTC)
    profile = CandidateProfile(user_id=owner.id, display_name="Synthetic Candidate", revision=1)
    db.add(profile)
    db.flush()
    fact = CareerFact(
        profile_id=profile.id,
        fact_type="skill",
        payload={"name": "Python"},
        verification_status="confirmed",
    )
    db.add(fact)
    db.commit()
    _seed_related_records(db, owner.id, profile.id, fact.id)
    draft = db.query(ResumeDraft).one()
    version = db.query(ResumeVersion).one()
    draft.revision = 5
    draft.template_id = "cloud-platform-en"
    app = db.query(Application).one()
    dossier_draft = db.query(ApplicationDossierDraft).one()
    dossier_draft.resume_version_id = None
    dossier_draft.resume_draft_id = draft.id
    dossier_draft.resume_draft_revision = draft.revision
    source = b"Synthetic template reference"
    digest = sha256(source)
    source_path = f"assets/{digest[:2]}/{digest}"
    atomic_write(source_path, source)
    asset = CareerAsset(
        profile_id=profile.id,
        kind="source_document",
        original_name="reference.txt",
        media_type="text/plain",
        sha256=digest,
        byte_size=len(source),
        storage_path=source_path,
        normalized=False,
    )
    db.add(asset)
    db.flush()
    db.add(
        SourceDocument(
            profile_id=profile.id,
            asset_id=asset.id,
            document_type="text",
            source_role="template_reference",
            extracted_text=source.decode(),
            extracted_text_sha256=digest,
        )
    )
    scraped = ScrapedJob(
        platform="manual",
        platform_job_id=str(uuid.uuid4()),
        title="Python role",
        company="Synthetic",
        description="Python",
        external_url="https://example.test/role",
    )
    db.add(scraped)
    db.flush()
    job = Job(user_id=owner.id, scraped_job_id=scraped.id)
    db.add(job)
    db.flush()
    grant = AutomationGrant(
        user_id=owner.id,
        label="Synthetic grant",
        token_digest="1" * 64,
        scopes=["work:read", "proposal:submit"],
        expires_at=now + timedelta(days=1),
    )
    db.add(grant)
    db.flush()
    request_id, proposal_id = str(uuid.uuid4()), str(uuid.uuid4())
    context = WorkContextPayload(
        request_id=request_id,
        work_kind="analyze",
        historical_grant_id=grant.id,
        instruction="Review Python role",
        input_digest="0" * 64,
        input_revisions={"profile": 1, "job": 1},
        facts=[],
    ).model_dump(mode="json")
    context["input_digest"] = sha256(canonical_json(context))
    work = AgentWorkRequest(
        id=request_id,
        user_id=owner.id,
        bound_grant_id=grant.id,
        work_kind="analyze",
        state="returned",
        instruction="Review Python role",
        target_job_id=job.id,
        target_application_id=app.id,
        target_resume_id=draft.id,
        selected_fact_ids=[fact.id],
        context_snapshot=context,
        input_digest=context["input_digest"],
        input_revisions=context["input_revisions"],
        expires_at=now + timedelta(days=1),
        revision=2,
    )
    db.add(work)
    db.flush()
    dimensions = ("role", "requirements", "language", "location", "contract", "freshness")
    payload = AnalysisProposalPayload.model_validate(
        {
            "kind": "analyze",
            "contract_version": 1,
            "gates": [
                {
                    "dimension": key,
                    "status": "hold",
                    "reason": "Requires review",
                    "unknowns": ["Pending"],
                }
                for key in dimensions
            ],
            "scores": {
                **{key: {"score": 0, "explanation": "Pending"} for key in dimensions},
                "overall_score": 0,
            },
            "claims": [{"claim_text": "Python", "fact_ids": [fact.id]}],
            "recommendation": "insufficient_evidence",
        }
    ).model_dump(mode="json")
    proposal = AgentProposal(
        id=proposal_id,
        request_id=request_id,
        user_id=owner.id,
        submitting_grant_id=grant.id,
        idempotency_key="synthetic-proposal",
        payload_digest=sha256(canonical_json(payload)),
        contract_version=1,
        client_label="Synthetic",
        payload=payload,
        created_at=now,
        review_required=True,
    )
    db.add(proposal)
    provenance = {
        "source": "external-agent",
        "request_id": work.id,
        "grant_id": grant.id,
        "input_digest": work.input_digest,
        "payload_digest": proposal.payload_digest,
        "generated_at": now.isoformat(),
    }
    dossier_draft.content = {**dossier_draft.content, "generation_provenance": provenance}
    dossier_draft.updated_at = datetime.now(UTC)
    dossier_id = str(uuid.uuid4())
    bundle = build_dossier_bundle(
        dossier_id=dossier_id,
        version_number=1,
        application_revision=2,
        application_id=app.id,
        created_at=now.isoformat(),
        role={"title": "Role"},
        resume_version_id=version.id,
        readiness={"status": "ready"},
        cover_letter="Synthetic letter",
        answers=[],
        checklist=[],
        requirement_matrix=[],
        evidence_catalog=[],
        resume_artifacts={"pdf": (b"%PDF synthetic immutable", "application/pdf")},
        schema_version="3.0",
        generation_provenance=provenance,
    )
    packet = store_packet_artifact(application_id=app.id, dossier_id=dossier_id, data=bundle.data)
    app.revision = 2
    app.latest_event_at = max(app.latest_event_at, now)
    db.add(
        ApplicationEvent(
            id=dossier_id,
            application_id=app.id,
            event_type="dossier_published",
            occurred_at=now,
            created_at=now,
            payload={
                "schema_version": "3.0",
                "dossier": {
                    "schema_version": "3.0",
                    "resume_version_id": version.id,
                    "manifest": bundle.manifest,
                    "manifest_sha256": bundle.manifest_sha256,
                    "generation_provenance": provenance,
                },
            },
        )
    )
    db.add(
        ApplicationPacketArtifact(
            application_id=app.id,
            dossier_id=dossier_id,
            storage_path=packet.relative_path,
            sha256=packet.sha256,
            byte_size=packet.byte_size,
        )
    )
    db.commit()
    return {
        "profile": profile.id,
        "work": work.id,
        "proposal": proposal.id,
        "job": job.id,
        "draft": draft.id,
        "version": version.id,
        "packet_path": packet.relative_path,
        "packet_bytes": bundle.data,
        "context": context,
        "payload": payload,
        "provenance": provenance,
    }


def reset(db, owner):
    session = issue_auth_session(db, owner)
    begin_vault_maintenance(
        db,
        owner.id,
        session.session_id,
        VAULT_STATE_RESET_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )
    counts = delete_complete_vault(db, owner.id, maintenance_session_id=session.session_id)
    db.expire_all()
    return counts


def rewrite(data, change):
    with zipfile.ZipFile(BytesIO(data)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(members["payload.json"])
    change(payload)
    members["payload.json"] = canonical_json(payload)
    manifest = json.loads(members["manifest.json"])
    manifest["record_counts"] = {name: len(rows) for name, rows in payload["tables"].items()}
    for entry in manifest["entries"]:
        entry.update(sha256=sha256(members[entry["path"]]), byte_size=len(members[entry["path"]]))
    members["manifest.json"] = canonical_json(manifest)
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for name, content in members.items():
            target.writestr(name, content)
    return output.getvalue()


def rewrite_manifest(data, change):
    with zipfile.ZipFile(BytesIO(data)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(members["manifest.json"])
    change(manifest)
    members["manifest.json"] = canonical_json(manifest)
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for name, content in members.items():
            target.writestr(name, content)
    return output.getvalue()


def test_current_roundtrip_preserves_v7_history_packet_bytes_and_remaps_live_targets(workspace_db):
    db, owner, foreign = workspace_db
    seeded = seed_workspace(db, owner)
    snapshot = db.get(ResumeVersion, seeded["version"]).snapshot.copy()
    exported = export_archive(db, owner.id)
    assert not all_packet_journals()
    with zipfile.ZipFile(BytesIO(exported)) as archive:
        payload = json.loads(archive.read("payload.json"))
        assert json.loads(archive.read("manifest.json"))["format_version"] == 8
    assert payload["tables"]["agent_work_requests"][0]["bound_grant_id"] is None
    assert payload["tables"]["agent_proposals"][0]["submitting_grant_id"] is None
    assert db.get(AgentWorkRequest, seeded["work"]).bound_grant_id is not None
    counts = reset(db, owner)
    assert (
        counts["agent_work_requests"]
        == counts["agent_proposals"]
        == counts["application_packet_artifacts"]
        == 1
    )
    assert not resolve_data_path(seeded["packet_path"]).exists()
    foreign_scraped = ScrapedJob(
        platform="manual",
        platform_job_id="foreign",
        title="Foreign",
        company="Foreign",
        description="Foreign",
        external_url="https://example.test/foreign",
    )
    db.add(foreign_scraped)
    db.flush()
    foreign_job = Job(id=seeded["job"], user_id=foreign.id, scraped_job_id=foreign_scraped.id)
    db.add(foreign_job)
    db.commit()
    restore_archive(db, owner.id, exported)
    work = db.get(AgentWorkRequest, seeded["work"])
    assert (
        work.state == "canceled"
        and work.error_code == "restored_without_authority"
        and work.revision == 3
    )
    assert work.bound_grant_id is None and work.target_job_id != seeded["job"]
    assert db.get(Job, work.target_job_id).user_id == owner.id
    assert work.context_snapshot == seeded["context"]
    assert db.get(AgentProposal, seeded["proposal"]).payload == seeded["payload"]
    assert db.get(AgentProposal, seeded["proposal"]).submitting_grant_id is None
    assert db.get(ResumeVersion, seeded["version"]).snapshot == snapshot
    assert db.get(ResumeDraft, seeded["draft"]).template_id == "cloud-platform-en"
    draft = db.query(ApplicationDossierDraft).one()
    assert draft.resume_draft_id == seeded["draft"] and draft.resume_draft_revision == 5
    assert draft.content["generation_provenance"] == seeded["provenance"]
    assert db.query(SourceDocument).one().source_role == "template_reference"
    assert resolve_data_path(seeded["packet_path"]).read_bytes() == seeded["packet_bytes"]
    assert (
        not db.query(AuthSession)
        .filter(AuthSession.user_id == owner.id, AuthSession.revoked_at.is_(None))
        .count()
    )
    assert inspect_archive(db, owner.id, export_archive(db, owner.id)).compatible


@pytest.mark.parametrize(
    "case",
    [
        "target_job",
        "target_resume",
        "proposal_owner",
        "context_digest",
        "proposal_digest",
        "context_limit",
        "packet_event",
        "packet_missing",
        "draft_revision",
        "source_role",
        "preset_version",
        "packet_provenance",
        "packet_metadata_mismatch",
    ],
)
def test_v7_rejects_malformed_history_before_any_restore_write(workspace_db, case):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    reset(db, owner)

    def change(payload):
        tables = payload["tables"]
        if case == "target_job":
            tables["agent_work_requests"][0]["target_job_id"] = 987654
        elif case == "target_resume":
            tables["agent_work_requests"][0]["target_resume_id"] = str(uuid.uuid4())
        elif case == "proposal_owner":
            tables["agent_proposals"][0]["request_id"] = str(uuid.uuid4())
        elif case == "context_digest":
            tables["agent_work_requests"][0]["context_snapshot"]["instruction"] = "Forged"
        elif case == "proposal_digest":
            tables["agent_proposals"][0]["payload"]["claims"][0]["claim_text"] = "Forged"
        elif case == "context_limit":
            tables["agent_work_requests"][0]["context_snapshot"]["preferences"] = {
                "large": "x" * 65536
            }
        elif case == "packet_event":
            tables["application_packet_artifacts"][0]["dossier_id"] = str(uuid.uuid4())
        elif case == "packet_missing":
            tables["application_packet_artifacts"].clear()
        elif case == "draft_revision":
            tables["application_dossier_drafts"][0]["resume_draft_revision"] = 999
        elif case == "source_role":
            tables["source_documents"][0]["source_role"] = "authority"
        elif case == "preset_version":
            tables["resume_drafts"][0]["template_version"] = 999
        elif case in {"packet_provenance", "packet_metadata_mismatch"}:
            dossier = next(
                row
                for row in tables["application_events"]
                if row["event_type"] == "dossier_published"
            )["payload"]["dossier"]
            dossier["generation_provenance"]["source"] = "external_agent"
            if case == "packet_provenance":
                dossier["manifest"]["generation_provenance"]["source"] = "external_agent"

    with pytest.raises(ArchiveError):
        restore_archive(db, owner.id, rewrite(exported, change))
    assert db.query(CandidateProfile).count() == 0
    assert db.query(AgentWorkRequest).count() == 0
    assert not resolve_data_path(seeded["packet_path"]).exists()


@pytest.mark.parametrize(
    "case",
    [
        "preferences_scalar",
        "preferences_boolean_string",
        "preferences_numeric_string",
        "invalid_application_stage",
        "fact_payload_scalar",
        "resume_canvas_scalar",
        "generation_context_unknown",
        "event_payload_scalar",
        "version_resume_scalar",
    ],
)
def test_v7_rejects_invalid_domain_json_during_inspection_before_writes(workspace_db, case):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    reset(db, owner)

    def change(payload):
        tables = payload["tables"]
        if case == "preferences_scalar":
            tables["candidate_profiles"][0]["preferences"] = "remote"
        elif case == "preferences_boolean_string":
            tables["candidate_profiles"][0]["preferences"]["remote_only"] = "false"
        elif case == "preferences_numeric_string":
            tables["candidate_profiles"][0]["preferences"]["workload_min"] = "50"
        elif case == "invalid_application_stage":
            tables["applications"][0]["current_stage"] = "invented"
        elif case == "fact_payload_scalar":
            tables["career_facts"][0]["payload"] = "Python"
        elif case == "resume_canvas_scalar":
            tables["resume_drafts"][0]["canvas_document"] = "canvas"
        elif case == "generation_context_unknown":
            tables["resume_drafts"][0]["generation_context"] = {"authority": "external"}
        elif case == "event_payload_scalar":
            tables["application_events"][0]["payload"] = "event"
        else:
            tables["resume_versions"][0]["snapshot"]["resume"] = "layout"

    malformed = rewrite(exported, change)
    with pytest.raises(ArchiveError):
        inspect_archive(db, owner.id, malformed)
    with pytest.raises(ArchiveError):
        restore_archive(db, owner.id, malformed)
    assert db.query(CandidateProfile).count() == 0
    assert not resolve_data_path(seeded["packet_path"]).exists()


@pytest.mark.parametrize("case", ["manifest_extra", "entry_extra", "duplicate_entry"])
def test_v7_manifest_is_strict_and_has_unique_entries(workspace_db, case):
    db, owner, _ = workspace_db
    seed_workspace(db, owner)
    exported = export_archive(db, owner.id)

    def change(manifest):
        if case == "manifest_extra":
            manifest["unexpected"] = True
        elif case == "entry_extra":
            manifest["entries"][0]["unexpected"] = True
        else:
            manifest["entries"].append(dict(manifest["entries"][0]))

    with pytest.raises(ArchiveError):
        inspect_archive(db, owner.id, rewrite_manifest(exported, change))


def test_v7_payload_rejects_unknown_top_level_fields(workspace_db):
    db, owner, _ = workspace_db
    seed_workspace(db, owner)
    exported = export_archive(db, owner.id)

    def change(payload):
        payload["unexpected"] = []

    with pytest.raises(ArchiveError):
        inspect_archive(db, owner.id, rewrite(exported, change))


def test_v7_manifest_rejects_duplicate_json_object_keys(workspace_db):
    db, owner, _ = workspace_db
    seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    with zipfile.ZipFile(BytesIO(exported)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    original = members["manifest.json"].decode("utf-8")
    members["manifest.json"] = (
        '{"format":"careeros-portable-archive",' + original.lstrip()[1:]
    ).encode("utf-8")
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for name, content in members.items():
            target.writestr(name, content)
    with pytest.raises(ArchiveError):
        inspect_archive(db, owner.id, output.getvalue())


def test_existing_ai_execution_makes_inspection_and_restore_report_nonempty_vault(workspace_db):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    reset(db, owner)
    db.add(
        AIExecution(
            user_id=owner.id,
            task="coach",
            contract_version="1.0.0",
            model_id="local/synthetic",
            input_fingerprint="a" * 64,
            output_fingerprint=None,
            row_fingerprints=[],
            row_input_fingerprints=[],
            evidence_count=0,
            accepted=False,
            repair_count=0,
            validation_codes=[],
            duration_ms=1,
        )
    )
    db.commit()
    inspected = inspect_archive(db, owner.id, exported)
    assert not inspected.restorable
    assert "restore_requires_empty_vault" in inspected.warning_codes
    with pytest.raises(ArchiveConflictError, match="AI execution history"):
        restore_archive(db, owner.id, exported)
    assert not resolve_data_path(seeded["packet_path"]).exists()


def test_shared_catalog_conflict_is_reported_by_inspection_before_file_writes(workspace_db):
    db, owner, foreign = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    listing = (
        db.query(ScrapedJob)
        .filter_by(platform="manual", external_url="https://example.test/role")
        .one()
    )
    db.add(Job(user_id=foreign.id, scraped_job_id=listing.id))
    db.commit()
    reset(db, owner)
    listing.description = "Foreign owner changed this shared catalog row"
    db.commit()
    inspected = inspect_archive(db, owner.id, exported)
    assert not inspected.restorable
    assert "restore_target_conflict" in inspected.warning_codes
    assert not resolve_data_path(seeded["packet_path"]).exists()
    with pytest.raises(ArchiveConflictError):
        restore_archive(db, owner.id, exported)
    assert not resolve_data_path(seeded["packet_path"]).exists()


def test_packet_files_rollback_with_failed_database_restore(workspace_db, monkeypatch):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    reset(db, owner)

    def fail(*args, **kwargs):
        assert resolve_data_path(seeded["packet_path"]).read_bytes() == seeded["packet_bytes"]
        raise RuntimeError("synthetic late DB failure")

    monkeypatch.setattr(restore_module, "_restore_preference_state", fail)
    with pytest.raises(RestoreRolledBackError, match="synthetic late DB failure"):
        restore_archive(db, owner.id, exported)
    assert db.query(CandidateProfile).count() == db.query(ApplicationPacketArtifact).count() == 0
    assert not resolve_data_path(seeded["packet_path"]).exists()


def test_v7_restore_rejects_foreign_uuid_collision(workspace_db):
    db, owner, foreign = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    reset(db, owner)
    other = CandidateProfile(id=seeded["profile"], user_id=foreign.id, display_name="Foreign")
    db.add(other)
    db.commit()
    with pytest.raises(ArchiveConflictError):
        restore_archive(db, owner.id, exported)
    assert db.get(CandidateProfile, seeded["profile"]).user_id == foreign.id
    assert not resolve_data_path(seeded["packet_path"]).exists()


def rebuild_archive(members, payload, version=8):
    members["payload.json"] = canonical_json(payload)
    manifest = json.loads(members["manifest.json"])
    manifest["format_version"] = version
    manifest["record_counts"] = {name: len(rows) for name, rows in payload["tables"].items()}
    manifest["entries"] = [
        {"path": name, "sha256": sha256(content), "byte_size": len(content)}
        for name, content in sorted(members.items())
        if name != "manifest.json"
    ]
    members["manifest.json"] = canonical_json(manifest)
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue()


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6])
def test_legacy_photo_backfill_preserves_historical_snapshot_and_artifact(workspace_db, version):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    with zipfile.ZipFile(BytesIO(exported)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    payload = json.loads(members["payload.json"])
    tables = payload["tables"]
    original_snapshot = tables["resume_versions"][0]["snapshot"]
    for name in ("resume_drafts", "resume_versions"):
        for row in tables[name]:
            row["template_kind"] = "photo"
            for field in ("template_id", "template_version", "locale"):
                row.pop(field)
    tables["source_documents"][0].pop("source_role")
    tables["application_events"] = [
        row for row in tables["application_events"] if row["event_type"] != "dossier_published"
    ]
    for row in tables["applications"]:
        for field in (
            "job_title",
            "job_company",
            "job_location",
            "latest_event_at",
            "next_action_task_id",
            "next_action_title",
            "next_action_at",
            "next_action_priority",
        ):
            row.pop(field, None)
        if version < 3:
            row.pop("scraped_job_id", None)
    # Historical v6 drafts bind only published versions.
    for row in tables["application_dossier_drafts"]:
        row["resume_version_id"] = seeded["version"]
        row.pop("resume_draft_id")
        row.pop("resume_draft_revision")
    payload["tables"] = {
        name: rows for name, rows in tables.items() if name in expected_tables(version)
    }
    payload["file_bindings"] = [
        binding
        for binding in payload["file_bindings"]
        if binding["table"] != "application_packet_artifacts"
    ]
    allowed = {binding["member"] for binding in payload["file_bindings"]} | {
        "manifest.json",
        "payload.json",
    }
    members = {name: content for name, content in members.items() if name in allowed}
    legacy = rebuild_archive(members, payload, version)
    old_resume_bytes = {
        name: content
        for name, content in members.items()
        if name.startswith("files/resume-artifacts/")
    }
    reset(db, owner)
    response = restore_archive(db, owner.id, legacy)
    assert response.format_version == version
    assert db.get(ResumeDraft, seeded["draft"]).template_id == "swiss-software-en"
    restored_version = db.get(ResumeVersion, seeded["version"])
    assert restored_version.template_id == "swiss-software-en" and restored_version.locale == "en"
    assert restored_version.snapshot == original_snapshot
    assert db.query(SourceDocument).one().source_role == "profile"
    with zipfile.ZipFile(BytesIO(export_archive(db, owner.id))) as archive:
        assert {name: archive.read(name) for name in old_resume_bytes} == old_resume_bytes


def test_packet_nested_manifest_checksum_is_checked_even_with_valid_outer_archive(workspace_db):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    with zipfile.ZipFile(BytesIO(exported)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    payload = json.loads(members["payload.json"])
    binding = next(
        row for row in payload["file_bindings"] if row["table"] == "application_packet_artifacts"
    )
    output = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(members[binding["member"]])) as original,
        zipfile.ZipFile(output, "w") as forged,
    ):
        for name in original.namelist():
            forged.writestr(
                name, b"modified historical CV" if name == "resume.pdf" else original.read(name)
            )
    packet = payload["tables"]["application_packet_artifacts"][0]
    old_digest = packet["sha256"]
    packet.update(sha256=sha256(output.getvalue()), byte_size=len(output.getvalue()))
    packet["storage_path"] = packet["storage_path"].replace(old_digest, packet["sha256"])
    binding["storage_path"] = packet["storage_path"]
    members[binding["member"]] = output.getvalue()
    tampered = rebuild_archive(members, payload)
    reset(db, owner)
    with pytest.raises(ArchiveError, match="packet failed verification"):
        restore_archive(db, owner.id, tampered)
    assert not resolve_data_path(packet["storage_path"]).exists()
    assert not resolve_data_path(seeded["packet_path"]).exists()


def test_packet_nested_manifest_rejects_duplicate_keys_with_valid_recomputed_digests(
    workspace_db,
):
    db, owner, _ = workspace_db
    seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    with zipfile.ZipFile(BytesIO(exported)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    payload = json.loads(members["payload.json"])
    binding = next(
        row for row in payload["file_bindings"] if row["table"] == "application_packet_artifacts"
    )
    with zipfile.ZipFile(BytesIO(members[binding["member"]])) as packet_archive:
        packet_members = {
            name: packet_archive.read(name) for name in packet_archive.namelist()
        }
    manifest = json.loads(packet_members["manifest.json"])
    duplicate_manifest = (
        '{"application_id":'
        + json.dumps(manifest["application_id"], separators=(",", ":"))
        + ","
        + packet_members["manifest.json"].decode("utf-8").lstrip()[1:]
    ).encode("utf-8")
    assert json.loads(duplicate_manifest) == manifest
    packet_members["manifest.json"] = duplicate_manifest
    packet_output = BytesIO()
    with zipfile.ZipFile(packet_output, "w") as packet_archive:
        for name, content in packet_members.items():
            packet_archive.writestr(name, content)
    packet_bytes = packet_output.getvalue()

    packet = payload["tables"]["application_packet_artifacts"][0]
    old_digest = packet["sha256"]
    packet.update(sha256=sha256(packet_bytes), byte_size=len(packet_bytes))
    packet["storage_path"] = packet["storage_path"].replace(old_digest, packet["sha256"])
    binding["storage_path"] = packet["storage_path"]
    event = next(
        row for row in payload["tables"]["application_events"] if row["id"] == packet["dossier_id"]
    )
    event["payload"]["dossier"]["manifest_sha256"] = sha256(duplicate_manifest)
    members[binding["member"]] = packet_bytes
    tampered = rebuild_archive(members, payload)

    with pytest.raises(ArchiveError):
        inspect_archive(db, owner.id, tampered)
    reset(db, owner)
    with pytest.raises(ArchiveError, match="packet failed verification"):
        restore_archive(db, owner.id, tampered)
    assert not resolve_data_path(packet["storage_path"]).exists()


@pytest.mark.parametrize("operation", ["export", "restore", "reset", "erasure"])
def test_maintenance_reconciles_orphan_packet_journals(workspace_db, operation):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    if operation == "restore":
        reset(db, owner)
    orphan = store_packet_artifact(
        application_id=str(uuid.uuid4()),
        dossier_id=str(uuid.uuid4()),
        data=b"synthetic crash-left bytes",
    )
    if operation == "export":
        export_archive(db, owner.id)
    elif operation == "restore":
        restore_archive(db, owner.id, exported)
    elif operation == "reset":
        reset(db, owner)
    else:
        authority = issue_auth_session(db, owner)
        begin_vault_maintenance(
            db,
            owner.id,
            authority.session_id,
            VAULT_STATE_ERASURE_PENDING,
            token_purpose=ACCESS_PURPOSE_SESSION,
        )
        delete_complete_vault(
            db, owner.id, erase_auth_sessions=True, erasure_session_id=authority.session_id
        )
    assert not all_packet_journals()
    assert not resolve_data_path(orphan.relative_path).exists()
    if operation in {"reset", "erasure"}:
        assert (
            not db.query(AgentWorkRequest).count()
            and not db.query(ApplicationPacketArtifact).count()
        )
        assert not resolve_data_path(seeded["packet_path"]).exists()


def test_reset_rollback_restores_packet_files_and_agent_history(workspace_db, monkeypatch):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    export_archive(db, owner.id)
    authority = issue_auth_session(db, owner)
    begin_vault_maintenance(
        db,
        owner.id,
        authority.session_id,
        VAULT_STATE_RESET_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )

    def fail():
        raise RuntimeError("synthetic deletion commit failure")

    monkeypatch.setattr(db, "commit", fail)
    with pytest.raises(RuntimeError, match="synthetic deletion commit failure"):
        delete_complete_vault(db, owner.id, maintenance_session_id=authority.session_id)
    assert db.get(AgentWorkRequest, seeded["work"]) is not None
    assert db.query(ApplicationPacketArtifact).count() == 1
    assert resolve_data_path(seeded["packet_path"]).read_bytes() == seeded["packet_bytes"]


def test_restored_accepted_receipt_is_historical_and_forged_analysis_is_quarantined(workspace_db):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    work = db.get(AgentWorkRequest, seeded["work"])
    work.state = "accepted"
    receipt = {
        "request_id": work.id,
        "proposal_id": seeded["proposal"],
        "work_kind": "analyze",
        "accepted_at": datetime.now(UTC).isoformat(),
        "target_job_id": seeded["job"],
    }
    work.accepted_receipt = receipt
    db.commit()
    exported = export_archive(db, owner.id)

    def forge(payload):
        payload["tables"]["jobs"][0].update(
            analysis_provenance="external_agent_proposal",
            analysis_structured={
                "source": "external_agent",
                "request_id": work.id,
                "proposal_id": seeded["proposal"],
            },
            affinity_score=100,
            worth_applying=True,
        )

    exported = rewrite(exported, forge)
    reset(db, owner)
    restore_archive(db, owner.id, exported)
    restored = db.get(AgentWorkRequest, seeded["work"])
    assert restored.state == "accepted" and restored.accepted_receipt == receipt
    assert restored.bound_grant_id is None
    job = db.get(Job, restored.target_job_id)
    assert job.analysis_provenance is None and job.analysis_structured is None
    assert job.affinity_score is None and not job.worth_applying
    assert (
        job.analysis_legacy_snapshot["analysis"]["analysis_provenance"] == "external_agent_proposal"
    )


def test_reset_preserves_packet_path_claimed_by_foreign_asset(workspace_db):
    db, owner, foreign = workspace_db
    seeded = seed_workspace(db, owner)
    export_archive(db, owner.id)
    foreign_profile = CandidateProfile(user_id=foreign.id, display_name="Foreign")
    db.add(foreign_profile)
    db.flush()
    foreign_asset = CareerAsset(
        profile_id=foreign_profile.id,
        kind="source_document",
        original_name="foreign.zip",
        media_type="application/zip",
        sha256=sha256(seeded["packet_bytes"]),
        byte_size=len(seeded["packet_bytes"]),
        storage_path=seeded["packet_path"],
        normalized=False,
    )
    db.add(foreign_asset)
    db.commit()
    reset(db, owner)
    assert db.get(CareerAsset, foreign_asset.id) is not None
    assert resolve_data_path(seeded["packet_path"]).read_bytes() == seeded["packet_bytes"]
    assert db.query(ApplicationPacketArtifact).count() == 0


def test_export_recovery_failure_releases_writer_reservation(workspace_db, monkeypatch):
    db, owner, _ = workspace_db
    seed_workspace(db, owner)

    def fail(_db):
        raise OSError("synthetic packet recovery failure")

    monkeypatch.setattr(archive_module, "reconcile_packet_journals", fail)
    with pytest.raises(OSError, match="synthetic packet recovery failure"):
        export_archive(db, owner.id)
    assert not db.in_transaction()


def test_lost_restore_commit_ack_preserves_committed_packet_and_history(workspace_db, monkeypatch):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    reset(db, owner)
    commit = db.commit

    def lost_ack():
        commit()
        raise OSError("synthetic lost commit acknowledgement")

    monkeypatch.setattr(db, "commit", lost_ack)
    result = restore_archive(db, owner.id, exported)
    assert result.restored_records["application_packet_artifacts"] == 1
    assert db.get(AgentWorkRequest, seeded["work"]).bound_grant_id is None
    assert resolve_data_path(seeded["packet_path"]).read_bytes() == seeded["packet_bytes"]


@pytest.mark.parametrize("invalid_size", [0, MAX_DOSSIER_BUNDLE_BYTES + 1, True])
def test_packet_size_metadata_rejected_before_restore(workspace_db, invalid_size):
    db, owner, _ = workspace_db
    seeded = seed_workspace(db, owner)
    exported = export_archive(db, owner.id)
    reset(db, owner)

    def alter(payload):
        payload["tables"]["application_packet_artifacts"][0]["byte_size"] = invalid_size

    with pytest.raises(ArchiveError, match="file size metadata"):
        restore_archive(db, owner.id, rewrite(exported, alter))
    assert not resolve_data_path(seeded["packet_path"]).exists()
