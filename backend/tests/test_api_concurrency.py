# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""One-event-loop API concurrency and validation regressions (OCR stubbed)."""

import asyncio
import threading
import time
import unittest
import sys
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import numpy as np

from backend.tests.test_server_pipeline import _load_server


class TestApiConcurrency(unittest.IsolatedAsyncioTestCase):
    async def test_decode_does_not_block_other_requests(self):
        server = _load_server()
        server.cache.configure(ttl_sec=0)
        self.addCleanup(server.cache.configure, ttl_sec=180)
        event_loop_thread = threading.get_ident()
        threads = []

        def decode(_raw):
            threads.append(threading.get_ident())
            time.sleep(0.05)
            return np.full((20, 20, 3), 255, np.uint8)

        transport = httpx.ASGITransport(app=server.app)
        with patch.object(
            server, "_to_numpy", side_effect=decode
        ), patch.object(
            server, "_ocr_process", return_value={"ok": True}
        ), patch.object(
            server, "_analyze_vl_process", return_value={"ok": True}
        ), patch.object(
            server, "_report_python_process", return_value={"ok": True}
        ):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                responses = await asyncio.gather(
                    *[
                        client.post(
                            path,
                            files={
                                "image": ("test.png", b"input", "image/png")
                            },
                        )
                        for path in ("/ocr", "/analyze-vl", "/report-python")
                    ]
                )
        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertEqual(len(threads), 3)
        self.assertNotIn(event_loop_thread, threads)

    def test_concurrent_cold_start_builds_each_model_once(self):
        server = _load_server()
        backends = server.ocr_backends
        for getter, builder in (
            (backends.get_engine, backends._build_engine_cached),
            (backends.get_engine_safe, backends._build_engine_safe_cached),
        ):
            builder.cache_clear()
            calls = []

            def construct(**_kwargs):
                calls.append(1)
                time.sleep(0.05)
                return object()

            try:
                with patch.dict(
                    sys.modules,
                    {"paddleocr": SimpleNamespace(PaddleOCR=construct)},
                ):
                    with ThreadPoolExecutor(max_workers=5) as pool:
                        models = list(pool.map(getter, ["en"] * 5))
                self.assertEqual(len(calls), 1)
                self.assertTrue(all(model is models[0] for model in models))
            finally:
                builder.cache_clear()

    async def test_invalid_and_missing_uploads(self):
        server = _load_server()
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            for path in ("/ocr", "/analyze-vl", "/report-python"):
                with self.subTest(path=path):
                    missing = await client.post(path)
                    self.assertEqual(missing.status_code, 422)
                    for content in (b"", b"not an image", b"%PDF-broken"):
                        invalid = await client.post(
                            path,
                            files={"image": ("bad.png", content, "image/png")},
                        )
                        self.assertEqual(invalid.status_code, 422)
                        self.assertIn(
                            "valid image or PDF", invalid.json()["detail"]
                        )


if __name__ == "__main__":
    unittest.main()
