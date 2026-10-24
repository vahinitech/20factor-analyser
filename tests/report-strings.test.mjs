/* SPDX-License-Identifier: AGPL-3.0-only */
// The report's string tables (docs/10-practice-framework.md, "Print in the
// parent's language"): every id English has, each listed language has too
// (a missing one is printed in English for that sentence, and listed here);
// placeholders and count forms match English; a missing id falls back to
// English; no word that judges the child, in either language; no em dash;
// the Telugu stage names are the approved ones; the Telugu spelling lines
// say the check covered English words only; the Telugu font is bundled
// with its licence.
import fs from 'node:fs';
import vm from 'node:vm';
import { runSource } from './run-source.mjs';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

const window = {};
const context = vm.createContext({ window, localStorage: undefined });
for (const file of ['frontend/src/report/strings/en.js', 'frontend/src/report/strings/en-us.js', 'frontend/src/report/strings/te.js', 'frontend/src/report/i18n.js']) {
  runSource(file, context);
}
const { en, te } = window.VahiniReportStrings;
const i18n = window.VahiniI18n;
const LANGS = { te };

// American English only replaces English sentences, with the same
// placeholders, and changes the spelling of practise (owner, 2026-10-24).
const us = window.VahiniReportStrings['en-US'];
for (const [id, value] of Object.entries(us)) {
  assert.ok(id in en, `en-us.js: ${id} is an English id`);
  assert.deepEqual(String(value).match(/\{\w+\}/g) || [], String(en[id]).match(/\{\w+\}/g) || [], `en-us.js: ${id} keeps the placeholders`);
}
assert.ok(!Object.values(us).some(v => /practis/i.test(v)), 'American English says practice');

// Completeness: list what is missing per language, then fail on it.
let failed = false;
for (const [lang, table] of Object.entries(LANGS)) {
  const missing = [...i18n.missing(lang)];
  const extra = Object.keys(table).filter(id => !(id in en));
  console.log(`${lang}: ${Object.keys(en).length - missing.length}/${Object.keys(en).length} ids translated` + (missing.length ? `; missing: ${missing.join(', ')}` : ''));
  if (missing.length || extra.length) failed = true;
  assert.deepEqual(extra, [], `${lang}.js has ids English does not: ${extra.join(', ')}`);
}
assert.ok(!failed, 'te.js must be complete (see the missing ids above)');

