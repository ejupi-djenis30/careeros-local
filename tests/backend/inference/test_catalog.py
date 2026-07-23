import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.inference.catalog import (
    current_platform_key,
    load_model_catalog,
    load_verified_catalog,
    verify_file_sha256,
)


def test_bundled_catalog_has_a_valid_signature_and_all_platforms() -> None:
    catalog = load_model_catalog()

    assert catalog.models
    assert set(catalog.runtime.assets) == {
        "linux-aarch64",
        "linux-x86_64",
        "macos-aarch64",
        "macos-x86_64",
        "windows-aarch64",
        "windows-x86_64",
    }


def test_bundled_catalog_has_checkout_stable_line_endings() -> None:
    catalog = Path("backend/inference/model_catalog.json").read_bytes()

    assert b"\r\n" not in catalog


@pytest.mark.parametrize(
    ("system_name", "machine_name", "expected"),
    [
        ("win32", "AMD64", "windows-x86_64"),
        ("darwin", "arm64", "macos-aarch64"),
        ("linux", "x86_64", "linux-x86_64"),
        ("linux", "aarch64", "linux-aarch64"),
    ],
)
def test_platform_selection_is_explicit(
    system_name: str, machine_name: str, expected: str
) -> None:
    assert current_platform_key(system_name=system_name, machine_name=machine_name) == expected


def test_catalog_signature_rejects_modified_content() -> None:
    with TemporaryDirectory(prefix="careeros-catalog-") as directory:
        root = Path(directory)
        source = Path("backend/inference/model_catalog.json")
        catalog = root / "model_catalog.json"
        catalog.write_bytes(source.read_bytes() + b" ")
        signature = root / "model_catalog.sha256"
        signature.write_text(
            Path("backend/inference/model_catalog.sha256").read_text(encoding="ascii"),
            encoding="ascii",
        )

        with pytest.raises(ValueError, match="SHA-256"):
            load_verified_catalog(catalog, signature)


def test_file_hash_verification_rejects_tampering() -> None:
    with TemporaryDirectory(prefix="careeros-hash-") as directory:
        asset = Path(directory) / "asset.bin"
        asset.write_bytes(b"trusted")
        expected = hashlib.sha256(b"trusted").hexdigest()
        verify_file_sha256(asset, expected)

        asset.write_bytes(b"tampered")
        with pytest.raises(ValueError, match="SHA-256"):
            verify_file_sha256(asset, expected)
