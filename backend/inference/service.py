import asyncio
import os

from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.inference.catalog import public_catalog
from backend.inference.managed_runtime import (
    ManagedRuntimeSnapshot,
    get_managed_runtime,
)
from backend.providers.llm.factory import get_provider_for_step


class ManagedModelStatus(BaseModel):
    phase: str
    model_key: str | None = None
    bytes_downloaded: int = 0
    bytes_total: int = 0
    runtime_installed: bool = False
    model_installed: bool = False
    ready: bool = False
    endpoint: str | None = None
    error_code: str | None = None

    @classmethod
    def from_snapshot(cls, snapshot: ManagedRuntimeSnapshot) -> "ManagedModelStatus":
        return cls.model_validate(snapshot.as_dict())


class LocalModelStatus(BaseModel):
    available: bool
    ready: bool
    endpoint: str
    configured_model: str
    installed_models: list[str]
    error_code: str | None = None
    runtime: str = "ollama"
    managed: ManagedModelStatus | None = None


class ModelInstallRequest(BaseModel):
    model_key: str = Field(min_length=2, max_length=80)
    license_accepted: bool


class ModelRemovalResult(BaseModel):
    model_files: int
    model_bytes: int
    status: ManagedModelStatus


def get_local_model_catalog() -> dict[str, object]:
    return public_catalog()


def _desktop_mode() -> bool:
    return os.getenv("CAREEROS_DESKTOP_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def get_local_model_status() -> LocalModelStatus:
    """Return a non-sensitive local runtime status; unavailability is not exceptional."""
    manager = get_managed_runtime()
    managed_snapshot = manager.snapshot()
    managed = ManagedModelStatus.from_snapshot(managed_snapshot)
    if managed_snapshot.ready:
        return LocalModelStatus(
            available=True,
            ready=True,
            endpoint=managed_snapshot.endpoint or "",
            configured_model=managed_snapshot.model_key or "",
            installed_models=[managed_snapshot.model_key] if managed_snapshot.model_key else [],
            runtime="llama.cpp",
            managed=managed,
        )
    if _desktop_mode() or managed_snapshot.phase != "idle" or managed_snapshot.model_installed:
        return LocalModelStatus(
            available=managed_snapshot.runtime_installed,
            ready=False,
            endpoint="managed-loopback",
            configured_model=managed_snapshot.model_key or "",
            installed_models=[managed_snapshot.model_key]
            if managed_snapshot.model_installed and managed_snapshot.model_key
            else [],
            error_code=managed_snapshot.error_code
            or (
                "managed_model_setup_required"
                if not managed_snapshot.model_installed
                else "managed_runtime_not_ready"
            ),
            runtime="llama.cpp",
            managed=managed,
        )
    try:
        provider = get_provider_for_step("default")
        installed = await provider.list_models_async()
    except Exception:
        return LocalModelStatus(
            available=False,
            ready=False,
            endpoint=settings.LOCAL_INFERENCE_URL,
            configured_model=settings.LOCAL_MODEL,
            installed_models=[],
            error_code="local_runtime_unreachable",
            managed=managed,
        )

    configured = settings.LOCAL_MODEL
    ready = configured in installed or f"{configured}:latest" in installed
    return LocalModelStatus(
        available=True,
        ready=ready,
        endpoint=settings.LOCAL_INFERENCE_URL,
        configured_model=configured,
        installed_models=installed,
        error_code=None if ready else "configured_model_missing",
        managed=managed,
    )


async def install_managed_model(request: ModelInstallRequest) -> ManagedModelStatus:
    if not request.license_accepted:
        raise ValueError("model license consent is required")
    snapshot = await get_managed_runtime().install(request.model_key)
    return ManagedModelStatus.from_snapshot(snapshot)


async def replace_managed_model(request: ModelInstallRequest) -> ManagedModelStatus:
    if not request.license_accepted:
        raise ValueError("model license consent is required")
    snapshot = await get_managed_runtime().install(request.model_key, replace=True)
    return ManagedModelStatus.from_snapshot(snapshot)


async def cancel_managed_model_install() -> ManagedModelStatus:
    manager = get_managed_runtime()
    manager.cancel_install()
    await manager.wait_for_install()
    manager.discard_partial_downloads()
    return ManagedModelStatus.from_snapshot(manager.snapshot())


def pause_managed_model_install() -> ManagedModelStatus:
    return ManagedModelStatus.from_snapshot(get_managed_runtime().pause_install())


async def resume_managed_model_install() -> ManagedModelStatus:
    snapshot = await get_managed_runtime().resume_install()
    return ManagedModelStatus.from_snapshot(snapshot)


async def remove_managed_model() -> ModelRemovalResult:
    manager = get_managed_runtime()
    manager.cancel_install()
    await manager.wait_for_install()
    removed = await asyncio.to_thread(manager.erase_installation)
    return ModelRemovalResult(
        **removed,
        status=ManagedModelStatus.from_snapshot(manager.snapshot()),
    )


async def restart_managed_model() -> ManagedModelStatus:
    snapshot = await asyncio.to_thread(get_managed_runtime().restart)
    return ManagedModelStatus.from_snapshot(snapshot)
