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
 */
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const BASE = (process.env.VAHINI_BASE_URL || 'http://localhost:8080').replace(/\/$/, '');
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const FIXTURE = path.join(ROOT, 'tests', 'fixtures', 'handwriting-sample.jpg');

const results = [];
const ok = (n, d = '') => results.push({ n, ok: true, d });
const fail = (n, d = '') => results.push({ n, ok: false, d });

async function main() {
  if (!fs.existsSync(FIXTURE)) fail('fixture present', FIXTURE);

  // Confirm the OCR backend is reachable before driving the UI.
  try {
    const h = await fetch(`${BASE}/ocr/health`).catch(() => fetch(`${BASE}/analyser/Vahini%20Analyser.html`, { method: 'HEAD' }));
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
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e)));

    await page.goto(`${BASE}/analyser/Vahini%20Analyser.html`, { waitUntil: 'load', timeout: 30000 });
    await page.setInputFiles('#file-input', FIXTURE);
    await page.waitForSelector('#go-process:not([disabled])', { timeout: 15000 });
    await page.click('#go-process');

    // First request can include model load; allow generous time.
    await page.waitForSelector('#screen-report.on', { timeout: 180000 });
    await page.waitForSelector('.ea-head.exp', { timeout: 30000 });

    const info = await page.evaluate(() => {
      const tag = (document.querySelector('.ea-head.exp .tag') || {}).textContent || '';
      const notEnabled = document.body.innerText.includes('Text recognition not yet enabled');
      const recPanel = (document.querySelector('.ea-panel') || {}).innerText || '';
      // recognised lines = the panel text minus its header/caption
      const recText = recPanel.replace(/DETECTED & RECOGNISED TEXT|AI OCR/gi, '').trim();
      return { tag: tag.trim(), notEnabled, recLen: recText.replace(/\s+/g, '').length, recText };
    });

    if (info.tag.includes('AI OCR') || info.tag.includes('AI')) ok('report uses recognition server', `tag "${info.tag}"`);
    else fail('report uses recognition server', `tag "${info.tag}"`);

    if (!info.notEnabled) ok('recognition not shown as "not enabled"');
    else fail('recognition not shown as "not enabled"', 'fallback message present');

    if (info.recLen >= 40) ok('real words recognised from sample', `${info.recLen} chars`);
    else fail('real words recognised from sample', `only ${info.recLen} chars: "${info.recText.slice(0, 80)}"`);

    // sanity: a clearly-written line should read recognisably
    if (/writing|the|hand|brown|day/i.test(info.recText)) ok('recognised text contains expected words');
    else fail('recognised text contains expected words', info.recText.slice(0, 120));

    if (pageErrors.length === 0) ok('no page errors'); else fail('no page errors', pageErrors.join('|').slice(0, 160));
  } catch (err) {
    fail('harness', String(err && err.message ? err.message : err));
  } finally {
    if (browser) await browser.close().catch(() => {});
  }

  let passed = 0;
  for (const r of results) { console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.n}${r.d ? ` :: ${r.d}` : ''}`); if (r.ok) passed += 1; }
  console.log(`\nSummary: ${passed}/${results.length} checks passing`);
  if (passed !== results.length || results.length === 0) process.exitCode = 1;
}

// Explicit exit as a backstop even with the browser.close() fix above: a
// CI test runner hanging past its own printed summary must never rely on
// every last handle (a stray CDP socket, etc.) closing itself.
main().finally(() => process.exit(process.exitCode ?? 0));
