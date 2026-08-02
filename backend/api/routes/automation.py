"""Authenticated desktop management for scoped external-agent grants."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id
from backend.automation.grants import (
    AutomationGrantError,
    issue_grant,
    list_grants,
    revoke_grant,
)
from backend.automation.reauth import AccountReauthenticationGuard
from backend.automation.schemas import (
    AutomationErrorResponse,
    GrantIssuedView,
    GrantIssueRequest,
    GrantRevokeRequest,
    GrantView,
    PrivateErrorResponse,
)
from backend.db.base import get_db
from backend.repositories.user_repository import UserRepository
from backend.services.auth import DUMMY_PASSWORD_HASH, verify_password

desktop_session_header = APIKeyHeader(
    name="X-CareerOS-Session",
    scheme_name="desktopSession",
    description=(
        "Per-launch native-shell secret. The middleware enforces it in desktop mode; "
        "explicit browser development disables that boundary."
    ),
    auto_error=False,
)
router = APIRouter(dependencies=[Security(desktop_session_header)])
reauthentication_guard = AccountReauthenticationGuard()
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}
GrantId = Annotated[
    str,
    Path(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    ),
]
PRIVATE_RESPONSE_HEADERS = {
    "Cache-Control": {
        "description": "Prevents storage of account access and error responses.",
        "schema": {"type": "string", "example": "no-store, max-age=0"},
    },
    "Pragma": {
        "description": "Compatibility directive for legacy HTTP caches.",
        "schema": {"type": "string", "example": "no-cache"},
    },
}
AUTOMATION_SECURITY: list[dict[str, list[str]]] = [
    {
        "desktopSession": [],
        "OAuth2PasswordBearer": [],
    }
]


def _mark_private(response: Response) -> None:
    for name, value in NO_STORE_HEADERS.items():
        response.headers[name] = value


def _require_current_password(
    db: Session,
    *,
    user_id: int,
    password: str,
) -> None:
    with reauthentication_guard.serialize_verification(user_id):
        _verify_current_password(
            db,
            user_id=user_id,
            password=password,
            allow_session_only_reduction=False,
        )


def _verify_current_password(
    db: Session,
    *,
    user_id: int,
    password: str,
    allow_session_only_reduction: bool,
) -> bool:
    """Verify one password, or authorize only a reduction while issuance is locked.

    The caller must hold ``serialize_verification`` for the account. Returning
    ``False`` means no password was inspected: an already authenticated desktop
    session may only reduce authority by revoking one owned grant.
    """
    retry_after = reauthentication_guard.retry_after(user_id)
    if retry_after is not None:
        if allow_session_only_reduction:
            return False
        raise _reauthentication_locked(retry_after)
    user = UserRepository(db).get(user_id)
    candidate_hash = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, candidate_hash)
    if user is None or not password_ok:
        retry_after = reauthentication_guard.register_failure(user_id)
        if retry_after is not None:
            raise _reauthentication_locked(retry_after)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "authentication_failed",
                "message": "Current CareerOS password verification failed",
            },
            headers=NO_STORE_HEADERS,
        )
    reauthentication_guard.register_success(user_id)
    return True


def _revoke_with_account_control(
    db: Session,
    *,
    user_id: int,
    grant_id: str,
    password: str,
) -> GrantView:
    """Revoke under the same account lock that bounds password verification."""
    with reauthentication_guard.serialize_verification(user_id):
        _verify_current_password(
            db,
            user_id=user_id,
            password=password,
            allow_session_only_reduction=True,
        )
        return revoke_grant(db, user_id=user_id, grant_id=grant_id)


def _reauthentication_locked(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "reauthentication_locked",
            "message": (
                "Too many failed password checks. Grant creation is temporarily locked; "
                "the authenticated desktop session may still revoke owned access"
            ),
        },
        headers={
            **NO_STORE_HEADERS,
            "Retry-After": str(retry_after),
        },
    )


def _grant_error(exc: AutomationGrantError) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if exc.code == "grant_not_found"
        else (
            status.HTTP_409_CONFLICT
            if exc.code == "active_grant_limit"
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
        headers=NO_STORE_HEADERS,
    )


@router.get(
    "",
    response_model=list[GrantView],
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": PrivateErrorResponse,
            "description": "The local user session is not authenticated.",
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
        status.HTTP_403_FORBIDDEN: {
            "model": PrivateErrorResponse,
            "description": "Desktop session authorization failed.",
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": PrivateErrorResponse,
            "description": "The local access register could not be read.",
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
    },
    openapi_extra={"security": AUTOMATION_SECURITY},
)
def list_automation_grants(
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[GrantView]:
    _mark_private(response)
    return list_grants(db, user_id=user_id)


@router.post(
    "",
    response_model=GrantIssuedView,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": PrivateErrorResponse,
            "description": "The local user session is not authenticated.",
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
        status.HTTP_403_FORBIDDEN: {
            "model": AutomationErrorResponse | PrivateErrorResponse,
            "description": (
                "The current password did not match, or desktop session authorization failed."
            ),
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
        status.HTTP_409_CONFLICT: {
            "model": AutomationErrorResponse,
            "description": "The account has reached its active-grant limit.",
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": AutomationErrorResponse,
            "description": "Repeated failures temporarily locked grant creation.",
            "headers": {
                **PRIVATE_RESPONSE_HEADERS,
                "Retry-After": {
                    "description": "Whole seconds before grant creation may retry.",
                    "schema": {"type": "integer", "minimum": 1},
                },
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": PrivateErrorResponse,
            "description": "Grant creation failed unexpectedly.",
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
    },
    openapi_extra={"security": AUTOMATION_SECURITY},
)
def create_automation_grant(
    response: Response,
    payload: GrantIssueRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> GrantIssuedView:
    _mark_private(response)
    _require_current_password(
        db,
        user_id=user_id,
        password=payload.password.get_secret_value(),
    )
    try:
        grant, token = issue_grant(
            db,
            user_id=user_id,
            label=payload.label,
            scopes=tuple(payload.scopes),
            lifetime=timedelta(days=payload.lifetime_days),
        )
    except AutomationGrantError as exc:
        raise _grant_error(exc) from exc
    return GrantIssuedView(
        grant=grant,
        token=token,
        token_environment_variable="CAREEROS_MCP_TOKEN",
        warning=(
            "This token is shown once. Store it in your OS credential manager and never commit it."
        ),
    )


@router.post(
    "/{grant_id}/revoke",
    response_model=GrantView,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": PrivateErrorResponse,
            "description": "The local user session is not authenticated.",
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
        status.HTTP_403_FORBIDDEN: {
            "model": AutomationErrorResponse | PrivateErrorResponse,
            "description": (
                "The current password did not match, or desktop session authorization failed."
            ),
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
        status.HTTP_404_NOT_FOUND: {
            "model": AutomationErrorResponse,
            "description": "The grant does not belong to this account.",
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": AutomationErrorResponse,
            "description": (
                "This failed password check activated issuance lockout. "
                "Subsequent locked-session revocations do not inspect a password."
            ),
            "headers": {
                **PRIVATE_RESPONSE_HEADERS,
                "Retry-After": {
                    "description": "Whole seconds before grant creation may retry.",
                    "schema": {"type": "integer", "minimum": 1},
                },
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": PrivateErrorResponse,
            "description": "Revocation failed unexpectedly.",
            "headers": PRIVATE_RESPONSE_HEADERS,
        },
    },
    openapi_extra={"security": AUTOMATION_SECURITY},
)
def revoke_automation_grant(
    response: Response,
    grant_id: GrantId,
    payload: GrantRevokeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> GrantView:
    _mark_private(response)
    try:
        return _revoke_with_account_control(
            db,
            user_id=user_id,
            grant_id=grant_id,
            password=payload.password.get_secret_value(),
        )
    except AutomationGrantError as exc:
        raise _grant_error(exc) from exc
