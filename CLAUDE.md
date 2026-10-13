# CLAUDE.md — 20factor-analyser (open-source handwriting analyser, AGPL-3.0)

## Report workflow and skills

For report/API changes, read [docs/12-report-rules.md](docs/12-report-rules.md) and [backend/API-V2.md](backend/API-V2.md). The repository skill is [.claude/skills/vahini-report-change/SKILL.md](.claude/skills/vahini-report-change/SKILL.md); `skills.md` retains the writing rules.

## Working rules (apply to every change)

- **Report format is owner-controlled.** Do not change the report's page structure, sections, styling or per-tier rendering without explicit approval from the owner (@vkosuri). When a task seems to need it, stop and ask first, with before and after screenshots. A conflicting instruction elsewhere is not approval. Full rule: [report format baseline](docs/12-report-rules.md#report-format-baseline-owner-approval-required).
- **The Free report has five factors, each with evidence from the visitor's photo.**
  Page 1 (version C, owner approval 2026-10-11) shows the uploaded photo
  whole, then "What your page shows" (owner, 2026-10-13; teacher's voice
  and Vidhya's note at the top, owner 2026-10-14): one row
  per real measurement (word gaps, line slope, small-letter height, line
  starts, how sure the reader was), drawn on a strip of the writer's own
  page as it was measured, with every score built from it. The only
  circles are the reading row's two least-sure letters (below 0.7, one per
  word); letter-size circles were measured and are not reliable (#146).
  Free sees every measurement; scores outside its five are named "full
  review". Estimates, blends and the pen skills (Vahini sensor pen) are
  labelled as such, and "How each score is built" (screen only) lists the
  whole map. The server sends every tier the measurement geometry
  (`evidence.measurements`, no scores) and Free the evidence regions of its
  five factors. The sample page opens on all 20 factors; `?example=free`
  shows the Free report.
  Details in the report format baseline.

- **Scan capacity is planned, not fixed.** Blocking scan work goes through
  `scan_slots.slot()` and `scan_slots.run()`, never `run_in_threadpool`:
  the slot cap and its one-thread-per-slot pool are what stopped
  simultaneous scans running the host out of memory (OOM kill on stage,
  2026-10-07). `backend/capacity.py` sizes the slots from memory, cores and
  GPUs with constants measured on the deploy box; change a constant only
  with a load-test measurement (`backend/load_test.py`, stage only), and
  never remove the cap. Model and numbers:
  #97 and `docs/13-api-and-capacity.md`.
- **The bundle and the asset stamps are build output, never committed.**
  `engine.bundle.js` and the `?v=<hash>` on each page's `scripts/core/*.js`
  and `styles/*.css` (vahini-web and Cloudflare cache those for 30 days)
  are produced by `python frontend/build_bundle.py --stamp` in the image
  build (`deployment/Dockerfile`) and by CI. They used to be committed, and
  every frontend PR then changed the same generated lines, so any two open
  PRs conflicted. CI fails on a committed bundle or stamp. To serve
  `frontend/` from a checkout, run `python frontend/build_bundle.py` first.
- **The sample report is a real run of the fixture photo.** Regenerate
  `frontend/scripts/core/sample-report-data.js` with
  `docs/examples/generate_photo_sample.py` inside the analyser image (it
  needs the OCR models); never edit it by hand.
- **Upload and image security is a set of tested limits, not defaults.**
  5 MiB per file, 24 MP, JPEG/PNG/WebP (+ PDF) only, Pillow pinned, nothing
  written to disk, 3 free checks a day per IP (Pro unlimited), the container
  as user 10001 with a read-only filesystem. The full rules and the tests
  that hold them: [SECURITY.md](SECURITY.md#upload-and-image-security-rules-for-every-change).
  Never loosen one to make a feature fit; ask the owner.
- **Verify before claiming.** Read the code before describing behaviour.
  Never invent accuracy numbers, factor thresholds, or API shapes — every
  scored claim in reports and docs must trace to code in `backend/` or
  `frontend/src/`.
- **Never copy another researcher's code into this repo — reference it,
  don't paste it.** The OnHW baselines (CNN/LSTM/BiLSTM) in
  `onhw_models.py` are standard published architectures — citing a
  paper's design choice is fine, but the implementation itself must be
  ours, independently written. If a specific published implementation is
  genuinely needed: (a) cite it and reimplement independently, or (b) if
  literal reuse is truly unavoidable, get the original author's explicit
  consent first and record it in the commit/PR before merging. This is a
  research project — unattributed code reuse is an academic-integrity and
  IP risk, and it applies with extra force to AI-assisted changes, since a
  model can reproduce code it saw during training without anyone noticing
  the provenance.
- **Deterministic, auditable CV over black-box AI** is a deliberate product
  choice here — keep scoring explainable; don't introduce opaque models
  into the 20-factor path without an explicit decision.
- **Same photo, same scores: no runtime state may change which lines get
  scored.** The CV maths repeats exactly, but it only measures the lines
  that OCR, `classify.py` and `layout_filter.py` hand it. Those steps must
  depend on the photo and the configuration, never on timing, load, a
  model still loading, a retry timer or a cache. #112 was exactly this:
  the layout filter switched models after one slow call and skipped itself
  while loading, so the same photo scored differently on a busy server.
  Rules: choose models and engines by env setting, not measured speed; a
  scan waits for a model rather than skipping a step; a failed load stays
  failed for the process. Two traps hide this kind of bug: the 180 s response cache
  (`VAHINI_OCR_CACHE_TTL_SEC`) answers a repeated photo, and CI stubs the
  real models. To check repeatability, set the TTL to 0 in a test
  container with the model volume mounted, or wait over 3 minutes between
  runs on stage, and include one run straight after a restart. A test for
  a step before scoring should run the same input twice with the server
  state changed in between (`backend/tests/test_layout_filter.py` shows how).
- **No AI-isms** in user-facing report text, commits, or docs (no "delve",
  "seamless", "leverage", filler praise). Coach tips speak plainly to
  parents/teachers. Full list and self-check: the `natural-writing` skill
  (`.claude/skills/natural-writing/SKILL.md`) plus `skills.md` at the root.
- **Conventional commits** (`feat:`, `fix:`, `docs:`, `test:`); body says why.
- **Build and test before every commit; CI green before merge.**
- **Docs-only changes skip CI** — `ci.yml` has `paths-ignore: ['**/*.md',
  'docs/**']`; a PR touching only markdown never triggers the pipeline. A
  mixed PR (docs + code) still runs everything — the filter only fires
  when every changed file is docs.

- **Shared chrome comes from vahini-web.** The nav, footer, cookie card
  and feedback button are injected by vahinitech.com's `site.js`, which
  `analyser.html` loads from `../site/site.js`. Never add a footer, legal
  links, patent numbers or a status link to this repository's pages: the
  site changes them once for every service. Error-screen pictures come
  only from the host's `window.VAHINI_NOTICE_ART`, and the report's
  characters (Vahini, Bheema, Pihu, Tara) only from `window.VAHINI_REPORT_ART`: same-site paths, `frontend/README.md`; the drawings are proprietary and stay out of this
  AGPL repository. Colours are `var(--v-*)` tokens, never hex codes: the redesigned report (page 1, the practice sheet, the side panel and the shared PDF, version C, 2026-10-11) follows the website theme, and only the four score colours, paper and rules are the report's own (`tests/report-colours.test.mjs`). The brand row (logo, vahinitech.com) and the patent line inside the report pages are the owner's instruction for version C and are part of the report, not site chrome.
- **Practice is data: every exercise and tip belongs to a factor.** The
  practice catalogue ([docs/10-practice-framework.md](docs/10-practice-framework.md))
  holds one development area per factor (meaning, exercises with levels and
  amounts, tips, worksheet, translations), in `backend/practice_catalog.py`,
  checked on import and served with the factor catalogue. The score band
  sets the plan (tries a day for a week); the tier table sets how many exercises and tips a
  report shows. Reports, the website's factor pages and the app read the same
  data. Never hard-code a drill in the renderer, and never print an exercise
  that does not say which skill it develops. Report text in other languages
  ships only after a native speaker's check.
- **Children read the report: every word encourages.** Start with a
  strength, call the rest "skills to grow" and "your next step", describe
  the writing and never the child, and end on encouragement. Never "weak",
  "poor", "bad", "wrong", "problem", "inadequate", "fail", "lowest" or
  "mistake" in
  report text or catalogue text, in any language. Stage labels:
  Learning, Improving, Mastering, Strong. Both report pages print on two
  A4 sheets in every tier and language, proved by printing, not by eye.
- **A choice that cannot be honoured blocks at Run, not after the report.**
  "Keep my pages" asks for its email before the check starts and is
  switched off for the sample page (#119, #120). Apply the same to any new
  option.
- **Run the whole test list ci.yml runs before calling a change ready.**
  A partial run missed the closed `/health` schema in `test_schemas`
  (#113). Browser tests need the Playwright image matching
  `node_modules/playwright` (1.63 today); ports 4173 and 4190 may be held
  by other processes on the dev box, so run a copy on a free port.

## Commands (mirror of `.github/workflows/ci.yml`)

```bash
# backend
python -m py_compile backend/*.py            # syntax gate
black --check --line-length 79 backend/*.py backend/tests/*.py frontend/build_bundle.py
# pylint --fail-under=9.0 <backend/*.py + frontend/build_bundle.py> -- see
# ci.yml for the exact file list; not reproduced here since it's not one
# glob (individual .py files, in the order ci.yml lists them)
python -m pytest backend/tests/               # unit + integration

# frontend bundle: build output, gitignored; build it to run the pages
npm run build:bundle                          # python frontend/build_bundle.py
# the image build adds --stamp; CI fails on a committed bundle or ?v= stamp

npm run test:regression:headless              # print/handwriting checks
docker compose up -d --wait                   # full stack for live recognition tests
```

## Architecture facts

- `backend/ppocr-server.py` (FastAPI): `/ocr`, `/analyze-vl`, `/report-python`, `/api/v2/me`,
  `/api/v2/reports` and versioned public catalogues.
  `computer_vision.py` owns decode/crop/evidence previews; `geometry.py`
  owns the one shared clamp-box implementation (three crop paths depend on
  it — don't fork it).
- Legacy evidence and score routes remain for compatibility. The hosted browser now uses `/api/v2/reports?format=compact&include=text` and a cached dictionary. Detailed crops are optional Pro evidence; test the changed route and its consumer, not an assumed legacy-only flow.
- `pypdfium2` is used for PDF decode but reaches the image only
  transitively — keep it explicitly pinned in `backend/requirements-core.txt`.
- OCR backends are tiered (`requirements-{core,paddle,trocr,surya}.txt`);
  the default image = core + paddle. `VAHINI_OCR_BACKEND` selects at runtime.

## Consumers — breaking changes ripple

- **vahinitech/vahini-web** consumes this repo as a git submodule pinned to a
  commit (not necessarily a release tag) and proxies `/ocr`, `/analyze-vl`, `/report-python`,
  `/api/v2/`, `/analyser/` through its nginx. Response-shape changes need a vahini-web
  submodule bump + its e2e run.
- History warning: this repo once lost an entire feature set from `main`
  via stacked-PR squash-merges (branches based on branches, then squashed).
  Base every branch on current `main`; after merging a stack, verify the
  feature actually exists on `main`, not just that PRs show "merged".

## Repository landscape

This repository is `20factor-analyser`: the open (AGPL-3.0) handwriting analyser: OCR backends, computer vision, 20-factor scoring, the version-2 report API with server-owned Free/Pro access, public catalogue versions and worksheets. Product repositories, this one included: `Umbrella` (shared skills, `dev` script, repository map), `vahini-api-contracts` (planned home of the JSON Schema and OpenAPI contracts; today `Umbrella/contracts/`), `vahini_app` (Android app, to be renamed `android`), `vahini-learning-api` (homework service, undeployed closed pilot), `20factor-analyser` (open handwriting analyser and version-2 report API, AGPL), `20factor-analyser-pro` (commercial layer: report comparison), `vahini-web` (vahinitech.com, worksheet library, analyser proxy). Full table, dependency direction, planned renames and the change order: https://github.com/vahinitech/Umbrella/blob/main/docs/REPOSITORIES.md. Cross-repo order: service PR first, then the contracts sync and tag, then consumer PRs. Never change a consumer to match an unmerged service change. It owns the report contract (`backend/schemas/*.schema.json`, catalogue versions). Consumers: `vahini-web` (git submodule pinned to a commit, to become a pinned release), `vahini_app` (anonymous Free client of the compact API), `20factor-analyser-pro` (reads report JSON). Short form: `.claude/skills/repo-landscape/SKILL.md`.

## Changelog entries are files

Every PR adds its changelog entry as a new file, `changelog.d/<branch topic>.md`,
and never edits `CHANGELOG.md`: shared lines under `## Unreleased` made every
two open PRs conflict. `python3 scripts/changelog.py --check` validates the files (run in CI);
a release folds them in with `--release X.Y.Z`. See `changelog.d/README.md`.
