// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// What the shared PDF carries for the Pro comparison (owner, 2026-10-16;
// frontend/src/report/report-share.js): the stored report's receipt in the
// XMP metadata and the page photo, at most 1600 px, as an embedded file.
// The printed PDF stays exactly two A4 pages, nothing names the child, the
// photo carries no camera data, a sample run embeds nothing, and making the
// file still sends nothing to a server. Its document properties (title,
// author, creator, subject) are Vahini's in every print language, the
// subject says Free or Pro, and none carries the typed name. The page
// photo here is drawn on a canvas with the cast's names, never real
// handwriting. Runs the packed bundle (python frontend/build_bundle.py) in
// Chromium on a free port.
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { readFileSync, readdirSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright';
import { useDesign } from './design-route.mjs';

const freePort = () => new Promise((resolve, reject) => {
  const s = createServer(); s.once('error', reject);
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)); });
});
const PORT = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', String(PORT), '-a', '127.0.0.1', '-c-1', '-s'], { stdio: 'ignore' });
const results = [];
const add = (ok, name, detail = '') => results.push({ ok: !!ok, name, detail: typeof detail === 'string' ? detail : JSON.stringify(detail) });
const RECEIPT = { id: '0123456789abcdef0123456789abcdef', token: 'Tk_0123456789-abcdefghijklmnopqrstuvwxyzABC',
  read_token: 'Rd_9876543210-ZYXWVUTSRQPONMLKJIHGFEDcbaxyz', expires: '2027-10-16' };
const NAME = 'Bheema Kosuri';

async function waitUp() {
  for (let i = 0; i < 50; i++) {
    try { if ((await fetch(BASE + '/frontend/sample-report.html', { method: 'HEAD' })).ok) return; } catch { /* starting */ }
    await delay(200);
  }
  throw new Error('static server did not start');
}
const pdfPages = buf => (buf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
/* The PDF's XMP packet, and its embedded files as {name: bytes}, read by
   following the catalogue's EmbeddedFiles name tree to each stream. */
function embedded(buf) {
  const s = buf.toString('latin1');
  const obj = n => { const i = s.search(new RegExp(`(^|\\n)${n} 0 obj`)); return i < 0 ? null : i; };
  const xmp = (s.match(/<x:xmpmeta[\s\S]*?<\/x:xmpmeta>/) || [''])[0];
  const files = {};
  const tree = s.match(/\/EmbeddedFiles\s*<<\s*\/Names\s*\[([^\]]*)\]/);
  for (const [, name, ref] of tree ? tree[1].matchAll(/\((.*?)\)\s*(\d+) 0 R/g) : []) {
    const specAt = obj(ref);
    const spec = s.slice(specAt, s.indexOf('endobj', specAt));
    const at = obj(spec.match(/\/EF\s*<<\s*\/F (\d+) 0 R/)[1]);
    const head = s.slice(at, s.indexOf('stream', at));
    const len = +head.match(/\/Length (\d+)/)[1];
    const start = s.indexOf('stream', at) + 'stream\n'.length;
    files[name] = { spec, head, bytes: buf.subarray(start, start + len), size: +(head.match(/\/Size (\d+)/) || [])[1] };
  }
  return { xmp, files, text: s };
}
/* The PDF's Info dictionary as {key: text}, found through the trailer's
   /Info reference. Literal and hex strings are both read; a string that
   starts with the FE FF mark is UTF-16BE, any other PDFDocEncoding,
   which agrees with Latin-1 for every character jsPDF writes here. */
