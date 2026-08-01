"""Bounded reader for the persisted installation signing secret."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

INSTALLATION_SECRET_MIN_BYTES = 43
INSTALLATION_SECRET_MAX_BYTES = 256
_INSTALLATION_SECRET = re.compile(r"^[A-Za-z0-9_-]+$")


class InstallationSecretError(RuntimeError):
    """The persisted installation secret is not one safe canonical file."""


def _is_link_like(metadata: os.stat_result) -> bool:
    file_attributes = int(getattr(metadata, "st_file_attributes", 0))
    return stat.S_ISLNK(metadata.st_mode) or bool(file_attributes & 0x400)


def _valid_file_metadata(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and not _is_link_like(metadata)
        and int(getattr(metadata, "st_nlink", 1)) == 1
        and INSTALLATION_SECRET_MIN_BYTES <= metadata.st_size <= INSTALLATION_SECRET_MAX_BYTES + 2
    )


def _effective_user_id() -> int:
    getter = getattr(os, "geteuid", None)
    if getter is None:
        raise InstallationSecretError("Installation secret ownership checks are unavailable")
    return int(getter())


def _validated_path_in_root(path: str | Path, trusted_root: str | Path) -> Path:
    source = Path(os.path.abspath(os.fspath(Path(path).expanduser())))
    root = Path(os.path.abspath(os.fspath(Path(trusted_root).expanduser())))
    normalized_source = os.path.normcase(os.path.normpath(os.fspath(source)))
    normalized_root = os.path.normcase(os.path.normpath(os.fspath(root)))
    try:
        common = os.path.commonpath((normalized_source, normalized_root))
    except ValueError as exc:
        raise InstallationSecretError("Installation secret is outside its private root") from exc
    if common != normalized_root or normalized_source == normalized_root:
        raise InstallationSecretError("Installation secret is outside its private root")

    relative = Path(os.path.relpath(source, root))
    current = root
    for component in relative.parts[:-1]:
        metadata = current.lstat()
        if _is_link_like(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise InstallationSecretError("Installation secret path contains a linked directory")
        current /= component
    metadata = current.lstat()
    if _is_link_like(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise InstallationSecretError("Installation secret path contains a linked directory")
    return source


def read_installation_secret_file(
    path: str | Path,
    *,
    trusted_root: str | Path | None = None,
) -> str:
    """Read one bounded, unaliased and descriptor-stable local secret.

    The desktop publisher and container entrypoint create this file privately.
    Headless consumers still validate it independently before using its bytes as
    signing material. POSIX permissions are repaired only after ownership and
    descriptor identity have been proven.
    """

    source = _validated_path_in_root(path, trusted_root) if trusted_root is not None else Path(path)
    before = source.lstat()
    if not _valid_file_metadata(before):
        raise InstallationSecretError(
            "Installation secret must be one bounded, unaliased regular file"
        )

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if os.name != "nt":
        flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise InstallationSecretError("Installation secret changed while opening") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not _valid_file_metadata(opened)
            or not os.path.samestat(before, opened)
            or opened.st_size != before.st_size
        ):
            raise InstallationSecretError("Installation secret changed while opening")

        if os.name != "nt":
            get_effective_user_id = getattr(os, "geteuid", None)
            change_mode = getattr(os, "fchmod", None)
            if (
                get_effective_user_id is None
                or change_mode is None
                or int(opened.st_uid) != int(get_effective_user_id())
            ):
                raise InstallationSecretError(
                    "Installation secret is not owned by the current user"
                )
            change_mode(descriptor, 0o600)

        baseline = os.fstat(descriptor)
        if (
            not _valid_file_metadata(baseline)
            or not os.path.samestat(opened, baseline)
            or (os.name != "nt" and stat.S_IMODE(baseline.st_mode) != 0o600)
        ):
            raise InstallationSecretError("Installation secret is not private")

        chunks: list[bytes] = []
        remaining = baseline.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(payload) != baseline.st_size
            or not _valid_file_metadata(after)
            or not os.path.samestat(baseline, after)
            or after.st_size != baseline.st_size
            or after.st_mtime_ns != baseline.st_mtime_ns
            or after.st_ctime_ns != baseline.st_ctime_ns
        ):
            raise InstallationSecretError("Installation secret changed while reading")
    finally:
        os.close(descriptor)

    try:
        current = source.lstat()
    except OSError as exc:
        raise InstallationSecretError("Installation secret changed while reading") from exc
    if (
        not _valid_file_metadata(current)
        or not os.path.samestat(after, current)
        or current.st_size != after.st_size
        or (
            os.name != "nt"
            and (
                int(current.st_uid) != _effective_user_id()
                or stat.S_IMODE(current.st_mode) != 0o600
            )
        )
    ):
        raise InstallationSecretError("Installation secret changed while reading")
    if trusted_root is not None:
        _validated_path_in_root(source, trusted_root)

    try:
        encoded = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise InstallationSecretError("Installation secret is not canonical") from exc
    value = encoded.removesuffix("\r\n").removesuffix("\n")
    if (
        encoded not in {value, f"{value}\n", f"{value}\r\n"}
        or not INSTALLATION_SECRET_MIN_BYTES <= len(value) <= INSTALLATION_SECRET_MAX_BYTES
        or _INSTALLATION_SECRET.fullmatch(value) is None
    ):
        raise InstallationSecretError("Installation secret is not canonical")
    return value
