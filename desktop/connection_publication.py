"""Renew desktop discovery only while the acquired desktop instance is serving."""

from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from typing import Any
from uuid import uuid4

from backend.desktop.connection_descriptor import (
    RELATIVE_PATH,
    invalidate_connection_descriptor,
    publish_connection_descriptor,
)


@contextmanager
def connection_publication(server: Any, root: Path, url: str):
    instance = str(uuid4())
    stop = Event()
    failed = Event()

    def renew():
        while not stop.wait(0.05):
            if not server.started:
                continue
            try:
                publish_connection_descriptor(root, url, instance)
            except (OSError, ValueError):
                failed.set()
                server.should_exit = True
                return
            if stop.wait(10):
                return

    thread = Thread(target=renew, name="careeros-connection-descriptor", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        invalidate_connection_descriptor(root / RELATIVE_PATH, instance)
    if failed.is_set():
        raise RuntimeError("Cannot publish private desktop connection metadata")
