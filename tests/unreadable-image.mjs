/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// A photo the browser cannot open must say so, and must not reach the
// upload store as a failure. On 2026-10-06 a visitor on Chrome for Mac tried
// one iPhone HEIC photo five times: the page showed nothing, and the store
// logged five rejected uploads. Chromium, like Chrome, cannot decode HEIC, so
// the page converts it with libheif; when that fails, it says what to do.
// tests/fixtures/handwriting-sample.heic is a real HEIC (brand heic, HEVC,
// 540 x 720) made from handwriting-sample.jpg with libheif's x265 encoder.
// Uses the real functions from app.js and analyser.html and the real libheif
// files from the pinned CDN URLs; no server needed.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { chromium } from 'playwright';

const app = await readFile('frontend/src/app/app.js', 'utf8');
const reader = app.slice(app.indexOf('function isHeic('), app.indexOf('\nfunction setupUploadDrop('));
assert.ok(reader.includes('function readImageFile('), 'readImageFile not found in app.js');
const page = await readFile('frontend/analyser.html', 'utf8');
const store = page.slice(page.indexOf('  function readAsDataURL('), page.indexOf('  function readConsent('))
  + page.slice(page.indexOf('  var STORED_TYPES'), page.indexOf('  function persistUpload('));
assert.ok(store.includes('function asStorable('), 'asStorable not found in analyser.html');

