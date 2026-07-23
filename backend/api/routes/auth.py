from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.api.deps import limiter
from backend.core.config import settings
from backend.db.base import get_db
from backend.repositories.user_repository import UserRepository
from backend.schemas import Token, UserCreate
from backend.services.auth import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)

router = APIRouter()

REFRESH_COOKIE_NAME = "careeros_refresh_token"
LEGACY_REFRESH_COOKIE_NAME = "jh_refresh_token"


def _clear_refresh_cookies(response: Response) -> None:
    for cookie_name in (REFRESH_COOKIE_NAME, LEGACY_REFRESH_COOKIE_NAME):
        response.delete_cookie(
            cookie_name,
            httponly=True,
            samesite="lax",
            secure=settings.ENVIRONMENT == "production",
        )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )
    response.delete_cookie(
        LEGACY_REFRESH_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )


def _refresh_failure(detail: str) -> JSONResponse:
    response = JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": detail})
    _clear_refresh_cookies(response)
    return response


@router.post("/register", response_model=Token)
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
    user_repo.create({"username": user_in.username, "hashed_password": hashed_password})

    access_token = create_access_token(data={"sub": user_in.username})
    refresh_token = create_refresh_token(data={"sub": user_in.username})
    _set_refresh_cookie(response, refresh_token)
    return {"access_token": access_token, "token_type": "bearer", "username": user_in.username}


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
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

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    _set_refresh_cookie(response, refresh_token)
    return {"access_token": access_token, "token_type": "bearer", "username": user.username}


@router.post("/refresh", response_model=Token)
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
    payload = decode_refresh_token(refresh_token)
    if not payload or "sub" not in payload:
        return _refresh_failure("Invalid refresh token")

    username = payload["sub"]
    user_repo = UserRepository(db)
    user = user_repo.get_by_username(username)
    if not user:
        return _refresh_failure("User vanished")

    access_token = create_access_token(data={"sub": username})
    new_refresh_token = create_refresh_token(data={"sub": username})

    _set_refresh_cookie(response, new_refresh_token)
    return {"access_token": access_token, "token_type": "bearer", "username": username}


@router.post("/logout")
def logout(response: Response):
    _clear_refresh_cookies(response)
    return {"message": "Logged out successfully"}