function pdfInfo(buf) {
  const s = buf.toString('latin1');
  const ref = [...s.matchAll(/\/Info (\d+) 0 R/g)].at(-1)?.[1];
  if (!ref) return null;
  const at = s.search(new RegExp(`(^|\\n)${ref} 0 obj`));
  const body = s.slice(at, s.indexOf('endobj', at));
  const ESC = { n: '\n', r: '\r', t: '\t', b: '\b', f: '\f' };
  const bytes = raw => raw[0] === '<'
    ? Buffer.from(raw.slice(1, -1).replace(/\s/g, ''), 'hex')
    : Buffer.from(raw.slice(1, -1).replace(/\\(\r\n|\n|[0-7]{1,3}|[\s\S])/g, (_, c) =>
      /^\r?\n$/.test(c) ? '' : /^[0-7]/.test(c) ? String.fromCharCode(parseInt(c, 8)) : ESC[c] ?? c), 'latin1');
  const out = {};
  for (const [, key, raw] of body.matchAll(/\/(\w+)\s*(\((?:\\[\s\S]|[^\\)])*\)|<[0-9A-Fa-f\s]*>)/g)) {
    const b = bytes(raw);
    out[key] = b[0] === 0xfe && b[1] === 0xff ? Buffer.from(b.subarray(2)).swap16().toString('utf16le') : b.toString('latin1');
  }
  return out;
}
/* What may be there: the four properties report-share.js sets (title,
   author, creator, subject) and the three jsPDF adds (producer and the
   dates). Any other key is a new place a name could go. */
const INFO_KEYS = ['Title', 'Author', 'Creator', 'Subject', 'Producer', 'CreationDate', 'ModDate'];
const META = { Title: 'Vahini handwriting snapshot', Author: 'Vahini Technologies · vahinitech.com', Creator: 'Vahini Technologies · vahinitech.com' };
const SUBJECTS = { free: 'Free handwriting review', pro: 'Handwriting review' };

async function share(page) {
  const [download] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), page.click('#share-pdf')]);
  return readFileSync(await download.path());
}

