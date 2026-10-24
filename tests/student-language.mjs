/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// Words and sentences to check in the student view (#317), on the free
// sample page with a `language` section added to its data:
// - a card for words and one for sentences, only from the server's
//   findings, at most three of each;
// - each finding shows the child's own ink at its place (a cut of the
//   photo), never our reading of the child's word, and the word to write;
// - a page not checked, or checked with nothing found, shows no card and
//   never says there are no mistakes;
// - the parent report is unchanged, nothing is sent, and the cards fit a
//   phone in English and in Telugu.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import { useDesign } from './design-route.mjs';
import { runSource } from './run-source.mjs';

const context = vm.createContext({ window: {} });
for (const f of ['frontend/src/report/strings/en.js', 'frontend/src/report/strings/te.js']) runSource(f, context);
const { en, te } = context.window.VahiniReportStrings;
for (const id of Object.keys(en).filter((k) => /^stu\.(sp|gr|lang)\./.test(k))) {
  assert.ok(id in te, `te.js has ${id}`);
  assert.ok(!/\b(mistake|wrong|bad|poor)\b/i.test(en[id]), `${id}: words for children`);
}

// Places on the sample photo's hardest row (its measured letters).
const place = (bbox, placed = 'letters') => [{ line: 'line_5', bbox, placed }];
const LANGUAGE = {
  version: 1,
  checked: true,
  reason: null,
  rows: { read: 9, checked: 2, not_read: 0, over_cap: 0, unclear: 0 },
  spelling: [
    { written: 'eviclc', suggestion: 'quick', kind: 'letters', against: 'sentence', places: place([153, 820, 120, 70]) },
    { written: 'Sumef', suggestion: 'jumps', kind: 'other_letter', against: 'sentence', places: place([300, 820, 110, 70]) },
    { written: 'ove', suggestion: 'over', kind: 'missing_letter', against: 'sentence', places: place([428, 820, 60, 70]) },
    { written: 'tu', suggestion: 'the', kind: 'letters', against: 'sentence', places: place([500, 820, 40, 70]) },
  ],
  grammar: [
    { rule: 'verb_s', written: 'she sing', suggestion: 'she sings', places: place([153, 804, 200, 88], 'estimated') },
  ],
};

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4213', '-c-1', '--silent']);
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4213/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const open = async (query, language, { width = 1280, lang = 'en' } = {}) => {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    await useDesign(page);
    const sent = [];
    page.on('request', (r) => { if (r.method() !== 'GET') sent.push(r.url()); });
    await page.route('**/scripts/core/sample-report-data.js', async (route) => {
      const res = await route.fetch();
      const body = (await res.text()) + (language === undefined ? '' : `\nwindow.VAHINI_SAMPLE_REPORT.language=${JSON.stringify(language)};\n`);
      await route.fulfill({ response: res, body });
    });
    await page.addInitScript((l) => { try { localStorage.setItem('vahini_report_lang', l); } catch {} }, lang);
    await page.goto(`http://127.0.0.1:4213/frontend/sample-report.html?example=free${query}`, { waitUntil: 'networkidle' });
    return { page, sent };
  };

  // The cards, from the server's findings.
  {
    const { page, sent } = await open('&for=student', LANGUAGE);
    const words = page.locator('.stu-words');
    const sentences = page.locator('.stu-sentences');
    assert.equal(await words.count(), 1, 'a card for words');
    assert.equal(await sentences.count(), 1, 'a card for sentences');
    assert.equal(await words.locator('.stu-fix').count(), 3, 'at most three words');
    assert.deepEqual(await words.locator('.stu-right').allTextContents(), ['quick', 'jumps', 'over'], 'the words to write, in order');
    assert.equal(await words.locator('.stu-fix svg.stu-ink image').count(), 3, "each word is the child's own ink, cut from the photo");
    const shown = await page.locator('.stu-lang').innerText();
    for (const w of ['eviclc', 'Sumef', 'ove ']) assert.ok(!shown.includes(w), `our reading "${w.trim()}" is never shown as the child's word`);
    assert.ok(shown.includes(en['stu.sp.copied']), 'says the words come from the copied sentence');
    assert.ok(shown.includes(en['stu.sp.letters']) && shown.includes(en['stu.sp.missing_letter']), 'a short reason for each word');
    assert.equal(await words.locator('.stu-proof ellipse.stu-m-word').count(), 3, 'the row strip circles the words on it');
    assert.equal(await sentences.locator('.stu-right').innerText(), 'she sings');
    assert.ok(shown.includes(en['stu.gr.verb_s']), 'the rule in one line');
    assert.equal(await sentences.locator('.stu-proof line.stu-m-sentence').count(), 1, 'the sentence is underlined on the strip');
    assert.equal(await page.locator('.stu-lang .stu-tip').count(), 2, "Pihu's tip on each card");
    assert.equal(sent.length, 0, 'nothing is sent');
    await page.close();
  }

  // Not checked, checked with nothing found, or no section: no card, no claim.
  for (const [what, language] of [
    ['not checked', { version: 1, checked: false, reason: 'not_english' }],
    ['nothing found', { ...LANGUAGE, spelling: [], grammar: [] }],
    ['no section', undefined],
  ]) {
    const { page } = await open('&for=student', language);
    assert.equal(await page.locator('.stu').count(), 1, `${what}: the student view is there`);
    assert.equal(await page.locator('.stu-lang').count(), 0, `${what}: no words or sentences card`);
    assert.ok(!/no (spelling|grammar)? ?mistakes/i.test(await page.locator('.stu').innerText()), `${what}: never "no mistakes"`);
    await page.close();
  }

  // The parent report does not show the cards.
  {
    const { page } = await open('', LANGUAGE);
    assert.equal(await page.locator('.stu-lang').count(), 0, 'no cards without ?for=student');
    await page.close();
  }

  // A phone, in English and in Telugu.
  for (const lang of ['en', 'te']) {
    const { page } = await open('&for=student', LANGUAGE, { width: 390, lang });
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(over <= 0, `${lang}: nothing runs off a phone screen (${over}px)`);
    const off = await page.locator('.stu-lang *').evaluateAll((els) => els.filter((e) => !(e.closest('svg') && e.tagName !== 'svg') && e.getBoundingClientRect().right > window.innerWidth + 1).length);
    assert.equal(off, 0, `${lang}: every part of the cards fits the screen`);
    const pill = await page.locator('.stu-words .stu-pill').innerText();
    assert.equal(pill, (lang === 'te' ? te : en)['stu.sp.pill'], `${lang}: the card speaks the report's language`);
    await page.close();
  }
  console.log('student language cards: all checks passed');
} finally {
  if (browser) await browser.close();
  server.kill();
}
