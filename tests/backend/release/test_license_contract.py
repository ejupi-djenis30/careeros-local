from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.license_contract import (
    APPROVED_LICENSE_SHA256,
    ROOT,
    approved_license_bytes,
    find_packaged_license,
    main,
    verify_distributed_license,
)


def test_repository_license_is_the_exact_canonical_lf_payload() -> None:
    payload = (ROOT / "LICENSE").read_bytes()

    assert payload == approved_license_bytes()
    assert b"\r" not in payload
    assert APPROVED_LICENSE_SHA256 == "7e1d73415a3de7fa896ac8871ae0aea8fc736e9f0d274bf658c18399236976c6"


def test_extracted_package_requires_one_exact_project_license(tmp_path: Path) -> None:
    package = tmp_path / "package"
    (package / "third-party").mkdir(parents=True)
    (package / "third-party" / "LICENSE").write_text(
        "A dependency license that must not satisfy the project contract.\n", encoding="utf-8"
    )
    project_license = package / "LICENSE"
    project_license.write_bytes(approved_license_bytes())

    path, record = find_packaged_license(package)

    assert path == project_license
    assert record["sha256"] == APPROVED_LICENSE_SHA256


@pytest.mark.parametrize("payload", [None, b"tampered\n", approved_license_bytes() + b"\n"])
def test_extracted_package_rejects_missing_or_tampered_project_license(
    tmp_path: Path, payload: bytes | None
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    if payload is not None:
        (package / "LICENSE").write_bytes(payload)

    with pytest.raises(RuntimeError, match="Packaged project LICENSE"):
        find_packaged_license(package)


def test_extracted_package_rejects_duplicate_project_license(tmp_path: Path) -> None:
    package = tmp_path / "package"
    for directory in ("", "nested"):
        destination = package / directory / "LICENSE"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(approved_license_bytes())

    with pytest.raises(RuntimeError, match="found 2"):
        find_packaged_license(package)


def test_extracted_package_rejects_lowercase_duplicate_project_license(tmp_path: Path) -> None:
    package = tmp_path / "package"
    nested = package / "nested"
    nested.mkdir(parents=True)
    (package / "LICENSE").write_bytes(approved_license_bytes())
    (nested / "license").write_bytes(approved_license_bytes())

    with pytest.raises(RuntimeError, match="found 2"):
        find_packaged_license(package)


def test_extracted_package_rejects_license_symlink_without_dereferencing_it(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    nested = package / "nested"
    nested.mkdir(parents=True)
    project_license = package / "LICENSE"
    project_license.write_bytes(approved_license_bytes())
    (nested / "license").symlink_to(project_license)

    with pytest.raises(RuntimeError, match="LICENSE alias is unsafe"):
        find_packaged_license(package)


def test_distributed_license_rejects_noncanonical_newlines(tmp_path: Path) -> None:
    destination = tmp_path / "LICENSE"
    destination.write_bytes(approved_license_bytes().replace(b"\n", b"\r\n"))

    with pytest.raises(RuntimeError, match="differs from the approved text"):
        verify_distributed_license(destination)


def test_cli_rejects_package_root_symlink_before_resolving_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "LICENSE").write_bytes(approved_license_bytes())
    link = tmp_path / "package-link"
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(sys, "argv", ["license_contract.py", "--package-root", str(link)])

    with pytest.raises(RuntimeError, match="root is missing or unsafe"):
        main()
