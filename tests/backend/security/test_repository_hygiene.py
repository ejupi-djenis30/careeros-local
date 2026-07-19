import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRUNED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "coverage",
    "binaries",
    "dist",
    "htmlcov",
    "node_modules",
    "target",
}
FORBIDDEN_OUTPUT_DIRECTORIES = {
    "cmd_outputs",
    "command_outputs",
    "command-output",
}
APPROVED_MARKDOWN = {
    Path("AGENTS.md"),
    Path("CHANGELOG.md"),
    Path("CODE_OF_CONDUCT.md"),
    Path("CONTRIBUTING.md"),
    Path("README.md"),
    Path("SECURITY.md"),
    Path("SUPPORT.md"),
    Path(".github/pull_request_template.md"),
    Path("backend/README.md"),
    Path("frontend/README.md"),
    Path("docs/architecture.md"),
    Path("docs/brand.md"),
    Path("docs/development.md"),
    Path("docs/demo.md"),
    Path("docs/devpost.md"),
    Path("docs/privacy.md"),
    Path("docs/releasing.md"),
}
APPROVED_MARKDOWN_ROOTS = {
    Path(".agents/skills"),
    Path(".specify"),
    Path("specs"),
}


def _source_files():
    for directory, subdirectories, filenames in os.walk(ROOT):
        subdirectories[:] = [
            name
            for name in subdirectories
            if name not in PRUNED_DIRECTORIES and name not in {"data", ".artifacts", ".build"}
        ]
        current = Path(directory)
        for filename in filenames:
            yield current / filename


def test_command_output_directories_do_not_exist():
    offenders = []
    for directory, subdirectories, _filenames in os.walk(ROOT):
        subdirectories[:] = [name for name in subdirectories if name not in PRUNED_DIRECTORIES]
        for name in subdirectories:
            if name.casefold() in FORBIDDEN_OUTPUT_DIRECTORIES:
                offenders.append((Path(directory) / name).relative_to(ROOT).as_posix())
    assert offenders == []


def test_markdown_inventory_contains_only_product_spec_and_tooling_docs():
    offenders = []
    for path in _source_files():
        if path.suffix.casefold() != ".md":
            continue
        relative = path.relative_to(ROOT)
        allowed_by_root = any(relative.is_relative_to(root) for root in APPROVED_MARKDOWN_ROOTS)
        if relative not in APPROVED_MARKDOWN and not allowed_by_root:
            offenders.append(relative.as_posix())
    assert offenders == []
    assert all((ROOT / path).is_file() for path in APPROVED_MARKDOWN)


def test_no_command_logs_or_temporary_dumps_are_source_files():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _source_files()
        if path.suffix.casefold() in {".log", ".out", ".tmp"}
    ]
    assert offenders == []


def test_portfolio_demo_assets_are_present_and_github_sized():
    assets = ROOT / "docs/assets"
    screenshots = (
        assets / "careeros-workspace.png",
        assets / "careeros-vault.png",
        assets / "careeros-resume-studio.png",
        assets / "careeros-applications.png",
    )
    for screenshot in screenshots:
        assert screenshot.is_file()
        assert 10_000 < screenshot.stat().st_size < 2 * 1024 * 1024

    video = assets / "careeros-demo.webm"
    assert video.is_file()
    assert 100_000 < video.stat().st_size < 10 * 1024 * 1024
    assert (assets / "careeros-demo-poster.jpg").is_file()
    assert (assets / "careeros-demo.gif").is_file()


def test_release_workflow_uploads_each_native_extension_explicitly():
    workflow = (ROOT / ".github/workflows/desktop-release.yml").read_text(encoding="utf-8")

    assert "artifact_pattern" not in workflow
    assert "**/*.{" not in workflow
    for extension in ("exe", "msi", "dmg", "AppImage", "deb"):
        assert f"release/bundle/**/*.{extension}" in workflow
    assert "name: verified-release-assets" in workflow
    assert "needs: assemble-release" in workflow


def test_security_exception_manifest_is_scoped_and_expiry_is_enforced():
    manifest = json.loads((ROOT / "security-exceptions.json").read_text(encoding="utf-8"))
    assert manifest == {
        "exceptions": [
            {
                "id": "CE-2026-001",
                "advisory": "RUSTSEC-2024-0429",
                "dependency": "glib",
                "version": "0.18.5",
                "cargo_lock": "frontend/src-tauri/Cargo.lock",
                "scope": "linux-desktop-transitive",
                "expires": "2026-10-19",
            }
        ]
    }

    checker = ROOT / "scripts/check_security_exceptions.py"
    before_expiry = subprocess.run(
        [sys.executable, str(checker), "--today", "2026-10-18"],
        capture_output=True,
        check=False,
        text=True,
    )
    at_expiry = subprocess.run(
        [sys.executable, str(checker), "--today", "2026-10-19"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert before_expiry.returncode == 0
    assert at_expiry.returncode == 1
    assert "CE-2026-001 expired on 2026-10-19" in at_expiry.stdout


def test_cargo_audit_exception_is_narrow_and_evidence_is_uploaded():
    workflows = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (".github/workflows/ci.yml", ".github/workflows/desktop-release.yml")
    )
    scoped_command = "cargo audit --deny unsound --ignore RUSTSEC-2024-0429"
    assert workflows.count(scoped_command) == 2
    assert workflows.count("scripts/check_security_exceptions.py") == 2
    assert workflows.count("cargo-exception-tree.txt") >= 3


def test_legacy_service_facades_stay_thin():
    facades = (
        ROOT / "backend/services/llm_service.py",
        ROOT / "backend/services/search_service.py",
        ROOT / "backend/services/search/listing_utils.py",
    )
    for facade in facades:
        assert len(facade.read_text(encoding="utf-8").splitlines()) < 300
