# Mixed handwritten and printed text (issue #6)

Reports append separate classification sections for handwritten text and printed text. Printed text is shown only for identification; it remains outside factor scores, factor evidence crops, recognized handwriting text and grammar checks. Each row shows its source-region ID, available classification level, printed-likeness score and whether its region contributed to scoring.

| Acceptance criterion | Implementation and verification |
|---|---|
| Distinct handwritten and printed sections in mixed-page PDFs | Separate paginated tables; browser tests check both streams. An exported PDF from the existing mixed-page fixture was checked for both transcriptions and labels. |
| Letter/word/text labels where available | The presentation preserves explicit `letter`, `word` or `line` metadata. Current detection/classification is line-level; no finer labels are inferred by splitting a string. Tests cover explicit finer metadata and the line default. |
| Accurate handling of handwritten-only and printed-only pages | Handwritten-only reports say no printed text was detected. Printed-only pages retain the no-handwriting refusal and show excluded printed text on the refusal screen, without generating handwriting scores. |

The report's `analysis.textClassification` and the response's `text_classification` contain `handwritten`, `printed` and `unclassified` arrays plus a limitations note. Refusals carry `text_classification` with `analysis:null`. OCR-free fallback is unclassified when no classifier score exists, rather than being presented as a confident handwriting classification.

A classification score is an uncalibrated heuristic, not measured recognition accuracy or a probability of correctness. The current classifier cannot split a single detected line containing both print and handwriting into separately labeled characters. Classification mistakes remain possible; this change presents the decisions transparently and does not claim a new accuracy benchmark. Regions discarded before text classification by layout or noise filtering are not reconstructed.

Long transcripts are split across table rows and pages without dropping text. Recognized text is HTML-escaped. Existing reports without classification metadata continue to render normally.
