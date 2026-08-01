import os
import stat
from pathlib import Path

import pytest

from backend.storage import private_secret
from backend.storage.private_secret import (
    InstallationSecretError,
    read_installation_secret_file,
)

_VALID_SECRET = "s" * 64


@pytest.mark.parametrize("suffix", ["", "\n", "\r\n"])
def test_private_secret_reader_accepts_only_canonical_line_endings(
    tmp_path: Path,
    suffix: str,
) -> None:
    secret = tmp_path / ".installation-secret"
    secret.write_bytes(f"{_VALID_SECRET}{suffix}".encode("ascii"))

    assert read_installation_secret_file(secret) == _VALID_SECRET
    if os.name != "nt":
        assert stat.S_IMODE(secret.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "payload",
    [
        b"s" * 42,
        b"s" * 257,
        b"s" * 64 + b"\n\n",
        b"s" * 63 + b"!",
        b"\xff" * 64,
    ],
)
def test_private_secret_reader_rejects_noncanonical_payloads(
    tmp_path: Path,
    payload: bytes,
) -> None:
    secret = tmp_path / ".installation-secret"
    secret.write_bytes(payload)

    with pytest.raises(InstallationSecretError):
        read_installation_secret_file(secret)


def test_private_secret_reader_rejects_oversized_file_before_opening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = tmp_path / ".installation-secret"
    secret.write_bytes(b"s" * 1024)

    def unexpected_open(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("oversized secret must be rejected before open")

    monkeypatch.setattr(private_secret.os, "open", unexpected_open)
    with pytest.raises(InstallationSecretError, match="bounded"):
        read_installation_secret_file(secret)


def test_private_secret_reader_rejects_hard_link_alias(tmp_path: Path) -> None:
    secret = tmp_path / ".installation-secret"
    alias = tmp_path / "alias"
    secret.write_text(_VALID_SECRET, encoding="ascii")
    try:
        os.link(secret, alias)
    except OSError as exc:
        pytest.skip(f"Hard links are unavailable: {exc}")

    with pytest.raises(InstallationSecretError, match="unaliased"):
        read_installation_secret_file(secret)


def test_private_secret_reader_rejects_symbolic_link_without_reading_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    alias = tmp_path / ".installation-secret"
    target.write_text(_VALID_SECRET, encoding="ascii")
    try:
        alias.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"File symlinks are unavailable: {exc}")

    with pytest.raises(InstallationSecretError, match="unaliased"):
        read_installation_secret_file(alias)
    assert target.read_text(encoding="ascii") == _VALID_SECRET


def test_private_secret_reader_rejects_a_linked_parent_inside_trusted_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (external / ".installation-secret").write_text(_VALID_SECRET, encoding="ascii")
    linked_parent = root / "vault"
    try:
        linked_parent.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symlinks are unavailable: {exc}")

    with pytest.raises(InstallationSecretError, match="linked directory"):
        read_installation_secret_file(
            linked_parent / ".installation-secret",
            trusted_root=root,
        )


def test_private_secret_reader_rejects_lstat_open_exchange(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = tmp_path / ".installation-secret"
    replacement = tmp_path / "replacement"
    secret.write_text(_VALID_SECRET, encoding="ascii")
    replacement.write_text("r" * 64, encoding="ascii")
    real_open = private_secret.os.open
    exchanged = False

    def exchange_then_open(path, flags, *args, **kwargs):
        nonlocal exchanged
        if Path(path) == secret and not exchanged:
            exchanged = True
            replacement.replace(secret)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(private_secret.os, "open", exchange_then_open)

    with pytest.raises(InstallationSecretError, match="changed while opening"):
        read_installation_secret_file(secret)
    assert exchanged is True
