"""Credential-size invariants shared by schemas and password services."""

BCRYPT_MAX_PASSWORD_BYTES = 72
MAX_USERNAME_CHARS = 50


def password_fits_bcrypt(value: str) -> bool:
    return len(value.encode("utf-8")) <= BCRYPT_MAX_PASSWORD_BYTES
