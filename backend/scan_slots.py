# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Admission control for scans: how many pages are processed at once.

Every scan decodes the image, runs OCR, layout and scoring, and holds its
arrays until it finishes; on the 4-core, 8 GB deployment box each one adds
about 0.5 GB. Without a cap, four simultaneous visitors pushed the stage
analyser out of memory and the kernel killed it mid-request (2026-10-07,
docker events "oom" then "die 137"), failing every scan in flight.

So at most PLAN["active"] scans run at once (capacity.py works it out from
memory, cores and GPUs), up to PLAN["queued"] wait their turn, and anything
beyond that gets 503 with Retry-After instead of a crash. Cache hits never
take a slot: callers ask for one only after a cache miss.

The work itself runs on a dedicated pool with one thread per slot, not on
Starlette's shared pool of ~40. Paddle keeps working buffers per calling
thread, so scans spread over many threads each kept a scan's peak: one scan
at a time still climbed past 2.4 GB after a burst of queued requests. Each
slot thread also has its own OCR engine copy (ocr_backends._replica_index),
so slots no longer queue on one engine's lock.
"""

import asyncio
import collections
import functools
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import HTTPException

import capacity

RETRY_AFTER_SEC = 20
BUSY_DETAIL = "The analyser is busy. Please try again in a moment."


def _wake(turn):
    if not turn.done():
        turn.set_result(None)


class ScanSlots:
    """Counters plus a FIFO of waiters, safe across threads and event loops.

    Each waiter is a future on the loop that is running when it waits, and
    a released slot wakes it with call_soon_threadsafe on that loop. uvicorn
    runs one loop, but Starlette's TestClient (and any embedding) can run
    each request on its own; completing a future from a foreign thread left
    such a waiter asleep forever."""

    def __init__(self, max_active, max_queued):
        self.max_active = max_active
        self.max_queued = max_queued
        self._lock = threading.Lock()
        self._running = 0
        self._waiters = collections.deque()

    @asynccontextmanager
    async def slot(self):
        turn = None
        with self._lock:
            if self._running < self.max_active:
                self._running += 1
            elif len(self._waiters) >= self.max_queued:
                raise HTTPException(
                    503,
                    BUSY_DETAIL,
                    headers={"Retry-After": str(RETRY_AFTER_SEC)},
                )
            else:
                turn = asyncio.get_running_loop().create_future()
                self._waiters.append(turn)
        if turn is not None:
            try:
                await turn  # _release hands this waiter the slot
            except BaseException:
                with self._lock:
                    handed = turn not in self._waiters
                    if not handed:
                        self._waiters.remove(turn)
                if handed:
                    self._release()  # handed the slot, then cancelled
                raise
        try:
            yield
        finally:
            self._release()

    def _release(self):
        with self._lock:
            while self._waiters:
                turn = self._waiters.popleft()
                if not turn.done():
                    # The slot passes on; _running stays the same.
                    turn.get_loop().call_soon_threadsafe(_wake, turn)
                    return
            self._running -= 1

    def stats(self):
        with self._lock:
            return {
                "running": self._running,
                "waiting": len(self._waiters),
                "max_active": self.max_active,
                "max_queued": self.max_queued,
            }


# Sized from this host's memory, cores and GPUs (capacity.py); the
# VAHINI_MAX_ACTIVE_SCANS / VAHINI_MAX_QUEUED_SCANS overrides still win.
PLAN = capacity.detect_plan()
SLOTS = ScanSlots(PLAN["active"], PLAN["queued"])

# One worker per slot: the same few threads run every scan, so Paddle's
# per-thread buffers exist at most max_active times.
EXECUTOR = ThreadPoolExecutor(
    max_workers=SLOTS.max_active, thread_name_prefix="scan"
)


async def run(fn, *args):
    """Run blocking scan work on the scan pool (use inside slot())."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(EXECUTOR, functools.partial(fn, *args))
