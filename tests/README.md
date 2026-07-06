# Tests

Three suites, smallest first. CI runs all of them on every push and PR.

## 1. Python server tests

Server logic without the heavy paddle/torch install:

```bash
pip install -r backend/requirements-core.txt
python -m unittest -v \
  backend.tests.test_backends_classify \
  backend.tests.test_server_pipeline \
  backend.tests.test_regression_functional \
  backend.tests.test_handwriting_only
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
