from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.automation import cli, mcp_server, runtime
from backend.automation.grants import TOKEN_PREFIX, AutomationGrantError
from backend.automation.mcp_server import run_server
from backend.automation.models import AutomationGrant
from backend.automation.runtime import AutomationRuntimeError
from backend.services.auth import DUMMY_PASSWORD_HASH


def test_json_output_is_safe_on_legacy_windows_code_pages() -> None:
    raw = io.BytesIO()
    destination = io.TextIOWrapper(raw, encoding="cp1252", write_through=True)

    cli._emit({"company": "Code Compass 🧭"}, stream=destination)

    assert json.loads(raw.getvalue().decode("cp1252")) == {"company": "Code Compass 🧭"}


def test_client_config_uses_environment_reference_and_absolute_data_dir(
    tmp_path: Path, capsys
) -> None:
    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path.resolve()),
            "mcp",
            "config",
            "--client",
            "claude-code",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    server = payload["mcpServers"]["careeros"]
    assert server["command"] == "careeros"
    assert server["env"]["CAREEROS_MCP_TOKEN"] == "${CAREEROS_MCP_TOKEN}"
    assert str(tmp_path.resolve()) in server["args"]
    assert TOKEN_PREFIX not in json.dumps(payload)


def test_cli_forwards_explicit_developer_desktop_url_to_workspace_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def capture_server(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(mcp_server, "run_server", capture_server)

    assert (
        cli.main(
            [
                "mcp",
                "serve",
                "--desktop-url",
                "http://127.0.0.1:8000/api/v1",
                "--acknowledge-agent-disclosure",
            ]
        )
        == 0
    )
    assert captured == {
        "data_dir": None,
        "desktop_url": "http://127.0.0.1:8000/api/v1",
        "acknowledge_agent_disclosure": True,
    }


def test_mcp_server_requires_explicit_disclosure_acknowledgement() -> None:
    with pytest.raises(AutomationRuntimeError) as raised:
        run_server(
            data_dir=None,
            acknowledge_agent_disclosure=False,
            token=TOKEN_PREFIX + "x" * 43,
        )
    assert raised.value.code == "disclosure_acknowledgement_required"


def test_standalone_mcp_redacts_unexpected_startup_failure(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    sensitive_token = TOKEN_PREFIX + "s" * 43
    sensitive_path = str(tmp_path / "private-vault")
    monkeypatch.setenv("CAREEROS_MCP_TOKEN", sensitive_token)

    def fail_startup(**_kwargs) -> None:
        raise RuntimeError(f"database failure at {sensitive_path} using {sensitive_token}")

    monkeypatch.setattr(mcp_server, "run_server", fail_startup)

    assert mcp_server.main(["--acknowledge-agent-disclosure"]) == 1
    diagnostics = capsys.readouterr().err
    payload = json.loads(diagnostics)
    assert payload == {
        "error": "internal_error",
        "message": "CareerOS MCP could not start",
    }
    assert sensitive_token not in diagnostics
    assert sensitive_path not in diagnostics
    assert "Traceback" not in diagnostics


def test_campaign_parser_requires_explicit_owner_fingerprint_and_write_acknowledgement() -> None:
    parser = cli._parser()
    arguments = parser.parse_args(
        [
            "campaign",
            "import",
            "campaign.zip",
            "--username",
            "owner",
            "--expected-fingerprint",
            "a" * 64,
            "--acknowledge-local-vault-write",
        ]
    )

    assert arguments.campaign_command == "import"
    assert arguments.username == "owner"
    assert arguments.expected_fingerprint == "a" * 64
    assert arguments.acknowledge_local_vault_write is True

    with pytest.raises(SystemExit):
        parser.parse_args(["campaign", "import", "campaign.zip", "--username", "owner"])


def test_campaign_preview_is_side_effect_free_and_emits_bounded_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    from tests.backend.campaigns.fixture_builder import build_fictional_campaign_zip

    archive = tmp_path / "campaign.zip"
    archive.write_bytes(build_fictional_campaign_zip(credentials_count=2))

    def runtime_must_not_start(*_args, **_kwargs):
        raise AssertionError("preview must not open the vault runtime")

    monkeypatch.setattr(cli, "automation_runtime", runtime_must_not_start)

    assert cli.main(["campaign", "preview", str(archive)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["fingerprint"]) == 64
    assert payload["credential_rows_omitted"] == 2
    assert payload["logical_application_count"] >= 1
    assert "password" not in json.dumps(payload).lower()


def test_campaign_import_requires_acknowledgement_before_reading_archive(capsys) -> None:
    exit_code = cli.main(
        [
            "campaign",
            "import",
            "missing-private-path.zip",
            "--username",
            "owner",
            "--expected-fingerprint",
            "a" * 64,
        ]
    )
    payload = json.loads(capsys.readouterr().err)

    assert exit_code == 2
    assert payload == {
        "error": "campaign_write_acknowledgement_required",
        "message": "Campaign import requires --acknowledge-local-vault-write",
    }
    assert "missing-private-path" not in json.dumps(payload)


def test_campaign_import_registers_resume_foreign_key_targets_in_fresh_process() -> None:
    code = """
from backend.models.base_model import Base
from backend.automation.cli import _load_campaign_persistence_models
assert "resume_versions" not in Base.metadata.tables
assert "resume_drafts" not in Base.metadata.tables
_load_campaign_persistence_models()
assert "resume_versions" in Base.metadata.tables
assert "resume_drafts" in Base.metadata.tables
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_campaign_import_binds_explicit_account_and_confirmed_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    from backend.campaigns import service as campaign_service

    archive = tmp_path / "campaign.zip"
    archive.write_bytes(b"fictional archive bytes")
    db = object()
    captured: dict[str, object] = {}

    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate, write_access):
        assert migrate is True
        assert write_access is True

        @contextlib.contextmanager
        def session_factory():
            yield db

        yield SimpleNamespace(session_factory=session_factory)

    def fake_import(_db, **kwargs):
        assert _db is db
        captured.update(kwargs)
        return {"campaign_id": "campaign-1", "created": True}

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    monkeypatch.setattr(cli, "_campaign_user", lambda _db, username: SimpleNamespace(id=17))
    monkeypatch.setattr(campaign_service, "import_campaign", fake_import)

    exit_code = cli.main(
        [
            "campaign",
            "import",
            str(archive),
            "--username",
            "explicit-owner",
            "--expected-fingerprint",
            "b" * 64,
            "--name",
            "September search",
            "--profile-display-name",
            "Fictional Candidate",
            "--acknowledge-local-vault-write",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"campaign_id": "campaign-1", "created": True}
    assert captured["user_id"] == 17
    assert captured["archive_bytes"] == b"fictional archive bytes"
    assert captured["expected_fingerprint"] == "b" * 64
    assert captured["campaign_name"] == "September search"
    assert captured["profile_display_name"] == "Fictional Candidate"


def test_campaign_read_is_owner_scoped_and_uses_read_only_runtime(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    from backend.campaigns import api_service

    db = object()

    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate):
        assert migrate is False

        @contextlib.contextmanager
        def session_factory():
            yield db

        yield SimpleNamespace(session_factory=session_factory)

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    monkeypatch.setattr(cli, "_campaign_user", lambda _db, username: SimpleNamespace(id=23))
    monkeypatch.setattr(
        api_service,
        "list_campaigns",
        lambda _db, user_id: [{"id": "campaign-owner-23", "owner": user_id}],
    )

    assert cli.main(["campaign", "list", "--username", "owner-23"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"id": "campaign-owner-23", "owner": 23}]


def test_campaign_submission_record_requires_explicit_write_acknowledgement(capsys) -> None:
    exit_code = cli.main(
        [
            "campaign",
            "record-submission",
            "campaign-1",
            "APP-001",
            "--username",
            "owner",
            "--expected-revision",
            "4",
            "--channel",
            "Test portal",
            "--confirmation",
            "Submission received",
            "--resume-sha256",
            "a" * 64,
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().err) == {
        "error": "campaign_submission_acknowledgement_required",
        "message": "Recording a submission requires --acknowledge-submission-record-write",
    }


def test_campaign_submission_record_is_owner_scoped_and_evidence_bound(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    from backend.applications import service as application_service

    db = object()
    captured: dict[str, object] = {}
    application = SimpleNamespace(id="application-7", current_stage="preparing", revision=7)

    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate, write_access):
        assert migrate is False
        assert write_access is True

        @contextlib.contextmanager
        def session_factory():
            yield db

        yield SimpleNamespace(session_factory=session_factory)

    class FakeApplicationService:
        def __init__(self, database):
            assert database is db

        def append_event(self, user_id, application_id, event):
            captured.update(
                user_id=user_id,
                application_id=application_id,
                event=event,
            )
            return SimpleNamespace(id=application_id, current_stage="applied", revision=8)

    def campaign_application(_db, **kwargs):
        assert _db is db
        captured.update(kwargs)
        return SimpleNamespace(application=application)

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    monkeypatch.setattr(cli, "_campaign_user", lambda _db, username: SimpleNamespace(id=29))
    monkeypatch.setattr(cli, "_campaign_application", campaign_application)
    monkeypatch.setattr(application_service, "ApplicationService", FakeApplicationService)

    exit_code = cli.main(
        [
            "campaign",
            "record-submission",
            "campaign-1",
            "APP-001",
            "--username",
            "explicit-owner",
            "--expected-revision",
            "7",
            "--channel",
            "Official ATS",
            "--confirmation",
            "Application received",
            "--resume-sha256",
            "a" * 64,
            "--cover-letter-sha256",
            "b" * 64,
            "--acknowledge-submission-record-write",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["created"] is True
    assert payload["stage"] == "applied"
    assert captured["user_id"] == 29
    assert captured["campaign_id"] == "campaign-1"
    assert captured["source_application_id"] == "APP-001"
    event = captured["event"]
    assert event.expected_revision == 7
    assert event.stage == "applied"
    assert event.payload == {
        "cover_letter_sha256": "b" * 64,
        "external_confirmation": "Application received",
        "resume_sha256": "a" * 64,
        "submission_channel": "Official ATS",
    }


def _outcome_args(*extra: str) -> list[str]:
    return [
        "campaign",
        "record-outcome",
        "campaign-1",
        "APP-001",
        "--username",
        "explicit-owner",
        "--expected-revision",
        "7",
        "--source-kind",
        "email",
        "--source-date",
        "2020-09-01",
        "--evidence",
        "Recruiting team email names this exact role and declines the application.",
        *extra,
    ]


def test_campaign_outcome_requires_acknowledgement_and_valid_evidence(capsys) -> None:
    assert cli.main(_outcome_args()) == 2
    assert json.loads(capsys.readouterr().err)["error"] == (
        "campaign_outcome_acknowledgement_required"
    )
    arguments = _outcome_args("--acknowledge-outcome-record-write")
    arguments[arguments.index("--source-date") + 1] = "not-a-date"
    assert cli.main(arguments) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "campaign_outcome_evidence_invalid"


def test_campaign_outcome_records_sourced_rejection_without_external_action(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from backend.applications import service as application_service

    db = object()
    captured: dict[str, object] = {}
    application = SimpleNamespace(id="application-7", current_stage="applied", revision=7)

    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate, write_access):
        assert migrate is False
        assert write_access is True

        @contextlib.contextmanager
        def session_factory():
            yield db

        yield SimpleNamespace(session_factory=session_factory)

    class FakeApplicationService:
        def __init__(self, database):
            assert database is db

        def append_event(self, user_id, application_id, event):
            captured.update(user_id=user_id, application_id=application_id, event=event)
            return SimpleNamespace(id=application_id, current_stage="rejected", revision=8)

    def campaign_application(_db, **kwargs):
        assert _db is db
        captured.update(kwargs)
        return SimpleNamespace(application=application)

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    monkeypatch.setattr(cli, "_campaign_user", lambda _db, username: SimpleNamespace(id=29))
    monkeypatch.setattr(cli, "_campaign_application", campaign_application)
    monkeypatch.setattr(application_service, "ApplicationService", FakeApplicationService)

    assert cli.main(_outcome_args("--acknowledge-outcome-record-write")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "rejected"
    assert payload["revision"] == 8
    assert captured["user_id"] == 29
    assert captured["campaign_id"] == "campaign-1"
    assert captured["source_application_id"] == "APP-001"
    event = captured["event"]
    assert event.expected_revision == 7
    assert event.event_type == "stage"
    assert event.stage == "rejected"
    assert event.payload == {
        "campaign_outcome_v1": {
            "outcome": "rejected",
            "source_kind": "email",
            "source_date": "2020-09-01",
        }
    }


def test_campaign_outcome_rejects_pre_submission_stage(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    db = object()

    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate, write_access):
        @contextlib.contextmanager
        def session_factory():
            yield db

        yield SimpleNamespace(session_factory=session_factory)

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    monkeypatch.setattr(cli, "_campaign_user", lambda _db, username: SimpleNamespace(id=29))
    monkeypatch.setattr(
        cli,
        "_campaign_application",
        lambda _db, **_kwargs: SimpleNamespace(
            application=SimpleNamespace(id="application-7", current_stage="preparing", revision=7)
        ),
    )
    assert cli.main(_outcome_args("--acknowledge-outcome-record-write")) == 2
    assert json.loads(capsys.readouterr().err)["error"] == (
        "campaign_outcome_not_post_submission"
    )


def _review_args(*extra: str) -> list[str]:
    return [
        "campaign",
        "record-review",
        "campaign-1",
        "APP-003",
        "--username",
        "explicit-owner",
        "--expected-revision",
        "7",
        "--decision",
        "hold",
        "--reason",
        "Official posting does not state the required workplace.",
        "--source-url",
        "https://jobs.example.org/roles/123",
        "--next-action",
        "Verify the office address with the employer",
        *extra,
    ]


def test_campaign_show_accepts_only_known_review_filters() -> None:
    parser = cli._parser()
    for decision in ("none", "hold", "excluded", "cleared"):
        arguments = parser.parse_args(
            [
                "campaign", "show", "campaign-1", "--username", "explicit-owner",
                "--review-decision", decision,
            ]
        )
        assert arguments.review_decision == decision
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "campaign", "show", "campaign-1", "--username", "explicit-owner",
                "--review-decision", "ready",
            ]
        )


def test_campaign_review_requires_acknowledgement_before_opening_vault(capsys) -> None:
    assert cli.main(_review_args()) == 2
    assert json.loads(capsys.readouterr().err) == {
        "error": "campaign_review_acknowledgement_required",
        "message": "Recording a review requires --acknowledge-review-record-write",
    }


@pytest.mark.parametrize(
    ("replacement", "expected_error"),
    [
        ({"reason": "short"}, "campaign_review_evidence_invalid"),
        ({"source_url": "file:///private/cv.pdf"}, "campaign_review_evidence_invalid"),
        ({"next_action": ""}, "campaign_review_evidence_invalid"),
        ({"decision": "excluded"}, "campaign_review_evidence_invalid"),
        ({"reason": "Invalid\nreview note"}, "campaign_review_evidence_invalid"),
        ({"expected_revision": "0"}, "campaign_review_evidence_invalid"),
    ],
)
def test_campaign_review_rejects_invalid_evidence_before_vault(
    replacement: dict[str, str], expected_error: str, capsys
) -> None:
    arguments = _review_args("--acknowledge-review-record-write")
    for key, value in replacement.items():
        arguments[arguments.index("--" + key.replace("_", "-")) + 1] = value
    assert cli.main(arguments) == 2
    assert json.loads(capsys.readouterr().err)["error"] == expected_error


def test_campaign_review_is_owner_scoped_revisioned_and_does_not_submit(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from backend.applications import service as application_service

    db = object()
    captured: dict[str, object] = {}
    application = SimpleNamespace(id="application-7", current_stage="preparing", revision=7)

    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate, write_access):
        assert migrate is False
        assert write_access is True

        @contextlib.contextmanager
        def session_factory():
            yield db

        yield SimpleNamespace(session_factory=session_factory)

    class FakeApplicationService:
        def __init__(self, database):
            assert database is db

        def append_event(self, user_id, application_id, event):
            captured.update(user_id=user_id, application_id=application_id, event=event)
            return SimpleNamespace(id=application_id, current_stage="preparing", revision=8)

    def campaign_application(_db, **kwargs):
        assert _db is db
        captured.update(kwargs)
        return SimpleNamespace(application=application)

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    monkeypatch.setattr(cli, "_campaign_user", lambda _db, username: SimpleNamespace(id=29))
    monkeypatch.setattr(cli, "_campaign_application", campaign_application)
    monkeypatch.setattr(application_service, "ApplicationService", FakeApplicationService)

    assert cli.main(_review_args("--acknowledge-review-record-write")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "preparing"
    assert payload["decision"] == "hold"
    assert payload["revision"] == 8
    assert captured["user_id"] == 29
    assert captured["campaign_id"] == "campaign-1"
    assert captured["source_application_id"] == "APP-003"
    event = captured["event"]
    assert event.expected_revision == 7
    assert event.event_type == "note"
    assert event.stage is None
    assert event.payload == {
        "campaign_review_v1": {
            "decision": "hold",
            "source_url": "https://jobs.example.org/roles/123",
            "next_action": "Verify the office address with the employer",
        }
    }


def test_campaign_review_rejects_post_submission_without_appending(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    db = object()

    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate, write_access):
        @contextlib.contextmanager
        def session_factory():
            yield db

        yield SimpleNamespace(session_factory=session_factory)

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    monkeypatch.setattr(cli, "_campaign_user", lambda _db, username: SimpleNamespace(id=29))
    monkeypatch.setattr(
        cli,
        "_campaign_application",
        lambda _db, **_kwargs: SimpleNamespace(
            application=SimpleNamespace(id="application-7", current_stage="applied", revision=7)
        ),
    )
    assert cli.main(_review_args("--acknowledge-review-record-write")) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "campaign_review_not_pre_submission"


def test_campaign_review_redacts_stale_revision_and_foreign_link(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from backend.applications import service as application_service
    from backend.applications.exceptions import ApplicationConflictError

    db = object()

    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate, write_access):
        @contextlib.contextmanager
        def session_factory():
            yield db

        yield SimpleNamespace(session_factory=session_factory)

    class StaleApplicationService:
        def __init__(self, database):
            assert database is db

        def append_event(self, user_id, application_id, event):
            raise ApplicationConflictError("private current revision: 99")

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    monkeypatch.setattr(cli, "_campaign_user", lambda _db, username: SimpleNamespace(id=29))
    monkeypatch.setattr(application_service, "ApplicationService", StaleApplicationService)
    monkeypatch.setattr(
        cli,
        "_campaign_application",
        lambda _db, **_kwargs: SimpleNamespace(
            application=SimpleNamespace(id="application-7", current_stage="saved", revision=99)
        ),
    )
    assert cli.main(_review_args("--acknowledge-review-record-write")) == 2
    diagnostics = capsys.readouterr().err
    assert json.loads(diagnostics)["error"] == "campaign_review_record_failed"
    assert "private" not in diagnostics

    def foreign_link(_db, **_kwargs):
        raise AutomationRuntimeError(
            "campaign_application_unavailable",
            "The campaign application is unavailable for the named account",
        )

    monkeypatch.setattr(cli, "_campaign_application", foreign_link)
    assert cli.main(_review_args("--acknowledge-review-record-write")) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "campaign_application_unavailable"


def test_authorize_requires_an_explicit_least_privilege_scope() -> None:
    parser = cli._parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["authorize", "--username", "operator", "--label", "Codex"])

    arguments = parser.parse_args(
        [
            "authorize",
            "--username",
            "operator",
            "--label",
            "Codex",
            "--scope",
            "system:read",
        ]
    )
    assert arguments.scope == ["system:read"]


def test_unknown_cli_account_still_uses_the_constant_work_password_path(
    db_session,
    monkeypatch,
) -> None:
    from backend.repositories.user_repository import UserRepository
    from backend.services import auth as auth_service

    verification_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        UserRepository,
        "get_by_username",
        lambda _repository, _username: None,
    )
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "candidate-secret")

    def verify(candidate: str, hashed_password: str) -> bool:
        verification_calls.append((candidate, hashed_password))
        return False

    monkeypatch.setattr(auth_service, "verify_password", verify)

    with pytest.raises(AutomationGrantError) as raised:
        cli._account(db_session, "missing-account")

    assert raised.value.code == "authentication_failed"
    assert verification_calls == [("candidate-secret", DUMMY_PASSWORD_HASH)]


def test_authorize_authenticates_account_and_binds_requested_scope(
    db_session, test_user, monkeypatch, capsys
) -> None:
    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate, write_access):
        assert migrate is True
        assert write_access is True
        yield SimpleNamespace(session_factory=session_factory)

    def session_factory():
        return db_session

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    arguments = argparse.Namespace(
        data_dir=None,
        username=test_user.username,
        label="Codex read access",
        days=7,
        scope=["system:read"],
        acknowledge_external_disclosure=False,
    )

    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "wrong-password")
    with pytest.raises(AutomationGrantError) as raised:
        cli._authorize(arguments)
    assert raised.value.code == "authentication_failed"
    assert db_session.query(AutomationGrant).count() == 0
    assert capsys.readouterr().out == ""

    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "Globalpass1")
    cli._authorize(arguments)
    payload = json.loads(capsys.readouterr().out)
    db_session.expire_all()
    grant = db_session.query(AutomationGrant).one()

    assert grant.user_id == test_user.id
    assert grant.scope_set() == {"system:read"}
    assert payload["grant"]["scopes"] == ["system:read"]
    assert payload["token"].startswith(TOKEN_PREFIX)


def test_authorize_workspace_scopes_requires_and_propagates_disclosure(
    db_session, test_user, monkeypatch, capsys
) -> None:
    @contextlib.contextmanager
    def test_runtime(_data_dir, *, migrate, write_access):
        assert migrate is True
        assert write_access is True
        yield SimpleNamespace(session_factory=lambda: db_session)

    monkeypatch.setattr(cli, "automation_runtime", test_runtime)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "Globalpass1")
    arguments = argparse.Namespace(
        data_dir=None,
        username=test_user.username,
        label="Claude workspace access",
        days=1,
        scope=["context:read", "proposals:write"],
        acknowledge_external_disclosure=False,
    )

    with pytest.raises(AutomationGrantError) as raised:
        cli._authorize(arguments)
    assert raised.value.code == "disclosure_required"
    assert db_session.query(AutomationGrant).count() == 0

    arguments.acknowledge_external_disclosure = True
    cli._authorize(arguments)
    payload = json.loads(capsys.readouterr().out)
    grant = db_session.query(AutomationGrant).one()
    assert grant.scope_set() == {"context:read", "proposals:write"}
    assert payload["grant"]["scopes"] == ["context:read", "proposals:write"]


def test_authorize_parser_exposes_explicit_external_disclosure_flag() -> None:
    arguments = cli._parser().parse_args(
        [
            "authorize",
            "--username",
            "owner",
            "--label",
            "Workspace access",
            "--scope",
            "context:read",
            "--acknowledge-external-disclosure",
        ]
    )
    assert arguments.acknowledge_external_disclosure is True


def test_doctor_reports_corrupt_schema_and_short_secret_without_false_readiness(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "careeros-data"
    vault = data_dir / "vault"
    vault.mkdir(parents=True)
    (vault / "careeros.db").write_bytes(b"not-a-sqlite-database")
    (vault / ".installation-secret").write_text("too-short", encoding="utf-8")

    report = runtime.doctor(data_dir)

    assert report["ready"] is False
    assert report["installation_secret_status"] == "invalid"
    assert report["schema_status"] == "unavailable"
    assert report["migration_required"] is None
    diagnostic_codes = report["diagnostic_codes"]
    assert isinstance(diagnostic_codes, list)
    assert set(diagnostic_codes) == {
        "installation_secret_invalid",
        "schema_unavailable",
    }


def test_automation_rejects_a_linked_installation_secret_before_environment_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "careeros-data"
    vault = data_dir / "vault"
    vault.mkdir(parents=True)
    (vault / "careeros.db").touch()
    external = tmp_path / "external-secret"
    external.write_text("s" * 64, encoding="ascii")
    secret = vault / ".installation-secret"
    try:
        secret.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"File symlinks are unavailable: {exc}")
    monkeypatch.delenv("CAREEROS_SECRET_FILE", raising=False)

    with pytest.raises(AutomationRuntimeError) as raised:
        runtime._configure_environment(data_dir)

    assert raised.value.code == "installation_secret_invalid"
    assert "CAREEROS_SECRET_FILE" not in os.environ
    assert external.read_text(encoding="ascii") == "s" * 64

    report = runtime.doctor(data_dir)
    assert report["installation_secret_exists"] is True
    assert report["installation_secret_status"] == "invalid"


def _subprocess_environment(data_dir: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "TESTING": "0",
            "DATA_DIR": str(data_dir),
            "DATABASE_URL": f"sqlite:///{(data_dir / 'vault' / 'careeros.db').as_posix()}",
            "SECRET_KEY": "automation-test-secret-key-at-least-32-bytes",
            "CAREEROS_SECRET_FILE": str(data_dir / "vault" / ".installation-secret"),
        }
    )
    environment.pop("CAREEROS_DESKTOP_MODE", None)
    return environment


def _create_real_vault(project_root: Path, data_dir: Path) -> str:
    (data_dir / "vault").mkdir(parents=True)
    (data_dir / "vault" / ".installation-secret").write_text(
        "automation-test-installation-secret-at-least-32-bytes",
        encoding="utf-8",
    )
    environment = _subprocess_environment(data_dir)
    migrated = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert migrated.returncode == 0, migrated.stderr
    seeded = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from backend.db.base import SessionLocal; "
                "from backend.models import User; "
                "from backend.automation.grants import issue_grant; "
                "db=SessionLocal(); "
                "user=User(username='mcp-smoke', hashed_password='not-used'); "
                "db.add(user); db.commit(); db.refresh(user); "
                "view,token=issue_grant(db,user_id=user.id,label='Protocol smoke',"
                "scopes=('system:read','applications:read')); "
                "print(token); db.close()"
            ),
        ],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert seeded.returncode == 0, seeded.stderr
    return seeded.stdout.strip()


def test_runtime_fails_closed_when_settings_were_preloaded(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    data_dir = tmp_path / "careeros-data"
    vault = data_dir / "vault"
    vault.mkdir(parents=True)
    (vault / "careeros.db").touch()
    (vault / ".installation-secret").write_text(
        "preload-test-installation-secret-at-least-32-bytes",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import backend.core.config; "
                "from pathlib import Path; "
                "from backend.automation.runtime import "
                "_configure_environment, AutomationRuntimeError; "
                "\ntry: _configure_environment(Path(sys.argv[1]))"
                "\nexcept AutomationRuntimeError as exc: print(exc.code)"
            ),
            str(data_dir),
        ],
        cwd=project_root,
        env=_subprocess_environment(data_dir),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "runtime_already_initialized"
    assert str(data_dir) not in completed.stderr


def test_runtime_read_session_is_enforced_by_sqlite(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    data_dir = tmp_path / "careeros-data"
    _create_real_vault(project_root, data_dir)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json,sys; "
                "from pathlib import Path; "
                "from sqlalchemy import text; "
                "from sqlalchemy.exc import OperationalError; "
                "from backend.automation.runtime import automation_runtime; "
                "blocked=False; "
                "\nwith automation_runtime(Path(sys.argv[1])) as runtime:"
                "\n with runtime.session_factory() as db:"
                "\n  query_only=int(db.execute(text('PRAGMA query_only')).scalar_one())"
                "\n  try:"
                "\n   db.execute(text(\"UPDATE users SET username='write-should-fail' "
                "WHERE username='mcp-smoke'\")); db.commit()"
                "\n  except OperationalError:"
                "\n   db.rollback(); blocked=True"
                "\nprint(json.dumps({'query_only':query_only,'write_blocked':blocked}))"
                "\nraise SystemExit(0 if blocked else 3)"
            ),
            str(data_dir),
        ],
        cwd=project_root,
        env=_subprocess_environment(data_dir),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert probe.returncode == 0, probe.stderr
    assert json.loads(probe.stdout) == {
        "query_only": 1,
        "write_blocked": True,
    }
    with sqlite3.connect(data_dir / "vault" / "careeros.db") as database:
        assert database.execute(
            "SELECT username FROM users WHERE username = 'mcp-smoke'"
        ).fetchone() == ("mcp-smoke",)


def test_revision_inspection_is_enforced_by_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(__file__).resolve().parents[3]
    data_dir = tmp_path / "careeros-data"
    _create_real_vault(project_root, data_dir)
    database_path = data_dir / "vault" / "careeros.db"

    import sqlalchemy
    from sqlalchemy import event

    from desktop.backend_main import database_revision_state

    real_create_engine = sqlalchemy.create_engine
    observed_connections: list[dict[str, int | bool]] = []

    def create_checked_engine(*args, **kwargs):
        engine = real_create_engine(*args, **kwargs)

        @event.listens_for(engine, "connect")
        def verify_read_only_revision_connection(dbapi_connection, _connection_record) -> None:
            query_only = int(dbapi_connection.execute("PRAGMA query_only").fetchone()[0])
            write_blocked = False
            try:
                dbapi_connection.execute(
                    "UPDATE users SET username='revision-write-should-fail' "
                    "WHERE username='mcp-smoke'"
                )
                dbapi_connection.commit()
            except sqlite3.OperationalError:
                dbapi_connection.rollback()
                write_blocked = True
            observed_connections.append({"query_only": query_only, "write_blocked": write_blocked})
            if query_only != 1 or not write_blocked:
                raise AssertionError("revision inspection received a write-capable connection")

        return engine

    monkeypatch.setattr(sqlalchemy, "create_engine", create_checked_engine)
    current, expected = database_revision_state(database_path, read_only=True)

    assert current == expected
    assert observed_connections == [{"query_only": 1, "write_blocked": True}]


@pytest.mark.parametrize("bootstrap_environment", ["absent", "conflicting"])
@pytest.mark.parametrize(
    ("grant_transition", "expected_code"),
    [("revoke", "revoked_grant"), ("expire", "expired_grant")],
)
@pytest.mark.asyncio
async def test_real_stdio_subprocess_has_clean_protocol_and_redacted_stderr(
    tmp_path: Path,
    bootstrap_environment: str,
    grant_transition: str,
    expected_code: str,
) -> None:
    project_root = Path(__file__).resolve().parents[3]
    data_dir = tmp_path / "careeros-data"
    token = _create_real_vault(project_root, data_dir)
    environment = os.environ.copy()
    for name in (
        "CAREEROS_DESKTOP_MODE",
        "CAREEROS_DESKTOP_DATA_DIR",
        "CAREEROS_SECRET_FILE",
        "DATABASE_URL",
        "DATA_DIR",
        "SECRET_KEY",
        "ENVIRONMENT",
    ):
        environment.pop(name, None)
    environment["TESTING"] = "0"
    environment["CAREEROS_MCP_TOKEN"] = token
    if bootstrap_environment == "conflicting":
        wrong_data_dir = tmp_path / "wrong-careeros-data"
        environment.update(
            {
                "CAREEROS_DESKTOP_DATA_DIR": str(wrong_data_dir),
                "CAREEROS_SECRET_FILE": str(wrong_data_dir / "vault" / ".installation-secret"),
                "DATABASE_URL": f"sqlite:///{(wrong_data_dir / 'vault' / 'careeros.db').as_posix()}",
                "DATA_DIR": str(wrong_data_dir),
                "SECRET_KEY": "conflicting-secret-that-must-never-select-the-vault",
            }
        )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "backend.automation.mcp_server",
            "--data-dir",
            str(data_dir),
            "--acknowledge-agent-disclosure",
        ],
        cwd=project_root,
        env=environment,
    )
    stderr_path = tmp_path / "mcp-stderr.log"
    with stderr_path.open("w+", encoding="utf-8") as errlog:
        async with stdio_client(parameters, errlog=errlog) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools = await session.list_tools()
                status = await session.call_tool("get_status", {})
                with sqlite3.connect(data_dir / "vault" / "careeros.db") as database:
                    if grant_transition == "revoke":
                        database.execute(
                            "UPDATE automation_grants SET revoked_at = ? WHERE revoked_at IS NULL",
                            (datetime.now(UTC).isoformat(),),
                        )
                    else:
                        database.execute(
                            "UPDATE automation_grants SET expires_at = ?",
                            (datetime(2000, 1, 1, tzinfo=UTC).isoformat(),),
                        )
                denied = await session.call_tool("get_status", {})
        errlog.seek(0)
        diagnostics = errlog.read()

    assert {tool.name for tool in tools.tools} == {
        "get_status",
        "get_local_model_status",
        "list_applications",
        "get_application_readiness",
        "get_application_agenda",
    }
    assert status.isError is False
    assert status.structuredContent is not None
    assert status.structuredContent["access_mode"] == "read_only"
    assert denied.isError is True
    assert expected_code in str(denied.content)
    assert "read-only stdio session started" in diagnostics
    assert token not in diagnostics
    assert str(data_dir) not in diagnostics
    assert "installation-secret" not in diagnostics
