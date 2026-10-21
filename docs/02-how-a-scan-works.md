# How a scan works: reading, measuring, confidence and the marked places

This is the path one photo takes through the analyser, written from the code.
Every statement names the function and file it comes from. Line numbers are
at commit `fbb4909`; when they drift, the function names still find the code.
[05-computer-vision-algorithms.md](05-computer-vision-algorithms.md) explains the
same techniques for a general reader. This page is the precise version, and
it is the one to update when the code changes.

The five free skills are the thread through it: Letter Formation (1), Size
Consistency (5), Baseline Alignment (7), Word Spacing (8) and Legibility (18)
(`FREE_FACTORS`, `backend/entitlements.py:14`).

## 1. From upload to a picture we measure

| Step | What happens | Code |
|---|---|---|
| Size limits | Request body over 6 MiB refused; file over 5 MiB refused (413) | `upload_limits.py:12-53`, `_read_upload` in `ppocr-server.py:183-187` |
| Busy server | No free scan slot: 503 with `Retry-After` | `scan_slots.py:61-70` |
| Decode | JPEG, PNG, WebP; PDF uses page 1 only, drawn at 150 DPI | `computer_vision.to_numpy`, `computer_vision.py:39-99` |
| Turn upright | The phone's EXIF orientation is applied, then RGB | `computer_vision.py:84` |
| Shrink | Longest side at most `VAHINI_OCR_MAX_SIDE` (2200 by default, never under 960), LANCZOS. The website's stage compose file sets 2600; production uses the default | `config.py:96-98` |
| Repeat answers | The same bytes within 180 s get the stored answer | `cache.py`, key built at `ppocr-server.py:835-840` |

The shrunk, upright picture is the **processed image**. Every box in a report
(`bbox`, `source_size`, `coordinate_space: "processed-image"`) is in its
pixels, not the original photo's.

There is no deskew. The page's tilt is estimated only to correct left edges
for Margins, factor 10 (`_page_tilt_degrees`, `scoring_parts/page.py:15-32`).

## 2. Reading the page: lines, then handwriting only

**Finding text lines.** PaddleOCR always runs first (`recognizer.collect_lines`,
`recognizer.py:143-215`). Its detector (`PP-OCRv5_mobile_det`) draws one
four-corner polygon around each line of text, and its recogniser reads the
line (`en:PP-OCRv5_server_rec`, Telugu `te_PP-OCRv5_mobile_rec`;
`config.py:70-115`). Each result becomes a line record:
`{text, poly, box, score, lang, printed_hint}` (`ocr_backends.run`,
`ocr_backends.py:373-470`).

**The detector gives one box per line.** There are no word boxes and no letter
boxes from OCR. Anything finer than a line is measured from the ink itself
(section 3).

**Picture variants.** Up to two versions of the page are tried: the photo as
taken, then a grey, contrast-stretched, sharpened copy (denoised and
equalised when advanced preprocessing is on). Other variants exist (a
thresholded copy, a 1.8x enlargement) but `max_variants` is 2 by default
(`detector.variants`, `detector.py:25-100`; `config.py:85-87`).

**Other engines** are chosen by the `VAHINI_OCR_BACKEND` setting, never by load
(`config.py:20, 60-69`; default `paddle`). `trocr` and `hybrid` re-read the
words of each handwriting line and change only the text, never a box; a
re-read is kept when it agrees with Paddle by 0.70 or its own confidence is
0.75 or more (`recognizer.py:234-329`, `config.py:140-143`). `surya` and
`paddleocr-vl` replace Paddle's lines when they find any.

**Keeping only handwriting**, in this order (`recognizer.extract_hand_lines`,
`recognizer.py:332-358`):

1. Repeated readings removed and lines sorted top to bottom
   (`detector.merge_lines`). Two boxes overlapping by more than half are
   one line whatever they say (the two image variants read "seeta" and
   "seetha" for one line on a UJI test page, and it was scored twice); a
   box mostly inside another is the same line when the texts agree or one
   is part of the other, and a whole line then replaces a piece of it
   read on its own.
2. Tiny low-confidence fragments, wide header and footer strips that look
   printed, and long number strings dropped
   (`detector.region_filter_lines`). A wide line in the top 14% of the
   photo used to go when it was read confidently, printed or not, which
   dropped the first handwritten line of most UJI test pages.
3. Pictures, charts, stamps and seals found by a layout model
   (PP-DocLayout-M) removed: a line goes when 60% of it lies inside one
   (`layout_filter.py:46-69, 195-209`). The scan waits for that model to load,
   so a busy server reads the same page the same way.
4. Printed or handwritten, per line (`classify.classify_lines`,
   `classify.py:308-399`). The probability of print is
   `0.58 x shape + 0.42 x text`:
   - shape: how even the stroke width is, how even the letter heights are,
     and how crisp the edges are, from an Otsu ink mask (`classify.py:232-268`);
   - text: a very confident OCR reading, form words ("Name", "Date"), capitals
     and digits (`classify.py:193-229`).
   A line at 0.58 or above is printed (`PRINTED_THRESHOLD`, `classify.py:46`).
   Note one rule here: a line read with OCR confidence 0.93 or more, six or
   more characters and even strokes is treated as printed on any page
   (`classify.py:388-394`). Very neat handwriting can be removed by it.
5. Lines shorter than two characters, or with no letters or digits, dropped.
6. The pieces of each written line joined into one line
   (`detector.join_row_pieces`). Rows are anchored on the widest pieces; a
   piece joins a row when it overlaps the anchor in height by 60% of the
   shorter one and their middles are within 35% of the taller one's height.
   A piece over ink the row already holds is a second reading and is
   dropped, and a row is cut where two pieces are more than four line
   heights apart, so two columns stay apart. One UJI page gave ten pieces
   for four lines.

Between steps 3 and 4, **writing the detector missed is read again**
(`line_recovery.py`). The detector finds no box at all for some closely
written lines (the first or last line of several UJI pages, or a line's
middle words). Ink outside every found line's box, joined into word-sized
blobs at least 1.2 line heights wide, is cropped and read by the scan's
own engine, detection and recognition, which finds the words on a crop
around one line; when it finds none, the recogniser reads the crop as one
line. A word is kept when it holds at least two letters, was read at 0.60
or more, is at most 1.5 lines tall and its middle lies outside every
found line. A reading of one letter at low confidence does not count as a
found line, so it cannot hide the writing under it. Two rounds: the second
reads what the first left unread. Recovered words are classified like any
line but do not change the page's own evidence of print (step 4's
letterhead and form rules), and step 6 joins them to their line. All of it
depends only on the photo, so the same photo gives the same lines.
**What the visitor sees when this fails**

