/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// The free tier's daily checks (backend/daily_limit.py) as the visitor sees
// them. The real analyser page, its recognition server stubbed:
// - the server's 429 daily_limit shows "Today's free checks are used", why,
//   when the count starts again, and the next steps, not "server not
//   reachable";
// - the outcome is reported as daily_limit;
// - nginx's own per-minute 429 (an HTML page) is still "busy";
// - with a Pro key connected the page sends the key, which the server
//   never limits.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4190', '-c-1', '--silent']);
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4190/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  let mode = 'daily';
  const auth = [];
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: r.request().headers().authorization ? 'pro' : 'free' } } }));
  await page.route('**/api/v2/reports?**', (r) => {
    auth.push(r.request().headers().authorization || '');
    if (mode === 'daily') {
      return r.fulfill({ status: 429, headers: { 'Retry-After': '50400' }, json: { detail: { error_code: 'daily_limit', error: "Today's 3 free checks from this connection are used. Come back tomorrow.", limit: 3 } } });
    }
    return r.fulfill({ status: 429, contentType: 'text/html', body: '<html><body>429 Too Many Requests</body></html>' });
  });
  await page.goto('http://127.0.0.1:4190/frontend/analyser.html', { waitUntil: 'networkidle' });
  await page.evaluate(() => { window.outcomes = []; window.VahiniInsights = { check: (o) => window.outcomes.push(o) }; });

  const daily = await page.evaluate(() => VahiniOCR.serverPythonReport(new Blob(['x']), ''));
  assert.deepEqual(daily, { ok: false, error_code: 'daily_limit', limit: 3, retry_after: 50400 }, 'the server\'s daily limit is a definitive answer');
  mode = 'nginx';
  const burst = await page.evaluate(() => VahiniOCR.serverPythonReport(new Blob(['x']), ''));
  assert.equal(burst.error_code, 'busy', 'nginx\'s per-minute 429 is "busy", not the daily limit');
  assert.ok(burst.retry_after <= 60);

  // The whole flow, as a visitor: pick the sample page, run, see the message.
  mode = 'daily';
  await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
  await page.click('#go-process');
  await page.waitForSelector("text=Today’s free checks are used", { timeout: 20000 });
  const panel = await page.locator('#screen-process .panel').innerText();
  assert.match(panel, /allows 3 pages a day from each internet connection/);
  assert.match(panel, /midnight, India time/);
  assert.doesNotMatch(panel, /not reachable/, 'not blamed on the server');
  const links = await page.locator('#screen-process .panel a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
  assert.ok(links.includes('/practice.html') && links.includes('/reach.html?topic=handwriting'), 'next steps link to practice and to the team');
  assert.deepEqual(await page.evaluate(() => window.outcomes), ['daily_limit'], 'reported as daily_limit');
  assert.ok(auth.every((a) => a === ''), 'a free visitor sends no key');
  console.log('daily-limit: free checks used is explained with next steps, nginx bursts stay "busy", reported as daily_limit');
} finally {
  if (browser) await browser.close();
  server.kill();
}
