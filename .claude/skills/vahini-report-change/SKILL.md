---
name: vahini-report-change
description: Implement or review Vahini analyser Free/Pro access, report APIs, compact dictionaries, browser rendering, worksheet recommendations and PDF output.
---

Read [CLAUDE.md](../../../CLAUDE.md) and the relevant sections of [report contract guidance](../../../docs/AI-REPORT-CONTRACT.md). Consult [API-V2.md](../../../backend/API-V2.md) for request/response details and [skills.md](../../../skills.md) for prose.

Before editing any report file, read the [report format baseline](../../../docs/AI-REPORT-CONTRACT.md#report-format-baseline-owner-approval-required). The owner (@vkosuri) approves every change to the report's page structure, sections, styling or per-tier rendering. If the task needs one, stop and ask with before and after screenshots; do not make it and explain afterwards. Bug fixes that keep the rendered format need no approval.

Brand colours, type and ink come from the Vahini design system: pages link `/site/design/v1/vahini.css` (served by vahinitech.com) and CSS uses `var(--v-*)` tokens with no fallbacks and no brand colour codes. Only the report's own colours (score bands, paper, rules) stay in `report.css`; vahini-web's `input-manifest.yaml` caps how many colour literals each stylesheet may hold.

The Free report shows all five Free factors on page 1, each with an example cropped from the visitor's uploaded photo and the photo marked with where each crop came from (owner decision, 2026-10-06). The server sends Free the `evidence` regions of those five factors only; never show a locked factor's crop, a stock example in place of a missing crop, or a crop from any photo but the visitor's.

Scan work runs through `scan_slots.slot()` and `scan_slots.run()` (capacity sized by `backend/capacity.py`, see #97); a new endpoint that decodes or scans must use them too. After any change under `frontend/src`, run `python frontend/build_bundle.py`: it rebuilds the bundle and the `?v=` stamps that keep Cloudflare from serving old scripts with a new page. Regenerate the sample report with `docs/examples/generate_photo_sample.py`, not by hand.

Keep authorization server-owned, preserve the existing expanded contract, and update dictionary versions and the browser adapter together when their contract changes. Rebuild the frontend bundle after source edits. Verify returned values and actual printable output rather than only screenshots or fixture counts.

Printable output means the page count, not only each sheet's height. The free report is two A4 sheets; `tests/report-layout.mjs` prints the PDF and fails on any other count, once with the fixture and once with sheets stretched to the length a real photo produces (the fixture's text is shorter, which is how 3-4 page prints with blank pages passed every check on 2026-10-07). Any change to report content, spacing or `fitPrintPages()` reruns it; when real content grows, update the stretched heights from a real print, not from the fixture.

For PR review, use [review instructions](../../../.github/instructions/code-review.instructions.md). Use synthetic samples and test credentials. Do not claim native app changes or store purchase verification from backend work. The consuming website owns its staging and production deployment workflow.
