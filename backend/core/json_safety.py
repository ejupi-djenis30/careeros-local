"""Strict JSON decoding for persisted trust boundaries."""

from __future__ import annotations

import json
from typing import Any


def strict_json_loads(data: bytes | str) -> Any:
    """Decode JSON while rejecting ambiguous keys and non-finite numbers."""

    def object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("JSON object contains duplicate keys")
            result[key] = value
        return result

    def reject_non_finite(value: str) -> Any:
        raise ValueError(f"JSON contains unsupported numeric value: {value}")

    return json.loads(
        data,
        object_pairs_hook=object_without_duplicates,
        parse_constant=reject_non_finite,
    )
