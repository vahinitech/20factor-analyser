# Example report, walked through page by page

This is a complete 20-factor report for one handwriting page, shown here
so you can judge what the analyser delivers before installing anything.

**Every number on this page is real scorer output, not marketing copy.**
The repo forbids committing real handwriting with personal data
(CONTRIBUTING.md) and forbids inventing scores in docs (CLAUDE.md), so the
page behind this report is synthetic: a script builds the line geometry
and ink of a plausible writer — a competent hand whose baseline sinks,
whose ascenders stop short, and whose left margin wanders — and feeds it
to the real engine, `build_analysis()` in `backend/scoring.py`. The raw
response is committed next to this file. Reproduce it yourself:

```bash
pip install -r backend/requirements-core.txt
python docs/examples/generate_examples.py   # deterministic, fixed seed
```

Full JSON: [`examples/example-report.json`](examples/example-report.json).
The rendered PDF (from `frontend/src/report/report-render.js`) lays these
same numbers out with evidence crops from the scanned page; the page
order below is the renderer's.

## Page 1 — Scorecard

**Overall: 84 / 100** — the weighted average of four sections.

| Section | Weight | Score |
|---|---|---|
| Structure — letter shapes, size & control | 30% | 83 |
| Spatial — spacing, baseline & layout | 30% | 82 |
| Dynamics — speed, pressure & flow | 20% | 87 |
| Style & Readability — slant, legibility & neatness | 20% | 87 |

Every factor lands in one of four bands (cut-offs in
[`scoring-criteria.md`](scoring-criteria.md)): **strong**, **good**,
**developing**, **focus**.

Strongest factors on this page: Loop Closure 10.0, Word Spacing 10.0,
Stroke Order Consistency 9.4, Slant Consistency 9.4.

The three factors most worth practising, ranked weakest first:

| # | Factor | Score | Band |
|---|---|---|---|
| 10 | Margin Discipline | 4.5 / 10 | developing |
| 6 | Ascender / Descender Control | 5.5 / 10 | developing |
| 7 | Baseline Alignment | 7.9 / 10 | good |

## Page 2 — Your writing, in plain words

Coaches score a page by asking eight plain questions. The report answers
six of them from measurements and leaves a column for the writer's own
marks; the two aspects a single scan cannot see get an honest note
instead of a number.

| Question | Measured |
|---|---|
| Are my letters the right shape, and closed where they should be? | 9.2 — strong |
| Are my letters the same size? Do tall letters stand tall and tails hang below? | 6.8 — developing |
| Do my words and letters have enough room? Did I leave a margin? | 7.8 — good |
| Does my writing sit on the line and stay straight across the page? | 8.5 — good |
| Are my strokes smooth and steady, not shaky or pressed too hard? | 8.6 — strong |
| Can someone else read my page easily? | 8.7 — strong |
| How do I sit and hold the pen while writing? | *Not visible in a scan. The Vahini pen senses it through pen-angle steadiness.* |
| Does my writing stay the same after two or three pages? | *Scan 2-3 pages as one assessment to measure this (endurance).* |

## Page 3 — Where exactly to improve

Each of the top three factors gets a concept drawing, a crop of the
writer's own page as evidence, and one drill. What the engine reported
for this page, quoted from the JSON:

**#10 Margin Discipline — 45%, target: left CV ≤ 0.05.**
Measured over 10 lines from left-edge consistency.
Drill: *"Margin-box writing — keep an even left edge down the page."*

**#6 Ascender / Descender Control — 55%, target: ratio err ≤ 0.15.**
Evidence: *"Measured zone bands over 10 lines: ascenders reach 1.3x,
descenders reach 2.5x the x-height (the 1:2 rule targets 2.0x). Flags:
single-zone."* The 1:2 rule is the coaches' three-zone proportion — a
`t` should stand two x-heights tall, a `g` hang two deep. This writer's
tall letters stop at 1.3x: the classic squashed-into-one-zone habit.
Drill: *"Tall–short pattern drills (bl bl bl) to train ascenders and
descenders."*

**#7 Baseline Alignment — 79%.**
Evidence: *"Direction: sinking ~1.9 deg across the page."* The report
also carries the honest caveat that a tilted photo shows the same
signature: *"scan flat to be sure."*

