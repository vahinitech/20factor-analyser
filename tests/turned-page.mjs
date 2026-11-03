/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// A photo taken sideways or upside down (#297). The server reads the page
// upright and says how far it turned it ("turned", degrees clockwise), or
// refuses it with error_code "turned_page" when it cannot tell which way
// up the page is. The real analyser page, its recognition server stubbed:
// - turned 90, 180 or 270: "From your page" is drawn from a copy of the
//   photo turned the same way (a mark in the photo's top left corner ends
//   up where the turn puts it), and the report is otherwise unchanged;
// - no turn, or a value that is not a quarter turn: the photo as it is;
// - turned_page: its own screen asking to turn the photo, no report, the
//   free check not used up, reported as turned_page.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const version = readdirSync('backend/catalogs').find((f) => f.endsWith('.json')).replace(/\.json$/, '');
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4195', '-c-1', '--silent']);
let browser;
const compact = (extra) => ({ schema_version: '2.1', format: 'compact', catalog_version: version, ...extra });
const REPORT = { ok: true, access: { tier: 'free' }, summary: { score: 60 }, factors: [1, 5, 7, 8, 18].map((n) => ({ n, s: 6, st: 'e' })) };

async function openPage(answer){
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
  await page.route('**/api/v2/catalog/**', (r) => r.fulfill({ contentType: 'application/json', body: readFileSync(`backend/catalogs/${version}.json`) }));
  await page.route('**/api/v2/reports/renew', (r) => r.fulfill({ json: { renewed: 0 } }));
  await page.route('**/api/v2/reports?**', (r) => r.fulfill({ json: compact(answer) }));
  await page.goto('http://127.0.0.1:4195/frontend/analyser.html', { waitUntil: 'networkidle' });
  await page.evaluate(() => { window.outcomes = []; window.VahiniInsights = { check: (o) => window.outcomes.push(o) }; });
  return page;
}

// A portrait photo, 600 x 800, white with a red block in its top left
// corner: where the block lands shows which way the copy was turned.
async function markedPhoto(page){
  const b64 = await page.evaluate(() => {
    const c = document.createElement('canvas'); c.width = 600; c.height = 800;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 600, 800);
    ctx.fillStyle = '#000'; for (let y = 200; y < 760; y += 40) ctx.fillRect(60, y, 480, 4);
    ctx.fillStyle = '#f00'; ctx.fillRect(0, 0, 150, 150);
    return c.toDataURL('image/png').split(',')[1];
  });
  return { name: 'page.png', mimeType: 'image/png', buffer: Buffer.from(b64, 'base64') };
}

// The report's "From your page" picture: its size and which corner is red.
async function shownPhoto(page){
  return page.evaluate(async () => {
    const el = document.querySelector('#report-host .sn-zoom img, #report-host .sn-zoom image');
    const src = el && (el.getAttribute('src') || el.getAttribute('href'));
    if (!src) return null;
    const img = new Image(); img.src = src; await img.decode();
    const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
    const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
    const red = (x, y) => { const d = ctx.getImageData(x, y, 1, 1).data; return d[0] > 200 && d[1] < 80 && d[2] < 80; };
    const w = c.width - 5, h = c.height - 5;
    const corner = [['top left', 5, 5], ['top right', w, 5], ['bottom right', w, h], ['bottom left', 5, h]].filter(([, x, y]) => red(x, y)).map(([n]) => n);
    return { w: img.naturalWidth, h: img.naturalHeight, corner };
  });
}

async function run(answer){
  const page = await openPage(answer);
  await page.setInputFiles('#file-input', await markedPhoto(page));
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
  await page.check('input[name="check-who"][value="parent"]'); await page.click('#go-process');
  return page;
}

try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4195/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();

  // The compact decoder keeps a quarter turn and nothing else.
  const probe = await openPage({ ...REPORT, turned: 90 });
  assert.equal((await probe.evaluate(() => VahiniOCR.serverPythonReport(new Blob(['x']), ''))).turned, 90);
  await probe.close();
  const junk = await openPage({ ...REPORT, turned: 45 });
  assert.equal((await junk.evaluate(() => VahiniOCR.serverPythonReport(new Blob(['x']), ''))).turned, 0, 'only a quarter turn is used');
  await junk.close();

  const want = {
    none: { landscape: false, corner: 'top left' },
    90: { landscape: true, corner: 'top right' },
    180: { landscape: false, corner: 'bottom right' },
    270: { landscape: true, corner: 'bottom left' },
  };
  for (const [turn, expect] of Object.entries(want)){
    const page = await run(turn === 'none' ? REPORT : { ...REPORT, turned: Number(turn) });
    await page.waitForSelector('#screen-report.on', { timeout: 20000 });
    const shown = await shownPhoto(page);
    assert.ok(shown, `turned ${turn}: the report shows the photo`);
    assert.equal(shown.w > shown.h, expect.landscape, `turned ${turn}: ${JSON.stringify(shown)}`);
    assert.deepEqual(shown.corner, [expect.corner], `turned ${turn}: the mark is ${expect.corner}`);
    assert.deepEqual(await page.evaluate(() => window.outcomes), ['report'], `turned ${turn}: reported as a report`);
    if (process.env.SHOT && turn === '90') await page.locator('#report-host').screenshot({ path: process.env.SHOT });
    await page.close();
  }

  const page = await run({ ok: false, error: { code: 'turned_page' } });
  await page.waitForSelector('text=This photo is on its side', { timeout: 20000 });
  const panel = await page.locator('#screen-process .panel').innerText();
  assert.match(panel, /lines of writing run up and down/);
  assert.match(panel, /Turn the photo so the lines of writing run across/);
  assert.match(panel, /did not use up one of your free checks/);
  assert.doesNotMatch(panel, /not reachable|busy/i, 'not blamed on load or a dead server');
  assert.equal(await page.locator('#screen-report.on').count(), 0, 'no report is shown');
  assert.deepEqual(await page.evaluate(() => window.outcomes), ['turned_page'], 'reported as turned_page');
  if (process.env.SHOT_REFUSAL) await page.locator('#screen-process .panel').screenshot({ path: process.env.SHOT_REFUSAL });
  console.log('turned-page: a turned photo is drawn turned the way the server read it, any quarter turn; a page the server could not set upright gets its own screen, no report, reported as turned_page');
} finally {
  if (browser) await browser.close();
  server.kill();
}
