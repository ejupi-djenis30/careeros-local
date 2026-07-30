"""Authenticated desktop management for read-only external-agent grants."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
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
    GrantIssuedView,
    GrantIssueRequest,
    GrantRevokeRequest,
    GrantView,
)
from backend.db.base import get_db
from backend.repositories.user_repository import UserRepository
from backend.services.auth import DUMMY_PASSWORD_HASH, verify_password

router = APIRouter()
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


def _mark_private(response: Response) -> None:
    for name, value in NO_STORE_HEADERS.items():
        response.headers[name] = value


def _require_current_password(
    db: Session,
    *,
    user_id: int,
    password: str,
    allow_during_lockout: bool,
) -> None:
    with reauthentication_guard.serialize_verification(user_id):
        if not allow_during_lockout:
            retry_after = reauthentication_guard.retry_after(user_id)
            if retry_after is not None:
                raise _reauthentication_locked(retry_after)
        user = UserRepository(db).get(user_id)
        candidate_hash = (
            user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
        )
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


def _reauthentication_locked(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "reauthentication_locked",
            "message": (
                "Too many failed password checks. Grant creation is temporarily locked; "
                "a correct password can still revoke access"
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


@router.get("", response_model=list[GrantView])
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
        allow_during_lockout=False,
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
    return GrantIssuedView(grant=grant, token=token)


@router.post("/{grant_id}/revoke", response_model=GrantView)
def revoke_automation_grant(
    response: Response,
    grant_id: GrantId,
    payload: GrantRevokeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> GrantView:
    _mark_private(response)
    _require_current_password(
        db,
        user_id=user_id,
        password=payload.password.get_secret_value(),
        allow_during_lockout=True,
    )
    try:
        return revoke_grant(db, user_id=user_id, grant_id=grant_id)
    except AutomationGrantError as exc:
        raise _grant_error(exc) from exc
