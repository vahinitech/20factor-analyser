# Scoring criteria: the 20 factors, targets and bands

What the analyser scores, how each score is computed, and where the
cut-offs sit. Everything on this page is read from the code, not
described from memory: sections and weights from `_SECTIONS`, factor
definitions from `_FACTOR_META` / `_FACTOR_EXTRAS`, formulas from
`_score_factor_map()` and `build_analysis()` — all in
`backend/scoring.py` — and the zone rule from `backend/zone_analysis.py`.
If this page and the code ever disagree, the code wins; please file an
issue.

A worked report using these criteria is in
[`example-report.md`](example-report.md); before/after arcs in
[`case-studies.md`](case-studies.md). How the underlying pixel
measurements are made is a separate walkthrough:
[`computer-vision-algorithms.md`](computer-vision-algorithms.md).

## Sections, weights and the overall score

Each factor scores 0-10. A section's score is the plain average of its
factors; the overall 0-100 score is the weighted average of the section
scores:

| Section | Weight | Factors |
|---|---|---|
| Structure — letter shapes, size & control | 30% | 1-6 |
| Spatial — spacing, baseline & layout | 30% | 7-12 |
| Dynamics — speed, pressure & flow | 20% | 13-16 |
| Style & Readability — slant, legibility & neatness | 20% | 17-20 |

## Bands

Four bands, one threshold set for the whole report (`_band()`):

| Band | Range (0-10) |
|---|---|
| strong | ≥ 8.5 |
| good | 7.0 - 8.4 |
| developing ("dev") | 4.5 - 6.9 |
| focus | < 4.5 |

## The 20 factors

The measurement inputs are the OCR layer's detected lines (box, corner
polygon, recognized text, confidence) plus the page image. "CV" below is
the coefficient of variation (spread ÷ mean): 0 means perfectly
consistent. Each formula clamps to 0-10; `min(1, x/limit)` means the
score falls linearly and hits zero at the stated limit.

| # | Factor | What is measured | Score (0-10) | Report target |
|---|---|---|---|---|
| 1 | Letter Formation Accuracy | shape regularity proxy: recognizer confidence + letter-height consistency | `7.2·conf + 2.8·(1 − height CV)` | shape dist ≤0.10 |
| 2 | Stroke Order Consistency | stroke order proxy: char-width consistency + confidence | `5.4 + 2.6·(1 − char-width CV) + 2.0·conf` | edit dist ≤2 |
| 3 | Loop Closure | share of loop-bearing letters (a o d p e g q) among letters read | `10 · min(1, loop share / 0.28)` | ≥95% closed |
| 4 | Line Quality (Smoothness) | stroke smoothness proxy: line-width consistency | `10 · (1 − min(1, width CV / 0.8))` | jitter ≤0.5 px |
| 5 | Size Consistency | letter-height consistency across lines | `10 · (1 − min(1, height CV / 0.65))` | height CV ≤0.12 |
| 6 | Ascender / Descender Control | **measured** three-zone reach when the page supports it, else tall-letter-share proxy | see "The three-zone rule" below | ratio err ≤0.15 |
| 7 | Baseline Alignment | mean absolute line angle | `10 · (1 − min(1, mean °/ 8))` | RMS ≤0.08 x-h |
| 8 | Word Spacing | consistency of gaps between detected segments sharing a row, in x-heights | `10 · (1 − min(1, gap CV / 1.4))` | ≈1.0 x-h, CV ≤0.25 |
| 9 | Letter Spacing | intra-word spacing proxy: char-width consistency | `10 · (1 − min(1, char-width CV / 1.2))` | gap CV ≤0.30 |
| 10 | Margin Discipline | left-edge consistency after page-tilt correction | `10 · (1 − min(1, left CV / 0.55))` | left CV ≤0.05 |
| 11 | Line Straightness | mean absolute line angle (looser limit than #7) | `10 · (1 − min(1, mean °/ 10))` | drift ≤1° |
| 12 | Vertical Alignment | line-to-line tilt spread | `10 · (1 − min(1, angle std / 10))` | tilt CV ≤0.20 |
| 13 | Speed Consistency | speed proxy from stroke/line-width regularity | `10 · (1 − min(1, width CV / 0.85))` | velocity CV ≤0.20 |
| 14 | Pressure Consistency | pressure proxy from ink-density variance across lines | `10 · (1 − min(1, ink CV / 0.95))` | CV ≤0.20 |
| 15 | Stroke Continuity | continuity proxy from word morphology (letters per word vs 5) | `10 · (1 − min(1, |chars/word − 5| / 5))` | 0 unintended breaks |
| 16 | Pen Lift Frequency | pen-lift proxy from segmentation (char-width consistency) | `10 · (1 − min(1, char-width CV / 1.4))` | ≤0.3 lifts/char |
| 17 | Slant Consistency | page-level tilt variability line to line | `10 · (1 − min(1, angle std / 12))` | angle CV low |
| 18 | Legibility Score | composite of other factors | `0.35·F1 + 0.25·F5 + 0.20·F8 + 0.20·F7` | even & clear |
| 19 | Character Distinction | separability proxy: confidence + non-digit share | `7.5·conf + 2.5·(1 − min(1, digit share / 0.5))` | clear letter pairs |
| 20 | Overall Neatness | layout composite | `0.30·F5 + 0.20·F8 + 0.20·F10 + 0.15·F11 + 0.15·F17` | weighted variance |

Every factor's report card also carries a `basedOn` count (how many
letters/words/lines fed it) and an evidence sentence naming the
measurement.

