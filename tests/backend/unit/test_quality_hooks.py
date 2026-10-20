import os
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import run_frontend_lint

ROOT = Path(__file__).resolve().parents[3]


def test_python_hooks_run_the_same_source_checks_as_ci_in_the_locked_environment():
    configuration = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = {
        hook["id"]: hook
        for repository in configuration["repos"]
        for hook in repository["hooks"]
        if hook["id"] in {"ruff", "mypy"}
    }
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = {step["name"]: step for step in workflow["jobs"]["backend"]["steps"]}

    for hook_id, step_name in (("ruff", "Lint"), ("mypy", "Type-check")):
        hook = hooks[hook_id]
        command = shlex.split(hook["entry"])
        assert command[:2] == ["python", "-m"]
        assert command[2:] == shlex.split(steps[step_name]["run"])
        assert hook["language"] == "system"
        assert hook["pass_filenames"] is False
        assert "additional_dependencies" not in hook


def test_frontend_hook_uses_the_preflight_runner_without_installing_dependencies():
    configuration = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hook = next(
        hook
        for repository in configuration["repos"]
        for hook in repository["hooks"]
        if hook["id"] == "frontend-lint"
    )
    assert shlex.split(hook["entry"]) == ["python", "scripts/run_frontend_lint.py"]
    assert hook["language"] == "system"
    assert hook["pass_filenames"] is False


def test_missing_frontend_dependencies_fail_without_running_a_package_manager(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_frontend_lint, "FRONTEND", tmp_path)
    calls = []
    monkeypatch.setattr(
        run_frontend_lint.subprocess, "run", lambda *args, **kwargs: calls.append(args)
    )

    with pytest.raises(RuntimeError, match="npm ci --ignore-scripts --prefix frontend"):
        run_frontend_lint.main()

    assert calls == []


@pytest.fixture
def installed_frontend(tmp_path, monkeypatch):
    executable = (
        tmp_path / "node_modules" / ".bin" / ("eslint.cmd" if os.name == "nt" else "eslint")
    )
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(run_frontend_lint, "FRONTEND", tmp_path)
    return tmp_path


def test_frontend_lint_preserves_npm_node_preflight(installed_frontend, monkeypatch):
    monkeypatch.setattr(run_frontend_lint.shutil, "which", lambda name: "installed-npm")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_frontend_lint.subprocess, "run", run)

    assert run_frontend_lint.main() == 0

    assert calls == [(["installed-npm", "run", "lint"], {"cwd": installed_frontend, "check": True})]


def test_missing_npm_reports_the_explicit_runtime_setup(installed_frontend, monkeypatch):
    monkeypatch.setattr(run_frontend_lint.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="Install the Node version in .nvmrc"):
        run_frontend_lint.main()
