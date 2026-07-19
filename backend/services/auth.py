from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

import bcrypt
import jwt
from jwt.exceptions import PyJWTError

from backend.core.config import settings

# A fixed, valid bcrypt hash keeps unknown-user login checks on the same expensive
# verification path as known users without generating a second hash for every request.
# The plaintext is intentionally not a credential and the value can be public.
DUMMY_PASSWORD_HASH = "$2b$12$wwDasuPkoAs8hmlsQ61aB.Jm6dSQnQMeBPEp5zYhmdg0Nv54rzwza"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return cast(
            bool, bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        )
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    return cast(bytes, bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return cast(str, jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return cast(str, jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") and payload.get("type") != "access":
            return None
        return cast(dict[Any, Any], payload)
    except PyJWTError:
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return cast(dict[Any, Any], payload)
    except PyJWTError:
        return None
