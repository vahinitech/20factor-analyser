/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini Growth Forecast — innovative, transparent prediction layer.
   From the measured factor scores (+ optional IMU dynamics) it projects:
     • expected score uplift after the prescribed practice (8-week curve)
     • time to "fast & efficient / fluent" handwriting
     • a writing-speed (wpm) estimate, now vs projected
   All outputs are ESTIMATES that assume consistent practice — framed as such.
   Model: each factor approaches a realistic ceiling along an exponential
   learning curve s(w) = s0 + (ceiling - s0)·(1 - e^(-r·w)).
   ========================================================================= */
(function (global) {
'use strict';
const mean = (a)=> a.length ? a.reduce((s,x)=>s+x,0)/a.length : 0;
const clamp = (v,lo,hi)=> Math.max(lo, Math.min(hi, v));

const RATE = 0.30;                 // learning rate per week
const HORIZON = 8;                 // weeks shown
const FLUENT = 80;                 // maturity % = "fast & efficient"

// realistic reachable score after sustained practice (weak factors gain most)
function ceilingOf(s0){ return Math.min(9.3, s0 + Math.max(1.0, (8.6 - s0) * 0.85)); }
function projScore(s0, w){ const c=ceilingOf(s0); return s0 + (c - s0) * (1 - Math.exp(-RATE*w)); }

function compute(analysis, imu, pipeline, baseline){
  const byId = {}; analysis.results.forEach(f=>byId[f.n]=f);
  const score = (n)=> byId[n] ? byId[n].score : 6;
  // single source of truth: forecast is baselined off the SAME corrected overall
  // the rest of the report shows (Fix-Spec #6) — not a divergent internal number.
  const base = (baseline!=null ? baseline : analysis.overall);

  // ---- projected OVERALL curve (recompute weighted overall each week) ----
  function overallAt(w){
    let total=0;
    analysis.sections.forEach(s=>{ total += mean(s.factors.map(f=>projScore(f.score,w))) * 10 * s.weight; });
    return Math.round(total);
  }
  // model the UPLIFT shape, then apply it to the real baseline so the curve
  // starts exactly at the reported score.
  const model0 = overallAt(0) || base;
  const curve = [];
  for (let w=0; w<=HORIZON; w++){ curve.push({ w, overall: clamp(Math.round(base + (overallAt(w)-model0)), 0, 100) }); }
  curve[0].overall = base;
  const overallNow = base, overallProj = curve[HORIZON].overall;
  const modelDelta = Math.max(0, overallProj - overallNow);
  // express the projection as a RANGE, not a false-precision point (#6)
  const projLow  = clamp(overallNow + Math.round(modelDelta*0.55), 0, 100);
  const projHigh = clamp(overallNow + Math.round(modelDelta*1.05), 0, 100);

  // ---- maturity / fluency (drivers: consistency + dynamics) --------------
  const consIds = [5,7,9,11,12,17];                    // size, baseline, letter-spacing, line, vertical, slant
  const consMean = mean(consIds.map(score));
  const dynMean  = mean([13,14,15,16].map(score));
  const haveDyn  = !!imu;                               // IMU gives real dynamics
  function maturityAt(w){
    const c = projScore(consMean, w);
    const d = haveDyn ? projScore(dynMean, w) : c*0.9;  // image: dynamics proxied, slight discount
    return clamp((haveDyn ? 0.55*c + 0.45*d : 0.92*c) * 10, 0, 100);
  }
  const maturityNow = Math.round(maturityAt(0));
  const maturityProj = Math.round(maturityAt(HORIZON));
  let weeksToFluent = null;
  for (let w=0; w<=16; w++){ if (maturityAt(w) >= FLUENT){ weeksToFluent = w; break; } }
  const alreadyFluent = maturityNow >= FLUENT;
  const matBand = (m)=> m>=80?'Fast & easy' : m>=62?'Getting smoother' : m>=42?'Starting to flow' : 'Slow & careful — early days';

  // ---- writing speed estimate (wpm) --------------------------------------
  // maturity maps to fluency; fluent hands write faster & more automatically.
  let nowWpm = Math.round(7 + maturityNow/100 * 21);
  let projWpm = Math.round(7 + maturityProj/100 * 21);
  let speedSource = haveDyn ? 'IMU velocity + consistency' : 'writing consistency';
  if (haveDyn && imu.dur > 2 && imu.chars > 3){
    const measured = (imu.chars/5) / (imu.dur/60);      // words ≈ strokes/5
    nowWpm = Math.round(clamp(0.5*nowWpm + 0.5*measured, 5, 40));
    projWpm = Math.max(projWpm, nowWpm + Math.round((maturityProj-maturityNow)/100*18));
  }

  // ---- per-factor uplift (the prescribed weak factors) -------------------
  const weak = analysis.results.filter(f=>f.score<6.5).sort((a,b)=>a.score-b.score).slice(0,5);
  const pool = weak.length ? weak : [...analysis.results].sort((a,b)=>a.score-b.score).slice(0,4);
  const factorUplift = pool.map(f=>({ name:f.name, now:f.score, proj:Math.round(projScore(f.score,HORIZON)*10)/10,
    target: Math.round(ceilingOf(f.score)*10)/10 }));

  return {
    horizon:HORIZON, fluentThreshold:FLUENT,
    overallNow, overallProj, overallDelta: overallProj-overallNow, projLow, projHigh, curve,
    fluency:{ maturityNow, maturityProj, bandNow:matBand(maturityNow), bandProj:matBand(maturityProj),
              weeksToFluent, alreadyFluent, imageOnly: !haveDyn },
    speed:{ nowWpm, projWpm, source:speedSource },
    factorUplift,
    source: haveDyn ? 'imu' : 'image',
  };
}

global.VahiniForecast = { compute };
})(window);
