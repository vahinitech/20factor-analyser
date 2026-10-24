/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// Pihu's guide on the check page (owner, 2026-10-25), on the real page:
// - a first visit opens it by itself: "I am", the photo button (Take a
//   photo on a phone, Choose a photo on a computer), "Try a sample",
//   "Analyse", each lit with the note beside it, Next and then Done;
// - once per browser: Done, Skip, Escape or a chosen photo ends it for good,
//   and "Show me around" brings it back;
// - Pihu is the host's cut layers when the host maps them, the whole bird
//   otherwise; the wings beat only while flying, and with motion off Pihu
//   appears beside each button without flying;
// - nothing is sent.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4231', '-c-1', '--silent']);
const URL = 'http://127.0.0.1:4231/frontend/analyser.html';
const ART = { body: '/frontend/assets/samples/handwriting-sample.jpg', wingBack: '/frontend/assets/samples/handwriting-sample.jpg', wingFront: '/frontend/assets/samples/handwriting-sample.jpg' };
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4231/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const open = async (viewport, { motion = 'no-preference', art = ART } = {}) => {
    const ctx = await browser.newContext({ viewport, reducedMotion: motion });
    await ctx.addInitScript((art) => { if (art) window.VAHINI_GUIDE_ART = art; window.VAHINI_REPORT_ART = { tip: '/frontend/assets/samples/handwriting-sample.jpg' }; }, art);
    const page = await ctx.newPage();
    const sent = [];
    page.on('request', (r) => { if (r.method() !== 'GET') sent.push(r.url()); });
    await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
    await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
    await page.goto(URL, { waitUntil: 'networkidle' });
    return { page, sent, ctx };
  };
  const guide = (page) => page.locator('#pihu-guide.on .pg-say');
  const lit = async (page, sel) => {
    await page.waitForTimeout(500);
    const [ring, el] = [await page.locator('.pg-ring').boundingBox(), await page.locator(sel).boundingBox()];
    return ring.x <= el.x && ring.y <= el.y && ring.x + ring.width >= el.x + el.width && ring.y + ring.height >= el.y + el.height;
  };

  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }]) {
    const { page, sent, ctx } = await open(viewport);
    await guide(page).waitFor({ timeout: 3000 });
    const photo = viewport.width < 500 ? '#take-photo' : '#choose-photo';
    const stops = [['#who-bar', 'Hello! I am Pihu.'], [photo, 'Add one page'], ['#try-sample', 'No page handy?'], ['#go-process', 'Then press here']];
    for (let i = 0; i < stops.length; i++) {
      const [sel, title] = stops[i];
      assert.equal(await page.locator('.pg-n').innerText(), `${i + 1} of 4`);
      assert.equal(await page.locator('#pg-title').innerText(), title);
      assert.ok(await lit(page, sel), `${viewport.width}px: ${sel} is lit`);
      const say = await page.locator('.pg-say').boundingBox();
      assert.ok(say.x >= 0 && say.x + say.width <= viewport.width, `${viewport.width}px: the note fits the screen`);
      assert.equal(await page.evaluate(() => document.activeElement.className), 'pg-next', 'the keyboard is on Next');
      assert.equal(await page.locator('.pg-next').innerText(), i === 3 ? 'Done' : 'Next');
      await page.click('.pg-next');
    }
    assert.equal(await page.locator('#pihu-guide').count(), 0, 'Done closes it');
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    assert.equal(await page.locator('#pihu-guide').count(), 0, 'once per browser');
    await page.click('#guide-again');
    await guide(page).waitFor();
    assert.equal(await page.locator('.pg-n').innerText(), '1 of 4', '"Show me around" brings it back');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#pihu-guide').count(), 0, 'Escape closes it');
    assert.deepEqual(sent, [], 'nothing is sent');
    await ctx.close();
  }

  // Skip, and a chosen photo, end it for good.
  {
    const { page, ctx } = await open({ width: 1280, height: 900 });
    await guide(page).waitFor({ timeout: 3000 });
    await page.click('.pg-skip');
    assert.equal(await page.locator('#pihu-guide').count(), 0);
    assert.equal(await page.evaluate(() => localStorage.getItem('vahini_guide_check')), '1', 'Skip is remembered');
    await page.click('#guide-again');
    await guide(page).waitFor();
    await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
    await page.waitForTimeout(300);
    assert.equal(await page.locator('#pihu-guide').count(), 0, 'a chosen photo ends it');
    await ctx.close();
  }

  // Pihu: the cut layers, beating only in flight; the whole bird without them.
  {
    const { page, ctx } = await open({ width: 1280, height: 900 });
    await guide(page).waitFor({ timeout: 3000 });
    assert.equal(await page.locator('.pg-bird--layers img').count(), 3, 'the three layers');
    await page.waitForTimeout(1500);
    assert.equal(await page.locator('.pg-bird.is-flying').count(), 0, 'perched: no beating');
    await page.click('.pg-next');
    await page.waitForSelector('.pg-bird.is-flying', { timeout: 1500 });
    await page.waitForSelector('.pg-bird:not(.is-flying)', { timeout: 3000 });
    const [bird, ring] = [await page.locator('.pg-bird').boundingBox(), await page.locator('.pg-ring').boundingBox()];
    assert.ok(Math.abs(bird.y + bird.height * 0.8 - (ring.y + 8)) < 6 && bird.x > ring.x, 'Pihu perches on the lit button');
    await ctx.close();
  }
  {
    const { page, ctx } = await open({ width: 1280, height: 900 }, { art: null });
    await guide(page).waitFor({ timeout: 3000 });
    assert.equal(await page.locator('.pg-bird img').count(), 1, 'the whole bird without the layers');
    await ctx.close();
  }
  {
    const { page, ctx } = await open({ width: 1280, height: 900 }, { motion: 'reduce' });
    await guide(page).waitFor({ timeout: 3000 });
    await page.click('.pg-next');
    await page.waitForTimeout(100);
    assert.equal(await page.locator('.pg-bird.is-flying').count(), 0, 'no flying with motion off');
    assert.ok(await lit(page, '#choose-photo'), 'the next button is lit at once');
    await ctx.close();
  }
  console.log('pihu-guide: four stops at 390 and 1440 px, once per browser, Show me around, Skip, Escape; layers, no flight with motion off');
} finally {
  if (browser) await browser.close();
  server.kill();
}
