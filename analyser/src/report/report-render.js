/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini report renderer — builds the data-driven report from
   { intake, analysis, expectedText, actualCanvas, detCanvas, pipeline }.
   Reuses report.css classes (Ink & Paper).
   ========================================================================= */
(function (global) {
'use strict';
/* Overall-score label. Previously imported from VahiniFactors (factors.js); the
   scoring engine now lives server-side, so this trivial rendering helper is
   inlined here to keep the report self-contained. */
const overallBand = (o)=> o>=80?'Strong & consistent' : o>=66?'Developing well' : o>=50?'Emerging — clear focus areas' : 'Early — lots to build on';

const BAND_LABEL = { strong:'Strong', dev:'Developing', focus:'Focus area' };
const BAND_COLOR = { strong:'var(--grow)', dev:'var(--gold)', focus:'var(--band-focus)' };
const SEC_ICON = {
  structure:'<path d="M4 20 L9 4 M9 20 L14 4 M14 20 L19 4" />',
  spatial:'<path d="M5 6v12M19 6v12M9 12h6"/><path d="M9 12l2-2M9 12l2 2"/>',
  dynamics:'<path d="M3 12h3l2-7 4 14 2-7h7"/>',
  style:'<path d="M4 19h16M7 19l5-12 5 12"/>',
};
/* Published reference bands (the "normal ranges" printed on the report's
   reference-values table — same convention as a medical lab report). */
const REF_BANDS = { strong:[7.5,10.0], dev:[5.0,7.4], focus:[0.0,4.9] };

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
/* Compact field-launch report — at most 4 pages from a photo (5 with the
   pen) so a young writer keeps interest:
     1. Scorecard        — overall, sections, all 20 factors at a glance
     2. Where to improve — concept drawing + a reference crop from THEIR page
     3. Reference values — the published ranges for all 20 factors, read
                           like a medical lab report
     4. Practice & tries — the drills, and how many tries to the milestone */
function render(host, data){
  const { intake, analysis, recognizedText, ocrEngine, detURL, pipeline, imu, crops, history } = data;
  const rc = roleConfig('individual');
  const name = intake.writerName || 'this sample';
  const isLive = (f)=> !f.unmeasured && (f.imuMeasured || f.conf!=='imu');
  const penPending = analysis.results.filter(f=>!f.imuMeasured && f.conf==='imu').length;
  const unmeasuredCount = analysis.results.filter(f=>f.unmeasured).length;
  const measuredCount = (analysis.measuredCount!=null ? analysis.measuredCount : (20-penPending));
  // Headline score: in photo mode use the Measured overall (excludes pen-pending factors)
  const overall = imu ? analysis.overall : (analysis.overallMeasured!=null ? analysis.overallMeasured : analysis.overall);
  const MILESTONE = Math.min(100, Math.ceil((overall+1)/5)*5);
  const topWeakNames = analysis.topWeak.slice(0,2).map(f=>f.name);
  const today = new Date().toLocaleDateString('en-GB',{ day:'numeric', month:'long', year:'numeric' });
  const rid = (function(){
    /* Sequential, incrementing report number (not random): 0001, 0002, … */
    let n = 0;
    try{ n = parseInt(localStorage.getItem('vahini_report_seq')||'0', 10) || 0; }catch(e){}
    n += 1;
    try{ localStorage.setItem('vahini_report_seq', String(n)); }catch(e){}
    return 'VHN-'+new Date().getFullYear()+'-'+String(n).padStart(4,'0');
  })();
  const logo = 'assets/vahini-logo.png';
  const head = (label)=>`<div class="run-head"><span class="rh-mark"><img class="rh-logo" src="${logo}" alt=""><span class="rh-name">Vahini</span></span><span class="rh-right">${label}</span></div>`;
  const foot = (pg, mid)=>`<div class="run-foot"><span>Vahini Handwriting Analysis · ${rid}</span><span>${mid||'info@vahinitech.com · vahinitech.com'}</span><span class="pg-num">${String(pg).padStart(2,'0')}</span></div>`;
  let pg=0; const P=()=>++pg;
  const pages = [];

  /* ---- drill prescription (shared by Scorecard + Practice page) ---- */
  const DRILL = {
    slant:  { title:'Slant rails',          goal:'a single, steady slant' },
    round:  { title:'Oval & circle roll',   goal:'even, rounded, same-size letters' },
    rhythm: { title:'Even spacing practice', goal:'even gaps between letters and words' },
    frame:  { title:'Frame the page',       goal:'tidy margins and a straight baseline' },
    wave:   { title:'Pressure waves',       goal:'smooth, even pen pressure' },
  };
  const liveSorted = analysis.results.filter(isLive).sort((a,b)=>a.score-b.score);
  const focusFactors = liveSorted.slice(0,3);
  const maintenance = !liveSorted.some(f=>f.score<6.5);
  const prescribed = maintenance ? liveSorted.slice(0,2) : liveSorted.filter(f=>f.score<6.5).slice(0,4);
  const groupMap = {};
  prescribed.forEach(f=>{ const t=f.ex||'round'; (groupMap[t]=groupMap[t]||{type:t,factors:[]}).factors.push(f); });
  const drills = Object.values(groupMap)
    .map(g=>({ ...g, low: Math.min(...g.factors.map(f=>f.score)) }))
    .sort((a,b)=>a.low-b.low).slice(0,3);

  /* ---- prediction: how many tries to the next milestone ---- */
  let fc = null, tries = null;
  if (window.VahiniForecast){
    fc = window.VahiniForecast.compute(analysis, imu, pipeline, overall);
    let wk = null;
    for (const p of fc.curve){ if (p.overall >= MILESTONE){ wk = p.w; break; } }
    if (wk != null){ const w = Math.max(1, wk); tries = { weeks: w, sessions: w*3 }; }
  }

  /* ---------- PAGE 1 · SCORECARD ---------- */
  pg=P();
  const scSecRows = analysis.sections.map(s=>{
    const b = s.avg>=7.5?'strong':s.avg>=5?'dev':'focus';
    if (s.avg100==null) return `<div class="cat-row" style="padding:10px 14px;">
      <span class="ci" style="color:var(--accent-deep)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${SEC_ICON[s.id]}</svg></span>
      <span class="ct">${s.name}<small>${s.id==='dynamics'?'measured by the Vahini pen — not scored from a photo':'couldn’t be measured reliably — re-scan'}</small></span>
      <span class="cmeter"><span class="meter"><i style="width:0%"></i></span><span class="cval" style="color:var(--muted)">—</span></span>
    </div>`;
    return `<div class="cat-row" style="padding:10px 14px;">
      <span class="ci" style="color:var(--accent-deep)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${SEC_ICON[s.id]}</svg></span>
      <span class="ct">${s.name}<small>${s.blurb} · ${Math.round(s.weight*100)}% weight</small></span>
      <span class="cmeter"><span class="meter"><i style="width:${s.avg100}%;background:${BAND_COLOR[b]}"></i></span><span class="cval">${s.avg100}</span></span>
    </div>`;
  }).join('');
  const chip = (f, kind)=>`<span class="sc2-chip ${kind}">${esc(f.name)}<i>${(f.imuMeasured||f.conf!=='imu')?f.score.toFixed(1):'—'}</i></span>`;
  const scoreboard = `<div class="ea-panel" style="margin-top:14px;">
    <div class="ea-head act"><span class="t">All 20 factors at a glance</span><span class="tag" style="background:var(--ink);color:#fff;">reference values on page ${imu?'04':'03'}</span></div>
    <div class="fscore-grid">${analysis.results.map(f=>`<span class="fscore ${f.band}"${isLive(f)?'':' style="opacity:.45;filter:grayscale(.55)"'}><b>${String(f.n).padStart(2,'0')}</b><span class="fs-nm">${esc(f.name)}</span><i>${isLive(f)?f.score.toFixed(1):'—'}</i></span>`).join('')}</div>
  </div>`;
  const rec = (analysis && analysis.recognition) ? analysis.recognition : null;
  const recPct = (rec && Number.isFinite(rec.confidence_pct)) ? rec.confidence_pct : null;
  const recLine = rec ? (({
    'passage-verified':'Words verified against your passage',
    'high':'Words read with high confidence',
    'moderate':'Words read with moderate confidence',
    'low':'Word reading is assistive on this scan',
    'unavailable':'Words were not read this scan — the scores are unaffected',
  }[rec.level] || 'Word reading is assistive') + (recPct!=null?` (${recPct}%)`:'') + '.') : '';
  // Document checks — like the stamp on a lab report: parsed fully, and the
  // recognised words run through the spelling/grammar rules when reading was
  // dependable. Never claim a clean sheet off a low-confidence reading.
  let checksLine = '';
  if (ocrEngine==='server' && rec){
    const readable = ['passage-verified','high','moderate'].indexOf(rec.level) >= 0;
    const readText = String(recognizedText||'').trim();
    if (readable && readText && window.VahiniCraft){
      const craft = window.VahiniCraft.analyze(readText, pipeline.docType && pipeline.docType.key);
      if (craft && craft.runGrammar){
        checksLine = craft.count
          ? `Document parsed fully ✓ · spelling &amp; grammar: <b>${craft.count} thing${craft.count>1?'s':''} to check</b> — ${esc(craft.findings.slice(0,1).map(x=>x.msg).join(''))}`
          : `Document parsed fully ✓ · <b style="color:var(--grow);">no spelling mistakes ✓ · no grammar mistakes ✓</b> in the recognised text`;
      }
    } else {
      checksLine = `Document parsed fully ✓ · spelling &amp; grammar checks switch on once the words are read dependably${recPct!=null?` (reading now: ${recPct}%)`:''}`;
    }
  }
  pages.push(`<section class="page" data-screen-label="Scorecard">
    ${head('Scorecard · '+today)}
    <div class="sec-title"><div><div class="eyebrow">Report ${rid} · 20-Factor Engine v3.1</div><h2>${esc(rc.greet(name))}</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
    <div class="dash-grid" style="margin-bottom:12px;">
      <div class="score-card">
        <div class="ring">${ringSVG(overall)}<div class="ring-num"><b>${overall}</b><span>out of 100</span></div></div>
        <div class="band-pill">${overallBand(overall)}</div>
        <div class="sc-note">${imu?'All 20 factors measured (pen + image).':`Measured from the photo — ${measuredCount} of 20 factors${unmeasuredCount?'; '+unmeasuredCount+' couldn’t be read':''}.${penPending?` The ${penPending} motion factors await the Vahini pen.`:''}`}</div>
      </div>
      <div class="cat-list">${scSecRows}
        <div class="sc2-goal"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/></svg><span><b>Next milestone: ${MILESTONE}/100</b> — reachable by lifting ${esc(topWeakNames.join(' and '))}.${tries?` Our estimate: about <b>${tries.sessions} practice tries</b> (${tries.weeks} week${tries.weeks>1?'s':''} at 3× a week).`:''}</span></div>
      </div>
    </div>
    ${scoreboard}
    <div class="sc2-row" style="margin-top:12px;"><div class="sc2-h good">Top strengths</div><div class="sc2-chips">${analysis.topStrong.slice(0,3).map(f=>chip(f,'good')).join('')}</div></div>
    <div class="sc2-row"><div class="sc2-h focus">Focus areas</div><div class="sc2-chips">${analysis.topWeak.slice(0,3).map(f=>chip(f,'focus')).join('')}</div></div>
    ${history?`<div class="hist-strip"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l5-5 4 4 8-8"/><path d="M14 8h6v6"/></svg><span><b>Since the last scan (${esc(history.date)}):</b> overall ${history.overall} → <b>${overall}</b> (${overall-history.overall>=0?'+':''}${overall-history.overall})</span></div>`:''}
    <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:12px;font-size:11px;color:var(--ink-2);">
      <b>${pipeline.nWords} words · ${pipeline.nLines} lines · ${pipeline.nChars} letters</b>
      ${pipeline.docType ? docTypeChip(pipeline.docType) : ''}
      ${checksLine?`<span>${checksLine}</span>`:''}
    </div>
    ${recLine?`<div style="margin-top:8px;font-size:10.5px;color:var(--muted);line-height:1.5;">${recLine} Text recognition is <b>under progress and will improve soon</b> — accuracy rises with every update, delivered in increments. The 20 factors are measured from the <b>geometry</b> of the writing and don’t depend on reading the words.</div>`:''}
    ${foot(pg,'One-page scorecard · improvement plan follows')}
  </section>`);

  /* ---------- IMU CAPTURE & SIGNALS (pen mode only — page 2) ---------- */
  if (imu){
    pg=P();
    const groups = (window.VahiniIMU? window.VahiniIMU.SENSOR_GROUPS : []);
    const sensorCells = groups.map(g=>`<div style="border:1px solid var(--hair);border-radius:11px;padding:11px 13px;background:var(--card);">
      <div style="display:flex;align-items:center;gap:8px;"><span style="width:10px;height:10px;border-radius:50%;background:${g.color};"></span><b style="font-size:12px;color:var(--ink);">${g.label}</b></div>
      <div style="font-size:10px;color:var(--muted);margin:3px 0 7px;">${g.sub}</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;">${g.axes.map(a=>`<span style="font-size:9px;font-weight:700;color:${g.color};background:${g.color}1a;padding:2px 6px;border-radius:5px;">${a}</span>`).join('')}</div>
    </div>`).join('');
    const stat = (k,v)=>`<div style="padding:12px 14px;border-right:1px solid var(--hair);"><div style="font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:700;">${k}</div><div style="font-family:var(--serif);font-size:18px;margin-top:4px;color:var(--ink);">${v}</div></div>`;
    pages.push(`<section class="page" data-screen-label="IMU Capture">
      ${head('Battu · Live Capture')}
      <div class="sec-title"><div><div class="eyebrow">${imu.axes}-axis sensor fusion · Kalman-filtered</div><h2>What the pen felt</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
      <p class="lead" style="max-width:84%;margin-bottom:16px;">The IMU pen streamed at <b>${imu.fs} Hz</b> while ${esc(name)} wrote — capturing the <b>process</b> a photo cannot see. A 9-axis IMU, a 6-axis IMU and a tip force sensor were fused and de-noised with a Kalman filter, then read out as the four Dynamics factors.</p>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--hair);border-radius:13px;overflow:hidden;background:var(--card);margin-bottom:16px;">
        ${stat('Duration', imu.dur.toFixed(1)+' s')}${stat('Samples', imu.nSamp.toLocaleString())}${stat('Strokes', imu.strokes)}<div style="padding:12px 14px;"><div style="font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:700;">Pen-lifts</div><div style="font-family:var(--serif);font-size:18px;margin-top:4px;color:var(--ink);">${imu.lifts}</div></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px;">
        <div class="ea-panel"><div class="ea-head act" style="background:#E1E3F7;"><span class="t" style="color:#3A45B0;">Tip force / pressure</span><span class="tag">N · ${imu.meanForce.toFixed(2)} avg</span></div><div style="padding:8px 10px;">${sparkline(imu.charts.force,'#4F5BD5')}</div></div>
        <div class="ea-panel"><div class="ea-head exp"><span class="t">Pen tilt / slant</span><span class="tag">${imu.meanTilt.toFixed(0)}° lean</span></div><div style="padding:8px 10px;">${sparkline(imu.charts.tilt,'#2F8F7F')}</div></div>
      </div>
      <div class="ea-panel" style="margin-bottom:16px;"><div class="ea-head act"><span class="t">Writing velocity (per-stroke pulses)</span><span class="tag">mm/s</span></div><div style="padding:8px 10px;">${sparkline(imu.charts.vel,'#D4633A',1080,90)}</div></div>
      <div class="cat-band"><span class="cb-no" style="color:var(--accent-deep)">16-AXIS</span><span class="cb-name" style="font-size:17px;">Sensor array</span><span class="cb-rule"></span></div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:11px;">${sensorCells}</div>
      ${foot(pg,'Vahini IMU Sensor Pen · Patent No. 584433')}
    </section>`);
  }

  /* ---------- PAGE · WHERE EXACTLY TO IMPROVE ---------- */
  pg=P();
  const improveCards = focusFactors.map(f=>{
    const fx = focusSVG(f);
    const N = window.VahiniNarrate ? window.VahiniNarrate.narrate(f) : null;
    const why = plainText(N ? N.body : f.evidence);
    const act = plainText(N ? N.action : f.tip);
    const cr = crops && crops[f.n];
    return `<div class="factor" style="page-break-inside:avoid;">
      <div class="f-top">
        <span class="f-no">${String(f.n).padStart(2,'0')}</span>
        <span class="f-name">${esc(f.name)}<small>${f.score.toFixed(1)}/10 now · reference ${REF_BANDS.strong[0].toFixed(1)}–${REF_BANDS.strong[1].toFixed(1)}</small></span>
        <span class="f-band ${f.band}">${BAND_LABEL[f.band]}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:stretch;margin:8px 0 4px;">
        <figure style="margin:0;">
          <div class="f-focus" style="height:64px;margin:0;">${fx.svg}</div>
          <figcaption style="font-size:10px;color:var(--muted);margin-top:4px;"><b>The concept</b> — we look at ${esc(fx.look)}</figcaption>
        </figure>
        <figure style="margin:0;">
          ${cr?`<img class="f-crop" src="${cr.url}" alt="from your writing" style="width:100%;height:64px;object-fit:cover;border-radius:8px;border:1px solid var(--paper-edge);background:#fff;display:block;">`
              :`<div class="f-focus" style="height:64px;margin:0;display:grid;place-items:center;color:var(--muted);font-size:10.5px;">reference crop appears when the recognition server maps your page</div>`}
          <figcaption style="font-size:10px;color:var(--muted);margin-top:4px;"><b>Your reference</b> — ${cr?esc(cr.caption):'measured from your own page'}</figcaption>
        </figure>
      </div>
      <div class="f-scorebar"><i style="width:${f.score100}%;background:${BAND_COLOR[f.band]}"></i></div>
      <p class="f-why"><b>Why this score:</b> ${esc(why)}</p>
      <div class="f-tip"><b>Try this&nbsp;·&nbsp;</b>${esc(act)} <span style="color:var(--muted);">Target: ${esc(f.target)}.</span></div>
    </div>`;
  }).join('');
  pages.push(`<section class="page" data-screen-label="Where to improve">
    ${head('Where exactly to improve')}
    <div class="sec-title"><div><div class="eyebrow">${maintenance?'Nothing is weak — the three to keep polishing':'Your top '+focusFactors.length+' issues — where the score grows fastest'}</div><h2>Where exactly to improve</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
    ${detURL?`<div class="ea-panel" style="margin-bottom:12px;">
      <div class="ea-head act"><span class="t">Your page, as detected</span><span class="tag" style="background:var(--accent-deep);color:#fff;">orange = detected writing</span></div>
      <div style="display:grid;grid-template-columns:220px 1fr;gap:14px;align-items:center;padding:10px 14px;background:#fff;">
        <img src="${detURL}" alt="detected sample" style="display:block;width:100%;max-height:235px;object-fit:contain;background:#fff;border:1px solid var(--paper-edge);border-radius:8px;">
        <div style="font-size:11px;color:var(--ink-2);line-height:1.6;">Each <b style="color:var(--accent-deep);">orange box</b> is a piece of writing the engine found and measured — that is the evidence behind every score in this report. The <b style="color:var(--grow);">teal line</b> under a box is the baseline the writing sits on.</div>
      </div>
    </div>`:''}
    <p class="lead" style="max-width:86%;margin-bottom:12px;">Each card pairs the <b>concept</b> (what good looks like) with a <b>reference cropped from ${rc.you==='you'?'your':esc(name)+'’s'} own page</b> — so you can see exactly what was measured and where to aim next.</p>
    <div style="display:grid;gap:12px;">${improveCards}</div>
    <div style="margin-top:10px;font-size:10.5px;color:var(--ink-2);background:var(--paper-2);border-radius:10px;padding:9px 13px;">We show the <b>top 3 issues</b> so practice stays focused. Want the full 20-factor deep-dive report? Email <a href="mailto:info@vahinitech.com" style="color:var(--accent-deep);font-weight:700;">info@vahinitech.com</a>.</div>
    ${foot(pg,'Top 3 issues · full 20-factor deep-dive: info@vahinitech.com')}
  </section>`);

  /* ---------- PAGE · REFERENCE VALUES (read like a lab report) ---------- */
  pg=P();
  const td = 'padding:4px 8px;border-bottom:1px solid var(--hair);font-size:10.5px;text-align:center;vertical-align:middle;';
  const flagOf = (f)=> f.band==='strong' ? `<span style="color:var(--grow);font-weight:800;">✓ in range</span>`
    : f.band==='dev' ? `<span style="color:#9A7B25;font-weight:800;">△ below range</span>`
    : `<span style="color:var(--accent-deep);font-weight:800;">▲ well below</span>`;
  const refRows = analysis.results.map(f=>{
    const live = isLive(f);
    const noteTxt = f.conf==='imu' && !f.imuMeasured && !imu ? 'measured by the pen' : 'not read this scan';
    return `<tr>
      <td style="${td}color:var(--muted);">${String(f.n).padStart(2,'0')}</td>
      <td style="${td}text-align:left;"><b>${esc(f.name)}</b></td>
      <td style="${td}"><b style="font-variant-numeric:tabular-nums;font-size:11.5px;">${live?f.score.toFixed(1):'—'}</b></td>
      <td style="${td}color:var(--muted);">/10</td>
      <td style="${td}font-variant-numeric:tabular-nums;">${REF_BANDS.strong[0].toFixed(1)} – ${REF_BANDS.strong[1].toFixed(1)}</td>
      <td style="${td}text-align:left;color:var(--ink-2);">${esc(f.target)}</td>
      <td style="${td}white-space:nowrap;">${live?flagOf(f):`<span style="color:var(--muted);">— ${noteTxt}</span>`}</td>
    </tr>`;
  }).join('');
  const th = 'padding:6px 8px;font-size:9px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);border-bottom:2px solid var(--ink);text-align:center;';
  pages.push(`<section class="page" data-screen-label="Reference Values">
    ${head('Reference values · every factor, published')}
    <div class="sec-title"><div><div class="eyebrow">Read it like a lab report — result · reference interval · flag</div><h2>The reference values</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
    <p class="lead" style="max-width:88%;margin-bottom:12px;">Every Vahini report scores against the <b>same fixed, published reference values</b> — so a result means the same thing on every scan, for every writer. A factor is <b>in reference</b> at ${REF_BANDS.strong[0].toFixed(1)}–${REF_BANDS.strong[1].toFixed(1)} points, <b>developing</b> at ${REF_BANDS.dev[0].toFixed(1)}–${REF_BANDS.dev[1].toFixed(1)}, and a <b>focus area</b> below ${REF_BANDS.dev[0].toFixed(1)}. Overall: ${overall}/100 (strong zone: 80–100).</p>
    <table style="width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--hair);border-radius:12px;overflow:hidden;">
      <thead><tr>
        <th style="${th}">#</th><th style="${th}text-align:left;">Factor</th><th style="${th}">Result</th><th style="${th}">Unit</th><th style="${th}">Reference interval</th><th style="${th}text-align:left;">Measured target (how it’s judged)</th><th style="${th}">Flag</th>
      </tr></thead>
      <tbody>${refRows}</tbody>
    </table>
    <div style="margin-top:10px;font-size:10px;color:var(--muted);line-height:1.55;background:var(--paper-2);border-radius:10px;padding:10px 14px;">
      <b style="color:var(--ink-2);">How these reference values are set:</b> each factor is real geometry measured from the page (e.g. Size Consistency = letter-height variation, in reference when CV ≤ 0.12). The thresholds come from established document-analysis methods and handwriting-coaching practice (see <i>docs/Computer Vision Algorithms.md</i> in the open-source engine) and are identical in every report, so scans are comparable over time. “—” means the factor needs the Vahini pen (motion) or couldn’t be read from this photo; it never silently defaults to a made-up value.
    </div>
    ${foot(pg,'Fixed, published reference values — comparable across scans')}
  </section>`);

  /* ---------- PAGE · PRACTICE PLAN + HOW MANY TRIES ---------- */
  pg=P();
  const joinList = (a)=> a.length<2 ? (a[0]||'') : a.slice(0,-1).join(', ')+' and '+a[a.length-1];
  const exCards = drills.map(d=>{
    const addresses = d.factors.map(f=>f.name).slice(0,2);
    return `<div class="ex-card">
      <div class="ex-info">
        <div class="ex-head"><span class="ex-tag">${maintenance?'Maintain':'Priority'}</span><span class="ex-grp">addresses: ${esc(addresses.join(' · '))}</span></div>
        <div class="ex-title">${DRILL[d.type].title}</div>
        <p class="ex-why"><b>${d.low.toFixed(1)}/10 lowest.</b> Because ${esc(joinList(addresses.map(a=>a.toLowerCase())))} ${addresses.length>1?'are':'is'} below the reference, this drill builds ${DRILL[d.type].goal}.</p>
        <span class="ex-reps"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M20 6 9 17l-5-5"/></svg>5–10 min · 3× a week</span>
      </div>
      <div class="ex-rail">${exDraw(d.type)}<div class="rl-cap"><span>${EX_CAP[d.type][0]}</span><span>${EX_CAP[d.type][1]}</span></div></div>
    </div>`;
  }).join('');
  const card = (k,big,sub,accent)=>`<div style="background:var(--card);border:1px solid var(--hair);border-radius:14px;padding:15px 16px;">
    <div style="font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:700;">${k}</div>
    <div style="font-family:var(--serif);font-size:24px;line-height:1.05;margin:6px 0 4px;color:${accent||'var(--ink)'};">${big}</div>
    <div style="font-size:10.5px;color:var(--ink-2);line-height:1.4;">${sub}</div></div>`;
  let predictHTML = '';
  if (fc){
    const fluentLine = fc.fluency.imageOnly
      ? 'estimated from the photo — the pen measures it exactly'
      : (fc.fluency.alreadyFluent ? 'Already fast &amp; easy'
        : (fc.fluency.weeksToFluent!=null ? `~${fc.fluency.weeksToFluent} weeks to fast, easy writing` : 'with steady practice'));
    predictHTML = `
      <div class="cat-band" style="margin-top:14px;"><span class="cb-no" style="color:var(--accent-deep)">PREDICTION</span><span class="cb-name" style="font-size:17px;">How many tries to the milestone</span><span class="cb-rule"></span></div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:12px;">
        ${card('How many tries?', tries?`≈ ${tries.sessions} tries`:'keep going', tries?`about <b>${tries.sessions} short practice sessions</b> (${tries.weeks} week${tries.weeks>1?'s':''} at 3× a week) to reach <b>${MILESTONE}/100</b>`:`the milestone of ${MILESTONE}/100 sits beyond an 8-week projection — practise the drills and re-scan every 2 weeks`, 'var(--grow)')}
        ${card('Projected score', `${fc.overallNow} <span style="color:var(--muted);font-size:16px;">→</span> ${fc.projLow}–${fc.projHigh}`, `over ${fc.horizon} weeks of steady practice`, 'var(--ink)')}
        ${card('Writing flow &amp; speed', fc.fluency.bandNow, `${fluentLine}`, 'var(--accent-deep)')}
      </div>
      <div class="ea-panel">
        <div class="ea-head act"><span class="t">Projected score · each dot is one week of practice</span><span class="tag">estimate</span></div>
        <div style="padding:8px 12px 2px;">${trajectoryChart(fc.curve, fc.overallNow, fc.overallProj)}</div>
      </div>
      <div style="margin-top:8px;font-size:10px;color:var(--muted);line-height:1.5;">Projections assume ~10 minutes of the prescribed drills, 3× a week, along a normal learning curve — a motivational estimate, not a guarantee. Re-scan to track the real curve.</div>`;
  }
  const stars = Math.max(1, Math.min(5, Math.round(overall/20)));
  const starRow = [1,2,3,4,5].map(i=>`<svg viewBox="0 0 24 24" width="22" height="22" ${i<=stars?'fill="#C29A45"':'fill="none" stroke="#C29A45" stroke-width="2"'}><path d="M12 2l3 6.5 7 .7-5.2 4.7 1.5 6.9L12 17l-6.3 3.8L7.2 14 2 9.2l7-.7z"/></svg>`).join('');
  pages.push(`<section class="page ex-page" data-screen-label="Practice & Prediction">
    ${head('Practice plan · Prediction')}
    <div class="sec-title"><div><div class="eyebrow">Chosen from ${esc(name)}’s own results — nothing generic</div><h2>Your drill prescription</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
    <div class="ex-list">${exCards}</div>
    ${predictHTML}
    <div class="mascot-strip" style="margin-top:12px;"><div style="display:flex;gap:3px;align-items:center;">${starRow}</div><div><h4>${stars} star${stars>1?'s':''} earned! ✏️</h4><p>Practise just ${drills.length===1?'this drill':'these '+drills.length+' drills'} for a few fun minutes, 3× a week, and re-scan in 2–4 weeks to earn more stars and watch the score climb.</p></div></div>
    <div class="disclaimer" style="margin-top:12px;">
      <h4><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg> Important — please read</h4>
      <p>This report is intended <b>solely for handwriting improvement, education and skill-building</b>. It is <b>not a medical, psychological, neurological or diagnostic assessment</b> and must not be used to diagnose, screen for, or rule out any condition (including dysgraphia or learning differences) — if you have such concerns, please consult a qualified professional. Results can vary with the writing sample, pen, surface and lighting.</p>
    </div>
    <div class="patent-strip"><span>© ${new Date().getFullYear()} Vahini Technologies</span><span class="ps-dot"></span><span>IMU Sensor Pen · Patent No. 584433</span><span class="ps-dot"></span><span>info@vahinitech.com · vahinitech.com</span></div>
    ${foot(pg,'Questions about this report: info@vahinitech.com')}
  </section>`);

  host.innerHTML = pages.join('');
}

global.VahiniReport = { render };
})(window);
