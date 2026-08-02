"""Typed invocation callbacks shared by the split MCP tool registrars."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol


class SyncInvoker(Protocol):
    """Authorize and invoke one synchronous facade operation."""

    def __call__[**Params, Result](
        self,
        call: Callable[Params, Result],
        *args: Params.args,
        **kwargs: Params.kwargs,
    ) -> Awaitable[Result]: ...


class AsyncInvoker(Protocol):
    """Authorize and invoke one asynchronous facade operation."""

    def __call__[**Params, Result](
        self,
        call: Callable[Params, Awaitable[Result]],
        *args: Params.args,
        **kwargs: Params.kwargs,
    ) -> Awaitable[Result]: ...
