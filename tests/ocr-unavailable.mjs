/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// When the server cannot read a page it answers 503 with error_code
// "ocr_unavailable" (#112) instead of scoring rough line shapes. The real
// analyser page, its recognition server stubbed:
// - the answer is "could not read your photo just now, try again", not
//   "busy" and not "server not reachable";
// - no report is shown, and the free check is said not to be used up;
// - the outcome is reported as ocr_unavailable;
// - a plain 503 (the scan cap) is still "busy".
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4191', '-c-1', '--silent']);
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4191/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  let mode = 'unreadable';
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
  await page.route('**/api/v2/reports?**', (r) => {
    if (mode === 'unreadable') {
      return r.fulfill({ status: 503, headers: { 'Retry-After': '60' }, json: { detail: { error_code: 'ocr_unavailable', error: 'The analyser could not read this photo just now. Please try again in a minute.' } } });
    }
    return r.fulfill({ status: 503, headers: { 'Retry-After': '20' }, json: { detail: 'The analyser is busy. Please try again in a moment.' } });
  });
  await page.goto('http://127.0.0.1:4191/frontend/analyser.html', { waitUntil: 'networkidle' });
  await page.evaluate(() => { window.outcomes = []; window.VahiniInsights = { check: (o) => window.outcomes.push(o) }; });

  const unread = await page.evaluate(() => VahiniOCR.serverPythonReport(new Blob(['x']), ''));
  assert.deepEqual(unread, { ok: false, error_code: 'ocr_unavailable', retry_after: 60 });
  mode = 'busy';
  const busy = await page.evaluate(() => VahiniOCR.serverPythonReport(new Blob(['x']), ''));
  assert.deepEqual(busy, { ok: false, error_code: 'busy', retry_after: 20 }, 'the scan cap is still "busy"');

  mode = 'unreadable';
  await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
  await page.click('#go-process');
  await page.waitForSelector('text=We could not read your photo just now', { timeout: 20000 });
  const panel = await page.locator('#screen-process .panel').innerText();
  assert.match(panel, /did not use up one of your free checks/);
  assert.match(panel, /Wait a minute, then upload the photo again/);
  assert.doesNotMatch(panel, /not reachable|busy/i, 'not blamed on load or a dead server');
  assert.equal(await page.locator('#screen-report.on').count(), 0, 'no report is shown');
  assert.deepEqual(await page.evaluate(() => window.outcomes), ['ocr_unavailable'], 'reported as ocr_unavailable');
  console.log('ocr-unavailable: an unread page asks for a retry, shows no report, reported as ocr_unavailable; the scan cap stays "busy"');
} finally {
  if (browser) await browser.close();
  server.kill();
}
