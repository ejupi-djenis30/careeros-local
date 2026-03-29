from unittest.mock import MagicMock, patch

import pytest

from backend.pre_start import init, main


def test_init_success():
    with patch("backend.pre_start.engine.connect") as mock_connect:
        mock_db = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_db

        # Should not raise
        init()
        mock_db.execute.assert_called_once()


def test_init_failure():
    with patch("backend.pre_start.engine.connect") as mock_connect:
        mock_connect.side_effect = Exception("DB Down")

        with patch("tenacity.nap.time.sleep", return_value=None):
            from tenacity import RetryError

            with pytest.raises(RetryError) as exc:
                init()
            assert "DB Down" in str(exc.value.last_attempt.exception())


def test_main():
    with patch("backend.pre_start.init") as mock_init:
        main()
        mock_init.assert_called_once()
