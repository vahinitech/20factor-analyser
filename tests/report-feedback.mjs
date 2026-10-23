/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// "How was the report?" (analyser.html, owner approval 2026-10-23). The real
// check page with its recognition server stubbed, on Playwright's clock:
// - it appears ten seconds after the report, not before, and not while the
//   report is off screen or the tab is hidden;
// - one tap sends one fixed code through window.VahiniInsights.reportFeedback
//   and nothing else; the card thanks and closes; the close button sends nothing;
// - once a day in this browser; never for "Try a sample"; never after a print
//   or a share; it waits while the print popup or the feedback form is open;
// - without the site script an answer does nothing and breaks nothing;
// - never printed; Pihu comes only from the host and is cut to the drawing.
// SHOT=<dir> also writes desktop and phone screenshots of the card without
// a picture (docs/report-feedback/).
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { chromium } from 'playwright';
import { useDesign } from './design-route.mjs';

const freePort = () => new Promise((resolve, reject) => {
  const s = createServer(); s.once('error', reject);
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)); });
});
const PORT = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const version = readdirSync('backend/catalogs').find((f) => f.endsWith('.json')).replace(/\.json$/, '');
const catalog = readFileSync(`backend/catalogs/${version}.json`);
const REPORT = { schema_version: '2.1', format: 'compact', catalog_version: version, ok: true, access: { tier: 'free' },
  summary: { score: 60 }, factors: [1, 5, 7, 8, 18].map((n) => ({ n, s: 6, st: 'e' })) };
const ANSWERS = ['useful', 'trying', 'scores_off', 'print_later', 'no_printout', 'other'];
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', String(PORT), '-a', '127.0.0.1', '-c-1', '-s']);

// A 360x360 picture with a 120x60 figure at (100, 200), like the host's
// Pihu (a figure in empty space). Same-origin data, so it can be measured.
const ART = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360"><rect x="100" y="200" width="120" height="60" fill="teal"/></svg>');

