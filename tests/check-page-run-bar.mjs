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

  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    // A first visit: vahinitech.com's cookie card sits in the bottom corner
    // (site.js sets body.cc-open and --cc-h). The stuck bar rides above it,
    // so Analyse is never under the card, and Feedback goes above both.
    const page = await open(viewport);
    const w = viewport.width;
    await page.evaluate(() => {
      const cc = document.createElement('div'); cc.className = 'cc';
      cc.style.cssText = 'position:fixed;left:12px;bottom:12px;width:min(390px,calc(100vw - 24px));height:180px;z-index:400';
      document.body.append(cc); document.body.classList.add('cc-open');
      document.documentElement.style.setProperty('--cc-h', '192px');
    });
    await addPhoto(page);
    const card = await page.locator('.cc').boundingBox();
    const go = await page.locator('#go-process').boundingBox();
    assert.ok(go.y + go.height <= card.y + 1 && go.y >= 0, `${w}: Analyse sits above the cookie card (${go.y + go.height} vs ${card.y})`);
    const fb = await page.locator('.vfb-launch').boundingBox();
    const bar = await page.locator('#run-bar').boundingBox();
    assert.ok(fb.y + fb.height <= bar.y + 1, `${w}: Feedback sits above the bar and the card`);
    // Tab through the form: no focused field hides under the bar.
    await page.evaluate(() => window.scrollTo(0, 0));
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press('Tab');
      // Measure after the scroll and the observer that marks the bar stuck
      // have both run (two frames), or a slow machine reads the old state.
      const covered = await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => {
        const a = document.activeElement, b = document.querySelector('#run-bar');
        if (!a || b.contains(a) || !b.classList.contains('is-stuck')) return done('');
        const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
        done(ar.bottom > br.top + 2 && ar.top < br.bottom ? `${a.id || a.tagName} ${(a.textContent || a.value || '').trim().slice(0, 30)} at ${Math.round(ar.top)}-${Math.round(ar.bottom)}, bar ${Math.round(br.top)}-${Math.round(br.bottom)}` : '');
      }))));
      assert.equal(covered, '', `${w}: a field reached with Tab is never under the stuck bar`);
    }
    // Opened, the row's link says Done; folded again, Change.
    // (The toggle event comes after the click, so wait for the words.)
    const says = (t) => page.waitForFunction((x) => document.querySelector('.po-change').textContent === x, t, { timeout: 3000 });
    await page.locator('#page-opts > summary').click();
    await says('Done');
    await page.locator('#page-opts > summary').click();
    await says('Change');
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
  console.log('check-page-run-bar: Analyse on screen with a photo at 1440 and 390, the bar sticks only then, Feedback lifted; above the cookie card; Tab never lands under the bar; Optional row folds the picker (Change/Done); five tiles, one at a time, none with reduced motion');
} finally {
  if (browser) await browser.close();
  server.kill();
}
