- The check page shows what changed lately (owner, 2026-10-24): one line
  under the heading with one of the ten latest changes, the next one on each
  visit, and the full list on a tap. The lines are written for parents and
  teachers in `frontend/whats-new.json`, each naming the changelog fragments
  it comes from, and `build_bundle.py --stamp` writes them into the page at
  build time, so the committed page carries only the empty markers.
  `tests/whats-new.test.mjs` keeps the list to ten dated lines with real
  sources and nothing internal, priced or about Telugu scoring;
  `tests/whats-new.mjs` checks the line in a browser.
