/* SPDX-License-Identifier: AGPL-3.0-only */
// The report follows the vahinitech.com theme (owner instruction,
// 2026-10-11): page 1, the practice sheet, the side panel and the shared PDF
// use var(--v-*) tokens from /site/design/v1/vahini.css. Only the report's
// own colours (score bands, paper, rules) are literals in report.css, and no
// stylesheet may gain one: vahini-web's input-manifest.yaml holds the same
// caps and counts them the same way (tools/check-input-manifest.py).
// Lower a cap when literals move to tokens; never raise one.
import fs from 'node:fs';
import assert from 'node:assert/strict';
const CAPS = { 'frontend/styles/report.css': 86, 'frontend/styles/studio.css': 72, 'frontend/styles/nav.css': 37 };
const LITERAL = /#[0-9a-fA-F]{3,8}\b|rgba?\(/g;
for (const [file, cap] of Object.entries(CAPS)) {
  const css = fs.readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
  const found = (css.match(LITERAL) || []).length;
  assert.ok(found <= cap, `${file}: ${found} colour literals (cap ${cap}); use var(--v-*) tokens`);
}
// The version C rules (everything after its heading) use tokens only, apart
// from the one orange the four score colours needed.
const report = fs.readFileSync('frontend/styles/report.css', 'utf8');
const versionC = report.slice(report.indexOf('Version C (owner approval')).replace(/\/\*[\s\S]*?\*\//g, '');
assert.deepEqual(versionC.match(LITERAL) || [], [], 'the redesigned report uses theme tokens, no colour codes');
const bands = report.match(/--sn-(strong|good|dev|focus):[^;]+;/g);
assert.equal(bands.length, 4, 'four score colours');
console.log('report colours: theme tokens only, literals within the caps');
