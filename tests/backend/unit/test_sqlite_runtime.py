from unittest.mock import MagicMock

from backend.db.base import configure_sqlite_connection


def test_sqlite_connections_enable_local_durability_pragmas():
    connection = MagicMock()
    cursor = connection.cursor.return_value

    configure_sqlite_connection(connection, None)

    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert "PRAGMA foreign_keys=ON" in statements
    assert "PRAGMA secure_delete=ON" in statements
    assert "PRAGMA journal_mode=WAL" in statements
    assert "PRAGMA busy_timeout=5000" in statements
    cursor.close.assert_called_once_with()
