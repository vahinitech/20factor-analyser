# Data for the before/after comparison

The paid comparison in 20factor-analyser-pro sets two saved version-2
reports side by side: the same child, an earlier page and a later one. A
family keeps both reports; the analyser keeps neither (photos are never
stored, docs/15-persistence.md). This page lists what a version-2 report
gives that comparison beyond the factor scores, where each value comes
from, and what it does not claim. The fields are built by
`backend/comparison_data.py` from what the scorer and the reader already
produced; nothing here measures the writing in a new way.

Order of changes across repositories: this analyser change first, then the
contracts copy in Umbrella (`contracts/analyser/`), then the comparison
library and viewer in 20factor-analyser-pro.

## Section scores (`sections`)

The four sections of the catalogue (Structure, Spatial, Dynamics, Style &
Readability), scored as `scoring.build_analysis` scores them for the
overall number: the mean of the section's measured factors, out of ten
with one decimal. A section with no measured factor (Dynamics, from a
photo) has a null score and weight 0, and the other weights are scaled to
add up to 1. These are the weights the overall score used, so
`round(sum(normalized * weight))` gives `summary.score` back
(`backend/tests/test_comparison_data.py` checks it on the case-study
pages).

| Format | Shape |
| --- | --- |
| Expanded 2.0 | `sections: [{id, name, score, normalized, weight, factor_count, scored_factor_count}]` |
| Compact 2.1 | `sections: [{id, s, w}]`; the name comes from the catalogue's `sections` |

Pro only. A section mean includes factors a Free report does not show, so
giving it to Free would reveal locked scores.

## Can these two pages be compared? (`comparability`)

A later page that is half as long, in another script, or photographed
with a printed worksheet around it, can move scores for reasons that have
nothing to do with practice. Every successful report, Free and Pro, both
formats, carries the facts a comparison needs to say so:

| Field | Meaning | Source |
| --- | --- | --- |
| `lines` | Handwriting lines that were scored | `recognition.hand_lines` |
| `words` | Words read, split on spaces; null when nothing was read | `full_text` |
| `characters` | Non-space characters read; null when nothing was read | `full_text` |
| `script` | `latin`, `telugu` or `devanagari` when at least 90% of the letters read are in that Unicode block, `mixed` otherwise, `other` when the text has no letters (digits only), null when nothing was read | `full_text` |
| `languages` | Reading-engine languages that read the lines (`en`, `te`) | `rec_langs` |
| `printed_lines` | Printed lines found on the page and left out of scoring | `recognition.printed_lines` |
| `page` | `handwriting`, or `handwriting_with_print` when printed lines were left out. A page with only print is refused and never gets a report | `printed_lines` |
| `reading` | The recognition level (`passage-verified`, `high`, `moderate`, `low`, `unavailable`) | `recognition.level` |
| `passage_aligned` | The page was matched to a copied passage, so two pages of the same passage compare best | `recognition.passage_aligned` |
| `ruleset` | sha256 of the rules the page was scored by: the language pack and the request's school, class and child `profile` (`backend/languages/profile.py`). Without a profile it is the pack's own hash. Two pages with different hashes were scored by different rules, so compare them as you would two scripts. Null only for a payload made before the hash existed | the request's `profile` |

