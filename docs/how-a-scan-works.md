# How a scan works: reading, measuring, confidence and the marked places

This is the path one photo takes through the analyser, written from the code.
Every statement names the function and file it comes from. Line numbers are
at commit `fbb4909`; when they drift, the function names still find the code.
[computer-vision-algorithms.md](computer-vision-algorithms.md) explains the
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
for Margins, factor 10 (`_page_tilt_degrees`, `scoring.py:340-376`).

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

1. Duplicates removed and lines sorted top to bottom (`detector.merge_lines`).
2. Tiny low-confidence fragments, wide header and footer strips and long
   number strings dropped (`detector.region_filter_lines`).
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

**What the visitor sees when this fails**

| Case | Result | Code |
|---|---|---|
| Lines found, all printed | `no_handwriting` screen; not counted against the daily limit | `ppocr-server.py:633-648, 876-879` |
| OCR engine failed | 503 `ocr_unavailable`; the page says try again. Never a score from a broken read | `ppocr-server.py:649-652` |
| OCR ran and found nothing | Lines are found from ink alone (`cv-fallback`) and the report is made without the skills that need reading | `computer_vision.fallback_line_regions`, `computer_vision.py:166-248`; `ppocr-server.py:653-661` |
| Still nothing | `no_handwriting`, "No handwriting found" | `ppocr-server.py:662-676` |

**When the family typed the passage**, each read line whose text is at least
45% similar to a passage line takes the passage text instead
(`recognizer.align_to_expected`, `recognizer.py:361-416`). That happens before
scoring, so word counts come from the passage.

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
letter. **Word gaps** come from this (`line_word_gaps`,
`computer_vision.py:702-727`): blobs that overlap left to right are merged (the
dot of an i, the bar of a t), and the widest `words - 1` spaces between them
are the word breaks.

## 4. The five free skills: what is measured and how the score is made

All scores are 0 to 10, rounded to one decimal (`scoring._score_factor_map`,
`scoring.py:571-620`). Bands: 8.5 and above Strong, 7.0 Good, 4.5 Developing,
below that Focus (`_band`, `scoring.py:379-386`). Section weights and the
overall score are in [scoring-criteria.md](scoring-criteria.md).

| Skill | Measured from | Score | Needs reading? |
|---|---|---|---|
| **1 Letter Formation** | `avg_score`: the mean OCR confidence of the handwriting lines; `height_cv`: how much line heights vary | `avg_score x 7.2 + (1 - height_cv) x 2.8` | Yes |
| **5 Size Consistency** | `height_cv`: standard deviation / mean of the **line box heights** | `(1 - height_cv / 0.65) x 10` | No |
| **7 Baseline Alignment** | `line_slope_abs`: mean of each line's angle, from the first two corners of its polygon (the top edge) | `(1 - angle / 8 degrees) x 10` | Yes |
| **8 Word Spacing** | `word_gap_cv`: variation of every word gap, each divided by its line's height. Gaps come from section 3, plus gaps between separate line boxes on one row | `(1 - word_gap_cv / 1.4) x 10` | Yes |
| **18 Legibility** | A blend of the four above | `0.35 x F1 + 0.25 x F5 + 0.20 x F8 + 0.20 x F7` | Yes |

Code: features at `scoring.py:422-560`, formulas at `scoring.py:571-612`,
`_NEEDS_RECOGNITION` at `scoring.py:652-654`.

Three things a reader of a report should know:

- **Size Consistency also counts tilt as size.** A line box is level, so a
  sloping line's box is taller by about its width times the tangent of its
  angle. On the sample photo, a 654-pixel line at 4.5 degrees gains about
  51 pixels, and that line is the one Size Consistency marks as tallest.
  The fix is to measure height across the line's own slope, or per letter
  (section 7).
- **Size Consistency compares lines, not letters.** It measures how much the
  line boxes differ in height. A line box is as tall as its tallest letter, so
  one tall letter makes its whole line taller, but the score does not say
  which letter. (The report's "based on N letters" counts the letters read,
  not letters measured.)
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
| Per-skill `conf` | `measured`, or why not: `imu` (needs the pen), `ocr` (needs reading), `insufficient` (Word Spacing with fewer than 3 gaps) (`scoring.py:743-846`) | The report says "Not measured" and leaves the skill out of every average |
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
| 8 | The pair of line boxes on one row whose gap is furthest from the median gap | `normalized-word-gap-deviation` (whole page when there is no such pair) | measurement |
| 18 | Every handwriting line | `aggregate-context` | context |

Two gaps between what is scored and what is marked:

- **Word Spacing marks only gaps between line boxes**, but most of its score
  comes from gaps inside lines (section 3). With one box per line there is
  usually no pair. The crop then falls back to the line with the gap that
  stands out most (section 7), or the whole page when no gap was measured.
- **Every mark is a whole line.** No mark today is a single letter or word.

The report draws marks only for its two "Look closer" skills, both in one
theme colour, and reads only `bbox`, `source_size` and `url` from each entry
(`report-render.js:643-690`; `report.css:1022-1024`). The free compact API
returns these entries for skills 1, 5, 7, 8 and 18
(`compact_reports.py:165-175`).

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
| 8 | Word gaps, from ink inside lines and between boxes on a row, each over its line's height | 50% or more away from the median gap | within 15% |
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
