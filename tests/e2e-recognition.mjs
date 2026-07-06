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
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e)));

    await page.goto(`${BASE}/analyser/analyser.html`, { waitUntil: 'load', timeout: 30000 });
    await page.setInputFiles('#file-input', FIXTURE);
    await page.waitForSelector('#go-process:not([disabled])', { timeout: 15000 });

    // Assert against the ACTUAL /report-python response the app calls
    // (src/engine/ocr.js's serverPythonReport), not scraped report HTML --
    // that markup has been redesigned before (report-render.js's current
    // scorecard has no ".ea-head.exp"/"AI OCR" tag at all, which is why this
    // test hung/failed against current code) and will drift again. The
    // JSON response is the real, stable contract this test is meant to
    // verify: recognizer.collect_lines' selected backend and the recognised
    // text server-side, in analysis.recognition / full_text.
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/report-python') && r.request().method() === 'POST',
      { timeout: 180000 } // first request can include model load; allow generous time
    );
    await page.click('#go-process');
    const resp = await respPromise;
    const json = await resp.json();

    if (resp.ok() && json.ok) ok('report-python request succeeded', `HTTP ${resp.status()}`);
    else fail('report-python request succeeded', `HTTP ${resp.status()} :: ${json.error || ''}`);

    const backend = json.selected_backend || '';
    if (backend && backend !== 'cv-fallback') ok('report uses recognition server', `backend "${backend}"`);
    else fail('report uses recognition server', `backend "${backend || '(none)'}" -- OCR did not run`);

    const level = (json.analysis && json.analysis.recognition && json.analysis.recognition.level) || '';
    if (level && level !== 'unavailable') ok('recognition not shown as "not enabled"', `level "${level}"`);
    else fail('recognition not shown as "not enabled"', `level "${level || '(none)'}"`);

    const recText = String(json.full_text || '').trim();
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
