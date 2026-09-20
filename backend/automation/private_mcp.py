"""Strict, content-free FastMCP boundary shared by CareerOS transports."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any, cast

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ContentBlock


class SafeMCPToolError(ToolError):
    """A domain error whose stable code may cross the MCP boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"{code}: CareerOS could not complete the operation")


def _safe_error_code(exc: BaseException) -> str | None:
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, SafeMCPToolError):
            return current.code
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return None


class PrivateContractMCP(FastMCP):
    """Close tool objects and redact validation inputs from protocol errors."""

    def __init__(
        self,
        *args: Any,
        allowed_arguments: Mapping[str, Collection[str]],
        **kwargs: Any,
    ) -> None:
        self._allowed_arguments = {
            name: frozenset(arguments) for name, arguments in allowed_arguments.items()
        }
        super().__init__(*args, **kwargs)

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.inputSchema["additionalProperties"] = False
        return tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[ContentBlock] | dict[str, Any]:
        allowed = self._allowed_arguments.get(name)
        if allowed is None or not isinstance(arguments, dict) or set(arguments) - allowed:
            raise SafeMCPToolError("invalid_result")
        try:
            return cast(
                Sequence[ContentBlock] | dict[str, Any],
                await super().call_tool(name, arguments),
            )
        except Exception as exc:
            # FastMCP validation errors can contain the rejected input value. Only
            # stable codes from errors created above may cross this boundary.
            raise SafeMCPToolError(_safe_error_code(exc) or "invalid_result") from None
