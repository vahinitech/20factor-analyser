/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// The check page's "What's new" line in a browser (owner, 2026-10-24), on
// the page as the image build writes it (build_bundle.py's block):
// - one line under the heading, above the upload, on a phone and a desktop,
//   never wider than the screen;
// - the newest change first, with "1 of 10", then the next every 5 seconds
//   on the same line, back to the newest after the last (owner,
//   2026-10-25);
// - it waits while the pointer is on it or the list is open, and does not
//   move for people who turn off motion;
// - a tap opens all of them.
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import { chromium } from 'playwright';

const { items } = JSON.parse(fs.readFileSync('frontend/whats-new.json', 'utf8'));
const block = execFileSync('python3', ['frontend/build_bundle.py', '--whats-new'], { encoding: 'utf8' });
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4197', '-c-1', '--silent']);
const URL = 'http://127.0.0.1:4197/frontend/analyser.html';
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4197/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const open = async (viewport, { motion = 'no-preference' } = {}) => {
    const context = await browser.newContext({ viewport, reducedMotion: motion });
    await context.route('**/frontend/analyser.html', async (route) => {
      const res = await route.fetch();
      const body = (await res.text()).replace(/(<!-- whats-new:begin[^>]*-->)[\s\S]*?(<!-- whats-new:end -->)/, (_, a, b) => a + block + b);
      await route.fulfill({ response: res, body });
    });
    await context.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
    await context.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
    const page = await context.newPage();
    await page.clock.install();
    await page.goto(URL, { waitUntil: 'networkidle' });
    return page;
  };
  const shown = (page) => page.locator('#whats-new .wn-line span').innerText();
  const count = (page) => page.locator('#whats-new .wn-count').innerText();

  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }]) {
    const page = await open(viewport);
    const box = await page.locator('#whats-new summary').boundingBox();
    const upload = await page.locator('#start-check').boundingBox();
    const heading = await page.locator('.check-heading h1').boundingBox();
    assert.ok(box.height <= 36, `${viewport.width}px: one line, ${box.height}px tall`);
    assert.ok(box.x >= 0 && box.x + box.width <= viewport.width, `${viewport.width}px: inside the screen`);
    assert.ok(box.y > heading.y && box.y + box.height < upload.y, `${viewport.width}px: under the heading, above the upload`);
    assert.ok(upload.y < viewport.height * 0.6, `${viewport.width}px: the upload still starts on the first screen (${upload.y}px)`);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${viewport.width}px: no sideways scroll`);
    assert.equal(await shown(page), items[0].text, 'the newest change first');
    assert.equal(await count(page), `1 of ${items.length}`);

    const seen = [await shown(page)];
    for (let i = 1; i <= items.length; i++) {
      await page.clock.runFor(5000);
      seen.push(await shown(page));
      const h = (await page.locator('#whats-new summary').boundingBox()).height;
      assert.ok(h <= 36, `${viewport.width}px: still one line on change ${i} (${h}px)`);
    }
    assert.deepEqual(seen.slice(0, items.length), items.map((i) => i.text), 'the next change every 5 seconds');
    assert.equal(seen[items.length], items[0].text, 'back to the newest after the last');
    assert.equal(await count(page), `1 of ${items.length}`);

    await page.hover('#whats-new summary');
    await page.clock.runFor(15000);
    assert.equal(await shown(page), items[0].text, 'it waits while the pointer is on it');
    await page.mouse.move(0, viewport.height - 1);

    await page.click('#whats-new summary');
    const listed = await page.locator('#whats-new .wn-list li span').allInnerTexts();
    assert.deepEqual(listed, items.map((i) => i.text), 'a tap shows every change');
    assert.match(await page.locator('#whats-new .wn-head').innerText(), /^Updated \d+ \w{3} \d{4}\./);
    await page.context().close();
  }

  const still = await open({ width: 390, height: 844 }, { motion: 'reduce' });
  await still.clock.runFor(30000);
  assert.equal(await shown(still), items[0].text, 'no movement for people who turn off motion');
  assert.equal(await count(still), `1 of ${items.length}`);
  console.log(`whats-new: one line at 390 and 1440 px, ${items.length} changes every 5 s, still without motion`);
} finally {
  if (browser) await browser.close();
  server.kill();
}
