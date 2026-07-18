from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True, slots=True)
class StructuredInferenceRequest:
    system_prompt: str
    user_prompt: str
    json_schema: dict[str, Any]
    max_tokens: int
    temperature: float = 0.0
    top_p: float = 0.9
    seed: int = 0
    task_id: str = "default"


@dataclass(frozen=True, slots=True)
class InferenceUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class StructuredInferenceResult:
    payload: dict[str, Any]
    model_id: str
    runtime: str
    usage: InferenceUsage = field(default_factory=InferenceUsage)
    duration_ms: int = 0


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

    async def generate_structured_async(
        self, request: StructuredInferenceRequest
    ) -> StructuredInferenceResult: ...


LocalInferenceFactory = Callable[[str], LocalInferencePort]
