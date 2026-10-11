/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Choosing the practice a report prints (docs/PRACTICE-FRAMEWORK.md,
   "Many-to-many selection"). Every exercise and tip in the catalogue says
   which skills it helps (helps: {factor: weight}, its own factor 1.0).

   need[f]   = max(0, 8.5 - score) x reliability (measured 1.0, else 0.6);
               a composite (18, 20) passes its need to the factors it is
               made of, by their weights in backend/scoring.py.
   value(e)  = sum of helps[f] x need[f], minus REPEAT_PENALTY when the
               entry was printed last time (rotation through the history
               saved in this browser), minus LEVEL_COST for each level
               above 1 (a child starts with the first exercises).
   Rows are the report's flagged skills. The first focus picks first, then
   the row with the most need left. Each row takes candidates only from
   its own skill's list, so every printed entry's highest-weight factor
   is a flagged skill. After a pick, each skill it helps keeps
   (1 - weight / 2) of its need, so the next pick goes after what is left.
   Ties go to the lower level, then catalogue order: the same report
   always picks the same practice.
   Tries a day come from the weakest measured skill the exercise helps.
   ========================================================================= */
(function (global) {
'use strict';
const TARGET = 8.5;
const REPEAT_PENALTY = 100;
const LEVEL_COST = 0.75;
/* Must track backend/scoring.py (s[18], s[20] _blend weights);
   backend/tests/test_practice_catalog.py checks it. */
const COMPOSITES = {
  18: { 1:0.35, 5:0.25, 8:0.20, 7:0.20 },
  20: { 5:0.30, 8:0.20, 10:0.20, 11:0.15, 17:0.15 },
};
const bandOf = s=> s>=8.5?'strong' : s>=7.0?'good' : s>=4.5?'dev' : 'focus';

function reliability(f){
  return f && (f.conf === 'measured' || f.imuMeasured === true) ? 1 : 0.6;
}
/* Need per factor number, from the report's measured skills. */
function needs(measured){
  const need = {};
  measured.forEach(f=>{ need[f.n] = Math.max(0, TARGET - f.score) * reliability(f); });
  Object.entries(COMPOSITES).forEach(([c, parts])=>{
    const own = need[c];
    if (!own) return;
    const live = Object.entries(parts).filter(([n])=>n in need);
    const sum = live.reduce((s, [, w])=>s + w, 0);
    live.forEach(([n, w])=>{ need[n] += own * w / sum; });
    need[c] = 0;
  });
  return need;
}
function helpsOf(entry, own){
  const h = entry && entry.helps;
  if (h && typeof h === 'object' && Object.keys(h).length) return h;
  return own ? { [own]: 1 } : {};
}
function value(entry, need, own){
  return Object.entries(helpsOf(entry, own)).reduce((s, [n, w])=>s + w * (need[n] || 0), 0);
}
function damp(need, entry, own){
  Object.entries(helpsOf(entry, own)).forEach(([n, w])=>{ if (need[n]) need[n] *= 1 - w / 2; });
}
/* Greedy pick of up to count entries from list. */
function pick(list, count, need, own, printedBefore){
  const pool = list.map((e, i)=>({ e, i }));
  const out = [];
  while (out.length < count && pool.length){
    let best = 0, bestScore = -Infinity;
    pool.forEach((c, k)=>{
      const s = value(c.e, need, own) - (printedBefore.has(c.e.id) ? REPEAT_PENALTY : 0) - LEVEL_COST * Math.max(0, (c.e.level || 1) - 1);
      const b = pool[best].e;
      if (s > bestScore + 1e-9 || (Math.abs(s - bestScore) <= 1e-9 &&
          ((c.e.level || 0) < (b.level || 0) || ((c.e.level || 0) === (b.level || 0) && c.i < pool[best].i)))){
        best = k; bestScore = s;
      }
    });
    const [chosen] = pool.splice(best, 1);
    out.push(chosen.e);
    damp(need, chosen.e, own);
  }
  return out;
}
/* The weakest measured skill an exercise helps sets its band (tries). */
function triesBand(entry, own, scoreOf){
  const scores = Object.keys(helpsOf(entry, own)).map(n=>scoreOf[n]).filter(Number.isFinite);
  return scores.length ? bandOf(Math.min(...scores)) : null;
}
/* opts: {rows: flagged factors in display order (first focus first),
          measured: every measured factor, cat, limits, latin,
          last: {exercises:{n:[ids]}, tips:{n:[ids]}}}
   returns {rows: [{f, exercises:[{entry, band}], tips:[entry], band}],
            printed: {exercises:{n:[ids]}, tips:{n:[ids]}}} */
function select(opts){
  const { rows, measured, cat, limits, latin } = opts;
  const last = opts.last || {};
  const flat = m=>new Set(Object.values(m || {}).flat());
  const before = { exercises: flat(last.exercises), tips: flat(last.tips) };
  const scoreOf = Object.fromEntries(measured.map(f=>[f.n, f.score]));
  const area = f=>(cat && cat.factors && cat.factors[String(f.n)]) || { exercises: [], tips: [] };
  const dose = band=>(cat && cat.dosage && cat.dosage[band]) || null;
  const out = rows.map(f=>({ f, exercises: [], tips: [], band: bandOf(f.score) }));
  const printed = { exercises: {}, tips: {} };
  const run = (kind, wanted)=>{
    const need = needs(measured);
    const left = out.slice();
    while (left.length){
      // The first focus first, then the row with the most need left.
      let k = 0;
      if (left[0] !== out[0]) {
        left.forEach((r, j)=>{ if ((need[r.f.n] || 0) > (need[left[k].f.n] || 0) + 1e-9) k = j; });
      }
      const [row] = left.splice(k, 1);
      const list = (area(row.f)[kind] || []).filter(e=>kind === 'tips' || (e.needs !== 'pen' && (latin || e.script !== 'latin')));
      const chosen = pick(list, wanted(row), need, row.f.n, before[kind]);
      row[kind] = kind === 'exercises' ? chosen.map(e=>({ entry: e, band: triesBand(e, row.f.n, scoreOf) || row.band })) : chosen;
      printed[kind][row.f.n] = chosen.map(e=>e.id);
    }
  };
  run('exercises', row=>Math.min((dose(row.band) || {}).exercises ?? 1, limits.exercises_max));
  run('tips', ()=>limits.tips_max);
  // A row's plan follows its weakest exercise.
  out.forEach(r=>{
    const order = ['focus', 'dev', 'good', 'strong'];
    r.planBand = r.exercises.reduce((b, x)=>order.indexOf(x.band) < order.indexOf(b) ? x.band : b, r.band);
  });
  return { rows: out, printed };
}

global.VahiniPracticeSelect = { select, needs, value, pick, triesBand, reliability, bandOf, COMPOSITES, TARGET, REPEAT_PENALTY, LEVEL_COST };
})(typeof window !== 'undefined' ? window : globalThis);
