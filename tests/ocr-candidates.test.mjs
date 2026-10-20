/* SPDX-License-Identifier: AGPL-3.0-only */
// The loopback helper server is a developer convenience. On a public host the
// health probe must never reach for 127.0.0.1 on the visitor's machine.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const src = fs.readFileSync('frontend/src/engine/ocr.js', 'utf8');

async function probedUrls(hostname){
  const urls = [];
  const context = { AbortController, setTimeout, clearTimeout, location: { hostname } };
  context.window = context;
  context.fetch = async url => { urls.push(String(url)); throw new Error('offline'); };
  vm.createContext(context);
  vm.runInContext(src, context);
  const res = await context.VahiniOCR.checkHealth(50);
  assert.equal(res.ok, false);
  return urls;
}

const pub = await probedUrls('vahinitech.com');
assert.deepEqual(pub, ['/ocr/health']);
console.log('PASS public host probes same-origin /ocr/health only');

const local = await probedUrls('localhost');
assert.deepEqual(local, ['/ocr/health', 'http://127.0.0.1:8080/ocr/health']);
console.log('PASS localhost also probes the loopback helper server');

// #34: a proxy's soft 404 (an HTML page with status 200) is not the
// server; only the server's JSON health payload counts as up.
async function probe(reply){
  const context = { AbortController, setTimeout, clearTimeout, location: { hostname: 'vahinitech.com' } };
  context.window = context;
  context.fetch = async () => reply;
  vm.createContext(context);
  vm.runInContext(src, context);
  return context.VahiniOCR.checkHealth(50);
}
const html = { ok: true, json: async () => { throw new SyntaxError('Unexpected token <'); } };
assert.equal((await probe(html)).ok, false);
console.log('PASS an HTML page with status 200 is not the server');

const down = { ok: true, json: async () => ({ ok: false }) };
assert.equal((await probe(down)).ok, false);
console.log('PASS a health payload saying ok:false is down');

const up = { ok: true, json: async () => ({ ok: true, engine: 'pp-ocrv5' }) };
assert.deepEqual({ ...(await probe(up)) }, { ok: true, endpoint: '/ocr/health' });
console.log('PASS the JSON health payload is up');
