from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

import scripts.agent_distribution as agent_distribution
from scripts.agent_distribution import (
    AGENT_REQUIREMENTS_LOCK,
    canonical_agent_wheel_name,
    stage_agent_candidate,
    validate_agent_candidate,
    validate_agent_wheel,
)
from scripts.check_release_versions import ROOT
from tests.backend.release.helpers import (
    COMMIT,
    VERSION,
    write_agent_candidate,
    write_agent_wheel,
)


def _replace_member(wheel: Path, name: str, payload: bytes) -> None:
    replacement = wheel.with_name("replacement.whl")
    with (
        zipfile.ZipFile(wheel) as source,
        zipfile.ZipFile(replacement, mode="w", compression=zipfile.ZIP_DEFLATED) as destination,
    ):
        for info in source.infolist():
            destination.writestr(
                info.filename, payload if info.filename == name else source.read(info)
            )
    replacement.replace(wheel)


def test_agent_candidate_binds_the_validated_wheel_and_tagged_lock(tmp_path: Path) -> None:
    candidate = write_agent_candidate(tmp_path)

    manifest = validate_agent_candidate(
        candidate,
        version=VERSION,
        source_commit=COMMIT,
        project_root=ROOT,
        source_requirements_lock=ROOT / AGENT_REQUIREMENTS_LOCK,
    )

    assert manifest["wheel"]["name"] == canonical_agent_wheel_name(VERSION)
    assert manifest["wheel"]["wheelTag"] == "py3-none-any"
    assert manifest["wheel"]["entryPoints"] == {
        "careeros": "backend.automation.cli:main",
        "careeros-mcp": "backend.automation.mcp_server:main",
    }
    assert manifest["requirementsLock"]["name"] == AGENT_REQUIREMENTS_LOCK


def test_agent_wheel_record_rejects_changed_runtime_bytes(tmp_path: Path) -> None:
    wheel = write_agent_wheel(tmp_path / "wheel")
    _replace_member(wheel, "backend/automation/cli.py", b"tampered")

    with pytest.raises(RuntimeError, match="RECORD does not bind"):
        validate_agent_wheel(wheel, version=VERSION, project_root=ROOT)


def test_agent_wheel_rejects_private_state_and_unsafe_paths(tmp_path: Path) -> None:
    wheel = write_agent_wheel(tmp_path / "wheel")
    with zipfile.ZipFile(wheel, mode="a") as archive:
        archive.writestr("backend/careeros.db", b"private")

    with pytest.raises(RuntimeError, match="private runtime state"):
        validate_agent_wheel(wheel, version=VERSION, project_root=ROOT)

    wheel = write_agent_wheel(tmp_path / "second")
    with zipfile.ZipFile(wheel, mode="a") as archive:
        archive.writestr("../secret", b"private")
    with pytest.raises(RuntimeError, match="unsafe member path"):
        validate_agent_wheel(wheel, version=VERSION, project_root=ROOT)


@pytest.mark.parametrize(
    "name",
    [
        "backend//ambiguous.py",
        "backend/./ambiguous.py",
        "backend/path/../ambiguous.py",
        "backend/stream:payload.py",
        "backend/control\x1f.py",
        "backend/control\u0085.py",
        "backend/CON.txt",
        "backend/LPT¹.log",
        "backend/trailing.",
        "backend/question?.py",
        "backend/re\u0301sume\u0301.py",
    ],
)
def test_agent_wheel_rejects_non_canonical_portable_names(tmp_path: Path, name: str) -> None:
    wheel = write_agent_wheel(tmp_path / "wheel")
    with zipfile.ZipFile(wheel, mode="a") as archive:
        archive.writestr(name, b"unsafe")

    with pytest.raises(
        RuntimeError,
        match="non-portable|unsafe member path|non-canonical Unicode|Windows-",
    ):
        validate_agent_wheel(wheel, version=VERSION, project_root=ROOT)


def test_agent_wheel_rejects_portable_alias_collisions(tmp_path: Path) -> None:
    wheel = write_agent_wheel(tmp_path / "wheel")
    with zipfile.ZipFile(wheel, mode="a") as archive:
        archive.writestr("BACKEND/AUTOMATION/CLI.PY", b"alias")

    with pytest.raises(RuntimeError, match="portable path collision"):
        validate_agent_wheel(wheel, version=VERSION, project_root=ROOT)

    wheel = write_agent_wheel(tmp_path / "file-directory")
    with zipfile.ZipFile(wheel, mode="a") as archive:
        archive.writestr("backend/automation", b"file shadow")

    with pytest.raises(RuntimeError, match="file/directory path collision"):
        validate_agent_wheel(wheel, version=VERSION, project_root=ROOT)


def test_agent_wheel_rejects_excessive_member_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_distribution, "MAX_AGENT_MEMBERS", 32)
    wheel = write_agent_wheel(tmp_path / "wheel")
    with zipfile.ZipFile(wheel, mode="a") as archive:
        for index in range(32):
            archive.writestr(f"backend/padding/{index}.txt", b"")

    with pytest.raises(RuntimeError, match="too many members"):
        validate_agent_wheel(wheel, version=VERSION, project_root=ROOT)


def test_agent_wheel_rejects_excessive_uncompressed_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_distribution, "MAX_AGENT_TOTAL_UNCOMPRESSED_SIZE", 1_024)
    wheel = write_agent_wheel(tmp_path / "wheel")

    with pytest.raises(RuntimeError, match="uncompressed size limit"):
        validate_agent_wheel(wheel, version=VERSION, project_root=ROOT)


def test_agent_wheel_rejects_suspicious_compression_ratio(tmp_path: Path) -> None:
    wheel = write_agent_wheel(tmp_path / "wheel")
    with zipfile.ZipFile(wheel, mode="a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("backend/compression-bomb.txt", b"0" * (1024 * 1024))

    with pytest.raises(RuntimeError, match="suspiciously compressed member"):
        validate_agent_wheel(wheel, version=VERSION, project_root=ROOT)


def test_agent_candidate_rejects_lock_drift_and_extra_build_output(tmp_path: Path) -> None:
    wheel_root = tmp_path / "wheel"
    write_agent_wheel(wheel_root)
    (wheel_root / "unexpected.tar.gz").write_bytes(b"sdist")
    with pytest.raises(RuntimeError, match="must contain exactly"):
        stage_agent_candidate(
            wheel_root=wheel_root,
            requirements_lock=ROOT / AGENT_REQUIREMENTS_LOCK,
            output=tmp_path / "candidate",
            version=VERSION,
            source_commit=COMMIT,
            project_root=ROOT,
        )

    candidate = write_agent_candidate(tmp_path / "drift")
    (candidate / AGENT_REQUIREMENTS_LOCK).write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="differs from the tagged source"):
        validate_agent_candidate(
            candidate,
            version=VERSION,
            source_commit=COMMIT,
            project_root=ROOT,
            source_requirements_lock=ROOT / AGENT_REQUIREMENTS_LOCK,
        )
