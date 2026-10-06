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
assert.deepEqual(pub, ['/health']);
console.log('PASS public host probes same-origin /health only');

const local = await probedUrls('localhost');
assert.deepEqual(local, ['/health', 'http://127.0.0.1:8080/health']);
console.log('PASS localhost also probes the loopback helper server');
