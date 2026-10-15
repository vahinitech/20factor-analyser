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
