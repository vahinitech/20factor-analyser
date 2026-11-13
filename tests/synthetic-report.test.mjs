/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// The browser fixture has stable facts, not borrowed accuracy evidence.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { runSource } from './run-source.mjs';
import { ALL_FACTORS, FREE_FACTORS, SENSOR_FACTORS, catalog, syntheticReport } from './helpers/synthetic-report.mjs';

const context = {};
vm.createContext(context);
runSource('frontend/src/engine/compact-client.js', context);
for (const tier of ['free', 'pro']) {
  const report = syntheticReport(tier);
  assert.deepEqual(report, syntheticReport(tier), `${tier}: repeatable synthetic input`);
  assert.deepEqual(report.factors.map(f => f.n), tier === 'pro' ? ALL_FACTORS : FREE_FACTORS);
  assert.deepEqual([...report.factors.map(f => f.n), ...report.locked].sort((a, b) => a - b), ALL_FACTORS, 'returned and locked factors partition all twenty');
  assert.equal(report.summary.factor_count, report.factors.length);
  assert.equal(report.recognition.backend, 'synthetic-browser-fixture', 'never claim a real OCR engine ran');
  const decoded = context.VahiniCompact.decode(report, catalog);
  assert.equal(decoded.analysis.access.tier, tier);
  assert.deepEqual(JSON.parse(JSON.stringify(decoded.analysis.results.map(f => ({ n: f.n, score: f.score, unmeasured: f.unmeasured })))), report.factors.map(f => ({ n: f.n, score: f.s, unmeasured: f.st === 'u' })));
  assert.deepEqual(Object.keys(report.evidence.factor_regions).map(Number), report.factors.filter(f => f.st !== 'u').map(f => f.n), 'no locked or sensor-only evidence crop');
  assert.equal(decoded.analysis.measuredCount, tier === 'pro' ? 14 : 5);
  for (const f of report.factors) {
    if (SENSOR_FACTORS.includes(f.n)) assert.deepEqual(f, { n: f.n, s: null, st: 'u' });
    else assert.ok(Number.isFinite(f.s) && f.s > 0 && f.s <= 10);
  }
}
assert.deepEqual(SENSOR_FACTORS, [2, 4, 13, 14, 15, 16]);
assert.throws(() => syntheticReport('unknown'));
console.log('PASS synthetic fixture: Free five, Pro twenty, six unavailable sensor-only skills, deterministic decoder facts');
