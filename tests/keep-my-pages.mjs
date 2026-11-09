/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// "Keep my pages" on the upload screen (app.js keepIfAsked, analyser.html).
// Photos are never kept unless the box is ticked; when it is, the same JPEG
// the analyser received goes to vahinitech.com's keep store with the check's
// facts, and the page says to open the emailed link. Runs the real markup and
// functions in Chromium against a stubbed store; no server needed.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const app = await readFile('frontend/src/app/app.js', 'utf8');
const html = await readFile('frontend/analyser.html', 'utf8');
const keep = app.slice(app.indexOf('const KEEP_EMAIL_RE'), app.indexOf('\n/* The "next step" block'));
const note = html.match(/<div class="photo-note"[\s\S]*?\n    <\/div>/)[0];
const status = html.match(/<p class="keep-status"[^>]*><\/p>/)[0];
const css = html.match(/<style>[\s\S]*?<\/style>/)[0];
const JPEG = [...await readFile('tests/fixtures/handwriting-sample.jpg')];
const FACTS = { overall: 74, factors: [{ n: 5, score: 50, band: 'dev', measured: true }] };

const browser = await chromium.launch();
try {
  const ctx = await browser.newContext();
  const calls = [];
  await ctx.route('https://keep-test.local/', (r) => r.fulfill({ contentType: 'text/html', body: `<!doctype html><head>${css}</head><body>${note}${status}</body>` }));
  await ctx.route('https://keep-test.local/persist/keep/**', async (r) => {
    const req = r.request();
    calls.push({ url: new globalThis.URL(req.url()).pathname, type: req.headers()['content-type'], token: req.headers()['x-upload-token'] || '', body: req.postDataBuffer() });
    if (req.url().endsWith('/start')) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, id: 'f'.repeat(32), uploadToken: 'T'.repeat(43) }) });
    return r.fulfill({ contentType: 'application/json', body: '{"ok":true,"mailed":true}' });
  });
  const p = await ctx.newPage();
  await p.goto('https://keep-test.local/');
  await p.addScriptTag({ content: `const $ = (s) => document.querySelector(s);\n${keep}\nsetupKeepPages(); window.k = { keepIfAsked, keepStatus, keepEmailMissing, keepForSample };` });
  const run = (opts) => p.evaluate(async ({ JPEG, FACTS, opts }) => {
    document.querySelector('#keep-pages').checked = !!opts.tick;
    document.querySelector('#keep-email').value = opts.email || '';
    window.VAHINI_SAMPLE_RUN = !!opts.sample;
    window.k.keepStatus('');
    const blob = new Blob([new Uint8Array(JPEG)], { type: opts.type || 'image/jpeg' });
    await window.k.keepIfAsked(blob, FACTS);
    const s = document.querySelector('#keep-status');
    return { shown: !s.hidden, text: s.textContent, error: s.classList.contains('is-error') };
  }, { JPEG, FACTS, opts });

  const before = await p.evaluate(() => ({ ticked: document.querySelector('#keep-pages').checked, emailHidden: document.querySelector('#keep-email-row').hidden }));
  assert.deepEqual(before, { ticked: false, emailHidden: true }, 'unticked by default, no email field');
  await p.click('#keep-pages');
  assert.equal(await p.evaluate(() => document.querySelector('#keep-email-row').hidden), false, 'ticking shows the email field');

  // Ticked with no usable email: Run does not start, and says why under the field.
  const guard = (opts) => p.evaluate((opts) => {
    document.querySelector('#keep-pages').checked = !!opts.tick;
    document.querySelector('#keep-email').value = opts.email || '';
    window.VAHINI_SAMPLE_RUN = !!opts.sample;
    const blocked = window.k.keepEmailMissing();
    const e = document.querySelector('#keep-email-error');
    return { blocked, shown: !e.hidden, text: e.textContent, invalid: document.querySelector('#keep-email').getAttribute('aria-invalid') };
  }, opts);
  let g = await guard({ tick: true, email: '' });
  assert.ok(g.blocked && g.shown && /Enter your email/.test(g.text) && g.invalid === 'true', 'ticked, no email: the check does not start and the field says why');
  assert.equal(await p.evaluate(() => document.activeElement.id), 'keep-email', 'the email field gets the focus');
  g = await guard({ tick: true, email: 'parent@' });
  assert.ok(g.blocked && /does not look right/.test(g.text), 'a bad address blocks with its own message');
  await p.fill('#keep-email', 'parent@example.com');
  assert.equal(await p.evaluate(() => document.querySelector('#keep-email-error').hidden), true, 'typing clears the message');
  g = await guard({ tick: true, email: 'parent@example.com' });
  assert.ok(!g.blocked && !g.shown, 'a good address lets the check start');
  assert.ok(!(await guard({ tick: false, email: '' })).blocked, 'unticked never blocks');
  assert.ok((await guard({ tick: true, email: '', sample: true })).blocked, 'a ticked box needs an email even with the sample loaded');
  // The sample is never kept: while it is loaded the box is unticked and off, with a note.
  const sampleState = () => p.evaluate(() => ({ ticked: document.querySelector('#keep-pages').checked, disabled: document.querySelector('#keep-pages').disabled,
    note: !document.querySelector('#keep-sample-note').hidden, row: !document.querySelector('#keep-email-row').hidden }));
  await p.evaluate(() => { document.querySelector('#keep-pages').checked = true; document.querySelector('#keep-email-row').hidden = false; window.k.keepForSample(true); });
  assert.deepEqual(await sampleState(), { ticked: false, disabled: true, note: true, row: false }, 'sample loaded: box unticked and off, the note says why');
  await p.evaluate(() => window.k.keepForSample(false));
  assert.deepEqual(await sampleState(), { ticked: false, disabled: false, note: false, row: false }, 'own photo: the box is back on');
  assert.ok(/By running the check you agree to the <a href="\/terms\.html#analyser-terms">terms of the check<\/a>\. If the writer is under 18, a parent, guardian or teacher says yes first\. It describes the page and does not diagnose anything\./.test(html), 'the consent line, with the terms link, sits above Run');

  let r = await run({ tick: false, email: 'parent@example.com' });
  assert.equal(calls.length, 0, 'unticked: nothing leaves for the keep store'); assert.equal(r.shown, false);
  r = await run({ tick: true, email: 'parent@example.com', sample: true });
  assert.equal(calls.length, 0, 'the sample is never kept');
  r = await run({ tick: true, email: 'not an address' });
  assert.equal(calls.length, 0, 'a bad address sends nothing'); assert.ok(r.error && /email address looks wrong/.test(r.text));

  r = await run({ tick: true, email: 'parent@example.com' });
  assert.equal(calls.length, 2, 'ticked: start, then the image');
  const start = JSON.parse(calls[0].body.toString('utf8'));
  assert.equal(calls[0].url, '/persist/keep/start');
  assert.deepEqual(start, { email: 'parent@example.com', facts: FACTS, consent: { keep: true } }, 'start carries the address, the facts and the consent, nothing else');
  assert.equal(calls[1].url, `/persist/keep/image/${'f'.repeat(32)}`);
  assert.equal(calls[1].type, 'image/jpeg'); assert.equal(calls[1].token, 'T'.repeat(43));
  assert.ok(calls[1].body.equals(Buffer.from(JPEG)), 'the image is the JPEG the analyser received, unchanged');
  assert.ok(!r.error && /Check your email: we sent a link to parent@example\.com\. Open it within 24 hours/.test(r.text), r.text);
  console.log('keep-my-pages: unticked by default; ticked needs an email before Run; nothing sent unless ticked; the analysed JPEG and facts sent when it is');
} finally {
  await browser.close();
}
