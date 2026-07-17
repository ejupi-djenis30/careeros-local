# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller graph for the CareerOS Local backend sidecar."""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


PROJECT_ROOT = Path(SPECPATH).resolve().parent
MODE = os.environ.get("CAREEROS_PYINSTALLER_MODE", "onedir").strip().lower()
if MODE not in {"onedir", "onefile"}:
    raise ValueError("CAREEROS_PYINSTALLER_MODE must be onedir or onefile")


def collect_project_files(source_root, destination_root):
    """Collect source-controlled runtime data without interpreter caches."""
    collected = []
    for source in source_root.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(source_root)
        if "__pycache__" in relative.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        destination = Path(destination_root) / relative.parent
        collected.append((str(source), str(destination)))
    return collected


datas = [
    (str(PROJECT_ROOT / "alembic.ini"), "."),
    (str(PROJECT_ROOT / "backend" / "inference" / "model_catalog.json"), "backend/inference"),
    (str(PROJECT_ROOT / "backend" / "inference" / "model_catalog.sha256"), "backend/inference"),
    (str(PROJECT_ROOT / "backend" / "ai" / "fixtures"), "backend/ai/fixtures"),
]
datas += collect_project_files(PROJECT_ROOT / "alembic", "alembic")
datas += collect_project_files(PROJECT_ROOT / "backend" / "data", "backend/data")
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
