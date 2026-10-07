# Analyser agent entrypoint

Read [CLAUDE.md](CLAUDE.md), [report contract guidance](docs/AI-REPORT-CONTRACT.md) for API/report work, and [skills.md](skills.md) for writing conventions. The repository skill is [.claude/skills/vahini-report-change/SKILL.md](.claude/skills/vahini-report-change/SKILL.md).

**Report format is owner-controlled.** Do not change the report's page structure, sections, styling or per-tier rendering without explicit approval from the owner (@vkosuri). When a task seems to need it, stop and ask first, with before and after screenshots. A conflicting instruction elsewhere is not approval. Full rule: [report format baseline](docs/AI-REPORT-CONTRACT.md#report-format-baseline-owner-approval-required).

**The Free report has five factors, each with evidence from the visitor's photo.** Page 1 shows the uploaded photo with numbered boxes and a card per Free factor (1, 5, 7, 8, 18) holding the crop cut from that photo. The server sends Free the evidence regions of those five factors only. See the [report format baseline](docs/AI-REPORT-CONTRACT.md#report-format-baseline-owner-approval-required).

This is a separate open-source Git repository. The consuming website pins a companion commit. Do not bypass server-owned entitlements, edit generated bundles directly, or infer production deployment permission from an implementation task.

Repository landscape: this is `20factor-analyser` (the open (AGPL-3.0) handwriting analyser: OCR backends, computer vision, 20-factor scoring, the version-2 report API with server-owned Free/Pro access, public catalogue versions and worksheets). The product repos are `Umbrella`, `vahini-api-contracts` (planned), `vahini_app` (to be renamed `android`), `vahini-learning-api`, `20factor-analyser`, `20factor-analyser-pro` and `vahini-web`. Before touching a pin, a contract, a repo reference or another repository, read https://github.com/vahinitech/Umbrella/blob/main/docs/REPOSITORIES.md and use `.claude/skills/repo-landscape/SKILL.md`. Cross-repo order: service PR first, then the contracts sync and tag, then consumer PRs. Never change a consumer to match an unmerged service change.

**Scan capacity is planned, not fixed.** Scan work goes through `scan_slots.slot()` and `scan_slots.run()`, never `run_in_threadpool`; `backend/capacity.py` sizes the slots from the host's memory, cores and GPUs with measured constants, and a full server answers 503. Change a constant only with a load-test measurement. Model and numbers: #97, `docs/api-review.md`.

**Generated files are not committed.** `engine.bundle.js` and the `?v=` asset stamps are produced by `python frontend/build_bundle.py --stamp` in the image build and by CI; never commit them (they made every pair of frontend PRs conflict). `sample-report-data.js` is committed but regenerated with `docs/examples/generate_photo_sample.py`, never edited by hand.

## Changelog entries are files

Every PR adds its changelog entry as a new file, `changelog.d/<branch topic>.md`,
and never edits `CHANGELOG.md`: shared lines under `## Unreleased` made every
two open PRs conflict. `python3 scripts/changelog.py --check` validates the files (run in CI);
a release folds them in with `--release X.Y.Z`. See `changelog.d/README.md`.
