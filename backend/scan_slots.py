# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Admission control for scans: how many pages are processed at once.

Every scan decodes the image, runs OCR, layout and scoring, and holds its
arrays until it finishes; on the 4-core, 8 GB deployment box each one adds
about 0.5 GB. Without a cap, four simultaneous visitors pushed the stage
analyser out of memory and the kernel killed it mid-request (2026-10-07,
docker events "oom" then "die 137"), failing every scan in flight.

So at most VAHINI_MAX_ACTIVE_SCANS run at once, up to VAHINI_MAX_QUEUED_SCANS
wait their turn, and anything beyond that gets 503 with Retry-After instead
of a crash. Cache hits never take a slot: callers ask for one only after a
cache miss. One event loop owns the counters, so no lock is needed.
"""

import asyncio
import collections
import os
from contextlib import asynccontextmanager

from fastapi import HTTPException

RETRY_AFTER_SEC = 20
BUSY_DETAIL = "The analyser is busy. Please try again in a moment."


def _env_int(name, default, minimum):
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        value = default
    return max(minimum, value)


class ScanSlots:
    """Counters plus a FIFO of waiters. Each waiter is a future on the loop
    that is running when it waits, so the object is not tied to one event
    loop (an asyncio.Semaphore binds to the first loop that waits on it)."""

    def __init__(self, max_active, max_queued):
        self.max_active = max_active
        self.max_queued = max_queued
        self._running = 0
        self._waiters = collections.deque()

    @asynccontextmanager
    async def slot(self):
        if self._running >= self.max_active:
            if len(self._waiters) >= self.max_queued:
                raise HTTPException(
                    503,
                    BUSY_DETAIL,
                    headers={"Retry-After": str(RETRY_AFTER_SEC)},
                )
            turn = asyncio.get_running_loop().create_future()
            self._waiters.append(turn)
            try:
                await turn  # _release hands this waiter the slot
            except BaseException:
                if turn in self._waiters:
                    self._waiters.remove(turn)
                elif not turn.cancelled():
                    self._release()  # handed the slot, then cancelled
                raise
        else:
            self._running += 1
        try:
            yield
        finally:
            self._release()

    def _release(self):
        while self._waiters:
            turn = self._waiters.popleft()
            if not turn.done():
                turn.set_result(None)  # slot passes on; _running unchanged
                return
        self._running -= 1

    def stats(self):
        return {
            "running": self._running,
            "waiting": len(self._waiters),
            "max_active": self.max_active,
            "max_queued": self.max_queued,
        }


SLOTS = ScanSlots(
    _env_int("VAHINI_MAX_ACTIVE_SCANS", 2, 1),
    _env_int("VAHINI_MAX_QUEUED_SCANS", 4, 0),
)
