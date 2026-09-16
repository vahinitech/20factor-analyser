---
name: repo-landscape
description: Know which Vahini repository you are in, what it owns, who consumes it, and the order cross-repo changes land in. Use before any change that touches an API shape, a pin, a rename or another repository.
---

cd "$(git rev-parse --show-toplevel)"

Read the landscape page once per task: https://github.com/vahinitech/vahini-umbrella/blob/main/docs/REPOSITORIES.md (in the umbrella checkout: `docs/REPOSITORIES.md`).

1. Name this repository and its role from the table. Check `CLAUDE.md` here for the local code map.
2. List who consumes what you are changing. Services own contracts: `20factor-analyser` owns the report schemas, `vahini-learning-api` owns `openapi.json`. Consumers today: the Android app pins a contracts tag; `vahini-web` pins an analyser submodule commit (a pinned release is planned); `20factor-analyser-pro` reads analyser report JSON directly (moving to the compact contract is planned).
3. Order the work: service PR, then contracts sync and tag, then consumer PRs. Do not change a consumer to match an unmerged service change. A website change that needs a new analyser build also needs the submodule pin bump and the website's e2e run.
4. If the task renames a repo, moves a directory between repos, or creates a repo, update `docs/REPOSITORIES.md` in the umbrella in the same change set and say so in the PR body.
5. State plainly in docs what is deployed (nothing for the learning API) and what a Free report contains (factors 1, 5, 7, 8, 18). Never bundle a Pro key.

Stop and ask the user if the change needs a merge, a deployment, a repository setting or another repository you were not asked to touch.
