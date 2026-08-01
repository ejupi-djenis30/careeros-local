from __future__ import annotations

import math
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

    def __post_init__(self) -> None:
        if not isinstance(self.system_prompt, str) or not isinstance(self.user_prompt, str):
            raise TypeError("Inference prompts must be strings")
        if len(self.system_prompt) + len(self.user_prompt) > 2_000_000:
            raise ValueError("Inference prompt exceeds the local runtime safety limit")
        if not isinstance(self.json_schema, dict):
            raise TypeError("Inference JSON schema must be an object")
        if (
            not isinstance(self.max_tokens, int)
            or isinstance(self.max_tokens, bool)
            or not 1 <= self.max_tokens <= 131_072
        ):
            raise ValueError("Inference max_tokens must be between 1 and 131072")
        if not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("Inference temperature must be between 0 and 2")
        if not math.isfinite(self.top_p) or not 0 <= self.top_p <= 1:
            raise ValueError("Inference top_p must be between 0 and 1")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError("Inference seed must be an integer")
        if (
            not isinstance(self.task_id, str)
            or not self.task_id
            or len(self.task_id) > 128
            or any(ord(character) < 32 or ord(character) == 127 for character in self.task_id)
        ):
            raise ValueError("Inference task_id is invalid")


@dataclass(frozen=True, slots=True)
class InferenceUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def __post_init__(self) -> None:
        for value in (self.prompt_tokens, self.completion_tokens):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError("Inference token usage must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class StructuredInferenceResult:
    payload: dict[str, Any]
    model_id: str
    runtime: str
    usage: InferenceUsage = field(default_factory=InferenceUsage)
    duration_ms: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.payload, dict):
            raise TypeError("Structured inference payload must be an object")
        for name, value in (("model_id", self.model_id), ("runtime", self.runtime)):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 512
                or any(ord(character) < 32 or ord(character) == 127 for character in value)
            ):
                raise ValueError(f"Structured inference {name} is invalid")
        if (
            not isinstance(self.duration_ms, int)
            or isinstance(self.duration_ms, bool)
            or self.duration_ms < 0
        ):
            raise ValueError("Structured inference duration must be non-negative")


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
