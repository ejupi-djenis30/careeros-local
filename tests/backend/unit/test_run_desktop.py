import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import run_desktop

TARGET = "aarch64-pc-windows-msvc"


@pytest.fixture
def desktop_commands(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    cli = frontend / "node_modules" / ".bin" / (
        "tauri.cmd" if os.name == "nt" else "tauri"
    )
    cli.parent.mkdir(parents=True)
    cli.write_text("installed CLI", encoding="utf-8")
    manifest = frontend / "sidecar-build.json"
    python = tmp_path / "sidecar-python"
    calls = []
    state = {"installed": TARGET, "prepared": TARGET, "sidecar_error": False}

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:2] == [str(python), "-c"]:
            return subprocess.CompletedProcess(command, 0, stdout=TARGET + "\n")
        if command == ["installed-rustup", "target", "list", "--installed"]:
            return subprocess.CompletedProcess(command, 0, stdout=state["installed"] + "\n")
        if command == [str(python), str(tmp_path / "scripts" / "build_backend_sidecar.py")]:
            if state["sidecar_error"]:
                raise subprocess.CalledProcessError(1, command)
            manifest.write_text(json.dumps({"target": state["prepared"]}), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)
        assert command[0] == str(cli), "The wrapper must use only installed local commands"
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_desktop, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(run_desktop, "FRONTEND", frontend)
    monkeypatch.setattr(run_desktop, "MANIFEST", manifest)
    monkeypatch.setattr(run_desktop, "workspace_python", lambda: python)
    monkeypatch.setattr(run_desktop.shutil, "which", lambda name: "installed-rustup")
    monkeypatch.setattr(run_desktop.subprocess, "run", run)
    return cli, python, calls, state


@pytest.mark.parametrize("debug", [False, True])
def test_build_uses_local_cli_and_forwards_locked_after_tauri_options(
    desktop_commands, monkeypatch, debug
):
    cli, python, calls, _state = desktop_commands
    arguments = ["run_desktop.py", "build"] + (["--debug"] if debug else [])
    monkeypatch.setattr(sys, "argv", arguments)

    assert run_desktop.main() == 0

    expected = [str(cli), "build", "--target", TARGET]
    if debug:
        expected.append("--debug")
    expected.extend(["--", "--locked"])
    assert calls[-1][0] == expected
    assert calls[0][0][:2] == [str(python), "-c"]
    assert calls[1][0] == ["installed-rustup", "target", "list", "--installed"]
    assert calls[2][0][0] == str(python)
    assert all(options["check"] for _command, options in calls)


def test_dev_uses_installed_cli_and_checks_target_without_provisioning(
    desktop_commands, monkeypatch
):
    cli, _python, calls, _state = desktop_commands
    monkeypatch.setattr(sys, "argv", ["run_desktop.py", "dev"])

    assert run_desktop.main() == 0

    assert calls[-1][0] == [str(cli), "dev", "--target", TARGET]
    assert calls[1][0] == ["installed-rustup", "target", "list", "--installed"]


def test_missing_cli_fails_before_any_build_command(desktop_commands, monkeypatch):
    cli, _python, calls, _state = desktop_commands
    cli.unlink()
    monkeypatch.setattr(sys, "argv", ["run_desktop.py", "build"])

    with pytest.raises(RuntimeError, match="npm ci --ignore-scripts --prefix frontend"):
        run_desktop.main()

    assert calls == []


def test_missing_rust_target_fails_before_sidecar_build(desktop_commands, monkeypatch):
    _cli, _python, calls, state = desktop_commands
    state["installed"] = "x86_64-pc-windows-msvc"
    monkeypatch.setattr(sys, "argv", ["run_desktop.py", "build"])

    with pytest.raises(RuntimeError, match=f"rustup target add {TARGET}"):
        run_desktop.main()

    assert len(calls) == 2


def test_missing_rustup_fails_without_provisioning(desktop_commands, monkeypatch):
    _cli, _python, calls, _state = desktop_commands
    monkeypatch.setattr(sys, "argv", ["run_desktop.py", "build"])
    monkeypatch.setattr(run_desktop.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="Rust/Tauri prerequisites"):
        run_desktop.main()

    assert len(calls) == 1


def test_changed_sidecar_target_is_rejected(desktop_commands, monkeypatch):
    _cli, _python, calls, state = desktop_commands
    state["prepared"] = "x86_64-pc-windows-msvc"
    monkeypatch.setattr(sys, "argv", ["run_desktop.py", "build"])

    with pytest.raises(RuntimeError, match="prepared sidecar target differs"):
        run_desktop.main()

    assert len(calls) == 3


def test_sidecar_failure_does_not_launch_tauri(desktop_commands, monkeypatch):
    _cli, _python, calls, state = desktop_commands
    state["sidecar_error"] = True
    monkeypatch.setattr(sys, "argv", ["run_desktop.py", "build"])

    with pytest.raises(subprocess.CalledProcessError):
        run_desktop.main()

    assert len(calls) == 3


def test_workspace_python_prefers_the_repository_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(run_desktop, "PROJECT_ROOT", tmp_path)
    assert run_desktop.workspace_python() == Path(sys.executable)
    relative = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    python = tmp_path / ".venv" / relative
    python.parent.mkdir(parents=True)
    python.touch()

    assert run_desktop.workspace_python() == python
