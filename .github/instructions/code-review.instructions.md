---
applyTo: "**"
---

# Code review instructions — vahinitech/20factor-analyser

Open-source (AGPL-3.0) handwriting analyser: FastAPI recognition backend
+ static frontend, deterministic/auditable computer vision over black-box
AI by design. Consumed by `vahinitech/vahini-web` as a pinned submodule.

## Report format (owner approval required)

Flag, as a blocking issue, any PR that changes the rendered report's page count, sections, card types, styling or per-tier rendering, adds an early return or alternate renderer for a tier, swaps report CSS classes for inline styles, or weakens `tests/report-layout.mjs` or the Free-report checks, unless the PR links the owner's (@vkosuri) explicit approval. A description of a different layout elsewhere (issue text, plan, another doc) is not approval. Rule and protected files: [report format baseline](../../docs/12-report-rules.md#report-format-baseline-owner-approval-required).

## Personal data and the DPDP Act

Use the [DPDP check](../../.claude/skills/dpdp-check/SKILL.md) on any diff that touches uploads and the check (`backend/server/app.py`, `upload_limits.py`, `daily_limit.py`), the report store (`backend/server/report_store.py`), the debug store (`debug_store.py`), access and subscriptions (`access_api.py`, `entitlements.py`, `subscription_admin.py`), the age band (`age_band.py`), the words read from a page and anything in the report text that could name a person, and the check page, print popup and share in `frontend/src/app/`. Flag as blocking: no `DPDP` section in the PR body; a photo, crop, the words read, a name, email, IP address, browser string or time of day reaching a record, log or store; a field added to the report store's allowlist; a new outside service that receives a page; a longer retention or a removed deletion; a path around the parent or guardian step; a weakened privacy test. Each needs the owner's (@vkosuri) quoted decision in the PR, not an agent's reasoning.

## Report and subscription review

Use [report contract guidance](../../docs/12-report-rules.md) and [API specification](../../backend/API-V2.md). Review server entitlement enforcement on fresh results and cache hits, expiry rechecks, the five-factor Free allowlist, compact/expanded compatibility, immutable dictionaries, optional Pro fields and skipped preview work. Check the browser decoder and actual PDF output when those paths change. Report real defects with file/line evidence, and distinguish core tests from live OCR, load and native-app validation.

## Provenance: Never Copied Research Code

- **Flag any newly added code that looks lifted from a paper's official
  implementation or another public repo** — unusual style vs. the rest
  of the file, naming that doesn't match this codebase, or a
  suspiciously complete block appearing all at once. Ask directly: "is
  this cited and independently written, or copied?"
- The OnHW baselines and CV techniques here should reference published
  methods (cite the paper) but be our own implementation. If literal
  reuse of someone else's code is genuinely needed, it must come with
  documented author consent *and* be license-compatible with this repo's
  AGPL-3.0 — don't paste code without checking its original license
  first.
- This is a research project; unattributed/uncredited reuse is an
  academic-integrity and IP risk, not just a style issue, and applies
  with extra force to AI-assisted changes.

## Security Critical Issues

- Endpoints that accept uploads (`/ocr`, `/analyze-vl`, `/report-python`)
  handle untrusted image/PDF bytes — check decode paths (`computer_vision.py`,
  `pypdfium2` PDF rendering) for unbounded memory/size issues, and that
  `MAX_OCR_SIDE`-style limits aren't bypassed by a new code path.
- No hardcoded API keys or model-download credentials.
- Check the OCR-input guard patterns (rate limits, homoglyph/SSRF checks —
  see `tests/ocr-input-guard.test.mjs` in the consuming vahini-web repo, and
  this repo's own `backend/tests/`) aren't weakened by a refactor.
- Dependency pins in `requirements-*.txt` are security-motivated in places
  (e.g., paddleocr/pillow/numpy versions) — a PR loosening a pin should
  explain why, not just "for compatibility."

## Performance Red Flags

- Heavy work (OCR inference, image decode/crop) must run via
  `run_in_threadpool` off the event loop in `server/app.py` — flag any
  new endpoint that does blocking work directly in an `async def` handler.
- Crop/preview generation (`computer_vision.py`): check new code doesn't
  duplicate the shared `geometry.py` clamp-box logic — `classify.py`,
  `ocr_backends.py`, and `zone_analysis.py` already import `clamp_box`
  from it specifically to avoid drift; a fourth reimplementation
  (including inside `server/app.py`, which doesn't use it today) is
  the drift this rule exists to prevent.
- The bundle (`frontend/scripts/core/engine.bundle.js`) is build output
  and gitignored: a PR that commits it, or a `?v=` stamp, is a red flag
  (CI fails on both).
- Benchmarks run only when the `changes` job says the change can move
  them (`scripts/score_closure.py`). When it skipped them, check the PR
  adds no module loaded by name (importlib, a file path) and no new
  benchmark script; either needs an entry in `GROUPS` there, or a skipped
  benchmark could hide a moved score. A PR that moves a score must commit
  the updated `expected.json`.

## Code Quality Essentials

- `black --line-length 79` and `pylint` (min score 9.0) are CI gates —
  formatting/lint issues should be caught before requesting review, not
  left for CI to find.
- **Evaluation honesty**: any accuracy/confidence number in a PR
  description or docstring must state what it was measured against
  (writer-independent vs random split, dataset size). Don't let a number
  ship without that context — this repo exists partly because an earlier
  version's "~99%" turned out to be train-set memorization elsewhere in
  the org (imu2text).
- The deterministic-CV-over-black-box-AI principle is a deliberate
  product choice — a PR introducing an opaque model into the core
  20-factor scoring path (not the OCR engines, which are already
  pluggable) should be questioned, not waved through.

## Review Style

- Be specific and cite the function/line.
- No AI-isms in comments or docstrings.
- For anything touching `/analyze-vl` or `/report-python`: these feed
  different consumers (evidence crops vs. scores) — a fix tested against
  one endpoint isn't verified for the other; ask whether both were
  checked.
- This repo's `main` was once silently missing a whole merged feature due
  to stacked-PR squash-merge ancestry — for any PR based on another
  unmerged branch, confirm the base is current `main`, not a sibling
  branch.
