# CLAUDE.md — 20factor-analyser (open-source handwriting analyser, AGPL-3.0)

## Working rules (apply to every change)

- **Verify before claiming.** Read the code before describing behaviour.
  Never invent accuracy numbers, factor thresholds, or API shapes — every
  scored claim in reports and docs must trace to code in `backend/` or
  `frontend/src/`.
- **Deterministic, auditable CV over black-box AI** is a deliberate product
  choice here — keep scoring explainable; don't introduce opaque models
  into the 20-factor path without an explicit decision.
- **No AI-isms** in user-facing report text, commits, or docs (no "delve",
  "seamless", "leverage", filler praise). Coach tips speak plainly to
  parents/teachers.
- **Conventional commits** (`feat:`, `fix:`, `docs:`, `test:`); body says why.
- **Build and test before every commit; CI green before merge.**
- **Docs-only changes skip CI** — `ci.yml` has `paths-ignore: ['**/*.md',
  'docs/**']`; a PR touching only markdown never triggers the pipeline. A
  mixed PR (docs + code) still runs everything — the filter only fires
  when every changed file is docs.

## Commands (mirror of `.github/workflows/ci.yml`)

```bash
# backend
python -m py_compile backend/*.py            # syntax gate
black --check --line-length 79 backend/*.py backend/tests/*.py frontend/build_bundle.py
pylint (min score 9.0)                        # see ci.yml for exact args
python -m pytest backend/tests/               # unit + integration

# frontend bundle — REBUILD WHENEVER frontend/src changes:
npm run build:bundle                          # python frontend/build_bundle.py
# CI fails if engine.bundle.js is out of sync with src/ — this is the
# single most common avoidable CI failure in this repo.

npm run test:regression:headless              # print/handwriting checks
docker compose up -d --wait                   # full stack for live recognition tests
```

## Architecture facts

- `backend/ppocr-server.py` (FastAPI): `/ocr`, `/analyze-vl`, `/report-python`.
  `computer_vision.py` owns decode/crop/evidence previews; `geometry.py`
  owns the one shared clamp-box implementation (three crop paths depend on
  it — don't fork it).
- Evidence crops for the report come from **`/analyze-vl`'s
  `factor_regions`**, scores from `/report-python`. When "images look
  broken", test both endpoints **inside the container** with pixel-range
  measurement before suspecting this code — the 2026-07-20 incident was an
  nginx-layer misroute in the deploy host, not a backend bug.
- `pypdfium2` is used for PDF decode but reaches the image only
  transitively — keep it explicitly pinned in `backend/requirements-core.txt`.
- OCR backends are tiered (`requirements-{core,paddle,trocr,surya}.txt`);
  the default image = core + paddle. `VAHINI_OCR_BACKEND` selects at runtime.

## Consumers — breaking changes ripple

- **vahinitech/web-live** consumes this repo as a git submodule pinned to a
  release tag and proxies `/ocr`, `/analyze-vl`, `/report-python`,
  `/analyser/` through its nginx. Response-shape changes need a web-live
  submodule bump + its e2e run.
- History warning: this repo once lost an entire feature set from `main`
  via stacked-PR squash-merges (branches based on branches, then squashed).
  Base every branch on current `main`; after merging a stack, verify the
  feature actually exists on `main`, not just that PRs show "merged".
