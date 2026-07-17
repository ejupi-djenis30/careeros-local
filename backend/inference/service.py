from pydantic import BaseModel

from backend.core.config import settings
from backend.providers.llm.factory import get_provider_for_step


class LocalModelStatus(BaseModel):
    available: bool
    ready: bool
    endpoint: str
    configured_model: str
    installed_models: list[str]
    error_code: str | None = None


async def get_local_model_status() -> LocalModelStatus:
    """Return a non-sensitive local runtime status; unavailability is not exceptional."""
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
    )
