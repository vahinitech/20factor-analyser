/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// A page read as mostly numbers and sums (a maths or science notebook page)
// is refused with error_code "not_writing_page" (recognizer.not_writing_page).
// The real analyser page, its recognition server stubbed with a compact
// refusal:
// - the answer says it looks like a maths or science page and asks for four
//   lines of English, not "server not reachable";
// - no report is shown, and the free check is said not to be used up;
// - the outcome is reported as not_writing_page.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const version = readdirSync('backend/catalogs').find((f) => f.endsWith('.json')).replace(/\.json$/, '');
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4194', '-c-1', '--silent']);
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4194/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
  await page.route('**/api/v2/catalog/**', (r) => r.fulfill({ contentType: 'application/json', body: readFileSync(`backend/catalogs/${version}.json`) }));
  await page.route('**/api/v2/reports?**', (r) => r.fulfill({ json: { schema_version: '2.1', format: 'compact', catalog_version: version, ok: false, error: { code: 'not_writing_page' } } }));
  await page.goto('http://127.0.0.1:4194/frontend/analyser.html', { waitUntil: 'networkidle' });
  await page.evaluate(() => { window.outcomes = []; window.VahiniInsights = { check: (o) => window.outcomes.push(o) }; });

  const answer = await page.evaluate(() => VahiniOCR.serverPythonReport(new Blob(['x']), ''));
  assert.equal(answer.ok, false);
  assert.equal(answer.error_code, 'not_writing_page', 'the compact refusal keeps its code');

  await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
  await page.check('input[name="check-who"][value="parent"]'); await page.click('#go-process');
  await page.waitForSelector('text=This looks like a maths or science page', { timeout: 20000 });
  const panel = await page.locator('#screen-process .panel').innerText();
  assert.match(panel, /Write four lines of English/);
  assert.match(panel, /could not score the 20 factors/);
  assert.match(panel, /did not use up one of your free checks/);
  assert.doesNotMatch(panel, /not reachable|busy/i, 'not blamed on load or a dead server');
  assert.equal(await page.locator('#screen-report.on').count(), 0, 'no report is shown');
  assert.deepEqual(await page.evaluate(() => window.outcomes), ['not_writing_page'], 'reported as not_writing_page');
  if (process.env.SHOT) await page.locator('#screen-process .panel').screenshot({ path: process.env.SHOT });
  console.log('not-writing-page: a maths page is refused with its own screen asking for four lines of English, shows no report, reported as not_writing_page');
} finally {
  if (browser) await browser.close();
  server.kill();
}
