/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// The check page's "Privacy and security" card (owner, 2026-10-29), in a
// browser:
// - its four lines and the link to the full statement are in the page's
//   HTML, so they are there without a script and for crawlers;
// - on a computer it opens on hover and closes when the pointer leaves, a
//   click keeps it open, and Escape closes it with focus back on the link;
// - the keyboard opens it with Enter;
// - on a phone a tap opens it in place, inside the screen, and a tap
//   elsewhere closes it.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import { chromium } from 'playwright';

const LINES = [
  'We check your photo. We don’t save it.',
  'Nothing we keep from your check has your name on it.',
  'Pages are saved only if you tick “Keep my pages”. Only you can open them.',
  'We never sell your data.',
];
const html = fs.readFileSync('frontend/analyser.html', 'utf8');
const card = html.match(/<details class="prv" id="prv">[\s\S]*?<\/details>/)?.[0] || '';
for (const line of LINES) assert.ok(card.includes(line), `the card says: ${line}`);
assert.match(card, /<summary>[\s\S]*Privacy and security<\/summary>/, 'the card opens from "Privacy and security"');
assert.match(card, /We follow India’s DPDP Act, 2023\. <a href="\/privacy\.html">Full privacy statement<\/a>/, 'the card ends with the full statement');

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4198', '-c-1', '--silent']);
const URL = 'http://127.0.0.1:4198/frontend/analyser.html';
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4198/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const open = async (viewport, touch = false) => {
    const context = await browser.newContext({ viewport, isMobile: touch, hasTouch: touch });
    // Pihu's first-visit tour would cover the page.
    await context.addInitScript(() => { try { localStorage.setItem('vahini_guide_check', '1'); } catch {} });
    await context.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
    await context.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
    const page = await context.newPage();
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.locator('#prv > summary').scrollIntoViewIfNeeded();
    return page;
  };
  const isOpen = (page) => page.evaluate(() => document.getElementById('prv').open);
  const cardBox = (page) => page.locator('.prv__card').boundingBox();

  {
    const page = await open({ width: 1440, height: 900 });
    assert.equal(await isOpen(page), false, 'closed at first');
    // The link near the top of the screen, then at its very bottom: the
    // card opens below, then above, and stays on screen both times.
    for (const at of [0.25, 0.95]) {
      await page.evaluate((f) => { const l = document.querySelector('#prv > summary'); scrollBy(0, l.getBoundingClientRect().top - innerHeight * f); }, at);
      await page.hover('#prv > summary');
      await page.waitForTimeout(100);
      assert.equal(await isOpen(page), true, 'hover opens it');
      const box = await cardBox(page);
      assert.ok(box.x >= 0 && box.x + box.width <= 1440 && box.y >= 0 && box.y + box.height <= 900, `the card is on screen with the link at ${at * 100}% down: ${JSON.stringify(box)}`);
      await page.mouse.move(1400, 20);
      await page.waitForTimeout(400);
    }
    await page.evaluate(() => { const l = document.querySelector('#prv > summary'); scrollBy(0, l.getBoundingClientRect().top - innerHeight * 0.25); });
    await page.hover('#prv > summary');
    for (const line of LINES) assert.ok(await page.getByText(line, { exact: true }).isVisible(), `shown: ${line}`);
    await page.mouse.move(1400, 20);
    await page.waitForTimeout(400);
    assert.equal(await isOpen(page), false, 'leaving closes it');
    await page.hover('#prv > summary');
    await page.click('#prv > summary');
    await page.mouse.move(1400, 20);
    await page.waitForTimeout(400);
    assert.equal(await isOpen(page), true, 'a click keeps it open');
    await page.keyboard.press('Escape');
    assert.equal(await isOpen(page), false, 'Escape closes it');
    await page.focus('#prv > summary');
    await page.keyboard.press('Enter');
    assert.equal(await isOpen(page), true, 'Enter opens it');
    await page.keyboard.press('Escape');
    assert.equal(await isOpen(page), false, 'Escape closes it again');
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#prv > summary')), true, 'focus is back on the link');
    await page.context().close();
  }
  {
    // A narrow window with a mouse: the card opens in place there, so hover
    // leaves it shut and the page does not jump under the pointer.
    const page = await open({ width: 390, height: 844 });
    const before = await page.locator('#go-process').boundingBox();
    await page.hover('#prv > summary');
    await page.waitForTimeout(100);
    assert.equal(await isOpen(page), false, 'hover does not open it in the phone layout');
    assert.deepEqual(await page.locator('#go-process').boundingBox(), before, 'nothing moves');
    await page.click('#prv > summary');
    assert.equal(await isOpen(page), true, 'a click opens it there');
    await page.context().close();
  }
  {
    const page = await open({ width: 390, height: 844 }, true);
    await page.tap('#prv > summary');
    assert.equal(await isOpen(page), true, 'a tap opens it');
    const box = await cardBox(page);
    assert.ok(box.x >= 0 && box.x + box.width <= 390, `the card fits the phone: ${JSON.stringify(box)}`);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no sideways scroll');
    await page.tap('.check-heading h1');
    assert.equal(await isOpen(page), false, 'a tap elsewhere closes it');
    await page.context().close();
  }
  console.log('privacy-card: ok');
} finally {
  if (browser) await browser.close();
  server.kill();
}
