/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini report renderer: builds the data-driven report from
   { intake, analysis, expectedText, actualCanvas, detCanvas, pipeline }.
   Reuses report.css classes (Ink & Paper).
   ========================================================================= */
(function (global) {
'use strict';
/* Overall-score label. Previously imported from VahiniFactors (factors.js); the
   scoring engine now lives server-side, so this trivial rendering helper is
   inlined here to keep the report self-contained. */
const overallBand = (o)=> o>=80?'Strong & consistent' : o>=66?'Developing well' : o>=50?'Emerging: clear focus areas' : 'Early: lots to build on';

/* Single source of truth for the 4 score bands, read by every report page
   that shows a band (scorecard section rows via bandOf(), factor cards and
   the reference-values table via the server-assigned f.band) so the
   thresholds, wording and colour never drift apart between pages again.
   Must track backend/scoring.py's _band(). */
const bandOf = (score)=> score>=8.5?'strong' : score>=7.0?'good' : score>=4.5?'dev' : 'focus';
const BAND_LABEL = { strong:'Strong', good:'Good', dev:'Developing', focus:'Needs support' };
const BAND_COLOR = { strong:'var(--grow)', good:'var(--band-good)', dev:'var(--gold)', focus:'var(--band-focus)' };
const BAND_STARS = { strong:'★★★★', good:'★★★☆', dev:'★★☆☆', focus:'★☆☆☆' };
const SEC_ICON = {
  structure:'<path d="M4 20 L9 4 M9 20 L14 4 M14 20 L19 4" />',
  spatial:'<path d="M5 6v12M19 6v12M9 12h6"/><path d="M9 12l2-2M9 12l2 2"/>',
  dynamics:'<path d="M3 12h3l2-7 4 14 2-7h7"/>',
  style:'<path d="M4 19h16M7 19l5-12 5 12"/>',
};
/* Published reference bands (the "normal ranges" printed on the report's
   reference-values table: same convention as a medical lab report).
   Must track backend/scoring.py's _band() thresholds. */
const REF_BANDS = { strong:[8.5,10.0], good:[7.0,8.4], dev:[4.5,6.9], focus:[0.0,4.4] };

function ringSVG(score){
  const r=78, c=2*Math.PI*r, off=c*(1-score/100);
  return `<svg viewBox="0 0 178 178" style="position:absolute;inset:0;">
    <circle cx="89" cy="89" r="${r}" fill="none" stroke="rgba(255,255,255,.14)" stroke-width="13"/>
    <circle cx="89" cy="89" r="${r}" fill="none" stroke="var(--accent)" stroke-width="13"
      stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}" transform="rotate(-90 89 89)"/>
  </svg>`;
}

/* line chart for the 8-week projected trajectory */
function trajectoryChart(curve, nowVal, projVal){
  const w=1040, h=190, padL=46, padR=20, padT=18, padB=30;
  const ys = curve.map(p=>p.overall);
  const maxW = Math.max(...curve.map(p=>p.w));
  const lo = Math.max(0, Math.min(...ys)-8), hi = 100;
  const X = (wk)=> padL + (wk/maxW)*(w-padL-padR);
  const Y = (v)=> padT + (1-(v-lo)/(hi-lo))*(h-padT-padB);
  const pts = curve.map(p=>[X(p.w), Y(p.overall)]);
  const line = pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const area = line+` L ${X(maxW)} ${h-padB} L ${padL} ${h-padB} Z`;
  let grid='';
  [25,50,75,100].forEach(v=>{ if(v>=lo){ const y=Y(v); grid+=`<line x1="${padL}" y1="${y}" x2="${w-padR}" y2="${y}" stroke="var(--hair)" stroke-width="1"/><text x="${padL-8}" y="${y+4}" text-anchor="end" font-size="11" fill="var(--muted)" font-family="Hanken Grotesk">${v}</text>`; } });
  let wk='';
  curve.forEach(p=>{ if(p.w%2===0){ wk+=`<text x="${X(p.w)}" y="${h-9}" text-anchor="middle" font-size="11" fill="var(--muted)" font-family="Hanken Grotesk">${p.w===0?'now':'wk '+p.w}</text>`; } });
  const bandY = Y(100), bandH = Y(80)-Y(100);
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;display:block;">
    <rect x="${padL}" y="${bandY}" width="${w-padL-padR}" height="${bandH}" fill="var(--grow)" opacity="0.07"/>
    <text x="${w-padR-4}" y="${Y(90)+4}" text-anchor="end" font-size="10" fill="var(--grow)" font-family="Hanken Grotesk" font-weight="700">strong zone</text>
    ${grid}${wk}
    <path d="${area}" fill="var(--accent)" opacity="0.10"/>
    <path d="${line}" fill="none" stroke="var(--accent)" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${X(0)}" cy="${Y(nowVal)}" r="6" fill="#fff" stroke="var(--ink)" stroke-width="3"/>
    <circle cx="${X(maxW)}" cy="${Y(projVal)}" r="6" fill="var(--accent)" stroke="#fff" stroke-width="2.5"/>
    <text x="${X(0)+10}" y="${Y(nowVal)-10}" font-size="12" font-weight="800" fill="var(--ink)" font-family="Hanken Grotesk">${nowVal}</text>
    <text x="${X(maxW)-8}" y="${Y(projVal)-12}" text-anchor="end" font-size="12" font-weight="800" fill="var(--accent-deep)" font-family="Hanken Grotesk">${projVal}</text>
  </svg>`;
}

/* mini signal chart (filled area + line) for the IMU report page */
function sparkline(values, color, w, h){
  w=w||520; h=h||96; if(!values||!values.length) return '';
  const min=Math.min(...values), max=Math.max(...values), rng=(max-min)||1;
  const pts = values.map((v,i)=>[ (i/(values.length-1))*w, h-6 - ((v-min)/rng)*(h-16) ]);
  const line = pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const area = line+` L ${w} ${h} L 0 ${h} Z`;
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:${h}px;display:block;">
    <path d="${area}" fill="${color}" opacity="0.12"/>
    <path d="${line}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}

/* ---- exercise drill drawings (CSS/SVG, direction arrows) --------------- */
function exDraw(type){
  const INK='#27406b';
  const rail = `<line x1="14" y1="20" x2="326" y2="20" stroke="#cdd6e6" stroke-width="1.4"/>
    <line x1="14" y1="44" x2="326" y2="44" stroke="#cdd6e6" stroke-width="1.2" stroke-dasharray="4 4"/>
    <line x1="14" y1="68" x2="326" y2="68" stroke="#9fb0cb" stroke-width="1.6"/>`;
  const defs = `<defs><marker id="ah_${type}" markerWidth="7" markerHeight="7" refX="5.5" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6 Z" fill="currentColor"/></marker></defs>`;
  const AR = `stroke="currentColor" stroke-width="1.6" stroke-dasharray="3 3" fill="none" stroke-linecap="round" marker-end="url(#ah_${type})"`;
  let s='';
  if(type==='slant'){
    s+='<line x1="170" y1="14" x2="170" y2="74" stroke="#e3d6bd" stroke-width="1.2" stroke-dasharray="3 3"/>';
    for(let i=0;i<6;i++){ const x=26+i*22; s+=`<line x1="${x}" y1="68" x2="${x+13}" y2="20" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`; }
    for(let i=0;i<6;i++){ const x=190+i*22; s+=`<line x1="${x}" y1="20" x2="${x+13}" y2="68" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`; }
    s+=`<path d="M24 80 L40 80" ${AR}/><path d="M198 80 L214 80" ${AR}/>`;
  } else if(type==='round'){
    for(let i=0;i<5;i++){ const cx=40+i*26; s+=`<ellipse cx="${cx}" cy="44" rx="9" ry="17" transform="rotate(-16 ${cx} 44)" fill="none" stroke="${INK}" stroke-width="2.6"/>`; }
    for(let i=0;i<5;i++){ const cx=200+i*26; s+=`<circle cx="${cx}" cy="44" r="13" fill="none" stroke="${INK}" stroke-width="2.6"/>`; }
    s+='<line x1="170" y1="14" x2="170" y2="74" stroke="#e3d6bd" stroke-width="1.2" stroke-dasharray="3 3"/>';
    s+=`<path d="M44 30 A14 14 0 1 0 30 47" ${AR}/><path d="M204 30 A14 14 0 1 0 190 47" ${AR}/>`;
  } else if(type==='rhythm'){
    let pts=''; for(let i=0;i<8;i++){ const x=24+i*18; pts+=`${x},${i%2?64:24} `; }
    s+=`<polyline points="${pts.trim()}" fill="none" stroke="${INK}" stroke-width="2.8" stroke-linejoin="round"/>`;
    let g='M186 44 '; for(let i=0;i<5;i++) g+='q 13 26 26 0 ';
    s+=`<path d="${g}" fill="none" stroke="${INK}" stroke-width="2.8" stroke-linecap="round"/>`;
    s+='<line x1="170" y1="14" x2="170" y2="74" stroke="#e3d6bd" stroke-width="1.2" stroke-dasharray="3 3"/>';
    s+=`<path d="M150 80 L168 80" ${AR}/><path d="M300 80 L318 80" ${AR}/>`;
  } else if(type==='frame'){
    s+=`<rect x="40" y="12" width="260" height="62" rx="3" fill="none" stroke="${INK}" stroke-width="2"/>`;
    s+=`<rect x="58" y="22" width="224" height="42" rx="2" fill="none" stroke="#cdd6e6" stroke-width="1.4" stroke-dasharray="4 3"/>`;
    for(let i=0;i<4;i++){ const y=30+i*9; s+=`<line x1="66" y1="${y}" x2="${200+(i%2?40:0)}" y2="${y}" stroke="#bcc7da" stroke-width="2"/>`; }
    s+=`<path d="M58 17 L98 17" ${AR}/><path d="M52 22 L52 50" ${AR}/>`;
  } else if(type==='wave'){
    s+=`<path d="M22 44 Q52 16 82 44 T142 44 T202 44 T262 44 T322 44" fill="none" stroke="${INK}" stroke-width="2" stroke-linecap="round"/>`;
    [2,3,4,5,6,7].forEach((w,i)=>{ const x=40+i*48; s+=`<line x1="${x}" y1="70" x2="${x+22}" y2="70" stroke="${INK}" stroke-width="${w}" stroke-linecap="round"/>`; });
    s+=`<path d="M30 80 L300 80" ${AR}/>`;
    s+=`<text x="40" y="64" font-size="8" font-family="Hanken Grotesk" fill="currentColor" font-weight="700">light</text>`;
    s+=`<text x="280" y="64" font-size="8" font-family="Hanken Grotesk" fill="currentColor" font-weight="700">heavy</text>`;
  }
  return `<svg viewBox="0 0 340 86" preserveAspectRatio="xMidYMid meet">${defs}${rail}${s}</svg>`;
}
const EX_CAP = { slant:['forward  /  →','back  \\  →'], round:['ovals','circles'], rhythm:['zigzag','wave loops'], frame:['draw frame','write inside'], wave:['light → heavy','then even'] };

/* ---- role config ------------------------------------------------------- */
function roleConfig(role){
  const map = {
    student:{ label:'Student', greet:(n)=>`Brilliant effort, ${n}!`, you:'you', show:'kid' },
    parent:{ label:'Parent / Guardian', greet:(n)=>`${n}'s handwriting journey`, you:'your child', show:'kid' },
    coach:{ label:'Coach / Instructor', greet:(n)=>`Assessment for ${n}`, you:'the writer', show:'coach' },
    institute:{ label:'Institute / School', greet:(n)=>`Assessment for ${n}`, you:'the student', show:'coach' },
    individual:{ label:'Individual', greet:()=>`Your handwriting, in twenty factors`, you:'you', show:'individual' },
  };
  return map[role] || map.individual;
}

function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

/* document-type accuracy colour + panel */
function docAccColor(acc){
  if(/high/i.test(acc)) return { c:'var(--grow)', bg:'var(--grow-soft)', t:'Strong fit' };
  if(/moderate/i.test(acc)) return { c:'#9A7B25', bg:'var(--gold-soft)', t:'Usable' };
  return { c:'var(--accent-deep)', bg:'var(--accent-soft)', t:'Reduced accuracy' };
}
function docTypeChip(dt){
  const a = docAccColor(dt.accuracy);
  return `<span style="display:inline-flex;align-items:center;gap:7px;font-size:11px;font-weight:700;color:${a.c};background:${a.bg};padding:5px 12px;border-radius:99px;">
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/></svg>
    ${esc(dt.label)}</span>`;
}
/* ---- strip internal jargon (§4C Fxx, "proxy", section refs) from copy --- */
function plainText(s){
  return String(s||'')
    .replace(/\s*\(§4[ABC][^)]*\)/g,'')
    .replace(/\s*§4[ABC]\s*F?\d*/g,'')
    .replace(/\s*\(image proxy[^)]*\)/ig,'')
    .replace(/\s*\([^)]*proxy[^)]*\)/ig,'')
    .replace(/\bproxy\b/ig,'estimate')
    .replace(/\s*\(\s*\)/g,'')
    .replace(/\s{2,}/g,' ').replace(/\s+([.;,])/g,'$1').replace(/;\s*$/,'').trim();
}

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
/* Reader report: six pages, with one shared factor-based practice plan. */
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


