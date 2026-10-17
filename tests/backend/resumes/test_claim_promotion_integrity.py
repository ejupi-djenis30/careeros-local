from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.api.deps import get_current_user_id, limiter
from backend.api.routes.resumes import router
from backend.career.models import CandidateProfile, CareerFact
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent, get_db
from backend.models import User
from backend.resumes.exceptions import (
    ResumeConflictError,
    ResumeNotFoundError,
    ResumeValidationError,
)
from backend.resumes.models import ResumeDraft
from backend.resumes.schemas import ResumeClaimPromote, ResumeDraftCreate, ResumeDraftUpdate
from backend.resumes.service import ResumeService


@dataclass
class ClaimVault:
    factory: sessionmaker
    user_id: int
    profile_id: str
    fact_id: str


@pytest.fixture
def claim_vault(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.core.config.settings.DATA_DIR", str(tmp_path / "data"))
    database_url = "sqlite:///" + (tmp_path / "claims.sqlite").as_posix()
    ensure_sqlite_parent(database_url)
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", configure_sqlite_connection)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=True)
    with factory() as session:
        user = User(username="synthetic-claim-owner", hashed_password="not-used")
        session.add(user)
        session.flush()
        profile = CandidateProfile(user_id=user.id, display_name="Synthetic owner", revision=1)
        session.add(profile)
        session.flush()
        fact = CareerFact(
            profile_id=profile.id,
            fact_type="skill",
            position=0,
            payload={"name": "Synthetic skill"},
            verification_status="confirmed",
            confidence=1,
        )
        session.add(fact)
        session.commit()
        vault = ClaimVault(factory, user.id, profile.id, fact.id)
    try:
        yield vault
    finally:
        engine.dispose()


def _draft(vault, subtitle="Synthetic context"):
    with vault.factory() as session:
        service = ResumeService(session)
        draft = service.create(
            vault.user_id,
            ResumeDraftCreate(title="Synthetic draft", selected_fact_ids=[vault.fact_id]),
        )
        canvas = deepcopy(draft.canvas_document.model_dump(mode="json"))
        canvas["sections"].append(
            {
                "id": "manual-achievements",
                "kind": "achievement",
                "title": "ACHIEVEMENTS",
                "visible": True,
                "page_break_before": False,
                "blocks": [
                    {
                        "id": block,
                        "kind": "fact",
                        "fact_ids": [],
                        "visible": True,
                        "content": {
                            "title": "Synthetic " + block,
                            "subtitle": subtitle,
                            "description": "Synthetic evidence",
                            "bullets": [],
                        },
                        "manual_fields": ["title", "description"],
                    }
                    for block in ("claim-a", "claim-b")
                ],
            }
        )
        return service.update(
            vault.user_id,
            draft.id,
            ResumeDraftUpdate(
                expected_revision=draft.revision,
                title=draft.title,
                selected_fact_ids=[vault.fact_id],
                canvas_document=canvas,
            ),
        )


def _request(draft, block="claim-a"):
    return ResumeClaimPromote(
        expected_revision=draft.revision,
        expected_profile_revision=1,
        block_id=block,
    )


def _fingerprint(vault):
    with vault.factory() as session:
        rows = {
            model.__tablename__: [
                {column.name: getattr(row, column.name) for column in model.__table__.columns}
                for row in session.query(model).order_by(model.id)
            ]
            for model in (CandidateProfile, CareerFact, ResumeDraft)
        }
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


@pytest.mark.parametrize("different_draft", [False, True])
def test_cached_promotion_conflict_preserves_all_committed_state(claim_vault, different_draft):
    vault = claim_vault
    draft = _draft(vault)
    other = _draft(vault) if different_draft else draft
    with vault.factory() as first, vault.factory() as second:
        winner, stale = ResumeService(first), ResumeService(second)
        cached = (stale.drafts.draft(vault.user_id, other.id), stale.drafts.profile(vault.user_id))
        assert (cached[0].revision, cached[1].revision) == (other.revision, 1)
        promoted = winner.promote_claim(vault.user_id, draft.id, _request(draft))
        assert promoted.revision == draft.revision + 1
        before = _fingerprint(vault)

        with pytest.raises(ResumeConflictError):
            stale.promote_claim(vault.user_id, other.id, _request(other, "claim-b"))
        second.rollback()

        assert _fingerprint(vault) == before


def test_independent_concurrent_promotions_have_one_winner(claim_vault):
    vault = claim_vault
    draft = _draft(vault)
    ready = Barrier(2)

    def promote(block):
        with vault.factory() as session:
            service = ResumeService(session)
            cached = (
                service.drafts.draft(vault.user_id, draft.id),
                service.drafts.profile(vault.user_id),
            )
            ready.wait(timeout=10)
            assert cached[0].revision == draft.revision
            try:
                service.promote_claim(vault.user_id, draft.id, _request(draft, block))
                return "committed"
            except ResumeConflictError:
                session.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(promote, ["claim-a", "claim-b"]))
    assert sorted(results) == ["committed", "conflict"]
    with vault.factory() as session:
        assert session.query(CareerFact).count() == 2