let browser;
async function openPage({ insights = true, art = ART, viewport = { width: 1280, height: 900 } } = {}) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await useDesign(page);
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
  await page.route('**/api/v2/catalog/**', (r) => r.fulfill({ contentType: 'application/json', body: catalog }));
  await page.route('**/api/v2/reports?**', (r) => r.fulfill({ json: REPORT }));
  await page.route('**/persist/**', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/missing-art/**', (r) => r.fulfill({ status: 404, body: '' }));
  await page.addInitScript(({ insights, art }) => {
    window.answers = [];
    if (art) window.VAHINI_REPORT_ART = { tip: art };
    if (insights) window.VahiniInsights = { check: () => {}, reportFeedback: (...args) => window.answers.push(args) };
    window.print = () => {};
    window.__vis = 'visible';
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => window.__vis });
  }, { insights, art });
  await page.clock.install();
  await page.goto(BASE + '/frontend/analyser.html', { waitUntil: 'load' });
  return { context, page, errors };
}
// Runs a check to its report; the clock moves only as far as the check needs.
async function check(page, { sample = false } = {}) {
  if (sample) await page.click('#try-sample');
  else await page.setInputFiles('#file-input', 'tests/fixtures/handwriting-sample.jpg');
  for (let i = 0; i < 100 && !(await page.locator('#go-process:enabled').count()); i++) await page.clock.runFor(100);
  await page.click('#go-process');
  for (let i = 0; i < 300 && !(await page.locator('#screen-report.on').count()); i++) await page.clock.runFor(100);
  assert.equal(await page.locator('#screen-report.on').count(), 1, 'the stubbed check reaches its report');
}
const shown = (page) => page.evaluate(() => !document.getElementById('report-feedback').hidden);

try {
  for (let i = 0; i < 50; i++) { try { if ((await fetch(BASE + '/frontend/analyser.html', { method: 'HEAD' })).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();

  // Ten seconds after the report, one tap, one code.
  let { context, page, errors } = await openPage();
  await check(page);
  await page.clock.runFor(9000);
  assert.equal(await shown(page), false, 'not before ten seconds');
  await page.clock.runFor(1500);
  assert.equal(await shown(page), true, 'shown ten seconds after the report');
  assert.equal(await page.locator('#rfb-title').innerText(), 'How was the report?');
  assert.deepEqual([await page.locator('#rfb-ask').isVisible(), await page.locator('#rfb-done').isVisible()], [true, false], 'the question, not the thanks');
  assert.deepEqual(await page.locator('.rfb__opts button').evaluateAll((b) => b.map((x) => [x.dataset.answer, x.textContent])),
    [['useful', 'Useful'], ['trying', 'Just trying it out'], ['scores_off', "Scores don't look right"], ['print_later', "I'll print it later"], ['no_printout', "I don't need a printout"], ['other', 'Something else']],
    'the six approved answers, as worded');
  assert.equal(await page.locator('#report-feedback input, #report-feedback textarea, #report-feedback select').count(), 0, 'nothing can be typed');
  const pihu = await page.evaluate(() => { const f = document.querySelector('#rfb-ask .rfb__pihu'); return { hidden: f.hidden, w: f.offsetWidth, h: f.offsetHeight }; });
  assert.deepEqual(pihu, { hidden: false, w: 84, h: 42 }, "the host's picture, cut to the figure and 84px wide");
  assert.equal(await page.evaluate(() => !!document.activeElement.closest('#report-feedback')), false, 'it does not take the focus');
  await page.emulateMedia({ media: 'print' });
  assert.equal(await page.evaluate(() => getComputedStyle(document.getElementById('report-feedback')).display), 'none', 'never printed');
  await page.emulateMedia({ media: 'screen' });
  await page.click('button[data-answer="no_printout"]');
  assert.deepEqual(await page.evaluate(() => window.answers), [['no_printout']], 'one call, the fixed code only');
  assert.deepEqual([await page.locator('#rfb-ask').isVisible(), await page.locator('#rfb-done').isVisible()], [false, true], 'says thank you in place of the question');
  assert.deepEqual(await page.evaluate(() => { const f = document.querySelector('#rfb-done .rfb__pihu'); return [f.offsetWidth, f.offsetHeight]; }), [84, 42], 'with the same picture');
  await page.clock.runFor(3000);
  assert.equal(await shown(page), false, 'and closes');
  assert.ok(await page.evaluate(() => /^\d{4}-\d{2}-\d{2}$/.test(localStorage.getItem('vahini_report_feedback_day'))), 'the browser keeps the day only');

  // Once a day: the next check in this browser is not asked.
  await page.click('#new-report');
  await check(page);
  await page.clock.runFor(15000);
  assert.equal(await shown(page), false, 'not asked twice in a day');
  assert.deepEqual(errors, [], 'no page errors');
  await context.close();

  // The close button sends nothing; a hidden tab or another screen does not count.
  ({ context, page, errors } = await openPage({ viewport: { width: 390, height: 844 } }));
  await check(page);
  await page.evaluate(() => { window.__vis = 'hidden'; });
  await page.clock.runFor(20000);
  assert.equal(await shown(page), false, 'a hidden tab does not count');
  await page.evaluate(() => { window.__vis = 'visible'; document.getElementById('screen-report').classList.remove('on'); });
  await page.clock.runFor(20000);
  assert.equal(await shown(page), false, 'off the report screen does not count');
  await page.evaluate(() => document.getElementById('screen-report').classList.add('on'));
  await page.clock.runFor(10500);
  assert.equal(await shown(page), true, 'ten seconds on the visible report');
  await page.click('#rfb-close');
  assert.equal(await shown(page), false, 'closed with one tap');
  assert.deepEqual(await page.evaluate(() => window.answers), [], 'closing sends nothing');
  assert.deepEqual(errors, [], 'no page errors');
  await context.close();

  // Never after a print or a share in this check.
  for (const id of ['print-report', 'share-pdf']) {
    ({ context, page, errors } = await openPage());
    await check(page);
    await page.clock.runFor(3000);
    await page.evaluate((id) => document.getElementById(id).click(), id);
    await page.evaluate(() => { document.getElementById('vgate').classList.remove('on'); });
    await page.clock.runFor(20000);
    assert.equal(await shown(page), false, `not after #${id}`);
    await context.close();
  }

  // It waits while the print popup or the feedback form is open.
  ({ context, page, errors } = await openPage());
  await check(page);
  await page.evaluate(() => { const d = document.createElement('div'); d.id = 'vfb-ov'; d.className = 'on'; document.body.appendChild(d); });
  await page.clock.runFor(15000);
  assert.equal(await shown(page), false, 'not on top of the feedback form');
  await page.evaluate(() => document.getElementById('vfb-ov').classList.remove('on'));
  await page.clock.runFor(600);
  assert.equal(await shown(page), true, 'shown once the form closes');
  await context.close();

  // Never for "Try a sample".
  ({ context, page, errors } = await openPage());
  await check(page, { sample: true });
  await page.clock.runFor(20000);
  assert.equal(await shown(page), false, 'never for the sample');
  await context.close();

  // The host's picture does not load, or there is none: the card shows no
  // picture, never a broken image.
  for (const art of ['/missing-art/pihu.webp', null]) {
    ({ context, page, errors } = await openPage({ art }));
    await check(page);
    await page.clock.runFor(10500);
    // The 404 arrives over the network, not on the page clock.
    for (let i = 0; i < 40 && await page.evaluate(() => document.querySelectorAll('.rfb__pihu img').length); i++) await new Promise((r) => setTimeout(r, 50));
    assert.equal(await shown(page), true, `shown with art ${art}`);
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('.rfb__pihu')].map((f) => [f.hidden, f.querySelectorAll('img').length])),
      [[true, 0], [true, 0]], `no picture and no broken image (art ${art})`);
    assert.equal(await page.locator('#rfb-title').isVisible(), true, 'the question still shows');
    // The screenshots show this card: the drawings stay out of this repository.
    if (process.env.SHOT && !art) {
      await page.screenshot({ path: `${process.env.SHOT}/popup-desktop.png`, animations: 'disabled' });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({ path: `${process.env.SHOT}/popup-phone.png`, animations: 'disabled' });
    }
    await context.close();
  }

  // Self-hosted, no site script: an answer breaks nothing.
  ({ context, page, errors } = await openPage({ insights: false }));
  await check(page);
  await page.clock.runFor(10500);
  await page.click('button[data-answer="useful"]');
  assert.equal(await page.locator('#rfb-done').isVisible(), true, 'still says thank you');
  assert.deepEqual(errors, [], 'no page errors without VahiniInsights');
  await context.close();

  console.log(`report-feedback: asks ten seconds after the report, sends one of ${ANSWERS.length} fixed codes, once a day, never for the sample, after a print or on top of another popup, never printed`);
} finally {
  if (browser) await browser.close();
  server.kill();
}