| Case | Result | Code |
|---|---|---|
| Lines found, all printed | `no_handwriting` screen; not counted against the daily limit | `ppocr-server.py:633-648, 876-879` |
| OCR engine failed | 503 `ocr_unavailable`; the page says try again. Never a score from a broken read | `ppocr-server.py:649-652` |
| OCR ran and found nothing | Lines are found from ink alone (`cv-fallback`) and the report is made without the skills that need reading | `computer_vision.fallback_line_regions`, `computer_vision.py:166-248`; `ppocr-server.py:653-661` |
| Still nothing | `no_handwriting`, "No handwriting found" | `ppocr-server.py:662-676` |
| Asked for as Telugu (`lang=te`), and fewer than three in four letters read are Telugu, or the reader's mean confidence is under 0.80 | `handwriting_not_read` screen; not counted against the daily limit. The Telugu reader returns Latin fragments on handwriting, so no report is made from them | `recognizer.telugu_not_read` |
| Digits and maths signs are 35% or more of the letters, digits and signs read (at least 12 of them): a maths or science page | `not_writing_page` screen, "write four lines of English"; not counted against the daily limit | `recognizer.not_writing_page` |

**When the family typed the passage**, each read line whose text is at least
45% similar to a passage line takes the passage text instead
(`recognizer.align_to_expected`, `recognizer.py:361-416`). That happens before
scoring, so word counts come from the passage.

**Rows from the ink instead of the reader's lines.** Two kinds of page are
not measured on the reader's line boxes as they come. The response says
which in `analysis.recognition`: `ink_rows` is true and `ink_reason` says
why.

- `language`: the check asked for a language named in
  `VAHINI_INK_GEOMETRY_LANGS` (Telugu; empty by default). Rows, baselines,
  letter sizes and, with a passage, word gaps come from the ink alone
  (`ink_geometry.find_rows`); nothing is read. The factors that need what
  was read (1, 2, 3, 9, 17, 18, 19) are "Not measured".