@pytest.mark.parametrize("subtitle", ["", " \t ", "Synthetic context"])
def test_explicit_http_promotion_returns_one_valid_acknowledgement(claim_vault, subtitle):
    vault = claim_vault
    draft = _draft(vault, subtitle)
    with vault.factory() as session:
        assert session.query(CareerFact).count() == 1
        assert session.get(CandidateProfile, vault.profile_id).revision == 1
    app = FastAPI(
        telemetry={
            key: False
            for key in (
                "tracing",
                "metrics",
                "logs",
                "operation_spans",
                "auto_configure",
            )
        }
    )
    app.state.limiter = limiter
    app.include_router(router, prefix="/api/v1/resumes")

    def owned_session():
        with vault.factory() as session:
            yield session

    app.dependency_overrides[get_db] = owned_session
    app.dependency_overrides[get_current_user_id] = lambda: vault.user_id
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/resumes/{draft.id}/claims/promote",
            json=_request(draft).model_dump(),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["revision"] == draft.revision + 1
        assert payload["profile_revision"] == 2
        block = next(
            block
            for section in payload["canvas_document"]["sections"]
            for block in section["blocks"]
            if block["id"] == "claim-a"
        )
        assert block["content"]["subtitle"] == subtitle.strip()
        assert len(block["fact_ids"]) == 1
        promoted_fact = block["fact_ids"][0]
        assert promoted_fact in payload["selected_fact_ids"]
        before = _fingerprint(vault)
        retry = client.post(
            f"/api/v1/resumes/{draft.id}/claims/promote",
            json=_request(draft).model_dump(),
        )
        assert retry.status_code == 409
        assert _fingerprint(vault) == before
    with vault.factory() as session:
        assert session.query(CareerFact).count() == 2
        assert session.get(CareerFact, promoted_fact).verification_status == "confirmed"


@pytest.mark.parametrize("failure", ["commit", "response"])
def test_failed_promotion_rolls_back_fact_links_and_revisions(claim_vault, monkeypatch, failure):
    vault = claim_vault
    draft = _draft(vault)
    before = _fingerprint(vault)
    with vault.factory() as session:
        service = ResumeService(session)

        def fail(*_args, **_kwargs):
            raise ResumeValidationError("Synthetic promotion failure")

        monkeypatch.setattr(
            session if failure == "commit" else service.drafts,
            "commit" if failure == "commit" else "response",
            fail,
        )
        with pytest.raises(ResumeValidationError, match="Synthetic promotion failure"):
            service.promote_claim(vault.user_id, draft.id, _request(draft))
        session.rollback()
    assert _fingerprint(vault) == before


def test_promotion_cannot_confirm_another_owners_claim(claim_vault):
    vault = claim_vault
    draft = _draft(vault)
    before = _fingerprint(vault)
    with vault.factory() as session:
        with pytest.raises(ResumeNotFoundError):
            ResumeService(session).promote_claim(vault.user_id + 1, draft.id, _request(draft))
        session.rollback()
    assert _fingerprint(vault) == before
