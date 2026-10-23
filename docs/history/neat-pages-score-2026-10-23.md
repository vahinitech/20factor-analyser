# Does neat handwriting score high? (23 October 2026)

On 23 October students and teachers in the Guntur school pilot said that
some students with good, neat handwriting got low scores. The owner asked
for neat handwriting to score high, and for a fresh look at how much each
part of the score weighs, the line and spelling especially. This note is the
diagnosis and a proposal for the owner's approval. No score has changed.

**Short answer.** The weights are not the main problem. Five measurements
misread neat writing, joined writing above all, and no reweighting lifts a
neat page past the high 60s while they stay in. The neatest handwriting we
have (eight engraved model pages from two penmanship manuals) scores 58 to
82 today, and the analyser's own sample page 59. The fix is to leave the
broken measurements out of the overall until each passes a neat-page test,
and to fix the line measurement before the line gets more weight.

## How the overall is built today

`_section_scores()` in `backend/scoring.py` takes each section's mean over
its measured factors, then a weighted mean of the sections: Structure 0.30,
Spatial 0.30, Dynamics 0.20, Style 0.20. Dynamics (13 to 16) needs the pen,
so on a photo it is left out and the other three become 0.375, 0.375 and
0.25.

| Section | Factors |
|---|---|
| Structure | 1 Letter Formation, 2 Stroke Order, 3 Loop Closure, 4 Line Quality, 5 Size, 6 Ascender/Descender |
| Spatial | 7 Baseline, 8 Word Spacing, 9 Letter Spacing, 10 Margin, 11 Line Straightness, 12 Vertical Alignment |
| Style | 17 Slant, 18 Legibility, 19 Character Distinction, 20 Overall Neatness |

With all 16 photo factors measured, each one is worth exactly 6.25 points
of 100. Two of them are blends of others: Legibility (18) is 35% factor 1,
25% factor 5, 20% factor 8 and 20% factor 7, and Overall Neatness (20) is
30% factor 5, 20% factor 8, 20% factor 10, 15% factor 11 and 15% factor 17.
Following the blends through, a factor's real share of the overall is:

| Factor | Points of 100 |
|---|---|
| 5 Size | 9.7 |
| 8 Word Spacing | 8.8 |
| 1 Letter Formation | 8.4 |
| 7 Baseline, 10 Margin | 7.5 each |
| 11 Line Straightness, 17 Slant | 7.2 each |
| 2, 3, 4, 6, 9, 12, 19 | 6.25 each |

The line (7, 10, 11, 12) already carries 28.4 points. Spelling carries none.

A Free report shows five factors (1, 5, 7, 8, 18;
`backend/server/entitlements.py`), but its overall is the one above, from
all 16 (`report_contract.legacy_report` passes `analysis.overall` through).
So a family can see five good scores and a low number made mostly of
factors they cannot see.

## What drags neat pages down

Two sources. The 200 GNHK phone photos from 19 October
([real-photos-gnhk-2026-10-19.md](real-photos-gnhk-2026-10-19.md)), of
which 7 of the 37 rubric pages scored 22 or more of 25 by eye; those
scores came from analyser main at 4055c6f, before #168, #197, #199, #267
and #277 landed. And the current code replayed on the neat penmanship set,
the sample page and the 20 UJI clean pages (`benchmark.py`'s replay of the
kept reader output, no OCR models).

"Points lost" is how much the overall would rise if that one factor were at
full marks, averaged over the pages.