### The three-zone rule (factor 6)

Handwriting coaches teach letter size as a 1:2 proportion across three
vertical zones: a `t` stands two x-heights tall, a `g` hangs two deep.
When the page has enough Latin letters, factor 6 is scored from
measured ink geometry (`zone_analysis.py`): per line, the densest
horizontal band of ink is the middle zone (x-height); topmost and
bottommost meaningful ink give the ascender/descender extents; reach =
(zone + middle) / middle, target 2.0.

- Full credit within ±0.35 of 2.0; zero credit at an error of 1.0 or
  more; up to 2 points off when reach varies line to line.
- Named flags for the coaches' three classic mistakes: `single-zone`
  (reach < 1.35), `upper-heavy` / `lower-heavy` (reach > 3.2).
- Pages that can't support the measurement fall back to a tall-letter
  share proxy, and the report's `zoneProfile.method` field says which
  path produced the numbers, and why.

## Honesty rules — what a score does and doesn't claim

- **From a photo, Dynamics (13-16) are proxies.** True speed, pressure
  and pen lifts are motion, not ink; the static-ink proxies above stand
  in for them. The dual-IMU sensor pen measures them directly, and the
  report marks pen-measured factors (`imuMeasured`).
- **Some factors lean on OCR text**: loop closure (#3), the factor-6
  proxy path and character distinction's confidence term. The rest is
  pure geometry and survives OCR being wrong or unavailable.
- **Slant (#17) is page-level tilt variability**, not a per-letter
  cursive-lean angle; loop closure is letter-share, not per-letter
  contour tracing. Both simplifications are stated in
  [`computer-vision-algorithms.md`](computer-vision-algorithms.md).
- **Fragmented detection hurts spatial scores.** Word Spacing reads the
  gaps between detected segments on one row, so a line detected whole
  shows no measurable gap irregularity (scores 10); a page whose gaps
  split detection also drags Margin Discipline down, since fragments'
  left edges start mid-page. Case 2 in
  [`case-studies.md`](case-studies.md) shows both sides of this.
- **Sinking writing vs a tilted photo are indistinguishable** from line
  geometry alone; the report prints that caveat next to the baseline
  drift note, and the margin measurement shares the coupling (audit
  note in [`example-report.md`](example-report.md)).
- **Two of the coaches' eight questions are never faked**: posture and
  page-to-page endurance appear with an honest note instead of a number
  unless the pen / a multi-page assessment measures them.
- **Determinism over models.** The same page always produces the same
  score — the reason progress tracking works. Where a model helps
  (reading messy words), it labels text and never decides a score.
- **Not a diagnostic tool.** Education and skill-building only: no
  medical, psychological or personality claims. The one graphology card
  in the coach tips is labelled folklore, for fun, and feeds no score.
