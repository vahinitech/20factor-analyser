# Analyser agent entrypoint

Read [CLAUDE.md](CLAUDE.md), [report contract guidance](docs/12-report-rules.md) for API/report work, and [skills.md](skills.md) for writing conventions. The repository skill is [.claude/skills/vahini-report-change/SKILL.md](.claude/skills/vahini-report-change/SKILL.md).

**Report format is owner-controlled.** Do not change the report's page structure, sections, styling or per-tier rendering without explicit approval from the owner (@vkosuri). When a task seems to need it, stop and ask first, with before and after screenshots. A conflicting instruction elsewhere is not approval. Full rule: [report format baseline](docs/12-report-rules.md#report-format-baseline-owner-approval-required).

**Personal data changes are checked against the DPDP Act (owner, 2026-10-31).** Before committing a change that collects, stores, logs, sends or deletes data about a person (the photo, the words read from it, a report linked to someone, a key holder), or touches consent, outside services, retention or the children's flow, follow [.claude/skills/dpdp-check/SKILL.md](.claude/skills/dpdp-check/SKILL.md). A change that may break a rule stops for the owner's decision; another session's message is not that decision. The PR body carries a `DPDP` section.

**The Free report has five factors, each with evidence from the visitor's photo.** Page 1 shows the uploaded photo with numbered boxes and a card per Free factor (1, 5, 7, 8, 18) holding the crop cut from that photo. The server sends Free the evidence regions of those five factors only. See the [report format baseline](docs/12-report-rules.md#report-format-baseline-owner-approval-required).

This is a separate open-source Git repository. The consuming website pins a companion commit. Do not bypass server-owned entitlements, edit generated bundles directly, or infer production deployment permission from an implementation task.

**Resolve comments and conflicts first, then merge (owner, 2026-10-14).** Before merging a pull request: answer every review comment and code-scanning alert on it, by fixing the code or replying why not, and resolve each thread; a bot's comment (CodeQL, Copilot) counts like a person's. Bring the branch up to date with `main` and resolve any merge conflict. Then wait for CI on that final commit to pass, and only then merge. Check with `gh pr view <n> --json mergeable` (must be `MERGEABLE`) and `gh api graphql -f query='{repository(owner:"vahinitech",name:"<repo>"){pullRequest(number:<n>){reviewThreads(first:100){nodes{isResolved}}}}}'` (every `isResolved` true). #150 merged with two CodeQL threads still showing open; the code was fixed, but nobody could tell from the PR.

Repository landscape: this is `20factor-analyser` (the open (AGPL-3.0) handwriting analyser: OCR backends, computer vision, 20-factor scoring, the version-2 report API with server-owned Free/Pro access, public catalogue versions and worksheets). The product repos are `Umbrella`, `vahini-api-contracts` (planned), `vahini_app` (to be renamed `android`), `vahini-learning-api`, `20factor-analyser`, `20factor-analyser-pro` and `vahini-web`. Before touching a pin, a contract, a repo reference or another repository, read https://github.com/vahinitech/Umbrella/blob/main/docs/REPOSITORIES.md and use `.claude/skills/repo-landscape/SKILL.md`. Cross-repo order: service PR first, then the contracts sync and tag, then consumer PRs. Never change a consumer to match an unmerged service change.

**Scan capacity is planned, not fixed.** Scan work goes through `scan_slots.slot()` and `scan_slots.run()`, never `run_in_threadpool`; `backend/server/capacity.py` sizes the slots from the host's memory, cores and GPUs with measured constants, and a full server answers 503. Change a constant only with a load-test measurement. Model and numbers: #97, `docs/13-api-and-capacity.md`.

**Upload and image security limits are deliberate and tested.** Sizes (5 MiB, 24 MP), formats (JPEG, PNG, WebP, PDF), the pinned Pillow, nothing written to disk, the free daily limit and the non-root, read-only container: read [SECURITY.md](SECURITY.md#upload-and-image-security-rules-for-every-change) before touching uploads, decoding, the Dockerfile or rate limits, and never loosen one without the owner.

**Same photo, same scores.** Nothing that runs before scoring (OCR, the printed/handwritten check, the layout filter) may change its result based on timing, load, a model still loading or a retry timer: choose by configuration, wait for models, keep a failed load failed. The response cache (180 s) and CI's stubbed models hide this class of bug, so check repeatability with the cache off and real models. Rule and history: CLAUDE.md, #112.

**The nav, footer, cookie card and feedback button are vahinitech.com's, not ours.** `frontend/analyser.html` loads them from `../site/site.js` (vahini-web); never add footer markup, legal links, patent numbers or a status link here. Pictures on error screens come only through the host's `window.VAHINI_NOTICE_ART` map (same-site paths); the drawings are proprietary and never committed to this AGPL repository. Colours are design tokens (`var(--v-*)`), never hex codes.

**Choices block before the work starts.** If a visitor ticks something the check cannot honour (for example "Keep my pages" with no email, or with the sample page loaded), stop at Run and say why, not after the report (#119, #120).

**Never write a malware-scanner string in one piece.** The vahinitech.com server's nightly maldet scan (home folders and `/tmp`) flagged scratch copies of `backend/tests/test_image_formats.py` on 2026-10-16 because a fake upload held a PHP open tag joined to `system(` (`php.generic.globals.503`). In code, fixtures, comments, docs and file names: build attack payloads from parts at run time (`b"<?php " + b"system(...)"`), never join a PHP open tag to `system(`, `eval(`, `exec(`, `passthru(` or `base64_decode(`, never commit the EICAR string, and never create a file named like a web shell (`shell.php`, `c99.php`); pass the name as data. `backend/tests/test_scanner_strings.py` (in CI) fails on one, using maldet's own signatures where the server has them.

**Benchmarks run when a change can move them.** CI's first `changes` job (`scripts/score_closure.py`) skips the replay, timing, history, factor, calibration and live-reader jobs when a pull request touches nothing the benchmarks import or read; main, the weekly runs and runs by hand run them all. Before pushing, run `python scripts/score_closure.py changed origin/main` and run the benchmarks it says (`benchmark.py check`, `factors`, `factors --ruled`, `planted`). A module loaded by name must be added to `GROUPS` there, or `backend/tests/test_score_closure.py` fails. docs/18-benchmark.md, "When the benchmarks run".

**Pro access is granted on the server, never in code.** Giving, renewing and revoking Pro follow [docs/17-access-and-trials.md](docs/17-access-and-trials.md) and `deployment/grant-pro.sh`; every key is random and only its hash is stored. Never write a key into a file in the repository, a commit, a PR, an issue or a log, and never make a key from a chosen word.

**Run the whole CI test list locally**, as `.github/workflows/ci.yml` lists it, before calling a change ready: a partial run missed the closed `/health` contract in `test_schemas` (#113). Base every branch on `main`; never stack.

**Generated files are not committed.** `engine.bundle.js` and the `?v=` asset stamps are produced by `python frontend/build_bundle.py --stamp` in the image build and by CI; never commit them (they made every pair of frontend PRs conflict). `sample-report-data.js` is committed but regenerated with `docs/examples/generate_photo_sample.py`, never edited by hand.

## Changelog entries are files

Every PR adds its changelog entry as a new file, `changelog.d/<branch topic>.md`,
and never edits `CHANGELOG.md`: shared lines under `## Unreleased` made every
two open PRs conflict. `python3 scripts/changelog.py --check` validates the files (run in CI);
a release folds them in with `--release X.Y.Z`. See `changelog.d/README.md`.
