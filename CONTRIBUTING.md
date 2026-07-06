# Contributing to the Vahini 20-Factor Analyser

Thanks for your interest! This project is free software under the
**GNU AGPL-3.0**.

## Contributor license agreement

By submitting a contribution (a pull request, patch, or code in an issue)
you agree that:

1. You wrote the contribution yourself, or you have the right to submit it.
2. Your contribution is licensed to everyone under **AGPL-3.0-only**, the
   same license as the project.
3. You additionally grant **Vahini Technologies** a perpetual, worldwide,
   non-exclusive, royalty-free right to use, modify, and distribute your
   contribution under other license terms, including in commercial and
   proprietary versions of this software.

Point 3 is what lets the project offer a hosted or pro edition without
chasing every past contributor for permission. Your contribution always
stays AGPL in this repository; nothing is taken away from the community
version. If you cannot accept this grant, say so in the PR and we will
discuss it before merging.

## Feature requests

- Have an idea? [Open an issue](https://github.com/vahinitech/20factor-analyser/issues)
  describing the problem it solves and who it helps.
- Need a specific feature for your school, coaching centre, or product,
  or prefer to discuss privately? Email **info@vahinitech.com**.

## Ground rules

- **No personal data in the repo.** Never commit real handwriting samples that
  contain personal, medical, or otherwise identifying information. `samples/` is
  git-ignored. Test fixtures under `tests/fixtures/` must be synthetic or
  contain **no personal data** (e.g. historical or stock pages).
- **No secrets.** API keys (e.g. `DATALAB_API_KEY`), tokens or passwords belong
  in environment variables, never in code, commits, or issues.
- Keep the engine **deterministic and explainable**: scores are real geometry
  computed from pixels/motion, never random or inferred personality traits.
- **Handwriting only.** Printed text must never reach the factor
  measurements, the reference crops, or the recognised text. If a change
  could leak printed content into a report, add a regression to
  `backend/tests/test_handwriting_only.py` first.
- Match the surrounding code style. House style for prose: no em dashes, no
  AI-isms. The full checklist is in [skills.md](skills.md).

## Development setup

```bash
# Browser engine: edit frontend/src/, then ALWAYS rebuild the bundle
python frontend/build_bundle.py

# Python OCR/20-factor server
pip install -r backend/requirements-core.txt
```

The packed bundle `frontend/scripts/core/engine.bundle.js` is generated from
`frontend/src/`. CI fails if it is out of sync, so commit the rebuilt bundle
together with your `src/` changes.

## Before you open a PR

Run what CI runs:

```bash
python frontend/build_bundle.py          # then `git diff --exit-code` the bundle
python -m unittest -v \
  backend.tests.test_backends_classify \
  backend.tests.test_server_pipeline \
  backend.tests.test_regression_functional \
  backend.tests.test_handwriting_only
npm ci && npx playwright install --with-deps chromium
npm run test:regression:headless
```

## Headers

New source files should carry the SPDX header used throughout the tree:

```
SPDX-License-Identifier: AGPL-3.0-only
© 2026 Vahini Technologies. Distributed under GNU AGPL v3.0 only.
```

## Pull requests

- Keep PRs focused; describe what changed and why.
- Link any related issue.
- Make sure CI is green.

Questions? Open an issue or email info@vahinitech.com.
