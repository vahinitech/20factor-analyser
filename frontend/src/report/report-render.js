/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Indian Patents No. 584433 and 604895.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini report renderer: builds the data-driven report from
   { intake, analysis, expectedText, actualCanvas, detCanvas, pipeline }.
   Reuses report.css classes (Ink & Paper).
   ========================================================================= */
(function (global) {
'use strict';
/* Single source of truth for the 4 score bands, read by every report page
   that shows a band (scorecard section rows via bandOf(), factor cards and
   the reference-values table via the server-assigned f.band) so the
   thresholds, wording and colour never drift apart between pages again.
   Must track backend/scoring.py's _band(). */
const bandOf = (score)=> score>=8.5?'strong' : score>=7.0?'good' : score>=4.5?'dev' : 'focus';

function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

/* ---- per-factor "where we look" visual: a handwriting sample with the
   exact region this factor measures highlighted, so a human can SEE why
   the score is what it is. Returns { svg, look }. -------------------------*/
const FOCUS = {
  1:['form','the shape of each letter vs the ideal'],
  2:['break','the order strokes are built in'],
  3:['loop','whether round letters close (a o e g)'],
  4:['smooth','how smooth, un-shaky each stroke is'],
  5:['size','that every letter is the same height'],
  6:['zone','tall letters & tails reaching their zones'],
  7:['baseline','whether letters sit on the line'],
  8:['wordspace','the gap between words'],
  9:['letterspace','the gaps between letters'],
  10:['margin','the left margin down the page'],
  11:['drift','whether the line runs level'],
  12:['slant','that up-strokes point one way'],
  13:['speed','the steadiness of writing pace'],
  14:['pressure','how evenly the pen presses'],
  15:['break','where strokes break instead of flowing'],
  16:['lift','how often the pen leaves the page'],
  17:['slant','the consistency of the lean'],
  18:['clarity','overall how easy it is to read'],
  19:['confuse','telling look-alike letters apart'],
  20:['clarity','the overall tidiness'],
};
function focusSVG(f){
  const map = FOCUS[f.n] || ['clarity','this quality'];
  const kind = map[0], look = map[1];
  const off = f.band==='focus', dev = f.band==='dev';
  const HL = off ? '#C85A3C' : dev ? '#C29A45' : '#2F8F7F';   // highlight colour by band
  const INK = '#27406b';
  const W=240, H=54;
  const wrap = (inner)=>`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%;">${inner}</svg>`;
  const word = (t,x,y,s,col,extra)=>`<text x="${x}" y="${y}" font-family="Caveat, cursive" font-weight="600" font-size="${s}" fill="${col||INK}" ${extra||''}>${t}</text>`;
  switch(kind){
    case 'slant':{
      // "min" with stem guide-lines showing the lean
      const lean = off ? [18,-6,12] : dev ? [12,10,11] : [11,11,11];
      let g=''; lean.forEach((a,i)=>{ const x=42+i*52; g+=`<line x1="${x}" y1="44" x2="${x+a}" y2="14" stroke="${HL}" stroke-width="2" stroke-dasharray="3 3"/>`; });
      return { svg: wrap(`${word('min',26,40,40)}${g}<text x="150" y="40" font-family="Caveat,cursive" font-size="40" fill="${INK}">i</text>`), look };
    }
    case 'baseline':{
      const path = off ? 'M16 38 Q70 30 120 40 T224 34' : 'M16 38 L224 38';
      return { svg: wrap(`<path d="${path}" fill="none" stroke="${HL}" stroke-width="2.5"/>${word('handwriting',20,34,30)}`), look };
    }
    case 'drift':{
      const y2 = off ? 20 : 36;
      return { svg: wrap(`${word('a steady line',18,30,26,INK,'transform="rotate('+(off?-7:0)+' 120 30)"')}<line x1="14" y1="42" x2="226" y2="${y2+6}" stroke="${HL}" stroke-width="2.5" stroke-dasharray="4 3"/>`), look };
    }
    case 'size':{
      const hs = off ? [26,16,30,18,24] : dev ? [24,20,26,21,23] : [22,22,22,22,22];
      let g=''; hs.forEach((h,i)=>{ const x=24+i*40; g+=`<rect x="${x}" y="${44-h}" width="22" height="${h}" rx="3" fill="none" stroke="${HL}" stroke-width="1.6"/>`+word(['m','i','n','i','m'][i],x+3,42,h*0.9,INK); });
      return { svg: wrap(`<line x1="16" y1="44" x2="224" y2="44" stroke="#cdd6e6" stroke-width="1.4"/>${g}`), look };
    }
    case 'zone':{
      return { svg: wrap(`
        <rect x="14" y="8" width="212" height="13" fill="${f.n===6?HL:'#e8eef7'}" opacity="0.5"/>
        <rect x="14" y="34" width="212" height="13" fill="${f.n===6?HL:'#e8eef7'}" opacity="0.5"/>
        ${word('baking',24,40,40)}`), look };
    }
    case 'wordspace':{
      const gap = off ? 12 : 40;
      return { svg: wrap(`${word('the',20,38,30)}<rect x="${74}" y="14" width="${gap}" height="28" fill="${HL}" opacity="0.28"/>${word('quick',74+gap+4,38,30)}`), look };
    }
    case 'letterspace':{
      let g=word('open',24,38,34); const xs=off?[60,92,120]:[58,98,140];
      xs.forEach(x=>{ g+=`<rect x="${x}" y="16" width="${off?4:10}" height="26" fill="${HL}" opacity="0.3"/>`; });
      return { svg: wrap(g), look };
    }
    case 'loop':{
      const r = off ? 'M70 20 A12 14 0 1 0 70 44' : '';   // open gap when off
      return { svg: wrap(`${word('a o e',26,40,40)}<circle cx="40" cy="30" r="15" fill="none" stroke="${HL}" stroke-width="2"/>${off?`<path d="${r}" fill="none" stroke="${HL}" stroke-width="2"/>`:''}`), look };
    }
    case 'confuse':{
      return { svg: wrap(`${word('c  e  o',30,40,40)}<rect x="22" y="12" width="44" height="36" rx="6" fill="none" stroke="${HL}" stroke-width="1.8" stroke-dasharray="4 3"/>`), look };
    }
    case 'margin':{
      return { svg: wrap(`<rect x="20" y="8" width="200" height="40" rx="3" fill="none" stroke="#cdd6e6" stroke-width="1.4"/><line x1="${off?'42':'40'}" y1="8" x2="${off?'52':'40'}" y2="48" stroke="${HL}" stroke-width="2.5"/>
        <line x1="50" y1="16" x2="150" y2="16" stroke="#bcc7da" stroke-width="2"/><line x1="50" y1="26" x2="170" y2="26" stroke="#bcc7da" stroke-width="2"/><line x1="50" y1="36" x2="130" y2="36" stroke="#bcc7da" stroke-width="2"/>`), look };
    }
    case 'break':{
      let g=word('writing',24,38,34); const breaks = off?[64,96,128,160]:[];
      breaks.forEach(x=>{ g+=`<circle cx="${x}" cy="30" r="5" fill="none" stroke="${HL}" stroke-width="2"/><line x1="${x-3}" y1="27" x2="${x+3}" y2="33" stroke="${HL}" stroke-width="2"/>`; });
      if(!off) g+=`<path d="M28 42 Q120 50 196 42" fill="none" stroke="${HL}" stroke-width="2" stroke-dasharray="2 3"/>`;
      return { svg: wrap(g), look };
    }
    case 'lift':{
      let g=word('hello',24,38,36); const lifts=off?[58,92,128,160]:[92];
      lifts.forEach(x=>{ g+=`<path d="M${x} 18 l5 -8 l5 8" fill="none" stroke="${HL}" stroke-width="2"/>`; });
      return { svg: wrap(g), look };
    }
    case 'pressure':{
      const ws = off ? [2,6,3,7,2,5] : [4,4,5,4,5,4];
      let g=''; ws.forEach((w,i)=>{ const x=20+i*36; g+=`<line x1="${x}" y1="27" x2="${x+30}" y2="27" stroke="${HL}" stroke-width="${w}" stroke-linecap="round"/>`; });
      return { svg: wrap(g), look };
    }
    case 'speed':{
      const pts = off ? '16,40 40,16 60,42 84,18 104,40 128,14 150,42 172,20 196,40 224,24' : '16,30 48,26 80,30 112,26 144,30 176,26 224,30';
      return { svg: wrap(`<polyline points="${pts}" fill="none" stroke="${HL}" stroke-width="2.4" stroke-linejoin="round"/>`), look };
    }
    case 'form':{
      return { svg: wrap(`${word('a',30,44,46,'#cdd6e6')}${word('a',30,44,46,'none','stroke="'+HL+'" stroke-width="1.5"')}${word('abc',96,42,38,INK)}`), look };
    }
    case 'smooth':{
      const p = off ? 'M16 30 q12 -16 24 0 t24 0 t24 0 t24 0 t24 0 t24 0 t24 0' : 'M16 30 q60 -10 104 0 t104 0';
      return { svg: wrap(`<path d="${p}" fill="none" stroke="${HL}" stroke-width="2.4"/>`), look };
    }
    default:{ // clarity
      return { svg: wrap(`${word('clear &',22,32,28)}${word('legible',30,50,28)}<rect x="14" y="10" width="212" height="40" rx="6" fill="none" stroke="${HL}" stroke-width="1.4" stroke-dasharray="3 3"/>`), look };
    }
  }
}

/* ===================== MAIN RENDER ===================================== */
/* Classification panels are shown on printed-only refusals; the two-page
   reader report below never appends them. */
function classificationPanels(summary){
  if (!summary) return [];
  const panels = [];
  const groups = [
    ['handwritten', 'Handwritten text'],
    ['printed', 'Printed text (excluded from scoring)'],
    ['unclassified', 'Unclassified text'],
  ];
  groups.forEach(([kind, title])=>{
    const entries = Array.isArray(summary[kind]) ? summary[kind] : [];
    if (kind==='unclassified' && !entries.length) return;
    const rows = [];
    entries.forEach(entry=>{
      const characters = Array.from(String(entry.text || '(Text not recognized)'));
      for (let offset=0; offset<characters.length; offset+=120){
        const text = characters.slice(offset, offset+120).join('');
        const granularity = ['letter','word','line'].includes(entry.granularity) ? entry.granularity : 'region';
        const score = Number.isFinite(entry.printed_score) ? entry.printed_score.toFixed(3) : 'Unavailable';
        rows.push(`<tr><td>${esc(entry.id || '')}${offset?' (continued)':''}<br><small>${esc(granularity)}</small></td><td style="white-space:pre-wrap;overflow-wrap:anywhere;">${esc(text)}</td><td>${score}</td><td>${kind!=='printed' && entry.included_in_scoring?'Included':'Excluded'}</td></tr>`);
      }
    });
    if (!rows.length) rows.push('<tr><td colspan="4">No '+esc(kind)+' text detected.</td></tr>');
    for (let offset=0; offset<rows.length; offset+=10){
      panels.push(`<div class="text-classification" data-kind="${kind}">
        <h3>${title}${offset?' (continued)':''}</h3>
        <p style="font-size:11px;line-height:1.5;">${esc(summary.note || 'Classification applies to detected regions; finer labels may be unavailable.')}</p>
        <p style="font-size:11px;">Print score: 0 = less print-like, 1 = more print-like. This is not measured accuracy. Printed text is shown for identification only.</p>
        <table style="width:100%;table-layout:fixed;font-size:11px;border-collapse:collapse;"><thead><tr><th style="width:18%;">Region / level</th><th style="width:52%;">Recognized text</th><th style="width:15%;">Print score</th><th style="width:15%;">Scoring</th></tr></thead><tbody>${rows.slice(offset,offset+10).join('')}</tbody></table>
      </div>`);
    }
  });
  return panels;
}


/* Pen capture: the server scores the trace image and marks the four
   Dynamics factors unmeasured; the pen's own per-stroke measurements fill
   them in here, and the section scores are recomputed. The overall stays
   the server's: it counts factors 1, 5, 7, 11 and 17 only
   (scoring._OVERALL_POINTS, #304), which the pen does not change. */
function applyPenDynamics(analysis, imu){
  const dyn=imu && imu.dynamics;
  if(!analysis || !Array.isArray(analysis.results) || !dyn) return analysis;
  analysis.results.forEach(f=>{
    const d=dyn[f.n]; if(!d || !Number.isFinite(d.score)) return;
    const score=Math.max(0,Math.min(10,Number(d.score)));
    Object.assign(f,{score:Number(score.toFixed(1)),score100:Math.round(score*10),band:bandOf(score),conf:'measured',
      imuMeasured:true,unmeasured:false,unmeasuredReason:null,unmeasuredKind:null,
      value:d.value||f.value,evidence:d.evidence||f.evidence});
  });
  const live=analysis.results.filter(f=>!f.unmeasured && Number.isFinite(f.score));
  (analysis.sections||[]).forEach(s=>{
    const fs=live.filter(f=>f.sec===s.id);
    s.factors=analysis.results.filter(f=>f.sec===s.id);
    s.avg=fs.length?Number((fs.reduce((n,f)=>n+f.score,0)/fs.length).toFixed(1)):null;
    s.avg100=s.avg==null?null:Math.round(s.avg*10);
    s.scoredCount=fs.length;
  });
  analysis.measuredCount=live.length;
  const ranked=live.slice().sort((a,b)=>a.score-b.score);
  analysis.topWeak=ranked.slice(0,3); analysis.topStrong=ranked.slice().reverse().slice(0,4);
  return analysis;
}

/* ---- practice (docs/10-practice-framework.md; owner approval 2026-10-11, #122)
   Exercises, tips and how many tries come from the practice catalogue
   (backend/report/practice_catalog.py), never from this file: the catalogue served
   with the report's dictionary version when there is one, otherwise the copy
   build_bundle.py packs into the bundle (window.VahiniPracticeCatalog).
   Which ones a report prints is chosen by VahiniPracticeSelect
   (practice-select.js, "Many-to-many selection"). */
const STAGE_ORDER = ['focus','dev','good','strong'];
const DEFAULT_LIMITS = { free:{areas_max:3,exercises_max:1,tips_max:1}, pro:{areas_max:3,exercises_max:2,tips_max:2} };
function practiceCatalog(analysis){
  const served = analysis && analysis.practice;
  if (served && served.factors && served.dosage) return served;
  const bundled = window.VahiniPracticeCatalog;
  return bundled && bundled.factors && bundled.dosage ? bundled : null;
}
/* How many skills, exercises and tips: the numbers /api/v2/me returned for
   this visitor (analysis.practiceLimits), else the catalogue's tier
   defaults. Anything that is not a small whole number is ignored. */
function practiceLimits(analysis, cat, tier){
  const base = { ...DEFAULT_LIMITS[tier], ...((cat && cat.tiers && cat.tiers[tier]) || {}) };
  const given = analysis && analysis.practiceLimits;
  const out = {};
  Object.keys(DEFAULT_LIMITS.free).forEach(k=>{
    const v = given && given[k];
    out[k] = Number.isInteger(v) && v >= 0 && v <= 20 ? v : base[k];
  });
  return out;
}
/* Why a skill helps, the win to look for and its page on vahinitech.com
   (practice catalogue, 2026-10-11): from the served catalogue, or the
   bundled copy when a saved report's older catalogue has none. Each text
   falls back to English on its own. */
function factorAbout(cat, n, lang){
  const own = cat && cat.factors && cat.factors[String(n)];
  const bundled = window.VahiniPracticeCatalog && window.VahiniPracticeCatalog.factors && window.VahiniPracticeCatalog.factors[String(n)];
  const area = own && typeof own.why === 'string' ? own : bundled && typeof bundled.why === 'string' ? bundled : null;
  if (!area) return null;
  const local = (lang !== 'en' && area.i18n && area.i18n[lang]) || {};
  const pick = k=>typeof local[k] === 'string' && local[k] ? local[k] : area[k];
  return { why: pick('why'), win: pick('win'), page: /^[a-z0-9-]+$/.test(area.page || '') ? area.page : '' };
}
/* Latin-only exercises (a-o pairs, joined writing) are skipped when most
   letters read from the page are another script. No text reads as Latin. */
function latinPage(text){
  const letters = String(text || '').match(/\p{L}/gu) || [];
  if (!letters.length) return true;
  return letters.filter(c=>/[A-Za-zÀ-ɏ]/.test(c)).length * 2 >= letters.length;
}
/* The spelling row's tips move on at a re-check: start after the last one
   printed and wrap back to the first. */
function rotate(list, lastIds, count){
  if (!list.length || count <= 0) return [];
  const ids = Array.isArray(lastIds) ? lastIds : [];
  const last = Math.max(-1, ...ids.map(id=>list.findIndex(e=>e.id===id)));
  const start = last < 0 ? 0 : (last + 1) % list.length;
  return Array.from({ length: Math.min(count, list.length) }, (_, k)=>list[(start + k) % list.length]);
}
/* Pictures of Vahini and friends come only from the host page, as
   same-site paths in window.VAHINI_REPORT_ART ({teacher, tip, encourage}),
   validated like VAHINI_NOTICE_ART. The drawings are not part of this
   repository; without the map the report has no pictures. */
function reportArt(key){
  const map = window.VAHINI_REPORT_ART;
  const url = map && typeof map[key] === 'string' ? map[key] : '';
  return /^\/(?!\/)[\w\-./%]+$/.test(url) ? url : '';
}
function artImg(key, cls){
  const url = reportArt(key);
  // Without the map yet, leave an empty slot: a host that loads its script
  // after the report (the sample page loads site.js async) fills it on load.
  return url ? `<img class="rp-art ${cls}" src="${esc(url)}" alt="" data-art="${key}">`
    : `<span class="rp-art-slot" data-art-slot="${key}" data-art-cls="${esc(cls)}" hidden></span>`;
}
function fillReportArt(root){
  (root || document).querySelectorAll('[data-art-slot]').forEach(slot=>{
    const key = slot.getAttribute('data-art-slot'), url = reportArt(key);
    if (!url) return;
    const img = document.createElement('img');
    img.className = 'rp-art ' + (slot.getAttribute('data-art-cls') || '');
    img.src = url; img.alt = ''; img.setAttribute('data-art', key);
    slot.replaceWith(img);
  });
}

/* Report words come from the string tables (strings/<lang>.js, looked up
   through VahiniI18n): the language chosen in "Print in", English by
   default. Exercises and tips carry their own translations in the practice
   catalogue (i18n.<lang>), each falling back to English on its own. */
function translatorFor(data){
  const i18n = window.VahiniI18n;
  const lang = data && data.lang || (i18n ? i18n.language() : 'en');
  return i18n ? i18n.translator(lang) : null;
}
function localEntry(entry, lang){
  const own = entry && entry.i18n && entry.i18n[lang];
  if (!own || lang === 'en') return entry;
  const out = { ...entry };
  ['title','steps','check','example','text'].forEach(k=>{ if (typeof own[k] === 'string' && own[k]) out[k] = own[k]; });
  return out;
}
/* A step is up to three short sentences, one action each: numbered 1, 2, 3. */
function stepList(steps){
  return String(steps || '').trim().split(/(?<=[.!?])\s+/).filter(Boolean);
}

/* ---- drawings (our own, inline SVG; colours from the theme tokens in
   report.css through currentColor and classes) ---------------------------*/
const ICON = {
  shape:'<path d="M4 20l1-4L16 5l3 3L8 19z"/><path d="M14 7l3 3"/>',
  order:'<circle cx="7" cy="5" r="1.6"/><path d="M7 8v12M7 13c2.5-3 9-3 9 1.5S9.5 21 7 18"/>',
  size:'<path d="M3 20h18M3 9h18" stroke-dasharray="2 3"/><path d="M7 20v-8.5M12 20v-8.5M17 20v-8.5"/>',
  tall:'<path d="M3 15h18" stroke-dasharray="2 3"/><path d="M6 3v12M12 9v6M18 9v12"/>',
  line:'<path d="M4 7h16M4 12h16M4 17h11"/>',
  space:'<path d="M3 12h18M6 8l-3 4 3 4M18 8l3 4-3 4"/>',
  margin:'<path d="M7 3v18M10 7h9M10 12h7M10 17h8"/>',
  slant:'<path d="M5 20L9 4M11 20l4-16M17 20l4-16"/>',
  smooth:'<path d="M3 12c3-6 6 6 9 0s6 6 9 0"/>',
  pen:'<path d="M14 3l7 7-9 9H5v-7z"/><path d="M5 19l4-4"/>',
  read:'<path d="M12 6c-2-1.5-5-2-8-1.5V19c3-.5 6 0 8 1.5 2-1.5 5-2 8-1.5V4.5C17 4 14 4.5 12 6z"/><path d="M12 6v14.5"/>',
  page:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
};
const FACTOR_ICON = {1:'shape',2:'order',3:'shape',4:'smooth',5:'size',6:'tall',7:'line',8:'space',9:'space',10:'margin',
  11:'line',12:'slant',13:'pen',14:'pen',15:'smooth',16:'pen',17:'slant',18:'read',19:'shape',20:'page'};
const iconSVG = n=>`<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${ICON[FACTOR_ICON[n]||'page']}</svg>`;
const LEAF = '<svg class="sn-leaf" viewBox="0 0 40 48" aria-hidden="true"><path class="lf-stem" d="M20 46 C20 30 20 20 21 8"/><path class="lf-a" d="M21 22 C10 22 5 14 6 6 C14 6 21 12 21 22Z"/><path class="lf-b" d="M21 30 C32 30 37 22 36 14 C28 14 21 20 21 30Z"/></svg>';
const PENCIL = '<svg class="sn-pencil" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M4 20l1-4L16 5l3 3L8 19z"/><path d="M14 7l3 3"/></svg>';
const SPARK = '<svg class="sn-spark" viewBox="0 0 26 40" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M4 4l10 10M16 20h9M4 34l10-4"/></svg>';

/* What to write in a drawing when the exercise has no example of its own:
   Latin practice text for the picture only, not a drill. */
const MODEL_WORDS = { ladder:'a o e c n m', zones:'h l g y', baseline:'on the line', gaps:'a big red bus',
  'letter-gaps':'minim', slant:'l h l h', loops:'o a o a', trace:'a d g o', 'start-dots':'a b c d', pairs:'a o c e' };
/* "Copy this": one drawing per exercise kind (the catalogue's model). */
function modelHTML(kind, example){
  const text = String(example || MODEL_WORDS[kind] || '').trim();
  const words = text.split(/\s+/).filter(Boolean);
  const hand = s=>`<span class="md-hand">${esc(s)}</span>`;
  switch(kind){
    case 'ladder': return `<div class="md md-ladder">${hand(text)}</div>`;
    case 'zones': return `<div class="md md-zones">${hand(text)}</div>`;
    case 'baseline': return `<div class="md md-baseline">${hand(text)}</div>`;
    case 'gaps': return `<div class="md md-gaps">${words.map(hand).join('<i class="md-gap" aria-hidden="true"></i>')}</div>`;
    case 'letter-gaps': return `<div class="md md-letter-gaps">${Array.from(text.replace(/\s+/g,'')).map(hand).join('<i class="md-lgap" aria-hidden="true"></i>')}</div>`;
    case 'slant': return `<div class="md md-slant">${hand(text)}</div>`;
    case 'loops': return `<div class="md md-loops">${words.map(w=>`<span class="md-ring">${hand(w)}</span>`).join('')}</div>`;
    case 'trace': return `<div class="md md-trace">${hand(text)}<span class="md-arrow" aria-hidden="true">→</span>${hand(text)}</div>`;
    case 'start-dots': return `<div class="md md-dots">${words.map(w=>`<span class="md-dot">${hand(w)}</span>`).join('')}</div>`;
    case 'pairs': {
      const pairs = []; for (let i=0; i<words.length; i+=2) pairs.push(words.slice(i, i+2).join(' '));
      return `<div class="md md-pairs">${pairs.map(p=>`<span class="md-pair">${hand(p)}</span>`).join('')}</div>`;
    }
    case 'margin': return '<div class="md md-margin"><i></i><i></i><i></i></div>';
    case 'ovals': return '<div class="md md-ovals"><svg viewBox="0 0 300 40" aria-hidden="true"><g transform="translate(6 0) skewX(-16)"><ellipse cx="32" cy="20" rx="8" ry="16"/><ellipse cx="34" cy="20" rx="8" ry="16"/><ellipse cx="36" cy="20" rx="8" ry="16"/><ellipse cx="82" cy="20" rx="8" ry="16"/><ellipse cx="84" cy="20" rx="8" ry="16"/><ellipse cx="86" cy="20" rx="8" ry="16"/><ellipse cx="132" cy="20" rx="8" ry="16"/><ellipse cx="134" cy="20" rx="8" ry="16"/><ellipse cx="136" cy="20" rx="8" ry="16"/><ellipse cx="182" cy="20" rx="8" ry="16"/><ellipse cx="184" cy="20" rx="8" ry="16"/><ellipse cx="186" cy="20" rx="8" ry="16"/></g><path class="md-way" d="M247 20 A11 11 0 1 0 236 31 M236 31 l-5 -4 M236 31 l-5 4"/><path class="md-way" d="M265 20 A11 11 0 1 1 276 31 M276 31 l5 -4 M276 31 l5 4"/></svg></div>';
    case 'push-pulls': return '<div class="md md-push-pulls"><svg viewBox="0 0 300 40" aria-hidden="true"><path d="M24 36 L35 4 M29 36 L40 4 M34 36 L45 4 M39 36 L50 4 M84 36 L95 4 M89 36 L100 4 M94 36 L105 4 M99 36 L110 4 M144 36 L155 4 M149 36 L160 4 M154 36 L165 4 M159 36 L170 4"/><path class="md-way" d="M236 34 L248 6 M248 6 l-5 4 M248 6 l1 6 M236 34 l5 -4 M236 34 l-1 -6"/></svg></div>';
    case 'waves': return '<div class="md md-waves"><svg viewBox="0 0 300 40" preserveAspectRatio="none" aria-hidden="true"><path d="M4 12 H140"/><path d="M160 22 c12 -16 24 16 36 0 s24 16 36 0 s24 16 36 0"/><path d="M4 30 H140"/></svg></div>';
    case 'page': return '<div class="md md-page"><span class="md-sheet"><i></i><i></i><i></i><i></i></span></div>';
    default: return '';
  }
}
/* "Your turn" lines that match the drawing. */
function turnHTML(kind){
  const k = ['ladder','zones','baseline','slant','margin'].includes(kind) ? kind : 'line';
  return `<div class="yt yt-${k}" aria-hidden="true"></div>`;
}

/* ---- the QR code on page 1: drawn with qrcode-generator (MIT, vendored
   in scripts/vendor/qrcode.js, see sources.json there). Without the
   library the page has no QR and keeps its layout. -------------------------*/
function qrSVG(text){
  const make = window.qrcode;
  if (typeof make !== 'function' || !text) return '';
  try{
    const qr = make(0, 'M'); qr.addData(text); qr.make();
    const n = qr.getModuleCount(), q = 2;
    let d = '';
    for (let r=0; r<n; r++) for (let c=0; c<n; c++) if (qr.isDark(r, c)) d += `M${c+q} ${r+q}h1v1h-1z`;
    return `<svg class="sn-qr-code" viewBox="0 0 ${n+2*q} ${n+2*q}" shape-rendering="crispEdges" role="img" data-qr="${esc(text)}"><rect class="qr-bg" width="${n+2*q}" height="${n+2*q}"/><path class="qr-fg" d="${d}"/></svg>`;
  }catch(_e){ return ''; }
}

/* The last render, so "Print in" can redraw the same report in another
   language: same scores, crops, photo, history and pictures. */
let lastRender = null;
/* Who the report is for (owner, 2026-10-23; issue #291): "parent" (today's
   report, the default) or "student" (the student view above it). Chosen by
   ?for=student on the check page's address or the "Report for" switch
   beside the report, and kept in this tab only: never sent, never stored
   with a photo. */
const AUDIENCE_KEY = 'vahini_report_for';
let view = null;
function audience(){
  if (view) return view;
  let v = null;
  try{ v = new URLSearchParams(location.search).get('for'); }catch(_e){ /* no address */ }
  if (v !== 'student' && v !== 'parent'){ try{ v = sessionStorage.getItem(AUDIENCE_KEY); }catch(_e){ /* blocked */ } }
  view = v === 'student' ? 'student' : 'parent';
  return view;
}
function setAudience(v){
  view = v === 'student' ? 'student' : 'parent';
  try{ sessionStorage.setItem(AUDIENCE_KEY, view); }catch(_e){ /* this page only */ }
  return view;
}
/* "Details for your teacher" opens and folds the two pages on screen. */
function wireStudent(host){
  const btn = host.querySelector('.stu-more');
  if (!btn) return;
  btn.addEventListener('click', ()=>{
    const open = host.classList.toggle('stu-folded') === false;
    btn.setAttribute('aria-expanded', String(open));
    btn.textContent = btn.getAttribute(open ? 'data-open' : 'data-closed');
  });
}

function rerender(){
  if (!lastRender || !lastRender.host.isConnected) return null;
  return render(lastRender.host, lastRender.data);
}

function render(host, data){
  const {analysis, intake={}, recognizedText='', crops={}, imu=null, history=null}=data;
  lastRender = { host, data };
  const t=translatorFor(data);
  host.setAttribute('lang', t.lang);
  host.toggleAttribute('data-caseless', !!(global.VahiniI18n && VahiniI18n.caseless(t.lang)));
  if(imu && imu.dynamics) applyPenDynamics(analysis, imu);
  const rec=analysis.recognition || {};
  const isLive=f=>!f.unmeasured && (f.imuMeasured || f.conf!=='imu') && Number.isFinite(f.score);
  const stage=band=>t('stage.'+band);
  const measured=analysis.results.filter(isLive);
  const sorted=measured.filter(f=>![18,20].includes(f.n)).sort((a,b)=>a.score-b.score || a.n-b.n);
  const toGrow=sorted.filter(f=>f.score<8.5);
  const maintenance=!toGrow.length && sorted.length>0;
  const readable=['high','passage-verified'].includes(rec.level);
  // Classification entries preserve original OCR, unlike passage-corrected
  // text. Never check the printed stream or score-excluded regions.
  const classification=analysis.textClassification;
  const sources=classification
    ? (classification.handwritten || []).filter(r=>r.included_in_scoring).map(r=>({id:r.evidence_id||r.id,text:r.text}))
    : [{id:null,text:recognizedText}];
  const hasText=sources.some(r=>String(r.text||'').trim());
  // English spelling runs only on a page the server read as English (#221).
  const spelling=readable && window.VahiniCraft
    ? sources.flatMap(r=>VahiniCraft.checkSpelling(r.text,analysis.comparability).map(f=>({...f,region:r.id}))) : [];
  const firstSpelling=spelling[0];
  const free=analysis.access?.tier==='free';
  const tier=free?'free':'pro';
  const cat=practiceCatalog(analysis);
  const lim=practiceLimits(analysis, cat, tier);
  // Skill names: in another language the English name follows in brackets
  // on its first use on each page, so a teacher and a parent mean the same
  // skill.
  const skillName=f=>t.has('name.'+f.n)?t('name.'+f.n):f.name;
  const named={1:new Set(),2:new Set()};
  const nameOn=(page,f)=>{
    const local=skillName(f);
    if(t.lang==='en'||named[page].has(f.n)||!t.has('name.'+f.n)) return local;
    named[page].add(f.n);
    const en=t.en('name.'+f.n);
    return local===en?local:`${local} (${en})`;
  };
  // The skills to grow: the lowest measured skills below 8.5, composites
  // left out, up to the tier's number. The first one is "Start here".
  const rowFactors=(maintenance?sorted:toGrow).slice(0,lim.areas_max);
  const first=rowFactors[0]||null;
  const spellingStatus=!readable ? t('spelling.deferred')
    : !hasText ? t('spelling.notext')
    : spelling.length ? t('spelling.found')
    : t('spelling.clear');
  const writer=String(intake.writerName||'').trim();
  // Brand row with the Vahini logo and the website; the patent numbers on
  // every page (owner instruction, 2026-10-10). Both stay as written in
  // every language.
  const SITE='vahinitech.com';
  const brand=`<span class="sn-brand"><img class="sn-logo" src="assets/vahini-logo.png" alt="" width="40" height="40"><span><b class="sn-brandname">Vahini</b><span class="sn-site">${SITE}</span></span></span>`;
  const head=label=>`<div class="run-head sn-head">${brand}<span class="sn-headlabel">${esc(label)}</span></div>`;
  const foot=(n, note)=>`<div class="run-foot sn-foot"><span>${note?`${esc(note)}<br>`:''}${esc(t(free?'foot.review':'foot.review.pro'))} · Indian Patents No. 584433 and 604895 · ${SITE}</span><span class="pg-num">0${n}</span></div>`;
  const empty=`<p class="sn-empty">${esc(t('sn.empty'))}</p>`;
  const worksheetFor=f=>f&&(window.VahiniWorksheetCatalog||[]).find(w=>w.factors.includes(f.n));
  const sheetBase=()=>window.VahiniWorksheets?VahiniWorksheets.base():'https://'+SITE;
  const sheetURL=sheet=>`${sheetBase()}/assets/worksheets/${sheet.id}.pdf`;
  // #84: the practice sheet for each skill, from the worksheet catalogue the
  // website generates (same PDFs as the practice library).
  const practiceSheet=f=>{
    const sheet=worksheetFor(f);
    return sheet?`<p class="practice-sheet">${esc(t('row.sheet'))} <a href="${esc(sheetURL(sheet))}">${esc(sheet.title)} (PDF)</a></p>`:'';
  };
  // The last check saved in this browser, for the change line and the chips.
  const prev=history&&history.date?history:null;
  const prevScore=Object.fromEntries((prev&&Array.isArray(prev.factors)?prev.factors:[]).map(f=>[f.n,f.score]));
  const fmtDay=d=>{const day=new Date(d+'T00:00:00');return Number.isNaN(day.getTime())?d:day.toLocaleDateString(t.locale,{day:'numeric',month:'long'});};
  // #82: a skill counts as better from +0.3. The same page sent as PNG and
  // as JPEG moved factor scores by up to 0.2, so a smaller rise can be noise.
  const BETTER_BY=0.3;
  const gain=f=>Number.isFinite(prevScore[f.n])?f.score-prevScore[f.n]:null;
  const improved=measured.filter(f=>gain(f)!==null&&gain(f)>=BETTER_BY-1e-9);
  // Scores stay internal; the report says how many skills got better
  // (owner, 2026-10-23: no numbers on the report).
  const sinceLine=prev&&improved.length
    ?`<p class="since-last">${esc(t('sn.since',{date:fmtDay(prev.date)}))} ${esc(t.n('sn.since.better',improved.length))}</p>`:'';
  const wholePageCrop=c=>{const b=c&&c.bbox,s=c&&c.source_size;
    return Array.isArray(b)&&b.length===4&&Array.isArray(s)&&s.length===2&&b[2]*b[3]>0.8*s[0]*s[1];};

  /* ---- practice chosen for this report (many-to-many) ------------------ */
  const latin=latinPage(sources.map(r=>r.text).join(' ')||recognizedText);
  const lastPractice=(prev&&prev.practice)||{};
  const chosen=window.VahiniPracticeSelect
    ? VahiniPracticeSelect.select({rows:rowFactors,measured,cat,limits:lim,latin,last:lastPractice})
    : {rows:rowFactors.map(f=>({f,exercises:[],tips:[],band:bandOf(f.score),planBand:bandOf(f.score)})),printed:{exercises:{},tips:{}}};
  const printed=chosen.printed;
  const firstRow=chosen.rows[0]||null;
  const firstEx=firstRow&&firstRow.exercises[0]?localEntry(firstRow.exercises[0].entry,t.lang):null;
  const firstExModel=firstRow&&firstRow.exercises[0]?firstRow.exercises[0].entry:null;

  /* ---- page 1: "Your writing snapshot" (version C, owner approval
     2026-10-11) -------------------------------------------------------- */
  // No overall score on the report (owner, 2026-10-23): it is kept for
  // progress and comparison, never shown.
  const best=sorted.slice().sort((a,b)=>b.score-a.score||a.n-b.n)[0]||measured.slice().sort((a,b)=>b.score-a.score||a.n-b.n)[0];
  /* Vidhya's note (owner, 2026-10-14): the page opens the way a teacher
     writes on a child's work. What went well, the one or two skills to
     work on next, a promise to practise, and her score for the page.
     Vidhya is the series' teacher; her picture comes from the host like
     every character. Built only from this report's own scores. */
  const goalOf=f=>t.has('goal.'+f.n)?t('goal.'+f.n):nameOn(1,f)+'.';
  /* Vidhya's note in words, no scores (owner, 2026-10-23): what the writer
     is a master at beside what to improve next, as a two-column table.
     Praise comes only from five skills at Mastering or Strong (1, 5, 7,
     11, 17: the set #305 proposes for the overall, its
     scoring._OVERALL_POINTS), so a measurement known to misread a page
     never praises it. */
  const COUNTED=[1,5,7,11,17];
  const mastered=measured.filter(f=>COUNTED.includes(f.n)&&f.score>=7&&!rowFactors.includes(f))
    .sort((a,b)=>b.score-a.score||a.n-b.n).slice(0,3);
  const skillOf=n=>measured.find(f=>f.n===n);
  const clear=skillOf(1), easy=skillOf(18);
  const opening=clear&&clear.score>=8.5&&easy&&easy.score>=7?t('vt.open.beautiful')
    :(clear&&clear.score>=7)||(easy&&easy.score>=7)?t('vt.open.nice'):t('vt.open.thanks');
  const praised=mastered.map(f=>t.has('well.'+f.n)?t('well.'+f.n):t('keep.title.'+f.n));
  const improve=rowFactors.slice(0,2).map(goalOf);
  const noteRows=Math.max(praised.length,improve.length);
  const noteTable=noteRows?`<table class="sn-note-table"><thead><tr><th scope="col">${esc(t('vt.master'))}</th><th scope="col">${esc(t('vt.improve'))}</th></tr></thead>
      <tbody>${Array.from({length:noteRows},(_,r)=>`<tr><td>${esc(praised[r]||'')}</td><td>${esc(improve[r]||'')}</td></tr>`).join('')}</tbody></table>`
    :`<p class="sn-grow">${esc(t('vt.grow.none'))}</p>`;
  const keepN=(mastered[0]||best||{}).n;
  const teacherNote=best?`<div class="sn-teacher">${artImg('teacher','rp-art-teacher')}<div class="sn-note">
      <h2 class="sn-title">${esc(t('sn.title'))}</h2>
      <p class="sn-keep" data-factor="${keepN}"><span class="sn-hello">${esc(writer?t('vt.hello.name',{name:writer}):t('vt.hello'))}</span> ${esc(opening)}</p>
      ${noteTable}
      <div class="sn-note-end"><p class="sn-promise">${esc(t('vt.promise'))}</p><p class="sn-sign">${esc(t('vt.sign'))}</p></div></div></div>`
    :`<h2 class="sn-title">${esc(t('sn.title'))}</h2>`;
  // "Look closer": the first two skills to grow; a spelling finding may
  // take the second row.
  const lookItems=rowFactors.slice(0,2).map(f=>({f}));
  if(firstSpelling){ if(lookItems.length>=2) lookItems[1]={spelling:firstSpelling}; else lookItems.push({spelling:firstSpelling}); }
  // The photo, zoomed to the parts the rows point at: an SVG viewBox over
  // the photo (meet), every numbered box kept whole.
  const det=data.detURL||'';
  // The measurement rows below carry the drawings; the photo is shown
  // whole, without numbered boxes.
  const marks=[];
  const size=[...lookItems.map(it=>it.f&&crops[it.f.n]?.source_size),...Object.values(crops).map(c=>c&&c.source_size)].find(s=>Array.isArray(s)&&s.length===2&&s[0]>0&&s[1]>0);
  const zoom=()=>{
    if(!det) return '';
    if(!size) return `<figure class="sn-zoom"><div class="sn-zoom-frame"><img src="${esc(det)}" alt="${esc(t('sn.zoom.alt'))}"></div><figcaption><span>${esc(t('sn.zoom.whole'))}</span></figcaption></figure>`;
    const [W,H]=size;
    let x0=0,y0=0,x1=W,y1=H;
    if(marks.length){
      x0=Math.min(...marks.map(m=>m.b[0])); y0=Math.min(...marks.map(m=>m.b[1]));
      x1=Math.max(...marks.map(m=>m.b[0]+m.b[2])); y1=Math.max(...marks.map(m=>m.b[1]+m.b[3]));
      const pad=0.06*W;
      x0=Math.max(0,x0-pad); y0=Math.max(0,y0-pad*1.6); x1=Math.min(W,x1+pad); y1=Math.min(H,y1+pad);
      // Widen to the frame's shape where the photo allows; never cut a box.
      const want=1.75; let w=x1-x0, h=y1-y0;
      if(w/h<want){ const nw=Math.min(W,h*want), cx=(x0+x1)/2; x0=Math.max(0,Math.min(W-nw,cx-nw/2)); x1=x0+nw; }
      else { const nh=Math.min(H,w/want), cy=(y0+y1)/2; y0=Math.max(0,Math.min(H-nh,cy-nh/2)); y1=y0+nh; }
    }
    const vw=x1-x0, r=Math.max(vw*0.035,6);
    const boxes=marks.map(m=>{const [bx,by,bw,bh]=m.b;
      return `<g class="sn-mark" data-mark="${m.num}"><rect x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="${(r*0.4).toFixed(1)}" stroke-width="${(vw*0.006).toFixed(2)}"/><circle cx="${bx+bw/2}" cy="${by}" r="${r.toFixed(1)}" stroke-width="${(vw*0.004).toFixed(2)}"/><text x="${bx+bw/2}" y="${(by+r*0.42).toFixed(1)}" font-size="${(r*1.2).toFixed(1)}" text-anchor="middle">${m.num}</text></g>`;}).join('');
    return `<figure class="sn-zoom"><div class="sn-zoom-frame"><svg viewBox="${x0.toFixed(1)} ${y0.toFixed(1)} ${vw.toFixed(1)} ${(y1-y0).toFixed(1)}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(t('sn.zoom.alt'))}" data-view="${[x0,y0,x1,y1].map(v=>v.toFixed(1)).join(' ')}"><image href="${esc(det)}" x="0" y="0" width="${W}" height="${H}" preserveAspectRatio="none"/>${boxes}</svg></div>
      <figcaption><span>${esc(t('sn.zoom.caption'))}</span><span>${marks.length?esc(t.n('sn.zoom.marks',marks.length)):''}</span></figcaption></figure>`;
  };
  const startCard=first?`<div class="sn-start" data-factor="${first.n}"><div class="sn-start-top">${LEAF}<span class="sn-pill">${esc(t('sn.start'))}</span></div>${SPARK}
      <h3>${esc(t.has('goal.'+first.n)?t('goal.'+first.n):nameOn(1,first))}</h3>${stepList(t.has('look.'+first.n)?t('look.'+first.n):'').map(s=>`<p>${esc(s)}</p>`).join('')}
      <p class="sn-meta">${esc(nameOn(1,first))} · <span class="sn-band-text band-${bandOf(first.score)}">${esc(stage(bandOf(first.score)))}</span></p>
      <span class="sn-try">${PENCIL}${esc(t('sn.start.try.'+(firstExModel&&t.has('sn.start.try.'+firstExModel.unit)?firstExModel.unit:'row')))}</span></div>`:'';
  const chipList=measured.slice().sort((a,b)=>a.n-b.n);
  /* ---- "What we measured on your page" (owner, 2026-10-13, #137): one
     row per real measurement, drawn on the writer's own page as it was
     measured (no circles), with every score built from it. Free sees every
     measurement; scores outside its tier are named, not hidden. Estimates,
     blends and the pen skills are labelled as what they are. ------------ */
  const chipHTML=f=>{const band=bandOf(f.score), g=improved.includes(f);
    return `<div class="sn-chip" data-factor="${f.n}"><span class="sn-ic">${iconSVG(f.n)}</span><span class="sn-cn">${esc(t.has('chip.'+f.n)?t('chip.'+f.n):skillName(f))}</span><b class="band-${band}" data-band="${band}">${esc(stage(band))}${g?`<span class="sn-up" title="${esc(t('sn.chip.better'))}">↑</span>`:''}</b></div>`;};
  // Strongest first, wherever skills are listed (owner, 2026-10-23).
  const byScore=ns=>ns.slice().sort((a,b)=>(live(b)?live(b).score:-1)-(live(a)?live(a).score:-1)||a-b);
  const rowScore=r=>{const v=r.scores.map(live).filter(Boolean).map(f=>f.score);return v.length?v.reduce((x,y)=>x+y,0)/v.length:-1;};
  const ms=data.measurements||{};
  const live=n=>measured.find(f=>f.n===n);
  const scoreChip=n=>{const f=live(n);
    if(f) return chipHTML(f);
    return `<div class="sn-lockchip" data-locked="${n}"><span class="sn-cn">${esc(t('chip.'+n))}</span><i>${esc(t(free?'m.full':'m.nophoto'))}</i></div>`;};
  // A strip of the photo around one region, with drawings on top in
  // processed-image pixels (the photo is drawn at its own size).
  const strip=(region,draw,cls='')=>{
    if(!det||!size||!region) return '';
    const [W,H]=size;
    let [x0,y0,x1,y1]=region;
    x0=Math.max(0,x0); y0=Math.max(0,y0); x1=Math.min(W,x1); y1=Math.min(H,y1);
    const want=3.2; let w=x1-x0, h=y1-y0;
    if(w/h<want){ const nw=Math.min(W,h*want), cx=(x0+x1)/2; x0=Math.max(0,Math.min(W-nw,cx-nw/2)); x1=x0+nw; }
    else { const nh=Math.min(H,w/want), cy=(y0+y1)/2; y0=Math.max(0,Math.min(H-nh,cy-nh/2)); y1=y0+nh; }
    const vw=x1-x0;
    return `<div class="sn-m-strip${cls}"><svg viewBox="${x0.toFixed(1)} ${y0.toFixed(1)} ${vw.toFixed(1)} ${(y1-y0).toFixed(1)}" preserveAspectRatio="xMidYMid slice" role="img" aria-label="${esc(t('m.strip.alt'))}"><image href="${esc(det)}" x="0" y="0" width="${W}" height="${H}" preserveAspectRatio="none"/>${draw(vw)}</svg></div>`;
  };
  const line=(p,q,cls,sw,dash)=>`<line class="${cls}" x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" stroke-width="${sw.toFixed(2)}"${dash?` stroke-dasharray="${dash}"`:''}/>`;
  const pad=(b,fx,fy)=>[b[0]-b[2]*fx,b[1]-b[3]*fy,b[0]+b[2]*(1+fx),b[1]+b[3]*(1+fy)];
  const mRows=[];
  // 1. Gaps between words: brackets in the gaps the analyser measured.
  const gaps=((crops[8]||{}).places||[]).filter(p=>p.role==='look'&&p.kind==='gap'&&Array.isArray(p.bbox));
  if(gaps.length&&size){
    const g=gaps[0].bbox, W=size[0];
    const region=[g[0]-0.16*W,g[1]-g[3]*0.15,g[0]+g[2]+0.16*W,g[1]+g[3]*1.15];
    const inside=gaps.filter(p=>p.bbox[1]<region[3]&&p.bbox[1]+p.bbox[3]>region[1]);
    const draw=vw=>inside.map(p=>{const [x,y,w,h]=p.bbox, my=y+h/2, sw=vw*0.009;
      return line([x,my],[x+w,my],'sn-m-gap',sw)+line([x,y+h*0.3],[x,y+h*0.7],'sn-m-gap',sw)+line([x+w,y+h*0.3],[x+w,y+h*0.7],'sn-m-gap',sw);}).join('');
    mRows.push({key:'gaps',strip:strip(region,draw),text:t(gaps[0].direction==='narrower'?'m.gaps.narrower':'m.gaps.wider'),scores:[8]});
  }
  // 2. How each line sits: the steepest line's fitted baseline in red,
  //    against a dashed level line from the same start.
  if(ms.slope&&ms.slope.line){
    const L=ms.slope.line, [p,q]=L.baseline;
    const draw=vw=>line(p,[q[0],p[1]],'sn-m-level',vw*0.006,'8 6')+line(p,q,'sn-m-slope',vw*0.01);
    // Written as a teacher would say it: nearly straight below 3 degrees
    // on average; the red line climbs when its right end is higher.
    const lean=t(ms.slope.mean_deg<3?'m.slope.flat':'m.slope.tilt')+' '+t(q[1]<p[1]?'m.slope.up':'m.slope.down');
    mRows.push({key:'slope',strip:strip(pad(L.bbox,0.04,0.35),draw),text:lean,scores:[7,11,12,17]});
  }
  // 3. How tall the small letters are: the line's small-letter band.
  if(ms.size&&ms.size.line){
    const L=ms.size.line;
    const draw=vw=>line(L.midline[0],L.midline[1],'sn-m-band',vw*0.007)+line(L.baseline[0],L.baseline[1],'sn-m-band',vw*0.007);
    mRows.push({key:'size',strip:strip(pad(L.bbox,0.02,0.3),draw),text:t('m.size.text'),scores:[5,6]});
  }
  // 4. Where each line starts: the usual starting edge, and an arrow to a
  //    line that starts away from it.
  if(ms.margin&&size){
    const M=ms.margin, o=(M.off||[])[0], W=size[0];
    const region=o?[M.usual_x-0.05*W,o.bbox[1]-o.bbox[3]*1.4,M.usual_x+0.42*W,o.bbox[1]+o.bbox[3]*1.2]
      :[M.usual_x-0.05*W,M.top,M.usual_x+0.42*W,M.top+0.18*size[1]];
    const draw=vw=>line([M.usual_x,region[1]],[M.usual_x,region[3]],'sn-m-edge',vw*0.007,'10 7')+(o?(()=>{const y=o.bbox[1]+o.bbox[3]/2, x=o.bbox[0], s=vw*0.02;
      return line([M.usual_x,y],[x-s*0.3,y],'sn-m-arrow',vw*0.009)+line([x-s*1.2,y-s*0.7],[x-s*0.3,y],'sn-m-arrow',vw*0.009)+line([x-s*1.2,y+s*0.7],[x-s*0.3,y],'sn-m-arrow',vw*0.009);})():'');
    mRows.push({key:'margin',strip:strip(region,draw),text:t(o?'m.margin.text':'m.margin.even'),scores:[10]});
  }
  // 5. How easy the writing is to read: the hardest line, underlined,
  //    and on it up to two letters the reader was least sure of, circled
  //    (owner, 2026-10-14; letter_boxes.hardest_letters).
  if(ms.reading&&ms.reading.line){
    const L=ms.reading.line, [x,y,w,h]=L.bbox;
    const [u0,u1]=L.underline||[[x,y+h*0.98],[x+w,y+h*0.98]];
    const hard=(Array.isArray(L.letters)?L.letters:[]).filter(l=>Array.isArray(l.bbox)&&l.bbox.length===4).slice(0,2);
    const ring=(b,vw)=>`<ellipse class="sn-m-read sn-m-ring" cx="${b[0]+b[2]/2}" cy="${b[1]+b[3]/2}" rx="${(Math.max(b[2],b[3]*0.32)*0.85).toFixed(1)}" ry="${(b[3]*0.55).toFixed(1)}" stroke-width="${(vw*0.007).toFixed(2)}"/>`;
    const draw=vw=>line(u0,u1,'sn-m-read',vw*0.008,'7 5')+hard.map(l=>ring(l.bbox,vw)).join('');
    const said=t(ms.reading.confidence_pct>=70?'m.read.easy':'m.read.hard')+' '+t(hard.length>1?'m.read.circled':hard.length?'m.read.circled.one':'m.read.line');
    mRows.push({key:'read',strip:strip(pad(L.bbox,0.03,0.3),draw),text:said,how:t(hard.length?'m.read.how':'m.read.how.line'),scores:[1,19]});
  }
  const mRow=r=>`<div class="sn-m" data-measure="${r.key}">${r.strip||'<div class="sn-m-strip sn-m-none"></div>'}<div class="sn-m-what"><h4>${esc(t('m.'+r.key+'.h'))}</h4><p>${esc(r.text)} <small>${esc(r.how||t('m.'+r.key+'.how'))}</small></p></div><div class="sn-m-scores">${byScore(r.scores).map(scoreChip).join('')}</div></div>`;
  const group=(label,ns)=>`<div class="sn-m-group"><b>${esc(label)}</b><div class="sn-m-scores sn-m-row">${byScore(ns).map(scoreChip).join('')}</div></div>`;
  const counts=data.pipeline||{};
  const mSub=t('m.sub',{lines:ms.lines||counts.nLines||0,words:counts.nWords||0,letters:counts.nChars||0});
  const pen=`<div class="sn-m-pen"><p>${PENCIL}<span><b>${esc(t('m.pen'))}</b> ${esc(t('m.pen.text'))}</span></p><div class="sn-m-scores sn-m-row">${[13,14,15,16].map(n=>live(n)?chipHTML(live(n)):`<span class="sn-pen-skill">${esc(t('chip.'+n))}</span>`).join('')}</div></div>`;
  // The whole map, measurement by measurement, on screen only: what we
  // measure, the scores built from it, and whether a page can show it.
  const TABLE=[['height',[5,6],'yes'],['angle',[7,11],'yes'],['spread',[12,17],'no'],['gaps',[8],'exact'],['edges',[10],'yes'],['confidence',[1,19],'line'],['widths',[2,9,4],'no'],['loops',[3],'no'],['blends',[18,20],'no'],['pen',[13,14,15,16],'pen']];
  const howTable=`<details class="sn-m-how screen-only" data-html2canvas-ignore="true"><summary>${esc(t('m.table.title'))}</summary><table><thead><tr><th>${esc(t('m.table.what'))}</th><th>${esc(t('m.table.scores'))}</th><th>${esc(t('m.table.shown'))}</th></tr></thead><tbody>${TABLE.map(([k,ns,shown])=>`<tr data-measure="${k}"><td>${esc(t('m.t.'+k))}</td><td>${ns.map(n=>esc(t('chip.'+n))).join(', ')}</td><td>${esc(t('m.shown.'+shown))}</td></tr>`).join('')}</tbody></table></details>`;
  // A score whose measurement row could not be drawn (no photo, or too
  // little to measure) is still shown, never dropped.
  const shownN=new Set([...mRows.flatMap(r=>r.scores),18,20,2,9,4,3,13,14,15,16]);
  const leftover=measured.filter(f=>!shownN.has(f.n)).map(f=>f.n).sort((a,b)=>a-b);
  const measuredHTML=`<div class="sn-h3row"><h3 class="sn-h3">${esc(t('m.title'))}</h3><small>${esc(t('sn.chips.note'))}</small></div>
      <p class="sn-m-sub">${esc(mSub)}</p>${mRows.slice().sort((a,b)=>rowScore(b)-rowScore(a)).map(mRow).join('')}
      ${leftover.length?group(t('m.other'),leftover):''}${group(t('m.built'),[18,20])}${group(t('m.est'),[2,9,4,3])}${pen}${howTable}`;
  // The first practice: its steps, its example to trace between two guide
  // lines, its self-check and a QR code for the full practice sheet.
  const firstSheet=worksheetFor(first)||rowFactors.map(worksheetFor).find(Boolean)||null;
  const qr=firstSheet?qrSVG(sheetURL(firstSheet)):'';
  const practice=firstEx?`<div class="sn-prac" data-exercise="${esc(firstEx.id)}"><div class="sn-prac-head">${LEAF}<h3>${esc(t('sn.prac'))}</h3></div>
      <div class="sn-pgrid${qr?'':' no-qr'}"><ol class="sn-steps">${stepList(firstEx.steps).slice(0,3).map((s,k)=>`<li><i>${k+1}</i><span>${esc(s)}</span></li>`).join('')}</ol>
      <div class="sn-turn" aria-label="${esc(t('sn.turn.aria'))}"><b>${esc(t('sn.turn'))}</b><div class="sn-guide"><span class="md-hand">${esc(firstEx.example||MODEL_WORDS[firstEx.model]||'')}</span></div><div class="sn-guide"></div><p class="sn-chk"><i aria-hidden="true"></i>${esc(firstEx.check)}</p></div>
      ${qr?`<div class="sn-qr" aria-label="${esc(t('sn.qr.alt'))}">${qr}<span>${esc(t('sn.qr'))}</span></div>`:''}</div></div>`:'';
  const cta=`<div class="sn-cta screen-only" data-html2canvas-ignore="true">${firstSheet?`<a class="sn-b1" href="${esc(sheetURL(firstSheet))}" target="_blank" rel="noopener">⇩&nbsp; ${esc(t('sn.download'))}</a>`:''}<a class="sn-b2" href="analyser.html" data-action="new-report">↻&nbsp; ${esc(t('sn.again'))}</a></div>`;
  const page1Note=[t('sn.note'),spellingStatus,rec.printed_lines>0?t.n('note.printed',rec.printed_lines):''].filter(Boolean).join(' ');
  const page1=`<section class="page free-report compact-report snapshot-page snapshot-${tier}" data-screen-label="Your review">
      <div class="sn-top">${brand}<div class="sn-right"><span class="sn-eyebrow">${esc(t('sn.eyebrow'))}</span>${writer?`<span class="sn-writer">${esc(writer)}</span>`:''}</div></div>
      ${teacherNote}${sinceLine}
      ${measured.length?`
      <div class="sn-mid${det?'':' no-photo'}">${zoom()}${startCard}</div>
      ${measuredHTML}
      ${practice}${cta}`:empty}
      ${foot(1,page1Note)}</section>`;

  /* ---- page 2: the practice sheet, each skill beside its exercise ------ */
  const unitText=u=>esc(t.has('try.'+u)?t('try.'+u):t('try.other',{unit:u||'row'}));
  const dose=band=>(cat&&cat.dosage&&cat.dosage[band])||null;
  const planText=(band,count)=>{
    const d=dose(band);
    if(!d) return t('plan.none');
    if(d.per==='week') return t('plan.week',{tries:d.tries,weeks:Math.round(d.recheck_days/7)});
    return t(count>1?'plan.day.all':'plan.day',{tries:d.tries,days:d.days});
  };
  const exerciseBlock=(x,f)=>{
    const ex=localEntry(x.entry,t.lang), kind=x.entry.model;
    const model=modelHTML(kind, x.entry.example)||`<div class="md md-focus">${focusSVG({...f,band:'strong'}).svg}</div>`;
    return `<div class="pr-ex" data-exercise="${esc(ex.id)}" data-model="${esc(kind||'focus')}"><p class="pr-ex-title"><b>${esc(ex.title)}</b> <span class="pr-unit">${unitText(ex.unit)}</span></p>
      <ol class="pr-steps">${stepList(ex.steps).map(s=>`<li>${esc(s)}</li>`).join('')}</ol>
      <div class="pr-model"><span class="pr-model-label">${esc(t('row.copy'))}</span><div class="pr-model-art">${model}</div></div></div>`;
  };
  const tipBlock=tip=>`<p class="pr-tip" data-tip="${esc(tip.id)}">${artImg('tip','rp-art-tip')}<span><b>${esc(t('tip.label'))}</b> ${esc(tip.text)}</span></p>`;
  const stagePath=band=>{
    const at=STAGE_ORDER.indexOf(band);
    return `<p class="pr-path" aria-label="${esc(t('row.stage.aria',{stage:stage(band)}))}">${STAGE_ORDER.map((b,k)=>
      `<span class="pr-stage${k<at?' done':k===at?' now':''}">${esc(stage(b))}${k<at?' ✓':''}</span>`).join('<span class="pr-arrow">→</span>')}</p>`;
  };
  // Under each skill: why it helps, the win to look for and its page on the
  // website (linked on screen, the address when printed). trimSkillColumns()
  // drops these, "More" first, when they would make the row taller.
  const aboutBlock=f=>{
    const a=factorAbout(cat,f.n,t.lang);
    if(!a) return '';
    // The printed text is the short address (vahinitech.com redirects it
    // once to the page, vahini-web#210); the link keeps the canonical URL.
    const url=a.page?`${sheetBase()}/${a.page}.html`:'';
    return `<div class="pr-about"><p class="pr-why"><b>${esc(t('row.why'))}</b>${esc(a.why)}</p>
        <p class="pr-win"><b>${esc(t('row.win'))}</b> ${esc(a.win)}</p>${url?`
        <p class="pr-more">${esc(t('row.more'))} <a href="${esc(url)}" target="_blank" rel="noopener">${SITE}/${esc(a.page)}</a></p>`:''}</div>`;
  };
  const skillRow=(row,i)=>{
    const f=row.f, band=bandOf(f.score);
    const exs=row.exercises, tips=row.tips.map(e=>localEntry(e,t.lang));
    const lastKind=exs.length?exs[exs.length-1].entry.model:'line';
    return `<article class="practice-row coaching-card band-${band}" data-factor="${f.n}">
      <div class="pr-skill"><div class="pr-head"><h3>${i+1}. ${esc(nameOn(2,f))}</h3><span class="pr-badge band-${band}">${esc(stage(band))}</span></div>
        ${stagePath(band)}${aboutBlock(f)}${practiceSheet(f)}</div>
      <div class="pr-practice">${exs.map(x=>exerciseBlock(x,f)).join('')||`<p class="pr-steps">${esc(t('row.fallback'))}</p>`}
        <p class="pr-plan">${esc(planText(row.planBand||band,exs.length))}</p>${tips.length?`<div class="pr-tips">${tips.map(tipBlock).join('')}</div>`:''}
        <div class="pr-turn-row"><span class="pr-turn">${esc(t('row.turn'))}</span><div class="writing-lines pr-line" aria-label="${esc(t('row.line.aria'))}">${turnHTML(lastKind)}</div></div></div>
    </article>`;
  };
  const spellingRow=n=>{
    const f=firstSpelling, area=cat&&cat.spelling;
    const ex=area&&area.exercises&&area.exercises[0];
    const tips=area?rotate(area.tips||[],(lastPractice.tips||{}).spelling,lim.tips_max):[];
    if(ex) printed.exercises.spelling=[ex.id];
    printed.tips.spelling=tips.map(e=>e.id);
    const d=dose('good');
    return `<article class="practice-row coaching-card spelling-row" data-factor="spelling">
      <div class="pr-skill"><div class="pr-head"><h3>${n}. ${esc(t('spell.title'))}</h3><span class="pr-badge spelling">${esc(t('spell.badge'))}</span></div>
        <p class="pr-saw">${t.html('spell.saw',{word:`<b>${esc(f.word)}</b>`,suggestion:`<b>${esc(f.suggestion)}</b>`})}</p></div>
      <div class="pr-practice">${ex?exerciseBlock({entry:{...ex,example:f.suggestion}},{n:1,band:'strong'}):''}
        <p class="pr-plan">${esc(t('spell.plan',{tries:d?d.tries:5,days:d?d.days:7}))}</p>${tips.length?`<div class="pr-tips">${tips.map(e=>tipBlock(localEntry(e,t.lang))).join('')}</div>`:''}<div class="writing-lines pr-line" aria-label="${esc(t('spell.line.aria'))}">${turnHTML('line')}</div></div>
    </article>`;
  };
  const rows=chosen.rows.map(skillRow).join('')+(firstSpelling?spellingRow(chosen.rows.length+1):'');
  const others=measured.filter(f=>!rowFactors.includes(f)).sort((a,b)=>b.score-a.score||a.n-b.n);
  const praise=f=>{const b=bandOf(f.score);
    if([18,20].includes(f.n)&&(b==='focus'||b==='dev')) return t('other.composite');
    return b==='strong'?t('other.strong'):b==='good'?t('other.good'):'';};
  const locked=Math.max(0,20-analysis.results.length);
  const otherBox=others.length||free?`<div class="other-skills">${others.length?`<p class="os-list"><b>${esc(t('other.title'))}</b> ${others.map(f=>`<span data-factor="${f.n}">${esc(t('other.item',{skill:nameOn(2,f),stage:stage(bandOf(f.score))}))}${praise(f)?': '+esc(praise(f)):''}</span>`).join(' · ')}</p>`:''}
      ${free&&locked?`<p class="pro-note"><b>${esc(t('pro.ask'))}</b> ${esc(t('pro.more',{n:locked}))}</p>`:''}</div>`:'';
  // When writing feels hard: encouragement and where to read more, never a
  // diagnosis or a promise (owner, 2026-10-11).
  const hardURL=`${sheetBase()}/signs-child-needs-handwriting-help.html`;
  const hardNote=`<div class="p2-hard"><p><b>${esc(t('hard.title'))}</b> ${esc(t('hard.text'))} ${esc(t('hard.more'))} <a href="${esc(hardURL)}" target="_blank" rel="noopener">${SITE}/signs-child-needs-handwriting-help</a></p></div>`;
  const closing=`<div class="p2-close">${artImg('encourage','rp-art-encourage')}<p><b>${esc(t('close.cheer'))}</b> ${esc(t('close.next'))}</p></div>`;
  const page2=`<section class="page free-report compact-report practice-page practice-${tier}" data-screen-label="Practise and improve">${head(t('head.page2'))}
      <h2>${esc(t('p2.title'))}</h2><p class="p2-sub">${esc(t('p2.sub'))}</p>
      ${rows?`<div class="practice-wrap"><div class="pr-cols" aria-hidden="true"><span>${esc(t('p2.cols.skill'))}</span><span>${esc(t('p2.cols.how'))}</span></div><div class="practice-table">${rows}</div></div>${otherBox}${hardNote}${closing}`:empty}
      ${foot(2)}</section>`;
  /* ---- the student view (owner, 2026-10-23, option A) ------------------
     One screen above the two pages, for a student reading alone: one
     strength, one thing to practise and the five free skills, with no score
     and no skill names. Every sentence sits beside its proof, drawn from
     what the server measured on this page: the "keep" and "look" places of
     each skill (vision/marked_places.py) and the page measurements. A skill
     with no proof says so instead of making a claim. The pages stay as they
     are, folded behind "Details for your teacher" on screen; print and the
     shared PDF are unchanged. ---------------------------------------- */
  const student=(data.audience||audience())==='student';
  const studentCard=()=>{
    const FIVE=[1,5,7,8,18];
    const live5=measured.filter(f=>FIVE.includes(f.n));
    const placesOf=(n,role)=>((crops[n]||{}).places||[]).filter(p=>p.role===role&&Array.isArray(p.bbox)&&p.bbox.length===4);
    const S=ms.size&&ms.size.line, L=ms.slope&&ms.slope.line, R=ms.reading&&ms.reading.line;
    const under=(b,cls,dash)=>vw=>line([b[0],b[1]+b[3]],[b[0]+b[2],b[1]+b[3]],cls,vw*0.008,dash);
    const boxes=(list,cls)=>vw=>list.map(q=>{const [x,y,w,h]=q.bbox;
      return `<rect class="${cls}" x="${x}" y="${y}" width="${w}" height="${h}" rx="${(vw*0.004).toFixed(1)}" stroke-width="${(vw*0.008).toFixed(2)}"/>`;}).join('');
    const gapRegion=g=>[g[0]-0.16*size[0],g[1]-g[3]*0.15,g[0]+g[2]+0.16*size[0],g[1]+g[3]*1.15];
    const band=vw=>line(S.midline[0],S.midline[1],'sn-m-band',vw*0.007)+line(S.baseline[0],S.baseline[1],'sn-m-band',vw*0.007);
    const rings=(list,vw)=>list.map(l=>{const b=l.bbox;
      return `<ellipse class="sn-m-read sn-m-ring" cx="${b[0]+b[2]/2}" cy="${b[1]+b[3]/2}" rx="${(Math.max(b[2],b[3]*0.32)*0.85).toFixed(1)}" ry="${(b[3]*0.55).toFixed(1)}" stroke-width="${(vw*0.007).toFixed(2)}"/>`;}).join('');
    const ok=(html,say,extra)=>html?{strip:html,say,...(extra||{})}:null;
    // What this page shows well, skill by skill: the server's "keep" place.
    const keepProof={
      1:()=>{const q=placesOf(1,'keep')[0]; return q&&ok(strip(pad(q.bbox,0.03,0.3),under(q.bbox,'sn-m-band')),'stu.keep.1');},
      5:()=>S&&placesOf(5,'keep').length?ok(strip(pad(S.bbox,0.02,0.3),band),'stu.keep.5'):null,
      7:()=>{const q=placesOf(7,'keep')[0]; return q&&ok(strip(pad(q.bbox,0.04,0.35),under(q.bbox,'sn-m-band')),'stu.keep.7');},
      8:()=>{const q=placesOf(8,'keep')[0]; return q&&size&&ok(strip(gapRegion(q.bbox),boxes([q],'sn-m-band')),'stu.keep.8');},
    };
    // What to look at: the server's "look" places and the page measurements.
    const lookProof={
      1:()=>{const hard=R&&Array.isArray(R.letters)?R.letters.filter(l=>Array.isArray(l.bbox)&&l.bbox.length===4).slice(0,2):[];
        return hard.length?ok(strip(pad(R.bbox,0.03,0.3),vw=>rings(hard,vw)),'stu.see.1',{todo:'stu.do.1'}):null;},
      5:()=>S?ok(strip(pad(S.bbox,0.02,0.3),band),'stu.do.5'):null,
      7:()=>{if(!L||!Array.isArray(L.baseline)) return null; const [a,b]=L.baseline;
        return ok(strip(pad(L.bbox,0.04,0.35),vw=>line(a,[b[0],a[1]],'sn-m-level',vw*0.006,'8 6')+line(a,b,'sn-m-slope',vw*0.01)),b[1]<a[1]?'stu.see.7.up':'stu.see.7.down',{todo:'stu.do.7'});},
      8:()=>{const gaps=placesOf(8,'look').filter(q=>q.kind==='gap'); if(!gaps.length||!size) return null;
        const reg=gapRegion(gaps[0].bbox), inside=gaps.filter(q=>q.bbox[1]<reg[3]&&q.bbox[1]+q.bbox[3]>reg[1]);
        const say=inside.length>1?'stu.see.8.both':'stu.see.8.'+(inside[0].direction==='narrower'?'narrower':'wider');
        return ok(strip(reg,boxes(inside,'sn-m-gap')),say,{todo:'stu.do.8'});},
      18:()=>R?ok(strip(pad(R.bbox,0.03,0.3),under(R.bbox,'sn-m-read','7 5')),'stu.see.18'):null,
    };
    const proofOf=(f,role)=>{const fn=(role==='keep'?keepProof:lookProof)[f.n]; try{ return fn?fn():null; }catch(_e){ return null; }};
    // One skill to practise: the lowest of the five below Strong, as on page 1.
    const now=live5.filter(f=>f.n!==18&&f.score<8.5).sort((a,b)=>a.score-b.score||a.n-b.n)[0]||null;
    const state=f=>f===now?'now':f.n===18?'grow':f.score>=7?'keep':'later';
    const strong=live5.filter(f=>state(f)==='keep').sort((a,b)=>b.score-a.score||a.n-b.n);
    const shown=strong.map(f=>[f,proofOf(f,'keep')]).find(([,pr])=>pr);
    const ICON={keep:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>', now:PENCIL,
      later:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7"/></svg>',
      grow:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 17l5-5 4 4 5-7"/><path d="M15 9h4v4"/></svg>'};
    const mark=(st,label)=>`<span class="stu-mk stu-mk-${st}">${ICON[st]}${label?`<span>${esc(t('stu.tag.'+st))}</span>`:''}</span>`;
    const proofBox=pr=>pr?`<div class="stu-proof">${pr.strip}</div>`:'';
    const greet=writer?t('stu.greet.name',{name:writer}):t('stu.greet');
    const greetCard=`<div class="stu-card stu-greet"><div class="stu-who">${artImg('teacher','stu-art')}<p class="stu-say">${esc(greet)}</p></div>
      ${shown?`<p>${esc(t(shown[1].say))}</p>${proofBox(shown[1])}`:`<p>${esc(t(now?'stu.nostrength':'stu.allgood'))}</p>`}</div>`;
    let workCard='';
    if(now){
      const pr=proofOf(now,'look'), d=dose(bandOf(now.score)), sheet=worksheetFor(now);
      const plan=!d?'':d.per==='week'?t('stu.plan.week',{tries:d.tries}):d.days===7?t('stu.plan',{tries:d.tries}):t('stu.plan.days',{tries:d.tries,days:d.days});
      const todo=pr?(pr.todo||''):'stu.do.'+now.n;
      workCard=`<div class="stu-card stu-work" data-factor="${now.n}"><span class="stu-pill">${PENCIL}<span>${esc(t('stu.practise'))}</span></span>
        ${proofBox(pr)}<p>${esc(t(pr?pr.say:'stu.noproof'))}${todo&&t.has(todo)?` ${esc(t(todo))}`:''}</p>
        ${t.has('stu.why.'+now.n)?`<p class="stu-why">${esc(t('stu.why.'+now.n))}</p>`:''}
        ${plan?`<div class="stu-plan">${artImg('practise','stu-plan-art')}<span>${esc(plan)}</span></div>`:''}
        ${sheet?`<a class="stu-btn" href="${esc(sheetURL(sheet))}" target="_blank" rel="noopener">${esc(t('stu.sheet'))}</a>`:''}
        <p class="stu-again">${esc(t('stu.again'))}</p></div>`;
    }
    const order={keep:0,now:1,later:2,grow:3};
    const rowsOf=live5.slice().sort((a,b)=>order[state(a)]-order[state(b)]||(state(a)==='keep'?b.score-a.score:a.score-b.score)||a.n-b.n);
    const fiveRows=rowsOf.map(f=>{const st=state(f), pr=proofOf(f,st==='keep'?'keep':'look');
      return `<li class="stu-row stu-row-${st}" data-factor="${f.n}" data-state="${st}">${mark(st,false)}<div class="stu-row-body"><p>${esc(t(pr?pr.say:'stu.noproof'))} ${mark(st,true)}</p>${proofBox(pr)}</div></li>`;}).join('');
    const fiveCard=`<div class="stu-card stu-five"><h2>${esc(t.n('stu.five',live5.length))}</h2><ul>${fiveRows}</ul></div>`;
    // Words and sentences to check (#317): only what the server's
    // language check found, each shown as the child's own ink at its
    // place and the word to write. Never our reading of the child's word,
    // which can be off by a letter, and never "no mistakes": nothing
    // found, or a page not checked, shows no card.
    const lgSec=data.language&&data.language.checked?data.language:null;
    const lgPlace=f=>(f.places||[]).find(p=>Array.isArray(p.bbox)&&p.bbox.length===4);
    // A place estimated from the share of the line's text (not from the
    // letters) gets a wider cut, so the word is in it.
    const lgInk=(b,cls,wide)=>{
      if(!det||!size) return '';
      const [W,H]=size, px=Math.max(4,b[2]*(wide?0.45:0.08)), py=Math.max(4,b[3]*0.12);
      let x0=Math.max(0,b[0]-px), y0=Math.max(0,b[1]-py), x1=Math.min(W,b[0]+b[2]+px), y1=Math.min(H,b[1]+b[3]+py);
      // A one-letter word (i) still gets a square cut, not a sliver.
      const need=(y1-y0)-(x1-x0);
      if(need>0){ x0=Math.max(0,x0-need/2); x1=Math.min(W,x1+need/2); }
      return `<svg class="stu-ink${cls?' '+cls:''}" viewBox="${x0.toFixed(1)} ${y0.toFixed(1)} ${(x1-x0).toFixed(1)} ${(y1-y0).toFixed(1)}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(t('stu.lang.ink'))}"><image href="${esc(det)}" x="0" y="0" width="${W}" height="${H}" preserveAspectRatio="none"/></svg>`;
    };
    const LG_ARROW='<svg class="stu-arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h15"/><path d="M13 6l6 6-6 6"/></svg>';
    // One strip of the row that holds the first finding, every finding on
    // that row marked: rings round words, a line under sentences.
    const lgStrip=(list,mark)=>{
      const first=list.map(lgPlace).find(Boolean);
      if(!first) return '';
      const same=list.map(lgPlace).filter(p=>p&&p.line===first.line);
      const xs=same.map(p=>p.bbox), x0=Math.min(...xs.map(b=>b[0])), x1=Math.max(...xs.map(b=>b[0]+b[2]));
      const y0=Math.min(...xs.map(b=>b[1])), y1=Math.max(...xs.map(b=>b[1]+b[3]));
      return `<div class="stu-proof">${strip(pad([x0,y0,x1-x0,y1-y0],0.25,0.3),vw=>xs.map(b=>mark(b,vw)).join(''))}</div>`;
    };
    const lgRing=(b,vw)=>`<ellipse class="stu-m-word" cx="${b[0]+b[2]/2}" cy="${b[1]+b[3]/2}" rx="${(b[2]*0.62).toFixed(1)}" ry="${(b[3]*0.62).toFixed(1)}" stroke-width="${(vw*0.008).toFixed(2)}"/>`;
    const lgUnder=(b,vw)=>line([b[0],b[1]+b[3]*1.02],[b[0]+b[2],b[1]+b[3]*1.02],'stu-m-sentence',vw*0.009,'10 7');
    const lgFix=(f,why)=>{const p=lgPlace(f);
      return `<li class="stu-fix">${p?lgInk(p.bbox,'',p.placed==='estimated'):''}${LG_ARROW}<span class="stu-right">${esc(f.suggestion)}</span><span class="stu-fix-why">${esc(why)}</span></li>`;};
    const lgTip=key=>`<p class="stu-tip">${artImg('tip','stu-tip-art')}<span>${esc(t(key))}</span></p>`;
    let langCards='';
    if(lgSec){
      const words=(lgSec.spelling||[]).slice(0,3), sentences=(lgSec.grammar||[]).slice(0,3);
      const copied=words.some(f=>f.against==='sentence');
      const wordCard=words.length?`<div class="stu-card stu-words" data-lang="spelling"><span class="stu-pill stu-pill-lang">${esc(t('stu.sp.pill'))}</span>
        ${copied?`<p class="stu-lang-note">${esc(t('stu.sp.copied'))}</p>`:''}
        ${lgStrip(words,lgRing)}<ul class="stu-fixes">${words.map(f=>lgFix(f,t('stu.sp.'+f.kind))).join('')}</ul>${lgTip('stu.sp.tip')}</div>`:'';
      const sentenceCard=sentences.length?`<div class="stu-card stu-sentences" data-lang="grammar"><span class="stu-pill stu-pill-lang">${esc(t('stu.gr.pill'))}</span>
        ${lgStrip(sentences,lgUnder)}<ul class="stu-fixes">${sentences.map(f=>lgFix(f,t('stu.gr.'+f.rule))).join('')}</ul>${lgTip('stu.gr.tip')}</div>`:'';
      if(wordCard||sentenceCard) langCards=`<div class="stu-grid stu-lang">${wordCard}${sentenceCard}</div>`;
    }
    const more=`<button type="button" class="stu-more" aria-expanded="false" data-open="${esc(t('stu.teacher.hide'))}" data-closed="${esc(t('stu.teacher'))}">${esc(t('stu.teacher'))}</button>`;
    return `<section class="stu" aria-label="${esc(t('stu.label'))}" data-html2canvas-ignore="true"><div class="stu-grid">${greetCard}${workCard}</div>${fiveCard}${langCards}${more}</section>`;
  };
  host.classList.toggle('stu-view',student);
  host.classList.toggle('stu-folded',student);
  host.innerHTML=(student?studentCard():'')+page1+page2;
  if(student) wireStudent(host);
  // A PDF made for sharing showed the report as it was: make it again.
  if(window.VahiniReportShare) VahiniReportShare.invalidate();
  wirePrintFit(host);
  trimSkillColumns(host);
  if(document.fonts&&document.fonts.ready) document.fonts.ready.then(()=>trimSkillColumns(host));
  // What this report printed, so the next check can move on (app.js keeps
  // it with the check in this browser's history; nothing leaves it).
  return {practice:printed};
}

/* ---- print fit: keep "one report page = one printed sheet" honest --------
   .page boxes are designed as exactly one A4 sheet, but content height varies
   with names, recognition notes and reader fonts. Printing used to clamp the
   page and let flexbox squeeze the blocks into each other (the scrambled-print
   bug). Instead: measure each page before printing; FIT_MIN is a scale floor,
   not an overflow amount -- a page whose required shrink (sheetHeight/pageHeight)
   is still at or above FIT_MIN (0.84, i.e. shrinks by at most ~16%) is scaled
   down onto one sheet (width-compensated, so it still fills the full 210mm and
   text reflows slightly wider); a page that would need to shrink past that
   floor to be readable is left natural and flows onto a continuation sheet
   instead. */
const A4_MM = { w:210, h:296 };  /* 296: see report.css print note on 297mm */
const FIT_MIN = 0.84;            /* scale floor: below this, spill instead */
/* The free report is two sheets by design, and a real photo's text runs
   longer than the test fixture's: on 2026-10-07 its second sheet needed
   0.838, just under FIT_MIN, so it spilled and printed as 3-4 pages with
   blank ones between. Its pages may shrink a little further instead. */
const FIT_MIN_FREE = 0.78;
/* Fit to a little less than the sheet. A page that fills the sheet to the
   pixel (sheet 1 measured 1119px against 1118.7px) still tips onto a blank
   extra page in a real print dialog, through rounding. */
const FIT_SLACK_PX = 6;
/* Page 2's left column (why it helps, the win, "More") must never make a
   row taller than the practice beside it. When it would, drop "More" first,
   then the "why" sentence, then the win box, and mark the row with how far
   it went (data-trim). Only where the two columns sit side by side. */
const TRIM_STEPS = ['more', 'why', 'win'];
function trimSkillColumns(host){
  // The student view folds the pages on screen (display:none), where no row
  // can be measured. Open them for the measurement only, in this same task,
  // so nothing is painted open and page 2 trims as in today's report.
  const hosts = host && host.classList ? [host] : [...document.querySelectorAll('.report-host')];
  const opened = hosts.filter(h=>h.classList.contains('stu-folded') && !h.classList.contains('stu-printing'));
  opened.forEach(h=>h.classList.add('stu-printing'));
  try{ trimRows(host); }finally{ opened.forEach(h=>h.classList.remove('stu-printing')); }
}
function trimRows(host){
  (host || document).querySelectorAll('.practice-row').forEach(row=>{
    TRIM_STEPS.forEach(s=>row.classList.remove('trim-' + s));
    row.removeAttribute('data-trim');
    const left = row.querySelector('.pr-skill'), right = row.querySelector('.pr-practice');
    if (!left || !right || !left.querySelector('.pr-about')) return;
    if (getComputedStyle(row).gridTemplateColumns.split(' ').length < 2) return;
    const tall = ()=>{
      left.style.alignSelf = right.style.alignSelf = 'start';
      const over = left.getBoundingClientRect().height > right.getBoundingClientRect().height + 1;
      left.style.alignSelf = right.style.alignSelf = '';
      return over;
    };
    for (const step of TRIM_STEPS){
      if (!tall()) break;
      row.classList.add('trim-' + step);
      row.setAttribute('data-trim', step);
    }
  });
}
function fitPrintPages(host){
  host.classList.add('stu-printing');
  fillReportArt(host);
  trimSkillColumns(host);
  const pxPerMM = 96/25.4;
  const sheetH = A4_MM.h * pxPerMM - FIT_SLACK_PX;
  host.querySelectorAll('section.page').forEach(pageEl=>{
    pageEl.style.zoom = ''; pageEl.style.width = ''; pageEl.style.minHeight = '';
    const floor = pageEl.classList.contains('free-report') ? FIT_MIN_FREE : FIT_MIN;
    /* Width compensation reflows the text, which changes the height, so
       measure the rendered (zoomed) content again after each step and keep
       shrinking until it fits. Two fixed passes were not enough: the second
       left a sheet at 1129px for a 1113px target. Content is measured with
       min-height off, or every page would read as a full sheet. */
    /* A page that would need less than the floor at its first measure is
       still tried at the floor before it spills: the wider reflow there
       (width compensation) often saves the lines it needs. A report printed
       in Telugu, and Pro's practice page with the host's fonts, came out at
       0.72 to 0.76 by the first measure and fit at the floor (2026-10-11). */
    let z = 1;
    for (let i=0; i<6; i++){
      const minH = pageEl.style.minHeight;
      pageEl.style.minHeight = '0px';
      const h = pageEl.getBoundingClientRect().height;
      pageEl.style.minHeight = minH;
      if (h <= sheetH + 1) break;
      if (z <= floor + 0.001){            /* too tall even at the floor */
        pageEl.style.zoom=''; pageEl.style.width=''; pageEl.style.minHeight='';
        break;
      }
      const next = Math.max(floor, z * sheetH / h);
      z = Math.max(floor, Math.min(next, z - 0.002));   /* always progress */
      pageEl.style.zoom = String(z);
      pageEl.style.width = 'calc('+A4_MM.w+'mm / '+z+')';
      pageEl.style.minHeight = 'calc('+A4_MM.h+'mm / '+z+')';
    }
  });
}
function unfitPrintPages(host){
  host.classList.remove('stu-printing');
  host.querySelectorAll('section.page').forEach(p=>{
    p.style.zoom=''; p.style.width=''; p.style.minHeight='';
  });
  trimSkillColumns(host);
}
let printFitWired = false;
function wirePrintFit(host){
  if (printFitWired) return; printFitWired = true;
  window.addEventListener('beforeprint', ()=>fitPrintPages(host));
  window.addEventListener('afterprint', ()=>unfitPrintPages(host));
  let resized = 0;
  window.addEventListener('resize', ()=>{ clearTimeout(resized); resized = setTimeout(()=>trimSkillColumns(host), 150); });
}

if (document.readyState !== 'complete') window.addEventListener('load', ()=>fillReportArt(document), { once:true });
global.VahiniReport = { render, rerender, audience, setAudience, fitPrintPages, unfitPrintPages, trimSkillColumns, classificationPanels, applyPenDynamics, fillReportArt, modelHTML, stepList, MODEL_KINDS: Object.keys(MODEL_WORDS).concat(['margin','waves','ovals','push-pulls','page']) };
})(window);
