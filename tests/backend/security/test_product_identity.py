from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_product_surfaces_use_only_careeros_identity() -> None:
    product_surfaces = (
        "pyproject.toml",
        "frontend/package.json",
        "frontend/package-lock.json",
        "Dockerfile",
        "docker-compose.yml",
        "alembic.ini",
        ".serena/project.yml",
        "backend/ai/planning.py",
    )
    combined = "\n".join(_text(path) for path in product_surfaces).lower()
    assert "job-hunter-ai" not in combined
    assert "job_hunter" not in combined
    assert "ejupi-djenis30/job-hunter-ai" not in combined
    assert "careeros-local" in combined


def test_runtime_dependencies_have_no_remote_ai_client() -> None:
    dependency_files = ("requirements.txt", "frontend/package.json")
    forbidden = re.compile(r"\b(openai|anthropic|groq|google-generativeai|g4f)\b", re.I)
    for relative in dependency_files:
        assert not forbidden.search(_text(relative)), relative


def test_repository_uses_no_legacy_scratch_directory() -> None:
    checked = (
        ".gitignore",
        ".dockerignore",
        ".github/workflows/ci.yml",
        ".pre-commit-config.yaml",
    )
    for relative in checked:
        assert "cmd_outputs" not in _text(relative), relative
