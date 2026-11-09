/* SPDX-License-Identifier: AGPL-3.0-only */
// Words for children (docs/10-practice-framework.md, section 7): no string in
// the report renderer, the progress panel, the share bar or the string
// tables (every language) may use a word that judges the child, in English
// or in Telugu, and none may hold an em dash. The practice catalogue has the same
// check in backend/tests/test_practice_catalog.py.
import fs from 'node:fs';
import assert from 'node:assert/strict';
const AVOID = ['weak', 'poor', 'bad', 'wrong', 'problem', 'inadequate', 'fail', 'lowest', 'mistake'];
const banned = new RegExp('\\b(' + AVOID.join('|') + ')(s|ed|ing|ly|ness|er|est)?\\b', 'i');
// No claim to diagnose, treat or "overcome" anything (owner's growth plan,
// 2026-10-11): the report encourages practice and points to a teacher or an
// occupational therapist when writing stays hard.
const claims = /\b(cur(e|es|ed|ing)|overcom\w*|disorder\w*|diagnos\w*)\b/i;
const python = fs.readFileSync('backend/report/practice_catalog.py', 'utf8');
for (const word of ['cure', 'overcome', 'disorder', 'diagnos']) assert.ok(python.includes(`"${word}"`), `practice_catalog.CLAIM_WORDS lists ${word}`);
for (const word of AVOID) assert.ok(python.includes(`"${word}"`), `practice_catalog.AVOID_WORDS lists ${word}`);
const strings = source => {
  // Quoted and template strings; comments are stripped first.
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  return [...code.matchAll(/'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`/g)].map(m => m[0]);
};
let checked = 0;
const REPORT_FILES = ['frontend/src/report/report-render.js', 'frontend/src/report/progress.js', 'frontend/src/report/report-share.js',
  'frontend/src/report/i18n.js', ...fs.readdirSync('frontend/src/report/strings').map(f => 'frontend/src/report/strings/' + f)];
const teBlock = python.match(/AVOID_WORDS_TE = \(([\s\S]*?)\)/);
const AVOID_TE = teBlock ? [...teBlock[1].matchAll(/"([^"]+)"/g)].map(m => m[1]) : [];
assert.ok(AVOID_TE.length >= AVOID.length, 'practice_catalog.AVOID_WORDS_TE lists the Telugu words');
// The owner's exception (2026-10-24): the student view's two headings say
// "Spelling mistakes" and "Grammar mistakes", in plain words a child
// knows. Every other string keeps the rule.
const ALLOWED = /^\s*'stu\.(sp|gr)\.pill': .*$/gm;
for (const file of REPORT_FILES) {
  for (const text of strings(fs.readFileSync(file, 'utf8').replace(ALLOWED, ''))) {
    checked++;
    assert.ok(!banned.test(text), `${file}: avoid ${text.match(banned)?.[0]} in ${text.slice(0, 120)}`);
    assert.ok(!claims.test(text), `${file}: no claim word ${text.match(claims)?.[0]} in ${text.slice(0, 120)}`);
    assert.ok(!text.includes('—'), `${file}: em dash in ${text.slice(0, 120)}`);
    assert.ok(!AVOID_TE.some(w => text.includes(w)), `${file}: avoid ${AVOID_TE.find(w => text.includes(w))} in ${text.slice(0, 120)}`);
  }
}
// The stage names on both pages are the catalogue's (the string table's
// stage.<band>, English being the source).
const render = fs.readFileSync('frontend/src/report/report-render.js', 'utf8');
const en = fs.readFileSync('frontend/src/report/strings/en.js', 'utf8');
for (const [band, label] of [['focus', 'Learning'], ['dev', 'Improving'], ['good', 'Mastering'], ['strong', 'Strong']]) assert.ok(en.includes(`'stage.${band}': '${label}'`), band);
for (const label of ['Learning', 'Improving', 'Mastering', 'Strong']) assert.ok(python.includes(`"label": "${label}"`), label);
assert.ok(!/simpleDrills/.test(render), 'drills live in the catalogue, not the renderer');
// The "when writing feels hard" note: encouragement, a teacher or an
// occupational therapist, and the website's page; in every language.
const tables = {};
// en-us.js only replaces the few sentences American English spells
// differently; the rest come from en.js.
for (const f of fs.readdirSync('frontend/src/report/strings').filter(f => f !== 'en-us.js')) {
  const lang = f.replace('.js', ''), src = fs.readFileSync('frontend/src/report/strings/' + f, 'utf8');
  tables[lang] = ['hard.title', 'hard.text', 'hard.more', 'row.why', 'row.win', 'row.more'].every(id => src.includes(`'${id}':`));
}
assert.ok(Object.values(tables).every(Boolean), 'every string table has the note and the row labels: ' + JSON.stringify(tables));
assert.ok(/occupational therapist/.test(en) && /signs-child-needs-handwriting-help\.html/.test(render), 'the note names who can help and links the page');
console.log(`report words: ${checked} strings checked`);
