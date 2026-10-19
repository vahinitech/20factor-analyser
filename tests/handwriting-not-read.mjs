/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// A page asked for as Telugu that the reader returned as mostly Latin
// letters is refused with error_code "handwriting_not_read"
// (recognizer.telugu_not_read). The real analyser page, its recognition
// server stubbed with a compact refusal:
// - the answer says the writing could not be read and that handwritten
//   Telugu is not read yet, not "server not reachable";
// - no report is shown, and the free check is said not to be used up;
// - the outcome is reported as handwriting_not_read.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const version = readdirSync('backend/catalogs').find((f) => f.endsWith('.json')).replace(/\.json$/, '');
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4192', '-c-1', '--silent']);
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4192/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
  await page.route('**/api/v2/catalog/**', (r) => r.fulfill({ contentType: 'application/json', body: readFileSync(`backend/catalogs/${version}.json`) }));
  await page.route('**/api/v2/reports?**', (r) => r.fulfill({ json: { schema_version: '2.1', format: 'compact', catalog_version: version, ok: false, error: { code: 'handwriting_not_read' } } }));
  await page.goto('http://127.0.0.1:4192/frontend/analyser.html', { waitUntil: 'networkidle' });
  await page.evaluate(() => { window.outcomes = []; window.VahiniInsights = { check: (o) => window.outcomes.push(o) }; });

  const answer = await page.evaluate(() => VahiniOCR.serverPythonReport(new Blob(['x']), ''));
  assert.equal(answer.ok, false);
  assert.equal(answer.error_code, 'handwriting_not_read', 'the compact refusal keeps its code');

  await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
  await page.click('#go-process');
  await page.waitForSelector('text=We could not read the writing on this page', { timeout: 20000 });
  const panel = await page.locator('#screen-process .panel').innerText();
  assert.match(panel, /cannot read handwritten Telugu yet/);
  assert.match(panel, /did not use up one of your free checks/);
  assert.doesNotMatch(panel, /not reachable|busy/i, 'not blamed on load or a dead server');
  assert.equal(await page.locator('#screen-report.on').count(), 0, 'no report is shown');
  assert.deepEqual(await page.evaluate(() => window.outcomes), ['handwriting_not_read'], 'reported as handwriting_not_read');
  if (process.env.SHOT) await page.locator('#screen-process .panel').screenshot({ path: process.env.SHOT });
  console.log('handwriting-not-read: an unread Telugu page is refused with its own screen, shows no report, reported as handwriting_not_read');
} finally {
  if (browser) await browser.close();
  server.kill();
}
