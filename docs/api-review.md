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

Inference on the same Paddle model instance remains serialized for safety. Requests can overlap in decoding and other processing, but adding users does not make one model run faster. The default deployment starts one Uvicorn process. Starlette also shares a finite worker-thread pool across blocking operations; increasing it alone does not establish OCR capacity.

There is no application-level admission limit or durable job queue. Large uploads and queued requests can consume memory. Benchmark the deployed model and representative page sizes before setting a user-capacity target. Set gateway upload/request limits and origins for the intended deployment. Multiple processes or replicas each need their own models and memory budget, and do not share the in-memory cache.

## Measured request test

Run `python -m backend.tests.benchmark_concurrency` after installing core test dependencies. It uses one ASGI event loop, real decode/classification/scoring, a synthetic mixed page, disabled response caching, and a stub OCR call delayed by 150 ms. It checks that each response retains its own request marker.

| Simultaneous requests | Successful responses | Batch elapsed in this WSL run |
|---|---|---|
| 1 | 1 | 248 ms |
| 5 | 5 | 364 ms |
| 10 | 10 | 610 ms |

These timings demonstrate overlapping request handling, not real Paddle throughput, network latency, or a production capacity guarantee. Separate regressions verify decoding runs off the event-loop thread, invalid-upload responses on all three POST routes, and single-instance initialization under five concurrent callers. The existing Docker recognition CI verifies a real OCR path but is not a load test.

## Dependency and inventory review

Playwright is updated from 1.61.1 to 1.63.0. The compatible lockfile update moves `qs` to 6.16.0; npm audit reports zero known npm vulnerabilities at review time. `http-server` 14.1.1 remains its current release.

The separately CDN-loaded PDF.js was 3.11.174, affected by [CVE-2024-4367](https://github.com/mozilla/pdf.js/security/advisories/GHSA-wgrm-67xf-hhpq). It now uses the version-pinned 6.3.289 ES module and worker, disables evaluation, and releases the worker after each upload. The real-library browser test covers first-page rendering, repeated uploads and invalid input. npm audit alone does not cover CDN-loaded assets.

`sbom.spdx.json` is a source inventory: exact npm lockfile packages and integrity checksums, CDN assets, and declared Python core/default-engine dependencies. Python ranges are recorded as constraints rather than pretending to be installed versions. It is not a complete deployed-container inventory; OS packages, resolved Python transitives, optional OCR tiers and model weights require a build-time SBOM. Paddle/model upgrades were not made without real-model compatibility and performance evidence.

Use `python backend/update_sbom.py` to refresh and `python backend/update_sbom.py --check` to detect drift. CI checks drift, and this revision was validated with `pyspdxtools -i sbom.spdx.json`. The writing guidance in `skills.md` now requires evidence provenance and scoped concurrency/dependency claims.
