/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// A photo the browser cannot open must say so, and no photo ever leaves for
// the upload store: photos are never stored. On 2026-10-06 a visitor on
// Chrome for Mac tried one iPhone HEIC photo five times: the page showed
// nothing, and the store logged five rejected uploads. Chromium, like Chrome, cannot decode HEIC, so
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
const store = page.slice(page.indexOf('  var PHOTO_TYPES'), page.indexOf('  function persistUpload('));
assert.ok(store.includes('function photoRecord('), 'photoRecord not found in analyser.html');
// What a printed report is stored as: checkFacts and the photo-quality
// measure it uses, run on the sample report's real analysis.
const facts = app.slice(app.indexOf('const MIN_LONG_SIDE'), app.indexOf('\nfunction photoWarning('))
  + app.slice(app.indexOf('function checkFacts('), app.indexOf('\n/* The "next step" block'));
assert.ok(facts.includes('function checkFacts(') && facts.includes('function photoQuality('), 'checkFacts or photoQuality not found in app.js');
const sample = await readFile('frontend/scripts/core/sample-report-data.js', 'utf8');

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

// A 2x2 PNG.
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGP4z8DAwMDAxMDAAAAR/wP/7Dz5jwAAAABJRU5ErkJggg==';
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
    await p.addScriptTag({ content: `const readConsent = () => null;\n${store}\n${facts}\nwindow.s = { photoRecord, checkFacts };` });
    await p.addScriptTag({ content: sample });
    return p;
  };
  const p = await open(false);
  const r = await p.evaluate(async ({ PNG, BROKEN_HEIC, REAL_HEIC }) => {
    const bytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const read = (file) => new Promise((ok) => window.t.readImageFile(file, () => ok('opened'), () => ok('failed')));
    const size = (blob) => new Promise((ok) => { const i = new Image(); i.onload = () => ok([i.naturalWidth, i.naturalHeight]); i.onerror = () => ok(['unreadable']); i.src = URL.createObjectURL(blob); });
    const notice = (file) => { window.t.showDzNotice(file); const n = document.querySelector('#dz-notice'); return (n.hidden ? 'hidden: ' : '') + n.textContent; };
    const heic = new File([new Uint8Array(REAL_HEIC)], 'IMG_0001.heic', { type: 'image/heic' });
    const heicNoType = new File([new Uint8Array(REAL_HEIC)], 'IMG_0002.HEIC', { type: '' });
    const broken = new File([new Uint8Array(BROKEN_HEIC)], 'IMG_0003.heic', { type: 'image/heic' });
    const png = new File([bytes(PNG)], 'page.png', { type: 'image/png' });
    const text = new File(['hello'], 'notes.txt', { type: 'text/plain' });
    const named = new File([bytes(PNG)], 'Ravi Kumar homework.PNG', { type: 'image/png' });
    const record = (f) => JSON.stringify(window.s.photoRecord(f, 'file-input'));
    const jpeg = await window.t.heicToJpeg(heic);
    const again = await window.t.heicToJpeg(heic);
    const jpegNoType = await window.t.heicToJpeg(heicNoType);
    let brokenErr = '';
    try { await window.t.heicToJpeg(broken); } catch (e) { brokenErr = e.message; }
    return {
      heic: await read(heic), heicNoType: await read(heicNoType), png: await read(png), text: await read(text),
      converted: [jpeg.name, jpeg.type, ...await size(jpeg)], same: jpeg === again,
      convertedNoType: [jpegNoType.name, ...await size(jpegNoType)], brokenErr,
      heicMsg: notice(heic), textMsg: notice(text),
      recHeic: record(heic), recNamed: record(named), recNoType: record(heicNoType),
      facts: JSON.stringify(window.s.checkFacts(window.VAHINI_SAMPLE_REPORT.analysis, { nWords: 63 }, await new Promise((ok) => { const i = new Image(); i.onload = () => ok(i); i.src = URL.createObjectURL(png); }))),
    };
  }, { PNG, BROKEN_HEIC, REAL_HEIC });

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
  assert.ok(r.same, 'one conversion per file');
  assert.deepEqual(r.convertedNoType, ['IMG_0002.jpg', 540, 720], 'a .HEIC file with no type is converted too');
  assert.ok(r.brokenErr, 'a HEIC file libheif cannot decode is reported, not hung');
  assert.match(r.heicMsg, /iPhone photo \(HEIC\)/); assert.match(r.heicMsg, /Preview/); assert.match(r.heicMsg, /Most Compatible/);
  assert.doesNotMatch(r.heicMsg, /^hidden/, 'the notice is shown');
  assert.match(r.textMsg, /JPEG or PNG/);
  assert.match(tampered, /integrity/, 'a wasm file that fails its hash is refused');
  // Photos are never stored: the store gets a record, never the photo or its name.
  const recHeic = JSON.parse(r.recHeic);
  assert.deepEqual([recHeic.fileName, recHeic.mimeType, recHeic.source, recHeic.meta.size], ['photo.heic', 'image/heic', 'file-input', REAL_HEIC.length], 'a HEIC photo is described, not sent');
  for (const rec of [r.recHeic, r.recNamed, r.recNoType]) {
    assert.ok(!/dataUrl|data:|base64/.test(rec) && rec.length < 400, `the record carries no image data: ${rec}`);
  }
  assert.ok(!/Ravi|homework/i.test(r.recNamed) && JSON.parse(r.recNamed).fileName === 'photo.png', 'the record keeps the extension, not the file name');
  assert.equal(JSON.parse(r.recNoType).mimeType, '', 'a file with no type is sent with no type');
  // A printed report is stored as numbers and short codes: no factor names,
  // tips, evidence or recognised text from the analysis it came from.
  const f = JSON.parse(r.facts);
  assert.equal(f.overall, 74); assert.equal(f.factors.length, 20); assert.deepEqual(f.priorities.length, 3);
  assert.equal(f.recognition.confidence, 78); assert.equal(f.words, 63); assert.deepEqual(f.photo, { size: 'small', sharp: f.photo.sharp });
  const strings = JSON.stringify(f).match(/"[^"]*"/g).map((x) => x.slice(1, -1));
  const allowed = new Set(['overall', 'tier', 'factors', 'n', 'score', 'band', 'measured', 'priorities', 'recognition', 'backend', 'level', 'confidence', 'handLines', 'printedLines', 'words', 'photo', 'size', 'sharp',
    'good', 'strong', 'dev', 'focus', 'paddle', 'moderate', 'small', 'blurry', 'soft', 'sharp']);
  assert.deepEqual(strings.filter((x) => !allowed.has(x)), [], 'the stored facts hold no text beyond the schema');
  console.log('unreadable-image: HEIC converted in Chromium, unreadable photos explained, no photo or text leaves for the store');
} finally {
  await browser.close();
}
