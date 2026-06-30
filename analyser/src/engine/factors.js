/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini 20-Factor scorer — maps engine metrics to the guide's factors,
   target bands, section weights and role-aware narrative/exercises.
   Bands marked [default] are the guide's engineering starting values.
   ========================================================================= */
(function (global) {
'use strict';
const E = global.VahiniEngine;
const sErr = E.scoreFromError, sCon = E.scoreFromConsistency, mean=E.mean, cv=E.cv, median=E.median, std=E.std;

const clamp10 = v => Math.max(0, Math.min(10, v));
function band(score){ return score>=7.5 ? 'strong' : score>=5 ? 'dev' : 'focus'; }
function pct(x,d){ return (x*100).toFixed(d||0); }

/* Each factor: id, n, section, name, unit, target text, confidence,
   compute(m) -> { score(0-10), value(display), evidence }, tip, exercise(group) */
const SECTIONS = [
  { id:'structure', name:'Structure',          weight:0.30, blurb:'Letter shapes, size & control' },
  { id:'spatial',   name:'Spatial',            weight:0.30, blurb:'Spacing, baseline & layout' },
  { id:'dynamics',  name:'Dynamics',           weight:0.20, blurb:'Speed, pressure & flow (IMU pen)' },
  { id:'style',     name:'Style & Readability',weight:0.20, blurb:'Slant, legibility & neatness' },
];

const FACTORS = [
/* ---------------- Section 1 — Structure (30%) ------------------------- */
{ n:1, sec:'structure', name:'Letter Formation Accuracy', target:'shape dist ≤0.10', conf:'proxy',
  tip:'Slow block-writing drills for the letters that deviate most (a, o, b rows).', ex:'round',
  compute:(m)=>{ // proxy: rounder, consistent blobs => better formation; uses loop + size CV
    const sizePenalty = cv(m.letterHeights);
    const sc = clamp10(10 - sizePenalty*9 + (m.loopRatio-0.85)*4);
    return { score:clamp10(sc), value:'shape match '+pct(Math.max(0,Math.min(1,(sc/10))),0)+'%',
      evidence:'estimated from form regularity (image proxy; reference-glyph match in Phase 2)' }; } },

{ n:2, sec:'structure', name:'Stroke Order Consistency', target:'edit dist ≤2', conf:'imu',
  tip:'Guided stroke-tracing sheets for letters built in the wrong order.', ex:'round',
  compute:(m)=>({ score: clamp10(6 + (m.loopRatio-0.8)*3),
    value:'IMU-pending', evidence:'true stroke order needs the IMU pen (§4B); image gives only a weak proxy' }) },

{ n:3, sec:'structure', name:'Loop Closure', target:'≥95% closed', conf:'measured',
  tip:'Loop drills — rows of oooo and aaaa keeping every counter closed.', ex:'round',
  compute:(m)=>({ score: clamp10(10*m.loopRatio), value:pct(m.loopRatio,0)+'% closed',
    evidence:'interior-hole topology counted across loop-bearing letters (§4C F3)' }) },

{ n:4, sec:'structure', name:'Line Quality (Smoothness)', target:'jitter ≤0.5 px', conf:'measured',
  tip:'Straight-line and curve control drills — llll then cccc, slowly.', ex:'slant',
  compute:(m)=>{ const jitter = cv(m.strokeWidths); // width wobble as smoothness proxy
    return { score: clamp10(sErr(jitter,0.18,0.7)), value:'jitter '+jitter.toFixed(2),
      evidence:'stroke-width deviation along strokes (curvature-variance proxy, §4C F4)' }; } },

{ n:5, sec:'structure', name:'Size Consistency', target:'height CV ≤0.12', conf:'measured',
  tip:'Write inside two guide-lines so every letter reaches the same height.', ex:'round',
  compute:(m)=>{ const c=cv(m.letterHeights);
    return { score: clamp10(sCon(m.letterHeights,0.12,0.45)), value:'CV '+c.toFixed(2),
      evidence:'coefficient of variation of '+m.letterHeights.length+' letter heights (§4C F5)' }; } },

{ n:6, sec:'structure', name:'Ascender / Descender Control', target:'ratio err ≤0.15', conf:'measured',
  tip:'Tall–short pattern drills (bl bl bl) to train ascenders and descenders.', ex:'round',
  compute:(m)=>{ // balance of upper/lower zone presence vs ideal ~ a third each
    const errU=Math.abs(m.zoneUpper-0.30), errL=Math.abs(m.zoneLower-0.25);
    return { score: clamp10(sErr((errU+errL),0.12,0.6)), value:'up '+pct(m.zoneUpper)+'% · low '+pct(m.zoneLower)+'%',
      evidence:'zone occupancy vs expected proportion against fitted baseline (§4C F6)' }; } },

/* ---------------- Section 2 — Spatial (30%) --------------------------- */
{ n:7, sec:'spatial', name:'Baseline Alignment', target:'RMS ≤0.08 x-h', conf:'measured',
  tip:'Underline / baseline tracing on ruled sheets.', ex:'frame',
  compute:(m)=>{ const r=mean(m.baselineRMSnorm);
    return { score: clamp10(sErr(r,0.08,0.40)), value:r.toFixed(2)+' x-h',
      evidence:'RMS deviation from least-squares baseline across '+m.nLines+' line(s) (§4C F7)' }; } },

{ n:8, sec:'spatial', name:'Word Spacing', target:'≈1.0 x-h, CV ≤0.25', conf:'measured',
  tip:'"word␣␣word" spacing drill — one finger gap between words.', ex:'rhythm',
  compute:(m)=>{ const g=m.wordGapNorm; if(g.length<2) return {score:6,value:'n/a',evidence:'too few words to measure'};
    const tErr=Math.abs(mean(g)-1.0);
    const sc=0.5*sErr(tErr,0.2,1.5)+0.5*sCon(g,0.25,0.8);
    return { score: clamp10(sc), value:'mean '+mean(g).toFixed(2)+' x-h',
      evidence:'inter-word gaps vs ~1 x-height, plus their spread (§4C F8)' }; } },

{ n:9, sec:'spatial', name:'Letter Spacing', target:'gap CV ≤0.30', conf:'measured',
  tip:'Spaced-letter slow writing — a matchstick gap between letters.', ex:'rhythm',
  compute:(m)=>{ const g=m.letterGapNorm; if(g.length<2) return {score:6,value:'n/a',evidence:'too few letters'};
    return { score: clamp10(sCon(g,0.30,0.90)), value:'CV '+cv(g).toFixed(2),
      evidence:'consistency of intra-word letter gaps (§4C F9)' }; } },

{ n:10, sec:'spatial', name:'Margin Discipline', target:'left CV ≤0.05', conf:'measured',
  tip:'Margin-box writing — keep an even left edge down the page.', ex:'frame',
  compute:(m)=>{ if(m.leftX.length<2) return {score:6,value:'1 line',evidence:'single line — margin needs multiple lines'};
    const sc=0.6*sCon(m.leftX,0.05,0.25)+0.4*sCon(m.rightX,0.15,0.50);
    return { score: clamp10(sc), value:'left CV '+cv(m.leftX).toFixed(2),
      evidence:'spread of per-line left/right ink positions (§4C F10)' }; } },

{ n:11, sec:'spatial', name:'Line Straightness', target:'drift ≤1°', conf:'measured',
  tip:'Ruled-sheet practice; pause at the right margin to reset to the line.', ex:'frame',
  compute:(m)=>{ const d=mean(m.lineSlopesDeg);
    return { score: clamp10(sErr(d,1.0,8.0)), value:d.toFixed(1)+'° drift',
      evidence:'mean absolute slope of fitted text lines (§4C F11)' }; } },

{ n:12, sec:'spatial', name:'Vertical Alignment', target:'tilt CV ≤0.20', conf:'measured',
  tip:'Straight-stroke drills — l l l l kept upright.', ex:'slant',
  compute:(m)=>{ const a=m.slant; if(a.length<10) return {score:6,value:'n/a',evidence:'insufficient strokes'};
    return { score: clamp10(sCon(a.map(v=>Math.abs(v)),0.6,1.6)), value:'σ '+std(a).toFixed(1)+'°',
      evidence:'scatter of per-stroke axis angle vs upright (§4C F12)' }; } },

/* ---------------- Section 3 — Dynamics (20%) — IMU pen --------------- */
{ n:13, sec:'dynamics', name:'Speed Consistency', target:'velocity CV ≤0.20', conf:'imu',
  tip:'Slow-writing timing drill; write to a steady 1-2-3 count.', ex:'wave',
  compute:(m)=>({ score: clamp10(sCon(m.strokeWidths,0.25,0.70)),
    value:'image proxy', evidence:'stroke-width thinning proxy now; IMU velocity at 208 Hz is the true instrument (§4B)' }) },

{ n:14, sec:'dynamics', name:'Pressure Consistency', target:'CV ≤0.20', conf:'imu',
  tip:'Same-pressure line drills; keep one steady, relaxed force.', ex:'wave',
  compute:(m)=>{ const c=cv(m.inkIntensity);
    return { score: clamp10(sCon(m.inkIntensity,0.20,0.78)), value:'ink CV '+c.toFixed(2),
      evidence:'ink-intensity variation (weak proxy — IMU force is the real signal, §4B)' }; } },

{ n:15, sec:'dynamics', name:'Stroke Continuity', target:'0 unintended breaks', conf:'imu',
  tip:'Cursive joining practice — connect letters within a word.', ex:'rhythm',
  compute:(m)=>{ const perWord = m.nChars/Math.max(1,m.nWords);
    const sc = sErr(Math.abs(perWord-4)/2, 0.2, 2.0); // very rough connectivity proxy
    return { score: clamp10(6.5+ (sc-5)*0.3), value:perWord.toFixed(1)+' parts/word',
      evidence:'component-per-word connectivity proxy (§4C F15)' }; } },

{ n:16, sec:'dynamics', name:'Pen Lift Frequency', target:'≤0.3 lifts/char', conf:'imu',
  tip:'Continuous-word writing without lifting mid-word.', ex:'rhythm',
  compute:(m)=>({ score: 6.5, value:'IMU-pending',
    evidence:'pen-up events are temporal — recorded directly by the IMU pen (§4B flagship)' }) },

/* ---------------- Section 4 — Style & Readability (20%) -------------- */
{ n:17, sec:'style', name:'Slant Consistency', target:'angle CV low', conf:'measured',
  tip:'Slant rails — rows of / at one steady angle, then \\.', ex:'slant',
  compute:(m)=>{
    // Prefer the robust per-word shear-search angles; fall back to per-pixel gradient.
    const useWord = m.slantWord && m.slantWord.length >= 4;
    const a = useWord ? m.slantWord : m.slant;
    if (!a || a.length < (useWord?4:10)) return {score:6,value:'n/a',evidence:'insufficient strokes'};
    const c = std(a);
    // shear angles are per-word dominant slants (cleaner) → a slightly tighter band
    const tolGood = useWord ? 6 : 11, tolBad = useWord ? 26 : 40;
    return { score: clamp10(sErr(c,tolGood,tolBad)), value:'σ '+c.toFixed(1)+'° · '+mean(a).toFixed(0)+'° lean',
      evidence: useWord
        ? 'spread of per-word slant from shear-search deslanting (§4C F17)'
        : 'spread of dominant stroke angles (§4C F17)' }; } },

{ n:18, sec:'style', name:'Legibility Score', target:'even & clear', conf:'ml',
  tip:'Lift your two lowest factors first — legibility rises with them.', ex:'round',
  compute:(m)=>{ const lg=m.letterGapNorm||[];
    const gapsUsable = lg.length>=2 && mean(lg)>=0.12 && cv(lg)<=3.2;   // joined writing → no real gaps
    const sizeC=sCon(m.letterHeights,0.12,0.45), base=sErr(mean(m.baselineRMSnorm),0.08,0.40),
          space=gapsUsable?sCon(lg,0.30,0.90):null;
    const arr = space!=null
      ? [['letter size evenness',sizeC],['letter spacing',space],['sitting on the line',base]]
      : [['letter size evenness',sizeC],['sitting on the line',base]];
    const sc = space!=null ? 0.4*sizeC+0.3*space+0.3*base : 0.6*sizeC+0.4*base;
    const parts=[...arr].sort((a,b)=>a[1]-b[1]);
    return { score: clamp10(sc), value:'driven by '+parts[0][0],
      evidence:`Overall readability blends your basics. Right now it is held back most by ${parts[0][0]} — improve that and the legibility score follows.`+(space==null?' (Letter spacing is left out here — your letters join up, so there are no gaps to judge.)':'') }; } },

{ n:19, sec:'style', name:'Character Distinction', target:'clear letter pairs', conf:'ml',
  tip:'Practise easily-confused pairs side by side until each is unmistakable.', ex:'round',
  compute:(m)=>{ const targets = m.loopRatio<0.6 ? 'a, o, e, g' : 'n/h, r/v, c/e';
    return { score: clamp10(5.5+(m.loopRatio-0.8)*4),
      value:'target '+targets,
      evidence:`Some look-alike letters blur together. Focus on ${targets} — making each one distinct is the fastest way to raise this score.` }; } },

{ n:20, sec:'style', name:'Overall Neatness', target:'weighted variance', conf:'measured',
  tip:'Keep the page tidy — even size, even spacing, straight lines.', ex:'frame',
  compute:(m)=>{ const lg=m.letterGapNorm||[];
    const gapsUsable = lg.length>=2 && mean(lg)>=0.12 && cv(lg)<=3.2;
    const parts=[sCon(m.letterHeights,0.12,0.45),
      ...(gapsUsable?[sCon(lg,0.30,0.90)]:[]),
      sErr(mean(m.lineSlopesDeg),1,8), sErr(mean(m.baselineRMSnorm),0.08,0.40)];
    return { score: clamp10(mean(parts)), value:'aggregate', evidence:'weighted variance across size, '+(gapsUsable?'spacing, ':'')+'line & baseline (§4C F20)' }; } },
];

/* ---- per-factor validity gate (Fix-Spec #8): range-check the inputs a
   factor reads BEFORE trusting its score. Out-of-range inputs (phantom
   segmentation: CV 19.86, 25k "strokes", etc.) return false → the factor is
   marked "unmeasured" and the report renders an honest "couldn't read this
   reliably — re-scan" state instead of a misleading 0.0. -------------------*/
/* gateCheck returns { ok:true } when a factor's inputs are trustworthy, or
   { ok:false, reason } with an HONEST, factor-specific explanation of why we
   are NOT reporting a score. Two honest categories:
     • "photo"  — the image (lighting, focus, angle, crop) didn't give the
                  engine clean enough geometry to measure this reliably.
     • "writing"— the measurement genuinely doesn't apply to this hand
                  (e.g. letters are joined, so there are no letter gaps).
   We never invent a number we cannot stand behind. */
function gateCheck(n, m){
  const nC = m.nChars||0;
  const fin = v => typeof v==='number' && isFinite(v);
  const ok = { ok:true };
  const sw = m.strokeWidths||[], sl = m.slant||[], lh = m.letterHeights||[],
        lg = m.letterGapNorm||[], wg = m.wordGapNorm||[], ii = m.inkIntensity||[];
  // total ink pixels — slant is a PER-PIXEL gradient array, so it scales with
  // ink area, not letter count. Used to sanity-cap genuine phantom explosions.
  const inkPx = (m.inkIntensity||[]).length || (m.w*m.h)||1;
  switch(n){
    case 4:  if(sw.length<3) return {ok:false,kind:'photo',reason:'Too few clean strokes were traced from this photo to gauge how smooth the lines are.'};
             if(nC>0 && sw.length>nC*12) return {ok:false,kind:'photo',reason:'Stroke tracing fragmented on this image (likely noise, creases or shadow), so a smoothness reading would be unreliable.'};
             return fin(cv(sw))?ok:{ok:false,kind:'photo',reason:'Stroke-width measurements didn’t resolve cleanly from this photo.'};
    case 5:  if(lh.length<3) return {ok:false,kind:'photo',reason:'Too few letters were isolated to compare their heights.'};
             { const c=cv(lh); return (fin(c)&&c<=1.2)?ok:{ok:false,kind:'photo',reason:'Detected letter heights varied far beyond real handwriting — segmentation likely merged or split letters on this image.'}; }
    case 6:  return (fin(m.zoneUpper)&&fin(m.zoneLower)&&m.zoneUpper>=0&&m.zoneUpper<=1&&m.zoneLower>=0&&m.zoneLower<=1)?ok:{ok:false,kind:'photo',reason:'The upper/lower zones of the writing couldn’t be separated cleanly against the baseline in this photo.'};
    case 7:  { const r=mean(m.baselineRMSnorm||[]); return (fin(r)&&r>=0&&r<5)?ok:{ok:false,kind:'photo',reason:'A stable baseline couldn’t be fitted to the lines in this image.'}; }
    case 8:  if(wg.length<2) return {ok:false,kind:'writing',reason:'Not enough separate words on the page to measure the gaps between them.'};
             { const mm=mean(wg), c=cv(wg); return (fin(mm)&&fin(c)&&mm>0.05&&mm<8&&c<=2.5)?ok:{ok:false,kind:'photo',reason:'Word boundaries didn’t resolve reliably (words ran together or split), so the spacing reading can’t be trusted.'}; }
    case 9:  if(lg.length<2) return {ok:false,kind:'writing',reason:'Not enough separable letters to measure the gaps between them.'};
             { const c=cv(lg), mm=mean(lg);
               if(fin(mm) && mm<0.12) return {ok:false,kind:'writing',reason:'Your letters are joined (cursive/connected), so there are effectively no gaps between them to measure — this is about your style, not the photo.'};
               return (fin(c)&&c<=3.2)?ok:{ok:false,kind:'photo',reason:'Letter gaps came back wildly uneven, which usually means the photo merged or split letters rather than your spacing varying that much.'}; }
    case 11: return fin(mean(m.lineSlopesDeg||[]))?ok:{ok:false,kind:'photo',reason:'Line angles couldn’t be fitted reliably from this image.'};
    case 12: if(sl.length<40) return {ok:false,kind:'photo',reason:'Too little clean ink was traced to measure how upright the strokes stand.'};
             if(sl.length>inkPx*1.2) return {ok:false,kind:'photo',reason:'Gradient tracing picked up texture/noise instead of strokes, so an upright-tilt reading would be unreliable.'};
             return ok;
    case 14: return (ii.length>=3 && fin(cv(ii)))?ok:{ok:false,kind:'photo',reason:'Ink-darkness samples didn’t resolve cleanly from this photo.'};
    case 17: { const uw=m.slantWord&&m.slantWord.length>=4; const a=uw?m.slantWord:sl;
               return (a&&a.length>=(uw?4:40))?ok:{ok:false,kind:'photo',reason:'Too few clean words/strokes were traced to measure a consistent slant from this image.'}; }
    default: return ok;   // proxy/imu factors self-handle; composites gated by dependency below
  }
}
function gateMeasurable(n, m){ return gateCheck(n, m).ok; }

/* ---- run the full scorer (optional imu summary overrides dynamics) ----- */
function scoreAll(metrics, imu){
  const results = FACTORS.map(f=>{
    let r; try{ r=f.compute(metrics); }catch(e){ r={score:5,value:'n/a',evidence:'insufficient data'}; }
    let imuMeasured=false, conf=f.conf;
    if (imu && imu.dynamics && imu.dynamics[f.n]){
      const o = imu.dynamics[f.n];
      r = { score:o.score, value:o.value, evidence:o.evidence };
      imuMeasured = true; conf = 'imu';
    }
    const score = Math.round(r.score*10)/10;
    return { ...f, compute:undefined, conf, imuMeasured, score, band:band(score), value:r.value, evidence:r.evidence,
             score100: Math.round(score*10) };
  });

  // validity gate — mark factors whose inputs are implausible, with an honest reason
  results.forEach(r=>{ const g=gateCheck(r.n, metrics); r.unmeasured=!g.ok; r.unmeasuredReason=g.reason||null; r.unmeasuredKind=g.kind||null; });
  const byN={}; results.forEach(r=>byN[r.n]=r);
  // composites (Legibility, Neatness) inherit failure ONLY when a dependency
  // genuinely couldn't be READ from the photo. If the only "missing" input is
  // one that doesn't apply to this writing style (e.g. joined letters → no
  // letter gaps), the composite still scores from the basics that ARE present.
  [18,20].forEach(n=>{
    if(!byN[n]) return;
    const dep = [byN[5],byN[9],byN[7]].find(d=>d&&d.unmeasured&&d.unmeasuredKind==='photo');
    if(dep){ byN[n].unmeasured=true; byN[n].unmeasuredKind='photo';
      byN[n].unmeasuredReason='This blends several basics, and one of them — '+
        (dep.n===5?'letter-size evenness':dep.n===9?'letter spacing':'sitting on the line')+
        ' — couldn’t be read reliably from this photo, so we won’t report a combined score we can’t stand behind.'; }
  });

  // a factor counts toward a score only if it was actually measured this run
  const scored = r => !r.unmeasured && (r.imuMeasured || r.conf!=='imu');

  // section aggregates — exclude unmeasured AND pen-pending factors; null when nothing measured (#5)
  const sections = SECTIONS.map(s=>{
    const all = results.filter(r=>r.sec===s.id);
    const fs = all.filter(scored);
    const avg = fs.length ? mean(fs.map(r=>r.score)) : null;
    return { ...s, avg: avg==null?null:Math.round(avg*10)/10, avg100: avg==null?null:Math.round(avg*10),
             factors:all, scoredCount:fs.length };
  });

  // weighted overall over a filtered factor set, re-normalising weights
  function weightedOverall(filterFn){
    const parts = SECTIONS.map(s=>{
      const fs = results.filter(r=>r.sec===s.id && filterFn(r));
      return fs.length ? { w:s.weight, avg:mean(fs.map(r=>r.score)) } : null;
    }).filter(Boolean);
    const wsum = parts.reduce((a,x)=>a+x.w,0) || 1;
    return Math.round(parts.reduce((a,x)=>a + x.avg*10*(x.w/wsum), 0));
  }
  const overall = weightedOverall(r=>!r.unmeasured);   // imu mode: all live factors
  const overallMeasured = weightedOverall(scored);     // photo mode headline (no pen-pending, no unmeasured)
  const measuredCount = results.filter(scored).length;

  // per-factor sample size ("based on …") for credibility
  const BASIS = {
    1:m=>m.nChars+' letters', 3:m=>m.nChars+' letters', 4:m=>m.strokeWidths.length+' strokes',
    5:m=>m.letterHeights.length+' letters', 6:m=>m.nChars+' letters',
    7:m=>m.nLines+' line'+(m.nLines>1?'s':''), 8:m=>m.wordGapNorm.length+' word gaps',
    9:m=>m.letterGapNorm.length+' letter gaps', 10:m=>m.nLines+' line edges',
    11:m=>m.nLines+' line'+(m.nLines>1?'s':''), 12:m=>(m.slant?m.slant.length:0)+' strokes',
    17:m=>((m.slantWord&&m.slantWord.length>=4)?m.slantWord.length+' words':(m.slant?m.slant.length:0)+' strokes'),
    20:m=>m.nChars+' letters',
  };
  results.forEach(r=>{ try{ r.basedOn = (BASIS[r.n] && !r.unmeasured) ? BASIS[r.n](metrics) : null; }catch(e){ r.basedOn=null; } });

  // weakest / strongest — never rank an unmeasured factor
  const ranked = [...results].filter(r=>!r.unmeasured).sort((a,b)=>a.score-b.score);
  const weak = ranked.filter(r=>r.score<5);
  const topWeak = (weak.length?weak:ranked).slice(0,3);
  const topStrong = [...results].filter(scored).sort((a,b)=>b.score-a.score).slice(0,4);
  return { results, sections, overall, overallMeasured, measuredCount, topWeak, topStrong };
}

const overallBand = (o)=> o>=80?'Strong & consistent' : o>=66?'Developing well' : o>=50?'Emerging — clear focus areas' : 'Early — lots to build on';

global.VahiniFactors = { FACTORS, SECTIONS, scoreAll, overallBand, band };
})(window);
