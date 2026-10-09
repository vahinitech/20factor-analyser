/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// A photo the browser cannot open must say so, and must not reach the
// upload store as a failure. On 2026-10-06 a visitor on Chrome for Mac tried
// one iPhone HEIC photo five times: the page showed nothing, and the store
// logged five rejected uploads. Chromium, like Chrome, cannot decode HEIC.
// Uses the real functions from app.js and analyser.html; no server needed.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const app = await readFile('frontend/src/app/app.js', 'utf8');
const reader = app.slice(app.indexOf('function isHeic('), app.indexOf('\nfunction setupUploadDrop('));
assert.ok(reader.includes('function readImageFile('), 'readImageFile not found in app.js');
const page = await readFile('frontend/analyser.html', 'utf8');
const store = page.slice(page.indexOf('  function readAsDataURL('), page.indexOf('  function readConsent('))
  + page.slice(page.indexOf('  var STORED_TYPES'), page.indexOf('  function persistUpload('));
assert.ok(store.includes('function asStorable('), 'asStorable not found in analyser.html');

// A 2x2 PNG, and the same picture as a GIF: a type the browser opens but the
// store does not keep, so it must arrive there as a JPEG.
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGP4z8DAwMDAxMDAAAAR/wP/7Dz5jwAAAABJRU5ErkJggg==';
const GIF = 'R0lGODlhAgACAIAAAP///wAAACwAAAAAAgACAAACAoRRADs=';
// The first bytes of a real iPhone HEIC file (an ftyp box, brand heic).
const HEIC = [0, 0, 0, 24, 102, 116, 121, 112, 104, 101, 105, 99, 0, 0, 0, 0, 109, 105, 102, 49, 104, 101, 105, 99];

const browser = await chromium.launch();
try {
  const context = await browser.newContext();
  await context.route('http://unreadable-test.local/**', (route) => route.fulfill({ contentType: 'text/html', body: '<!doctype html><body></body>' }));
  const p = await context.newPage();
  await p.goto('http://unreadable-test.local/');
  await p.addScriptTag({ content: `${reader}\nwindow.t = { isHeic, unreadableMessage, readImageFile };` });
  await p.addScriptTag({ content: `${store}\nwindow.s = { asStorable };` });
  const r = await p.evaluate(async ({ PNG, GIF, HEIC }) => {
    const bytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const read = (file) => new Promise((ok) => window.t.readImageFile(file, () => ok('opened'), () => ok('failed')));
    const heic = new File([new Uint8Array(HEIC)], 'IMG_0001.heic', { type: 'image/heic' });
    const heicNoType = new File([new Uint8Array(HEIC)], 'IMG_0002.HEIC', { type: '' });
    const png = new File([bytes(PNG)], 'page.png', { type: 'image/png' });
    const gif = new File([bytes(GIF)], 'page.gif', { type: 'image/gif' });
    const text = new File(['hello'], 'notes.txt', { type: 'text/plain' });
    const stored = async (f) => { try { const v = await window.s.asStorable(f); return v.type + ' ' + v.name + ' ' + v.dataUrl.slice(0, 23); } catch (e) { return 'not sent: ' + e.message; } };
    // A wide image of a type the store does not keep (BMP), to check the
    // conversion stays inside iOS Safari's canvas limit (4000 px long side).
    const bmp = (w, h) => {
      const row = Math.ceil(w * 3 / 4) * 4, size = 54 + row * h, b = new DataView(new ArrayBuffer(size));
      b.setUint16(0, 0x4d42, true); b.setUint32(2, size, true); b.setUint32(10, 54, true); b.setUint32(14, 40, true);
      b.setInt32(18, w, true); b.setInt32(22, h, true); b.setUint16(26, 1, true); b.setUint16(28, 24, true); b.setUint32(34, row * h, true);
      return new File([b.buffer], 'wide.bmp', { type: 'image/bmp' });
    };
    const wide = await window.s.asStorable(bmp(5000, 4));
    const wideSize = await new Promise((ok) => { const i = new Image(); i.onload = () => ok([i.naturalWidth, i.naturalHeight, wide.type]); i.onerror = () => ok(['unreadable']); i.src = wide.dataUrl; });
    return {
      wideSize,
      heic: await read(heic), heicNoType: await read(heicNoType), png: await read(png), text: await read(text),
      heicMsg: window.t.unreadableMessage(heic), heicNoTypeMsg: window.t.unreadableMessage(heicNoType), textMsg: window.t.unreadableMessage(text),
      storePng: await stored(png), storeGif: await stored(gif), storeHeic: await stored(heic),
    };
  }, { PNG, GIF, HEIC });

  assert.equal(r.png, 'opened', 'a PNG opens');
  assert.equal(r.heic, 'failed', 'a HEIC photo this browser cannot open reports a failure instead of doing nothing');
  assert.equal(r.heicNoType, 'failed', 'a .HEIC file with no type is recognised too');
  assert.equal(r.text, 'failed', 'a non-image file reports a failure');
  assert.match(r.heicMsg, /HEIC/); assert.match(r.heicMsg, /Safari/); assert.match(r.heicMsg, /JPEG/);
  assert.match(r.heicNoTypeMsg, /HEIC/);
  assert.match(r.textMsg, /JPEG or PNG/);
  assert.match(r.storePng, /^image\/png page\.png data:image\/png;base64/, 'a PNG goes to the store as it is');
  assert.match(r.storeGif, /^image\/jpeg page\.jpg data:image\/jpeg;base64/, 'an image the store does not keep is sent as a JPEG made in the browser');
  assert.deepEqual(r.wideSize, [4000, 3, 'image/jpeg'], 'a large image is scaled to 4000 px on its long side before it is converted');
  assert.match(r.storeHeic, /^not sent: unreadable/, 'a photo the browser cannot open is not sent to the store');
  console.log('unreadable-image: unreadable photos explained, HEIC named, store gets only what it keeps');
} finally {
  await browser.close();
}
