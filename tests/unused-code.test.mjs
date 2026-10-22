/* SPDX-License-Identifier: AGPL-3.0-only */
// No browser code that nothing in the product uses. The sources under
// frontend/src are joined into one script (frontend/build_bundle.py), so every
// top-level name is a global another file could call, and coverage cannot
// help: report-render.js and app.js run only in browser tests, which c8 does
// not count, so they sit at 0% and the ratchet never fails. The old role
// table, score ring and trajectory chart stayed unused for months that way.
//
// A top-level function or const in frontend/src must be named somewhere else
// in frontend/ (another source, a page, a script). Tests do not count. A name
// kept on purpose goes in KEEP with the reason. The Python side is
// backend/tests/test_unused_code.py.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

// name -> why it stays although nothing in the product uses it.
const KEEP = {};

const walk = (dir, out = []) => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) { if (entry.name !== 'vendor' && entry.name !== 'node_modules') walk(p, out); }
    else if (/\.(js|mjs|html)$/.test(entry.name) && entry.name !== 'engine.bundle.js') out.push(p);
  }
  return out;
};

const sources = walk('frontend/src').filter(p => p.endsWith('.js'));
const product = Object.fromEntries(walk('frontend').map(p => [p, fs.readFileSync(p, 'utf8')]));
const DECL = /^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(|^(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=/;

const uses = name => {
  const n = name.replace(/\$/g, '\\$');
  const re = new RegExp(`(?<![\\w$])${n}(?![\\w$])`, 'g');
  return Object.values(product).reduce((sum, text) => sum + (text.match(re) || []).length, 0);
};

const found = [];
const declared = new Set();
for (const file of sources) {
  product[file].split('\n').forEach((line, i) => {
    const m = line.match(DECL);
    if (!m) return;
    const name = m[1] || m[2];
    declared.add(name);
    // The declaration itself is one mention.
    if (uses(name) <= 1 && !(name in KEEP)) found.push(`${file}:${i + 1} ${name}`);
  });
}
assert.ok(declared.size > 50, `the scan found only ${declared.size} top-level names; is the pattern still right?`);
assert.deepEqual(found, [], `Delete these, or add them to KEEP in tests/unused-code.test.mjs with the reason:\n${found.join('\n')}`);
const stale = Object.keys(KEEP).filter(name => !declared.has(name) || uses(name) > 1);
assert.deepEqual(stale, [], `These are used or gone now; take them out of KEEP: ${stale.join(', ')}`);

// The scan must see what it is meant to: a name only the declaration mentions.
const probe = 'function vahiniUnusedProbe(){}';
assert.equal((probe.match(DECL) || [])[1], 'vahiniUnusedProbe');
console.log(`unused-code: ${declared.size} top-level names in ${sources.length} files, all used`);
