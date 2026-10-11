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
/* Stage names on both pages (owner approval 2026-10-11, #122): the child
   is on a path, Learning, Improving, Mastering, Strong; the band colours
   stay. They match the practice catalogue's stages and live in the string
   tables as stage.<band> (strings/en.js). */
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
   them in here, and the section and overall scores are recomputed with the
   published weights so every factor counts. */
const SECTION_WEIGHTS={structure:0.30,spatial:0.30,dynamics:0.20,style:0.20};
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
    s.weight=SECTION_WEIGHTS[s.id]??s.weight;
  });
  const scored=(analysis.sections||[]).filter(s=>s.avg100!=null);
  const wsum=scored.reduce((n,s)=>n+s.weight,0)||1;
  const overall=Math.round(scored.reduce((n,s)=>n+s.avg100*(s.weight/wsum),0));
  analysis.overall=overall; analysis.overallMeasured=overall; analysis.measuredCount=live.length;
  const ranked=live.slice().sort((a,b)=>a.score-b.score);
  analysis.topWeak=ranked.slice(0,3); analysis.topStrong=ranked.slice().reverse().slice(0,4);
  return analysis;
}

/* ---- practice (docs/PRACTICE-FRAMEWORK.md; owner approval 2026-10-11, #122)
   Exercises, tips and how many tries come from the practice catalogue
   (backend/practice_catalog.py), never from this file: the catalogue served
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
   same-site paths in window.VAHINI_REPORT_ART ({cheer, tip, encourage}),
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
const TICK = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"/></svg>';
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
function rerender(){
  if (!lastRender || !lastRender.host.isConnected) return null;
  return render(lastRender.host, lastRender.data);
}

function render(host, data){
  const {analysis, intake={}, recognizedText='', crops={}, imu=null, history=null}=data;
  lastRender = { host, data };
  const t=translatorFor(data);
  host.setAttribute('lang', t.lang);
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
  const spelling=readable && window.VahiniCraft
    ? sources.flatMap(r=>VahiniCraft.checkSpelling(r.text).map(f=>({...f,region:r.id}))) : [];
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
  const rawOverall=analysis.overallMeasured ?? analysis.overall;
  const overall=Number.isFinite(rawOverall)?rawOverall:null;
  // The last check saved in this browser, for the change line and the chips.
  const prev=history&&history.date?history:null;
  const prevScore=Object.fromEntries((prev&&Array.isArray(prev.factors)?prev.factors:[]).map(f=>[f.n,f.score]));
  const fmtDay=d=>{const day=new Date(d+'T00:00:00');return Number.isNaN(day.getTime())?d:day.toLocaleDateString(t.locale,{day:'numeric',month:'long'});};
  // #82: a skill counts as better from +0.3. The same page sent as PNG and
  // as JPEG moved factor scores by up to 0.2, so a smaller rise can be noise.
  const BETTER_BY=0.3;
  const gain=f=>Number.isFinite(prevScore[f.n])?f.score-prevScore[f.n]:null;
  const improved=measured.filter(f=>gain(f)!==null&&gain(f)>=BETTER_BY-1e-9);
  const sinceLine=prev&&Number.isFinite(prev.overall)&&overall!=null
    ?`<p class="since-last">${esc(t('sn.since',{date:fmtDay(prev.date),was:prev.overall,now:overall}))}${improved.length?` ${esc(t.n('sn.since.better',improved.length))}`:''}</p>`:'';
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
  const overallBandId=overall==null?null:bandOf(overall/10);
  const scorePill=overall==null?'':`<span class="sn-score band-${overallBandId}" data-band="${overallBandId}"><b>${overall}</b><small>${esc(t('sn.outof'))} · ${esc(stage(overallBandId))}</small></span>`;
  const best=sorted.slice().sort((a,b)=>b.score-a.score||a.n-b.n)[0]||measured.slice().sort((a,b)=>b.score-a.score||a.n-b.n)[0];
  const cheer=artImg('cheer','rp-art-cheer');
  const keepBand=best?`<div class="sn-keep" data-factor="${best.n}"><span class="sn-tick">${TICK}</span><span class="sn-keep-label">${esc(t('sn.keep'))}</span><div class="sn-keep-text"><h3>${esc(t.has('keep.title.'+best.n)?t('keep.title.'+best.n):nameOn(1,best))}</h3><p>${esc(t.has('keep.text.'+best.n)?t('keep.text.'+best.n):'')}</p></div>${cheer}${LEAF}</div>`:'';
  // "Look closer": the first two skills to grow; a spelling finding may
  // take the second row.
  const lookItems=rowFactors.slice(0,2).map(f=>({f}));
  if(firstSpelling){ if(lookItems.length>=2) lookItems[1]={spelling:firstSpelling}; else lookItems.push({spelling:firstSpelling}); }
  // The photo, zoomed to the parts the rows point at: an SVG viewBox over
  // the photo (meet), every numbered box kept whole.
  const det=data.detURL||'';
  const marks=lookItems.map((it,i)=>{
    const c=it.f&&crops[it.f.n], b=c&&c.bbox;
    return it.f&&Array.isArray(b)&&b.length===4&&!wholePageCrop(c)?{b,num:i+1}:null;
  }).filter(Boolean);
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
      <p class="sn-meta">${esc(nameOn(1,first))} · <span class="sn-band-text band-${bandOf(first.score)}">${esc(first.score.toFixed(1))}/10</span> · ${esc(stage(bandOf(first.score)))}</p>
      <span class="sn-try">${PENCIL}${esc(t('sn.start.try.'+(firstExModel&&t.has('sn.start.try.'+firstExModel.unit)?firstExModel.unit:'row')))}</span></div>`:'';
  const lookRow=(it,i)=>{
    if(it.spelling){
      const s=it.spelling;
      return `<div class="sn-look" data-factor="spelling"><div class="sn-look-crop sn-look-word">${esc(s.word)}</div><div><h4><em>${i+1} ·</em> ${esc(t('spell.title'))}</h4><p>${t.html('sn.spell.saw',{word:`<b>${esc(s.word)}</b>`,suggestion:`<b>${esc(s.suggestion)}</b>`})}</p></div>
        <div class="sn-act">${PENCIL}<div><b>${esc(t('sn.next'))}</b>${esc(t('sn.spell.action'))}</div></div></div>`;
    }
    const f=it.f, c=crops[f.n], sheet=worksheetFor(f);
    const crop=wholePageCrop(c)?`<p class="sn-look-none">${esc(t('sn.wholepage'))}</p>`
      :c&&c.url?`<img class="sn-look-crop" src="${esc(c.url)}" alt="${esc(t('sn.crop.alt',{skill:skillName(f)}))}">`
      :`<p class="sn-look-none">${esc(t('sn.nocrop'))}</p>`;
    return `<div class="sn-look" data-factor="${f.n}">${crop}<div><h4><em>${i+1} ·</em> ${esc(nameOn(1,f))}</h4><p>${esc(t.has('saw.'+f.n)?t('saw.'+f.n):'')}</p></div>
      <div class="sn-act">${PENCIL}<div><b>${esc(t('sn.next'))}</b>${esc(t.has('action.'+f.n)?t('action.'+f.n):'')}${sheet?` <a class="sn-sheet" href="${esc(sheetURL(sheet))}">${esc(t('sn.sheet',{title:sheet.title}))}</a>`:''}</div></div></div>`;
  };
  const chipList=measured.slice().sort((a,b)=>a.n-b.n);
  const chips=chipList.map(f=>{const band=bandOf(f.score), g=improved.includes(f);
    return `<div class="sn-chip" data-factor="${f.n}"><span class="sn-ic">${iconSVG(f.n)}</span><span class="sn-cn">${esc(t.has('chip.'+f.n)?t('chip.'+f.n):skillName(f))}</span><b class="band-${band}" data-band="${band}">${esc(f.score.toFixed(1))}${g?`<span class="sn-up" title="${esc(t('sn.chip.better',{gain:gain(f).toFixed(1)}))}">↑</span>`:''}</b></div>`;}).join('');
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
      <div class="sn-top">${brand}<div class="sn-right"><span class="sn-eyebrow">${esc(t('sn.eyebrow'))}</span>${writer?`<span class="sn-writer">${esc(writer)}</span>`:''}${scorePill}</div></div>
      <h2 class="sn-title">${esc(t('sn.title'))}</h2><p class="sn-sub">${esc(t('sn.sub'))}</p>${sinceLine}
      ${measured.length?`${keepBand}
      <div class="sn-mid${det?'':' no-photo'}">${zoom()}${startCard}</div>
      ${lookItems.length?`<h3 class="sn-h3">${esc(t('sn.look'))}</h3>${lookItems.map(lookRow).join('')}`:''}
      <div class="sn-h3row"><h3 class="sn-h3">${esc(t('sn.chips'))}</h3><small>${esc(t('sn.chips.note'))}</small></div>
      <div class="sn-chips">${chips}</div>
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
  const skillRow=(row,i)=>{
    const f=row.f, band=bandOf(f.score);
    const exs=row.exercises, tips=row.tips.map(e=>localEntry(e,t.lang));
    const lastKind=exs.length?exs[exs.length-1].entry.model:'line';
    return `<article class="practice-row coaching-card band-${band}" data-factor="${f.n}">
      <div class="pr-skill"><div class="pr-head"><h3>${i+1}. ${esc(nameOn(2,f))}</h3><span class="pr-badge band-${band}">${esc(t('row.badge',{score:f.score.toFixed(1),stage:stage(band)}))}</span></div>
        ${stagePath(band)}${practiceSheet(f)}</div>
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
  const others=measured.filter(f=>!rowFactors.includes(f)).sort((a,b)=>a.score-b.score||a.n-b.n);
  const praise=f=>{const b=bandOf(f.score);
    if([18,20].includes(f.n)&&(b==='focus'||b==='dev')) return t('other.composite');
    return b==='strong'?t('other.strong'):b==='good'?t('other.good'):'';};
  const locked=Math.max(0,20-analysis.results.length);
  const otherBox=others.length||free?`<div class="other-skills">${others.length?`<p class="os-list"><b>${esc(t('other.title'))}</b> ${others.map(f=>`<span data-factor="${f.n}">${esc(t('other.item',{skill:nameOn(2,f),score:f.score.toFixed(1),stage:stage(bandOf(f.score))}))}${praise(f)?': '+esc(praise(f)):''}</span>`).join(' · ')}</p>`:''}
      ${free&&locked?`<p class="pro-note"><b>${esc(t('pro.ask'))}</b> ${esc(t('pro.more',{n:locked}))}</p>`:''}</div>`:'';
  const closing=`<div class="p2-close">${artImg('encourage','rp-art-encourage')}<p><b>${esc(t('close.cheer'))}</b> ${esc(t('close.next'))}</p></div>`;
  const page2=`<section class="page free-report compact-report practice-page practice-${tier}" data-screen-label="Practise and improve">${head(t('head.page2'))}
      <h2>${esc(t('p2.title'))}</h2><p class="p2-sub">${esc(t('p2.sub'))}</p>
      ${rows?`<div class="practice-wrap"><div class="pr-cols" aria-hidden="true"><span>${esc(t('p2.cols.skill'))}</span><span>${esc(t('p2.cols.how'))}</span></div><div class="practice-table">${rows}</div></div>${otherBox}${closing}`:empty}
      ${foot(2)}</section>`;
  host.innerHTML=page1+page2;
  // A PDF made for sharing showed the report as it was: make it again.
  if(window.VahiniReportShare) VahiniReportShare.invalidate();
  wirePrintFit(host);
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
function fitPrintPages(host){
  fillReportArt(host);
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

if (document.readyState !== 'complete') window.addEventListener('load', ()=>fillReportArt(document), { once:true });
global.VahiniReport = { render, rerender, fitPrintPages, unfitPrintPages, classificationPanels, applyPenDynamics, fillReportArt, modelHTML, stepList, MODEL_KINDS: Object.keys(MODEL_WORDS).concat(['margin','waves','page']) };
})(window);
