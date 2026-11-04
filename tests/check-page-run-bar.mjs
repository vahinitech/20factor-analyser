/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// Analyse within reach, and the five skill tiles (owner, 2026-11-04):
// - with a photo in, Analyse is on the first screen at 1440x900 and on a
//   390x844 phone: the terms line and the button stick to the bottom of the
//   screen until they reach their place, and then stop sticking;
// - before a photo they do not stick (the button is disabled);
// - the site's Feedback button is lifted above the stuck bar;
// - letter style and the copied sentence fold into one "Optional" row;
// - each skill row has its tile, the tile never makes a row taller, the
//   rows play one at a time, and with reduced motion none plays.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4236', '-c-1', '--silent']);
const URL = 'http://127.0.0.1:4236/frontend/analyser.html';
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4236/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const open = async (viewport, reducedMotion = 'no-preference') => {
    const ctx = await browser.newContext({ viewport, reducedMotion });
    await ctx.addInitScript(() => { try { localStorage.setItem('vahini_guide_check', '1'); } catch {} });
    const page = await ctx.newPage();
    await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
    await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
    await page.goto(URL, { waitUntil: 'networkidle' });
    // The site's Feedback button, as vahinitech.com's site.js adds it.
    await page.evaluate(() => { const b = document.createElement('button'); b.className = 'vfb-launch'; b.textContent = 'Feedback'; b.style.cssText = 'position:fixed;right:12px;bottom:12px;height:40px'; document.body.append(b); });
    return page;
  };
  const inView = (page, sel) => page.locator(sel).evaluate((e) => { const r = e.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; });
  const addPhoto = async (page) => {
    await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
    await page.waitForFunction(() => !document.querySelector('#go-process').disabled);
    await page.waitForTimeout(200);
  };

  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await open(viewport);
    const w = viewport.width;
    assert.equal(await page.locator('#run-bar').evaluate((e) => getComputedStyle(e).position), 'static', `${w}: no sticking before a photo`);
    assert.equal(await page.locator('#page-opts').evaluate((d) => d.open), false, `${w}: the Optional row starts folded`);
    assert.match(await page.locator('#page-opts > summary').innerText(), /Optional[\s\S]*Letter style[\s\S]*Not sure[\s\S]*Copied sentence[\s\S]*None[\s\S]*Change/);
    await addPhoto(page);
    assert.equal(await inView(page, '#go-process'), true, `${w}: Analyse is on screen once a photo is in`);
    assert.equal(await inView(page, '#run-consent'), true, `${w}: and so are the terms beside it`);
    const stuck = await page.locator('#run-bar').evaluate((e) => e.classList.contains('is-stuck'));
    if (stuck) {
      const bar = await page.locator('#run-bar').boundingBox();
      const fb = await page.locator('.vfb-launch').boundingBox();
      assert.ok(fb.y + fb.height <= bar.y + 1, `${w}: Feedback sits above the stuck bar (${fb.y + fb.height} vs ${bar.y})`);
    }
    await page.locator('#run-bar-end').scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollBy(0, 200));
    await page.waitForTimeout(200);
    assert.equal(await page.locator('#run-bar').evaluate((e) => e.classList.contains('is-stuck')), false, `${w}: in its place it stops sticking`);
    assert.equal(await page.locator('.vfb-launch').evaluate((e) => getComputedStyle(e).bottom), '12px', `${w}: and Feedback goes back down`);

    // Five tiles, none making its row taller or wider.
    const rows = await page.locator('#benefit-list > li').evaluateAll((lis) => lis.map((li) => {
      const tile = li.querySelector('svg.sk'), text = li.querySelector('div');
      return { tile: !!tile, th: tile && tile.getBoundingClientRect().height, xh: text.getBoundingClientRect().height, overflow: li.scrollWidth > li.clientWidth };
    }));
    assert.equal(rows.length, 5);
    for (const r of rows) {
      assert.ok(r.tile, `${w}: every skill has its tile`);
      assert.ok(r.th <= r.xh, `${w}: a tile (${r.th}px) is no taller than its words (${r.xh}px)`);
      assert.equal(r.overflow, false, `${w}: no row runs wider than the column`);
    }
    await page.locator('#benefit-list').scrollIntoViewIfNeeded();
    await page.waitForFunction(() => document.querySelectorAll('#benefit-list > li.is-on').length === 1);
    const first = await page.locator('#benefit-list > li.is-on h3').innerText();
    await page.waitForFunction((f) => { const on = document.querySelector('#benefit-list > li.is-on h3'); return on && on.textContent !== f; }, first, { timeout: 6000 });
    assert.equal(await page.locator('#benefit-list > li.is-on').count(), 1, `${w}: one tile plays at a time`);
    await page.context().close();
  }

  {
    const page = await open({ width: 1440, height: 900 }, 'reduce');
    await page.locator('#benefit-list').scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    assert.equal(await page.locator('#benefit-list > li.is-on').count(), 0, 'reduced motion: no tile plays');
    assert.equal(await page.evaluate(() => document.getAnimations().filter((a) => a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('.sk')).length), 0, 'and nothing moves');
    await page.context().close();
  }

  {
    // A link that picks a style opens the row, and it names the style.
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
    await page.goto(`${URL}?style=french`, { waitUntil: 'networkidle' });
    assert.equal(await page.locator('#page-opts').evaluate((d) => d.open), true, '?style= opens the Optional row');
    assert.equal(await page.locator('#po-style').innerText(), 'French cursive');
    await ctx.close();
  }
  console.log('check-page-run-bar: Analyse on screen with a photo at 1440 and 390, the bar sticks only then, Feedback lifted; Optional row folds the picker; five tiles, one at a time, none with reduced motion');
} finally {
  if (browser) await browser.close();
  server.kill();
}
