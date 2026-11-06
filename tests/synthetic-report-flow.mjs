/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// Full browser upload -> compact client -> existing report renderer, with
// isolated synthetic API responses. This is NOT a real OCR/Pro-stage run,
// a scoring-accuracy test, or evidence that server entitlement checks work.
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';
import { useDesign } from './design-route.mjs';
import { browserServer } from './helpers/browser-server.mjs';
import { ALL_FACTORS, FREE_FACTORS, SENSOR_FACTORS, catalog, syntheticReport, syntheticPhoto } from './helpers/synthetic-report.mjs';

const output = 'test-results/synthetic-report-flow';
await mkdir(output, { recursive: true });
const server = await browserServer();
let browser;
const summary = { source: 'synthetic browser fixtures; no real OCR or staging access', status: 'incomplete', pixelBaselines: false, browser: null, cases: [] };

async function open(viewport) {
  const context = await browser.newContext({ viewport, locale: 'en-GB', timezoneId: 'UTC', reducedMotion: 'reduce', serviceWorkers: 'block' });
  // Suppress the button tours and timed feedback card for stable review
  // screenshots. Their dedicated suites still cover those overlays.
  // The consent/guardian controls
  // are still used as a visitor uses them, and are never pre-approved.
  await context.addInitScript(() => {
    localStorage.setItem('vahini_guide_check', '1');
    localStorage.setItem('vahini_guide_report', '1');
    localStorage.setItem('vahini_report_feedback_day', '2026-01-15');
  });
  const calls = { reports: [], stores: 0, unexpected: [], catalog: 0 };
  const control = { failure: null };
  // A disposable value used only by the intercepted API; never accepted by
  // a server, saved to disk, included in artifacts or printed in assertions.
  const key = 'vh_' + randomBytes(24).toString('hex');
  await context.route('**/*', async route => {
    const req = route.request(), url = new URL(req.url());
    if (url.origin !== server.base) return route.abort();
    if (url.pathname === '/site/site.js') return route.fulfill({ contentType: 'text/javascript', body: '' });
    if (url.pathname.endsWith('/health')) return route.fulfill({ json: { ok: true } });
    const tier = req.headers().authorization === 'Bearer ' + key ? 'pro' : 'free';
    if (url.pathname === '/api/v2/me') return route.fulfill({ json: { access: syntheticReport(tier).access } });
    if (url.pathname === '/api/v2/catalog/' + catalog.version) { calls.catalog++; return route.fulfill({ json: catalog }); }
    if (url.pathname === '/api/v2/reports' && req.method() === 'POST') {
      calls.reports.push({ tier, include: url.searchParams.get('include'), format: url.searchParams.get('format') });
      if (control.failure) return route.fulfill(control.failure);
      return route.fulfill({ json: syntheticReport(tier) });
    }
    if (url.pathname.startsWith('/persist/')) { calls.stores++; return route.fulfill({ status: 500, json: { ok: false } }); }
    if (req.method() !== 'GET' && req.method() !== 'HEAD') { calls.unexpected.push(url.pathname); return route.abort(); }
    return route.continue();
  });
  await useDesign(context);
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.clock.setFixedTime(new Date('2026-01-15T12:00:00Z'));
  await page.goto(server.base + '/frontend/analyser.html', { waitUntil: 'load' });
  await page.waitForFunction(() => window.VahiniReport && window.VahiniAccount);
  // Observe the real decoder's output passed to the real renderer without
  // replacing either. Retain only factor facts, not images, text or keys.
  await page.evaluate(() => {
    const render = VahiniReport.render;
    window.__renderedFactors = [];
    VahiniReport.render = function (host, data) {
      window.__renderedFactors.push(data.analysis.results.map(({ n, score, unmeasured }) => ({ n, score, unmeasured })));
      return render.call(this, host, data);
    };
    const send = window.fetch;
    window.__uploads = [];
    window.fetch = function (url, opts) {
      if (opts?.body instanceof FormData && opts.body.has('image')) {
        const photo = opts.body.get('image');
        window.__uploads.push({ type: photo.type, bytes: photo.size, who: opts.body.get('who') });
      }
      return send.apply(this, arguments);
    };
  });
  return { context, page, calls, control, errors, key };
}

