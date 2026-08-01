import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.pre_start import init, main

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_init_success():
    mock_engine = MagicMock()
    with patch("backend.pre_start._runtime_engine", return_value=mock_engine):
        mock_connect = mock_engine.connect
        mock_db = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_db

        # Should not raise
        init()
        mock_db.execute.assert_called_once()


def test_init_failure():
    mock_engine = MagicMock()
    with patch("backend.pre_start._runtime_engine", return_value=mock_engine):
        mock_connect = mock_engine.connect
        mock_connect.side_effect = Exception("DB Down")

        with patch("tenacity.nap.time.sleep", return_value=None):
            from tenacity import RetryError

            with pytest.raises(RetryError) as exc:
                init()
            assert "DB Down" in str(exc.value.last_attempt.exception())


def test_main():
    with (
        patch("backend.pre_start.init") as mock_init,
        patch("backend.pre_start.migrate_schema") as mock_migrate,
    ):
        calls: list[str] = []
        mock_migrate.side_effect = lambda: calls.append("migrate")
        mock_init.side_effect = lambda: calls.append("readiness")
        main()
        assert calls == ["migrate", "readiness"]
        mock_init.assert_called_once()
        mock_migrate.assert_called_once()


def test_migrate_schema_uses_configured_database_and_data_directory(tmp_path, monkeypatch):
    from backend import pre_start

    database = tmp_path / "data" / "careeros.db"
    monkeypatch.setattr(pre_start.settings, "DATABASE_URL", f"sqlite:///{database.as_posix()}")
    monkeypatch.setattr(pre_start.settings, "DATA_DIR", str(tmp_path / "data"))
    with patch("desktop.backend_main.migrate_database") as migrate:
        pre_start.migrate_schema()

    migrate.assert_called_once_with(database.resolve(), (tmp_path / "data" / "backups").resolve())


def _pre_start_environment(data_root: Path, database: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("TESTING", None)
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database.as_posix()}",
            "DATA_DIR": str(data_root),
            "ENVIRONMENT": "development",
            "PYTHONPATH": str(PROJECT_ROOT),
            "SECRET_KEY": "pre-start-import-regression-secret-000000000000000000000000",
        }
    )
    return environment


def test_importing_pre_start_and_base_does_not_create_the_vault_parent(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "private-data"
    database = data_root / "nested" / "vault" / "careeros.db"
    code = (
        "import importlib; "
        "import backend.pre_start as pre_start; "
        "import backend.db.base as database_base; "
        "importlib.reload(database_base); "
        "importlib.reload(pre_start)"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=_pre_start_environment(data_root, database),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert not data_root.exists()


def test_lazy_application_engine_reserves_the_vault_before_its_first_connection(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "private-data"
    database = data_root / "vault" / "careeros.db"
    code = (
        "from pathlib import Path; "
        "from sqlalchemy import text; "
        "from backend.db.base import engine; "
        f"database=Path({str(database)!r}); "
        "assert not database.exists(); "
        "connection=engine.connect(); "
        "connection.execute(text('SELECT 1')); "
        "connection.close(); "
        "engine.dispose(); "
        "assert database.is_file()"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=_pre_start_environment(data_root, database),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert database.is_file()
    if os.name != "nt":
        assert stat.S_IMODE(data_root.stat().st_mode) == 0o700
        assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(database.stat().st_mode) == 0o600


def test_pre_start_refuses_a_hostile_lock_before_database_reservation(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "private-data"
    database = data_root / "vault" / "careeros.db"
    database.parent.mkdir(parents=True)
    lock_path = database.parent / f".{database.name}.migration.lock"
    unrelated = tmp_path / "unrelated-private-file"
    sentinel = b"preserve-this-file"
    unrelated.write_bytes(sentinel)
    os.link(unrelated, lock_path)
    code = (
        "import importlib; "
        "import backend.pre_start as pre_start; "
        "import backend.db.base as database_base; "
        "importlib.reload(database_base); "
        "importlib.reload(pre_start); "
        "pre_start.migrate_schema()"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=_pre_start_environment(data_root, database),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert "Migration lock must be one ordinary local file" in result.stderr
    assert not database.exists()
    assert unrelated.read_bytes() == sentinel
    assert lock_path.read_bytes() == sentinel
