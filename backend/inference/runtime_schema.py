from __future__ import annotations

from typing import Any


def runtime_json_schema(value: Any) -> Any:
    """Project the strict app contract to grammar features supported by local runtimes.

    Ollama/llama.cpp grammar initialization rejects nested ``pattern`` keywords for the
    JobMatch schema on supported Windows ARM64 builds. Regex constraints remain intact in
    the Pydantic contract and are enforced after generation; only the runtime grammar copy
    drops that unsupported keyword.
    """
    if isinstance(value, dict):
        return {
            key: runtime_json_schema(item)
            for key, item in value.items()
            if key not in {"maxLength", "pattern"}
        }
    if isinstance(value, list):
        return [runtime_json_schema(item) for item in value]
    return value
