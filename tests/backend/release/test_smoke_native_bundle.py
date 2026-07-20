from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import smoke_native_bundle


def _macos_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    bundle = tmp_path / "bundle"
    (bundle / "macos" / "CareerOS Local.app").mkdir(parents=True)
    dmg = bundle / "dmg" / "CareerOS Local.dmg"
    dmg.parent.mkdir()
    dmg.write_bytes(b"dmg-bytes")
    smoke = tmp_path / "smoke"
    smoke.mkdir()
    return bundle, dmg, smoke


def _populate_mounted_app(command: list[str]) -> Path:
    mount_point = Path(command[command.index("-mountpoint") + 1])
    app = mount_point / "CareerOS Local.app"
    executable = app / "Contents" / "MacOS" / "careeros-local"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"application")
    sidecar = app / "Contents" / "Resources" / "careeros-backend"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_bytes(b"backend")
    return app


def test_macos_verifies_and_exercises_the_mounted_dmg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, dmg, smoke = _macos_bundle(tmp_path)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[:2] == ["hdiutil", "attach"]:
            _populate_mounted_app(command)
        return subprocess.CompletedProcess(command, 0)

    exercised: dict[str, Path] = {}
    monkeypatch.setattr(smoke_native_bundle.subprocess, "run", fake_run)
    monkeypatch.setattr(
        smoke_native_bundle,
        "_run_export_smoke",
        lambda sidecar, _: exercised.setdefault("sidecar", sidecar),
    )
    monkeypatch.setattr(
        smoke_native_bundle,
        "_run_reopen",
        lambda command, _: exercised.setdefault("executable", Path(command[0])),
    )

    assert smoke_native_bundle._macos(bundle, smoke) == 1

    assert commands[0] == ["hdiutil", "verify", str(dmg)]
    assert commands[1][:2] == ["hdiutil", "attach"]
    assert commands[1][-1] == str(dmg)
    assert "-readonly" in commands[1]
    assert commands[-1] == ["hdiutil", "detach", str(smoke / "dmg-mount")]
    assert smoke / "dmg-mount" in exercised["sidecar"].parents
    assert smoke / "dmg-mount" in exercised["executable"].parents


def test_macos_always_detaches_when_mounted_package_smoke_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, _, smoke = _macos_bundle(tmp_path)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[:2] == ["hdiutil", "attach"]:
            _populate_mounted_app(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(smoke_native_bundle.subprocess, "run", fake_run)
    monkeypatch.setattr(
        smoke_native_bundle,
        "_run_export_smoke",
        lambda *_: (_ for _ in ()).throw(RuntimeError("mounted smoke failed")),
    )

    with pytest.raises(RuntimeError, match="mounted smoke failed"):
        smoke_native_bundle._macos(bundle, smoke)

    assert commands[-1] == ["hdiutil", "detach", str(smoke / "dmg-mount")]
