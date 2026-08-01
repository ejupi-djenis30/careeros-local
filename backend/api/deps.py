import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import PyJWTError
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.db.base import get_db
from backend.models.auth_session import AuthSession
from backend.models.user import (
    VAULT_STATE_ERASURE_PENDING,
    VAULT_STATE_READY,
    VAULT_STATE_RESET_PENDING,
    VAULT_STATE_RESTORE_PENDING,
    User,
)
from backend.services.auth import (
    ACCESS_PURPOSE_SESSION,
    ACCESS_PURPOSE_VAULT_MAINTENANCE,
    decode_access_token,
)
from backend.services.auth_sessions import is_erasure_pending_session

is_testing = os.environ.get("TESTING") == "1"
limiter = Limiter(key_func=get_remote_address, enabled=not is_testing)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthFamilyAuthority:
    user_id: int
    session_id: str
    lifecycle_state: str
    token_purpose: str


def get_current_user_id(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> int:
    try:
        payload = decode_access_token(token)
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as error:
        diagnostic = diagnose_failure(error, FailureCode.AUTH_TOKEN_DECODE_FAILED)
        log_failure(logger, diagnostic)
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    username = payload.get("sub")
    session_id = payload.get("sid")
    if (
        not isinstance(username, str)
        or not isinstance(session_id, str)
        or payload.get("purpose") != ACCESS_PURPOSE_SESSION
    ):
        raise HTTPException(status_code=401, detail="Invalid token")

    # Access JWTs are intentionally not self-sufficient. One indexed joined lookup
    # binds the signed subject and family id to live, non-revoked server-side state.
    user_id = (
        db.query(AuthSession.user_id)
        .join(User, User.id == AuthSession.user_id)
        .filter(
            AuthSession.id == session_id,
            User.username == username,
            User.vault_lifecycle_state == VAULT_STATE_READY,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
        .scalar()
    )
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return int(user_id)


def get_vault_maintenance_authority(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AuthFamilyAuthority:
    """Accept live access or the one durable single-purpose erasure retry family."""

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    username = payload.get("sub")
    session_id = payload.get("sid")
    if not isinstance(username, str) or not isinstance(session_id, str):
        raise HTTPException(status_code=401, detail="Invalid token")

    result = (
        db.query(AuthSession, User.vault_lifecycle_state)
        .join(User, User.id == AuthSession.user_id)
        .filter(
            AuthSession.id == session_id,
            User.username == username,
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
        .one_or_none()
    )
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    session, lifecycle_state = result
    purpose = payload.get("purpose")
    valid_authority = (
        (
            lifecycle_state == VAULT_STATE_READY
            and purpose == ACCESS_PURPOSE_SESSION
            and session.revoked_at is None
        )
        or (
            lifecycle_state in {VAULT_STATE_RESET_PENDING, VAULT_STATE_RESTORE_PENDING}
            and purpose == ACCESS_PURPOSE_VAULT_MAINTENANCE
            and session.revoked_at is None
        )
        or (
            lifecycle_state == VAULT_STATE_ERASURE_PENDING
            and purpose == ACCESS_PURPOSE_VAULT_MAINTENANCE
            and is_erasure_pending_session(session)
        )
    )
    if not valid_authority:
        raise HTTPException(status_code=401, detail="Invalid token")
    return AuthFamilyAuthority(
        user_id=int(session.user_id),
        session_id=session.id,
        lifecycle_state=str(lifecycle_state),
        token_purpose=str(purpose),
    )


def require_vault_maintenance_operation(
    authority: AuthFamilyAuthority,
    pending_state: str,
) -> None:
    """Reject operation confusion without converting valid maintenance auth to 401."""

    allowed_states = {VAULT_STATE_READY, pending_state}
    if pending_state == VAULT_STATE_ERASURE_PENDING:
        # Complete erasure is the recovery superset when reset/restore cannot
        # finish (for example, the original restore ZIP is no longer available).
        allowed_states.update({VAULT_STATE_RESET_PENDING, VAULT_STATE_RESTORE_PENDING})
    if authority.lifecycle_state in allowed_states:
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "vault_maintenance_conflict",
            "message": "Finish the pending local-data operation before starting another one.",
            "pending_state": authority.lifecycle_state,
        },
    )


# Compatibility name for focused tests and integrations introduced with the
# first erasure-only slice.
get_erasure_authority = get_vault_maintenance_authority


def job_service_dep(db: Session = Depends(get_db)):
    from backend.services.job_service import get_job_service

    return get_job_service(db)


def profile_service_dep(db: Session = Depends(get_db)):
    from backend.services.profile_service import get_profile_service

    return get_profile_service(db)


async def require_local_analysis_ready() -> None:
    """Fail closed before a route starts work that promises local-model analysis."""
    from backend.inference.service import check_local_model_readiness

    readiness = await check_local_model_readiness()
    if readiness.ready:
        return
    raise HTTPException(
        status_code=428,
        detail={
            "code": "local_model_required",
            "message": "A ready local model is required for analysis",
            "model_error_code": readiness.error_code,
        },
    )
