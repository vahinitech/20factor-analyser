/* SPDX-License-Identifier: AGPL-3.0-only
 * (c) 2026 Vahini Technologies.
 *
 * e2e-recognition.mjs — verifies SERVER text recognition actually works.
 *
 * Unlike e2e-pages.mjs (which runs fully offline and asserts the geometry-only
 * report), this test runs against a LIVE stack with the OCR backend up
 * (the Docker compose stack, or any base via VAHINI_BASE_URL) and asserts that:
 *   - the report uses the recognition server (tag "AI OCR", not "Geometry only")
 *   - the "Text recognition not yet enabled" fallback is NOT shown
 *   - real words are recognised from the sample handwriting page
 *
 *   VAHINI_BASE_URL=http://localhost:8080 node tests/e2e-recognition.mjs
 *
 * Requires the OCR server reachable at BASE (e.g. `docker compose up -d`).
 * Optional VAHINI_PRO_KEY uses an already authorized key for staging or a
 * local stack only. No key is generated, persisted or written to artifacts.
 * With no key, the existing Free recognition tier and CI behavior remain.
 */
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import { liveRecognitionOptions } from './helpers/live-recognition-options.mjs';

const LIVE = liveRecognitionOptions();
const BASE = LIVE.base;
const SENSOR_FACTORS = [2, 4, 13, 14, 15, 16];
const EXPECTED_FACTORS = LIVE.tier === 'pro' ? Array.from({ length: 20 }, (_, i) => i + 1) : [1, 5, 7, 8, 18];
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const FIXTURE = path.join(ROOT, 'tests', 'fixtures', 'handwriting-sample.jpg');

const results = [];
const ok = (n, d = '') => results.push({ n, ok: true, d });
const fail = (n, d = '') => results.push({ n, ok: false, d });