| Factor | What the code actually measures | Neat GNHK median | Penmanship median | Points lost, neat GNHK | Points lost, penmanship |
|---|---|---|---|---|---|
| 10 Margin | spread of line starts; 0 on 145 of 184 GNHK pages (#201, partly fixed since) | 0 | 93 | 6.1 | 1.9 |
| 8 Word Spacing | gaps between words; 0 on 78 of 165 GNHK pages (#168, #197 since) | 9 | 58 | 4.9 | 3.0 |
| 4 Line Quality | how much the **lines' lengths** differ (`width_cv`), not stroke smoothness | 41 | 78 | 4.1 | 2.1 |
| 5 Size | spread of small-letter heights; joined cursive reads as uneven | 51 | 35 | 3.0 | 4.5 |
| 6 Ascender/Descender | share of tall letters in the **words read**, unless the page is ruled | 72 | 10 | 2.9 | 5.3 |
| 7 Baseline | line slope against the photo's edges, plus words off their line | 63 | 56 | 2.6 | 2.1 |
| 9 Letter Spacing | gaps between letters; joined writing has none to measure | 71 | 50 | 2.4 | 3.4 |
| 11 Line Straightness | line slope against the photo's edges, plus wave | 70 | 64 | 2.0 | 2.1 |
| 3 Loop Closure | closed bowls; at 100 on 173 of 184 GNHK pages, so it tells pages apart only by what it costs the rare page it misses (#200) | 100 | 100 | 0 | 0 |
| 2 Stroke Order | from a photo, mostly the reader's confidence; floor of 54 | 88 | 92 | 1.0 | 0.6 |

The calibration tool (`scripts/calibrate.py`, #197) settles which of these
are scale problems and which are measurement problems. On the penmanship
set it finds that Size, Baseline, Word Spacing, Letter Spacing and Line
Straightness cannot be rescaled to put neat pages at 9 of 10 without
missing the planted mistakes they exist to catch. The measurement sees
mistakes on the neatest writing there is. Line Quality "passes" only with
a scale five times wider, which switches it off. Margin and Vertical
Alignment do pass with a new scale.

Two GNHK effects sit on top. On 4 of the 7 neat pages, 30% or more of the
words were marked printed and left out (#202), so they were scored on
fragments; #267 changed that rule since. And the reader reads joined,
engraved cursive in pieces (26 of 39 penmanship lines, #277), which is
where Size and Letter Spacing go wrong.

## Spelling

Confirmed: spelling does not enter the score. `VahiniCraft.checkSpelling`
(`frontend/src/engine/craft.js`, called from `report-render.js`) runs in
the browser on the words read, against a fixed list of 42 common
misspellings, and only adds a practice row. Nothing in `backend/scoring.py`
or `scoring_parts/` reads it. Factors 1, 2 and 19 do use the reader's
confidence in each word (72%, 20% and 75% of their formulas), so writing
the reader finds hard to read scores lower there, but that is legibility,
not spelling.

I would keep spelling out of the score. A child's misspelling and the
reader's misreading look the same in the text we get back (the penmanship
pages read at a 32% character error rate), so a spelling factor would mark
neat writers down for our reading errors.

## Ruled lines and the spiral binding

Same writer, same seed, same four sentences, on plain and on ruled paper:
40 UJI pages scored with the real scorer and known line boxes (no OCR).

| Factor | Median change, ruled minus plain | Pages moved 10 points or more | Worst |
|---|---|---|---|
| Overall | +2 | 1 of 40 | -17 |
| 6 Ascender/Descender | +16.5 | 29 | +93 (measured against the ruling, #194) |
| 9 Letter Spacing | +1 | 9 | -68 |
| 5 Size | +1 | 6 | -87 |
| 7 Baseline | 0 | 3 | -28 |
| 11 Line Straightness | 0 | 1 | -14 |
| 10 Margin, 12 Vertical Alignment | 0 | 0 | 0 |

So the printed lines do not move the margin or slope factors on these
pages, but on 9 of the 40 they knock Size or Letter Spacing down by 10
points or more, probably by counting a rule inside a line's box as ink. Only
factor 6 looks for the ruling (`vision/zone_analysis.find_ruling`); the
letter measurements do not take it out. These are made pages with known
boxes; on a real notebook photo the reader also has to find the lines past
the rules, which this test does not cover.

The spiral binding is untested: no page in any set has one. It sits outside
the written lines, so it should matter only if the reader takes it for a
line, and that needs a photo to check.

The bigger line problem is the camera. Baseline and Line Straightness take
each line's slope from its box against the photo's edges
(`features.py`, `line_slope_abs`). Margin corrects for the page's tilt
first (`_page_tilt_degrees`), the slope does not. Every degree a phone is
turned costs 1.25 of Baseline's 10 points and 1 of Line Straightness's,
level writing or not. The sample page's lines slope about 2 degrees in the
photo and it loses about 3.5 points of 100 to that alone. Raising the line's
weight before fixing this would punish the photo, not the writing.

## Reweighting alone

Before and after for three weightings. GNHK numbers are from the 19 October
factor scores, the rest from the current code. "Rho" is the rank
correlation with the rubric on the 37 pages; under about 0.33 it is within
chance.

| Set | Pages | Today | Free five, equal | Proposed, line 40 | Interim, line 30 |
|---|---|---|---|---|---|
| GNHK, all | 184 | median 62 | 54 | 71 | 72 |
| GNHK, neat by eye (22+ of 25) | 7 | median 63, lowest 47, 0 at 75+ | 56, 43, 1 | 67, 60, 3 | 69, 61, 3 |
| GNHK rho against the rubric | 37 | 0.11 | 0.23 | 0.16 | 0.13 |
| Penmanship (model handwriting) | 8 | 68 (58 to 82) | 58 (46 to 76) | 66 (54 to 82) | 67 (57 to 82) |
| Analyser sample page | 1 | 59 | 58 | 58 | 61 |
| UJI clean | 20 | 88 (71 to 92) | 88 (68 to 93) | 88 (75 to 94) | 88 (76 to 94) |

The two proposed columns are the weightings in the proposal below.

Every weighting leaves neat pages in the 60s, because the factors that
misread them (Size, Baseline, Line Straightness) are ones any sensible
weighting keeps. The rho differences are within chance on 37 pages rated
by one reviewer.

## Proposal

**1. A score out of 100 from the five measurements that work on a photo.**
Each factor scores 0 to 10, times its points, divided by 10. A factor that
is not measured on a page is left out and the rest are scaled to 100.

| Part | Factor | Points |
|---|---|---|
| Letter shapes | 1 Letter Formation | 30 |
| On the line | 7 Baseline | 25 |
| Even size | 5 Size | 20 |
| Level lines | 11 Line Straightness | 15 |
| Steady slant | 17 Slant | 10 |

Left out of the overall until each passes the neat test below, and still
shown in Pro as practice findings: 2, 3, 4, 6, 8, 9, 10, 12, 19. Also
left out: 18 and 20, which would count the same factors twice. Margin and
Word Spacing come back first, as each one's fix is in progress (#201,
#197). The line gets 40 points (Baseline and Line Straightness), up from
28, **but only after the slope is measured against the ruling or the
page's own tilt**; until then Baseline 20 and Line Straightness 10, with
the 10 points freed going to Letter Formation. Spelling stays at 0.

The practice plan should pick from the same five, so a neat child is not
sent to drill a skill that only a broken measurement found weak.

This makes neat pages fairer but does not yet make them score high: the
penmanship pages still land at 54 to 82. That needs the measurement fixes.

**2. Fixes, in this order.**

1. Slope against the ruling on ruled paper (the finder already exists for
   factor 6), against the page's median tilt otherwise.
2. Size on joined writing: the small-letter height of words the reader
   read in pieces (#277), and rules taken out of the ink.
3. Baseline's "words off the line": 17% to 43% of words flagged on five
   of the eight engraved model pages, where none are.
4. Neat print marked printed (#202) and the minimum evidence before a
   factor is scored (#47).
5. Line Quality from the strokes, as its name says, or retired.
6. Rescore the same 200 GNHK pages and the neat set after each one.

**3. What "neat handwriting scores high" means, as a test.** A neat
reference set that runs in `benchmark.py` on every pull request, with
these limits (the numbers are a proposal):

- Every page in the neat set scores 80 or more, the set's median 88 or
  more, and no factor in the overall under 7 of 10 on any page.
- The same page photographed straight and turned 3 degrees moves 3 points
  or less; the same writing on ruled and plain paper moves 3 points or
  less.
- The planted mistakes are still caught as often as
  `benchmarks/factors/expected.json` requires (`calibrate.py` checks this).
- On a mixed set ranked by a teacher, not by the assistant, the overall's
  rank correlation is 0.5 or more.

The neat set today is the eight penmanship pages. It needs 20 to 30 pages
written for it, with consent, by teachers and adult volunteers, in the
pilot's own notebooks (ruled, spiral-bound, phone photos). Never a child's
page: pilot pages are checked and deleted, not stored.

## A score children compare

A number out of 100 in a classroom becomes a ranking whether we mean it to
or not. Today that number can put a neat writer 20 points under a messier
classmate, which is worse in a class than at home: it teaches the wrong
lesson and the teacher stops trusting the check. The owner wants students
to use the tool to get better, not to beat each other. For the school
pilot I would show each student their own change since the last check and
the one skill to practise next, keep the five skills as bands (Strong,
Steady, Growing), and show no class ranking. The number can stay for the
family's own comparison once the neat test passes. That is a report format
change, so it is the owner's decision.

## How the numbers were made

- Current code: analyser main at 23768da. `scripts/benchmark.py`'s replay
  of `benchmarks/sample-page`, `neat-penmanship` and `uji-clean`, keeping
  every factor; `python scripts/calibrate.py --neat neat-penmanship`.
- Ruled and plain: `planted_pages.build_page(..., "clean", ruled=...)` for
  each of the 20 UJI test writers, seeds 1 and 2, scored with
  `scoring.build_analysis` as `variation_study.synthetic_pairs` does.
- GNHK: `results/pages-auto.tsv` and `sample40-auto.tsv` from the
  19 October run, in the data folder outside the repositories; the current
  overall was reproduced from the factor scores to within 1 point on all
  184 pages before any reweighting.
- No OCR model and no analyser container was run. GNHK was not rescored on
  current code: that needs the stage analyser, and another session's test
  analyser was running on the shared host. It is step 6 above.
