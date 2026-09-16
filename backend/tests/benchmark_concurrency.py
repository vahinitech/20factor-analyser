# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Exercise concurrent report requests on one ASGI event loop with stub OCR."""

import asyncio
import json
import time

import httpx
from backend.tests.test_server_pipeline import TestServerPipeline


async def main():
    TestServerPipeline.setUpClass()
    fixture = TestServerPipeline
    server = fixture.mod
    original = server.recognizer.collect_lines
    server.cache.configure(ttl_sec=0)

    def slow_collect(arr, lang):
        time.sleep(0.15)
        return original(arr, lang)

    server.recognizer.collect_lines = slow_collect
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app),
            base_url="http://test",
        ) as client:

            async def request(i):
                start = time.perf_counter()
                response = await client.post(
                    "/report-python",
                    files={
                        "image": ("synthetic.png", fixture.png, "image/png")
                    },
                    data={"expected_text": f"unique-{i}"},
                )
                payload = response.json()
                assert response.status_code == 200 and payload["ok"]
                assert payload["expected_text"] == f"unique-{i}"
                assert payload["analysis"]["measuredCount"] == 16
                return (time.perf_counter() - start) * 1000

            rows = []
            for concurrency in (1, 5, 10):
                start = time.perf_counter()
                latencies = await asyncio.gather(
                    *(request(i) for i in range(concurrency))
                )
                rows.append(
                    {
                        "concurrent_requests": concurrency,
                        "successes": len(latencies),
                        "elapsed_ms": round(
                            (time.perf_counter() - start) * 1000
                        ),
                        "max_request_ms": round(max(latencies)),
                    }
                )
            schema = (await client.get("/openapi.json")).json()
            result = {
                "mode": "One ASGI event loop; real decode/classification/scoring; OCR stub sleeps 150ms; cache disabled. Not a production OCR throughput benchmark.",
                "runs": rows,
                "paths": list(schema["paths"]),
            }
            print(json.dumps(result, indent=2))
    finally:
        server.recognizer.collect_lines = original
        server.cache.configure(ttl_sec=180)
        fixture.doClassCleanups()


if __name__ == "__main__":
    asyncio.run(main())
