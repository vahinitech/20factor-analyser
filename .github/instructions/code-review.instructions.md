---
applyTo: "**"
---

# Code review instructions — vahinitech/20factor-analyser

Open-source (AGPL-3.0) handwriting analyser: FastAPI recognition backend
+ static frontend, deterministic/auditable computer vision over black-box
AI by design. Consumed by `vahinitech/web-live` as a pinned submodule.

## Security Critical Issues

- Endpoints that accept uploads (`/ocr`, `/analyze-vl`, `/report-python`)
  handle untrusted image/PDF bytes — check decode paths (`computer_vision.py`,
  `pypdfium2` PDF rendering) for unbounded memory/size issues, and that
  `MAX_OCR_SIDE`-style limits aren't bypassed by a new code path.
- No hardcoded API keys or model-download credentials.
- Check the OCR-input guard patterns (rate limits, homoglyph/SSRF checks —
  see `tests/ocr-input-guard.test.mjs` in the consuming web-live repo, and
  this repo's own `backend/tests/`) aren't weakened by a refactor.
- Dependency pins in `requirements-*.txt` are security-motivated in places
  (e.g., paddleocr/pillow/numpy versions) — a PR loosening a pin should
  explain why, not just "for compatibility."

## Performance Red Flags

- Heavy work (OCR inference, image decode/crop) must run via
  `run_in_threadpool` off the event loop in `ppocr-server.py` — flag any
  new endpoint that does blocking work directly in an `async def` handler.
- Crop/preview generation (`computer_vision.py`): check new code doesn't
  duplicate the shared `geometry.py` clamp-box logic — three paths
  (`classify.py`, `ocr_backends.py`, `ppocr-server.py`) already share it
  specifically to avoid drift.
- `npm run build:bundle` must be re-run whenever `frontend/src/` changes —
  CI checks the bundle is in sync; a PR with source changes but no bundle
  diff is a red flag.

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
