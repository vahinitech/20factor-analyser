/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// Error screens for answers about the file or the key, and the optional
// pictures a host page can give each notice (window.VAHINI_NOTICE_ART).
// The real analyser page, its recognition server stubbed:
// - 413, 422, a wrong key (401) and the key service down (503) each get
//   their own screen and outcome, never "server not reachable";
// - without VAHINI_NOTICE_ART the screens keep their icon and add no image;
// - with it, the mapped picture replaces the icon (alt="", decorative), and
//   the upload notice and status line show theirs;
// - a map entry that is not a same-site path is ignored;
// - the small/blurry photo warning is drawn on top of the photo preview
//   (it used to sit behind it, unseen).
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const PORT = 4192;
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', String(PORT), '-c-1', '--silent']);
const ART = {
  too_large: '/art/size.webp', invalid_file: '/art/puzzled.webp', key_problem: '/art/key.webp',
  account_unavailable: '/art/wait.webp', unreadable: '/art/gentle.webp', busy: 'https://example.com/x.webp',
};
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', 'base64');
let browser;

async function open(report, { art = true, me } = {}) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.route('**/art/*', (r) => r.fulfill({ body: PNG, contentType: 'image/png' }));
  await page.route('**/api/v2/me', (r) => (me ? me(r) : r.fulfill({ json: { access: { tier: 'free' } } })));
  await page.route('**/api/v2/reports?**', report);
  await page.goto(`http://127.0.0.1:${PORT}/frontend/analyser.html`, { waitUntil: 'networkidle' });
  await page.evaluate((map) => {
    window.outcomes = []; window.VahiniInsights = { check: (o) => window.outcomes.push(o) };
    if (map) window.VAHINI_NOTICE_ART = map;
  }, art ? ART : null);
  return page;
}

async function run(page) {
  await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
  await page.click('#go-process');
  await page.waitForSelector('.reject-card', { timeout: 20000 });
  return {
    text: await page.locator('#screen-process .panel').innerText(),
    art: await page.locator('.reject-card img.reject-art').evaluateAll((i) => i.map((x) => [x.getAttribute('src'), x.getAttribute('alt')])),
    icon: await page.locator('.reject-card .reject-ico').count(),
    outcomes: await page.evaluate(() => window.outcomes),
  };
}

try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch(`http://127.0.0.1:${PORT}/`)).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();

  const cases = [
    ['too_large', (r) => r.fulfill({ status: 413, json: { detail: 'Upload exceeds 5 MiB' } }), /This photo is too large to check/, '/art/size.webp'],
    ['invalid_file', (r) => r.fulfill({ status: 422, json: { detail: 'Upload a valid image or PDF.' } }), /This file could not be opened/, '/art/puzzled.webp'],
    ['key_problem', (r) => r.fulfill({ status: 401, json: { detail: 'Invalid API credential' } }), /Your access key could not be checked/, '/art/key.webp'],
  ];
  for (const [code, report, heading, art] of cases) {
    const page = await open(report);
    const got = await run(page);
    assert.match(got.text, heading, code);
    assert.doesNotMatch(got.text, /not reachable/, `${code} is not blamed on the server`);
    assert.deepEqual(got.art, [[art, '']], `${code} shows its picture, decorative`);
    assert.equal(got.icon, 0, `${code}: the picture replaces the icon`);
    assert.deepEqual(got.outcomes, [code]);
    await page.close();
  }

  // A connected key whose check fails: 401 is the key, 503 the key service.
  for (const [status, code, heading] of [[401, 'key_problem', /Your access key could not be checked/], [503, 'account_unavailable', /Access keys cannot be checked right now/]]) {
    let calls = 0;
    const page = await open((r) => r.fulfill({ json: { ok: true } }), {
      me: (r) => (calls++ === 0 ? r.fulfill({ json: { access: { tier: 'pro' } } }) : r.fulfill({ status, json: { detail: 'x' } })),
    });
    await page.evaluate(() => VahiniAccount.connect('vh_test_key'));
    const got = await run(page);
    assert.match(got.text, heading, `key check ${status}`);
    assert.deepEqual(got.outcomes, [code]);
    await page.close();
  }

  // The scan cap stays "busy", and a map entry off this site is ignored.
  let page = await open((r) => r.fulfill({ status: 503, headers: { 'Retry-After': '20' }, json: { detail: 'busy' } }));
  let got = await run(page);
  assert.match(got.text, /The analyser is busy right now/);
  assert.deepEqual(got.art, [], 'an off-site picture is not used');
  assert.equal(got.icon, 1, 'the icon stays');
  await page.close();

  // Without a map nothing changes.
  page = await open((r) => r.fulfill({ status: 413, json: { detail: 'x' } }), { art: false });
  got = await run(page);
  assert.deepEqual(got.art, []);
  assert.equal(got.icon, 1);
  await page.close();

  // Upload notice with its picture, text intact.
  page = await open((r) => r.fulfill({ json: { ok: true } }));
  await page.setInputFiles('#file-input', { name: 'page.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('not an image') });
  await page.waitForSelector('#dz-notice:not([hidden])');
  assert.deepEqual(await page.locator('#dz-notice img.notice-art').evaluateAll((i) => i.map((x) => x.getAttribute('src'))), ['/art/gentle.webp']);
  assert.match(await page.locator('#dz-notice').innerText(), /This file could not be opened as a photo/);
  assert.deepEqual(await page.evaluate(() => window.outcomes), ['unreadable']);
  await page.close();

  // A small photo: the warning is on top of the preview, with its picture.
  page = await open((r) => r.fulfill({ json: { ok: true } }), { art: false });
  await page.evaluate(() => { window.VAHINI_NOTICE_ART = { photo_warning: '/art/gentle.webp' }; });
  const small = await page.evaluate(() => new Promise((res) => {
    const c = document.createElement('canvas'); c.width = 300; c.height = 200;
    const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, 300, 200); g.fillStyle = '#000';
    for (let y = 30; y < 200; y += 40) g.fillRect(20, y, 260, 2);
    c.toBlob((b) => b.arrayBuffer().then((a) => res(Array.from(new Uint8Array(a)))), 'image/png');
  }));
  await page.setInputFiles('#file-input', { name: 'small.png', mimeType: 'image/png', buffer: Buffer.from(small) });
  await page.waitForSelector('#dz-status.has-art img.status-art');
  const onTop = await page.evaluate(() => {
    const s = document.querySelector('#dz-status'); const r = s.getBoundingClientRect();
    return s.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
  });
  assert.ok(onTop, 'the photo warning is not hidden behind the preview');
  assert.match(await page.locator('#dz-status').innerText(), /This photo is small/);
  await page.close();

  console.log('notice-art: file and key errors have their own screens; pictures replace icons only from a same-site map');
} finally {
  if (browser) await browser.close();
  server.kill();
}
