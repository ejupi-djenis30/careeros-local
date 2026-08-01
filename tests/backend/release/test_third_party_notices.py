from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import scripts.third_party_notices as notices
from scripts.third_party_notices import (
    APPROVED_NOTICE_SHA256,
    NOTICE_NAME,
    NOTICE_PATH,
    find_packaged_notice,
    selected_rust_licenses,
    verify_notice_bytes,
    verify_notice_file,
)


def test_cpython_notice_generation_requires_the_exact_pinned_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notices.platform, "python_version", lambda: "3.12.10")

    with pytest.raises(RuntimeError, match="pinned CPython 3.12.13, not 3.12.10"):
        notices._runtime_legal_texts(
            {
                "ecosystem": "runtime",
                "name": "cpython",
                "version": "3.12.13",
                "license": "PSF-2.0",
                "source": ".python-version",
            },
            {},
        )


def test_repository_notice_is_lock_bound_complete_and_approved() -> None:
    payload = NOTICE_PATH.read_bytes()
    manifest = verify_notice_file()

    assert hashlib.sha256(payload).hexdigest() == APPROVED_NOTICE_SHA256
    assert manifest["componentCounts"] == {
        "frontend": 12,
        "python": 55,
        "runtime": 2,
        "rust": 484,
    }
    identities = {
        (component["ecosystem"], component["name"], component["version"])
        for component in manifest["components"]
    }
    assert ("frontend", "bootstrap", "5.3.8") in identities
    assert ("frontend", "bootstrap-icons", "1.13.1") in identities
    assert ("runtime", "cpython", "3.12.13") in identities
    assert ("runtime", "pyinstaller", "6.21.0") in identities
    assert all(component["textIds"] for component in manifest["components"])


def test_notice_rejects_tampered_text_even_without_the_outer_approved_digest() -> None:
    payload = NOTICE_PATH.read_bytes()
    tampered = payload.replace(b"Permission is hereby granted", b"Permission is hereby changed", 1)

    with pytest.raises(RuntimeError, match="text digest is invalid"):
        verify_notice_bytes(tampered, approved_sha256="TO_BE_GENERATED")


def test_notice_rejects_a_stale_lock_binding() -> None:
    payload = NOTICE_PATH.read_bytes()
    manifest = verify_notice_bytes(payload)
    expected = manifest["sourceLocks"]["requirements.lock"].encode()
    tampered = payload.replace(expected, b"0" * 64, 1)

    with pytest.raises(RuntimeError, match="stale for the locked dependency"):
        verify_notice_bytes(tampered, approved_sha256="TO_BE_GENERATED")


def test_unreviewed_rust_license_expression_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="Unreviewed Rust license expression"):
        selected_rust_licenses("GPL-3.0-only")


def test_extracted_package_requires_the_exact_notice_once(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    notice = package / NOTICE_NAME
    notice.write_bytes(NOTICE_PATH.read_bytes())

    path, manifest = find_packaged_notice(package)

    assert path == notice
    assert manifest["componentCounts"]["rust"] == 484

    duplicate = package / "nested" / NOTICE_NAME.lower()
    duplicate.parent.mkdir()
    duplicate.write_bytes(NOTICE_PATH.read_bytes())
    with pytest.raises(RuntimeError, match="found 2"):
        find_packaged_notice(package)

    duplicate.write_bytes(b"tampered duplicate\n")
    with pytest.raises(RuntimeError, match="found 2"):
        find_packaged_notice(package)


@pytest.mark.parametrize("payload", [None, b"tampered\n"])
def test_extracted_package_rejects_missing_or_tampered_notices(
    tmp_path: Path, payload: bytes | None
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    if payload is not None:
        (package / NOTICE_NAME).write_bytes(payload)

    with pytest.raises(RuntimeError, match=NOTICE_NAME):
        find_packaged_notice(package)
