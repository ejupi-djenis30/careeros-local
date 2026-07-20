from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import smoke_native_bundle
from scripts.license_contract import approved_license_bytes


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
    (app / "Contents" / "Resources" / "LICENSE").write_bytes(approved_license_bytes())
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


def test_macos_rejects_tampered_license_and_still_detaches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, _, smoke = _macos_bundle(tmp_path)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[:2] == ["hdiutil", "attach"]:
            app = _populate_mounted_app(command)
            (app / "Contents" / "Resources" / "LICENSE").write_bytes(b"tampered\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(smoke_native_bundle.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="license verification failed"):
        smoke_native_bundle._macos(bundle, smoke)

    assert commands[-1] == ["hdiutil", "detach", str(smoke / "dmg-mount")]


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


def test_linux_verifies_licenses_in_extracted_appimage_and_deb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    appimage = bundle / "appimage" / "CareerOS.AppImage"
    deb = bundle / "deb" / "careeros.deb"
    appimage.parent.mkdir(parents=True)
    deb.parent.mkdir(parents=True)
    appimage.write_bytes(b"appimage")
    deb.write_bytes(b"deb")
    smoke = tmp_path / "smoke"
    smoke.mkdir()
    commands: list[list[str]] = []

    def populate(root: Path) -> None:
        resources = root / "usr" / "lib" / "careeros-local"
        resources.mkdir(parents=True)
        (resources / "LICENSE").write_bytes(approved_license_bytes())
        runtime = resources / "careeros-backend-runtime"
        runtime.mkdir()
        (runtime / "careeros-backend").write_bytes(b"backend")
        executable = root / "usr" / "bin" / "careeros-local"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"application")

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[-1] == "--appimage-extract":
            populate(Path(kwargs["cwd"]) / "squashfs-root")
        elif command[:2] == ["dpkg-deb", "-x"]:
            populate(Path(command[-1]))
        return subprocess.CompletedProcess(command, 0)

    exercised: list[Path] = []
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setattr(smoke_native_bundle.subprocess, "run", fake_run)
    monkeypatch.setattr(
        smoke_native_bundle, "_run_export_smoke", lambda sidecar, _: exercised.append(sidecar)
    )
    monkeypatch.setattr(smoke_native_bundle, "_run_reopen", lambda *_: None)

    assert smoke_native_bundle._linux(bundle, smoke) == 2
    assert len(exercised) == 2
    assert commands[0][-1] == "--appimage-extract"
    assert commands[1][:2] == ["dpkg-deb", "-x"]
