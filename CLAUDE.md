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
  2026-10-07). `backend/server/capacity.py` sizes the slots from memory, cores and
  GPUs with constants measured on the deploy box; change a constant only
  with a load-test measurement (`backend/tools/load_test.py`, stage only), and
  never remove the cap. Model and numbers:
  #97 and `docs/13-api-and-capacity.md`.
- **Scans run in a child process the server outlives** (`backend/server/scan_worker.py`,
  #299, on in the image with `VAHINI_SCAN_WORKER=1`). The process that answers
  HTTP never loads a model; anything passed to `scan_slots.run` must be a
  module-level function with arguments that pickle. A scan lost with the child
  runs once more the same way, never on a lighter path (owner decision on #299:
  same photo, same score), and a second loss is 503 `ocr_unavailable`. Unit
  tests run scans in-process; `test_scan_worker.py` kills a real child.
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
- **Never write a malware-scanner string in one piece.** The vahinitech.com server's nightly maldet scan (home folders and `/tmp`) flagged scratch copies of `backend/tests/test_image_formats.py` on 2026-10-16 because a fake upload held a PHP open tag joined to `system(` (`php.generic.globals.503`). In code, fixtures, comments, docs and file names: build attack payloads from parts at run time (`b"<?php " + b"system(...)"`), never join a PHP open tag to `system(`, `eval(`, `exec(`, `passthru(` or `base64_decode(`, never commit the EICAR string, and never create a file named like a web shell (`shell.php`, `c99.php`); pass the name as data. `backend/tests/test_scanner_strings.py` (in CI) fails on one, using maldet's own signatures where the server has them.
- **Conventional commits** (`feat:`, `fix:`, `docs:`, `test:`); body says why.
- **Build and test before every commit; CI green before merge.**
- **Resolve comments and conflicts first, then merge (owner, 2026-10-14).** Before merging a pull request: answer every review comment and code-scanning alert on it, by fixing the code or replying why not, and resolve each thread; a bot's comment (CodeQL, Copilot) counts like a person's. Bring the branch up to date with `main` and resolve any merge conflict. Then wait for CI on that final commit to pass, and only then merge. Check with `gh pr view <n> --json mergeable` (must be `MERGEABLE`) and `gh api graphql -f query='{repository(owner:"vahinitech",name:"<repo>"){pullRequest(number:<n>){reviewThreads(first:100){nodes{isResolved}}}}}'` (every `isResolved` true). #150 merged with two CodeQL threads still showing open; the code was fixed, but nobody could tell from the PR.
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
  amounts, tips, worksheet, translations), in `backend/report/practice_catalog.py`,
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
  report text or catalogue text, in any language. One exception (owner,
  2026-10-24): the student view's headings "Spelling mistakes" and
  "Grammar mistakes", in plain words a child knows; the tests allow those
  two ids only. English follows the place: Indian English (British
  spelling) by default, American English (`strings/en-us.js`) for a
  reader in the Americas. Stage labels:
  Learning, Improving, Mastering, Strong. Both report pages print on two
  A4 sheets in every tier and language, proved by printing, not by eye.
- **A choice that cannot be honoured blocks at Run, not after the report.**
  "Keep my pages" asks for its email before the check starts and is
  switched off for the sample page (#119, #120). Apply the same to any new
  option.
- **A scoring or reading change runs the real-handwriting benchmark.**
  `python scripts/benchmark.py check` replays 20 real pages through the
  change; any score that moves fails CI until `benchmark.py update` is run
  and `benchmarks/uji-clean/expected.json` is committed, so the PR diff
  shows every move. Floors on lines scored, no line scored twice and no
  measured 0 cannot be updated away. Never add children's photos to
  `benchmarks/`. How it works: [docs/18-benchmark.md](docs/18-benchmark.md).
- **Text read from a page keeps no name or number (DPDP Act, section 6(1)).**
  It passes `backend/reading/identifiers.py` before it is cached or
  returned: names after "My name is" and the like, emails, phone numbers,
  roll numbers and school names become `[name]`, `[email]` and so on. A new
  text field in a payload goes in its `TEXT_KEYS`.
- **Pro access is granted on the server, never in code.** Operators follow
  [docs/17-access-and-trials.md](docs/17-access-and-trials.md); `deployment/grant-pro.sh`
  does a grant in one command and leaves the key in a private file. Every
  key is random and only its hash is stored: never write a key into the
  repository, a commit, a PR or a log, and never make one from a chosen word.
- **CI runs a benchmark only when a change can move it.**
  `scripts/score_closure.py` follows the imports from the benchmark
  scripts (scores) and from the reader up to the scorer (reader), plus the
  data each reads. A first `changes` job skips the replay, paired timing,
  history, factor, calibration and live-reader jobs on a pull request that
  touches neither list; pushes to main, the weekly runs and runs by hand
  run them all. Before pushing, run
  `python scripts/score_closure.py changed origin/main`. For scores, run
  `python scripts/benchmark.py check`, `factors`, `factors --ruled` and
  `planted`, and `python scripts/calibrate.py` when a scale moved. For
  reader, the live reader needs the analyser image, so CI's run is the
  check. A module loaded by name (importlib, a file path) is invisible to
  the closure: add its entry or data to `GROUPS`, or `test_score_closure`
  fails. Details: docs/18-benchmark.md, "When the benchmarks run".
- **Run the whole test list ci.yml runs before calling a change ready.**
  A partial run missed the closed `/health` schema in `test_schemas`
  (#113). Browser tests need the Playwright image matching
  `node_modules/playwright` (1.63 today); ports 4173 and 4190 may be held
  by other processes on the dev box, so run a copy on a free port.

## Commands (mirror of `.github/workflows/ci.yml`)

```bash
# backend
python -m py_compile backend/*.py backend/*/*.py   # syntax gate
black --check --line-length 79 frontend/build_bundle.py backend/*.py backend/*/*.py
# pylint --fail-under=9.0 <backend/*.py + frontend/build_bundle.py> -- see
# ci.yml for the exact file list; not reproduced here since it's not one
# glob (individual .py files, in the order ci.yml lists them)
python -m unittest discover -v -s backend/tests -t .   # unit + integration

# benchmarks: which ones this change needs, then run those
python scripts/score_closure.py changed origin/main
python scripts/benchmark.py check             # scores: the real pages replayed
python scripts/benchmark.py factors && python scripts/benchmark.py factors --ruled
python scripts/benchmark.py planted

# frontend bundle: build output, gitignored; build it to run the pages
npm run build:bundle                          # python frontend/build_bundle.py
# the image build adds --stamp; CI fails on a committed bundle or ?v= stamp

npm run test:regression:headless              # print/handwriting checks
docker compose up -d --wait                   # full stack for live recognition tests
```

## Architecture facts

- `backend/server/app.py` (FastAPI): `/ocr`, `/analyze-vl`, `/report-python`, `/api/v2/me`,
  `/api/v2/reports` and versioned public catalogues.
  `computer_vision.py` owns decode/crop/evidence previews; `geometry.py`
  owns the one shared clamp-box implementation (three crop paths depend on
  it — don't fork it).
- Legacy evidence and score routes remain for compatibility. The hosted browser now uses `/api/v2/reports?format=compact&include=text` and a cached dictionary. Detailed crops are optional Pro evidence; test the changed route and its consumer, not an assumed legacy-only flow.
- `pypdfium2` is used for PDF decode but reaches the image only
  transitively — keep it explicitly pinned in `backend/requirements/core.txt`.
- OCR backends are tiered (`requirements/{core,paddle,trocr,surya}.txt`);
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
