/* SPDX-License-Identifier: AGPL-3.0-only */
// Words for children (docs/PRACTICE-FRAMEWORK.md, section 7): no string in
// the report renderer or the progress panel may use a word that judges the
// child, and none may hold an em dash. The practice catalogue has the same
// check in backend/tests/test_practice_catalog.py.
import fs from 'node:fs';
import assert from 'node:assert/strict';
const AVOID = ['weak', 'poor', 'bad', 'wrong', 'problem', 'inadequate', 'fail', 'lowest', 'mistake'];
const banned = new RegExp('\\b(' + AVOID.join('|') + ')(s|ed|ing|ly|ness|er|est)?\\b', 'i');
const python = fs.readFileSync('backend/practice_catalog.py', 'utf8');
for (const word of AVOID) assert.ok(python.includes(`"${word}"`), `practice_catalog.AVOID_WORDS lists ${word}`);
const strings = source => {
  // Quoted and template strings; comments are stripped first.
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  return [...code.matchAll(/'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`/g)].map(m => m[0]);
};
let checked = 0;
for (const file of ['frontend/src/report/report-render.js', 'frontend/src/report/progress.js']) {
  for (const text of strings(fs.readFileSync(file, 'utf8'))) {
    checked++;
    assert.ok(!banned.test(text), `${file}: avoid ${text.match(banned)?.[0]} in ${text.slice(0, 120)}`);
    assert.ok(!text.includes('—'), `${file}: em dash in ${text.slice(0, 120)}`);
  }
}
// The stage names on both pages are the catalogue's.
const render = fs.readFileSync('frontend/src/report/report-render.js', 'utf8');
assert.match(render, /BAND_LABEL = \{ strong:'Strong', good:'Mastering', dev:'Improving', focus:'Learning' \}/);
for (const label of ['Learning', 'Improving', 'Mastering', 'Strong']) assert.ok(python.includes(`"label": "${label}"`), label);
assert.ok(!/simpleDrills/.test(render), 'drills live in the catalogue, not the renderer');
console.log(`report words: ${checked} strings checked`);
