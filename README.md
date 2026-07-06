# Vahini 20-Factor Handwriting Analyser

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![CI](https://github.com/vahinitech/20factor-analyser/actions/workflows/ci.yml/badge.svg)](https://github.com/vahinitech/20factor-analyser/actions/workflows/ci.yml)
[![SBOM: SPDX 2.3](https://img.shields.io/badge/SBOM-SPDX_2.3-green.svg)](sbom.spdx.json)

Open-source handwriting analysis from the geometry of writing. Upload a photo
of a handwriting page (or capture live with the dual-IMU sensor pen) and get a
compact, explainable 20-factor report: letter formation, spacing, baseline,
slant, pressure, speed and more. Every score is a real measurement with a
published reference range and a crop from your own page as evidence.

> **Not a diagnostic tool.** For handwriting improvement, education and
> skill-building only. It makes no medical, psychological or personality claims.

## Quick start

```bash
docker compose up -d --build
# open http://localhost:8080
```

That single container serves the app and the analysis APIs on one origin.
The first run downloads the OCR models, so give it a few minutes.

Pulled new code or changed a Dockerfile/requirements file? Rebuild from a
clean slate so nothing stale (cached layer, old dependency) survives:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

Use `http://`, not `https://`. The local server speaks plain HTTP; if the
browser autocompletes `https://localhost:8080` the connection fails before
the app can even redirect. Type `http://localhost:8080` and it lands on the
analyser automatically. For HTTPS in production, put the service behind a
TLS reverse proxy such as nginx or Caddy.

To run without Docker:

```bash
pip install -r backend/requirements.txt
python backend/analyser-ocr-server.py
# open http://localhost:8080
```

## What it measures

| Section | Weight | Factors |
|---|---|---|
| Structure | 30% | Letter Formation, Stroke Order, Loop Closure, Line Quality, Size Consistency, Ascender/Descender |
| Spatial | 30% | Baseline, Word Spacing, Letter Spacing, Margins, Line Straightness, Vertical Alignment |
| Dynamics | 20% | Speed, Pressure, Stroke Continuity, Pen Lifts (needs the sensor pen) |
| Style & Readability | 20% | Slant, Legibility, Character Distinction, Overall Neatness |

The overall score is the weighted average of the section scores, 0 to 100.
From a photo, the Dynamics factors are not scored; the headline uses only what
was actually measured. The report is 4 pages: scorecard, top 3 issues with
reference crops, the published reference values for all 20 factors, and a
practice plan with a prediction of how many tries reach the next milestone.

## Why deterministic computer vision, not an LLM

We tried scoring with large language and vision-language models and chose
classical computer vision instead. The reason is repeatable accuracy:

- An LLM grades the same page differently across runs, model versions and
  prompt wordings. A child who re-scans the same page must get the same score,
  or progress tracking means nothing.
- Vector and embedding similarity gives a fuzzy closeness number, not a
  measurement. It cannot say why a score moved, and a model update silently
  reshapes the whole vector space, making old scores incomparable.
- Geometry is auditable. Every factor traces to the exact crop of the page it
  was measured from, and the reference ranges are printed in the report.
- Generative models can be swayed by what the words say when judging how the
  words look, and can report things that are not in the image. Geometry cannot.

Where a model is the right tool, reading messy words, we use one assistively:
the pluggable OCR backends label what was written and never decide a score.
If OCR is unavailable the 20 factors are still measured from geometry alone.

## What the geometry actually checks

"Deterministic computer vision" is a claim, not a black box. Every factor
traces to a real measurement: character-level stroke width and edge
shape, word-level letter spacing, line-level tilt and height, and a few
page-level blends of the factors below it. Most of this never depends on
reading the words correctly; only loop closure, the ascender/descender
proxy and Character Distinction's confidence term lean on OCR text as a
secondary signal. The full walkthrough, from one stroke up to the whole
page, is in `docs/computer-vision-algorithms.md`.

## Repository layout

```
frontend/
  analyser.html           the app (loads the packed engine bundle)
  src/                    browser client source. Edit here, then rebuild.
  scripts/core/           packed build (engine.bundle.js) + runtime helpers
  styles/, static/        report CSS and printable pages
backend/                  Python OCR + 20-factor scoring server and its tests
deployment/               Dockerfile (docker-compose.yml stays at the root)
docs/                     architecture, build, CV algorithms, OCR notes
tests/                    headless Chrome e2e + fixtures
```

## Development

The client ships as one packed file. After editing anything in `frontend/src/`,
rebuild it (CI fails if it is out of date):

```bash
python frontend/build_bundle.py
```

Run the tests:

```bash
# Python server tests (no heavy paddle/torch install needed)
pip install -r backend/requirements-core.txt
python -m unittest -v \
  backend.tests.test_backends_classify \
  backend.tests.test_server_pipeline \
  backend.tests.test_regression_functional \
  backend.tests.test_handwriting_only \
  backend.tests.test_layout_filter

# Headless Chrome report checks
npm ci && npx playwright install --with-deps chromium
npm run test:regression:headless

# Full recognition test against a running stack
docker compose up -d --wait
VAHINI_BASE_URL=http://localhost:8080 npm run test:recognition
```

CI runs all three suites on every push and pull request.

## Contributing and license

Contributions are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md), which
includes a short contributor license agreement. Please do not commit real
handwriting samples containing personal data; the CI fixtures are synthetic.

Want a feature? [Open an issue](https://github.com/vahinitech/20factor-analyser/issues)
describing the problem it solves and who it helps. For features specific to
your school or coaching centre, or anything you'd rather discuss privately,
email **info@vahinitech.com**.

Copyright (c) 2026 Vahini Technologies. Free software under
**AGPL-3.0-only**, see [LICENSE](LICENSE). If you run a modified version as a
network service you must offer its users the modified source.

- Patent: the dual-IMU handwriting-motion sensing method on ordinary paper is
  the subject of Indian Patent No. 584433.
- Trademark: "Vahini" and associated marks are not licensed under AGPL-3.0.
- Third-party components keep their own licenses, see
  [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) and [sbom.spdx.json](sbom.spdx.json).

### Commercial licensing

As the copyright holder, Vahini Technologies also offers this software under
a separate commercial license for organizations that need terms AGPL-3.0
does not give them, most commonly embedding it in a proprietary product or
service without publishing their own modified source. The AGPL edition in
this repository stays free and unrestricted either way. For commercial
license terms, contact **info@vahinitech.com**.

## Contact

[vahinitech.com](https://vahinitech.com) · info@vahinitech.com
