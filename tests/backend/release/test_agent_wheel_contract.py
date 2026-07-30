from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _direct_requirements() -> list[str]:
    return [
        line.strip()
        for line in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_wheel_metadata_matches_the_reviewed_production_dependency_inputs() -> None:
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert sorted(metadata["project"]["dependencies"], key=str.casefold) == sorted(
        _direct_requirements(), key=str.casefold
    )


def test_ci_runs_the_clean_environment_wheel_smoke() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "python scripts/smoke_agent_wheel.py" in workflow
    assert "--build-wheel" in workflow
    assert "--requirements-lock requirements.lock" in workflow
    for required_runner in ("ubuntu-24.04", "windows-2025", "macos-15"):
        assert required_runner in workflow
    assert 'python: "3.13"' in workflow


def test_user_install_path_keeps_runtime_dependencies_hash_locked() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert readme.count("--require-hashes") >= 5
    assert readme.count("--no-deps") >= 5
    assert "requirements.lock" in readme


def test_local_wheel_build_directory_is_ignored() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".wheel-build/" in gitignore
