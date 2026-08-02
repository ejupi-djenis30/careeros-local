# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller graph for the CareerOS Local backend sidecar."""

# PyInstaller injects SPECPATH and its build primitives while evaluating specs.
# ruff: noqa: F821

import os
import stat
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

PROJECT_ROOT = Path(SPECPATH).resolve().parent
MODE = os.environ.get("CAREEROS_PYINSTALLER_MODE", "onedir").strip().lower()
if MODE not in {"onedir", "onefile"}:
    raise ValueError("CAREEROS_PYINSTALLER_MODE must be onedir or onefile")


def is_link_like(path):
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def collect_project_files(source_root, destination_root):
    """Collect source-controlled runtime data without interpreter caches."""
    source_root = Path(source_root)
    if is_link_like(source_root) or not source_root.is_dir():
        raise ValueError(f"Runtime data root must be a regular directory: {source_root}")
    resolved_root = source_root.resolve(strict=True)
    collected = []
    for source in source_root.rglob("*"):
        if is_link_like(source):
            raise ValueError(f"Runtime data must not contain links or junctions: {source}")
        if not source.is_file():
            continue
        if not source.resolve(strict=True).is_relative_to(resolved_root):
            raise ValueError(f"Runtime data escapes its source root: {source}")
        relative = source.relative_to(source_root)
        if "__pycache__" in relative.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        destination = Path(destination_root) / relative.parent
        collected.append((str(source), str(destination)))
    return collected


datas = [
    (str(PROJECT_ROOT / "backend" / "inference" / "model_catalog.json"), "backend/inference"),
    (str(PROJECT_ROOT / "backend" / "inference" / "model_catalog.sha256"), "backend/inference"),
    (str(PROJECT_ROOT / "backend" / "ai" / "fixtures"), "backend/ai/fixtures"),
]
datas += collect_project_files(PROJECT_ROOT / "backend" / "migrations", "backend/migrations")
datas += collect_project_files(PROJECT_ROOT / "backend" / "data", "backend/data")
datas += collect_project_files(
    PROJECT_ROOT / "backend" / "providers" / "configuration" / "packs",
    "backend/providers/configuration/packs",
)
for package in ("alembic", "docx", "reportlab"):
    datas += collect_data_files(package)
for distribution in ("alembic", "fastapi", "pydantic", "uvicorn"):
    datas += copy_metadata(distribution)

hidden_imports = sorted(
    set(
        collect_submodules("backend")
        + collect_submodules("uvicorn")
        + [
            "apscheduler.triggers.cron",
            "apscheduler.triggers.date",
            "apscheduler.triggers.interval",
            "greenlet",
            "multipart",
            "sqlite3",
        ]
    )
)

analysis = Analysis(
    [str(PROJECT_ROOT / "desktop" / "backend_main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "MySQLdb",
        "anthropic",
        "fitz",
        "g4f",
        "google.generativeai",
        "groq",
        "mypy",
        "openai",
        "psycopg2",
        "pymupdf",
        "pymysql",
        "pytest",
        "ruff",
        "supabase",
        "tkinter",
        "watchfiles",
    ],
    noarchive=False,
    optimize=1,
)
python_archive = PYZ(analysis.pure)
console = os.environ.get("CAREEROS_SIDECAR_CONSOLE", "0") == "1"

if MODE == "onefile":
    executable = EXE(
        python_archive,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name="careeros-backend",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    executable = EXE(
        python_archive,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name="careeros-backend",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    bundle = COLLECT(
        executable,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name="careeros-backend",
    )