An audit note worth seeing: the sinking baseline and the low margin
score are coupled. The engine corrects the page for camera tilt before
measuring the margin, and writing that genuinely sinks is
indistinguishable from a level page photographed at an angle — so the
correction spreads some of the drift into the left-edge measurement.
The report says what it measured and how; nothing is hidden behind a
model. That traceability is the point of deterministic scoring.

## Page 4 — Coach's corner

The tip engine (`backend/coach_tips.py`) ranks its lesson library
against this page's measurements and keeps the top few, each with a
`why` naming what earned it the slot. This page drew:

- **Improve your writing speed** — three habits: write from memory
  rather than word-by-word copying, short timed sprints, read more.
- **The 10 letters that improve your handwriting** — shown *"because
  this page has 38 words ending in the ten finishing letters"* (A D H I
  L M N R T U end on a downstroke; finish them with a small upward
  flick).
- **Five letters, one c: the rhythm secret** — a, d, g, q, o are all
  built on the same c; keep that c identical and words gain rhythm.
- **Just for fun: the letter n** — an old graphology reading, labelled
  as folklore: *"None of your scores use it; the 20 factors measure the
  writing, never the writer."*

The report also diagnoses which leg of the skill is short — Techniques,
Interest or Practice. Here: **practice** (technique 8.5, practice 8.4,
interest honestly marked *"not measurable from a photo"*).

## Page 5 — Reference values, read like a lab report

All 20 factors with the published target next to each measurement.
Scores are 0-10; the scorecard shows them as percentages.

| # | Factor | Score | Band | Target ("good hand") | Based on |
|---|---|---|---|---|---|
| 1 | Letter Formation Accuracy | 8.6 | strong | shape dist ≤0.10 | 382 letters |
| 2 | Stroke Order Consistency | 9.4 | strong | edit dist ≤2 | 90 words |
| 3 | Loop Closure | 10.0 | strong | ≥95% closed | 382 letters |
| 4 | Line Quality (Smoothness) | 8.3 | good | jitter ≤0.5 px | 10 lines |
| 5 | Size Consistency | 8.2 | good | height CV ≤0.12 | 382 letters |
| 6 | Ascender / Descender Control | 5.5 | dev | ratio err ≤0.15 | 382 letters |
| 7 | Baseline Alignment | 7.9 | good | RMS ≤0.08 x-h | 10 lines |
| 8 | Word Spacing | 10.0 | strong | ≈1.0 x-h, CV ≤0.25 | 90 words |
| 9 | Letter Spacing | 9.0 | strong | gap CV ≤0.30 | 382 letters |
| 10 | Margin Discipline | 4.5 | dev | left CV ≤0.05 | 10 lines |
| 11 | Line Straightness | 8.3 | good | drift ≤1° | 10 lines |
| 12 | Vertical Alignment | 9.3 | strong | tilt CV ≤0.20 | 10 lines |
| 13 | Speed Consistency | 8.4 | good | velocity CV ≤0.20 | 10 lines |
| 14 | Pressure Consistency | 8.6 | strong | CV ≤0.20 | 10 lines |
| 15 | Stroke Continuity | 8.5 | good | 0 unintended breaks | 90 words |
| 16 | Pen Lift Frequency | 9.2 | strong | ≤0.3 lifts/char | 90 words |
| 17 | Slant Consistency | 9.4 | strong | angle CV low | 10 lines |
| 18 | Legibility Score | 8.6 | strong | even & clear | 10 lines |
| 19 | Character Distinction | 8.9 | strong | clear letter pairs | 382 letters |
| 20 | Overall Neatness | 8.0 | good | weighted variance | 10 lines |

From a photo, the four Dynamics factors (13-16) are proxies read from
the static ink — stroke-width regularity, ink-density variance, word
morphology. The sensor pen replaces them with direct IMU measurement.
The style check also ran here: this page is 100% print (no cursive
joins), so the mixed-style warning stayed silent.

## Page 6 — Practice plan and prediction

The plan groups the three focus factors' drills — for this page,
**Frame the page** (*"tidy margins and a straight baseline"*, factors 10
and 7) and **Oval & circle roll** (*"even, rounded, same-size letters"*,
factor 6) — prescribes short daily sets, and predicts how many practice
tries typically reach the next milestone, baselined off the same
corrected overall score (`frontend/src/engine/forecast.js`). Rescanning
after a few days of practice moves the measured columns — see the
before/after arcs in [`case-studies.md`](case-studies.md).