// The libheif files the page loads, fetched once and served to the browser
// from the test, and checked against the hashes app.js pins.
const LIBHEIF = Object.fromEntries([...reader.matchAll(/(js|jsSri|wasm|wasmSha384): '([^']+)'/g)].map((m) => [m[1], m[2]]));
const cdn = new Map();
for (const url of [LIBHEIF.js, LIBHEIF.wasm]) {
  const res = await fetch(url);
  assert.ok(res.ok, `Cannot load ${url}`);
  cdn.set(url, Buffer.from(await res.arrayBuffer()));
}
assert.equal('sha384-' + createHash('sha384').update(cdn.get(LIBHEIF.js)).digest('base64'), LIBHEIF.jsSri, 'libheif.js matches its SRI hash');
assert.equal(createHash('sha384').update(cdn.get(LIBHEIF.wasm)).digest('base64'), LIBHEIF.wasmSha384, 'libheif.wasm matches its pinned hash');
const REAL_HEIC = [...await readFile('tests/fixtures/handwriting-sample.heic')];
assert.equal(Buffer.from(REAL_HEIC.slice(4, 12)).toString('latin1'), 'ftypheic', 'the fixture is a HEIC file');

// A 2x2 PNG, and the same picture as a GIF: a type the browser opens but the
// store does not keep, so it must arrive there as a JPEG.
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGP4z8DAwMDAxMDAAAAR/wP/7Dz5jwAAAABJRU5ErkJggg==';
const GIF = 'R0lGODlhAgACAIAAAP///wAAACwAAAAAAgACAAACAoRRADs=';
// Only the first bytes of a HEIC file: named like one, but cannot be decoded.
const BROKEN_HEIC = [0, 0, 0, 24, 102, 116, 121, 112, 104, 101, 105, 99, 0, 0, 0, 0, 109, 105, 102, 49, 104, 101, 105, 99];

const browser = await chromium.launch();
try {
  // tamper: serve a wasm file one byte off, as a compromised CDN would.
  const open = async (tamper) => {
    const context = await browser.newContext();
    await context.route('https://unreadable-test.local/**', (route) => route.fulfill({ contentType: 'text/html', body: '<!doctype html><body><div id="dz-notice" hidden></div></body>' }));
    await context.route('https://cdn.jsdelivr.net/**', (route) => {
      const url = route.request().url();
      let body = cdn.get(url);
      assert.ok(body, `Unexpected CDN request ${url}`);
      if (tamper && url === LIBHEIF.wasm) { body = Buffer.from(body); body[body.length - 1] ^= 1; }
      return route.fulfill({ contentType: url.endsWith('.wasm') ? 'application/wasm' : 'text/javascript', headers: { 'access-control-allow-origin': '*' }, body });
    });
    const p = await context.newPage();
    await p.goto('https://unreadable-test.local/');
    await p.addScriptTag({ content: `const $ = (s) => document.querySelector(s);\n${reader}\nwindow.t = { isHeic, readImageFile, heicToJpeg, showDzNotice };` });
    await p.addScriptTag({ content: `${store}\nwindow.s = { asStorable };` });
    return p;
  };
  const p = await open(false);
  const r = await p.evaluate(async ({ PNG, GIF, BROKEN_HEIC, REAL_HEIC }) => {
    const bytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const read = (file) => new Promise((ok) => window.t.readImageFile(file, () => ok('opened'), () => ok('failed')));
    const size = (blob) => new Promise((ok) => { const i = new Image(); i.onload = () => ok([i.naturalWidth, i.naturalHeight]); i.onerror = () => ok(['unreadable']); i.src = URL.createObjectURL(blob); });
    const notice = (file) => { window.t.showDzNotice(file); const n = document.querySelector('#dz-notice'); return (n.hidden ? 'hidden: ' : '') + n.textContent; };
    const heic = new File([new Uint8Array(REAL_HEIC)], 'IMG_0001.heic', { type: 'image/heic' });
    const heicNoType = new File([new Uint8Array(REAL_HEIC)], 'IMG_0002.HEIC', { type: '' });
    const broken = new File([new Uint8Array(BROKEN_HEIC)], 'IMG_0003.heic', { type: 'image/heic' });
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
    const jpeg = await window.t.heicToJpeg(heic);
    const again = await window.t.heicToJpeg(heic);
    const jpegNoType = await window.t.heicToJpeg(heicNoType);
    let brokenErr = '';
    try { await window.t.heicToJpeg(broken); } catch (e) { brokenErr = e.message; }
    const wide = await window.s.asStorable(bmp(5000, 4));
    const wideSize = await new Promise((ok) => { const i = new Image(); i.onload = () => ok([i.naturalWidth, i.naturalHeight, wide.type]); i.onerror = () => ok(['unreadable']); i.src = wide.dataUrl; });
    return {
      wideSize,
      heic: await read(heic), heicNoType: await read(heicNoType), png: await read(png), text: await read(text),
      converted: [jpeg.name, jpeg.type, ...await size(jpeg)], same: jpeg === again,
      convertedNoType: [jpegNoType.name, ...await size(jpegNoType)], brokenErr,
      heicMsg: notice(heic), textMsg: notice(text),
      storePng: await stored(png), storeGif: await stored(gif), storeHeic: await stored(heic), storeBroken: await stored(broken),
    };
  }, { PNG, GIF, BROKEN_HEIC, REAL_HEIC });

  // A wasm file that does not match its hash is never run.
  const t = await open(true);
  const tampered = await t.evaluate(async (REAL_HEIC) => {
    try { await window.t.heicToJpeg(new File([new Uint8Array(REAL_HEIC)], 'IMG_0004.heic', { type: 'image/heic' })); return 'converted'; } catch (e) { return e.message; }
  }, REAL_HEIC);

  assert.equal(r.png, 'opened', 'a PNG opens');
  assert.equal(r.heic, 'failed', 'a HEIC photo this browser cannot open reports a failure instead of doing nothing');
  assert.equal(r.heicNoType, 'failed', 'a .HEIC file with no type is recognised too');
  assert.equal(r.text, 'failed', 'a non-image file reports a failure');
  assert.deepEqual(r.converted, ['IMG_0001.jpg', 'image/jpeg', 540, 720], 'a real HEIC photo is converted to a JPEG of the same size');
  assert.ok(r.same, 'one conversion per file, shared by the preview and the store');
  assert.deepEqual(r.convertedNoType, ['IMG_0002.jpg', 540, 720], 'a .HEIC file with no type is converted too');
  assert.ok(r.brokenErr, 'a HEIC file libheif cannot decode is reported, not hung');
  assert.match(r.heicMsg, /iPhone photo \(HEIC\)/); assert.match(r.heicMsg, /Preview/); assert.match(r.heicMsg, /Most Compatible/);
  assert.doesNotMatch(r.heicMsg, /^hidden/, 'the notice is shown');
  assert.match(r.textMsg, /JPEG or PNG/);
  assert.match(tampered, /integrity/, 'a wasm file that fails its hash is refused');
  assert.match(r.storePng, /^image\/png page\.png data:image\/png;base64/, 'a PNG goes to the store as it is');
  assert.match(r.storeGif, /^image\/jpeg page\.jpg data:image\/jpeg;base64/, 'an image the store does not keep is sent as a JPEG made in the browser');
  assert.deepEqual(r.wideSize, [4000, 3, 'image/jpeg'], 'a large image is scaled to 4000 px on its long side before it is converted');
  assert.match(r.storeHeic, /^image\/jpeg IMG_0001\.jpg data:image\/jpeg;base64/, 'a HEIC photo reaches the store as the converted JPEG');
  assert.match(r.storeBroken, /^not sent: /, 'a photo that cannot be opened or converted is not sent to the store');
  console.log('unreadable-image: HEIC converted in Chromium, unreadable photos explained, store gets only JPEG/PNG/WebP');
} finally {
  await browser.close();
}
