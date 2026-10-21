/* SPDX-License-Identifier: AGPL-3.0-only */
// A stored report's receipt (backend/report_store.py) travels from the
// server's answer to the saved checks (progress.js), renews the earlier
// receipts on the same host, and stays on the expanded report for the
// shared PDF. With no receipt, nothing is renewed.
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { runSource } from './run-source.mjs';

const RECEIPT = { id: 'c'.repeat(32), token: 'd'.repeat(43), expires: '2027-10-21' };

async function check(answer){
  const progress = { receipts: [], renewed: [] };
  const context = {
    AbortController, setTimeout, clearTimeout, FormData, Blob, performance,
    location: { hostname: 'vahinitech.com', href: 'https://vahinitech.com/analyser/analyser.html' },
    VahiniAccount: { request: async url => ({ url, options: {} }), hasKey: () => false },
    VahiniCompact: { expand: async () => ({ ok: true, analysis: { results: [] } }) },
    VahiniProgress: {
      receiptFor: r => progress.receipts.push(r === undefined ? null : r),
      renew: url => progress.renewed.push(url),
    },
    fetch: async () => ({ ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(answer) }),
  };
  context.window = context;
  vm.createContext(context);
  runSource('frontend/src/engine/ocr.js', context);
  const report = await context.VahiniOCR.serverPythonReport(new Blob(['page']), '');
  return { report, progress };
}

{
  const { report, progress } = await check({ format: 'compact', receipt: RECEIPT });
  assert.equal(progress.receipts.length, 1);
  assert.equal(progress.receipts[0].id, RECEIPT.id);
  assert.equal(progress.renewed.length, 1);
  assert.match(progress.renewed[0], /\/api\/v2\/reports\?format=compact/);
  assert.equal(report.receipt.id, RECEIPT.id);
  console.log('PASS the receipt reaches the saved checks, renews earlier ones and stays on the report');
}

{
  const { report, progress } = await check({ format: 'compact' });
  assert.equal(progress.receipts.length, 1);
  assert.equal(progress.receipts[0], null);
  assert.equal(progress.renewed.length, 0);
  assert.equal(report.receipt, undefined);
  console.log('PASS without a receipt nothing is renewed or added');
}
