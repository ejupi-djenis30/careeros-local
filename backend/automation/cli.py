"""Human and agent-friendly command line for the CareerOS automation boundary."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from datetime import timedelta
from typing import Any

from backend.automation.grants import (
    TOKEN_ENVIRONMENT_VARIABLE,
    AutomationGrantError,
    authenticate_grant,
    issue_grant,
    list_grants,
    revoke_grant,
)
from backend.automation.runtime import (
    AutomationRuntimeError,
    automation_runtime,
    doctor,
    resolve_data_dir,
)
from backend.automation.schemas import ALL_AUTOMATION_SCOPES


def _emit(value: Any, *, stream: Any | None = None) -> None:
    """Write a reviewed command result to the caller's terminal as JSON."""
    destination = stream or sys.stdout
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif isinstance(value, list) and value and hasattr(value[0], "model_dump"):
        value = [item.model_dump(mode="json") for item in value]
    # This is the CLI's structured response channel, not application logging. All
    # call sites return public or already-redacted data; bearer issuance has a
    # separate one-time output path in _emit_authorized_grant.
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    destination.write(serialized + "\n")  # lgtm[py/clear-text-logging-sensitive-data]
    destination.flush()


def _emit_authorized_grant(grant: Any, token: str) -> None:
    """Return a newly minted bearer once to the authorizing terminal."""
    payload = {
        "grant": grant.model_dump(mode="json"),
        "token": token,
        "token_environment_variable": TOKEN_ENVIRONMENT_VARIABLE,
        "warning": "This token is shown once. Store it in your OS credential manager and never commit it.",
    }
    # This is the explicit authorization response, not a log entry. The token is
    # never persisted in clear text and every other diagnostic path stays redacted.
    # codeql[py/clear-text-logging-sensitive-data]
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    sys.stdout.flush()


def _account(db: Any, username: str) -> Any:
    from backend.repositories.user_repository import UserRepository
    from backend.services.auth import DUMMY_PASSWORD_HASH, verify_password

    user = UserRepository(db).get_by_username(username.strip())
    password = getpass.getpass("CareerOS password: ")
    # Keep unknown and known accounts on the same bcrypt path. The CLI is local,
    # but scripts and shared terminals must not gain a username timing oracle.
    candidate_hash = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, candidate_hash)
    if user is None or not password_ok:
        raise AutomationGrantError(
            "authentication_failed", "CareerOS account authentication failed"
        )
    return user


def _bearer() -> str:
    token = os.environ.get(TOKEN_ENVIRONMENT_VARIABLE, "").strip()
    if not token:
        raise AutomationGrantError(
            "grant_required", f"Set {TOKEN_ENVIRONMENT_VARIABLE} to an active automation grant"
        )
    return token


def _facade(runtime: Any) -> Any:
    from backend.automation.facade import AutomationFacade

    with runtime.session_factory() as db:
        principal = authenticate_grant(db, _bearer())
    return AutomationFacade(runtime.session_factory, principal)


def _authorize(arguments: argparse.Namespace) -> None:
    scopes = arguments.scope
    with automation_runtime(arguments.data_dir, migrate=True, write_access=True) as runtime:
        with runtime.session_factory() as db:
            user = _account(db, arguments.username)
            grant, token = issue_grant(
                db,
                user_id=user.id,
                label=arguments.label,
                scopes=scopes,
                lifetime=timedelta(days=arguments.days),
            )
    _emit_authorized_grant(grant, token)


def _list_grants(arguments: argparse.Namespace) -> None:
    with automation_runtime(arguments.data_dir, migrate=False) as runtime:
        with runtime.session_factory() as db:
            user = _account(db, arguments.username)
            grants = list_grants(db, user_id=user.id)
    _emit(grants)


def _revoke_grant(arguments: argparse.Namespace) -> None:
    with automation_runtime(arguments.data_dir, migrate=False, write_access=True) as runtime:
        with runtime.session_factory() as db:
            user = _account(db, arguments.username)
            grant = revoke_grant(db, user_id=user.id, grant_id=arguments.grant_id)
    _emit(grant)


def _read(arguments: argparse.Namespace) -> None:
    with automation_runtime(arguments.data_dir, migrate=False) as runtime:
        facade = _facade(runtime)
        if arguments.command == "status":
            result = facade.system_status()
        elif arguments.command == "model-status":
            result = asyncio.run(facade.local_model_status())
        elif arguments.command == "career-summary":
            result = facade.career_summary()
        elif arguments.command == "resumes":
            result = facade.resume_catalog()
        elif arguments.command == "applications":
            result = facade.list_applications(offset=arguments.offset, limit=arguments.limit)
        elif arguments.command == "readiness":
            result = facade.application_readiness(arguments.application_id)
        elif arguments.command == "agenda":
            result = facade.application_agenda(
                horizon_days=arguments.days,
                limit=arguments.limit,
                timezone_offset_minutes=arguments.timezone_offset_minutes,
            )
        else:  # pragma: no cover - argparse owns the command set.
            raise AutomationRuntimeError("unknown_command", "Unknown automation command")
    _emit(result)


