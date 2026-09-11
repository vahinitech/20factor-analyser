# Reader report and coaching alignment

Issues #59, #60 and #61 are addressed in the report renderer.

The reader report has six sections: scorecard, plain-language review, handwriting evidence, coaching, reference values and practice. Photo and pen reports use the same page numbering. Detailed classification transcripts and the separate technical sensor page are omitted. Classification remains in API responses and the printed-only refusal screen.

Evidence, coaching, scorecard priorities and practice share up to three lowest measured factors below 8.5. Composite factors 18 and 20 remain on the scorecard and reference table, but practice targets their underlying factors. If all actionable factors reach 8.5, the same cards use maintenance wording. Missing factors cannot drive drills.

Coaching and practice use the factor-specific narration instruction, also shown with the evidence. Broad exercise groups no longer choose drills. The backend legacy coaching library remains available in API responses, but the reader report does not render its generic habit or entertainment cards. No scores change in this revision.

The report does not infer interest, practice habits or improvement speed from the sample. It no longer displays projected scores, sessions to a milestone or photo-based speed predictions. Practice asks the reader to write a short guided row, repeat without the guide, and compare the same factor after a comparable re-scan.

Validation: browser regression covers shared priorities and instructions, missing dynamics, maintenance, good-band guidance, six-page photo and pen layouts, escaping and print fitting. A Chromium-exported mixed-fixture PDF was checked with PDFium and contained six sheets. Extremely long externally supplied content can still require print continuation to preserve legibility; content is never silently clipped to enforce a sheet count.
