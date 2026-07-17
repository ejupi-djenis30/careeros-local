from typing import Any, Callable, Protocol


class LocalInferencePort(Protocol):
    """Capabilities domain services may use from an on-device model runtime."""

    @property
    def model_id(self) -> str: ...

    async def generate_json_async(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> dict[str, Any]: ...

    async def list_models_async(self) -> list[str]: ...


LocalInferenceFactory = Callable[[str], LocalInferencePort]
