# changelog.d

Each PR adds **one new file** here instead of editing `CHANGELOG.md`:
`changelog.d/<topic>.md`, named after the branch topic (`fix/practice-svg`
becomes `practice-svg.md`), holding one or more Keep a Changelog bullets.

Why: when every PR added its line at the top of `## Unreleased`, any two
open PRs changed the same lines and the second to merge conflicted. Two PRs
never add the same file. (git's `merge=union` would keep both lines, but
GitHub's merge button ignores it.)

- Write a new file; never edit another PR's file or `CHANGELOG.md`.
- Plain prose, what changed and why, no em dashes.
- `python3 scripts/changelog.py --print` shows the next release's entries; `--check`
  validates them (run in CI).
- A release (only when asked): `python3 scripts/changelog.py --release X.Y.Z` folds every
  file into `CHANGELOG.md` under `## X.Y.Z - <date>`, deletes them and bumps
  the version source; tag `vX.Y.Z` after it merges.

The tool's canonical copy is `scripts/changelog.py` in
[vahinitech/Umbrella](https://github.com/vahinitech/Umbrella); copy changes
from there.