// Placeholders and count forms match English, id by id.
const holes = v => [...String(v).matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort().join(',');
const forms = v => (v && typeof v === 'object') ? Object.keys(v) : null;
for (const [lang, table] of Object.entries(LANGS)) {
  for (const [id, value] of Object.entries(table)) {
    const base = en[id];
    if (forms(base)) {
      assert.ok(forms(value) && 'other' in value, `${lang} ${id}: needs one/other forms like English`);
      const all = new Set(Object.values(base).flatMap(v => holes(v).split(',').filter(Boolean)));
      for (const form of Object.values(value)) {
        for (const h of holes(form).split(',').filter(Boolean)) assert.ok(all.has(h) || h === 'n', `${lang} ${id}: unknown placeholder {${h}}`);
      }
      assert.ok(Object.values(value).some(v => /\{n\}/.test(v)) || !Object.values(base).some(v => /\{n\}/.test(v)) || 'one' in value, `${lang} ${id}: count missing`);
    } else {
      assert.equal(holes(value), holes(base), `${lang} ${id}: placeholders differ from English`);
    }
  }
}

// Fallback: an id the language lacks prints the English sentence.
delete te['p2.title'];
const t = i18n.translator('te');
assert.equal(t('p2.title'), en['p2.title'], 'a missing Telugu id falls back to English');
assert.equal(JSON.stringify(i18n.missing('te')), '["p2.title"]', 'and the missing id is reported');
assert.equal(t('other.item', { skill: 'A', stage: t('stage.dev') }), 'A (మెరుగవుతోంది)');
assert.equal(t.n('pp.file.loaded', 1), 'సేవ్ అయిన 1 చెక్‌ను లోడ్ చేశాం.');
assert.equal(i18n.translator('en').n('sn.since.better', 1), '1 skill got better.', 'a count of one uses the one form');
assert.equal(i18n.translator('en').n('sn.since.better', 3), '3 skills got better.');
assert.equal(i18n.translator('xx')('p2.title'), en['p2.title'], 'an unknown language is English');
assert.equal(t.html('spell.saw', { word: '<b>recieve</b>', suggestion: '<b>receive</b>' }).includes('<b>recieve</b>'), true);
assert.ok(i18n.translator('en').html('pp.keep').includes('&quot;Keep my pages&quot;'), 'html() escapes the table text');
runSource('frontend/src/report/strings/te.js', context);

// The approved stage names (owner, 2026-10-11).
assert.deepEqual(['focus', 'dev', 'good', 'strong'].map(b => window.VahiniReportStrings.te['stage.' + b]),
  ['నేర్చుకుంటోంది', 'మెరుగవుతోంది', 'పట్టు సాధిస్తోంది', 'బలంగా ఉంది']);
assert.deepEqual(['focus', 'dev', 'good', 'strong'].map(b => en['stage.' + b]), ['Learning', 'Improving', 'Mastering', 'Strong']);
// The Telugu says the spelling check covered English words only.
for (const id of ['spelling.deferred', 'spelling.notext', 'spelling.found', 'spelling.clear', 'spell.saw', 'sn.spell.saw']) {
  assert.match(window.VahiniReportStrings.te[id], /ఇంగ్లీష్/, `te ${id} says the check covered English words`);
}

// Words for children, both languages; no em dash anywhere.
const python = fs.readFileSync('backend/report/practice_catalog.py', 'utf8');
const AVOID = ['weak', 'poor', 'bad', 'wrong', 'problem', 'inadequate', 'fail', 'lowest', 'mistake'];
const banned = new RegExp('\\b(' + AVOID.join('|') + ')(s|ed|ing|ly|ness|er|est)?\\b', 'i');
const teBlock = python.match(/AVOID_WORDS_TE = \(([\s\S]*?)\)/);
assert.ok(teBlock, 'practice_catalog.AVOID_WORDS_TE exists');
const AVOID_TE = [...teBlock[1].matchAll(/"([^"]+)"/g)].map(m => m[1]);
assert.ok(AVOID_TE.length >= AVOID.length, 'a Telugu word for every avoided English word');
// The owner's exception (2026-10-24): the student view's two headings,
// "Spelling mistakes" and "Grammar mistakes", in every language.
const HEADINGS = new Set(['stu.sp.pill', 'stu.gr.pill']);
const texts = table => Object.entries(table).filter(([id]) => !HEADINGS.has(id)).flatMap(([, v]) => (v && typeof v === 'object') ? Object.values(v) : [v]);
for (const [lang, table] of Object.entries(window.VahiniReportStrings)) {
  for (const text of texts(table)) {
    assert.ok(!banned.test(text), `${lang}: avoid ${String(text.match(banned)?.[0])} in ${text}`);
    assert.ok(!AVOID_TE.some(w => text.includes(w)), `${lang}: avoid ${AVOID_TE.find(w => text.includes(w))} in ${text}`);
    assert.ok(!text.includes('—'), `${lang}: em dash in ${text}`);
  }
}
// Telugu is written in Telugu: every sentence but the score formats has Telugu letters.
const latinOnly = Object.entries(window.VahiniReportStrings.te).filter(([id, v]) => typeof v === 'string' && !/[ఀ-౿]/.test(v)
  && !['meta.locale', 'other.item', 'sn.start.meta'].includes(id));
assert.deepEqual(latinOnly.map(([id]) => id), [], 'Telugu table entries without Telugu text');

// Simple English (owner, 2026-10-11): a parent with basic English and a
// child of 8 read the report. Short sentences: none over 16 words, and an
// average under 10. The words for children are checked above.
const sentences = text => String(text).replace(/\{\w+\}/g, 'x').split(/(?<=[.!?:])\s+/).filter(s => /\w/.test(s));
const english = texts(en).filter(text => typeof text === 'string');
const long = english.flatMap(sentences).filter(s => s.split(/\s+/).length > 16);
assert.deepEqual(long, [], 'report sentences over 16 words');
const all = english.flatMap(sentences);
const average = all.reduce((n, s) => n + s.split(/\s+/).length, 0) / all.length;
assert.ok(average < 10, `average sentence length ${average.toFixed(1)} words`);
const HARD = ['utilise', 'utilize', 'commence', 'subsequently', 'approximately', 'additionally', 'consistency', 'proficiency', 'legibility', 'cursive', 'diagnos'];
for (const text of english) assert.ok(!HARD.some(w => text.toLowerCase().includes(w)), `a plainer word than ${HARD.find(w => text.toLowerCase().includes(w))} in ${text}`);

// The Telugu font is bundled, unchanged, with its licence and source.
const sources = JSON.parse(fs.readFileSync('frontend/assets/fonts/sources.json', 'utf8'));
for (const file of ['NotoSansTelugu-Regular.woff2', 'NotoSansTelugu-Bold.woff2', 'notosanstelugu-OFL.txt']) {
  const entry = sources.find(s => s.file === file);
  assert.ok(entry && entry.license === 'OFL-1.1', `${file} is listed with its licence`);
  const hash = crypto.createHash('sha256').update(fs.readFileSync('frontend/assets/fonts/' + file)).digest('hex');
  assert.equal(hash, entry.sha256, `${file} matches its recorded source`);
}
assert.match(fs.readFileSync('frontend/assets/fonts/notosanstelugu-OFL.txt', 'utf8'), /SIL OPEN FONT LICENSE Version 1\.1/);
const fontsCss = fs.readFileSync('frontend/styles/report-fonts.css', 'utf8');
assert.match(fontsCss, /font-family:'Noto Sans Telugu';src:url\('..\/assets\/fonts\/NotoSansTelugu-Regular\.woff2'\)[^}]*font-display:swap;unicode-range:[^}]*U\+0C00-0C7F/);
assert.match(fs.readFileSync('THIRD-PARTY-NOTICES.md', 'utf8'), /Noto Sans Telugu/);
assert.match(fs.readFileSync('sbom.spdx.json', 'utf8'), /NotoSansTelugu-Regular\.woff2/);
console.log(`report strings: ${Object.keys(en).length} ids, ${Object.keys(LANGS).length} language(s) complete`);
