# Analyser agent entrypoint

Read [CLAUDE.md](CLAUDE.md), [report contract guidance](docs/AI-REPORT-CONTRACT.md) for API/report work, and [skills.md](skills.md) for writing conventions. The repository skill is [.claude/skills/vahini-report-change/SKILL.md](.claude/skills/vahini-report-change/SKILL.md).

This is a separate open-source Git repository. The consuming website pins a companion commit. Do not bypass server-owned entitlements, edit generated bundles directly, or infer production deployment permission from an implementation task.

Repository landscape: this is `20factor-analyser` (the open (AGPL-3.0) handwriting analyser: OCR backends, computer vision, 20-factor scoring, the version-2 report API with server-owned Free/Pro access, public catalogue versions and worksheets). The product repos are `vahini-umbrella` (including `contracts/`), `vahini_app` (to be renamed `android`), `vahini-learning-api`, `20factor-analyser`, `20factor-analyser-pro` and `vahini-web`. Before touching a pin, a contract, a repo reference or another repository, read https://github.com/vahinitech/vahini-umbrella/blob/main/docs/REPOSITORIES.md and use `.claude/skills/repo-landscape/SKILL.md`. Cross-repo order: service PR first, then the contracts sync and tag, then consumer PRs. Never change a consumer to match an unmerged service change.
