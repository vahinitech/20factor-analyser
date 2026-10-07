# API and concurrency review

Reviewed on 2026-09-11. The combined service is `backend/analyser-ocr-server.py`; `backend/ppocr-server.py` defines the analysis APIs.

| Endpoint | Method and input | Behavior |
|---|---|---|
| `/health` | GET | Service and model availability metadata. HTTP 200 alone does not prove an OCR model is ready; inspect `backends`. |
| `/ocr/health` | GET | Combined-server compatibility alias for `/health`. |
| `/ocr` | POST multipart `image`, optional `lang`, `det`, `rec` | Recognized handwriting. `det` and `rec` are accepted compatibility fields; currently they do not disable detection or recognition. |
| `/analyze-vl` | POST multipart `image`, optional `lang` | Handwriting regions, context and factor evidence. |
| `/report-python` | POST multipart `image`, optional `lang`, `expected_text` | Factor scores, evidence and recognition metadata. |
| `/openapi.json`, `/docs`, `/redoc` | GET | Machine-readable schema and API documentation. |
| `/`, `/analyser` | GET | Combined-server redirects to `/analyser/analyser.html`. |
| `/analyser/*` | GET | Static browser client. |

Missing, empty or malformed image/PDF uploads return HTTP 422. A valid image with no detected handwriting returns an application refusal (`ok:false`, `error_code:no_handwriting`) using the existing HTTP 200 contract. Clients must check both HTTP status and `ok`. OCR initialization failures can use geometry fallback; a successful report does not imply successful text recognition.

## Multi-user behavior

Image/PDF decoding, OCR and scoring now run outside the async event loop. The cache is thread-safe and returns copies. Cold model initialization is serialized per language/configuration so simultaneous first requests reuse a single model instance.

**Admission control (since #96).** Scans are capped and sized from the host. `backend/capacity.py` works out at startup how many can run at once from the container's memory limit (or the host's available memory), usable cores and GPUs in use. `backend/scan_slots.py` lets that many run, queues four per slot in order, and answers **503** with `Retry-After: 20` beyond that. Cache hits never take a slot. Scan work runs on a dedicated pool with one thread per slot, and each slot thread has its own OCR engine copy (`ocr_backends._replica_index`), limited to `cores // slots` threads. `/health` reports the plan as `scan_capacity`. `VAHINI_MAX_ACTIVE_SCANS` / `VAHINI_MAX_QUEUED_SCANS` override it.

Why it exists, measured on the deploy box on 2026-10-07 (4 cores, 7.9 GB shared host): one scan peaks at about 1.6 GB, and four simultaneous scans had the process killed by the kernel (`docker events`: `oom`, `die 137`). Spreading queued scans over Starlette's ~40 threads also held one scan's peak per thread inside Paddle, so the work runs on its own threads. On a shared engine, OCR is serialized per instance, so extra slots only add throughput with their own engine copy. OCR took 2.74 s on 4 threads and 3.01 s on 2, so two 2-thread copies beat one 4-thread copy when memory allows. The model, constants and projections for bigger hosts are in #97.

The deployment still starts one Uvicorn process and has no durable job queue. A queued request is lost if the process restarts. Multiple processes or replicas each need their own models and memory budget, and do not share the in-memory cache.

## Measured request test

Run `python -m backend.tests.benchmark_concurrency` after installing core test dependencies. It uses one ASGI event loop, real decode/classification/scoring, a synthetic mixed page, disabled response caching, and a stub OCR call delayed by 150 ms. It checks that each response retains its own request marker.

| Simultaneous requests | Successful responses | Batch elapsed in this WSL run |
|---|---|---|
| 1 | 1 | 248 ms |
| 5 | 5 | 364 ms |
| 10 | 10 | 610 ms |

These timings demonstrate overlapping request handling, not real Paddle throughput, network latency, or a production capacity guarantee. Separate regressions verify decoding runs off the event-loop thread, invalid-upload responses on all three POST routes, and single-instance initialization under five concurrent callers. The existing Docker recognition CI verifies a real OCR path but is not a load test.

## Real-model load test

`backend/load_test.py` sends N scans at once to a running analyser and reports real readings, 503 refusals, latency and reports per minute. Every request gets a random tail after the image bytes, so the response cache never answers. Image decoders ignore the tail; the cache keys on raw bytes. It uses the standard library only. Run it against stage, straight at the analyser container rather than through nginx, which rate-limits bursts, and watch `docker events` for `oom`/`die` and the container's `memory.peak`:

```bash
docker run --rm --network container:vahini-analyser-stage -v "$PWD":/w -w /w \
  python:3.12-slim python backend/load_test.py http://127.0.0.1:8868 --concurrency 1 4 8
```

Stage on 2026-10-07: 2.5 GB no-swap container, 4 cores, one slot and four queued, `tests/fixtures/handwriting-sample.jpg`:

| Simultaneous | Real readings | Refused (503) | Median | Slowest | Reports/min |
|---|---|---|---|---|---|
| 1 | 1 | 0 | 3.1 s | 3.1 s | 19.2 |
| 4 | 4 | 0 | 9.1 s | 12.4 s | 19.3 |
| 8 | 5 | 3 | 8.8 s | 14.9 s | 20.1 |

Kernel `memory.peak` was 1.43 GB; no `oom` or `die` events. Before the scan cap, 4 simultaneous scans got the container killed. Projections for bigger hosts and GPUs are in #97; measure them with this tool before relying on them.

## Dependency and inventory review

Playwright is updated from 1.61.1 to 1.63.0. The compatible lockfile update moves `qs` to 6.16.0; npm audit reports zero known npm vulnerabilities at review time. `http-server` 14.1.1 remains its current release.

The separately CDN-loaded PDF.js was 3.11.174, affected by [CVE-2024-4367](https://github.com/mozilla/pdf.js/security/advisories/GHSA-wgrm-67xf-hhpq). It now uses the version-pinned 6.3.289 ES module and worker, disables evaluation, and releases the worker after each upload. The real-library browser test covers first-page rendering, repeated uploads and invalid input. npm audit alone does not cover CDN-loaded assets.

`sbom.spdx.json` is a source inventory: exact npm lockfile packages and integrity checksums, CDN assets, and declared Python core/default-engine dependencies. Python ranges are recorded as constraints rather than pretending to be installed versions. It is not a complete deployed-container inventory; OS packages, resolved Python transitives, optional OCR tiers and model weights require a build-time SBOM. Paddle/model upgrades were not made without real-model compatibility and performance evidence.

Use `python backend/update_sbom.py` to refresh and `python backend/update_sbom.py --check` to detect drift. CI checks drift, and this revision was validated with `pyspdxtools -i sbom.spdx.json`. The writing guidance in `skills.md` now requires evidence provenance and scoped concurrency/dependency claims.
