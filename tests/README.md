# Tests

Browser-run smoke tests — no toolchain required. Open the file in a modern browser
(or the preview) and read the pass/fail panel.

| File | Checks |
|---|---|
| `smoke.test.html` | Loads the **packed engine bundle**, runs the demo analysis, and asserts the engine's public API, a rendered multi-page report, **no duplicate pages**, and that the **validity gate** + Dynamics handling behave in photo mode. |
| `print-vs-handwriting.test.html` | Feeds a server-shaped 20-factor `analysis` object (what `/report-python` returns) into the packed bundle's `VahiniReport.render` and asserts the report renders all 20 factors, the overall score, and no leaked control/replacement characters. Render-only: no CV engine or private sample images. |

## How to run

Open `tests/smoke.test.html`. Each assertion shows ✓ (pass) or ✗ (fail) with a short reason.
A green summary banner means all checks passed.

For fast report-render regression (no manual upload, no server, no sample images):

1. Start a local static server from project root:

	`npx http-server . -p 4173 -c-1`

2. Open:

	`http://127.0.0.1:4173/tests/print-vs-handwriting.test.html`

3. Refresh after editing `analyser/src/report/report-render.js` (rebuild the bundle first with
   `python analyser/build_bundle.py`) to rerun the render checks.

## Headless regression (terminal)

Run the same sample-image checks in headless Chromium and print PASS/FAIL in terminal:

1. Install browser once:

	`npm run test:regression:install`

2. Run checks:

	`npm run test:regression:headless`

These are intentionally lightweight, dependency-free regression checks for the highest-risk
report behaviours (the Fix-Spec items). Extend by adding more `assert(...)` calls in the file.

## Full headless E2E (`e2e-pages.mjs`)

End-to-end Chrome regression that drives the **real** pages and asserts the whole
journey, fully offline (no Python/paddle backend needed):

| Check | What it proves |
|---|---|
| Home / blog index / blog post load | marketing pages render, no page errors |
| Analyser loads + engine wired | the packed bundle initialises |
| Upload accepted | a real image upload enables Analyse |
| Report generated | the pipeline completes on-device |
| 20 distinct factors + 20-chip map | the report is complete and correct |
| Scores varied | factors differ (not a stuck/placeholder report) |
| Recognition note present | the trust/assistive note ships in the report |
| PDF save works | `page.pdf()` produces a real PDF |

Run it:

```
npm run test:regression:install   # once, downloads Chromium
npm run test:e2e                  # the full journey
npm run test:all                  # e2e + print/handwriting checks
```

Fixture: `tests/fixtures/handwriting-sample.jpg` (a committed real-handwriting page).

## Continuous integration

`.github/workflows/ci.yml` runs on **every push and pull request**:

- **python-tests** — server logic (pluggable OCR backends, printed/handwriting
  classifier, factor pipeline, PDF/passage alignment) on the light deps only
  (engines are lazy-imported, so no paddle/torch needed).
- **e2e** — installs Chromium, verifies the packed bundle is in sync with
  `analyser/src/`, then runs `test:e2e` and `test:regression:headless`.
