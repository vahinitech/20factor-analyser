/* SPDX-License-Identifier: AGPL-3.0-only */
// Many-to-many practice selection (docs/PRACTICE-FRAMEWORK.md, "Many-to-many
// selection"): need per skill, composites passing their need on, the same
// report always picking the same practice, rotation through last time's
// ids, tier limits, tries from the row's own skill, and every
// printed entry's highest-weight factor being a skill the report flags.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const window = {};
vm.runInContext(fs.readFileSync('frontend/src/report/practice-select.js', 'utf8'), vm.createContext({ window }));
const S = window.VahiniPracticeSelect;

// The catalogue version that serves the practice catalogue today: the one
// docs/PRACTICE-MAP.md names (generated, and checked current by CI).
const current = fs.readFileSync('docs/PRACTICE-MAP.md', 'utf8').match(/catalogue version `([0-9a-f]+)`/)[1];
const served = JSON.parse(fs.readFileSync(`backend/catalogs/${current}.json`, 'utf8'));
assert.ok(served.factors.every(x => x.exercises.every(e => e.helps)), 'the current catalogue says what each exercise helps');
const cat = { ...served.practice, factors: Object.fromEntries(served.factors.map(f => [String(f.n), { exercises: f.exercises, tips: f.tips }])) };

const f = (n, score, conf = 'measured') => ({ n, score, conf });
const FREE = [f(1, 7.5), f(5, 5.0), f(7, 7.1), f(8, 5.6), f(18, 6.4)];
const rowsOf = measured => measured.filter(x => ![18, 20].includes(x.n) && x.score < 8.5).sort((a, b) => a.score - b.score || a.n - b.n).slice(0, 3);
const run = (measured, limits, last) => S.select({ rows: rowsOf(measured), measured, cat, limits, latin: true, last });
const FREE_LIMITS = cat.tiers.free, PRO_LIMITS = cat.tiers.pro;

// Need: 8.5 minus the score, times reliability; 18 passes its need on.
const need = S.needs(FREE);
assert.equal(need[18], 0, 'a composite keeps none of its need');
const own18 = 8.5 - 6.4;
assert.ok(Math.abs(need[5] - (3.5 + own18 * 0.25)) < 1e-9, 'letter size gets its share of legibility');
assert.ok(Math.abs(need[1] - (1.0 + own18 * 0.35)) < 1e-9);
assert.ok(Math.abs(S.needs([f(5, 5.0, 'estimated')])[5] - 3.5 * 0.6) < 1e-9, 'an estimate counts 0.6');
assert.equal(S.needs([f(3, 9.1)])[3], 0, 'a strong skill needs nothing');

// Determinism: the same report picks the same practice.
const a = run(FREE, FREE_LIMITS), b = run(FREE, FREE_LIMITS);
assert.deepEqual(a.printed, b.printed);
assert.equal(a.rows[0].exercises[0].entry.id, 'size.two-line-ladder', 'the first focus starts with the two-line ladder');

// Every printed entry's highest-weight factor is a flagged skill.
for (const [label, measured, limits] of [['free', FREE, FREE_LIMITS], ['pro', served.factors.filter(x => ![13, 14, 15, 16].includes(x.n)).map((x, i) => f(x.n, [7.5, 9.2, 10, 6.4, 5.0, 6.0, 7.1, 5.6, 8.7, 7.1, 7.7, 8.4, 8.6, 6.4, 8.1, 6.5][i])), PRO_LIMITS]]) {
  const r = run(measured, limits);
  const flagged = new Set(r.rows.map(x => x.f.n));
  for (const row of r.rows) {
    for (const entry of [...row.exercises.map(x => x.entry), ...row.tips]) {
      const top = Object.entries(entry.helps).sort((x, y) => y[1] - x[1])[0][0];
      assert.ok(flagged.has(Number(top)), `${label}: ${entry.id} develops a flagged skill`);
      assert.equal(Number(top), row.f.n, `${label}: ${entry.id} sits under its own skill`);
    }
    // Tier limits.
    assert.ok(row.exercises.length <= limits.exercises_max, `${label}: exercises within the tier`);
    assert.ok(row.tips.length <= limits.tips_max, `${label}: tips within the tier`);
  }
  assert.ok(r.rows.length <= limits.areas_max, `${label}: skills within the tier`);
}
const pro = run(FREE, PRO_LIMITS);
assert.ok(pro.rows.some(r => r.exercises.length === 2), 'Pro can show two exercises for a skill');
assert.ok(a.rows.every(r => r.exercises.length === 1 && r.tips.length === 1), 'Free shows one of each');

// Rotation: last time's exercise is not printed again while another exists.
const again = run(FREE, FREE_LIMITS, a.printed);
for (const row of again.rows) {
  const before = a.printed.exercises[row.f.n];
  assert.notDeepEqual(again.printed.exercises[row.f.n], before, `skill ${row.f.n} moves on at a re-check`);
}
const third = run(FREE, FREE_LIMITS, again.printed);
assert.deepEqual(third.printed.exercises[5].length, 1);

// Many-to-many: with tall letters also measured and low, the ladder (which
// helps them at 0.6) wins over another letter-size exercise that does not.
const withTall = [...FREE, f(6, 4.0)];
const r6 = S.select({ rows: [f(5, 5.0)], measured: withTall, cat, limits: FREE_LIMITS, latin: true });
assert.equal(r6.rows[0].exercises[0].entry.id, 'size.two-line-ladder');
assert.ok(S.value(cat.factors['5'].exercises[0], S.needs(withTall), 5) > S.value(cat.factors['5'].exercises[0], S.needs(FREE), 5), 'help to another weak skill adds value');

// Tries follow the row's own skill (owner, 2026-10-11): a Mastering row
// asks 5 a day even when its exercise also helps a Learning skill.
const ownBand = S.select({ rows: [f(7, 7.1)], measured: [f(7, 7.1), f(5, 3.0)], cat, limits: FREE_LIMITS, latin: true });
const helpsWeaker = ownBand.rows[0].exercises[0].entry;
assert.ok(Object.keys(helpsWeaker.helps).includes('5'), 'the chosen exercise also helps letter size');
assert.equal(ownBand.rows[0].exercises[0].band, 'good');
assert.equal(ownBand.rows[0].planBand, 'good');
assert.equal(S.triesBand, undefined, 'no tries from the weakest helped skill');

// Latin-only exercises are skipped on a page in another script.
const nonLatin = S.select({ rows: [f(19, 4.0)], measured: [f(19, 4.0)], cat, limits: PRO_LIMITS, latin: false });
assert.ok(nonLatin.rows[0].exercises.every(x => x.entry.script !== 'latin'));

console.log('practice selection: need, composites, determinism, rotation, tier limits and flagged skills');
