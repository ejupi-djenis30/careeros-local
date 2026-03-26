from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.api.deps import limiter
from backend.core.config import settings
from backend.db.base import get_db
from backend.models import User
from backend.schemas import Token, UserCreate
from backend.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)

router = APIRouter()


@router.post("/register", response_model=Token)
@limiter.limit("5/minute")
def register(request: Request, response: Response, user_in: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_in.username).first()
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    hashed_password = get_password_hash(user_in.password)
    db_user = User(username=user_in.username, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    access_token = create_access_token(data={"sub": user_in.username})
    refresh_token = create_refresh_token(data={"sub": user_in.username})
    response.set_cookie(
        key="jh_refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )
    return {"access_token": access_token, "token_type": "bearer", "username": user_in.username}


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    response.set_cookie(
        key="jh_refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )
    return {"access_token": access_token, "token_type": "bearer", "username": user.username}


@router.post("/refresh", response_model=Token)
@limiter.limit("20/minute")
def refresh(request: Request, response: Response, jh_refresh_token: str | None = Cookie(None), db: Session = Depends(get_db)):
    if not jh_refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    payload = decode_refresh_token(jh_refresh_token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    username = payload["sub"]
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User vanished")

    access_token = create_access_token(data={"sub": username})
    new_refresh_token = create_refresh_token(data={"sub": username})

    response.set_cookie(
        key="jh_refresh_token",
        value=new_refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )
    return {"access_token": access_token, "token_type": "bearer", "username": username}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("jh_refresh_token", httponly=True, samesite="lax", secure=settings.ENVIRONMENT == "production")
    return {"message": "Logged out successfully"}
