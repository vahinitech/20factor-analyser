/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// A check that gets no answer (owner, 2026-10-23). The real analyser page,
// its recognition server stubbed:
// - a 502 while the server restarts shows "starting again" and waits for
//   the health check, then "ready" with the same photo offered on a tap;
// - the same photo dropped a second time is "we could not check this
//   photo", with no way to send it again, and "Ask our team";
// - "Choose another photo" goes back to the upload box;
// - a new photo after that starts again with its own wait;
// - outcomes: server_restarting, server_back, check_failed_twice.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4193', '-c-1', '--silent']);
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4193/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  let healthy = true, reports = 0;
  await page.route('**/health', (r) => (healthy ? r.fulfill({ json: { ok: true } }) : r.fulfill({ status: 502, body: '<h1>502 Bad Gateway</h1>' })));
  await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
  await page.route('**/api/v2/reports?**', (r) => {
    reports++;
    healthy = false;   // the analyser died mid-scan and is starting again
    if (reports === 1) return r.fulfill({ status: 502, contentType: 'text/html', body: '<h1>502 Bad Gateway</h1>' });
    return r.abort('connectionreset');
  });
  await page.goto('http://127.0.0.1:4193/frontend/analyser.html', { waitUntil: 'networkidle' });
  await page.evaluate(() => { window.outcomes = []; window.VahiniInsights = { check: (o) => window.outcomes.push(o) }; });
  const panel = () => page.locator('#screen-process .panel').innerText();
  const upload = async () => {
    await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#dz-preview')).display === 'block');
    await page.waitForFunction(() => !document.querySelector('#go-process').disabled);
    await page.check('input[name="check-who"][value="parent"]'); await page.click('#go-process');
  };

  await upload();
  await page.waitForSelector('text=The checker is starting again', { timeout: 20000 });
  const sent = reports;   // one check (a local page also tries 127.0.0.1:8080)
  assert.match(await panel(), /Your photo is still here on your phone/);
  assert.equal(await page.locator('.drop-wait__bar').count(), 1, 'a waiting bar');
  assert.doesNotMatch(await panel(), /not reachable|Check this photo again/);

  healthy = true;
  await page.waitForSelector('text=The checker is ready', { timeout: 10000 });
  assert.match(await panel(), /does not use up a free check/);
  assert.equal(reports, sent, 'the photo is not sent again by itself');

  await page.click('text=Check this photo again');
  await page.waitForSelector('text=We could not check this photo', { timeout: 20000 });
  assert.ok(reports > sent, 'sent again on the tap');
  const twice = await panel();
  assert.match(twice, /stopped the checker twice/);
  assert.match(twice, /The photo was not saved/);
  assert.equal(await page.locator('text=Check this photo again').count(), 0, 'not offered a third time');
  assert.equal(await page.locator('#screen-process a.btn', { hasText: 'Ask our team' }).getAttribute('href'), '/reach.html?topic=handwriting');
  assert.deepEqual(await page.evaluate(() => window.outcomes), ['server_restarting', 'server_back', 'check_failed_twice']);

  healthy = true;
  await page.click('#screen-process button:has-text("Choose another photo")');
  assert.equal(await page.locator('#screen-upload.on').count(), 1, 'back to the upload box');

  // A new photo starts again: its first drop waits, it is not "twice".
  await upload();
  await page.waitForSelector('text=The checker is starting again', { timeout: 20000 });
  assert.doesNotMatch(await panel(), /could not check this photo/);
  console.log('check-dropped: waits for a restarting server, offers the photo once more on a tap, refuses it after a second drop; a new photo starts again');
} finally {
  if (browser) await browser.close();
  server.kill();
}
