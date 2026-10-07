# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Scan admission control: a full server answers 503, it does not crash."""

import asyncio
import threading
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from backend.tests import test_report_access as access
from backend.tests.test_server_pipeline import _load_server
import scan_slots  # backend/ is on sys.path once the test helpers load


class ScanSlotsTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_queues_then_refuses(self):
        slots = scan_slots.ScanSlots(max_active=1, max_queued=1)
        release = asyncio.Event()
        order = []

        async def scan(name):
            async with slots.slot():
                order.append(name)
                await release.wait()

        first = asyncio.create_task(scan("first"))
        await asyncio.sleep(0)
        queued = asyncio.create_task(scan("queued"))
        await asyncio.sleep(0)
        self.assertEqual(slots.stats()["running"], 1)
        self.assertEqual(slots.stats()["waiting"], 1)

        with self.assertRaises(HTTPException) as refused:
            async with slots.slot():
                pass
        self.assertEqual(refused.exception.status_code, 503)
        self.assertEqual(
            refused.exception.headers["Retry-After"],
            str(scan_slots.RETRY_AFTER_SEC),
        )

        release.set()
        await asyncio.gather(first, queued)
        self.assertEqual(order, ["first", "queued"])
        self.assertEqual(slots.stats()["running"], 0)
        self.assertEqual(slots.stats()["waiting"], 0)


class ScanSlotsHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_server_answers_503_and_cache_hits_still_work(self):
        server = _load_server()
        started = threading.Event()
        finish = threading.Event()

        def slow_scan(*_args, **_kwargs):
            started.set()
            finish.wait(5)
            return access.sample()

        url = "/api/v2/reports?format=compact"
        transport = httpx.ASGITransport(app=server.app)
        with patch.object(
            scan_slots, "SLOTS", scan_slots.ScanSlots(1, 0)
        ), patch.object(server, "_to_numpy", return_value=None), patch.object(
            server, "_report_python_process", side_effect=slow_scan
        ):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # Fill the cache for one page first.
                finish.set()
                cached = await client.post(
                    url, files={"image": ("a.png", b"page-a", "image/png")}
                )
                self.assertEqual(cached.status_code, 200)
                finish.clear()
                started.clear()

                busy_scan = asyncio.create_task(
                    client.post(
                        url,
                        files={"image": ("b.png", b"page-b", "image/png")},
                    )
                )
                while not started.is_set():
                    await asyncio.sleep(0.01)

                refused = await client.post(
                    url, files={"image": ("c.png", b"page-c", "image/png")}
                )
                self.assertEqual(refused.status_code, 503)
                self.assertEqual(
                    refused.headers["retry-after"],
                    str(scan_slots.RETRY_AFTER_SEC),
                )
                self.assertEqual(
                    refused.json()["detail"], scan_slots.BUSY_DETAIL
                )

                again = await client.post(
                    url, files={"image": ("a.png", b"page-a", "image/png")}
                )
                self.assertEqual(again.status_code, 200)

                finish.set()
                self.assertEqual((await busy_scan).status_code, 200)


if __name__ == "__main__":
    unittest.main()
