import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.deps import limiter
from backend.core.config import settings
from backend.core.credentials import MAX_USERNAME_CHARS, password_fits_bcrypt
from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.db.base import get_db
from backend.models.user import VAULT_STATE_READY
from backend.repositories.user_repository import UserRepository
from backend.schemas import Token, UserCreate
from backend.services.auth import (
    DUMMY_PASSWORD_HASH,
    get_password_hash,
    verify_password,
)
from backend.services.auth_sessions import (
    VaultMaintenancePendingError,
    issue_auth_session,
    issue_maintenance_access,
    revoke_presented_sessions,
    rotate_refresh_session,
)

REFRESH_COOKIE_NAME = "careeros_refresh_token"
LEGACY_REFRESH_COOKIE_NAME = "jh_refresh_token"
REFRESH_COOKIE_PATH = f"{settings.API_V1_STR}/auth"
logger = logging.getLogger(__name__)


def _require_trusted_browser_origin(request: Request) -> None:
    """Reject browser-initiated cookie mutations outside the exact local UI origins.

    Native and CLI callers normally omit ``Origin`` and remain supported. When
    browsers send it, SameSite is not sufficient because ports share a site;
    the origin must therefore match the credentialed CORS allowlist exactly.
    """
    origins = request.headers.getlist("origin")
    if not origins:
        fetch_sites = request.headers.getlist("sec-fetch-site")
        if fetch_sites and (
            len(fetch_sites) != 1 or fetch_sites[0].strip().casefold() != "same-origin"
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Browser origin is not allowed",
            )
        return
    if len(origins) != 1 or origins[0] not in settings.cors_origins_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Browser origin is not allowed",
        )


router = APIRouter(dependencies=[Depends(_require_trusted_browser_origin)])


def _delete_refresh_cookie(response: Response, cookie_name: str, path: str) -> None:
    response.delete_cookie(
        cookie_name,
        path=path,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )


def clear_refresh_cookies(response: Response) -> None:
    # Clear both the current narrow path and historical root-path cookies so an
    # upgrade cannot leave two same-name values with ambiguous request order.
    for cookie_name in (REFRESH_COOKIE_NAME, LEGACY_REFRESH_COOKIE_NAME):
        for path in (REFRESH_COOKIE_PATH, "/"):
            _delete_refresh_cookie(response, cookie_name, path)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )
    _delete_refresh_cookie(response, REFRESH_COOKIE_NAME, "/")
    for path in (REFRESH_COOKIE_PATH, "/"):
        _delete_refresh_cookie(response, LEGACY_REFRESH_COOKIE_NAME, path)


def _optional_bearer_token(request: Request) -> str | None:
    values = request.headers.getlist("authorization")
    if not values:
        return None
    if len(values) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization header is invalid",
        )
    parts = values[0].split()
    if len(parts) != 2 or parts[0].casefold() != "bearer" or not parts[1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization header is invalid",
        )
    return parts[1]


def _refresh_failure(detail: str) -> JSONResponse:
    response = JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": detail})
    clear_refresh_cookies(response)
    return response


@router.post("/register", response_model=Token, response_model_exclude_none=True)
@limiter.limit("5/minute")
def register(
    request: Request, response: Response, user_in: UserCreate, db: Session = Depends(get_db)
):
    user_repo = UserRepository(db)
    if user_repo.get_by_username(user_in.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Please try a different username.",
        )

    hashed_password = get_password_hash(user_in.password)
    try:
        user = user_repo.create({"username": user_in.username, "hashed_password": hashed_password})
    except IntegrityError:
        # The initial lookup is advisory only: a concurrent registration can
        # still win the unique-key race. The repository already rolls back the
        # failed transaction; keep the public response identical so the race
        # cannot become a username-enumeration or internal-error oracle.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Please try a different username.",
        ) from None

    tokens = issue_auth_session(db, user)
    _set_refresh_cookie(response, tokens.refresh_token)
    return {
        "access_token": tokens.access_token,
        "token_type": "bearer",
        "username": user_in.username,
    }


@router.post("/login", response_model=Token, response_model_exclude_none=True)
@limiter.limit("10/minute")
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    if (
        not form_data.username
        or len(form_data.username) > MAX_USERNAME_CHARS
        or not form_data.password
        or not password_fits_bcrypt(form_data.password)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Credential fields exceed supported limits",
        )
    user_repo = UserRepository(db)
    user = user_repo.get_by_username(form_data.username)
    # Always call verify_password even when user is None to prevent username
    # enumeration via response-time side-channel. Reusing a valid hash avoids
    # performing an unnecessary bcrypt generation on every login request.
    candidate_hash = user.hashed_password if user else DUMMY_PASSWORD_HASH
    password_ok = verify_password(form_data.password, candidate_hash)
    if not user or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    lifecycle_state = getattr(user, "vault_lifecycle_state", VAULT_STATE_READY)
    if not isinstance(lifecycle_state, str):
        lifecycle_state = VAULT_STATE_READY
    if lifecycle_state != VAULT_STATE_READY:
        maintenance = issue_maintenance_access(db, user)
        clear_refresh_cookies(response)
        return {
            "access_token": maintenance.access_token,
            "token_type": "bearer",
            "username": user.username,
            "session_state": maintenance.lifecycle_state,
        }

    try:
        tokens = issue_auth_session(db, user)
    except VaultMaintenancePendingError:
        db.rollback()
        current = (
            db.query(type(user)).filter(type(user).id == user.id).populate_existing().one_or_none()
        )
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        maintenance = issue_maintenance_access(db, current)
        clear_refresh_cookies(response)
        return {
            "access_token": maintenance.access_token,
            "token_type": "bearer",
            "username": current.username,
            "session_state": maintenance.lifecycle_state,
        }
    _set_refresh_cookie(response, tokens.refresh_token)
    return {
        "access_token": tokens.access_token,
        "token_type": "bearer",
        "username": user.username,
    }


@router.post("/refresh", response_model=Token, response_model_exclude_none=True)
@limiter.limit("20/minute")
def refresh(
    request: Request,
    response: Response,
    careeros_refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
    legacy_refresh_token: str | None = Cookie(None, alias=LEGACY_REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    refresh_token = careeros_refresh_token or legacy_refresh_token
    if not refresh_token:
        return _refresh_failure("Refresh token missing")
    rotation = rotate_refresh_session(db, refresh_token)
    if rotation is None:
        return _refresh_failure("Invalid refresh token")
    _set_refresh_cookie(response, rotation.refresh_token)
    return {
        "access_token": rotation.access_token,
        "token_type": "bearer",
        "username": rotation.username,
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    careeros_refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
    legacy_refresh_token: str | None = Cookie(None, alias=LEGACY_REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    access_token = _optional_bearer_token(request)
    refresh_token = careeros_refresh_token or legacy_refresh_token
    try:
        revoke_presented_sessions(
            db,
            refresh_token=refresh_token,
            access_token=access_token,
        )
    except Exception as error:
        diagnostic = diagnose_failure(error, FailureCode.REPOSITORY_OPERATION_FAILED)
        log_failure(logger, diagnostic)
        failure = JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Logout could not revoke the local session. Retry logout."},
        )
        # Never leave an automatic refresh credential after the UI has unmounted
        # its private workspace. The renderer retains only the access bearer in
        # memory so an explicit retry can complete the atomic family revocation.
        clear_refresh_cookies(failure)
        return failure
    clear_refresh_cookies(response)
    return {"message": "Logged out successfully"}
