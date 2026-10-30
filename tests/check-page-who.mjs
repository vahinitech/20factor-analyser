/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// The check page's "I am" and "Report in" row, and the line-by-line sweep
// while a photo is checked (owner, 2026-10-25). The real analyser page, its
// recognition server stubbed:
// - "Who is checking?" (DPDP Rules, rule 10): nothing chosen on a first
//   visit, and Analyse says so instead of starting; Student shows the
//   adult's tick and needs it; Student picks the student view, the other
//   three the parent report; a grown-up's answer is kept in this browser
//   for the next visit, Student never; ?for=student starts on Student with
//   the tick still to do; the answer goes with the photo as one word
//   (who=parent...), the sample page as who=sample;
// - "Report in" is the report's language, the same choice as "Print in",
//   and is never sent;
// - one row under the heading, inside a phone screen, the upload still on
//   the first screen;
// - after "Analyse", the photo's own lines are swept one at a time, with
//   "Reading line n of N" and one bar a line, going round again until the
//   answer; no moving sweep for people who turn off motion; it stops when
//   the screen changes.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const server = spawn('./node_modules/.bin/http-server', ['.', '-p', '4219', '-c-1', '--silent']);
const URL = 'http://127.0.0.1:4219/frontend/analyser.html';
let browser;
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:4219/')).ok) break; } catch {} await new Promise((r) => setTimeout(r, 100)); }
  browser = await chromium.launch();
  const open = async (viewport, { query = '', motion = 'no-preference', context } = {}) => {
    const ctx = context || await browser.newContext({ viewport, reducedMotion: motion });
    const page = await ctx.newPage();
    const sent = [];
    page.on('request', (r) => { if (r.method() !== 'GET') sent.push(`${r.url()} ${r.postData() || ''}`); });
    let answer;
    const held = new Promise((r) => { answer = r; });
    await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
    await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
    await page.route('**/api/v2/reports?**', async (r) => { await held; r.fulfill({ status: 502, contentType: 'text/html', body: '<h1>502</h1>' }); });
    await page.goto(URL + query, { waitUntil: 'networkidle' });
    return { page, sent, answer, ctx };
  };
  const who = (page) => page.locator('input[name="check-who"]:checked').getAttribute('value');
  const view = (page) => page.evaluate(() => window.VahiniReport.audience());

  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }]) {
    const { page, sent, ctx } = await open(viewport);
    assert.equal(await page.locator('input[name="check-who"]:checked').count(), 0, 'nothing chosen on a first visit');
    assert.equal(await view(page), 'parent');
    assert.equal(await page.locator('#who-adult-row').isVisible(), false, 'no adult tick until Student');
    assert.equal(await page.locator('#check-lang').inputValue(), 'en', 'English by default');
    const bar = await page.locator('#who-bar').boundingBox();
    const heading = await page.locator('.check-heading h1').boundingBox();
    const upload = await page.locator('#start-check').boundingBox();
    assert.ok(bar.y > heading.y && bar.y + bar.height < upload.y, `${viewport.width}px: under the heading, above the upload`);
    assert.ok(bar.x >= 0 && bar.x + bar.width <= viewport.width, `${viewport.width}px: inside the screen`);
    assert.ok(upload.y < viewport.height * 0.6, `${viewport.width}px: the upload still starts on the first screen (${upload.y}px)`);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no sideways scroll');

    await page.check('input[name="check-who"][value="student"]');
    assert.equal(await view(page), 'student', 'Student picks the student view');
    assert.equal(await page.locator('#who-adult-row').isVisible(), true, 'Student shows the adult tick');
    assert.equal(await page.locator('#who-adult').isChecked(), false, 'the tick starts empty');
    assert.equal(await page.evaluate(() => localStorage.getItem('vahini_check_who')), null, 'Student is never kept');
    for (const v of ['teacher', 'self', 'parent']) {
      await page.check(`input[name="check-who"][value="${v}"]`);
      assert.equal(await view(page), 'parent', `${v}: the parent report`);
    }
    await page.check('input[name="check-who"][value="teacher"]');
    await page.selectOption('#check-lang', 'te');
    assert.equal(await page.locator('#report-lang').inputValue(), 'te', '"Report in" sets "Print in"');
    assert.equal(await page.evaluate(() => window.VahiniI18n.language()), 'te');
    // "Print in" is beside the report, on a screen not shown yet.
    await page.evaluate(() => { const s = document.querySelector('#report-lang'); s.value = 'en'; s.dispatchEvent(new Event('change')); });
    assert.equal(await page.locator('#check-lang').inputValue(), 'en', 'and "Print in" sets "Report in"');

    const again = await ctx.newPage();
    await again.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
    await again.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
    await again.goto(URL, { waitUntil: 'networkidle' });
    assert.equal(await who(again), 'teacher', 'a grown-up\'s answer is kept for the next visit');
    assert.deepEqual(sent.filter((s) => /teacher|student|check-who|check_who/.test(s)), [], 'nothing sent before a check');
    await ctx.close();
  }

  {
    const { page, ctx } = await open({ width: 1280, height: 900 }, { query: '?for=student' });
    assert.equal(await who(page), 'student', '?for=student starts on Student');
    assert.equal(await view(page), 'student');
    assert.equal(await page.locator('#who-adult').isChecked(), false, '?for=student: the adult tick still to do');
    await ctx.close();
  }

  // Analyse waits for the answer, and the answer goes with the photo.
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await ctx.addInitScript(() => { try { localStorage.setItem('vahini_guide_check', '1'); } catch {} });
    const page = await ctx.newPage();
    const bodies = [];
    await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
    await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
    await page.route('**/api/v2/reports?**', (r) => { bodies.push(r.request().postDataBuffer().toString('latin1')); r.fulfill({ status: 502, contentType: 'text/html', body: '<h1>502</h1>' }); });
    await page.goto(URL, { waitUntil: 'networkidle' });
    const whoSent = (body) => (body.match(/name="who"\r\n\r\n([^\r]*)/) || [])[1];
    const restart = async () => { await page.goto(URL, { waitUntil: 'networkidle' }); };
    const photo = async () => {
      await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
      await page.waitForFunction(() => !document.querySelector('#go-process').disabled);
    };
    await photo();
    await page.click('#go-process');
    assert.equal(await page.locator('#who-error').isVisible(), true, 'no answer: Analyse says so');
    assert.match(await page.locator('#who-error').innerText(), /Choose who is checking/);
    assert.equal(await page.locator('#screen-upload').evaluate((s) => s.classList.contains('on')), true, 'and stays on the upload');
    assert.equal(bodies.length, 0, 'and sends nothing');

    await page.check('input[name="check-who"][value="student"]');
    assert.equal(await page.locator('#who-error').isVisible(), false, 'choosing clears the note');
    await page.click('#go-process');
    assert.match(await page.locator('#who-error').innerText(), /parent, guardian or teacher to say yes/, 'Student without the tick: ask an adult');
    assert.equal(bodies.length, 0, 'still nothing sent');
    await page.check('#who-adult');
    await page.click('#go-process');
    for (let i = 0; i < 50 && !bodies.length; i++) await page.waitForTimeout(100);
    assert.equal(whoSent(bodies[0] || ''), 'student', 'Student with the tick: who=student');

    await restart();
    await photo();
    await page.check('input[name="check-who"][value="parent"]');
    let n = bodies.length;
    await page.click('#go-process');
    for (let i = 0; i < 50 && bodies.length <= n; i++) await page.waitForTimeout(100);
    assert.equal(whoSent(bodies[n] || ''), 'parent', 'Parent: who=parent');
    assert.ok(!/name="(check-who|check_lang|report_lang)"/.test(bodies[n]), 'the report language is not sent');

    // Vahini's own sample page needs no answer.
    await ctx.clearCookies();
    await page.evaluate(() => localStorage.removeItem('vahini_check_who'));
    await restart();
    assert.equal(await page.locator('input[name="check-who"]:checked').count(), 0);
    await page.click('#try-sample');
    await page.waitForFunction(() => !document.querySelector('#go-process').disabled);
    n = bodies.length;
    await page.click('#go-process');
    for (let i = 0; i < 50 && bodies.length <= n; i++) await page.waitForTimeout(100);
    assert.equal(whoSent(bodies[n] || ''), 'sample', 'the sample page: who=sample');
    await ctx.close();
  }

  // The sweep, on the sample photo, while the server has not answered.
  {
    const { page, answer, ctx } = await open({ width: 1280, height: 900 });
    await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
    await page.waitForFunction(() => !document.querySelector('#go-process').disabled);
    await page.check('input[name="check-who"][value="parent"]'); await page.click('#go-process');
    await page.waitForSelector('#proc-stage.is-scanning .scan-cap');
    const n = await page.locator('.scan-bars span').count();
    assert.ok(n >= 3 && n <= 12, `the photo's lines, one bar each (${n})`);
    assert.match(await page.locator('.scan-cap').innerText(), new RegExp(`^Reading line 1 of ${n}$`));
    assert.equal(await page.locator('.scan-line.now').count(), 1, 'one line at a time');
    assert.equal(await page.locator('.scan-beam').count(), 1, 'a moving sweep');
    await page.waitForFunction(() => document.querySelectorAll('.scan-letters').length > 0, null, { timeout: 3000 });
    await page.waitForFunction((n) => /^Reading line 2 of /.test(document.querySelector('.scan-cap').textContent), n, { timeout: 4000 });
    assert.equal(await page.locator('.scan-line.done').count(), 1, 'the first line is done');
    assert.equal(await page.locator('.scan-bars span.done').count(), 1);
    // Round again until the answer comes.
    await page.waitForFunction(() => /^Reading line 1 of /.test(document.querySelector('.scan-cap').textContent), null, { timeout: 1600 * (n + 1) });
    // The photo stays the size of the frame; the marks stay on it.
    const photo = await page.locator('.scan-sweep img.proc-preview').boundingBox();
    const stage = await page.locator('#proc-stage').boundingBox();
    assert.ok(photo.width <= stage.width && photo.height <= 410, 'the photo fits the frame');
    answer();
    await page.waitForSelector('#screen-process .reject-card', { timeout: 20000 });
    assert.equal(await page.locator('.scan-cap').count(), 0, 'the sweep ends with the screen');
    await ctx.close();
  }

  {
    const { page, ctx } = await open({ width: 1280, height: 900 }, { motion: 'reduce' });
    await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
    await page.waitForFunction(() => !document.querySelector('#go-process').disabled);
    await page.check('input[name="check-who"][value="parent"]'); await page.click('#go-process');
    await page.waitForSelector('#proc-stage.is-scanning .scan-cap');
    assert.equal(await page.locator('.scan-beam').count(), 0, 'no moving sweep when motion is off');
    assert.equal(await page.locator('.scan-line.now').count(), 1, 'the line being read is still marked');
    await ctx.close();
  }
  // "Does this page copy a sentence?" (owner, 2026-10-25): folded and empty
  // by default; what is typed goes with the photo as expected_text; empty
  // sends nothing to compare; the sample page never takes it.
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await ctx.addInitScript(() => { try { localStorage.setItem('vahini_guide_check', '1'); } catch {} });
    const page = await ctx.newPage();
    const bodies = [];
    await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
    await page.route('**/api/v2/me', (r) => r.fulfill({ json: { access: { tier: 'free' } } }));
    await page.route('**/api/v2/reports?**', (r) => { bodies.push(r.request().postDataBuffer().toString('latin1')); r.fulfill({ status: 502, contentType: 'text/html', body: '<h1>502</h1>' }); });
    await page.goto(URL, { waitUntil: 'networkidle' });
    const box = page.locator('#copy-sentence');
    assert.equal(await box.evaluate((d) => d.open), false, 'folded by default');
    assert.match(await box.locator('summary').innerText(), /Does this page copy a sentence\?[\s\S]*Optional/);
    const expected = (body) => (body.match(/name="expected_text"\r\n\r\n([^\r]*)/) || [])[1];
    const send = async () => {
      bodies.length = 0;   // a local page also tries a second address
      await page.setInputFiles('#file-input', 'frontend/assets/samples/handwriting-sample.jpg');
      await page.waitForFunction(() => !document.querySelector('#go-process').disabled);
      await page.check('input[name="check-who"][value="parent"]'); await page.click('#go-process');
      for (let i = 0; i < 100 && !bodies.length; i++) await page.waitForTimeout(100);
      await page.waitForTimeout(500);
      const body = bodies[bodies.length - 1];
      await page.evaluate(() => { const b = [...document.querySelectorAll('#screen-process button, #screen-process a')].find((x) => /another photo/i.test(x.textContent)); if (b) b.click(); else document.querySelector('#new-report')?.click(); });
      await page.waitForSelector('#screen-upload.on', { timeout: 20000 });
      return body;
    };
    assert.equal(expected(await send()) || '', '', 'empty by default: nothing to compare');
    await page.click('#copy-sentence summary');
    await page.fill('#cs-text', '  Seetha and   Rama practise slowly with care. ');
    assert.equal(expected(await send()), 'Seetha and Rama practise slowly with care.', 'the typed sentence goes with the photo, tidied');
    await ctx.close();
  }
  console.log('check-page-who: I am and Report in at 390 and 1440 px, kept and never sent; the sweep reads the photo line by line');
} finally {
  if (browser) await browser.close();
  server.kill();
}
