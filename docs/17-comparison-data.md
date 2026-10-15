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

When a copied passage was matched, `words` and `characters` count the
passage's words as the reader aligned them, which is what was written.
The fields are counts and labels: no text, no identifier and nothing about
the child. They come from the same photo the same way every time, so the
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
