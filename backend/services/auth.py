import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

import bcrypt  # type: ignore[import-untyped]
import jwt
from jwt.exceptions import PyJWTError

from backend.core.config import settings
from backend.core.credentials import MAX_USERNAME_CHARS, password_fits_bcrypt

# A fixed, valid bcrypt hash keeps unknown-user login checks on the same expensive
# verification path as known users without generating a second hash for every request.
# The plaintext is intentionally not a credential and the value can be public.
DUMMY_PASSWORD_HASH = "$2b$12$wwDasuPkoAs8hmlsQ61aB.Jm6dSQnQMeBPEp5zYhmdg0Nv54rzwza"
_TOKEN_IDENTIFIER = re.compile(r"^[0-9a-f]{32}$")
ACCESS_PURPOSE_SESSION = "session"
ACCESS_PURPOSE_VAULT_MAINTENANCE = "vault_maintenance"
_ACCESS_PURPOSES = {
    ACCESS_PURPOSE_SESSION,
    ACCESS_PURPOSE_VAULT_MAINTENANCE,
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not password_fits_bcrypt(plain_password):
        return False
    try:
        return cast(
            bool, bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        )
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    if not password_fits_bcrypt(password):
        raise ValueError("Password exceeds the bcrypt 72-byte limit")
    return cast(bytes, bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())).decode("utf-8")


def create_session_identifier() -> str:
    """Return a non-secret identifier shared by one access/refresh family."""

    return secrets.token_hex(16)


def _require_session_identifier(session_id: str) -> str:
    if not _TOKEN_IDENTIFIER.fullmatch(session_id):
        raise ValueError("Auth session identifier is invalid")
    return session_id


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    *,
    session_id: str,
    purpose: str = ACCESS_PURPOSE_SESSION,
) -> str:
    if purpose not in _ACCESS_PURPOSES:
        raise ValueError("Access token purpose is invalid")
    to_encode = data.copy()
    issued_at = datetime.now(timezone.utc)
    expire = issued_at + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    resolved_session_id = _require_session_identifier(session_id)
    to_encode.update(
        {
            "exp": expire,
            "iat": issued_at,
            "jti": secrets.token_hex(16),
            "sid": resolved_session_id,
            "type": "access",
            "purpose": purpose,
        }
    )
    return cast(str, jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def create_refresh_token(data: dict, *, session_id: str | None = None) -> str:
    to_encode = data.copy()
    issued_at = datetime.now(timezone.utc)
    expire = issued_at + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    resolved_session_id = _require_session_identifier(session_id or create_session_identifier())
    to_encode.update(
        {
            "exp": expire,
            "iat": issued_at,
            "jti": secrets.token_hex(16),
            "sid": resolved_session_id,
            "type": "refresh",
        }
    )
    return cast(str, jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM))


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "iat", "jti", "sid", "sub", "type", "purpose"]},
        )
        if (
            payload.get("type") != "access"
            or payload.get("purpose") not in _ACCESS_PURPOSES
            or not _valid_common_claims(payload)
            or not _valid_session_claim(payload)
        ):
            return None
        return cast(dict[Any, Any], payload)
    except PyJWTError:
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "iat", "jti", "sid", "sub", "type"]},
        )
        if (
            payload.get("type") != "refresh"
            or not _valid_common_claims(payload)
            or not _valid_session_claim(payload)
        ):
            return None
        return cast(dict[Any, Any], payload)
    except PyJWTError:
        return None


def _valid_common_claims(payload: dict[str, Any]) -> bool:
    subject = payload.get("sub")
    jti = payload.get("jti")
    return (
        isinstance(subject, str)
        and 0 < len(subject) <= MAX_USERNAME_CHARS
        and isinstance(jti, str)
        and _TOKEN_IDENTIFIER.fullmatch(jti) is not None
        and isinstance(payload.get("iat"), int)
        and not isinstance(payload.get("iat"), bool)
        and isinstance(payload.get("exp"), int)
        and not isinstance(payload.get("exp"), bool)
    )


def _valid_session_claim(payload: dict[str, Any]) -> bool:
    session_id = payload.get("sid")
    return isinstance(session_id, str) and _TOKEN_IDENTIFIER.fullmatch(session_id) is not None
