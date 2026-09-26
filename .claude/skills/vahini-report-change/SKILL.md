---
name: vahini-report-change
description: Implement or review Vahini analyser Free/Pro access, report APIs, compact dictionaries, browser rendering, worksheet recommendations and PDF output.
---

Read [CLAUDE.md](../../../CLAUDE.md) and the relevant sections of [report contract guidance](../../../docs/AI-REPORT-CONTRACT.md). Consult [API-V2.md](../../../backend/API-V2.md) for request/response details and [skills.md](../../../skills.md) for prose.

Before editing any report file, read the [report format baseline](../../../docs/AI-REPORT-CONTRACT.md#report-format-baseline-owner-approval-required). The owner (@vkosuri) approves every change to the report's page structure, sections, styling or per-tier rendering. If the task needs one, stop and ask with before and after screenshots; do not make it and explain afterwards. Bug fixes that keep the rendered format need no approval.

Brand colours, type and ink come from the Vahini design system: pages link `/site/design/v1/vahini.css` (served by vahinitech.com) and CSS uses `var(--v-*)` tokens with no fallbacks and no brand colour codes. Only the report's own colours (score bands, paper, rules) stay in `report.css`; vahini-web's `input-manifest.yaml` caps how many colour literals each stylesheet may hold.

Keep authorization server-owned, preserve the existing expanded contract, and update dictionary versions and the browser adapter together when their contract changes. Rebuild the frontend bundle after source edits. Verify returned values and actual printable output rather than only screenshots or fixture counts.

For PR review, use [review instructions](../../../.github/instructions/code-review.instructions.md). Use synthetic samples and test credentials. Do not claim native app changes or store purchase verification from backend work. The consuming website owns its staging and production deployment workflow.
