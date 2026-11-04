/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// "Letter style taught at school" on the check page (#346, #350). The real
// analyser page, its recognition server stubbed:
// - the names are in the page's HTML, written from the registry, so
//   crawlers read them; each joined style is drawn in its own Playwrite
//   face, which loads from the page's own server;
// - Not sure is picked to start with and sends no letter_style;
// - picking a style sends its id; More styles opens on a click;
// - analyser.html?style=french opens with French picked, More styles open;
// - Telugu hides the picker and sends no style.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const version = readdirSync('backend/catalogs').find((f) => f.endsWith('.json')).replace(/\.json$/, '');
const registry = JSON.parse(readFileSync('backend/styles/letter_styles.json', 'utf8')).styles;
const html = readFileSync('frontend/analyser.html', 'utf8');
for (const s of registry) assert.ok(html.includes(`value="${s.id}"`) && html.includes(s.label), `${s.id} is in the page's HTML`);

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4194', '-c-1', '--silent']);
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4194/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const sent = [];
  const foreign = [];
  page.on('request', (r) => { const u = new URL(r.url()); if (/font|woff/.test(u.pathname) && u.hostname !== '127.0.0.1') foreign.push(r.url()); });
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
  await page.route('**/api/v2/catalog/**', (r) => r.fulfill({ contentType: 'application/json', body: readFileSync(`backend/catalogs/${version}.json`) }));
  await page.route('**/api/v2/reports?**', (r) => {
    const body = (r.request().postDataBuffer() || Buffer.alloc(0)).toString('latin1');
    const m = body.match(/name="letter_style"\r\n\r\n([^\r]*)\r\n/);
    sent.push(m ? m[1] : null);
    r.fulfill({ json: { schema_version: '2.1', format: 'compact', catalog_version: version, ok: false, error: { code: 'handwriting_not_read' } } });
  });
  const run = async () => {
    await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
    await page.check('input[name="check-who"][value="parent"]'); await page.click('#go-process');
    await page.waitForSelector('text=We could not read the writing on this page', { timeout: 20000 });
  };
  const open = async (query = '') => page.goto(`http://127.0.0.1:4194/frontend/analyser.html${query}`, { waitUntil: 'networkidle' });

  await open();
  assert.equal(await page.locator('input[name="letter-style"][value="unsure"]').isChecked(), true, 'Not sure to start with');
  assert.equal(await page.locator('#letter-style').isVisible(), true);
  const looped = page.locator('.ls-opt', { has: page.locator('input[value="looped"]') }).locator('.ls-name');
  assert.match(await looped.evaluate((e) => getComputedStyle(e).fontFamily), /Playwrite US Trad/);
  await page.evaluate(() => document.fonts.ready);
  assert.equal(await page.evaluate(() => document.fonts.check("19px 'Playwrite US Trad'", 'Looped cursive')), true, 'the face loaded');
  assert.equal(await page.locator('input[name="letter-style"][value="french"]').isVisible(), false, 'French waits under More styles');
  await run();
  assert.deepEqual(sent, [null], 'Not sure sends no style');

  await open();
  await page.locator('.ls-opt', { hasText: 'Looped cursive' }).click();
  await run();
  assert.deepEqual(sent.slice(-1), ['looped'], 'a picked style sends its id');

  await open();
  await page.locator('.ls-more summary').click();
  await page.locator('.ls-opt', { hasText: 'Schulausgangsschrift' }).click();
  await run();
  assert.deepEqual(sent.slice(-1), ['german-sas'], 'More styles opens and sends');

  await open('?style=french');
  assert.equal(await page.locator('input[name="letter-style"][value="french"]').isChecked(), true, 'a link picks French');
  assert.equal(await page.locator('.ls-more').getAttribute('open'), '', 'and opens More styles');
  await open('?style=<b>');
  assert.equal(await page.locator('input[name="letter-style"][value="unsure"]').isChecked(), true, 'a bad link changes nothing');

  await open();
  await page.locator('.ls-opt', { hasText: 'Looped cursive' }).click();
  await page.locator('#write-lang label', { hasText: 'Telugu' }).click();
  assert.equal(await page.locator('#letter-style').isVisible(), false, 'no picker for Telugu');
  await run();
  assert.deepEqual(sent.slice(-1), [null], 'Telugu sends no style');
  assert.deepEqual(foreign, [], 'no font from another server');
  console.log('letter-style-choice: names in the HTML, own faces; Not sure sends nothing, a pick sends its id, links pick, Telugu hides it');
} finally {
  if (browser) await browser.close();
  server.kill();
}
