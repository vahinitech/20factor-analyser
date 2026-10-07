# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Real-model load test: send N scans at once to a running analyser.

Unlike backend/tests/benchmark_concurrency.py (stubbed OCR), this measures
the deployed models: how many simultaneous scans complete with a real
reading, how many are refused with 503 by the scan cap, and how long they
take. It is how the numbers in issue #97 and docs/api-review.md were taken.

Every request is a cache miss: the photo's bytes get a random tail after the
image data. JPEG and PNG decoders ignore it; the server's cache keys on the
raw bytes, so each request is a full scan without needing distinct photos.

    python backend/load_test.py http://127.0.0.1:8868 \
        --photo tests/fixtures/handwriting-sample.jpg --concurrency 1 4 8

Run it against stage only, straight at the analyser (not through nginx,
which rate-limits bursts), and watch the container while it runs:

    docker events --filter container=vahini-analyser-stage   # oom / die
    docker exec vahini-analyser-stage cat /sys/fs/cgroup/memory.peak

Standard library only, so it runs in any python:3 container.
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

URL_PATH = "/api/v2/reports?format=compact&include=text,evidence"


def unique_copy(photo):
    """The photo's bytes plus a random tail, so the server cannot answer
    from its cache."""
    return photo + b"\0vahini-load-test:" + os.urandom(16)


def scan(base, photo, content_type):
    """One request. Returns (status, seconds, reading backend or detail)."""
    boundary = uuid.uuid4().hex
    body = (
        (
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="image"; filename="page"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        + unique_copy(photo)
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        base.rstrip("/") + URL_PATH,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            doc = json.load(response)
            reading = (doc.get("recognition") or {}).get("backend", "none")
            return response.status, time.perf_counter() - started, reading
    except urllib.error.HTTPError as err:
        return err.code, time.perf_counter() - started, "refused"
    except OSError as err:  # reset while the server restarts, timeouts
        return "conn", time.perf_counter() - started, type(err).__name__


def burst(base, photo, content_type, concurrency):
    """`concurrency` simultaneous scans; returns a summary dict."""
    started = time.perf_counter()
    with ThreadPoolExecutor(concurrency) as pool:
        rows = list(
            pool.map(
                lambda _: scan(base, photo, content_type), range(concurrency)
            )
        )
    wall = time.perf_counter() - started
    read = sorted(t for s, t, how in rows if s == 200 and how != "cv-fallback")
    statuses = {}
    for status, _, _ in rows:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    return {
        "concurrency": concurrency,
        "real_readings": len(read),
        "statuses": statuses,
        "p50_s": round(read[len(read) // 2], 1) if read else None,
        "max_s": round(read[-1], 1) if read else None,
        "wall_s": round(wall, 1),
        "reports_per_min": round(len(read) / wall * 60, 1),
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    parser.add_argument("base", help="analyser base URL, e.g. http://...:8868")
    parser.add_argument(
        "--photo", default="tests/fixtures/handwriting-sample.jpg"
    )
    parser.add_argument(
        "--concurrency", type=int, nargs="+", default=[1, 2, 4, 8]
    )
    args = parser.parse_args()
    with open(args.photo, "rb") as f:
        photo = f.read()
    content_type = (
        "image/png" if args.photo.lower().endswith(".png") else "image/jpeg"
    )
    for level in args.concurrency:
        print(json.dumps(burst(args.base, photo, content_type, level)))


if __name__ == "__main__":
    main()