try {
  await waitUp();
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1200, height: 1000 } });
  const page = await context.newPage();
  await useDesign(page);
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  const requests = []; page.on('request', r => requests.push([r.method(), r.url()]));
  await page.addInitScript(() => { window.open = () => null; Object.defineProperty(navigator, 'canShare', { value: undefined, configurable: true }); });
  await page.goto(BASE + '/frontend/sample-report.html?example=free', { waitUntil: 'load' });
  await page.waitForSelector('#report-host .practice-page');

  // A sample run (or a page that never set a check) embeds nothing.
  const plain = embedded(await share(page));
  add(!/vahinitech\.com\/ns\/report-pdf/.test(plain.xmp) && !Object.keys(plain.files).length && !/\/EmbeddedFiles/.test(plain.text),
    'Without a check, the PDF carries no receipt and no photo', { xmp: plain.xmp.slice(0, 80), files: Object.keys(plain.files) });

  // A family's check: a 2400 x 3200 page photo and the stored report's receipt.
  await page.evaluate(({ receipt, name }) => {
    const d = window.VAHINI_SAMPLE_REPORT;
    const analysis = { ...d.analysis, access: { tier: 'free' }, results: d.analysis.results.filter(f => [1, 5, 7, 8, 18].includes(f.n)) };
    VahiniReport.render(document.getElementById('report-host'), { analysis, intake: { writerName: name }, crops: d.factor_regions || {}, detURL: d.photo, history: null });
    const c = document.createElement('canvas'); c.width = 2400; c.height = 3200;
    const g = c.getContext('2d');
    g.fillStyle = '#fbfaf5'; g.fillRect(0, 0, c.width, c.height);
    g.fillStyle = '#1f2a44'; g.font = '120px serif';
    ['Bheema and Pihu', 'went to the market', 'with little Vahini.'].forEach((t, i) => {
      g.save(); g.translate(240, 520 + i * 360); g.rotate((i - 1) * 0.02); g.fillText(t, 0, 0); g.restore();
    });
    VahiniReportShare.setCheck({ receipt, image: c });
  }, { receipt: RECEIPT, name: NAME });
  const before = requests.length;
  const file = await share(page);
  const after = requests.slice(before);
  const got = embedded(file);
  add(file.subarray(0, 5).toString() === '%PDF-' && pdfPages(file) === 2, 'The PDF still prints exactly two pages', { pages: pdfPages(file) });
  add(got.xmp.includes('xmlns:vahini="https://vahinitech.com/ns/report-pdf/1/"')
    && got.xmp.includes(`<vahini:receiptId>${RECEIPT.id}</vahini:receiptId>`)
    && got.xmp.includes(`<vahini:receiptToken>${RECEIPT.read_token}</vahini:receiptToken>`)
    && got.xmp.includes('<vahini:photo>vahini-page.jpg</vahini:photo>'),
    'The XMP metadata holds the read-only receipt and names the embedded photo', got.xmp);
  add(!file.includes(Buffer.from(RECEIPT.token)),
    'The full token, which can delete the record, is nowhere in the PDF');
  add(/\/Metadata \d+ 0 R/.test(got.text), 'The catalogue points at the XMP metadata');
  add(!got.xmp.includes(RECEIPT.expires) && !/expires/.test(got.xmp), 'Only the id and token go in, not the expiry date');
  const photo = got.files['vahini-page.jpg'];
  add(photo && /\/Type \/EmbeddedFile/.test(photo.head) && /\/Subtype \/image#2Fjpeg/.test(photo.head) && /\/AFRelationship \/Data/.test(photo.spec),
    'The page photo is an embedded file, image/jpeg, related as data', photo && { head: photo.head, spec: photo.spec });
  add(photo && photo.bytes.length === photo.size && photo.bytes[0] === 0xff && photo.bytes[1] === 0xd8
    && photo.bytes[photo.bytes.length - 2] === 0xff && photo.bytes[photo.bytes.length - 1] === 0xd9,
    'The embedded bytes are one whole JPEG of the declared size', photo && { len: photo.bytes.length, size: photo.size });
  const dims = photo && await page.evaluate(async b64 => {
    const img = new Image(); img.src = 'data:image/jpeg;base64,' + b64; await img.decode();
    return { w: img.naturalWidth, h: img.naturalHeight };
  }, photo.bytes.toString('base64'));
  add(dims && dims.w === 1200 && dims.h === 1600, 'The photo is scaled to 1600 px on its long side, uncropped', dims);
  add(photo && photo.bytes.length < 600 * 1024, 'The photo adds well under 600 KB', photo && photo.bytes.length);
  add(photo && !photo.bytes.includes(Buffer.from('Exif')), 'The photo is re-encoded, with no camera data');
  // Nothing names the child: not the metadata, the file specification or the Info dictionary.
  const outsideImages = got.xmp + (photo ? photo.spec + photo.head : '') + (got.text.match(/\/Title[\s\S]*?\/Creator \([^)]*\)/) || [''])[0];
  add(!/Bheema|Kosuri/.test(outsideImages), 'No embedded data names the child', outsideImages.slice(0, 400));
  add(after.every(([m, u]) => m === 'GET' && u.startsWith(BASE)) && !after.some(([, u]) => /persist|\/api\/|\/ocr|report-python/.test(u)),
    'Making the PDF with the receipt and photo sends nothing to a server', after);

  // A malformed receipt is left out; the photo still goes in.
  await page.evaluate(() => {
    const c = document.createElement('canvas'); c.width = 800; c.height = 600;
    c.getContext('2d').fillRect(0, 0, 10, 10);
    VahiniReportShare.setCheck({ receipt: { id: 'not-an-id', token: '<x>' }, image: c });
  });
  const badFile = await share(page);
  const bad = embedded(badFile);
  add(!/receipt/.test(bad.xmp) && bad.files['vahini-page.jpg'] && pdfPages(badFile) === 2,
    'A malformed receipt is not embedded; the photo still is', bad.xmp);
  // A receipt with no read-only token is left out too, never the full one.
  await page.evaluate(receipt => {
    const c = document.createElement('canvas'); c.width = 800; c.height = 600;
    c.getContext('2d').fillRect(0, 0, 10, 10);
    VahiniReportShare.setCheck({ receipt: { id: receipt.id, token: receipt.token }, image: c });
  }, RECEIPT);
  const fullFile = await share(page);
  add(!/receipt/.test(embedded(fullFile).xmp) && !fullFile.includes(Buffer.from(RECEIPT.token)),
    'Without a read-only token no receipt is embedded', embedded(fullFile).xmp);

  // The document properties are the brand's, the same in every print
  // language, with the subject telling a Free review from a Pro one, and
  // none of them carries the name the family typed (owner, 2026-10-11).
  // Each PDF here carries the receipt and photo, as a family's share does.
  for (const tier of ['free', 'pro']) for (const lang of ['en', 'te']) {
    const shown = await page.evaluate(({ tier, lang, receipt, name }) => {
      const d = window.VAHINI_SAMPLE_REPORT;
      const results = tier === 'free' ? d.analysis.results.filter(f => [1, 5, 7, 8, 18].includes(f.n)) : d.analysis.results;
      VahiniReport.render(document.getElementById('report-host'), { analysis: { ...d.analysis, access: { tier }, results },
        intake: { writerName: name }, crops: d.factor_regions || {}, detURL: d.photo, history: null });
      VahiniReportShare.applyLanguage(lang);
      const c = document.createElement('canvas'); c.width = 800; c.height = 600;
      c.getContext('2d').fillRect(0, 0, 10, 10);
      VahiniReportShare.setCheck({ receipt, image: c });
      const host = document.getElementById('report-host');
      return { lang: host.getAttribute('lang'), pro: !!host.querySelector('.practice-pro'), named: host.textContent.includes(name.split(' ')[0]) };
    }, { tier, lang, receipt: RECEIPT, name: NAME });
    const info = pdfInfo(await share(page)) || {};
    const label = `${tier === 'pro' ? 'Pro' : 'Free'} report printed in ${lang}`;
    add(shown.lang === lang && shown.pro === (tier === 'pro') && shown.named,
      `${label}: the report on screen is ${tier}, in ${lang}, and shows the typed name`, shown);
    add(info.Title === META.Title && info.Author === META.Author && info.Creator === META.Creator,
      `${label}: the PDF's title, author and creator are exactly Vahini's`, info);
    add(info.Subject === SUBJECTS[tier], `${label}: the subject is "${SUBJECTS[tier]}"`, info);
    add(Object.keys(info).every(k => INFO_KEYS.includes(k)) && !Object.values(info).some(v => /Bheema|Kosuri/.test(v)),
      `${label}: no document property names the child`, info);
  }
  await page.evaluate(() => VahiniReportShare.applyLanguage('en'));
  add(!errors.length, 'No page errors', errors);

  // The receipt survives expanding the compact report, so app.js can hand
  // it to the share button (ocr.js serverPythonReport).
  const app = await context.newPage();
  const catalogFile = readdirSync('backend/catalogs').find(n => n.endsWith('.json'));
  const catalog = JSON.parse(readFileSync('backend/catalogs/' + catalogFile, 'utf8'));
  await app.route('**/health', r => r.fulfill({ json: { ok: true } }));
  await app.route('**/api/v2/me', r => r.fulfill({ json: { access: { tier: 'free' } } }));
  await app.route('**/api/v2/catalog/**', r => r.fulfill({ json: catalog }));
  await app.route('**/api/v2/reports/renew', r => r.fulfill({ json: { renewed: 0 } }));
  await app.route('**/api/v2/reports?**', r => r.fulfill({ json: { schema_version: '2.1', format: 'compact', catalog_version: catalog.version, ok: true,
    access: { tier: 'free' }, summary: { score: 60 }, factors: [1, 5, 7, 8, 18].map(n => ({ n, s: 6, st: 'e' })), receipt: RECEIPT } }));
  await app.goto(BASE + '/frontend/analyser.html', { waitUntil: 'networkidle' });
  const report = await app.evaluate(() => VahiniOCR.serverPythonReport(new Blob(['x']), ''));
  add(report && report.analysis && report.receipt && report.receipt.id === RECEIPT.id && report.receipt.token === RECEIPT.token,
    'The expanded report keeps its receipt for the shared PDF', report && report.receipt);
  // The browser's saved check keeps the full token (it renews and deletes).
  const saved = await app.evaluate(() => VahiniProgress.entryFrom('Bheema', 60, [], [], null));
  add(saved && saved.receipt && saved.receipt.token === RECEIPT.token && !('read_token' in saved.receipt),
    'The saved check keeps the full token, not the read-only one', saved && saved.receipt);
  await browser.close();
} catch (e) {
  add(false, 'test run', e.stack || String(e));
} finally {
  server.kill();
}
let failed = 0;
for (const r of results) {
  if (!r.ok) failed++;
  console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.ok || !r.detail ? '' : '\n      ' + r.detail}`);
}
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
