/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// The student view (owner, 2026-10-23, option A), on the free sample page:
// - without ?for=student the report is today's, with no student card;
// - with it, one card above the pages: a strength, one thing to practise and
//   the five free skills, each sentence beside its proof from the page;
// - no score and no skill name in the card; sentences of ten words or fewer;
// - the pages fold behind "Details for your teacher" on screen, and print as
//   two A4 pages with the card left out;
// - "Report for" switches back without a new scan, and the choice is never
//   sent anywhere;
// - nothing runs off a phone screen, in English or in Telugu.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import { useDesign } from './design-route.mjs';
import { runSource } from './run-source.mjs';

const context = vm.createContext({ window: {} });
for (const f of ['frontend/src/report/strings/en.js', 'frontend/src/report/strings/te.js']) runSource(f, context);
const { en, te } = context.window.VahiniReportStrings;
const stu = Object.keys(en).filter((id) => id.startsWith('stu.'));
assert.ok(stu.length >= 30, 'the student strings are in the English table');
for (const id of stu) {
  assert.ok(id in te, `te.js has ${id}`);
  const value = en[id];
  for (const text of typeof value === 'object' ? Object.values(value) : [value]) {
    for (const sentence of String(text).split(/(?<=[.!])\s+/)) {
      assert.ok(sentence.split(/\s+/).length <= 10, `${id}: ten words or fewer: "${sentence}"`);
    }
  }
}
const skillNames = Object.keys(en).filter((id) => /^name\.\d+$/.test(id)).map((id) => en[id].toLowerCase());

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4207', '-c-1', '--silent']);
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4207/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const open = async (query, { width = 1280, lang = 'en' } = {}) => {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    await useDesign(page);
    const sent = [];
    page.on('request', (r) => { if (r.method() !== 'GET') sent.push(r.url() + ' ' + (r.postData() || '')); });
    await page.addInitScript((l) => { try { localStorage.setItem('vahini_report_lang', l); } catch {} }, lang);
    await page.goto(`http://127.0.0.1:4207/frontend/sample-report.html?example=free${query}`, { waitUntil: 'networkidle' });
    return { page, sent };
  };

  // Today's report: no card, both pages on screen.
  {
    const { page } = await open('');
    assert.equal(await page.locator('.stu').count(), 0, 'no student card without ?for=student');
    assert.equal(await page.locator('section.page:visible').count(), 2, 'both pages show');
    assert.equal(await page.locator('#report-for').inputValue(), 'parent', '"Report for" starts on parents and teachers');
    await page.close();
  }

  // The student view.
  {
    const { page, sent } = await open('&for=student');
    const card = page.locator('.stu');
    assert.equal(await card.count(), 1, 'one student card');
    assert.equal(await page.locator('section.page:visible').count(), 0, 'the pages are folded on screen');
    const rows = await page.locator('.stu-row').evaluateAll((list) => list.map((r) => ({
      n: r.dataset.factor, state: r.dataset.state, proof: !!r.querySelector('.stu-proof svg image'), text: r.querySelector('p').textContent,
    })));
    assert.deepEqual(rows.map((r) => r.n).sort(), ['1', '18', '5', '7', '8'], 'the five free skills');
    assert.equal(rows.filter((r) => r.state === 'now').length, 1, 'one skill to practise this week');
    for (const r of rows) {
      assert.ok(r.proof || r.text.includes(en['stu.noproof']), `skill ${r.n} has its proof, or says it has none`);
    }
    assert.ok(await page.locator('.stu-work .stu-proof svg image').count(), 'the thing to practise has its proof');
    assert.ok(await page.locator('.stu-greet .stu-proof svg image').count(), 'the strength has its proof');
    assert.ok(await page.locator('.stu-work .sn-m-gap, .stu-work .sn-m-slope, .stu-work .sn-m-read, .stu-work .sn-m-band').count(), 'its marks are drawn');
    // No score and no skill name: the only numbers are the practice amount
    // and how many things the card lists.
    const words = (await card.evaluate((el) => {
      const c = el.cloneNode(true); c.querySelectorAll('.stu-plan, svg').forEach((x) => x.remove()); return c.textContent;
    })).toLowerCase().replace(/\b\d+ things? on your page/, '');
    assert.ok(!/\d/.test(words), `no score in the card: ${words.match(/.{0,20}\d.{0,20}/)}`);
    for (const name of skillNames) assert.ok(!words.includes(name), `no skill name in the card: ${name}`);
    for (const stage of ['learning', 'improving', 'mastering', 'strong']) assert.ok(!new RegExp(`\\b${stage}\\b`).test(words), `no stage name: ${stage}`);
    const sheet = await page.locator('.stu-btn').getAttribute('href');
    assert.match(sheet || '', /\/assets\/worksheets\/[\w-]+\.pdf$/, 'the button opens the practice sheet');
    // "Details for your teacher" opens the pages and folds them again.
    const more = page.locator('.stu-more');
    await more.click();
    assert.equal(await more.getAttribute('aria-expanded'), 'true');
    assert.equal(await page.locator('section.page:visible').count(), 2, 'the details show both pages');
    await more.click();
    assert.equal(await page.locator('section.page:visible').count(), 0, 'and fold them again');
    // Print: the two pages, never the card, folded or not.
    await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
    await page.emulateMedia({ media: 'print' });
    assert.equal(await card.isVisible(), false, 'the card does not print');
    assert.equal(await page.locator('section.page:visible').count(), 2, 'both pages print');
    await page.emulateMedia({ media: 'screen' });
    await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
    assert.equal(await page.locator('section.page:visible').count(), 0, 'folded again after printing');
    // "Report for" switches back without a new scan; nothing is sent.
    await page.selectOption('#report-for', 'parent');
    assert.equal(await page.locator('.stu').count(), 0, 'switching to parents removes the card');
    assert.equal(await page.locator('section.page:visible').count(), 2);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('vahini_report_for')), 'parent', 'kept in this tab');
    await page.selectOption('#report-for', 'student');
    assert.equal(await page.locator('.stu').count(), 1, 'and back');
    assert.deepEqual(sent.filter((s) => /student|report_for/.test(s)), [], 'the choice is never sent');
    await page.close();
  }

  // A phone, in English and in Telugu.
  for (const lang of ['en', 'te']) {
    const { page } = await open('&for=student', { width: 390, lang });
    assert.equal(await page.locator('.stu').getAttribute('aria-label'), (lang === 'te' ? te : en)['stu.label']);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(over <= 0, `${lang}: nothing runs off a phone screen (${over}px)`);
    // The page photo inside each strip is wider than the strip, which clips it.
    const off = await page.locator('.stu *').evaluateAll((els) => els.filter((e) => !(e.closest('svg') && e.tagName !== 'svg') && e.getBoundingClientRect().right > window.innerWidth + 1).length);
    assert.equal(off, 0, `${lang}: every part of the card fits the screen`);
    await page.close();
  }
  console.log('student view: all checks passed');
} finally {
  if (browser) await browser.close();
  server.kill();
}
