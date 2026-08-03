# Case studies: three writers, before and after practice

Three common handwriting problems, each shown as a before/after pair of
real analyser runs — the kind of arc a parent or teacher sees over a few
weeks of the prescribed drills.

**No real children appear here.** The repo forbids committing real
handwriting with personal data (CONTRIBUTING.md) and forbids inventing
scores in docs (CLAUDE.md), so each "page" is synthetic geometry built to
portray one habit, and every number is genuine output of the real engine
(`build_analysis()` in `backend/scoring.py`). The raw responses sit in
[`examples/`](examples/) and regenerate deterministically:

```bash
pip install -r backend/requirements-core.txt
python docs/examples/generate_examples.py
```

The personas are illustrative; the *measurements and scores are not* —
they are exactly what the engine reports for pages written these ways.
This is education and skill-building material, not a diagnostic claim.

---

## Case 1 — The sinking baseline

*A nine-year-old copies homework onto unruled paper. Every line starts
level and slides downhill; some lines slide more than others.*

The "before" page writes each line with a slope around 3.6° and a wide
spread between lines. The report's baseline note reads: *"Lines tend to
keep sinking by about 2.6 degrees left to right"* — with its standing
caveat that a tilted photo shows the same signature.

Four weeks of the prescribed drills — *"Underline / baseline tracing on
ruled sheets"* (factor 7's tip) and *"Ruled-sheet practice; pause at the
right margin to reset to the line"* (factor 11's) — then a rescan:

| | Before | After |
|---|---|---|
| **Overall** | **80** | **90** |
| #7 Baseline Alignment | 5.4 | 8.6 |
| #11 Line Straightness | 6.3 | 8.9 |
| #12 Vertical Alignment | 6.5 | 9.5 |
| #17 Slant Consistency | 7.0 | 9.6 |
| #10 Margin Discipline | 4.1 | 6.9 |
| Measured drift | sinking 2.6° | sinking 1.1° |

Why five factors moved from one habit: baseline drift, line
straightness, tilt spread and slant all read the same line-angle
geometry from different directions, and the margin measurement improves
because the page-tilt correction no longer has a large sinking signal to
fold into the left edge (see the audit note in
[`example-report.md`](example-report.md)). Deterministic scoring makes
that chain inspectable instead of mysterious.

Full JSON: [before](examples/case1-baseline-before.json) ·
[after](examples/case1-baseline-after.json)

---

## Case 2 — Words crowding together

*A twelve-year-old writes fast before the school bell. Word gaps
collapse to nothing in places and gape in others; the OCR detector
splits every written line into ragged fragments.*

This is the case where one habit floods the whole report. The gaps are
erratic enough that each row is detected as three separate segments, so
the geometry every spatial factor reads is fragmented:

| | Before | After |
|---|---|---|
| **Overall** | **76** | **92** |
| #8 Word Spacing | 5.6 | 10.0 |
| #10 Margin Discipline | 0.0 | 8.2 |
| #4 Line Quality (Smoothness) | 4.7 | 8.9 |
| #13 Speed Consistency | 5.0 | 9.0 |
| #9 Letter Spacing | 6.9 | 9.2 |
| #16 Pen Lift Frequency | 7.4 | 9.3 |
| #20 Overall Neatness | 6.4 | 9.2 |

Margin Discipline reads 0.0 before practice not because the child's
margin is that bad, but because the left-edge statistic sees every
fragment's left edge, and fragments start mid-page. That is honest,
inspectable behaviour of the current geometry — the criteria doc states
it plainly — and it disappears the moment the writing itself heals: on
the "after" page the gaps are regular (the drill: *"'word␣␣word'
spacing drill — one finger gap between words"*), the detector returns
whole lines again, and Word Spacing's 10.0 means exactly "no gap
irregularity wide enough to split any line".

Full JSON: [before](examples/case2-spacing-before.json) ·
[after](examples/case2-spacing-after.json)

---

## Case 3 — Everything written in one size

*An adult learner writes fast, small and flat: tall letters barely rise
above the middle zone, tails barely hang below, pressure heavy and
uneven, left margin wandering.*

The three-zone rule (coaches' 1:2 proportion) is measured directly from
ink here, and it names the habit. The before page's factor 6 evidence:
ascenders reach **1.27x** and descenders **1.18x** the x-height against
the 2.0x target — flagged **single-zone**, the classic
everything-in-the-middle mistake. Score: 2.7/10.

After the drills — *"Tall–short pattern drills (bl bl bl)"*,
*"Margin-box writing"*, *"Same-pressure line drills"* — the rescan
measures reach at 1.89x and 2.14x, and the flag clears:

| | Before | After |
|---|---|---|
| **Overall** | **81** | **91** |
| #6 Ascender / Descender Control | 2.7 | 9.8 |
| #14 Pressure Consistency | 5.5 | 8.7 |
| #10 Margin Discipline | 4.5 | 7.2 |
| #5 Size Consistency | 7.7 | 8.8 |
| Ascender reach (target 2.0x) | 1.27x | 1.89x |
| Descender reach (target 2.0x) | 1.18x | 2.14x |
| Zone flags | single-zone | none |

Note what did *not* move: loop closure, slant, baseline and word
spacing stay in the same bands across both scans. A factor only moves
when its own measurement moves — there is no halo effect from an
overall impression, because there is no overall impression: only
per-factor geometry.

Full JSON: [before](examples/case3-size-margin-before.json) ·
[after](examples/case3-size-margin-after.json)

---

## Reading these arcs

- The engine is deterministic: rescanning the same page reproduces the
  same score, so a moved score means the writing moved. That is what
  makes before/after tracking meaningful (see README, "Why deterministic
  computer vision").
- Every drill quoted above is the factor's own `tip` field from the
  report — the practice plan is generated from the same measurements as
  the scores.
- The full factor definitions, formulas, targets and band cut-offs are
  in [`scoring-criteria.md`](scoring-criteria.md).
