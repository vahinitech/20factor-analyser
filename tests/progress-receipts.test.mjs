/* SPDX-License-Identifier: AGPL-3.0-only */
// The saved checks in the browser (frontend/src/report/progress.js) and the
// receipts of stored reports (backend/report_store.py): a check keeps only a
// well-formed receipt, "forget" deletes the stored reports it names, a new
// check renews the earlier ones, and a progress file is read field by field.
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { runSource } from './run-source.mjs';

// Values made inside the page's own context have its prototypes: compare
// plain copies.
const plain = v => JSON.parse(JSON.stringify(v));
const eq = (a, b) => assert.deepEqual(plain(a), plain(b));

const ID = 'a'.repeat(32);
const TOKEN = 'b'.repeat(43);

function page(){
  const items = new Map();
  const calls = [];
  const context = {
    URL, JSON, Date, Number, Object, Array, Set, Math, String,
    location: { href: 'https://vahinitech.com/analyser/analyser.html' },
    localStorage: {
      getItem: k => (items.has(k) ? items.get(k) : null),
      setItem: (k, v) => { items.set(k, String(v)); },
    },
    fetch: (url, opts) => { calls.push({ url: String(url), opts }); return Promise.resolve({ ok: true }); },
    VahiniI18n: { language: () => 'en', translator: () => key => key },
  };
  context.window = context;
  vm.createContext(context);
  runSource('frontend/src/report/progress.js', context);
  return { P: context.VahiniProgress, calls, items };
}

const results = [{ n: 1, score: 7.2 }, { n: 5, score: 6.1 }, { n: 8, unmeasured: true, score: 0 }];
const sections = [{ id: 'structure', avg100: 70 }, { id: 'other', avg100: 10 }];

{
  const { P } = page();
  P.receiptFor({ id: ID, token: TOKEN, expires: '2027-10-21', name: 'Vahini' });
  const entry = P.entryFrom('Vahini', 68, sections, results, { exercises: { 4: ['strokes.ovals'] } });
  eq(entry.receipt, { id: ID, token: TOKEN, expires: '2027-10-21' });
  eq(entry.factors, [{ n: 1, score: 7.2 }, { n: 5, score: 6.1 }]);
  eq(entry.sections, [{ id: 'structure', avg100: 70 }]);
  assert.ok(P.save(entry));
  assert.equal(P.last('VAHINI').receipt.id, ID);
  // The receipt belongs to one check only.
  assert.equal(P.entryFrom('Vahini', 70, [], results).receipt, undefined);
  console.log('PASS a check keeps its receipt, and only that check');
}

{
  const { P } = page();
  for (const bad of [{ id: 'x', token: TOKEN }, { id: ID, token: 'short' }, null, 'receipt']) {
    P.receiptFor(bad);
    assert.equal(P.entryFrom('Bheema', 50, [], results).receipt, undefined);
  }
  const base = { name: 'Bheema', date: '2026-10-21', overall: 50, factors: [{ n: 1, score: 5 }] };
  assert.equal(P.clean({ ...base, receipt: { id: ID, token: 'nope' } }), null);
  assert.equal(P.clean({ ...base, factors: [{ n: 1, score: 5 }, { n: 1, score: 6 }] }), null);
  assert.equal(P.clean({ ...base, sections: [{ id: 'structure', avg100: 150 }] }), null);
  assert.equal(P.clean({ ...base, practice: { exercises: { 4: ['Not An Id'] } } }), null);
  assert.equal(P.clean({ ...base, date: 'yesterday' }), null);
  eq(P.clean({ ...base, extra: 'dropped' }), base);
  console.log('PASS a malformed receipt or entry is refused, unknown fields dropped');
}

{
  const { P, calls } = page();
  P.save(P.clean({ name: 'Pihu', date: '2026-09-01', overall: 60, factors: [{ n: 1, score: 6 }], receipt: { id: ID, token: TOKEN } }));
  P.save(P.clean({ name: 'Tara', date: '2026-09-02', overall: 61, factors: [{ n: 1, score: 6 }] }));
  P.renew('https://stage.vahinitech.com/report-python');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://stage.vahinitech.com/api/v2/reports/renew');
  eq(JSON.parse(calls[0].opts.body), { receipts: [{ id: ID, token: TOKEN }] });
  assert.ok(P.forget('pihu'));
  assert.equal(calls.length, 2);
  assert.equal(calls[1].url, `https://stage.vahinitech.com/api/v2/reports/${ID}`);
  assert.equal(calls[1].opts.method, 'DELETE');
  assert.equal(calls[1].opts.headers['X-Report-Token'], TOKEN);
  assert.equal(P.forName('Pihu').length, 0);
  assert.equal(P.forName('Tara').length, 1);
  console.log('PASS a new check renews stored reports; forget deletes them on the same host');
}

{
  const { P } = page();
  P.save(P.clean({ name: 'Chinnu', date: '2026-09-01', overall: 55, factors: [{ n: 5, score: 5.5 }], receipt: { id: ID, token: TOKEN } }));
  const file = JSON.stringify(P.exportFile('Chinnu'));
  const { P: other } = page();
  const checks = other.readFile(file);
  assert.equal(checks[0].receipt.id, ID);
  assert.equal(other.merge(checks), 1);
  assert.equal(other.merge(checks), 0);
  assert.throws(() => other.readFile('not json'), /pp\.file\.not/);
  assert.throws(() => other.readFile(JSON.stringify({ format: 'vahini-progress', version: 1, checks: [{}] })), /pp\.file\.unreadable/);
  const cmp = other.compare({ factors: [{ n: 5, score: 6 }] }, checks[0]);
  assert.equal(cmp[0].kind, 'up');
  console.log('PASS a progress file carries receipts and merges without repeats');
}
