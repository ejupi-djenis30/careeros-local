#!/bin/sh
set -eu

data_dir="${DATA_DIR:-/app/data}"
secret_file="${CAREEROS_SECRET_FILE:-${data_dir}/.secret-key}"

mkdir -p "$data_dir" "${HOME:-${data_dir}/home}" "${XDG_CONFIG_HOME:-${data_dir}/config}" "${XDG_CACHE_HOME:-${data_dir}/cache}"

# A single-installation secret is generated locally and persisted with the vault.
# Explicit SECRET_KEY always wins, which keeps CI and advanced deployments deterministic.
if [ -z "${SECRET_KEY:-}" ]; then
    SECRET_KEY="$(python - "$secret_file" <<'PY'
import os
import re
import secrets
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])


def fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def settle_completed_publication(metadata: os.stat_result) -> os.stat_result:
    """Remove only the creator's canonical alias after a crash post-link."""

    link_count = int(getattr(metadata, "st_nlink", 1))
    if link_count == 1:
        return metadata
    if link_count != 2:
        raise RuntimeError("CareerOS installation secret has an ambiguous hard-link identity")

    temporary_pattern = re.compile(
        rf"^\.{re.escape(path.name)}\.[0-9a-f]{{32}}\.tmp$"
    )
    candidates = [
        candidate
        for candidate in path.parent.iterdir()
        if temporary_pattern.fullmatch(candidate.name)
    ]
    if len(candidates) > 256:
        raise RuntimeError("CareerOS installation secret has too many temporary siblings")
    aliases: list[Path] = []
    for candidate in candidates:
        try:
            candidate_metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        if os.path.samestat(metadata, candidate_metadata):
            if (
                stat.S_ISLNK(candidate_metadata.st_mode)
                or not stat.S_ISREG(candidate_metadata.st_mode)
                or int(getattr(candidate_metadata, "st_nlink", 1)) != 2
                or stat.S_IMODE(candidate_metadata.st_mode) not in {0o400, 0o600}
                or (
                    hasattr(os, "geteuid")
                    and candidate_metadata.st_uid != os.geteuid()
                )
            ):
                raise RuntimeError("CareerOS installation secret temporary alias is unsafe")
            aliases.append(candidate)

    if len(aliases) != 1:
        refreshed = path.lstat()
        if os.path.samestat(metadata, refreshed) and refreshed.st_nlink == 1:
            return refreshed
        raise RuntimeError("CareerOS installation secret has an ambiguous hard-link identity")
    try:
        alias_metadata = aliases[0].lstat()
    except FileNotFoundError:
        alias_metadata = None
    if alias_metadata is not None:
        if not os.path.samestat(metadata, alias_metadata):
            raise RuntimeError("CareerOS installation secret temporary alias changed")
        aliases[0].unlink()
        fsync_directory(path.parent)
    settled = path.lstat()
    if not os.path.samestat(metadata, settled) or settled.st_nlink != 1:
        raise RuntimeError("CareerOS installation secret publication did not settle safely")
    return settled


try:
    path.lstat()
except FileNotFoundError:
    # Write a private inode through an unpredictable, exclusively-created
    # sibling. O_NOFOLLOW and O_EXCL make a precreated symlink/collision fail
    # before any bytes are written. link(2) publishes without replacing a
    # concurrent winner.
    for _ in range(128):
        temporary = path.parent / f".{path.name}.{secrets.token_hex(16)}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(temporary, flags, 0o600)
        except FileExistsError:
            continue
        try:
            payload = f"{secrets.token_hex(32)}\n".encode("ascii")
            offset = 0
            while offset < len(payload):
                offset += os.write(descriptor, payload[offset:])
            os.fsync(descriptor)
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                pass
            else:
                fsync_directory(path.parent)
        finally:
            os.close(descriptor)
            temporary.unlink(missing_ok=True)
            fsync_directory(path.parent)
        break
    else:
        raise RuntimeError("CareerOS could not reserve a private installation secret")

metadata = path.lstat()
if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
    raise RuntimeError("CareerOS installation secret must be one regular non-linked file")
if stat.S_IMODE(metadata.st_mode) not in {0o400, 0o600}:
    raise RuntimeError("CareerOS installation secret must have private owner-only permissions")
if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
    raise RuntimeError("CareerOS installation secret must be owned by the service user")
if not 43 <= metadata.st_size <= 258:
    raise RuntimeError("CareerOS installation secret has an invalid size")
metadata = settle_completed_publication(metadata)
flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(path, flags)
try:
    opened = os.fstat(descriptor)
    if (
        not os.path.samestat(metadata, opened)
        or opened.st_nlink != 1
        or stat.S_IMODE(opened.st_mode) not in {0o400, 0o600}
        or (hasattr(os, "geteuid") and opened.st_uid != os.geteuid())
    ):
        raise RuntimeError("CareerOS installation secret changed while opening")
    payload = os.read(descriptor, 259)
finally:
    os.close(descriptor)
value = payload.removesuffix(b"\n")
if payload not in {value, value + b"\n"} or re.fullmatch(rb"[A-Za-z0-9_-]{43,256}", value) is None:
    raise RuntimeError("CareerOS installation secret is not canonical")
print(value.decode("ascii"))
PY
)"
    export SECRET_KEY
fi

python -m backend.pre_start

exec "$@"
