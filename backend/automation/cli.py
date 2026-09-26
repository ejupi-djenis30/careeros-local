"""Human and agent-friendly command line for the CareerOS automation boundary."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
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
    # JSON escapes preserve Unicode values after decoding while keeping the wire
    # output writable on Windows terminals configured for a legacy code page.
    serialized = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)
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
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
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


def _campaign_archive(path_value: str) -> tuple[Path, bytes]:
    """Read one bounded regular ZIP without exposing its path in diagnostics."""
    from backend.campaigns.archive_policy import MAX_COMPRESSED_BYTES

    path = Path(path_value).expanduser()
    try:
        if path.is_symlink():
            raise OSError
        resolved = path.resolve(strict=True)
        if not resolved.is_file() or resolved.suffix.lower() != ".zip":
            raise OSError
        if resolved.stat().st_size > MAX_COMPRESSED_BYTES:
            raise OSError
        archive_bytes = resolved.read_bytes()
        if len(archive_bytes) > MAX_COMPRESSED_BYTES:
            raise OSError
        return resolved, archive_bytes
    except (OSError, RuntimeError) as exc:
        raise AutomationRuntimeError(
            "campaign_archive_unavailable",
            "Campaign archive is unavailable or violates the local input boundary",
        ) from exc


def _campaign_user(db: Any, username: str) -> Any:
    """Resolve the explicitly named owner for an offline local-vault operation."""
    from backend.repositories.user_repository import UserRepository

    clean_username = username.strip()
    user = UserRepository(db).get_by_username(clean_username) if clean_username else None
    if user is None:
        raise AutomationRuntimeError(
            "campaign_account_unavailable",
            "The explicitly named CareerOS account is unavailable",
        )
    return user


def _campaign_preview(arguments: argparse.Namespace) -> None:
    from backend.campaigns.archive_policy import ArchivePolicyError
    from backend.campaigns.preview import build_campaign_preview

    archive_path, archive_bytes = _campaign_archive(arguments.archive)
    try:
        preview = build_campaign_preview(
            archive_bytes,
            archive_name=archive_path.name,
            user_has_profile=not arguments.requires_profile_name,
        )
    except ArchivePolicyError as exc:
        raise AutomationRuntimeError(
            "campaign_archive_invalid", "Campaign archive validation failed"
        ) from exc
    except Exception as exc:
        raise AutomationRuntimeError(
            "campaign_preview_failed", "Campaign archive could not be previewed"
        ) from exc
    _emit(preview)


def _load_campaign_persistence_models() -> tuple[type[Any], ...]:
    """Register FK targets needed by the isolated offline campaign writer."""
    from backend.resumes.models import ResumeDraft, ResumeVersion

    return (ResumeDraft, ResumeVersion)


def _campaign_import(arguments: argparse.Namespace) -> None:
    if not arguments.acknowledge_local_vault_write:
        raise AutomationRuntimeError(
            "campaign_write_acknowledgement_required",
            "Campaign import requires --acknowledge-local-vault-write",
        )
    _archive_path, archive_bytes = _campaign_archive(arguments.archive)
    with automation_runtime(arguments.data_dir, migrate=True, write_access=True) as runtime:
        _load_campaign_persistence_models()
        from backend.campaigns.service import import_campaign
        from backend.campaigns.service_helpers import CampaignImportError

        with runtime.session_factory() as db:
            user = _campaign_user(db, arguments.username)
            try:
                result = import_campaign(
                    db,
                    user_id=user.id,
                    archive_bytes=archive_bytes,
                    expected_fingerprint=arguments.expected_fingerprint,
                    imported_at=datetime.now(UTC),
                    campaign_name=arguments.name,
                    profile_display_name=arguments.profile_display_name,
                )
            except CampaignImportError as exc:
                raise AutomationRuntimeError("campaign_import_failed", str(exc)) from exc
    _emit(result)


def _campaign_read(arguments: argparse.Namespace) -> None:
    with automation_runtime(arguments.data_dir, migrate=False) as runtime:
        from backend.campaigns.api_service import (
            CampaignApiNotFound,
            campaign_detail,
            list_campaigns,
        )

        with runtime.session_factory() as db:
            user = _campaign_user(db, arguments.username)
            result: list[dict[str, Any]] | dict[str, Any]
            if arguments.campaign_command == "list":
                result = list_campaigns(db, user.id)
            else:
                try:
                    result = campaign_detail(
                        db,
                        user.id,
                        arguments.campaign_id,
                        query=arguments.query,
                        stage=arguments.stage,
                        priority=arguments.priority,
                        limit=arguments.limit,
                        offset=arguments.offset,
                        review_decision=arguments.review_decision,
                    )
                except CampaignApiNotFound as exc:
                    raise AutomationRuntimeError(
                        "campaign_not_found", "Campaign is unavailable for the named account"
                    ) from exc
    _emit(result)


def _campaign_application(
    db: Any,
    *,
    user_id: int,
    campaign_id: str,
    source_application_id: str,
) -> Any:
    """Resolve one owner-scoped imported application by its stable campaign ID."""
    from backend.applications.models import Application
    from backend.campaigns.models import Campaign, CampaignApplication

    link = (
        db.query(CampaignApplication)
        .join(Campaign, Campaign.id == CampaignApplication.campaign_id)
        .join(Application, Application.id == CampaignApplication.application_id)
        .filter(
            Campaign.id == campaign_id,
            Campaign.user_id == user_id,
            CampaignApplication.source_application_id == source_application_id,
            Application.user_id == user_id,
        )
        .first()
    )
    if link is None:
        raise AutomationRuntimeError(
            "campaign_application_unavailable",
            "The campaign application is unavailable for the named account",
        )
    return link


def _campaign_record_submission(arguments: argparse.Namespace) -> None:
    """Record an already-confirmed external submission; never submit it."""
    if not arguments.acknowledge_submission_record_write:
        raise AutomationRuntimeError(
            "campaign_submission_acknowledgement_required",
            "Recording a submission requires --acknowledge-submission-record-write",
        )

    channel = arguments.channel.strip()
    confirmation = arguments.confirmation.strip()
    digests = [arguments.resume_sha256, arguments.cover_letter_sha256]
    if not channel or len(channel) > 120 or not confirmation or len(confirmation) > 1_000:
        raise AutomationRuntimeError(
            "campaign_submission_evidence_invalid",
            "Submission evidence is missing or exceeds the local boundary",
        )
    if any(value is not None and re.fullmatch(r"[a-f0-9]{64}", value) is None for value in digests):
        raise AutomationRuntimeError(
            "campaign_submission_evidence_invalid",
            "Submission evidence is missing or exceeds the local boundary",
        )

    with automation_runtime(arguments.data_dir, migrate=False, write_access=True) as runtime:
        from backend.applications.exceptions import (
            ApplicationConflictError,
            ApplicationValidationError,
        )
        from backend.applications.schemas import ApplicationEventCreate
        from backend.applications.service import ApplicationService

        with runtime.session_factory() as db:
            user = _campaign_user(db, arguments.username)
            link = _campaign_application(
                db,
                user_id=user.id,
                campaign_id=arguments.campaign_id,
                source_application_id=arguments.source_application_id,
            )
            application = link.application
            if application.current_stage == "applied":
                result = {
                    "application_id": application.id,
                    "campaign_id": arguments.campaign_id,
                    "created": False,
                    "revision": application.revision,
                    "source_application_id": arguments.source_application_id,
                    "stage": application.current_stage,
                }
            else:
                payload = {
                    "external_confirmation": confirmation,
                    "resume_sha256": arguments.resume_sha256,
                    "submission_channel": channel,
                }
                if arguments.cover_letter_sha256 is not None:
                    payload["cover_letter_sha256"] = arguments.cover_letter_sha256
                occurred_at = datetime.now(UTC)
                try:
                    updated = ApplicationService(db).append_event(
                        user.id,
                        application.id,
                        ApplicationEventCreate(
                            expected_revision=arguments.expected_revision,
                            event_type="stage",
                            stage="applied",
                            occurred_at=occurred_at,
                            note=f"Submitted through {channel}. Confirmation: {confirmation}",
                            payload=payload,
                        ),
                    )
                except (ApplicationConflictError, ApplicationValidationError) as exc:
                    raise AutomationRuntimeError(
                        "campaign_submission_record_failed",
                        "CareerOS could not record the confirmed submission",
                    ) from exc
                result = {
                    "application_id": updated.id,
                    "campaign_id": arguments.campaign_id,
                    "created": True,
                    "occurred_at": occurred_at.isoformat(),
                    "revision": updated.revision,
                    "source_application_id": arguments.source_application_id,
                    "stage": updated.current_stage,
                }
    _emit(result)


def _campaign_record_outcome(arguments: argparse.Namespace) -> None:
    """Record a sourced rejection after an external application, without contacting anyone."""
    if not arguments.acknowledge_outcome_record_write:
        raise AutomationRuntimeError(
            "campaign_outcome_acknowledgement_required",
            "Recording an outcome requires --acknowledge-outcome-record-write",
        )
    evidence = arguments.evidence.strip()
    try:
        source_date = date.fromisoformat(arguments.source_date)
    except ValueError as exc:
        raise AutomationRuntimeError(
            "campaign_outcome_evidence_invalid",
            "Outcome evidence is missing or exceeds the local boundary",
        ) from exc
    if (
        arguments.expected_revision < 1
        or not 20 <= len(evidence) <= 1_000
        or any(ord(character) < 32 or ord(character) == 127 for character in evidence)
        or source_date > datetime.now(UTC).date() + timedelta(days=1)
    ):
        raise AutomationRuntimeError(
            "campaign_outcome_evidence_invalid",
            "Outcome evidence is missing or exceeds the local boundary",
        )

    with automation_runtime(arguments.data_dir, migrate=False, write_access=True) as runtime:
        from backend.applications.exceptions import (
            ApplicationConflictError,
            ApplicationValidationError,
        )
        from backend.applications.schemas import ApplicationEventCreate
        from backend.applications.service import ApplicationService

        with runtime.session_factory() as db:
            user = _campaign_user(db, arguments.username)
            link = _campaign_application(
                db,
                user_id=user.id,
                campaign_id=arguments.campaign_id,
                source_application_id=arguments.source_application_id,
            )
            application = link.application
            if application.current_stage == "rejected":
                result = {
                    "application_id": application.id,
                    "campaign_id": arguments.campaign_id,
                    "created": False,
                    "revision": application.revision,
                    "source_application_id": arguments.source_application_id,
                    "stage": application.current_stage,
                }
            else:
                if application.current_stage not in {"applied", "screening", "interview", "offer"}:
                    raise AutomationRuntimeError(
                        "campaign_outcome_not_post_submission",
                        "Only submitted applications can receive a rejection outcome",
                    )
                recorded_at = datetime.now(UTC)
                try:
                    updated = ApplicationService(db).append_event(
                        user.id,
                        application.id,
                        ApplicationEventCreate(
                            expected_revision=arguments.expected_revision,
                            event_type="stage",
                            stage="rejected",
                            occurred_at=recorded_at,
                            note=evidence,
                            payload={
                                "campaign_outcome_v1": {
                                    "outcome": "rejected",
                                    "source_kind": arguments.source_kind,
                                    "source_date": source_date.isoformat(),
                                }
                            },
                        ),
                    )
                except (ApplicationConflictError, ApplicationValidationError) as exc:
                    raise AutomationRuntimeError(
                        "campaign_outcome_record_failed",
                        "CareerOS could not record the verified outcome",
                    ) from exc
                result = {
                    "application_id": updated.id,
                    "campaign_id": arguments.campaign_id,
                    "created": True,
                    "recorded_at": recorded_at.isoformat(),
                    "revision": updated.revision,
                    "source_application_id": arguments.source_application_id,
                    "stage": updated.current_stage,
                }
    _emit(result)


def _campaign_record_review(arguments: argparse.Namespace) -> None:
    """Record a sourced pre-submission decision without changing application stage."""
    if not arguments.acknowledge_review_record_write:
        raise AutomationRuntimeError(
            "campaign_review_acknowledgement_required",
            "Recording a review requires --acknowledge-review-record-write",
        )

    from backend.jobs.urls import normalize_job_url

    reason = arguments.reason.strip()
    next_action = (arguments.next_action or "").strip()
    if (
        arguments.expected_revision < 1
        or not 8 <= len(reason) <= 1_000
        or any(ord(character) < 32 or ord(character) == 127 for character in reason)
        or (arguments.decision == "hold" and not 5 <= len(next_action) <= 500)
        or (arguments.decision != "hold" and next_action)
        or any(ord(character) < 32 or ord(character) == 127 for character in next_action)
    ):
        raise AutomationRuntimeError(
            "campaign_review_evidence_invalid",
            "Review evidence is missing or exceeds the local boundary",
        )
    try:
        source_url = normalize_job_url(arguments.source_url, required=True)
    except ValueError as exc:
        raise AutomationRuntimeError(
            "campaign_review_evidence_invalid",
            "Review evidence is missing or exceeds the local boundary",
        ) from exc

    with automation_runtime(arguments.data_dir, migrate=False, write_access=True) as runtime:
        from backend.applications.exceptions import (
            ApplicationConflictError,
            ApplicationValidationError,
        )
        from backend.applications.schemas import ApplicationEventCreate
        from backend.applications.service import ApplicationService

        with runtime.session_factory() as db:
            user = _campaign_user(db, arguments.username)
            link = _campaign_application(
                db,
                user_id=user.id,
                campaign_id=arguments.campaign_id,
                source_application_id=arguments.source_application_id,
            )
            application = link.application
            if application.current_stage not in {"saved", "preparing"}:
                raise AutomationRuntimeError(
                    "campaign_review_not_pre_submission",
                    "Only saved or preparing applications can receive a campaign review",
                )
            occurred_at = datetime.now(UTC)
            try:
                updated = ApplicationService(db).append_event(
                    user.id,
                    application.id,
                    ApplicationEventCreate(
                        expected_revision=arguments.expected_revision,
                        event_type="note",
                        occurred_at=occurred_at,
                        note=reason,
                        payload={
                            "campaign_review_v1": {
                                "decision": arguments.decision,
                                "source_url": source_url,
                                "next_action": next_action or None,
                            }
                        },
                    ),
                )
            except (ApplicationConflictError, ApplicationValidationError) as exc:
                raise AutomationRuntimeError(
                    "campaign_review_record_failed",
                    "CareerOS could not record the review decision",
                ) from exc
    _emit(
        {
            "application_id": updated.id,
            "campaign_id": arguments.campaign_id,
            "decision": arguments.decision,
            "reviewed_at": occurred_at.isoformat(),
            "revision": updated.revision,
            "source_application_id": arguments.source_application_id,
            "stage": updated.current_stage,
        }
    )


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
                acknowledged_disclosure=arguments.acknowledge_external_disclosure,
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
        desktop_url=arguments.desktop_url,
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
    authorize.add_argument(
        "--acknowledge-external-disclosure",
        action="store_true",
        help="Acknowledge disclosure to the separately configured agent for extended scopes",
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

    campaign = subparsers.add_parser(
        "campaign", help="Preview, import, and inspect a local campaign workspace"
    )
    campaign_commands = campaign.add_subparsers(dest="campaign_command", required=True)
    preview = campaign_commands.add_parser("preview", help="Preview a campaign ZIP without writes")
    preview.add_argument("archive")
    preview.add_argument(
        "--requires-profile-name",
        action="store_true",
        help="Report that the destination account has no candidate profile",
    )
    import_command = campaign_commands.add_parser(
        "import", help="Import a fingerprint-confirmed campaign into a closed local vault"
    )
    import_command.add_argument("archive")
    import_command.add_argument("--username", required=True)
    import_command.add_argument("--expected-fingerprint", required=True)
    import_command.add_argument("--name")
    import_command.add_argument("--profile-display-name")
    import_command.add_argument("--acknowledge-local-vault-write", action="store_true")
    campaign_list = campaign_commands.add_parser(
        "list", help="List campaigns owned by an explicitly named local account"
    )
    campaign_list.add_argument("--username", required=True)
    campaign_show = campaign_commands.add_parser(
        "show", help="Show owner-scoped campaign applications"
    )
    campaign_show.add_argument("campaign_id")
    campaign_show.add_argument("--username", required=True)
    campaign_show.add_argument("--query")
    campaign_show.add_argument("--stage")
    campaign_show.add_argument("--priority")
    campaign_show.add_argument(
        "--review-decision", choices=("none", "hold", "excluded", "cleared")
    )
    campaign_show.add_argument("--offset", type=int, default=0)
    campaign_show.add_argument("--limit", type=int, default=50)
    record_submission = campaign_commands.add_parser(
        "record-submission",
        help="Record a portal-confirmed submission without contacting the employer",
    )
    record_submission.add_argument("campaign_id")
    record_submission.add_argument("source_application_id")
    record_submission.add_argument("--username", required=True)
    record_submission.add_argument("--expected-revision", type=int, required=True)
    record_submission.add_argument("--channel", required=True)
    record_submission.add_argument("--confirmation", required=True)
    record_submission.add_argument("--resume-sha256", required=True)
    record_submission.add_argument("--cover-letter-sha256")
    record_submission.add_argument("--acknowledge-submission-record-write", action="store_true")
    record_outcome = campaign_commands.add_parser(
        "record-outcome",
        help="Record a source-verified rejection after submission without contacting the employer",
    )
    record_outcome.add_argument("campaign_id")
    record_outcome.add_argument("source_application_id")
    record_outcome.add_argument("--username", required=True)
    record_outcome.add_argument("--expected-revision", type=int, required=True)
    record_outcome.add_argument("--source-kind", choices=("email", "portal"), required=True)
    record_outcome.add_argument("--source-date", required=True)
    record_outcome.add_argument("--evidence", required=True)
    record_outcome.add_argument("--acknowledge-outcome-record-write", action="store_true")
    record_review = campaign_commands.add_parser(
        "record-review",
        help="Record a sourced hold/exclusion/clear decision without submitting",
    )
    record_review.add_argument("campaign_id")
    record_review.add_argument("source_application_id")
    record_review.add_argument("--username", required=True)
    record_review.add_argument("--expected-revision", type=int, required=True)
    record_review.add_argument("--decision", choices=("hold", "excluded", "cleared"), required=True)
    record_review.add_argument("--reason", required=True)
    record_review.add_argument("--source-url", required=True)
    record_review.add_argument("--next-action")
    record_review.add_argument("--acknowledge-review-record-write", action="store_true")

    mcp = subparsers.add_parser("mcp", help="Serve MCP or print client configuration")
    mcp_commands = mcp.add_subparsers(dest="mcp_command", required=True)
    serve = mcp_commands.add_parser("serve")
    serve.add_argument(
        "--desktop-url",
        help="Canonical loopback /api/v1 base for an open development desktop",
    )
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
        elif arguments.command == "campaign" and arguments.campaign_command == "preview":
            _campaign_preview(arguments)
        elif arguments.command == "campaign" and arguments.campaign_command == "import":
            _campaign_import(arguments)
        elif arguments.command == "campaign" and arguments.campaign_command == "record-submission":
            _campaign_record_submission(arguments)
        elif arguments.command == "campaign" and arguments.campaign_command == "record-outcome":
            _campaign_record_outcome(arguments)
        elif arguments.command == "campaign" and arguments.campaign_command == "record-review":
            _campaign_record_review(arguments)
        elif arguments.command == "campaign":
            _campaign_read(arguments)
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
