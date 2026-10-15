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
