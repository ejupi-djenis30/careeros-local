"""Process-local vault activity gate for the supported single-worker topology."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class VaultActivityGate:
    """Writer-priority async reader/writer gate.

    Normal API and scheduled-search activity holds a reader permit. Reset,
    restore and erasure first persist their lifecycle guard, cancel owned work,
    then take the writer permit so previously authorized work drains before any
    destructive snapshot is changed.
    """

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._maintenance_lock = asyncio.Lock()
        self._readers = 0
        self._writer = False
        self._waiting_writers = 0

    @property
    def maintenance_active(self) -> bool:
        """Expose a non-blocking probe signal without acquiring the async lock."""

        return self._maintenance_lock.locked() or self._writer or self._waiting_writers > 0

    @asynccontextmanager
    async def reader(self) -> AsyncIterator[None]:
        async with self._condition:
            await self._condition.wait_for(lambda: not self._writer and self._waiting_writers == 0)
            self._readers += 1
        try:
            yield
        finally:
            async with self._condition:
                self._readers -= 1
                self._condition.notify_all()

    @asynccontextmanager
    async def try_reader(self) -> AsyncIterator[bool]:
        """Acquire immediately or report maintenance without joining a wait queue."""

        acquired = False
        async with self._condition:
            if (
                not self._writer
                and self._waiting_writers == 0
                and not self._maintenance_lock.locked()
            ):
                self._readers += 1
                acquired = True
        try:
            yield acquired
        finally:
            if acquired:
                async with self._condition:
                    self._readers -= 1
                    self._condition.notify_all()

    @asynccontextmanager
    async def writer(self) -> AsyncIterator[None]:
        async with self._condition:
            self._waiting_writers += 1
            try:
                await self._condition.wait_for(lambda: not self._writer and self._readers == 0)
                self._writer = True
            finally:
                self._waiting_writers -= 1
                # Cancellation while waiting removes writer priority. Wake readers
                # that may otherwise remain asleep with no future state transition.
                self._condition.notify_all()
        try:
            yield
        finally:
            async with self._condition:
                self._writer = False
                self._condition.notify_all()

    @asynccontextmanager
    async def maintenance(self) -> AsyncIterator[None]:
        """Serialize maintenance revalidation before it can quiesce owned work."""

        async with self._maintenance_lock:
            yield


vault_activity_gate = VaultActivityGate()
