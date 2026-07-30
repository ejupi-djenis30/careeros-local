"""Install a CareerOS wheel into a clean venv and exercise its agent boundary."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterator, Sequence, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def _temporary_work_root(prefix: str) -> Iterator[Path]:
    work_root = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    try:
        yield work_root
    finally:
        for attempt in range(8):
            try:
                shutil.rmtree(work_root)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.25 * (attempt + 1))


def _run(
    arguments: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [os.fspath(item) for item in arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        command = " ".join(Path(os.fspath(item)).name for item in arguments)
        raise RuntimeError(
            f"Wheel smoke command failed ({command}):\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed


def _venv_executable(venv_root: Path, name: str) -> Path:
    scripts = venv_root / ("Scripts" if os.name == "nt" else "bin")
    suffix = ".exe" if os.name == "nt" else ""
    return scripts / f"{name}{suffix}"


def _clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "CAREEROS_DESKTOP_MODE",
        "CAREEROS_DESKTOP_DATA_DIR",
        "CAREEROS_MCP_TOKEN",
        "CAREEROS_SECRET_FILE",
        "DATABASE_URL",
        "DATA_DIR",
        "ENVIRONMENT",
        "PYTHONHOME",
        "PYTHONPATH",
        "SECRET_KEY",
        "TESTING",
    ):
        environment.pop(name, None)
    environment.update({"PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1"})
    return environment


def _doctor_smoke(
    executable: Path,
    *,
    work_root: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    data_dir = (work_root / "empty-doctor-vault").resolve()
    data_dir.mkdir()
    completed = _run(
        [executable, "--data-dir", data_dir, "doctor"],
        cwd=work_root,
        environment=environment,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("Doctor did not return a JSON object")
    if payload.get("ready") is not False:
        raise RuntimeError("Doctor incorrectly reported an empty synthetic vault as ready")
    codes = payload.get("diagnostic_codes")
    if not isinstance(codes, list) or "vault_not_found" not in codes:
        raise RuntimeError("Doctor did not report the synthetic vault as missing")
    return cast(dict[str, Any], payload)


async def _mcp_smoke(data_dir: Path, executable: Path) -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    vault = data_dir / "vault"
    vault.mkdir(parents=True)
    secret_path = vault / ".installation-secret"
    secret_path.write_text(
        "wheel-smoke-installation-secret-that-never-leaves-the-temp-directory",
        encoding="utf-8",
    )
    database_path = vault / "careeros.db"
    environment = _clean_environment()
    environment.update(
        {
            "CAREEROS_DESKTOP_DATA_DIR": str(data_dir),
            "CAREEROS_SECRET_FILE": str(secret_path),
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "DATA_DIR": str(data_dir),
            "ENVIRONMENT": "production",
            "SECRET_KEY": secret_path.read_text(encoding="utf-8"),
        }
    )
    os.environ.update(environment)

    from backend.ai.evaluation import load_dataset
    from backend.automation.grants import issue_grant
    from backend.db.base import SessionLocal, engine
    from backend.inference.catalog import load_model_catalog
    from backend.models import User
    from desktop.backend_main import migrate_database

    if not load_model_catalog().models:
        raise RuntimeError("Installed wheel model catalog is empty")
    if not load_dataset().cases:
        raise RuntimeError("Installed wheel evaluation fixture is empty")
    taxonomy = json.loads(
        files("backend.data").joinpath("skill_taxonomy.json").read_text(encoding="utf-8")
    )
    if not isinstance(taxonomy, dict) or not taxonomy.get("skills"):
        raise RuntimeError("Installed wheel skill taxonomy is empty")

    migrate_database(database_path, data_dir / "backups")
    with SessionLocal() as database:
        user = User(username="wheel-smoke", hashed_password="not-used-by-the-smoke")
        database.add(user)
        database.commit()
        database.refresh(user)
        _, token = issue_grant(
            database,
            user_id=user.id,
            label="Isolated wheel smoke",
            scopes=("system:read",),
        )
    engine.dispose()

    server_environment = environment.copy()
    server_environment["CAREEROS_MCP_TOKEN"] = token
    parameters = StdioServerParameters(
        command=str(executable),
        args=[
            "--data-dir",
            str(data_dir),
            "mcp",
            "serve",
            "--acknowledge-agent-disclosure",
        ],
        cwd=data_dir,
        env=server_environment,
    )
    diagnostics_path = data_dir / "mcp-stderr.log"
    with diagnostics_path.open("w+", encoding="utf-8") as diagnostics:
        async with stdio_client(parameters, errlog=diagnostics) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                response = await session.list_tools()
        diagnostics.seek(0)
        stderr = diagnostics.read()
    if token in stderr or str(data_dir) in stderr:
        raise RuntimeError("MCP diagnostics exposed a token or synthetic vault path")
    names = sorted(tool.name for tool in response.tools)
    if names != ["get_local_model_status", "get_status"]:
        raise RuntimeError(f"Unexpected MCP tool surface in wheel smoke: {names}")
    return names


def _verify_installed(arguments: argparse.Namespace) -> int:
    data_dir = Path(arguments.data_dir).resolve()
    executable = Path(arguments.careeros_executable).resolve()
    names = asyncio.run(_mcp_smoke(data_dir, executable))
    print(json.dumps({"mcp_initialize": "ok", "tools": names}, sort_keys=True))
    return 0


def _smoke_wheel(arguments: argparse.Namespace) -> int:
    wheel = Path(arguments.wheel).resolve()
    requirements_lock = Path(arguments.requirements_lock).resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError("--wheel must reference one built wheel")
    if not requirements_lock.is_file():
        raise ValueError("--requirements-lock must reference the production lock")

    with _temporary_work_root("careeros-agent-wheel-") as work_root:
        venv_root = work_root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(venv_root)
        python = _venv_executable(venv_root, "python")
        care_cli = _venv_executable(venv_root, "careeros")
        mcp_cli = _venv_executable(venv_root, "careeros-mcp")
        environment = _clean_environment()

        _run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--require-hashes",
                "--requirement",
                requirements_lock,
            ],
            cwd=work_root,
            environment=environment,
            timeout=900,
        )
        _run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                wheel,
            ],
            cwd=work_root,
            environment=environment,
        )
        _run([python, "-m", "pip", "check"], cwd=work_root, environment=environment)
        _run([care_cli, "--help"], cwd=work_root, environment=environment)
        _run([mcp_cli, "--help"], cwd=work_root, environment=environment)
        doctor = _doctor_smoke(care_cli, work_root=work_root, environment=environment)
        protocol = _run(
            [
                python,
                Path(__file__).resolve(),
                "--verify-installed",
                "--data-dir",
                work_root / "mcp-vault",
                "--careeros-executable",
                care_cli,
            ],
            cwd=work_root,
            environment=environment,
        )
        print(
            json.dumps(
                {
                    "doctor_codes": doctor["diagnostic_codes"],
                    "mcp": json.loads(protocol.stdout),
                    "pip_check": "ok",
                    "wheel": wheel.name,
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


def _build_and_smoke(arguments: argparse.Namespace) -> int:
    with _temporary_work_root("careeros-agent-build-") as build_root:
        wheel_directory = build_root / "wheel"
        wheel_directory.mkdir()
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-build-isolation",
                "--no-deps",
                "--wheel-dir",
                wheel_directory,
                PROJECT_ROOT,
            ],
            cwd=PROJECT_ROOT,
            environment=_clean_environment(),
            timeout=900,
        )
        wheels = list(wheel_directory.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(
                f"Expected exactly one CareerOS wheel, found {[wheel.name for wheel in wheels]}"
            )
        arguments.wheel = str(wheels[0])
        return _smoke_wheel(arguments)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install and smoke-test the CareerOS CLI/MCP wheel in a clean venv"
    )
    parser.add_argument("--wheel")
    parser.add_argument(
        "--build-wheel",
        action="store_true",
        help="Build the current project before running the isolated wheel smoke",
    )
    parser.add_argument(
        "--requirements-lock",
        default=str(PROJECT_ROOT / "requirements.lock"),
    )
    parser.add_argument("--verify-installed", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--data-dir", help=argparse.SUPPRESS)
    parser.add_argument("--careeros-executable", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.verify_installed:
        if not arguments.data_dir or not arguments.careeros_executable:
            raise ValueError("Installed verification requires its isolated data directory and CLI")
        return _verify_installed(arguments)
    if arguments.build_wheel:
        if arguments.wheel:
            raise ValueError("--build-wheel and --wheel are mutually exclusive")
        return _build_and_smoke(arguments)
    if not arguments.wheel:
        raise ValueError("--wheel is required")
    return _smoke_wheel(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
