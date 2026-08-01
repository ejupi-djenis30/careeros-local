"""Native-shell-only lifecycle controls for the loopback desktop sidecar."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, status

from backend.desktop.settings import DesktopRuntimeSettings

router = APIRouter()


class DesktopShutdownController:
    """Bind one running server to the authenticated desktop shutdown route."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handler: Callable[[], None] | None = None

    @contextmanager
    def bind(self, handler: Callable[[], None]) -> Iterator[None]:
        if not callable(handler):
            raise TypeError("Desktop shutdown handler must be callable")
        with self._lock:
            if self._handler is not None:
                raise RuntimeError("A desktop shutdown handler is already bound")
            self._handler = handler
        try:
            yield
        finally:
            with self._lock:
                if self._handler is handler:
                    self._handler = None

    def request(self) -> bool:
        with self._lock:
            handler = self._handler
        if handler is None:
            return False
        handler()
        return True


desktop_shutdown_controller = DesktopShutdownController()


@router.post(
    "/shutdown",
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
def request_desktop_shutdown() -> dict[str, str]:
    """Ask the bound Uvicorn server to drain requests and run lifespan cleanup.

    In desktop mode every HTTP request has already passed the per-launch
    ``X-CareerOS-Session`` middleware. Keeping this endpoint absent from browser
    mode prevents it from becoming a general remote process-control surface.
    """

    if not DesktopRuntimeSettings.from_environment().enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not desktop_shutdown_controller.request():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Desktop shutdown is temporarily unavailable",
        )
    return {"status": "shutting_down"}
