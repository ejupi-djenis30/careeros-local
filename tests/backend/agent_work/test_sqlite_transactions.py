"""Real migrated file-SQLite sessions, independent from the shared StaticPool fixture."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from backend.agent_work.acceptance import accept_work_proposal
from backend.agent_work.models import AgentProposal, AgentWorkRequest
from backend.agent_work.proposal_service import ProposalService
from backend.agent_work.schemas import AgentWorkAcceptRequest
from backend.agent_work.service import AgentWorkError, AgentWorkService
from backend.applications.models import Application
from backend.db.base import configure_sqlite_connection
from backend.models.job import Job
from backend.models.user import User
from tests.backend.agent_work.helpers import make_work, submission


@pytest.fixture
def file_sessions(tmp_path):
    root = Path(__file__).resolve().parents[3]
    url = "sqlite:///" + (tmp_path / "real-vault.sqlite").as_posix()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend/migrations"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    engine = sa.create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})
    sa.event.listen(engine, "connect", configure_sqlite_connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(User(id=9001, username="synthetic-transactions", hashed_password="synthetic-only"))
        db.commit()
    yield factory
    engine.dispose()


def test_cancel_cas_with_two_loaded_independent_sessions(file_sessions):
    with file_sessions() as setup:
        work, _, _, _ = make_work(setup, 9001)
    with file_sessions() as first, file_sessions() as second:
        first.get(AgentWorkRequest, work.id)
        second.get(AgentWorkRequest, work.id)
        AgentWorkService(first).cancel_work_request(9001, work.id, 1)
        with pytest.raises(AgentWorkError):
            AgentWorkService(second).cancel_work_request(9001, work.id, 1)
    with file_sessions() as db:
        req = db.get(AgentWorkRequest, work.id)
        assert req.state == "canceled" and req.revision == 2


def test_concurrent_submissions_leave_one_immutable_proposal(file_sessions):
    with file_sessions() as setup:
        work, grant, _, _ = make_work(setup, 9001)
    submitted = submission(work)
    barrier = Barrier(2)

    def submit():
        with file_sessions() as db:
            barrier.wait()
            try:
                return (
                    ProposalService(db)
                    .submit_proposal(grant.id, work.id, submitted.model_copy(deep=True))
                    .proposal_id
                )
            except AgentWorkError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))
    with file_sessions() as db:
        proposal = db.query(AgentProposal).one()
        req = db.get(AgentWorkRequest, work.id)
        assert req.state == "returned" and req.revision == 2
        assert proposal.id in results
        assert (
            ProposalService(db).submit_proposal(grant.id, work.id, submitted).proposal_id
            == proposal.id
        )


def test_concurrent_acceptance_has_one_atomic_receipt(file_sessions):
    with file_sessions() as setup:
        work, grant, _, _ = make_work(setup, 9001)
        ProposalService(setup).submit_proposal(grant.id, work.id, submission(work))
        expected = setup.get(AgentWorkRequest, work.id).input_revisions
    barrier = Barrier(2)

    def accept():
        with file_sessions() as db:
            barrier.wait()
            try:
                return accept_work_proposal(
                    db,
                    user_id=9001,
                    request_id=work.id,
                    accept_in=AgentWorkAcceptRequest(
                        expected_revision=2, expected_target_revisions=expected
                    ),
                )
            except AgentWorkError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: accept(), range(2)))
    assert any(isinstance(result, dict) for result in results)
    with file_sessions() as db:
        assert db.query(Job).count() == db.query(Application).count() == 1
        req = db.get(AgentWorkRequest, work.id)
        assert req.state == "accepted" and req.revision == 3 and req.accepted_receipt


def test_late_acceptance_failure_rolls_back_catalog_and_work(file_sessions, monkeypatch):
    with file_sessions() as db:
        work, grant, _, _ = make_work(db, 9001)
        ProposalService(db).submit_proposal(grant.id, work.id, submission(work))
        expected = db.get(AgentWorkRequest, work.id).input_revisions

        def fail_commit():
            raise RuntimeError("synthetic late failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="synthetic late failure"):
            accept_work_proposal(
                db,
                user_id=9001,
                request_id=work.id,
                accept_in=AgentWorkAcceptRequest(
                    expected_revision=2, expected_target_revisions=expected
                ),
            )
    with file_sessions() as db:
        assert db.query(Job).count() == db.query(Application).count() == 0
        assert db.get(AgentWorkRequest, work.id).state == "returned"


def test_deleting_grant_preserves_history_and_removes_authority(file_sessions):
    from backend.automation.models import AutomationGrant

    with file_sessions() as db:
        work, grant, _, _ = make_work(db, 9001)
        db.delete(db.get(AutomationGrant, grant.id))
        db.commit()
        db.expire_all()
        req = db.get(AgentWorkRequest, work.id)
        assert req.bound_grant_id is None
        assert req.context_snapshot["historical_grant_id"] == grant.id
        with pytest.raises(AgentWorkError):
            ProposalService(db).submit_proposal(grant.id, work.id, submission(work))


@pytest.mark.asyncio
async def test_real_sdk_session_against_leased_loopback_backend(file_sessions, tmp_path):
    import socket
    import threading
    import time
    from datetime import timedelta

    import httpx
    import uvicorn
    from fastapi import FastAPI
    from mcp.shared.memory import create_connected_server_and_client_session

    from backend.api.routes.agent_bridge import router
    from backend.automation.desktop_client import DesktopBridgeClient
    from backend.automation.grants import revoke_grant
    from backend.automation.workspace_mcp import build_workspace_mcp_server
    from backend.db.base import get_db
    from backend.desktop.lifecycle import desktop_instance_lease
    from backend.desktop.session import DesktopSessionMiddleware

    with file_sessions() as db:
        work, grant, token, _ = make_work(db, 9001)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/agent-bridge")
    app.add_middleware(
        DesktopSessionMiddleware,
        token="synthetic-desktop-session-" * 2,
        exempt_path_prefix="/api/v1/agent-bridge",
    )

    def database():
        with file_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    with desktop_instance_lease(root=tmp_path / "leased-vault"):
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            with DesktopBridgeClient(f"http://127.0.0.1:{port}/api/v1", token) as bridge:
                async with create_connected_server_and_client_session(
                    build_workspace_mcp_server(bridge),
                    read_timeout_seconds=timedelta(seconds=5),
                    raise_exceptions=True,
                ) as session:
                    assert not (await session.call_tool("get_agent_status", {})).isError
                    context = await session.call_tool("get_work_context", {"request_id": work.id})
                    assert not context.isError and work.input_digest in context.content[0].text
                    body = submission(work).model_dump(mode="json")
                    submitted = await session.call_tool("submit_work_result", body)
                    assert not submitted.isError, submitted.content
                    with file_sessions() as db:
                        revoke_grant(db, user_id=9001, grant_id=grant.id)
                    denied = await session.call_tool("get_work_result", {"request_id": work.id})
                    assert denied.isError and "grant_revoked" in denied.content[0].text
            with httpx.Client(trust_env=False) as client:
                denied = client.get(
                    f"http://127.0.0.1:{port}/api/v1/agent-bridge/status",
                    headers={"Authorization": "Bearer synthetic-owner-jwt"},
                )
                assert denied.status_code == 401
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
            assert not thread.is_alive()