async function upload(page) {
  await page.setInputFiles('#file-input', await syntheticPhoto(page));
  await page.waitForSelector('#go-process:not([disabled])');
}

async function screenshot(page, name) {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${output}/${name}.png`, fullPage: true, animations: 'disabled' });
}

async function assertReport(state, tier) {
  const { page, calls, errors } = state;
  await page.waitForSelector('#screen-report.on', { timeout: 20000 });
  if (await page.locator('#report-host.stu-folded .stu-more').count()) {
    await page.locator('#report-host .stu-more').click();
  }
  const expected = syntheticReport(tier).factors;
  const actual = await page.evaluate(() => window.__renderedFactors.at(-1));
  assert.deepEqual(actual, expected.map(({ n, s, st }) => ({ n, score: s, unmeasured: st === 'u' })), `${tier}: every returned factor survives decoding and rendering`);
  assert.equal(new Set(actual.map(f => f.n)).size, expected.length, 'factor numbers are unique');
  const chips = await page.locator('#report-host .sn-chip').evaluateAll(els => els.map(e => Number(e.dataset.factor)).sort((a, b) => a - b));
  assert.deepEqual(chips, expected.filter(f => f.st !== 'u').map(f => f.n), 'only available factors show score bands');
  assert.equal(await page.locator('#report-host .sn-m-pen .sn-chip').count(), 0, 'a still photo never scores pen-only skills');
  assert.equal(await page.locator('#report-host .sn-pen-skill').count(), SENSOR_FACTORS.length, 'all six sensor-only skills are labelled separately');
  assert.match(await page.locator('#report-host .sn-m-pen').innerText(), /sensor pen/i);
  assert.equal(await page.locator('#report-host .page').count(), 2, 'the existing two report sections remain');
  assert.equal(await page.locator('#report-host .sn-m svg image').count(), 5, 'all five synthetic measurement strips reach the renderer');
  const facts = await page.evaluate(() => window.VAHINI_CHECK_FACTS);
  assert.deepEqual(facts.factors.map(f => f.n), tier === 'pro' ? ALL_FACTORS : FREE_FACTORS);
  for (const n of SENSOR_FACTORS) {
    const fact = facts.factors.find(f => f.n === n);
    if (tier === 'pro') assert.ok(fact.score === null && fact.measured === false, `factor ${n}: unavailable, not a zero or a measured score`);
  }
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no horizontal page overflow');
  assert.equal(calls.stores, 0, 'no keep/upload/store request without opt-in');
  assert.deepEqual(calls.unexpected, [], 'no unexpected write request');
  assert.deepEqual(errors, [], 'no JavaScript page errors');
  const sent = calls.reports.at(-1);
  assert.deepEqual(sent, { tier, include: tier === 'pro' ? 'text,inputs,coaching,evidence' : 'text,evidence', format: 'compact' });
  const uploads = await page.evaluate(() => window.__uploads);
  assert.ok(uploads.every(p => p.type === 'image/jpeg' && p.bytes > 0 && p.bytes <= 5 * 1024 * 1024), 'the chosen photo is sent as a bounded JPEG');
  assert.ok(uploads.every(p => ['parent', 'student'].includes(p.who)), 'every upload carries who is checking');
}

async function runCase(name, viewport, run) {
  const state = await open(viewport);
  try {
    await run(state);
    summary.cases.push({ name, passed: true });
    console.log(`PASS synthetic browser: ${name}`);
  } catch (error) {
    summary.cases.push({ name, passed: false });
    await screenshot(state.page, name + '-failure').catch(() => {});
    throw error;
  } finally { await state.context.close(); }
}

try {
  browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
  summary.browser = browser.version();
  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 1000 }]) {
    await runCase(`free-pro-${viewport.width}`, viewport, async state => {
      const { page, calls, key } = state;
      await upload(page);
      assert.equal(await page.locator('input[name="check-who"]:checked').count(), 0, 'first visit has no preselected consent role');
      await page.click('#go-process');
      await page.waitForSelector('#who-error:not([hidden])');
      assert.equal(calls.reports.length, 0, 'no scan before choosing who checks');
      await page.check('input[name="check-who"][value="student"]');
      assert.equal(await page.locator('#who-adult').isChecked(), false, 'adult approval is not pre-ticked');
      await page.click('#go-process');
      assert.equal(calls.reports.length, 0, 'no scan before the adult tick');
      assert.equal(await page.evaluate(() => localStorage.getItem('vahini_check_who')), null, 'Student is not remembered');
      await page.check('#who-adult');
      await screenshot(page, `consent-${viewport.width}`);
      await page.click('#go-process');
      await assertReport(state, 'free');
      assert.equal(calls.reports.length, 1);
      await screenshot(page, `free-${viewport.width}`);
      await page.locator('#new-report').click();
      await page.waitForSelector('#screen-upload.on');
      await page.check('input[name="check-who"][value="parent"]');
      await page.getByText('Have a Vahini access key?', { exact: true }).click();
      await page.locator('#account-key').fill(key);
      await page.getByRole('button', { name: 'Connect account', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('#account-access [role="status"]').textContent.includes('Pro connected'));
      assert.equal(await page.locator('#account-key').inputValue(), '', 'the transient test key is cleared');
      assert.ok(await page.evaluate(secret => !JSON.stringify([localStorage, sessionStorage, location.href]).includes(secret), key), 'the transient key is not stored or placed in the URL');
      await upload(page);
      await page.click('#go-process');
      await assertReport(state, 'pro');
      assert.equal(calls.reports.length, 2);
      assert.equal(calls.catalog, 1, 'the same dictionary is reused across scans');
      await screenshot(page, `pro-${viewport.width}`);
      // A repeated run after Disconnect must not reuse Pro data or headers.
      await page.locator('#new-report').click();
      await page.waitForSelector('#screen-upload.on');
      await page.getByRole('button', { name: 'Disconnect', exact: true }).click();
      await upload(page);
      await page.click('#go-process');
      await assertReport(state, 'free');
      assert.equal(calls.reports.length, 3);
    });
  }
  await runCase('blocked-keep-error-retry', { width: 390, height: 844 }, async state => {
    const { page, calls, control } = state;
    await upload(page);
    await page.check('input[name="check-who"][value="parent"]');
    await page.check('#keep-pages');
    await page.click('#go-process');
    await page.waitForSelector('#keep-email-error:not([hidden])');
    assert.equal(calls.reports.length, 0, 'keep with no email blocks before upload');
    assert.equal(calls.stores, 0);
    await page.uncheck('#keep-pages');
    control.failure = { status: 503, headers: { 'Retry-After': '20' }, json: { detail: { error_code: 'ocr_unavailable' } } };
    await page.click('#go-process');
    await page.waitForSelector('#screen-process .reject-card');
    assert.match(await page.locator('.reject-card').innerText(), /did not score this page/);
    assert.equal(await page.locator('#screen-report.on').count(), 0);
    assert.equal((await page.evaluate(() => window.__renderedFactors)).length, 0, 'a server refusal never renders a score');
    await screenshot(page, 'ocr-error-390');
    control.failure = null;
    await page.locator('#reject-retry').click();
    await page.waitForSelector('#screen-upload.on');
    await upload(page);
    await page.click('#go-process');
    await assertReport(state, 'free');
    assert.equal(calls.reports.length, 2, 'one refused request then one successful retry');
  });
  summary.status = 'passed';
} finally {
  await writeFile(`${output}/summary.json`, JSON.stringify(summary, null, 2) + '\n');
  if (browser) await browser.close();
  await server.close();
}
console.log('Synthetic UI coverage only. Screenshots are review artifacts, not approved pixel baselines or real OCR evidence.');