async function main() {
  if (!fs.existsSync(FIXTURE)) fail('fixture present', FIXTURE);

  // Confirm the OCR backend is reachable before driving the UI.
  try {
    const h = await fetch(`${BASE}/ocr/health`).catch(() => fetch(`${BASE}/analyser/analyser.html`, { method: 'HEAD' }));
    if (h && (h.ok || h.status === 405)) ok('OCR backend reachable', `${BASE}`);
    else fail('OCR backend reachable', `status ${h && h.status}`);
  } catch (e) {
    fail('OCR backend reachable', String(e));
  }

  // browser is declared outside the try so the finally below can always
  // close it -- previously browser.close() sat at the end of the try block,
  // so any failure above it (e.g. a selector timeout) jumped straight to
  // catch and left the Chromium child process running. An orphaned browser
  // process keeps Node's event loop non-empty, so the script never exited
  // on its own: it hung until the CI runner's own multi-hour job timeout
  // killed it, instead of failing within seconds like the printed timeouts
  // below imply.
  let browser;
  try {
    const { chromium } = await import('playwright');
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    // Record the photo the page hands to fetch: Playwright cannot read a
    // multipart body built from a Blob.
    await page.addInitScript(() => {
      const send = window.fetch;
      window.fetch = function (url, opts) {
        const image = opts && opts.body instanceof FormData ? opts.body.get('image') : null;
        if (image) window.__vahiniUpload = { type: image.type, kb: Math.round(image.size / 1024) };
        return send.apply(this, arguments);
      };
    });
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e)));

    await page.goto(`${BASE}/analyser/analyser.html`, { waitUntil: 'load', timeout: 30000 });
    if (LIVE.key) {
      // A redirect must not move a staging credential to another website.
      if (new URL(page.url()).origin !== new URL(BASE).origin) {
        throw new Error('The staging/local page redirected to a different origin; no Pro key was sent');
      }
      // The existing account client checks the key on this origin, keeps it
      // only in this page's memory and adds it to the same-origin request.
      // Never print the thrown browser error or a request/header dump here.
      const connected = await page.evaluate(async key => {
        try { return (await VahiniAccount.connect(key)).tier === 'pro'; } catch { return false; }
      }, LIVE.key);
      if (!connected) throw new Error('The authorized staging/local key did not establish Pro access');
    }
    await page.setInputFiles('#file-input', FIXTURE);
    await page.waitForSelector('#go-process:not([disabled])', { timeout: 15000 });
    // The in-browser photo check (#87) must stay quiet on a clear photo.
    const warning = String(await page.textContent('#dz-status') || '').trim();
    if (!warning) ok('no photo warning for a clear photo');
    else fail('no photo warning for a clear photo', warning.slice(0, 120));

    // Assert against the compact /api/v2/reports response the app calls
    // (src/engine/ocr.js's serverPythonReport), not scraped report HTML --
    // that markup has been redesigned before (report-render.js's current
    // scorecard has no ".ea-head.exp"/"AI OCR" tag at all, which is why this
    // test hung/failed against current code) and will drift again. The
    // JSON response is the real, stable contract this test is meant to
    // verify: recognizer.collect_lines' selected backend and the recognised
    // text server-side, in recognition / text.
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/api/v2/reports') && r.request().method() === 'POST',
      { timeout: 180000 } // first request can include model load; allow generous time
    );
    await page.check('input[name="check-who"][value="parent"]'); await page.click('#go-process');
    const resp = await respPromise;
    const json = await resp.json();

    // The upload is a resized JPEG, not a full-size PNG (#87).
    const upload = await page.evaluate(() => window.__vahiniUpload || {});
    if (upload.type === 'image/jpeg') ok('photo uploaded as JPEG', `${upload.kb} KB`);
    else fail('photo uploaded as JPEG', JSON.stringify(upload));

    if (resp.ok() && json.ok) ok('compact report request succeeded', `HTTP ${resp.status()}`);
    else fail('compact report request succeeded', `HTTP ${resp.status()} :: ${json.error || ''}`);

    const numbers = (json.factors || []).map(f => f.n).sort((a, b) => a - b);
    if (JSON.stringify(numbers) === JSON.stringify(EXPECTED_FACTORS) && json.access?.tier === LIVE.tier) {
      ok(`${LIVE.tier} returns every expected factor exactly once`, `${numbers.length} records`);
    } else fail(`${LIVE.tier} returns every expected factor exactly once`, 'Unexpected tier or factor set');
    if (LIVE.tier === 'pro') {
      const sensorOnly = SENSOR_FACTORS.every(n => json.factors?.some(f => f.n === n && f.st === 'u' && f.s === null));
      if (sensorOnly) ok('all six sensor-only factors are unavailable on a still photo');
      else fail('all six sensor-only factors are unavailable on a still photo', 'A sensor-only factor was absent or scored');
    }

    const backend = json.recognition?.backend || '';
    if (backend && backend !== 'cv-fallback') ok('report uses recognition server', `backend "${backend}"`);
    else fail('report uses recognition server', `backend "${backend || '(none)'}" -- OCR did not run`);

    const level = json.recognition?.level || '';
    if (level && level !== 'unavailable') ok('recognition not shown as "not enabled"', `level "${level}"`);
    else fail('recognition not shown as "not enabled"', `level "${level || '(none)'}"`);

    const recText = String(json.text || '').trim();
    const recLen = recText.replace(/\s+/g, '').length;
    if (recLen >= 40) ok('real words recognised from sample', `${recLen} chars`);
    else fail('real words recognised from sample', `only ${recLen} chars: "${recText.slice(0, 80)}"`);

    // sanity: a clearly-written line should read recognisably
    if (/writing|the|hand|brown|day/i.test(recText)) ok('recognised text contains expected words');
    else fail('recognised text contains expected words', recText.slice(0, 120));

    // Sanity that the UI actually finished rendering the report too, not
    // just that the network call succeeded -- rendering is synchronous JS
    // once the response arrives, so this needs only a short timeout.
    await page.waitForSelector('#screen-report.on', { timeout: 30000 });
    const extra=await page.locator('#report-host .vl-insights').count();
    const reportText=await page.locator('#report-host').textContent();
    if(extra===0 && !reportText.includes('What kind of page is this?')) ok('document classification panel is absent from live report');
    else fail('document classification panel is absent from live report','unexpected document-context appendix');

    // Free report page 1 (version C, owner approval 2026-10-11) and the
    // next step beside it.
    const chips = await page.locator('#report-host .sn-chip').count();
    // Page 1 draws each measurement on a strip of the uploaded photo
    // (owner, 2026-10-13): the live server must send evidence.measurements.
    const strips = await page.locator('#report-host .sn-m svg image').count();
    const photo = await page.locator('#report-host .sn-zoom svg image, #report-host .sn-zoom img').count();
    const available = (json.factors || []).filter(f => f.st !== 'u' && f.s !== null).length;
    const expectedChips = LIVE.tier === 'pro' ? available : 5;
    if (chips === expectedChips && strips >= 3 && photo === 1) ok(`${LIVE.tier} report shows the photo and available skills`, `${chips} skills, ${strips} measurement strips`);
    else fail(`${LIVE.tier} report shows the photo and available skills`, `chips ${chips}, strips ${strips}, photo ${photo}`);
    if (LIVE.tier === 'pro') {
      const sensorChips = await page.locator('#report-host .sn-m-pen .sn-chip').count();
      if (sensorChips === 0) ok('Pro UI does not turn unavailable sensor-only factors into scored skills');
      else fail('Pro UI does not turn unavailable sensor-only factors into scored skills');
    }
    const nextVisible = await page.locator('#next-steps').isVisible();
    const sheet = await page.getAttribute('#ns-practice-link', 'href');
    if (nextVisible && /\.pdf$|practice\.html/.test(sheet || '')) ok('next step links a practice sheet', sheet);
    else fail('next step links a practice sheet', `visible ${nextVisible}, href ${sheet}`);

    if (pageErrors.length === 0) ok('no page errors'); else fail('no page errors', pageErrors.join('|').slice(0, 160));
  } catch (err) {
    fail('harness', String(err && err.message ? err.message : err));
  } finally {
    if (browser) await browser.close().catch(() => {});
  }

  let passed = 0;
  const redacted = text => LIVE.key ? String(text).split(LIVE.key).join('[redacted]') : text;
  for (const r of results) { console.log(redacted(`${r.ok ? 'PASS' : 'FAIL'} ${r.n}${r.d ? ` :: ${r.d}` : ''}`)); if (r.ok) passed += 1; }
  console.log(`\nSummary: ${passed}/${results.length} checks passing`);
  if (passed !== results.length || results.length === 0) process.exitCode = 1;
}

// Explicit exit as a backstop even with the browser.close() fix above: a
// CI test runner hanging past its own printed summary must never rely on
// every last handle (a stray CDP socket, etc.) closing itself.
main().finally(() => process.exit(process.exitCode ?? 0));