When a copied passage was matched, `words` and `characters` count the
passage's words as the reader aligned them, which is what was written.
The fields are counts and labels: no text, no identifier and nothing about
the child (`ruleset` is a hash; the profile behind it, which can hold
children's names as exception words, never comes back). They come from the same photo the same way every time, so the
same photo gives the same facts.

What this does not decide: how different two pages may be before a
comparison should warn. That is the comparison viewer's rule, and it
should be stated there in words a parent understands (for example "the
later page has about half as many words").

## Where each factor was measured (`evidence.factor_regions[n].marks`)

The comparison viewer draws the same factor from the earlier and the later
photo, which the family drops into the page on their own device. The photos
never come back to the analyser: they are not stored (docs/15-persistence.md)
and the report holds no picture of them for this. What the report holds is
where to look, as coordinates.

Each evidence region (requested with `include=evidence` in compact, always
in expanded Pro) now carries `marks`, and the evidence block carries the
uploaded photo's size as `photo_width` and `photo_height`. Marks are in that
photo's pixels: after its EXIF rotation, before the analyser's own downscale
(a PDF: its first page at 150 dpi). The website sends the whole photo,
scaled and turned upright, never cropped (`imageToBlob` in
`frontend/src/app/app.js`), so a viewer scales a mark onto the family's own
copy with `x * copy.width / photo_width` and `y * copy.height / photo_height`.

| `role` | `shape` | Factors | What it is | From |
| --- | --- | --- | --- | --- |
| `region` | box | every factor with evidence | The evidence crop's box (whole page for the composite factors 18 and 20) | `computer_vision._factor_region_map` |
| `look`, `keep` | box | 1, 5, 7, 8, 18 (and 10's lines off the usual edge) | The places that stand apart from the page, and the one closest to it, with their `measure` | `marked_places.free_skill_places` |
| `baseline` | line | 7 | The steepest line's edge, which the slope score is measured from | `page_measurements` `slope` |
| `baseline`, `midline` | line | 5 | One typical line's small-letter band | `page_measurements` `size` |
| `usual_start` | line | 10 | The usual left edge of the lines, top to bottom | `page_measurements` `margin` |
| `hardest_line`, `underline`, `letter` | box, line | 1, 19 | The line the reader was least sure of, and its least-sure letters when they could be placed | `page_measurements` `reading` |

Sensor-only factors (13 to 16) have no marks: a photo cannot show them. A
Free report gets the marks of its five factors only, like their regions.
Boxes are `[x, y, w, h]`, lines two `[x, y]` points, rounded to 0.1 pixel.
The marks are the positions the scan already measured, so the same photo
gives the same marks (`test_same_page_same_marks`). When a cached answer
predates this field, the photo's size is unknown and `marks` is left out
rather than guessed.

The schema test that checks the marks on real evidence also found that
`places` from the word-size measurement (#135) send `kind: "word"` and
`measure: "word_xheight"`, which the schema did not list; both are added.

## Real change or normal variation? (not published yet)

Two ordinary pages by the same child never score exactly alike. A
comparison should call a change real only when it is bigger than that
everyday movement, so each factor needs a measured band. **There is no
band in the catalogue yet, because we do not have the data to measure it
honestly.** A guessed band would tell a family that practice worked, or
did not, on no evidence.

### What we have, and why none of it is the band

| Data | What it shows |
| --- | --- |
| The same photo scanned twice | Nothing moves: scoring is deterministic and the steps before it may not depend on server state (CLAUDE.md, "Same photo, same scores"). This rules out noise from the server, not from the child or the camera |
| The case studies (`docs/examples/case*-before/after.json`) | Pages built to show a change. They are designed differences, not variation |
| The planted pages (`scripts/planted_pages.py`, UJI Pen Characters, 20 adult writers who wrote each letter twice on a tablet) | Two pages of the same passage from one writer's letters, below. The letters are a real writer's, but the line positions, gaps and baseline are the generator's own jitter, the reading confidence is fixed at 0.9 and no camera is involved |
| Families' reports | None kept: photos are never stored and reports are not stored either. The stage debug store holds real families' pages for debugging and is not consented for a study |

`python scripts/variation_study.py uji ujipenchars2.txt --pairs 5` (UJI
file SHA-256 `cc56f72f...a0300d61`, as `planted_pages.py` checks; 20
writers, 5 pairs each, fixed seeds, same output every run) gives, as the
absolute score difference out of ten between the two pages of a pair:

| Factor | Median | 90th percentile | Largest |
| --- | ---: | ---: | ---: |
| 1 Letter Formation | 0.1 | 0.3 | 0.4 |
| 2 Stroke Order (proxy) | 0.0 | 0.1 | 0.2 |
| 3 Loop Closure | 0.0 | 0.0 | 0.0 |
| 4 Line Quality | 0.1 | 0.3 | 0.5 |
| 5 Size Consistency | 0.2 | 0.72 | 3.5 |
| 6 Ascender/Descender Control | 0.2 (was 1.1) | 0.6 (was 5.31) | 4.6 (was 9.1) |
| 7 Baseline Alignment | 0.2 | 0.61 | 1.7 |
| 8 Word Spacing | 0.55 | 1.4 | 2.7 |
| 9 Letter Spacing | 0.1 | 0.2 | 0.4 |
| 10 Margin Discipline | 0.3 | 0.61 | 0.9 |
| 11 Line Straightness | 0.2 | 0.6 | 1.3 |
| 12 Vertical Alignment | 0.2 | 0.5 | 1.4 |
| 17 Slant Consistency | 0.2 | 0.41 | 1.2 |
| 18 Legibility | 0.2 | 0.5 | 1.1 |
| 19 Character Distinction | 0.0 | 0.0 | 0.0 |
| 20 Overall Neatness | 0.2 | 0.51 | 1.3 |

Factors 13 to 16 are not scored from a photo. Read this as an engine
check, not as children's variation: factors 3 and 19 do not move because
the text and confidence are fixed, factor 8 moves with the generator's
own gap jitter, and adults writing single letters on a tablet are steadier
than children writing sentences on paper.

The first run showed factor 6 moving by most of its scale between two
pages of the same passage by the same writer (median 1.1, 90th percentile
5.31, largest 9.1). The planted lines sit close together, as on a child's
notebook page, and three steps in `zone_analysis.py` read the
neighbouring lines as this line's reach:

- the line crop is padded by half the line's height, which takes in the
  line above or below; the x-height search kept the longest dense band of
  rows in the crop, and on a page where the line above wrote bigger that
  was the line above's. It now keeps the band that overlaps the detected
  line the most;
- a line's reach was its single tallest (or deepest) letter, so one long
  `f` set the whole line. It is now the median over the line's tall (or
  hanging) letters;
- a descender that touches a letter on the next line joins it into one
  blob, whose depth is the gap between the lines. Such a blob counts only
  when the line has no other hanging letter, and then stops at the next
  line's x-height band.

With those changes factor 6 moves like the other factors (the row above;
no other factor changed). Its largest movements now come from one writer,
UJI_W13, whose two `y` samples differ in length by a factor of two: the
pages really are different there. `backend/tests/test_zone_stability.py`
holds each step and a same-writer spread on drawn letters (largest 8.0
before, under 1.0 now). Factor 6 is then in the same position as every
other factor: no change is reported as progress until the band from real
pairs exists.

### How we will measure it

1. **Writers.** At least 30 children (the tool will not propose a band
   from fewer than 30 writers or 30 pairs), across the ages the product
   serves, with a parent's written consent for this study. Each child gets
   a study code (`w01`); no name, age, school or photo reaches the
   analyser's records.
2. **Pages.** Each child copies the same short passage twice, on two days
   a few days apart, with no practice in between, same pen and paper,
   photographed on a phone in ordinary light the way families do. Each
   page is also photographed a second time, which separates the camera's
   share of the movement from the writing's.
3. **Scans.** Every photo goes through one analyser version with the
   response cache off (`VAHINI_OCR_CACHE_TTL_SEC=0`), with the passage as
   `expected_text`. Only the version-2 reports are kept for the study;
   whether the study team keeps the photos (to re-measure after a scorer
   change) is the owner's decision under the consent wording.
4. **Pairs.** `scripts/variation_study.py reports pairs.json` pairs each
   child's two days, leaves out pairs whose `comparability` differs
   (script, print on the page, word counts more than 25% apart), and gives
   per factor the pairs, writers, median, 90th percentile and largest
   absolute difference. The proposed band is the 90th percentile: nine in
   ten ordinary repeats move less than that.
5. **Publish.** The bands go into the catalogue as
   `factors[].variation: {band, pairs, writers, method}` with a new
   catalogue version, this page records the data and the date, and the
   comparison then labels a change larger than the band as real. Until
   then the comparison shows the change and says plainly that we cannot
   yet tell it apart from everyday variation.
