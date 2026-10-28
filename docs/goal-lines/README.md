# Goal-ready lines in the report (mock-up for the owner)

**Status: mock-up only, waiting for the owner's decision.** Nothing here
changes the shipped report, the tiers, the print or the shared PDF. The
report format baseline ([12-report-rules.md](../12-report-rules.md#report-format-baseline-owner-approval-required))
says the owner decides any change to the report's sections or per-tier
rendering, so this folder only shows the options.

## Why

A school therapist at Elmhurst Community Unit School District 205
(Illinois) printed a report on 27 October 2026 and said the free report was
enough. School therapists and teachers write measurable goals and progress
notes for children on support plans. A line they can paste into that
paperwork, built from what we measured, would make the report part of their
routine, and is something a district could pay for.

The idea: for each factor the report scores, one measurable line about the
page, for example "67 of 71 gaps between words were between half and twice
the page's usual word gap (94%)." Every line states only what the code
measures on that page. It never judges the child, never says who wrote the
page or why, and never sets a target: choosing the goal is the therapist's
professional call, and our counts have no tested norms behind them.

## Where the lines could appear

| Option | What changes | Print and PDF | Rules it touches |
|---|---|---|---|
| **A. Teacher card** (recommended) | A card above page 1, shown when the check page's "I am" is Teacher: one row per line with Copy, "Copy all", "How it was measured", and the skills with no line and why. | Unchanged: the card never prints. The print of the mock-up is pixel-identical to the shipped sample (same file hash). | A new screen-only part of the report for one audience; numbers on screen beside the report. |
| **B. Copy line in each row** | Under each "What your page shows" row, a dashed box with that row's lines and Copy. | Unchanged (hidden in print, pixel-identical). | Changes page 1 on screen for every reader; page 1 gets taller; numbers inside the report page. |
| **C. Third printed sheet** | A "For school records" sheet after page 2 with every line and how it was measured. | **Three A4 sheets** instead of two. | Breaks the two-A4 rule; numbers on paper. |

A keeps the two pages exactly as they are, keeps numbers away from the
child's and parent's view, and gives the therapist the one thing they need:
text to paste. B puts numbers in front of every family. C changes the page
count, which the baseline forbids without the owner's approval and
`tests/report-layout.mjs` holds.

## Screenshots

All from the analyser's own sample (`frontend/scripts/core/sample-report-data.js`,
the real run of `tests/fixtures/handwriting-sample.jpg`), rendered in the
website theme. Desktop is 1440 px wide; print is Chromium print media on A4.

| | Before (shipped) | After |
|---|---|---|
| All 20 factors, desktop | [before-pro-desktop.png](before-pro-desktop.png) | A: [after-a-pro-desktop.png](after-a-pro-desktop.png) · B: [after-b-pro-desktop.png](after-b-pro-desktop.png) · C: [after-c-pro-desktop.png](after-c-pro-desktop.png) |
| Free, desktop | [before-free-desktop.png](before-free-desktop.png) | A: [after-a-free-desktop.png](after-a-free-desktop.png) |
| Phone, 390 px | | A: [after-a-pro-phone.png](after-a-pro-phone.png) |
| Print, all 20 factors | [before-pro-print.png](before-pro-print.png) (2 sheets) | A and B: identical to before (2 sheets) · C: [after-c-pro-print.png](after-c-pro-print.png) (3 sheets) |
| Print, Free | [before-free-print.png](before-free-print.png) (2 sheets) | A: identical to before (2 sheets) |

The yellow tag on each proposed part is for this review only.

## The lines, factor by factor

Values are from the sample. "Sent today" says which field holds the number
in the report response; scoring inputs go to Pro only (`inputs` include),
while `measurements` go to every tier.

| # | Skill (report name) | Line on the sample | What it rests on (code) | Sent today |
|---|---|---|---|---|
| 5 | Letter size | Small letters were within 30% of the page's usual small-letter height in 75 of 84 words measured (89%). | Each word's small-letter height along its own baseline; off size at 30% or more from the page's median (`features.SIZE_OFF`, `words_off_size`, `size_count`). | Words measured: `basedOn`, all tiers. Share off size: scoring inputs, Pro. |
| 7 | Writing on the line | 80 of 87 words sat on their row's baseline, less than a third of a small-letter height above or below it (92%). | Each word's baseline against its row's; off at 0.35 small letters or more (`letter_geometry.WORD_DROP_LOOK`, `words_off_line`). | Share: scoring inputs, Pro. Words measured: **not sent** (see the note below). |
| 8 | Spaces between words | 67 of 71 gaps between words were between half and twice the page's usual word gap (94%). | Every word gap in the ink against the page's median gap; uneven under 0.5 or over 2 times it (`features.NARROW_WORD_GAP`, `ODD_GAP`, `word_gaps_odd`, `word_gap_count`). | Scoring inputs, Pro. |
| 10 | Where rows begin | Rows began on average 2.6% of the page width from the usual left edge, over 16 rows. | Mean distance of row starts from the median start, rows starting 15% of the width or more to the right left out as titles or dates (`features._margin_spread`, `left_spread`). | Scoring inputs, Pro. |
| 11 | Level rows | Rows sloped 2.1° on average over 16 rows; the steepest sloped 6.2°. | Each row outline's angle against level (`marked_places.page_measurements`, `slope.mean_deg`, `slope.line.angle`). A photo taken at an angle adds to every row. | `measurements`, all tiers. |
| 6 | Tall letters and tails | Over 16 rows, tall letters reached 1.5 times the small-letter height and tails reached 1.4 times (the guide the analyser uses is 2.0 times). | Ink above and below the small-letter band from each row's ink profile (`zoneProfile.ascenderReach`, `descenderReach`, `targetReach`). | Analysis, Pro. |
| 17 | Slant | The lean of the words varied by 13.5° (standard deviation) across the words measured. | Spread of each word's lean (`features._stroke_features`, `slant_std`). | Scoring inputs, Pro. A weak goal line: it needs a count of words leaning away from the page's usual, which is not computed yet. |

The Free report scores factors 1, 5, 7, 8 and 18, so a Free teacher card has
three lines (5, 7, 8). The full review has seven.

**Counts worked back from shares.** The server sends shares, and the counts
above are the share times its count: 9 of 84 words off size
(0.1071 × 84), 4 of 71 gaps uneven (0.0563 × 71). For writing on the line
the number of words measured is not sent at all; 7 of 87 is the only
whole-number pair up to 173 words that gives the share 0.0805 exactly, and
87 is also the page's word count. A build would send the counts themselves.

## Factors with no honest measurable line

| # | Skill | Why not |
|---|---|---|
| 1 | Letter shapes | The score is the text reader's confidence plus how much row heights vary. Neither counts letter shapes. |
| 19 | Clear letters | The text reader's confidence plus the share of digits. Not a count of letters a person could tell apart. |
| 2 | Stroke order | Letter widths and reader confidence. A photo cannot see stroke order. |
| 3 | Closed letters | Closed bowls found in the ink against the bowl letters (a, b, d, e, g, o, p, q) in the text the reader guessed, not matched letter by letter. On the sample the reader misread much of the page ("eviclc brown fox"), so the count of expected letters is unreliable. |
| 4 | Smooth lines | Built from how much row widths vary, not from the strokes. |
| 9 | Letter spacing | Counts exist (`letter_gaps_odd`, `words_spaced_off`) but the report labels this an estimate, the counts behind the shares are not sent, and it gives our own neat practice page its lowest mark (0.0). Leave it out until it passes the neat-page test. |
| 12 | Upright strokes | Measures how much row angles vary, not how upright the strokes are. A line about it would describe something else under this skill's name. |
| 18, 20 | Readability, Neat page | Blends of other scores with no count of their own. |
| 13 to 16 | Writing speed, Pen pressure, Smooth joins, Pen lifts | Need the Vahini sensor pen; a photo has no pen data. |

The reader's average confidence (71% on the sample) is also left out as a
line: a therapist would read it as a legibility percentage, which it is not.

## What the owner needs to decide

1. **Format:** A, B, C or none. Any of them is a report format change.
2. **Numbers on screen.** The 2026-10-23 rule keeps scores off the report.
   These lines are counts of what was measured, not scores, and option A keeps
   them off both pages and out of the student and parent views. They are still
   numbers beside the report, so it is the owner's call.
3. **Tier.** Free responses carry no scoring inputs today. Either the counts
   go to every tier, as `measurements` already do (Free gets its three lines),
   or the card is Pro only (a reason for a district to pay). Recommendation:
   counts for every tier, lines limited to the tier's factors, so a free check
   shows a therapist what the full review adds without hiding what Free
   already measures.
4. **Wording.** A therapist in the Americas would get American English
   (`strings/en-us.js`); Telugu would be a draft until the pilot school's
   teacher checks it.

## What a build would take, after approval

- **Server:** send the counts behind the shares (words measured and words off
  the line, words off size, uneven word gaps, rows off the margin without the
  current cap of two in `measurements.margin.off`), as measurements with no
  score, in the API schema; a new catalogue version for compact reports; the
  contracts tag before vahini-web takes the pin.
- **Renderer:** the card for "I am: Teacher", every sentence in each strings
  table, Copy using the clipboard only (nothing sent to Vahini).
- **Tests:** both reports still print on two A4 sheets in every language
  (`tests/report-layout.mjs`, `tests/report-parity.mjs`); each line's numbers
  equal the response; no line for the factors listed above; the card never
  prints and never shows in the student view.
- **Honesty:** the card says the counts describe one photographed page and
  are not a standard test or clinical assessment. The analyser's agreement
  with a teacher's rubric is weak today (Spearman 0.12 on 200 GNHK photos;
  analyser #325 adds a therapist agreement test), which is why every line
  says what was measured and nothing more. Same photo, same counts holds
  because the counts come from the same features as the scores.

## Opening the mock-up

`mockup.html` loads the shipped renderer and the sample, then
`goal-lines-mock.js` adds one option: `?option=a`, `b`, `c` or `none`, plus
`&example=free` for the Free report. It needs the bundle and the website's
`/site/` (design tokens, `site.js` for the drawings):

```bash
python frontend/build_bundle.py
mkdir -p /tmp/gl/site && ln -s "$PWD" /tmp/gl/an
for f in ../vahini-web/site/*; do ln -s "$(realpath "$f")" /tmp/gl/site/; done
ln -s "$(realpath ../vahini-web/site/js/site.js)" /tmp/gl/site/site.js
python3 -m http.server 4391 -d /tmp/gl
# then open http://127.0.0.1:4391/an/docs/goal-lines/mockup.html?option=a
```
