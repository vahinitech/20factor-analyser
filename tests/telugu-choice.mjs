/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// "The page is written in" on the check page (#172). Under lang=auto the
// English reader reads a Telugu page first and the server scores what it
// invented, so a family that knows the page is Telugu says so. The real
// analyser page, its recognition server stubbed:
// - English is picked to start with, and the request sends lang=auto, as before;
// - picking Telugu shows the "not scored yet" note before Run, and the
//   request sends lang=te;
// - the refusal asks for four lines in English;
// - the sample page is English: loading it picks English and turns Telugu off.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const version = readdirSync('backend/catalogs').find((f) => f.endsWith('.json')).replace(/\.json$/, '');
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4193', '-c-1', '--silent']);
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4193/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const langs = [];
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
  await page.route('**/api/v2/catalog/**', (r) => r.fulfill({ contentType: 'application/json', body: readFileSync(`backend/catalogs/${version}.json`) }));
  await page.route('**/api/v2/reports?**', (r) => {
    const body = (r.request().postDataBuffer() || Buffer.alloc(0)).toString('latin1');
    const m = body.match(/name="lang"\r\n\r\n([^\r]*)\r\n/);
    langs.push(m ? m[1] : null);
    r.fulfill({ json: { schema_version: '2.1', format: 'compact', catalog_version: version, ok: false, error: { code: 'handwriting_not_read' } } });
  });
  await page.goto('http://127.0.0.1:4193/frontend/analyser.html', { waitUntil: 'networkidle' });

  assert.equal(await page.locator('input[name="write-lang"][value="en"]').isChecked(), true, 'English to start with');
  assert.equal(await page.locator('#write-lang-note').isVisible(), false, 'no note for English');
  assert.equal(await page.evaluate(() => window.VAHINI_OCR_LANG), 'auto', 'English keeps lang=auto');

  await page.locator('#write-lang label', { hasText: 'Telugu' }).click();
  assert.equal(await page.evaluate(() => window.VAHINI_OCR_LANG), 'te');
  const note = await page.locator('#write-lang-note').innerText();
  assert.match(note, /not scored yet/, 'said before Run');
  assert.match(note, /four lines in English/);

  await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
  if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT, fullPage: false });
  await page.click('#go-process');
  await page.waitForSelector('text=We could not read the writing on this page', { timeout: 20000 });
  assert.deepEqual(langs, ['te'], 'the request sends lang=te');
  const panel = await page.locator('#screen-process .panel').innerText();
  assert.match(panel, /Write four lines in English/);

  await page.goto('http://127.0.0.1:4193/frontend/analyser.html', { waitUntil: 'networkidle' });
  await page.locator('#write-lang label', { hasText: 'Telugu' }).click();
  await page.click('#try-sample');
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
  assert.equal(await page.locator('input[name="write-lang"][value="en"]').isChecked(), true, 'the sample is English');
  assert.equal(await page.locator('input[name="write-lang"][value="te"]').isDisabled(), true, 'Telugu is off for the sample');
  assert.equal(await page.evaluate(() => window.VAHINI_OCR_LANG), 'auto');
  assert.equal(await page.locator('#write-lang-note').isVisible(), false);
  console.log('telugu-choice: English sends auto; Telugu shows its note before Run and sends te; the sample is checked as English');
} finally {
  if (browser) await browser.close();
  server.kill();
}
