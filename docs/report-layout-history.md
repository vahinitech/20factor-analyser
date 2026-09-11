# Report layout restoration

The regression came from template changes, not only stylesheet changes.

| Commit | Report change |
|---|---|
| `402487c` | Scorecard with overall and factor overview; plain-language score view; concept plus uploaded evidence; optional coaching tips; factor reference table; practice with prediction; appended classification tables. |
| `8d041d4` | Aligned coaching and drills but removed the prediction content and classification appendix. |
| `a1946f9` | Replaced the report with three pages. Removed overall score, full score tables and target concept drawings. This was the main structural regression. |
| `65786f7` | Corrected typography and spacing but retained the reduced three-page structure. |
| Current restoration | Six pages: overall score; 20-factor score table; concept versus uploaded evidence; coaching; tips and drills; prediction. |

The restoration keeps confidence-aware spelling suggestions, three shared
practice priorities, printed-text exclusion and missing-measurement handling.
Target drawings are concept examples, not fabricated corrected scans.
The prediction chart is labelled illustrative and uncalibrated, excludes
unavailable factors and does not claim measured improvement or photo speed.
Classification transcript appendices stay out of the reader report.

Regression coverage now asserts the exact page sequence, overall score,
20 factor rows, three target/evidence pairs, coaching and drill alignment,
and prediction chart plus uncertainty wording. Desktop, mobile and print
checks measure overflow, clipping, overlaps and A4 fit. These assertions
replace the earlier tests that incorrectly treated removal of the scorecard
and pages as expected behavior.
