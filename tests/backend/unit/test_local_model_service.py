from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.inference.managed_runtime import ManagedRuntimeSnapshot
from backend.inference.service import get_local_model_status


def _idle_managed_runtime() -> MagicMock:
    manager = MagicMock()
    manager.snapshot.return_value = ManagedRuntimeSnapshot(
        phase="idle",
        model_key=None,
        bytes_downloaded=0,
        bytes_total=0,
        runtime_installed=False,
        model_installed=False,
        ready=False,
        endpoint=None,
        error_code=None,
    )
    return manager


@pytest.mark.asyncio
async def test_local_model_status_reports_ready_installed_model():
    provider = MagicMock()
    provider.list_models_async = AsyncMock(return_value=["qwen3:1.7b", "nomic-embed-text"])
    with (
        patch(
            "backend.inference.service.get_managed_runtime",
            return_value=_idle_managed_runtime(),
        ),
        patch("backend.inference.service._desktop_mode", return_value=False),
        patch("backend.inference.service.get_provider_for_step", return_value=provider),
    ):
        status = await get_local_model_status()

    assert status.available is True
    assert status.ready is True
    assert status.error_code is None
    assert status.runtime == "ollama"


@pytest.mark.asyncio
async def test_local_model_status_degrades_when_runtime_is_offline():
    with (
        patch(
            "backend.inference.service.get_managed_runtime",
            return_value=_idle_managed_runtime(),
        ),
        patch("backend.inference.service._desktop_mode", return_value=False),
        patch(
            "backend.inference.service.get_provider_for_step",
            side_effect=ConnectionError("private detail must not leak"),
        ),
    ):
        status = await get_local_model_status()

    assert status.available is False
    assert status.ready is False
    assert status.error_code == "local_runtime_unreachable"
    assert "private detail" not in status.model_dump_json()
