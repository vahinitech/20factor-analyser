---
name: vahini-report-change
description: Implement or review Vahini analyser Free/Pro access, report APIs, compact dictionaries, browser rendering, worksheet recommendations and PDF output.
---

Read [CLAUDE.md](../../../CLAUDE.md) and the relevant sections of [report contract guidance](../../../docs/AI-REPORT-CONTRACT.md). Consult [API-V2.md](../../../backend/API-V2.md) for request/response details and [skills.md](../../../skills.md) for prose.

Keep authorization server-owned, preserve the existing expanded contract, and update dictionary versions and the browser adapter together when their contract changes. Rebuild the frontend bundle after source edits. Verify returned values and actual printable output rather than only screenshots or fixture counts.

For PR review, use [review instructions](../../../.github/instructions/code-review.instructions.md). Use synthetic samples and test credentials. Do not claim native app changes or store purchase verification from backend work. The consuming website owns its staging and production deployment workflow.