- `read_in_fragments` (#277): the reader read the page in pieces. Joined
  cursive comes back as short pieces ("Thi", "cmen") with the rest of each
  row unread, and the factors used to be measured on the pieces' boxes.
  After step 6 the reader's handwriting lines are grouped into rows (lines
  overlapping in height by 45% of the shorter one), each row is widened to
  the ink on it (blobs whose middle lies within 0.6 of a line of the row's,
  leaving out ink inside the lines the reader found printed, such as a
  form's words beside the writing),
  and the reader's numbers are compared with the rows
  (`ink_geometry.fragment_rows`). The page is read in pieces when it has
  two rows or more and any of: the reader's boxes span under 60% of the
  rows' ink width, the median row holds three boxes or more, or half the
  boxes or more are under half their own row's ink width. Such a page is
  measured on the widened rows, each carrying its pieces' text and mean
  confidence, by the same measures as any read line (sections 3 and 9);
  the reader's own lines still give the text, the passage match and the
  recognition block. Rows nothing was read on are not measured. To keep
  the cost down, a page whose median row holds fewer than three lines,
  none under half the widest, the widest spanning 60% of the page or
  more, is taken as read whole without looking at its ink. So is a page
  where the reader found as many printed lines as handwriting lines or
  more: a form written on, whose unread ink is mostly print.

The thresholds are the `FRAGMENT_*` constants in `ink_geometry.py`.
`scripts/benchmark.py fragments` prints each benchmark page's numbers
against them, and CI fails if a page of a real-handwriting set would be
read in pieces.

## 3. Measuring inside a line: ink components

To see words and letters inside a line box, the analyser looks at the ink
(`_line_ink_components`, `computer_vision.py:643-699`):

1. Cut the line out, turn it grey, blur it slightly (3x3).
2. Adaptive threshold, with a window 0.6 times the line's height, so a big
   photo and a small one behave the same.
3. Connected components (8-neighbour): each separate blob of ink. Blobs
   smaller than 0.06% of the line's area are noise and dropped.
4. Each blob is a box `(x, y, w, h)` in processed-image pixels, left to right.

A line under 16 pixels tall is not measured this way, because the letters
blur together and the answer would be wrong rather than missing.

Joined-up writing gives about one blob per word; print gives about one per
letter. **Word gaps** come from this (`line_word_gaps`): only blobs whose
middle lies between 20% and 85% of the box's height count, since a line box
reaches into its neighbours and a tail from the line above is not a word;
blobs that overlap left to right are merged (the dot of an i, the bar of a
t), and the widest `words - 1` spaces between them are the word breaks.

## 4. The five free skills: what is measured and how the score is made

All scores are 0 to 10, rounded to one decimal (`scoring._score_factor_map`,
which runs `scoring_parts/structure.py`, `spatial.py`, `dynamics.py` and
`style.py` in turn). Bands: 8.5 and above Strong, 7.0 Good, 4.5 Developing,
below that Focus (`_band`, `scoring_parts/stats.py:39-46`). Section weights and the
overall score are in [03-scoring-criteria.md](03-scoring-criteria.md).

| Skill | Measured from | Score | Needs reading? |
|---|---|---|---|
| **1 Letter Formation** | `avg_score`: the mean OCR confidence of the handwriting lines; `height_cv`: how much line heights vary | `avg_score x 7.2 + (1 - height_cv) x 2.8` | Yes |
| **5 Size Consistency** | `size_cv`: standard deviation / mean of each **word's small-letter height**, measured along its line's own baseline (`letter_geometry.py`; since 2026-10-13, #135), as the median height of the word's columns (section 9). Fewer than three words measured: line box heights, as before | `(1 - size_cv / 0.60) x 10` (line boxes: `/ 0.65`) | No |
| **7 Baseline Alignment** | `line_slope_abs`: mean of each line's angle, from the first two corners of its polygon (the top edge) | `(1 - angle / 8 degrees) x 10` | Yes |
| **8 Word Spacing** | `word_gap_cv`: variation of every word gap, each divided by its line's height. Gaps come from the ink inside each line (section 3). The space between two boxes left on one row is not a gap: after step 6 of section 2 those are further apart than any word gap (a column, or words never read), and one such space scored Word Spacing 0 on four UJI pages. Fewer than three gaps: "Not measured" | `(1 - word_gap_cv / 1.4) x 10` | Yes |
| **18 Legibility** | A blend of the four above | `0.35 x F1 + 0.25 x F5 + 0.20 x F8 + 0.20 x F7` | Yes |

Code: features at `scoring_parts/features.py:41-203`, formulas in
`scoring_parts/structure.py` (1, 5), `spatial.py` (7, 8) and `style.py`
(18), what each factor needs from the page in `factor_needs.py`.

Three things a reader of a report should know:

- **Size Consistency is measured word by word (since 2026-10-13, #135).**
  It used to compare line box heights; a box drawn level around a sloping
  line is taller by its width times the slope, so a 654-pixel line at 4.5
  degrees gained about 51 pixels and tilt counted as size. Measured along
  each line's own baseline, a sloping line no longer changes it (sections
  8 and 9). On the sample page Size moved from 4.9 to 6.1.
- **Letter Formation leans on how sure the OCR is.** Clear letters are read
  with high confidence, so a low average means letters were hard to read. It
  cannot point at one letter. The recognition note in every report says the
  20 factors "do not depend on reading the words"; for factors 1, 2 and 19
  that is not quite true, because OCR confidence is part of their score.
- **A Kalman baseline tracker exists** (`baseline_track.py`) but runs only on
  rows with three or more boxes, which Paddle's one-box-per-line output
  rarely gives, and it feeds only the "sinking" or "climbing" sentence, not
  the score (`baseline_track.py:32-34`).

## 5. Confidence: what the numbers mean

There is **no calibrated probability** anywhere in a report. The API field
`confidence_probability` is always `null` and the schema requires it
(`generate_schemas.py:546-559`). What exists:

| Signal | Where it comes from | What uses it |
|---|---|---|
| OCR line confidence, 0 to 1 | Paddle's `rec_scores`, one number per line (`ocr_backends.py:407-432`). TrOCR averages its per-token scores into one (`ocr_backends.py:664-691`). Ink-only lines get 0 | Skills 1, 2, 19; the printed check; dropping fragments |
| Recognition level | Mean line confidence: `passage-verified` when the typed passage matched, `high` at 0.85, `moderate` at 0.70, else `low`; `unavailable` when nothing was read (`ppocr-server.py:741-799`) | The report shows it; the spelling check runs only at `high` or `passage-verified` (`report-render.js:554-563`) |
| Per-skill `conf` | `measured`, or why not: `imu` (needs the pen), `ocr` (needs reading), `insufficient` (Word Spacing with fewer than 3 gaps) (`scoring_parts/availability.py:50-60`) | The report says "Not measured" and leaves the skill out of every average |
| Printed probability | Section 2, step 4 | Which lines are scored. The code says it is "a heuristic, not a calibrated confidence" (`classify.py:439-444`) |
| Photo quality | Sharpness (Laplacian variance) and size, measured in the browser only (`app.js:629-658`) | A warning; the visitor may still go on |

**When confidence is low**, nothing is refused on that ground alone. Low OCR
confidence lowers skills 1 and 19 and sets the level to `low`. Refusals happen
only for the cases in the table at the end of section 2. A skill with too
little evidence is marked "Not measured" instead of being given a guess:
Word Spacing below 3 gaps, the reading skills when nothing was read, and the
four pen skills (13-16) on every photo.

## 6. The marked places on the report today

`_factor_region_map` (`computer_vision.py:269-555`) picks, for each skill, one
place on the page that contributed to its score, crops it, and returns its box.
The handwriting lines are numbered top to bottom (`line_1`, `line_2`, ...).

| Skill | Place chosen | Rule (`selection_method`) | Status |
|---|---|---|---|
| 1 | The line with the lowest OCR confidence | `ocr-confidence-context` | context: "letter-shape fault not localized" |
| 5 | The line whose height is furthest from the median line height | `height-deviation` | measurement |
| 7 | The line with the steepest angle | `absolute-line-angle` (whole page when no polygon) | measurement |
| 8 | The line holding the word gap furthest from the median gap, measured from the ink as it is scored (section 3) | `ink-word-gap-deviation` (whole page, `spacing-context`, when no gap stands out) | measurement |
| 18 | Every handwriting line | `aggregate-context` | context |

Two gaps between what is scored and what is marked:

- **Word Spacing used to mark the space between two line boxes**, which is
  no longer scored (section 4). It now marks the line with the ink gap
  that stands out most (section 7).
- **Every mark is a whole line.** No mark today is a single letter or word.

The report draws marks only for its two "Look closer" skills, both in one
theme colour, and reads only `bbox`, `source_size` and `url` from each entry
(`report-render.js:643-690`; `report.css:1022-1024`). The free compact API
returns these entries for skills 1, 5, 7, 8 and 18
(`compact_reports.py:165-175`).

### The fields of each evidence entry

The report pairs a complete crop with a small page map highlighting its source. Evidence is selected from all accepted handwriting regions, independently of the eight-image preview limit.

Each `factor_regions` entry keeps `url` and `caption` and adds:

- `status`: `measurement`, `context`, or `unavailable`.
- `bbox`: `[x, y, width, height]` of the encoded crop in processed-image pixels, or null when unavailable.
- `source_size`: `[width, height]` of that processed image.
- `coordinate_space`: `processed-image`. Coordinates follow EXIF correction and server resizing; they are not raw upload coordinates.
- `region_ids`: selected handwriting regions, numbered top to bottom then left to right within this evidence response. These identify detected regions, which may be words or lines depending on the OCR backend.
- `selection_method`: the rule used to select the crop.
- `location_url`: a small page map with selected boxes highlighted.

Size evidence selects the largest height deviation from the median. Baseline and straightness evidence select the largest absolute polygon angle. Margin evidence selects the largest corrected-left-edge deviation, using the scorer's camera-tilt correction. Word-spacing evidence uses the scorer's row grouping and selects the largest normalized-gap deviation, showing both adjacent regions.

A selected measurement is a contributing region, not a claim that it is the only problem. Factors based on OCR confidence, character-width proxies, loop-letter frequency or composite scores are explicitly labeled as context. They cannot identify an exact faulty character from their current scoring inputs. Factors 13-16 require sensor data and return an empty URL with unavailable status.

Aggregate images and page maps retain accepted handwriting rectangles and blank the rest. This prevents excluded headers and labels from returning through whole-page previews. It does not correct a printed region that the upstream classifier mistakenly accepts, or separate printed and handwritten pixels inside one accepted box.

The browser uses `object-fit: contain` so the crop is not cut off again during display. Older consumers can continue reading `url` and `caption`, but must allow an empty URL for unavailable evidence. Changes to scoring proxies and minimum evidence are tracked in issues #46 and #47.

## 7. Choosing exact words and letters to circle

`backend/marked_places.py` adds a `places` list to the evidence of skills
1, 5, 7, 8 and 18: up to three measurements that stand apart from the page
(`role: "look"`) and at most one closest to the page's usual (`role:
"keep"`, the writing to keep doing). Each place has its box, the
measurement, the value it was compared with and how far it is from it
(`deviation`, used only to rank; it is not a probability), plus the OCR
confidence of its line. The rules:

| Skill | Places | Marked when | Kept when |
|---|---|---|---|
| 5 | Lines, by height against the median line height | 20% or more away | within 10% |
| 7 | Lines, by angle | 2 degrees or more | 1 degree or less |
| 1 | Lines, by OCR confidence | below 0.85 | the clearest line, at 0.85 or more |
| 8 | Word gaps, from ink inside lines, each over its line's height | 50% or more away from the median gap | within 15% |
| 18 | The first marked place of 1, 5, 8 and 7, then the second, by blend weight, one per box | | |

A page needs at least three lines (5), two angled lines (7), two read lines
(1) or three gaps (8). Nothing is marked for 1, 7, 8 or 18 when nothing was
read. When a line holds all the word gaps (one OCR box per line), the
Word Spacing crop is now the line with the gap that stands out most
(`ink-word-gap-deviation`) instead of the whole page.

Checked on the sample photo, the word-gap boxes sit exactly in the spaces
between words and the angle boxes on the sloping lines. The size boxes show
the tilt problem in section 4. The confidence boxes include a row of
practice slashes, which the OCR reads poorly because they are not letters.

### What a letter-level circle needs

A circle on the report says "this is why". It can only say that when the
place was part of the measurement behind the score. With the measurements
above:

| Skill | Circled today, score unchanged | Needs a new measurement first |
|---|---|---|
| 8 Word Spacing | **Exact.** The word gaps the score uses | None |
| 5 Size Consistency | The 2 or 3 **lines** furthest from the median height | Letter-level size: measure each small letter's height against the page's usual small-letter height (zone analysis, `zone_analysis.py:96-145`, already finds each line's midline and baseline). Changes the factor-5 score for every photo |
| 7 Baseline Alignment | The 2 or 3 steepest **lines** | Letter-level: each ink component's bottom against a straight baseline fitted through the line. Changes the factor-7 score |
| 1 Letter Formation | The 2 or 3 **lines** read with least confidence | Per-letter OCR confidence, which Paddle does not return through the current calls; TrOCR's per-token scores are averaged away (`ocr_backends.py:684-688`) |
| 18 Legibility | The marks of 1, 5, 7 and 8, in the blend's weights | Follows the others |

Any new location must come only from the processed image and the handwriting
lines, sorted with a fixed tie-break (deviation, then top, then left), so the
same photo always gets the same circles. That is the analyser's
"same photo, same scores" rule, and the tests in
`backend/tests/test_factor_evidence.py` and `test_marked_places.py` check
each selection, including the same page giving the same places twice.

## 8. Testing the marks on pages with planted mistakes

`scripts/planted_pages.py` writes pages from real handwritten letters and
plants one known mistake on each, then checks whether a mark of the right
skill covers it (at least half of the planted box inside the mark).

- **Letters:** UJI Pen Characters, version 2 (Prat, Castro, Llorens, Marzal
  and Vilar, 2008, doi:10.24432/C5FG8S, CC BY 4.0), only the 20 writers of
  its published test split. Downloaded and checked by SHA-256; neither the
  data nor the pages are committed. The same data trained imu2text's
  drawing reader, so the evaluation and any later letter reader share one
  licence-clean source.
- **Pages:** one writer per page, four lines in our cast's words, small
  letters scaled to one height, letter and word gaps varied by up to 30%
  and 15%. One page per writer for each kind below: 120 pages a run.
- **Lines:** handed to the evidence code as the reader would hand them, one
  box and the smallest rotated rectangle around each line's ink.
  `--ocr` uses the real reader instead.

`backend/tests/test_planted_pages.py` checks the generator itself without
the download.

Results, seed 0, line outlines from the ink (seeds 1 and 2 agree to within
15 points on every "marked" figure):

| Planted mistake | Skill | Marked | Mark size vs mistake | Skill score (clean page: 5 7.55, 7 9.16, 8 7.91) |
|---|---|---|---|---|
| One line sinking 4 degrees | 7 | 100% | 0.97 | 7: 8.03; and 5 falls to 5.88 |
| One word gap three times wider | 8 | 100% | 0.72 | 8: 6.32 |
| One small letter 1.7 times taller | 5 | 15% | 0.01 | 5: 7.88 |
| One word sunk below the line | 7 | 15% | 0.04 | 7: 9.05 |
| One word gap a quarter as wide | 8 | 0% | | 8: 7.63 |

"Mark size vs mistake" is the planted box's area over the mark's: 1.0 is a
mark exactly around the mistake, 0.01 is a whole line around one letter.

What this says:

- **Tilted lines and wide gaps are found, and the mark is in the right
  place.**
- **A tall letter or a sunken word barely changes the score and is rarely
  marked.** A line box is as tall as its tallest letter, and most lines
  already hold a b, d, h or k, so one oversized small letter changes
  nothing that is measured. A sunken word deepens the box but does not
  turn its top edge, which is the angle factor 7 reads. Both need the
  letter-level measurement in section 7.
- **Words written too close together are missed.** `line_word_gaps` takes
  the widest gaps as the word breaks, so a gap narrower than the gaps
  between letters is never counted as a word break; the mark goes to a
  letter gap instead.
- **Tilt lowers Size Consistency** from 7.55 to 5.88 (section 4).
- **Clean pages still get marks:** on average 0.75 size, 0.05 angle and
  1.4 word-gap marks a page, from each writer's own variation and from
  letter gaps read as word gaps.

**Through the real reader (`--ocr`), 94 of the 120 pages were refused as
printed**, and 95 of 120 again after the pages were drawn as photos
(`--style photo`, the default: pen width that changes with pressure,
uneven light, paper grain, blur and JPEG). The cause is one rule in
`classify.classify_lines`: a line read with confidence 0.93 or more
becomes printed (0.85) unless its stroke width varies a lot. Judged line
by line, these handwritten lines score 0.26 to 0.51, well under the 0.58
cut-off; the rule lifts every one of them. The same rule relabels six
handwritten lines of `tests/fixtures/handwriting-sample.jpg` ("The quick
brown fox", "Dodo and Piku write letters", "Stay on the line" among them);
that page is kept only because a less confident second reading of each
line survives. A second rule counts any line read at 0.96 as evidence that
the page holds print.

Requiring even letter heights before either rule applies (glyph-height
variation under 0.25: type measures 0.00 to 0.16 on
`handwritten_printed_2.jpg`, lowercase handwriting 0.33 to 0.44) keeps the
six sample lines and passes every existing test, but lets two printed
fixtures through: the tracing worksheet in `handwritten_printed_1.jpg`
(capital and small letter pairs vary in height) and the receipt's printed
"Received from Mrs" label. The three structural measures the check has
(stroke width, letter height, edge sharpness) overlap between neat
handwriting and a clean font, so this needs a better signal, not a new
threshold. That change is not made; section 10 adds the better signal.

## 9. Measuring inside the line: letters, words and the baseline

`backend/letter_geometry.py` measures what section 8 showed the line boxes
cannot see. Per line:

1. Binarise and take the ink blobs whose middle lies inside the line's box.
   Each blob is a letter (print) or a word (joined writing); dots and specks
   join the nearest blob.
2. Fit a straight baseline through the bottoms of the blobs with Theil-Sen
   (the median of the slopes between every pair), so tails and one sunken
   word cannot tilt it. Its angle is the line's slope.
3. Shift each column so that baseline is level, smooth the row counts, and
   take the densest band (`zone_analysis.dense_band`): the line's
   small-letter height, measured along the line, so a sloping line no
   longer looks tall. A **word's** small-letter height is the median, over
   its columns, of how high the ink reaches above the baseline, counting
   columns that reach 0.35 to 2.0 of the line's height. Loops, stems and
   i dots cover a few columns and tails hang below, so the median stays on
   the letters' bodies. The densest band ran up into the loops on short
   words written with tall letters: on joined writing "the", "day" and
   "dog" measured up to 1.6 times their line and were marked "taller".
4. Split into words at the widest gaps; when the number of blobs equals the
   number of letters in the text, split where the text says each word ends
   instead, which also finds words written too close.
5. Each word's distance from the baseline is the median over its blobs.
   When blobs and letters match, each small letter's height is compared with
   the line's small-letter height.

Marks: a small letter 55% or more off the small-letter height, a word 0.35
of a small letter or more off the baseline, a line at 2 degrees or more, a
text-placed word gap 50% or more off the page's median. These were set on
seed 1 and are reported on seed 0, photo-style pages, 120 pages:

| Planted mistake | Line marks (section 7) | Letter-level marks | Mark size vs mistake |
|---|---|---|---|
| Word sunk below the line | 10% | **95%** | 0.94 |
| Line sinking 4 degrees | 100% | 90% | 0.97 |
| Small letter 1.7 times taller | 15% | 15% | 0.92 |
| Word gap 3 times wider | 95% | 25% | 1.00 |
| Word gap a quarter as wide | 15% | 15% | |

Marks on clean pages, per page: 0.85 letter size, 0.5 baseline, 0.4 gap.

- The **sunken word** goes from almost never found to almost always, with the
  mark around the word.
- The **slope** is measured to within 0.1 degrees (3.97 on a 4-degree line)
  and is about 0 on level lines.
- **Size no longer counts tilt.** Small-letter height variation is the same on
  a clean page and a page with a sinking line (0.13 and 0.13), where line box
  heights took Size Consistency from 7.93 to 5.67.
- A **tall letter** is found only when every letter of its word stands apart
  and the text is known (letters and blobs match on about a third of lines);
  when found, the mark is the letter itself. These writers' own small
  letters are often far apart in height too (clean pages carry 0.85 letter
  marks each at the 55% line), so one letter 1.7 times taller is often
  within their normal spread.
- **Word gaps** stay with the existing method (section 7), which finds wide
  gaps far more often; the text-placed gaps add the narrow ones it misses.

Candidate scores, computed beside today's and not used by the report
(`letter_geometry.page_features`):

| Page | Size today | Size from small-letter heights | Baseline today | Baseline from the fitted baseline and sunken words |
|---|---|---|---|---|
| Clean | 7.93 | 6.71 | 9.12 | 9.51 |
| Line sinking 4 degrees | 5.67 | 6.71 | 8.00 | 8.46 |
| Word sunk below the line | 7.45 | 6.87 | 9.11 | 9.07 |
| Small letter 1.7 times taller | 7.69 | 6.43 | 9.06 | 9.36 |

The candidate size score is stable under tilt but sits about one point
lower overall (its 0.40 full scale is a first choice), and neither
candidate moves much for one oversized letter or one sunken word: a single
mistake among about 30 words is a small share of a page. Switching the
report's scores to these needs those choices made first.

## 10. Print or handwriting: a trained line reader

`backend/print_hand.py` looks at a line's ink and gives a probability that
it is print. It does not replace the printed check: it can only stop the
two rules in section 8 that call a confidently read line print. When it
sees handwriting (probability under 0.1), those rules do not apply to that
line; when it cannot judge (too little ink, or no weights file), the check
behaves exactly as before.

**How it reads a line.** The crop is turned grey, scaled to 32 pixels tall
and contrast-stretched so ink is 1 and paper 0. Windows 64 pixels wide,
every 32 pixels, each go through three 3x3 convolutions (16, 32 and 48
filters, each with ReLU and 2x2 max pooling), an average and one output;
the line's probability is the logistic of the windows' mean. About 19,000
weights, stored as 8-bit integers (`backend/models/print_hand.json`, 26 KB),
run in plain numpy: the same crop always gets the same answer.

**Training data** (`scripts/print_hand_data.py`, never committed):

- Handwriting: the 40 training writers of UJI Pen Characters v2 (CC BY
  4.0), set into lines of words with the writer's own letters, some slant,
  size and baseline wobble, and joining strokes between some letters.
- Print: 21 open-licence fonts from google/fonts at one commit, each
  checked by SHA-256, including fonts that imitate handwriting, because a
  script font is print.
- Both through the same photo effects: pen or type weight, ink colour,
  ruled and dotted lines, uneven light, paper grain, aged paper, blur,
  rescaling, JPEG; small letters from 4 to 40 pixels tall.
- 6,000 lines of each for training (`scripts/train_print_hand.py`, seed 0,
  12 epochs, the best validation epoch kept). Real photos never train.

**Results, scored with the exported 8-bit weights:**

| Test | Lines | Correct |
|---|---|---|
| Synthetic: the 20 UJI test writers and four fonts that never trained | 1,600 | 96.1% |
| Every labelled line PaddleOCR finds on the nine committed sample pages | 239 | 86.6% |
| Of those, the three handwritten pages | 120 | 94%, 100%, 100% |
| The typed letter / the printed letter template | 45 / 34 | 73% / 97% |
| The two script-font pages (print imitating handwriting) | 8 / 7 | 12.5% / 43% |

On the real lines, the cut-off for "handwriting" (under 0.1) lets the
confidence rules skip 118 of 126 handwritten lines and wrongly skips 8 of
113 printed lines, mostly the script fonts. The cut-off was chosen on these
same lines, so those two figures are optimistic; the end-to-end checks
below are the independent ones.

**End to end, the full printed check on seven of the nine committed sample
pages** (all but the signature-font poster and the printed letter
template): five handwritten lines of `handwriting-sample.jpg` that were
turned into print are now kept ("The quick brown fox", "Dabe has a big blue
bag", "red box they play with ball", "Dodo and Piku write letters",
"Slowly he also writes 11, 22 and 33"). No other line on those pages
changed: the typed letter, the tracing worksheet, the script-font specimen
and the receipt's printed labels are as before. "Stay on the line" is still
called print (the reader gives it 0.51).

**On the 120 planted photo-style pages through the real reader:** refused
as print **0 of 120** (95 of 120 before). These pages are drawn the way the
training lines are, with different writers, so this flatters the reader;
the real sample pages above are the stronger evidence. With the pages now
read, the marks through the real reader:

| Planted mistake | Line marks | Letter-level marks |
|---|---|---|
| Line sloping 4 degrees | 50% | 50% |
| Word gap 3 times wider | 30% | 0% |
| Word sunk below the line | 5% | 40% |
| Small letter 1.7 times taller | 5% | 5% |
| Word gap a quarter as wide | 0% | 0% |

These were first published higher (90%, 60%, 60% in the best column).
That run called the reader without the server's set-up and with
`lang=en`, so it read with library-default models and both image
variants; the figures above use the server's set-up and `auto`, as the
website and the app send (2026-10-13, section 11). The `en` path also
keeps most lines twice, which changes scores (#145).

These are lower than with the ink outlines in section 9 because the
reader's line boxes are looser and sometimes join or split lines.

What it still gets wrong: script fonts that imitate handwriting, and some
lines of a heavily scaled-down typed page. `test_print_hand.py` checks both
directions on real crops: neat handwriting from the sample page stays
handwriting, a printed heading from the receipt stays print.


## 11. Where each letter is: positions from the reader

Small circles on a single letter need to know where each letter is. The
line reader already knows: PaddleOCR's recogniser reads a line as a row of
narrow columns and decides one character per column, and with
`return_word_box` it reports the column every kept character came from.
`backend/letter_boxes.py` maps each column back along the line's outline
to a point on the page (a quarter of a column back, measured below), and
the half-way points between neighbouring letters give each letter its
left and right edges. The column's own probability is a per-letter
confidence; PaddleOCR averages it away, so the evaluation reads it with a
hook. Nothing in the report uses any of this yet.

**How it is measured** (`scripts/letter_boxes_eval.py`, analyser image):
the 120 planted photo-style pages of section 8, with every real letter's
box recorded, read by the server's reader (`auto`, the server's
models), then each kept line read again for its columns. A placed letter
lands when its centre is inside a real letter's box.

| On 120 pages, 15,968 real letters | |
|---|---|
| Letters on the lines the reader kept | 70% |
| Of those, letters the reader placed | 67% |
| Placed letters that land on a real letter | 92% |
| Landed letters it also named correctly | 91% |
| Distance from the letter's centre (median / 90th percentile) | 0.15 / 0.36 letter widths |

The quarter-column shift was chosen on eight other planted pages (seed
1). There, the column's middle (half a column forward) gave a median
error of 0.30 letter widths with 83% of letters within half a letter of
their centre; a quarter back gave 0.14 and 97%.

**Per-letter confidence** separates letters named right (median 0.95)
from letters named wrong (0.71), but not cleanly: below 0.7 catches 48%
of the wrong ones and also 15% of the right ones.

**On the real sample photo** the 16 lines give 287 placed letters. On the
two neat lines at the top the boxes sit on their letters; on the crowded
lower half they drift between lines, and 123 of the 287 have a confidence
under 0.7.

**Letter size from the slots.** Each placed small letter's height is the
ink in the middle 60% of its slot, keeping only the ink pieces that reach
across most of the slot so that a neighbour's leaning stem is left out
(`letter_geometry.placed_letter_heights`). It is compared with the other
copies of the same letter on the page when there are three or more,
because writers make some letters bigger by habit (one writer's a is half
as tall again as their n on every line); otherwise with the line's
typical small letter. On the 20 pages with one small letter planted 1.7
times taller (cut-off 1.5, chosen on seed 1, reported on seed 0):

| | Reader slots | Ink gaps (today's letter level) |
|---|---|---|
| Planted letter measured at all | 40% | 5% |
| Its measured size, when measured | 1.58 | 1.72 |
| Tallest letter on the page is the planted one | 20% | 0% |
| Pages (all 120) with a false "tall letter" | 63% | 37% |
| False tall letters per page | 1.4 | 0.5 |

Of the 172 false tall letters, 59 are a tall or low letter (an l, a g)
read as a small one, 16 sit between letters, 7 are another small letter
and 90 are the right letter really measuring that tall: an ordinary
small letter varies about as much (95th percentile 1.4) as the planted
one was changed. With the text known (only letters the reader named
right) the false pages fall to 40%, still too many. A letter size circle
from a free photo is therefore not ready: it would be wrong more often
than right. Letter size can be measured against the printed lines of a
worksheet instead, where the target height is printed rather than
guessed from the child's other letters.

**What this means for small circles.** When the reader places a letter it
is nearly always on a real one, so a circle drawn only on placed letters
points at the right place on clean writing. It misses about a third of
the letters, so it cannot say that a letter is absent or count every
letter, and it is not yet reliable on crowded pages. The positions are
good enough to circle the letters the reader found hardest to read (the
lowest per-letter confidence), which is a true statement about the
reading; they are not good enough for letter size, as measured above.
Any report change waits for the owner.

## 12. Tested on real handwriting: the UJI test pages (19 October 2026)

Twenty pages, each written by one of the 20 writers in UJI Pen Characters'
published test split (CC BY 4.0, the same letters as section 8), four
lines of our cast's sentences per page with no planted mistake. Each was
scored through the real pipeline: PP-OCRv5 as deployed, the layout model,
the printed check and the scorer. The website's free check page scored
them on 19 October 2026 and the ranking did not match the eye: a tidy
joined hand (UPV_W57) scored 53, four pages scored 0 for Word Spacing,
and one line was read twice. Sections 2, 3, 4 and 9 describe the fixes.

**Lines.** Before, the reader scored 50 of the 80 written lines (53 when a
request names its language, which runs both image variants): the first
line of most pages was dropped as a header, some lines were never
detected, one line was read twice and others came in up to four pieces.
Now it scores 77 of 80 (78 with both variants), each once and whole. The
lines still missing are on UPV_W21, UPV_W27 and UPV_W54, where the reader
cannot read the line even in a crop of its own. Two runs in fresh
processes give the same lines and scores on every page.

**Scores**, with `lang=auto` as the website sends, before and after.
"Lines" counts the lines scored: UPV_W30's first line is still two lines,
because the words between its two parts are never read.

| Writer | Lines | Overall | Letter Formation (1) | Size (5) | Baseline (7) | Word Spacing (8) | Legibility (18) |
|---|---|---|---|---|---|---|---|
| UJI_W12 | 4 → 4 | 76 → 90 | 8.9 → 9.3 | 8.7 → 8.1 | 8.3 → 9.4 | 7.3 → 8.6 | 8.4 → 8.9 |
| UJI_W13 | 3 → 4 | 84 → 89 | 9.3 → 8.7 | 8.5 → 8.8 | 9.6 → 9.8 | 8.4 → 8.3 | 9.0 → 8.9 |
| UJI_W14 | 3 → 4 | 94 → 95 | 9.5 → 9.6 | 8.4 → 8.8 | 9.5 → 9.6 | 8.0 → 9.0 | 8.9 → 9.3 |
| UJI_W15 | 4 → 4 | 89 → 91 | 8.2 → 8.2 | 7.6 → 7.7 | 9.7 → 9.7 | 6.9 → 8.4 | 8.1 → 8.4 |
| UJI_W16 | 6 → 4 | 69 → 91 | 9.1 → 8.8 | 6.0 → 7.9 | 7.0 → 9.3 | 7.0 → 8.6 | 7.5 → 8.7 |
| UPV_W18 | 2 → 4 | 94 → 93 | 9.4 → 9.0 | 9.3 → 9.0 | 9.7 → 9.5 | 8.9 → 8.6 | 9.3 → 9.0 |
| UPV_W21 | 5 → 4 | 70 → 71 | 9.0 → 8.6 | 5.6 → 6.9 | 7.9 → 7.6 | 7.1 → 8.9 | 7.6 → 8.0 |
| UPV_W24 | 3 → 4 | 93 → 93 | 9.1 → 9.1 | 8.1 → 8.1 | 9.5 → 9.6 | 8.8 → 8.9 | 8.9 → 8.9 |
| UPV_W27 | 4 → 3 | 74 → 92 | 9.4 → 9.1 | 8.6 → 8.2 | 9.3 → 9.7 | 0.0 → 9.1 | 7.3 → 9.0 |
| UPV_W30 | 4 → 5 | 67 → 73 | 8.8 → 8.7 | 5.5 → 6.0 | 7.6 → 8.1 | 6.1 → 7.6 | 7.2 → 7.7 |
| UPV_W33 | 3 → 4 | 93 → 94 | 8.9 → 8.9 | 8.9 → 9.2 | 9.4 → 9.5 | 9.4 → 9.3 | 9.1 → 9.2 |
| UPV_W36 | 5 → 4 | 73 → 88 | 8.6 → 8.6 | 7.2 → 7.1 | 9.4 → 9.7 | 6.3 → 8.7 | 8.0 → 8.5 |
| UPV_W39 | 5 → 4 | 74 → 93 | 9.3 → 9.2 | 8.2 → 8.7 | 7.5 → 9.6 | 6.6 → 9.1 | 8.1 → 9.1 |
| UPV_W42 | 5 → 4 | 70 → 89 | 8.8 → 9.3 | 7.9 → 8.2 | 7.9 → 9.4 | 3.3 → 8.7 | 7.3 → 8.9 |
| UPV_W45 | 3 → 4 | 92 → 94 | 9.2 → 9.3 | 9.0 → 8.9 | 9.6 → 9.7 | 7.5 → 8.6 | 8.9 → 9.2 |
| UPV_W48 | 3 → 4 | 76 → 85 | 9.5 → 8.8 | 6.8 → 7.2 | 7.9 → 9.2 | 6.4 → 7.6 | 7.9 → 8.2 |
| UPV_W51 | 4 → 4 | 68 → 89 | 8.7 → 8.8 | 6.7 → 8.7 | 7.1 → 9.8 | 7.3 → 7.8 | 7.6 → 8.8 |
| UPV_W54 | 1 → 3 | 93 → 85 | 9.3 → 9.2 | 6.3 → 7.0 | 9.5 → 9.4 | 9.4 → 8.7 | 8.6 → 8.6 |
| UPV_W57 | 6 → 4 | 54 → 91 | 8.8 → 8.9 | 3.8 → 8.3 | 2.8 → 9.4 | 4.7 → 8.1 | 5.5 → 8.7 |
| UPV_W60 | 2 → 4 | 88 → 90 | 8.8 → 8.8 | 7.9 → 8.3 | 9.4 → 9.4 | 8.6 → 9.0 | 8.7 → 8.8 |

What moved and why (the benchmark in [18-benchmark.md](18-benchmark.md)
replays these pages on every pull request, so any later change to them
shows in the PR):

- **Word Spacing** no longer scores 0 (UPV_W27, W48, W51 and W54 were 0
  with `lang=en`): the space between two pieces of a line is not a word
  gap (section 4), the pieces are joined, and gaps come from the line's
  own blobs (section 3).
- **Baseline Alignment** rises where lines had been read in pieces: each
  piece's outline had its own slope, and short pieces slope a lot.
  UPV_W57 went from 2.8 to 9.4.
- **Size Consistency** rises on joined writing (UPV_W57 3.8 to 8.3,
  UPV_W51 6.7 to 8.7): words are measured column by column (section 9).
  UPV_W30 stays at 6.0 because its writer mixes capital-sized A, E and K
  with small letters, which the eye sees too.
- **UPV_W54 falls from 93 to 85.** Before, only one of its four lines was
  read, and that one was its neatest; three are scored now.
- **UPV_W21 stays at 70 to 71**: one of its lines is still not read and
  another only in part, so its size and slope come from fewer words than
  the others.

The same 120 planted pages as sections 8 and 9 (seed 0, photo style,
measured from ink outlines, so without the reader):

| | Before | After |
|---|---|---|
| False size marks per clean page | 1.25 | 0.85 |
| False word-gap marks per clean page | 0.95 | 0.50 |
| Wide word gap marked | 95% | 100% |
| Word Spacing, clean page and page with one wide gap | 8.25 and 5.88 | 8.69 and 6.21 |
| Size, clean page and page with one tall letter | 7.80 and 7.60 | 7.98 and 7.80 |
| Size, page with one sunken word | 7.91 | 7.58 |

The last row is a known cost of measuring words from the line's baseline:
a word sitting 0.6 of a small letter below the line measures that much
shorter. Measuring every word from its own baseline removes it but makes
neat pages measure less even (UPV_W45 8.9 to 8.4); the plan below removes
it only for the words the baseline check finds.

### Small changes inside a line: what is found and the plan

One planted mistake among about 30 words is still rarely found by the
report's marks: one tall letter on 3 of 20 pages, one sunken word on 2 of
20, two words written too close on 3 of 20. The letter-level measurements
of section 9 exist and are measured; most are not yet used by the report.
In order of cost:

1. **Sunken word: ready, needs the owner.** `letter_geometry.baseline_marks`
   finds the sunken word on 19 of 20 pages with the mark around the word
   (0.94 of its size), and 0.5 false marks per clean page. Using it as
   Baseline Alignment's marked places, and counting the share of words off
   the line in its score (`page_features`' candidate), changes what the
   report draws, so it waits for the owner's approval with before and
   after screenshots. The same measurement then lets Size measure a
   sunken word from its own baseline, which removes the leak above.
2. **Words too close: the reader's word breaks.** On joined writing the
   widest gaps are taken as the word breaks, so a word gap narrower than a
   letter gap is never measured. The reader already returns where it put
   each space (`ocr_backends.read_line_letters`, used today for the two
   least-sure letters); measuring the ink gap at the reader's breaks
   finds the narrow gap where the text says it is. Cost: one more call
   to the recogniser per line. To be measured on the planted pages before
   it is used.
3. **One tall letter: against printed lines, not from a free photo.**
   Section 11 measured the reader's letter slots: the planted letter is
   measured on 40% of pages and 63% of pages get a false tall letter,
   because these writers' own small letters vary about as much as the
   planted one. Column heights (section 9) catch a whole word written
   bigger, not one letter. A worksheet with printed guide lines gives the
   target height, so a letter can be measured against it; that is where
   letter size should be marked.

## 13. Each factor against its own mistake (English, 20 October 2026)

Every factor a photo can measure is tested against a mistake planted for
it, on the 20 UJI test writers' own letters (`scripts/factor_tests.py`).
Each planted page is made from the same random numbers as a clean twin,
so the two differ only by the mistake; a factor "catches" it when the
planted page scores at least 0.1 lower than its twin. Lines are given
from the ink (no reader), except where the reader is named.
`python scripts/benchmark.py factors` checks these rates on every change
to the measuring and weekly (`.github/workflows/factor-tests.yml`).

| Mistake planted | Factor | Caught before | Caught now |
|---|---|---|---|
| One line starts 2.5 small letters in | 10 Margin Discipline | 100% | 100% |
| One word gap three times wider | 8 Word Spacing | 100% | 100% |
| One word gap a quarter as wide | 8 Word Spacing | 100% | 100% |
| Last line sinking 4 degrees | 7 Baseline, 11 Straightness, 12 Vertical Alignment | 100% | 100% |
| One word sunk 0.6 of a small letter | 7 Baseline Alignment | 5% | **100%** |
| One line's letters riding a wave | 11 Line Straightness | 20% | **100%** |
| One line's letters leaning 25 degrees | 17 Slant Consistency | 0% | **100%** |
| One word's letters three times as far apart | 9 Letter Spacing | 25% | **100%** |
| Every a, d, g, o, p, q left open | 3 Loop Closure | 0% | **85%** |
| One word 1.5 times the size | 5 Size Consistency | 75% | 75% (falls 0.61, was 0.25) |
| One line's tall letters and tails 1.5 times | 6 Ascender/Descender | 75% | 75% |
| One small letter 1.7 times taller | 5 Size Consistency | 15% | 10% |
| One line written with a tremor | 4 Line Quality | 0% | 0% |
| One word scribbled, read by the real reader | 1 Letter Formation | 9 of 19 | unchanged |
| | 18 Legibility | 2 of 19 | unchanged |
| | 19 Character Distinction | 8 of 19 | unchanged |
| | 2 Stroke Order | 9 of 19 | unchanged |

What changed (`letter_geometry.py`, `_stroke_features` in `scoring_parts/features.py`):

- **Loop Closure (3)** counted the share of loop letters in the text, so
  an open loop could not move it. It now counts the closed bowls in each
  line's ink (holes of letter-bowl size) against the letters read that
  have one (a, b, d, e, g, o, p, q); full marks at 90%.
- **Letter Spacing (9)** was the spread of line width per character. It
  is now the spread of the gaps between the letters (or joined pieces)
  inside words. On a page the style check calls joined cursive
  (`style_analysis.py`) those gaps are pen lifts, not letter gaps, so it
  is "Not measured" there (#277; `scoring_inputs.method` is
  `letters_joined`).
- **Line Straightness (11)** was the line angle again, the same as
  Baseline. It now also loses up to 5 points as a line's letters wander
  off its fitted baseline (median distance, tails left out), worst line.
- **Slant Consistency (17)** was the spread of line angles. Each word's
  lean is now the shear that makes its strokes most upright, and the
  score falls with the spread of the leans.
- **Baseline Alignment (7)** also loses up to 5 points as the share of
  words sitting off their line (0.35 of a small letter or more) reaches
  25%: a sunken word does not turn a line, so the slope never saw it.
- **Size Consistency (5)** loses up to 2 points as the share of words 30%
  or more off the page's usual size reaches 10%; a word's height counts
  only the columns reaching at least half a small letter (joins and the
  bottoms of curves pulled it down); and a word sitting off its line is
  measured from where it sits, so a sunken word is no longer a size
  change.

The older stand-ins remain only for a page too small to measure. On the
20 real UJI pages (section 12) overall falls 2 to 7 points, mostly
because Letter Spacing and Slant Consistency, which scored about 9.7 on
any page, now measure clean writing near 7.7.

What is not solved, and why:

- **One letter 1.7 times taller** (10%) and **one word 1.5 times the
  size** (75%). Without knowing which letter is which, a small letter
  made tall looks like a tall letter, and a big word's V-shaped letters
  (w, v) or a word split in the wrong place hide its size. Section 11 has
  the letter-position measurements; they are not reliable enough yet.
- **Line Quality (4)** measures how much line lengths vary, not the
  stroke. A tremor at phone-photo resolution wobbles on the same scale as
  the curves of the letters themselves, and an edge-roughness measure
  caught it on 8 of 20 pages; it was not shipped. Smoothness belongs to
  the sensor pen, like speed and pressure (13 to 16).
- **Stroke Order (2)** cannot be seen in a finished letter; its score is
  a blend of letter widths and reading confidence. Also a pen skill.
- **Letter Formation (1), Legibility (18), Character Distinction (19)**
  average the reader's confidence over whole lines, so one scribbled word
  in 30 hardly moves them. Reading every line again letter by letter and
  scoring the share of letters the reader was unsure of would fix this,
  but in testing the extra readings took a scan past the analyser's 2.5 GB
  memory limit, so it needs a load test on stage first (CLAUDE.md, scan
  capacity) and is not in this change.
- **Ascender/Descender Control (6)** moves a little with every other
  mistake (0.3 to 0.9 points): its zone bands are measured per line and
  shift with whatever else changes in the line.
