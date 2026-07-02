# Vahini 20-Factor Handwriting Analyser

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![CI](https://github.com/vahinitech/20factor-analyser/actions/workflows/ci.yml/badge.svg)](https://github.com/vahinitech/20factor-analyser/actions/workflows/ci.yml)
[![SBOM: SPDX 2.3](https://img.shields.io/badge/SBOM-SPDX_2.3-green.svg)](sbom.spdx.json)

Open-source **handwriting analysis** from the **geometry and motion of writing**.
Upload a page of handwriting (a photo, or live capture from a dual-IMU sensor pen
on ordinary paper) and get a deterministic, explainable **20-factor report** —
letter formation, spacing, baseline, slant, pressure, speed and more — computed
by a first-party computer-vision engine, with an optional pluggable OCR backend
to read what was written.

This repository is the standalone analyser: the in-browser app, the CV engine,
and a Python OCR / 20-factor server. The marketing website is **not** part of
this repo.

> **Not a diagnostic tool.** The Analyser is for handwriting improvement,
> education and skill-building. It is **not** a medical, psychological,
> neurological, or graphological/personality assessment, and makes no such claims.

---

## Why this exists

Most "handwriting" tools either OCR the text or sell personality readings. This
one does neither by default: it **measures geometry** — the shapes, spacing and
rhythm of the strokes themselves — and explains every score against a reference.
A dual-IMU sensor pen additionally captures the **motion** behind the writing
(16 axes: a 9-axis IMU + a 6-axis IMU + tip force), which the same engine turns
into the dynamics factors (speed, pressure, pen-lifts).

---

## Quickstart

The analysis (computer vision + the 20-factor scoring) runs on the Python
recognition server; the browser captures the image and renders the report. A
running server is therefore required. The quickest way is Docker.

### With Docker (app + OCR backend on one origin)

```bash
docker compose up -d --build
# http://localhost:8080/analyser/Vahini%20Analyser.html
docker compose down
```

The single service is self-contained: the FastAPI server serves the app under
`/analyser` and the OCR + 20-factor APIs (`/ocr`, `/report-python`,
`/analyze-vl`) on the same origin.

### Run the OCR server directly

```bash
pip install -r analyser/server/requirements-core.txt
pip install paddlepaddle paddleocr          # default CPU backend
python analyser/server/analyser-ocr-server.py
# http://localhost:8868/analyser/Vahini%20Analyser.html
```

The backend is pluggable via `VAHINI_OCR_BACKEND` — `paddle` (default), `trocr`,
`surya`, `chandra`, `paddleocr-vl`, or `auto`. See
[`analyser/server/README.md`](analyser/server/README.md) for each backend, model
downloads, and the TrOCR/Surya build flags.

---

## How it works

```
upload / capture  ->  binarize  ->  segment lines & glyphs  ->  measure 20 factors
                                                              ->  score vs reference
                                                              ->  forecast + narrate
   (optional)      ->  OCR backend reads the text, classifies printed vs handwritten
   (pen only)      ->  16-axis motion -> speed / pressure / pen-lift dynamics
```

Everything in the engine is **real geometry computed from the uploaded pixels** —
no personality inference, no random scores. See [`docs/`](docs/) for the
architecture, the CV algorithms, and the OCR notes.

### The 20 factors

| Section | Weight | Factors |
|---|---|---|
| Structure | 30% | Letter Formation, Stroke Order, Loop Closure, Line Quality, Size Consistency, Ascender/Descender |
| Spatial | 30% | Baseline, Word Spacing, Letter Spacing, Margins, Line Straightness, Vertical Alignment |
| Dynamics | 20% | Speed, Pressure, Stroke Continuity, Pen-Lift Frequency (measured by the pen) |
| Style & Readability | 20% | Slant Consistency, Legibility, Character Distinction, Overall Neatness |

`overall = sum(section_average × 10 × weight)`, giving 0–100. In photo mode the
Dynamics factors are not scored (they need the pen), and the headline uses only
what was actually measured.

---

## Repository structure

```
analyser/
  ├── Vahini Analyser.html   live app entrypoint (loads the packed engine)
  ├── src/                   engine SOURCE (engine / report / app)  <- edit here
  ├── scripts/core/          packed build (engine.bundle.js) + runtime helpers
  ├── styles/                report / studio / nav CSS
  ├── static/                informational / printable HTML deliverables
  ├── server/                pluggable Python OCR / 20-factor server + tests
  └── build_bundle.py        rebuilds engine.bundle.js from src/
docs/         architecture, build, CV algorithms, OCR notes
tests/        headless Chrome e2e (recognition + print/handwriting) + fixtures
.github/      CI (runs on every push + PR)
```

---

## Development

The browser client source (recognition client + report renderer) lives in
`analyser/src/`; the CV + scoring engine lives in `analyser/server/`. The client
ships as a single packed file, `analyser/scripts/core/engine.bundle.js`. **After
editing `src/`, rebuild the bundle** (CI fails if it is out of sync):

```bash
python analyser/build_bundle.py
```

### Tests

```bash
# Python server unit + integration (no heavy paddle/torch needed)
pip install -r analyser/server/requirements-core.txt
python -m unittest -v \
  analyser.server.tests.test_backends_classify \
  analyser.server.tests.test_server_pipeline \
  analyser.server.tests.test_regression_functional

# Headless Chrome: print vs handwriting classification + bundle checks
npm ci && npx playwright install --with-deps chromium
npm run test:regression:headless

# Full-stack recognition test against a live OCR backend
docker compose up -d --wait
VAHINI_BASE_URL=http://localhost:8080 npm run test:recognition
```

### CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and PR:
`python-tests`, `e2e` (headless Chrome + bundle-sync check), and
`e2e-recognition` (full stack with the OCR backend, kept fast via a cached
Docker layer for the heavy paddle install).

---

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). By
contributing you agree your contributions are licensed under AGPL-3.0. For
security reports, see [SECURITY.md](SECURITY.md).

Please do **not** commit real handwriting samples that contain personal or
medical data; CI fixtures under `tests/fixtures/` are synthetic.

---

## License

Copyright © 2026 Vahini Technologies.

Free software under the **GNU Affero General Public License, version 3**
(AGPL-3.0-only). See [LICENSE](LICENSE).

**What AGPL-3.0 means for you:** you may use, study, modify and redistribute this
software. If you run a **modified** version to provide a service over a network,
you must make the complete corresponding source of your modified version
available to the users of that service.

- **Patent:** the dual-IMU handwriting-motion sensing method on ordinary paper is
  the subject of **Indian Patent No. 584433**. AGPL-3.0 §11 grants an express
  patent license for this software's contributor versions.
- **Trademark:** "Vahini" and associated marks are **not** licensed under
  AGPL-3.0. Forks must not imply endorsement by or affiliation with Vahini
  Technologies.
- Third-party components keep their own licenses — see
  [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) and [`sbom.spdx.json`](sbom.spdx.json).

---

## Contact

- Website: [vahinitech.com](https://vahinitech.com)
- General: info@vahinitech.com
- Source: https://github.com/vahinitech/20factor-analyser