def _client_config(arguments: argparse.Namespace) -> None:
    data_dir = str(resolve_data_dir(arguments.data_dir))
    args = [
        "--data-dir",
        data_dir,
        "mcp",
        "serve",
        "--acknowledge-agent-disclosure",
    ]
    if arguments.client == "codex":
        encoded_args = ", ".join(json.dumps(item) for item in args)
        sys.stdout.write(
            "[mcp_servers.careeros]\n"
            'command = "careeros"\n'
            f"args = [{encoded_args}]\n"
            f'env_vars = ["{TOKEN_ENVIRONMENT_VARIABLE}"]\n'
        )
        return
    _emit(
        {
            "mcpServers": {
                "careeros": {
                    "type": "stdio",
                    "command": "careeros",
                    "args": args,
                    "env": {TOKEN_ENVIRONMENT_VARIABLE: f"${{{TOKEN_ENVIRONMENT_VARIABLE}}}"},
                }
            }
        }
    )


def _serve(arguments: argparse.Namespace) -> None:
    from backend.automation.mcp_server import run_server

    run_server(
        data_dir=arguments.data_dir,
        acknowledge_agent_disclosure=arguments.acknowledge_agent_disclosure,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="careeros",
        description="Scoped local automation for CareerOS Local",
    )
    parser.add_argument(
        "--data-dir",
        help="Absolute CareerOS app-data directory; defaults to the native app location",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Inspect the local automation prerequisites")

    authorize = subparsers.add_parser("authorize", help="Create a revocable read grant")
    authorize.add_argument("--username", required=True)
    authorize.add_argument("--label", required=True)
    authorize.add_argument("--days", type=int, default=30, choices=range(1, 366), metavar="1..365")
    authorize.add_argument(
        "--scope",
        action="append",
        choices=ALL_AUTOMATION_SCOPES,
        required=True,
        help="Repeat to add each read scope the agent is allowed to use",
    )

    grants = subparsers.add_parser("grants", help="List or revoke automation grants")
    grant_commands = grants.add_subparsers(dest="grant_command", required=True)
    list_command = grant_commands.add_parser("list")
    list_command.add_argument("--username", required=True)
    revoke_command = grant_commands.add_parser("revoke")
    revoke_command.add_argument("--username", required=True)
    revoke_command.add_argument("grant_id")

    subparsers.add_parser("status", help="Show scoped product and schema status")
    subparsers.add_parser("model-status", help="Show required local-model readiness")
    subparsers.add_parser("career-summary", help="Show bounded Career Vault completeness")
    subparsers.add_parser("resumes", help="List resume drafts and published versions")

    applications = subparsers.add_parser("applications", help="List application summaries")
    applications.add_argument("--offset", type=int, default=0)
    applications.add_argument("--limit", type=int, default=25)

    readiness = subparsers.add_parser("readiness", help="Inspect one application preflight")
    readiness.add_argument("application_id")

    agenda = subparsers.add_parser("agenda", help="Show prioritized application follow-ups")
    agenda.add_argument("--days", type=int, default=7)
    agenda.add_argument("--limit", type=int, default=25)
    agenda.add_argument("--timezone-offset-minutes", type=int, default=0)

    mcp = subparsers.add_parser("mcp", help="Serve MCP or print client configuration")
    mcp_commands = mcp.add_subparsers(dest="mcp_command", required=True)
    serve = mcp_commands.add_parser("serve")
    serve.add_argument("--acknowledge-agent-disclosure", action="store_true")
    config = mcp_commands.add_parser("config")
    config.add_argument("--client", choices=("codex", "claude-code"), required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "doctor":
            _emit(doctor(arguments.data_dir))
        elif arguments.command == "authorize":
            _authorize(arguments)
        elif arguments.command == "grants" and arguments.grant_command == "list":
            _list_grants(arguments)
        elif arguments.command == "grants" and arguments.grant_command == "revoke":
            _revoke_grant(arguments)
        elif arguments.command == "mcp" and arguments.mcp_command == "serve":
            _serve(arguments)
        elif arguments.command == "mcp" and arguments.mcp_command == "config":
            _client_config(arguments)
        else:
            _read(arguments)
    except (AutomationRuntimeError, AutomationGrantError) as exc:
        _emit({"error": exc.code, "message": str(exc)}, stream=sys.stderr)
        return 2
    except Exception:
        _emit(
            {"error": "internal_error", "message": "CareerOS could not complete the command"},
            stream=sys.stderr,
        )
        return 1
    return 0
