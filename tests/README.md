# Tests

Three suites, smallest first. CI runs all of them on every push and PR.

## 1. Python server tests

Server logic without the heavy paddle/torch install:

```bash
pip install -r backend/requirements/core.txt
python -m unittest discover -v -s backend/tests -t .
```

Covers the API contracts, the printed/handwriting classifier, the 20-factor
pipeline, engine failure recovery, the reference-image guarantees, and the
handwriting-only rule: printed text never enters a report. The
handwriting-only suite runs against the real pages in `fixtures/samples/`
(pure handwriting, pure print, mixed print + pen) and asserts that mixed
pages score only the pen entries and fully printed pages are refused.

## 2. Headless report checks

`print-vs-handwriting.test.html` feeds a server-shaped analysis into the
packed bundle's `VahiniReport.render` and asserts the compact report is
complete: all 20 factors, the reference-values table, the improve cards with
concept plus reference, the tries prediction, and no leaked characters.

```bash
npm ci
npx playwright install --with-deps chromium   # once
npm run test:regression:headless
```

To debug in a normal browser instead:

```bash
npm run test:regression:serve
# open http://127.0.0.1:4173/tests/print-vs-handwriting.test.html
```

Rebuild the bundle first after editing anything under `frontend/src/`:
`python frontend/build_bundle.py`.

## 3. Recognition end to end

`e2e-recognition.mjs` uploads `tests/fixtures/handwriting-sample.jpg` to a
running stack and asserts real recognition and a full report:

```bash
docker compose up -d --wait
VAHINI_BASE_URL=http://localhost:8080 npm run test:recognition
```

The fixture is a committed, synthetic handwriting page. Please do not add
samples containing personal data.

## Synthetic full-page Free/Pro flow

`synthetic-report-flow.mjs` adds an isolated upload-to-report check to the
existing Playwright tier, at 390 and 1440 px. It uses generated curves and
invented compact responses, the current committed dictionary, and the real
account client, decoder and report renderer. It covers:

- No upload before choosing who checks or before the Student adult tick.
- “Keep my pages” with no email blocks before upload; with it off, no keep
  request is made.
- Free's five factor records, Pro's twenty unique records, and all six
  sensor-only skills (2, 4, 13–16) remaining unavailable with null scores.
- Pro connection, cleared key input, no key in browser storage or URLs,
  and Free again after disconnecting. The disposable test key is accepted
  only by the intercepted API and is never stored in an artifact.
- A reader failure produces no score, and another upload can succeed.
- Measurement strips, the existing two report sections and no horizontal
  overflow. Desktop and phone screenshots are saved for review.

```bash
npm run build:bundle
npm run test:synthetic-report
```

The test binds a free local port, rejects off-origin browser requests, and
writes only synthetic screenshots and a small results manifest under
`test-results/synthetic-report-flow/`. CI uploads `synthetic-browser-review`
even if a case fails. These are **review artifacts, not pixel baselines**.
Use the Playwright version from `npm ci` and its matching browser before
reviewing any proposed baseline. `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` can
select an installed Chromium for diagnosis; that is not a pinned-browser
visual pass. Existing PDF, print-layout, language, feedback and live OCR
suites remain separate and unchanged.

Synthetic success says the UI handled the supplied response. It does not
prove recognition accuracy, real server authorization, or staging access.

### Optional real staging Pro recognition

The existing `test:recognition` remains a real Free check by default. If an
operator already has an authorized staging Pro key in the environment,
set `VAHINI_BASE_URL=https://stage.vahinitech.com` and make `VAHINI_PRO_KEY`
available to that process, then run `npm run test:recognition`. Never paste
the key into a command, repository file, issue, PR, trace or log. No key is
created or granted by this test. Its Pro mode refuses production, other
remote hosts and non-HTTPS staging URLs; local test stacks are supported.
The key stays in the browser tab's memory and is sent through the existing
same-origin account client. No request headers or browser trace are saved.

Pro mode checks all 20 actual response records, the six null sensor-only
scores, real recognition and the rendered report. It uses the existing
committed synthetic sample photo. Run it only with the owner's permission
for that staging check. A synthetic browser run must never be described
as this real staging check, and a missing key is an **unrun** Pro check,
not a pass.