function render(host, data){
  const {analysis, intake={}, recognizedText='', crops={}}=data;
  const rec=analysis.recognition || {};
  const isLive=f=>!f.unmeasured && (f.imuMeasured || f.conf!=='imu') && Number.isFinite(f.score);
  const sorted=analysis.results.filter(f=>isLive(f) && ![18,20].includes(f.n)).sort((a,b)=>a.score-b.score || a.n-b.n);
  const weak=sorted.filter(f=>f.score<8.5);
  const maintenance=!weak.length && sorted.length>0;
  const readable=['high','passage-verified'].includes(rec.level);
  // Classification entries preserve original OCR, unlike passage-corrected
  // text. Never check the printed stream or score-excluded regions.
  const classification=analysis.textClassification;
  const sources=classification
    ? (classification.handwritten || []).filter(r=>r.included_in_scoring).map(r=>({id:r.id,text:r.text}))
    : [{id:null,text:recognizedText}];
  const hasText=sources.some(r=>String(r.text||'').trim());
  const spelling=readable && window.VahiniCraft
    ? sources.flatMap(r=>VahiniCraft.checkSpelling(r.text).map(f=>({...f,region:r.id}))) : [];
  const firstSpelling=spelling[0];
  const priorities=[];
  if(firstSpelling){
    const f=firstSpelling;
    priorities.push({id:'spelling',title:'Check this spelling',
      reason:`The text reader found “${f.word}”. Did you mean “${f.suggestion}”?`,
      instruction:`First check “${f.word}” against your handwriting. If it is a spelling mistake, read “${f.suggestion}” aloud and notice the letters that change. If the text reader got it wrong, ignore this suggestion.`,
      drill:`Look at “${f.suggestion}”, cover it, write it from memory, then check it. Use it in one sentence.`,
      spelling:f});
  }
  (maintenance?sorted:weak).slice(0,3-priorities.length).forEach(f=>{
    const n=window.VahiniNarrate ? VahiniNarrate.narrate(f) : null;
    const instruction=plainText(n ? n.drill : f.tip);
    priorities.push({id:String(f.n),factor:f,title:f.name,
      reason:`${f.score.toFixed(1)}/10. ${maintenance?'Within the strong reference range; maintain this skill.':'Below the strong reference range of 8.5–10; one of your measured practice priorities.'}`,
      instruction,drill:'Write one short guided row, then a fresh row without the guide. Compare the two.'});
  });
  const spellingStatus=!readable
    ? 'Spelling check deferred: the text reading is not confident enough. Try a clearer photo or check the words with a teacher.'
    : !hasText ? 'Spelling check unavailable: no usable handwritten text was read.'
    : spelling.length ? 'Possible English spelling mistakes found. One is included in your three priorities. Confirm it against the original page; text reading can make mistakes.'
    : 'No common English misspellings from our limited list were found. This is not a complete spelling or grammar check; other languages are not checked.';
  const title=esc(intake.writerName || 'Your handwriting');
  const head=label=>`<div class="run-head"><span class="rh-mark"><span class="rh-dot"></span><span class="rh-name">Vahini</span></span><span>${label}</span></div>`;
  const foot=n=>`<div class="run-foot"><span>Free handwriting review</span><span>Practise a little, then review again</span><span class="pg-num">0${n}</span></div>`;
  const cardStyle='';
  const evidence=p=>{
    if(p.spelling){
      const f=p.spelling;
      return `<div class="spelling-evidence"><p>Text read from your handwriting: <q>${esc(f.context)}</q></p><small>${f.region?'Source region: '+esc(f.region):'Source: recognized handwriting; exact word location unavailable.'} · Suggested correction: <b>${esc(f.suggestion)}</b></small></div>`;
    }
    const c=crops[p.factor.n];
    return c ? `<div class="priority-evidence">
      ${c.url?`<img class="f-crop" src="${esc(c.url)}" alt="Handwriting reference for ${esc(p.title)}" >`:''}
      ${c.location_url?`<img class="f-location" src="${esc(c.location_url)}" alt="Source page location" >`:''}</div>
      <p style="font-size:10px;">${c.status==='context'?'Context only. ':''}${esc(c.caption||'Reference from the uploaded page.')} Geometry proxies do not establish an exact letter fault.</p>`
      : '<p style="font-size:10px;">No localized evidence available for this scan. This score does not identify an exact letter fault.</p>';
  };
  const empty='<p>No actionable handwriting measurements are available. Upload a clearer page with several handwritten lines before choosing exercises.</p>';
  const reportCards=priorities.map((p,i)=>`<article class="priority-card" data-factor="${p.id}" style="${cardStyle}"><h3>${i+1}. ${esc(p.title)}</h3><p>${esc(p.reason)}</p><div class="concept-comparison"><div class="concept-target"><b>How it should look</b>${p.factor?focusSVG({...p.factor,band:'strong'}).svg:`<p>${esc(p.spelling.suggestion)}</p>`}<small>Concept example, not a corrected scan</small></div><div class="concept-actual"><b>Your handwriting</b>${evidence(p)}</div></div></article>`).join('');
  const coaching=priorities.map((p,i)=>`<article class="coaching-card" data-factor="${p.id}" style="${cardStyle}"><h3>${i+1}. ${esc(p.title)}</h3><p class="factor-instruction">${esc(p.instruction)}</p></article>`).join('');
  const drills=priorities.map((p,i)=>`<article class="practice-card" data-factor="${p.id}" style="${cardStyle}"><h3>${i+1}. ${esc(p.title)}</h3><p class="factor-instruction">${esc(p.instruction)}</p><p>${esc(p.drill)}</p></article>`).join('');
  const rawOverall=analysis.overallMeasured ?? analysis.overall;
  const overall=Number.isFinite(rawOverall)?rawOverall:null;
  const measured=analysis.results.filter(isLive);
  const scoreRows=analysis.results.map(f=>`<tr data-factor="${f.n}"><td>${f.n}</td><td>${esc(f.name)}</td><td>${isLive(f)?f.score.toFixed(1):'—'}</td><td>${isLive(f)?BAND_LABEL[bandOf(f.score)]:'Unavailable'}</td><td>${esc(f.target||'')}</td></tr>`).join('');
  let forecast=null;
  if(overall!=null && measured.length && window.VahiniForecast){
    const sections=analysis.sections.map(section=>({...section,factors:section.factors.filter(isLive)})).filter(section=>section.factors.length);
    const weight=sections.reduce((sum,section)=>sum+section.weight,0);
    if(weight>0)forecast=VahiniForecast.compute({...analysis,results:measured,sections:sections.map(section=>({...section,weight:section.weight/weight}))},data.imu,data.pipeline||{},overall);
  }
  const pages=[
    `<section class="page free-report" data-screen-label="Overall score">${head('1 · Overall score')}
      <div class="sec-title"><div><div class="eyebrow">Handwriting review</div><h2>${title}</h2></div></div>
      <div class="score-card restored-score"><div class="ring">${overall!=null?ringSVG(overall):''}<div class="ring-num"><b>${overall??'—'}</b><span>out of 100</span></div></div><div class="band-pill">${overall!=null?overallBand(overall):'Not measured'}</div></div>
      <p class="lead">${measured.length} of ${analysis.results.length} factors measured. Missing measurements do not contribute to the score.</p>
      <div class="restored-summary"><h3>Your practice priorities</h3>${priorities.map(p=>`<p>${esc(p.title)}</p>`).join('')||empty}</div>
      <p>Read the factor scores on page 2 and compare the concept with your handwriting on page 3. Coaching, tips and drills follow, with a practice projection on page 6.</p>
      <p class="spelling-status">${esc(spellingStatus)}</p>${foot(1)}</section>`,
    `<section class="page free-report" data-screen-label="Factor scores">${head('2 · Factor scores')}
      <div class="sec-title"><h2>Your 20-factor score table</h2></div>
      <p>The strong reference band is 8.5–10. These engine thresholds guide practice; they are not clinical or age-specific norms.</p>
      <table class="report-score-table"><thead><tr><th>#</th><th>Factor</th><th>/10</th><th>Band</th><th>Target</th></tr></thead><tbody>${scoreRows}</tbody></table>
      <p>“—” means unavailable. Some measurements are proxies; a score alone does not establish an exact letter fault.</p>${foot(2)}</section>`,
    `<section class="page free-report" data-screen-label="Your three priorities">${head('3 · Concept and your handwriting')}
      <div class="sec-title"><div><div class="eyebrow">Free review · up to three priorities</div><h2>${title}</h2></div></div>
      <p class="lead">${maintenance?'Keep these strengths steady.':'Start with these priorities.'} Small, regular practice can help make schoolwork easier to read.</p>
      <p class="spelling-status" style="font-size:11px;">${esc(spellingStatus)}</p>
      ${rec.printed_lines>0?`<p style="font-size:10px;">${rec.printed_lines} printed lines on the page were excluded. Only handwriting is reviewed.</p>`:''}
      ${reportCards || empty}
      <p style="font-size:10px;">Spelling suggestions do not change handwriting scores. Only measured factors are selected; a photo cannot measure pen speed or pressure.</p>${foot(3)}</section>`,
    `<section class="page free-report" data-screen-label="Coaching">${head('4 · Coaching')}
      <div class="sec-title"><h2>How to work on each priority</h2></div>
      <p class="lead">Use the same priorities from your review. Ask a teacher or parent to check a word or letter with you if you are unsure.</p>
      ${coaching || empty}${foot(4)}</section>`,
    `<section class="page free-report" data-screen-label="Tips and drills">${head('5 · Tips and drills')}
      <div class="sec-title"><h2>Your short practice session</h2></div>
      <p class="lead">Choose one priority to start. Take a few comfortable minutes and stop if your hand feels tired.</p>
      ${drills || empty}
      <p style="font-size:11px;">After practising, upload a fresh sample to get another free review. Use similar paper and lighting. Progress varies; this report does not predict marks or exam results.</p>
      <div class="guided-support" style="${cardStyle}"><h3>Want help choosing your next steps?</h3><p>Students, parents and teachers can ask about guided handwriting support. Schools can enquire about support for their students.</p><a href="mailto:info@vahinitech.com?subject=Guided%20handwriting%20support">Ask about guided support</a><p style="font-size:10px;">Your free review needs no purchase. Students can ask a parent or teacher to enquire.</p></div>
      <p style="font-size:10px;">This is practice guidance, not a medical assessment. <a href="https://github.com/vahinitech/20factor-analyser/issues">Report a mistake</a>.</p>${foot(5)}</section>`,
    `<section class="page free-report" data-screen-label="Prediction">${head('6 · Practice prediction')}
      <div class="sec-title"><h2>Your practice projection</h2></div>
      <p class="lead">An illustrative scenario, not a measured forecast or a promise of improvement.</p>
      ${forecast?`<div class="projection-chart">${trajectoryChart(forecast.curve,forecast.overallNow,forecast.overallProj)}</div><p>Current measured score: <b>${overall}/100</b>. Illustrative range after ${forecast.horizon} weeks: <b>${forecast.projLow}–${forecast.projHigh}/100</b>.</p>`:'<p>A projection is unavailable until there are usable measured scores.</p>'}
      <p>The model assumes short, regular practice. It has not been calibrated to predict this writer’s progress. Actual results depend on practice, the sample and image quality. Missing factors are excluded.</p>
      <h3>Check your progress</h3><p>Practise the same priorities from pages 4 and 5. Re-scan a comparable passage after practice and check the real measurements. A photo cannot establish writing speed or pressure.</p>${foot(6)}</section>`
  ];
  host.innerHTML=pages.join('');
  wirePrintFit(host);
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
function fitPrintPages(host){
  const pxPerMM = 96/25.4;
  const sheetH = A4_MM.h * pxPerMM;
  host.querySelectorAll('section.page').forEach(pageEl=>{
    pageEl.style.zoom = ''; pageEl.style.width = ''; pageEl.style.minHeight = '';
    /* two passes: width compensation reflows text, which changes height */
    for (let i=0; i<2; i++){
      const h = pageEl.scrollHeight;
      if (h <= sheetH + 1) break;
      const z = Math.max(FIT_MIN, sheetH / h);
      if (z <= FIT_MIN + 0.001){          /* too tall to shrink readably */
        pageEl.style.zoom=''; pageEl.style.width=''; pageEl.style.minHeight='';
        break;
      }
      pageEl.style.zoom = String(z);
      pageEl.style.width = 'calc('+A4_MM.w+'mm / '+z+')';
      pageEl.style.minHeight = 'calc('+A4_MM.h+'mm / '+z+')';
    }
  });
}
function unfitPrintPages(host){
  host.querySelectorAll('section.page').forEach(p=>{
    p.style.zoom=''; p.style.width=''; p.style.minHeight='';
  });
}
let printFitWired = false;
function wirePrintFit(host){
  if (printFitWired) return; printFitWired = true;
  window.addEventListener('beforeprint', ()=>fitPrintPages(host));
  window.addEventListener('afterprint', ()=>unfitPrintPages(host));
}

global.VahiniReport = { render, fitPrintPages, classificationPanels };
})(window);
