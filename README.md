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

Use `http://`, not `https://`. The local server speaks plain HTTP; if the
browser autocompletes `https://localhost:8080` the connection fails before
the app can even redirect. Type `http://localhost:8080` and it lands on the
analyser automatically. For HTTPS in production, put the service behind a
TLS reverse proxy such as nginx or Caddy.

To run without Docker:

```bash
pip install -r analyser/server/requirements.txt
python analyser/server/analyser-ocr-server.py
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

"Deterministic computer vision" is a claim, not a black box — here is what
that means at each level, from a single stroke up to the whole page. The
report shows a small diagram of exactly this next to a crop of your own
writing, for every factor.

**One character.** The page is thresholded to an ink mask (Otsu:
pen/print marks vs paper). Two measurements come straight from that mask:

- *Stroke width.* A distance transform gives every ink pixel its distance
  to the nearest background pixel; the ridge of that map is roughly half
  the stroke's width at that point. Printed type holds this width nearly
  constant end to end (low variance). A pen's width wanders with speed and
  pressure (higher variance) — that variance, not the width itself, is
  the signal, and it's the main structural cue behind Letter Formation and
  the printed-vs-handwriting split.
- *Edge crispness.* Canny edges divided by ink area. Print has sharp,
  mostly straight contours; a drawn line has soft, curved ones.
- *Loop closure* (Structure factor 3, for letters like a/o/d/p/e/g/q)
  is currently a proxy, not per-letter contour tracing: it's the share of
  loop-shaped letters among everything the OCR engine actually read on the
  page. Worth knowing plainly, since it's the one factor here that leans
  on reading the words rather than pure pixels.

**One word.** A word's own bounding box, and its neighbours on the same
line, give two more measurements: the gaps between adjacent letters
(their consistency is Letter Spacing, factor 9) and the word's width
divided by its own letter count (an average character width, feeding
Stroke Order and Size Consistency). None of this needs the word read
correctly — it only needs the boxes OCR detection already draws around
each cluster of ink, the same orange boxes shown on your page in the
report.

**One line.** A detected line carries a polygon, not just a box, so its
tilt is measurable directly (the angle between its first two corner
points). The *average* tilt across every line on the page is what
Baseline and Line Straightness measure; how much that tilt *varies* from
line to line, not its average, is what Vertical Alignment and Slant
measure instead — a page where one line suddenly veers scores worse here
than a page that leans the same modest amount throughout. (Worth being
plain about: Slant here is that page-level tilt-variability signal, not
a per-letter cursive-lean angle — a simplification, like loop closure
above.) The line's own bounding-box height and width, compared against
every other line's, give Size Consistency and Line Quality. Each line's
left edge, collected down the whole page, gives Margins: an edge that
steps in and out scores lower than one that holds steady. The vertical
gap between consecutive lines' centres feeds line-spacing rhythm.

**The whole page.** A few factors are not measured directly — they are
weighted blends of the ones above. Overall Neatness, for example, is
30% Size Consistency + 20% Word Spacing + 20% Margins + 15% Line
Straightness + 15% Slant. Legibility leans similarly on Letter Formation,
Size Consistency, Word Spacing and Baseline. Character Distinction is the
one factor that uses OCR's own confidence directly (a confident, easy
read implies clearly distinct letterforms) alongside how digit-heavy the
text is.

**What never depends on reading the words correctly:** stroke width,
glyph height, edge crispness, letter/word spacing, baseline tilt, line
straightness, margins, line spacing — every one of these comes from
pixel geometry and detected boxes, not from what the OCR engine thought
the letters said. **What does lean on it, as a secondary signal only:**
loop closure and the ascender/descender proxy (factor 6, the share of
tall/descending letters like b/d/f/h/k/l/t/g/j/p/q/y in the recognised
text), plus Character Distinction's confidence term. When OCR can't read
a page at all (see the cv-fallback path above), those specific
sub-signals fall back to a neutral default rather than failing the scan
— the geometry-only factors are unaffected either way.

## Repository layout

```
analyser/
  Vahini Analyser.html    the app (loads the packed engine bundle)
  src/                    browser client source. Edit here, then rebuild.
  scripts/core/           packed build (engine.bundle.js) + runtime helpers
  server/                 Python OCR + 20-factor scoring server and its tests
  styles/, static/        report CSS and printable pages
docs/                     architecture, build, CV algorithms, OCR notes
tests/                    headless Chrome e2e + fixtures
```

## Development

The client ships as one packed file. After editing anything in `analyser/src/`,
rebuild it (CI fails if it is out of date):

```bash
python analyser/build_bundle.py
```

Run the tests:

```bash
# Python server tests (no heavy paddle/torch install needed)
pip install -r analyser/server/requirements-core.txt
python -m unittest -v \
  analyser.server.tests.test_backends_classify \
  analyser.server.tests.test_server_pipeline \
  analyser.server.tests.test_regression_functional

# Headless Chrome report checks
npm ci && npx playwright install --with-deps chromium
npm run test:regression:headless

# Full recognition test against a running stack
docker compose up -d --wait
VAHINI_BASE_URL=http://localhost:8080 npm run test:recognition
```

CI runs all three suites on every push and pull request.

## Contributing and license

Contributions are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md). Please do
not commit real handwriting samples containing personal data; the CI fixtures
are synthetic.

Copyright (c) 2026 Vahini Technologies. Free software under
**AGPL-3.0-only**, see [LICENSE](LICENSE). If you run a modified version as a
network service you must offer its users the modified source.

- Patent: the dual-IMU handwriting-motion sensing method on ordinary paper is
  the subject of Indian Patent No. 584433.
- Trademark: "Vahini" and associated marks are not licensed under AGPL-3.0.
- Third-party components keep their own licenses, see
  [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) and [sbom.spdx.json](sbom.spdx.json).

## Contact

[vahinitech.com](https://vahinitech.com) · info@vahinitech.com
