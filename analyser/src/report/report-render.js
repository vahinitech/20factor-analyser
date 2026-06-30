/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini report renderer — builds the data-driven report from
   { intake, analysis, expectedText, actualCanvas, detCanvas, pipeline }.
   Reuses report.css classes (Ink & Paper).
   ========================================================================= */
(function (global) {
'use strict';
const F = global.VahiniFactors;

const BAND_LABEL = { strong:'Strong', dev:'Developing', focus:'Focus area' };
const BAND_COLOR = { strong:'var(--grow)', dev:'var(--gold)', focus:'var(--band-focus)' };
const CONF = {
  measured:{ t:'Measured', c:'var(--grow)', bg:'var(--grow-soft)' },
  proxy:   { t:'From image', c:'#9A7B25', bg:'var(--gold-soft)' },
  imu:     { t:'Needs the pen', c:'#3A45B0', bg:'#E1E3F7' },
  ml:      { t:'Estimated', c:'#7E3B73', bg:'#F0E0EE' },
};
const CONF_IMU_MEASURED = { t:'Battu · measured', c:'#2F4FC0', bg:'#DFE4FB' };
const SEC_ICON = {
  structure:'<path d="M4 20 L9 4 M9 20 L14 4 M14 20 L19 4" />',
  spatial:'<path d="M5 6v12M19 6v12M9 12h6"/><path d="M9 12l2-2M9 12l2 2"/>',
  dynamics:'<path d="M3 12h3l2-7 4 14 2-7h7"/>',
  style:'<path d="M4 19h16M7 19l5-12 5 12"/>',
};
const CRAFT_ICON = {
  format:'<path d="M4 6h16M4 10h16M4 14h10M4 18h13"/>',
  grammar:'<path d="M4 19l5-13 5 13M5.5 15h7"/><path d="M16 12l2 2 4-4"/>',
  homophone:'<path d="M4 5h10a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H8l-4 3z"/><path d="M20 9v9l-3-2h-3"/>',
  signoff:'<path d="M3 17c4 0 5-9 8-9s2 6 4 6 2-3 5-3"/><path d="M3 21h18"/>',
};
const SRC_ICO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7V4h16v3M9 20h6M12 4v16"/></svg>';

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
const EX_CAP = { slant:['forward  /  →','back  \\  →'], round:['ovals','circles'], rhythm:['zigzag','garland loops'], frame:['draw frame','write inside'], wave:['light → heavy','then even'] };

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
function docTypePanel(dt){
  const a = docAccColor(dt.accuracy);
  const sg = dt.signals || {};
  const profile = [];
  if (dt.printedLines>0) profile.push(['Printed lines', dt.printedLines+' (excluded)']);
  profile.push(['Handwritten lines', sg.nLines!=null?sg.nLines:'—']);
  profile.push(['Words', sg.nWords!=null?sg.nWords:'—']);
  profile.push(['Avg word length', sg.avgTokenLen!=null?sg.avgTokenLen+' chars':'—']);
  if (sg.bigBlobs>0 && dt.key==='figures') profile.push(['Figures / blocks', sg.bigBlobs+' (not scored)']);
  return `<div class="ea-panel" style="margin-top:16px;">
    <div class="ea-head act" style="background:${a.bg};"><span class="t" style="color:${a.c};">Detected document type</span><span class="tag" style="background:${a.c};color:#fff;">${esc(dt.accuracy)}</span></div>
    <div style="padding:14px 17px;display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:start;">
      <div style="min-width:150px;max-width:200px;">
        <div style="font-family:var(--serif);font-size:19px;color:var(--ink);line-height:1.12;margin-bottom:9px;">${esc(dt.label)}</div>
        <div class="dt-profile">${profile.map(p=>`<div><span>${esc(p[0])}</span><b>${esc(String(p[1]))}</b></div>`).join('')}</div>
      </div>
      <p style="margin:0;font-size:11.5px;line-height:1.55;color:var(--ink-2);">${esc(dt.note)}</p>
    </div>
  </div>`;
}

/* sample-quality validity strip (review item) */
function qualityStrip(q, pipeline){
  if(!q) return '';
  const col = q.grade==='Good'? 'var(--grow)' : q.grade==='Usable' ? '#9A7B25' : 'var(--accent-deep)';
  return `<div class="quality-strip">
    <span class="q-grade" style="background:${col}">Sample quality: ${q.grade}</span>
    <span class="q-base">based on ${pipeline.nWords} words · ${pipeline.nChars} letters · ${pipeline.nLines} line${pipeline.nLines>1?'s':''}</span>
    <span class="q-issues" style="${q.issues.length?'':'color:var(--grow);'}">${q.issues.length? q.issues.map(esc).join(' · ') : 'photo is clear, flat and well-lit'}</span>
    ${q.tips.length?`<span class="q-tips">Next time: ${esc(q.tips[0])}</span>`:''}
  </div>`;
}

function timingStrip(pipeline){
  const t = (pipeline && pipeline.timing) || null;
  if (!t) return '';
  const net = Number(t.network_ms || 0);
  const back = Number(t.backend_ms || 0);
  const wire = Number(t.wiring_ms || 0);
  return `<div class="quality-strip" style="margin-top:8px;">
    <span class="q-grade" style="background:var(--ink-2);">Pipeline timing</span>
    <span class="q-base">network ${Math.round(Math.max(0, net))} ms</span>
    <span class="q-issues" style="color:var(--ink-2);">backend ${Math.round(Math.max(0, back))} ms</span>
    <span class="q-tips">wiring ${Math.round(Math.max(0, wire))} ms</span>
  </div>`;
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
function render(host, data){
  const { intake, analysis, expectedText, recognizedText, ocrEngine, actualURL, detURL, pipeline, imu, crops, letterFindings, history } = data;
  const rc = roleConfig('individual');
  const name = intake.writerName || 'this sample';
  const overallFull = analysis.overall;
  const penPending = analysis.results.filter(f=>!f.imuMeasured && f.conf==='imu').length;
  const unmeasuredCount = analysis.results.filter(f=>f.unmeasured).length;
  // factors actually measured this run (excludes pen-pending AND validity-gated)
  const measuredCount = (analysis.measuredCount!=null ? analysis.measuredCount : (20-penPending));
  // real recognition only happens on the server; never present expected text as "read" (#3)
  const ocrReal = (ocrEngine==='server');
  // Headline score: in photo mode use the Measured overall (excludes pen-pending factors)
  const overall = imu ? analysis.overall : (analysis.overallMeasured!=null ? analysis.overallMeasured : analysis.overall);
  // single milestone number shared by scorecard, summary and forecast (#6)
  const MILESTONE = Math.min(100, Math.ceil((overall+1)/5)*5);
  const nextMilestone = (o)=> Math.min(100, Math.ceil((o+1)/5)*5);
  const topWeakNames = analysis.topWeak.slice(0,2).map(f=>f.name);
  const today = new Date().toLocaleDateString('en-GB',{ day:'numeric', month:'long', year:'numeric' });
  const rid = (function(){
    /* Sequential, incrementing report number (not random): 0001, 0002, …
       Read-modify-write on localStorage is synchronous, so even if reports are
       generated back-to-back the counter advances by exactly one each time. */
    let n = 0;
    try{ n = parseInt(localStorage.getItem('vahini_report_seq')||'0', 10) || 0; }catch(e){}
    n += 1;
    try{ localStorage.setItem('vahini_report_seq', String(n)); }catch(e){}
    return 'VHN-'+new Date().getFullYear()+'-'+String(n).padStart(4,'0');
  })();
  const logo = 'assets/vahini-logo.png';
  const modeLabel = imu ? 'the Battu (IMU pen)' : 'the Vahini deterministic-CV engine';
  const orgLogo = intake.logoData || null;
  const head = (label, pg)=>`<div class="run-head"><span class="rh-mark"><img class="rh-logo" src="${logo}" alt=""><span class="rh-name">Vahini</span></span><span class="rh-right">${label}${orgLogo?`<img class="rh-orglogo" src="${orgLogo}" alt="">`:''}</span></div>`;
  const foot = (pg, mid)=>`<div class="run-foot"><span>Vahini Handwriting Analysis · ${rid}</span><span>${mid||'info@vahinitech.com · vahinitech.com'}</span><span class="pg-num">${String(pg).padStart(2,'0')}</span></div>`;
  let pg=0; const P=()=>++pg;

  const pages = [];

  /* ---- drill prescription (computed early; used by Scorecard + Exercises) ---- */
  const DRILL = {
    slant:  { title:'Slant rails',          goal:'a single, steady slant' },
    round:  { title:'Oval & circle roll',   goal:'even, rounded, same-size letters' },
    rhythm: { title:'Spacing & rhythm run', goal:'consistent spacing between letters and words' },
    frame:  { title:'Frame the page',       goal:'tidy margins and a straight baseline' },
    wave:   { title:'Pressure waves',       goal:'smooth, even pen pressure' },
  };
  // never prescribe from pen-pending estimates in photo mode (high-confidence only)
  let weakFactors = analysis.results.filter(f=>f.score<6.5 && (imu || f.conf!=='imu')).sort((a,b)=>a.score-b.score);
  const maintenance = weakFactors.length===0;
  const prescribedFactors = maintenance ? [...analysis.results].filter(f=>imu||f.conf!=='imu').sort((a,b)=>a.score-b.score).slice(0,2) : weakFactors;
  const groupMap = {};
  prescribedFactors.forEach(f=>{ const t=f.ex||'round'; (groupMap[t]=groupMap[t]||{type:t,factors:[]}).factors.push(f); });
  const drills = Object.values(groupMap)
    .map(g=>({ ...g, low: Math.min(...g.factors.map(f=>f.score)) }))
    .sort((a,b)=>a.low-b.low).slice(0,3); // max 3 active drills (adherence research)

  /* ---------- COVER ---------- */
  pg=P();
  const orgLine = intake.org ? `<div class="cell"><div class="k">${rc.label}</div><div class="v" style="font-size:16px;">${esc(intake.org)}${intake.orgContact?`<small>${esc(intake.orgContact)}</small>`:''}</div></div>` :
    `<div class="cell"><div class="k">Prepared for</div><div class="v" style="font-size:16px;">You</div></div>`;
  pages.push(`<section class="page cover" data-screen-label="Cover">
      <div class="cover-top">
        <div class="brand-lockup">
          <img class="brand-logo" src="${logo}" alt="Vahini logo">
          <span class="brand-meta"><span class="brand-tt">Handwriting Intelligence</span><span class="brand-tag">by Vahini Technologies</span></span>
        </div>
        ${orgLogo?`<div class="cover-orgbrand"><img src="${orgLogo}" alt="${esc(intake.org||'')}"><span>${esc(intake.org||rc.label)}</span></div>`:`<div class="cover-id">Report ID&nbsp; <b>${rid}</b><br>Issued&nbsp; <b>${today}</b><br>20-Factor Engine&nbsp; <b>v3.0</b></div>`}
      </div>
    <div class="cover-mid">
      <div class="cover-kicker"><span class="line"></span><span class="eyebrow">Handwriting Quality Analysis</span></div>
      <h1 class="title">${esc(rc.greet(name)).replace(/(!|journey|handwriting,?)/i,'<span class="ink-flow">$1</span>')}</h1>
      <p class="subtitle">A warm, measurement-based look at twenty handwriting-quality factors — computed from ${rc.you==='you'?'your':rc.you+'\u2019s'} sample by ${modeLabel}, with a clear plan for growth.</p>
      <div class="cover-script">${imu?'the pen felt every stroke':'your writing, measured'}</div>
      ${pipeline.docType ? `<div style="margin-top:14px;">${docTypeChip(pipeline.docType)}</div>` : ''}
    </div>
    <div class="subject">
      <div class="cell"><div class="k">Subject</div><div class="v">Your writing<small>20-factor analysis</small></div></div>
      ${orgLine}
      <div class="cell"><div class="k">Overall</div><div class="v">${overall} / 100<small>${imu?F.overallBand(overall):('measured · '+measuredCount+' of 20 factors')}</small></div></div>
      <div class="cell"><div class="k">Sample</div><div class="v">${pipeline.nWords} words<small>${pipeline.nLines} lines · ${pipeline.nChars} letters</small></div></div>
    </div>
    <div class="cover-foot" style="margin-top:18px;">
      ${imu?`<div class="pen-badge">
        <svg viewBox="0 0 24 24" fill="none" stroke="#F4EFE3" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21l3-1 11-11-2-2L4 18l-1 3z"/><path d="M14 6l2 2"/><circle cx="19" cy="5" r="2"/></svg>
        <span><div class="pb-t">Vahini IMU Sensor Pen</div><div class="pb-s">Patent No. 584433 · dynamics factors captured in real time</div></span>
      </div>`:`<div class="pen-badge">
        <svg viewBox="0 0 24 24" fill="none" stroke="#F4EFE3" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.5" r="3.5"/></svg>
        <span><div class="pb-t">Measured from your photo</div><div class="pb-s">${measuredCount} of 20 factors measured from this image · motion factors await the Vahini pen (Patent 584433)</div></span>
      </div>`}
      ${orgLogo?`<div class="cover-logoslot" style="display:block"><div class="ls-cap">${esc(rc.label)}</div><img src="${orgLogo}" style="max-width:150px;max-height:74px;border-radius:8px;object-fit:contain;" alt="logo"></div>`:''}
    </div>
    ${foot(pg,'For improvement guidance only — not a clinical diagnosis')}
  </section>`);

  /* ---------- SCORECARD (the shareable one-pager) ---------- */
  pg=P();
  const scSecRows = analysis.sections.map(s=>{
    const b = s.avg>=7.5?'strong':s.avg>=5?'dev':'focus';
    if (s.avg100==null) return `<div class="cat-row" style="padding:10px 14px;">
      <span class="ci" style="color:var(--accent-deep)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${SEC_ICON[s.id]}</svg></span>
      <span class="ct">${s.name}</span>
      <span class="cmeter"><span class="meter"><i style="width:0%"></i></span><span class="cval" style="color:var(--muted)">—</span></span>
    </div>`;
    return `<div class="cat-row" style="padding:10px 14px;">
      <span class="ci" style="color:var(--accent-deep)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${SEC_ICON[s.id]}</svg></span>
      <span class="ct">${s.name}</span>
      <span class="cmeter"><span class="meter"><i style="width:${s.avg100}%;background:${BAND_COLOR[b]}"></i></span><span class="cval">${s.avg100}</span></span>
    </div>`;
  }).join('');
  const chip = (f, kind)=>`<span class="sc2-chip ${kind}">${esc(f.name)}<i>${(f.imuMeasured||f.conf!=='imu')?f.score.toFixed(1):'—'}</i></span>`;
  pages.push(`<section class="page" data-screen-label="Scorecard">
    ${head('Scorecard · Share this page')}
    <div class="sec-title"><div><div class="eyebrow">${esc(name)} · ${today}</div><h2>The one-page scorecard</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
    <div class="dash-grid" style="margin-bottom:14px;">
      <div class="score-card">
        <div class="ring">${ringSVG(overall)}<div class="ring-num"><b>${overall}</b><span>out of 100</span></div></div>
        <div class="band-pill">${F.overallBand(overall)}</div>
        <div class="sc-note">${imu?'All 20 factors measured (pen + image).':`Measured from the image — ${measuredCount} of 20 factors${unmeasuredCount?'; '+unmeasuredCount+' couldn’t be read — re-scan':''}. The ${penPending} motion factors await the Vahini pen.`}</div>
      </div>
      <div class="cat-list">${scSecRows}
        <div class="sc2-goal"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/></svg><span><b>Next milestone: ${MILESTONE}/100</b> — reachable by lifting ${esc(topWeakNames.join(' and '))}.</span></div>
      </div>
    </div>
    <div class="sc2-row"><div class="sc2-h good">Top strengths</div><div class="sc2-chips">${analysis.topStrong.slice(0,3).map(f=>chip(f,'good')).join('')}</div></div>
    <div class="sc2-row"><div class="sc2-h focus">Focus areas</div><div class="sc2-chips">${analysis.topWeak.slice(0,3).map(f=>chip(f,'focus')).join('')}</div></div>
    <div class="sc2-row"><div class="sc2-h drill">The ${drills.length} prescribed drill${drills.length>1?'s':''}</div><div class="sc2-chips">${drills.map(d=>`<span class="sc2-chip drill">${DRILL[d.type].title}<i>${d.low.toFixed(1)}</i></span>`).join('')}</div></div>
    <div class="sc2-share"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/></svg>This page stands alone — share it as a photo or PDF page; the full detail follows in the report. Re-scan in 2–4 weeks to track progress against the milestone.</div>
    ${foot(pg,'One-page summary · full analysis follows')}
  </section>`);

  /* ---------- TABLE OF CONTENTS (reserve slot; filled at the end) ---------- */
  const tocIdx = pages.length; pages.push(null); pg=P(); const tocPg=pg;

  /* ---------- SUMMARY ---------- */
  pg=P();
  const secRows = analysis.sections.map(s=>{
    const b = s.avg>=7.5?'strong':s.avg>=5?'dev':'focus';
    if (s.avg100==null) return `<div class="cat-row">
      <span class="ci" style="color:var(--accent-deep)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${SEC_ICON[s.id]}</svg></span>
      <span class="ct">${s.name}<small>${s.id==='dynamics'?'not scored from a photo — measured by the Battu':'couldn’t be measured reliably from this photo — re-scan'}</small></span>
      <span class="cmeter"><span class="meter"><i style="width:0%"></i></span><span class="cval" style="color:var(--muted)">—</span></span>
    </div>`;
    return `<div class="cat-row">
      <span class="ci" style="color:var(--accent-deep)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${SEC_ICON[s.id]}</svg></span>
      <span class="ct">${s.name}<small>${s.blurb} · ${Math.round(s.weight*100)}% weight</small></span>
      <span class="cmeter"><span class="meter"><i style="width:${s.avg100}%;background:${BAND_COLOR[b]}"></i></span><span class="cval">${s.avg100}</span></span>
    </div>`;
  }).join('');
  pages.push(`<section class="page" data-screen-label="Summary">
    ${head('Summary & Overview')}
    <div class="sec-title"><div><div class="eyebrow">At a glance</div><h2>How ${esc(name)} is doing</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
    <p class="lead" style="max-width:80%;margin-bottom:20px;">Twenty quality factors were computed across four families. ${overall>=66?'The writing is clear and well-organised, with a few friendly areas to polish.':'There is a solid foundation here, with clear, specific areas to focus on next.'} ${imu?'Every factor was measured — image geometry plus the pen’s motion stream.':`The score uses the ${measuredCount} factors we could measure from this image; the ${penPending} motion factors await the pen${unmeasuredCount?', and '+unmeasuredCount+' couldn’t be read reliably':''}.`}</p>
    <div class="dash-grid">
      <div class="score-card">
        <div class="ring">${ringSVG(overall)}<div class="ring-num"><b>${overall}</b><span>out of 100</span></div></div>
        <div class="band-pill">${F.overallBand(overall)}</div>
        <div class="sc-note">Weighted: Structure 30 · Spatial 30 · Dynamics 20 · Style 20.${imu?'':' Measured factors only.'}</div>
      </div>
      <div class="cat-list">${secRows}</div>
    </div>
    ${history?`<div class="hist-strip"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l5-5 4 4 8-8"/><path d="M14 8h6v6"/></svg><span><b>Since the last scan (${esc(history.date)}):</b> overall ${history.overall} → <b>${overall}</b> (${overall-history.overall>=0?'+':''}${overall-history.overall})</span>${(history.sections||[]).map(hs=>{const cur=analysis.sections.find(s=>s.id===hs.id); if(!cur||cur.avg100==null||hs.avg100==null) return ''; const d=cur.avg100-hs.avg100; return `<span class="hs-chip ${d>=0?'up':'down'}">${esc(cur.name.split(' ')[0])} ${d>=0?'+':''}${d}</span>`;}).join('')}</div>`:''}
    <div class="callouts">
      <div class="callout good"><h4><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg> Real strengths</h4>
        <ul>${analysis.topStrong.map(f=>`<li><b>${f.name}</b> — ${esc(plainText(f.value))}</li>`).join('')}</ul></div>
      <div class="callout focus"><h4><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20v-6M12 8h.01M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/></svg> Where to focus</h4>
        <ul>${analysis.topWeak.map(f=>`<li><b>${f.name}</b> — ${esc(plainText(f.tip).replace(/\.$/,''))}</li>`).join('')}</ul></div>
    </div>
    ${foot(pg)}
  </section>`);

  /* ---------- IMU CAPTURE & SIGNALS (only in pen mode) ---------- */
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
      ${foot(pg,'Demonstration pen stream · measured with the published Vahini method')}
    </section>`);
  }

  /* ---------- EXPECTED vs ACTUAL ---------- */
  pg=P();
  const expLines = (expectedText||'').split(/\n+/).filter(Boolean);
  const recLines = (recognizedText||'').split(/\n+/).filter(Boolean);
  const showText = imu || ocrReal;                 // never present expected text as "recognised" (#3)
  const shownLines = recLines.length ? recLines : expLines;
  const readTag = imu ? 'Pen path' : (ocrReal ? 'AI OCR' : 'Geometry only');
  const actLabel = imu ? 'Reconstructed trace' : 'Uploaded &amp; detected';
  const actTag = imu ? 'Pen' : (ocrEngine==='server'?'AI recognition':'Detected');
  const cap2 = imu ? 'Ink reconstructed from the captured pen path; geometry measured from it.'
    : 'Word boxes <span style="color:var(--accent-deep);font-weight:700;">(orange)</span> and fitted baselines <span style="color:var(--grow);font-weight:700;">(teal)</span> from the detection stage.';
  const introLine = imu
    ? `We reconstructed the ink from ${esc(name)}’s pen trajectory and measured twenty qualities of the handwriting. Here is what we read, with an at-a-glance map of all twenty factors.`
    : `We read ${rc.you==='you'?'your':esc(name)+'’s'} handwriting from the uploaded image and measured twenty qualities of it. Here is what we detected, with an at-a-glance map of all twenty factors.`;
  // Recognition trust line: keep the reader's confidence calibrated, and make
  // explicit that the 20 factors are geometric and do NOT depend on the reading.
  const rec = (analysis && analysis.recognition) ? analysis.recognition : null;
  const recLevelLabel = rec ? ({ 'passage-verified':'Passage-verified','high':'High confidence','moderate':'Moderate confidence','low':'Low confidence' }[rec.level] || '') : '';
  const recCap = rec
    ? (rec.passage_aligned
        ? `Matched to your reference passage · ${Math.round((rec.passage_match||0)*100)}% match. The 20 factors are measured from geometry and don’t depend on reading the words.`
        : `Reading is assistive${recLevelLabel?(' ('+recLevelLabel+')'):''}. The 20 factors are measured from the geometry of your writing and don’t depend on it.`)
    : 'Recognised from your handwriting.';

  // A plain, prominent note so a reader never mistakes an OCR slip for a flawed
  // report: word-reading is a work in progress; the computer-vision assessment
  // (the 20 factors and the reference crops) is accurate and independent of it.
  const recNote = `<div class="rec-note" style="margin:14px 0 0;padding:13px 16px;border:1px solid rgba(34,40,49,.12);border-left:4px solid var(--accent-deep,#B4502E);border-radius:11px;background:var(--paper-2,#FBF7F1);page-break-inside:avoid;">
    <div style="font-size:11px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:var(--accent-deep,#B4502E);margin-bottom:4px;">Note · text recognition is being improved</div>
    <p style="margin:0;font-size:12.5px;line-height:1.6;color:var(--ink-2,#354052);">Reading your exact words from the photo is an <b>assistive feature that is still being improved</b>, so the recognised text above can contain mistakes on joined or rushed handwriting. <b>This does not change your assessment.</b> Your 20-factor scores and the highlighted reference crops are measured by computer vision from the <b>geometry</b> of your writing (size, spacing, slant, baseline) and remain accurate on their own. For any clarification, contact <a href="mailto:info@vahinitech.com" style="color:var(--accent-deep,#B4502E);font-weight:600;">info@vahinitech.com</a>.</p>
  </div>`;

  // 20-factor scoreboard (strong / developing / focus)
  const allF = analysis.results;
  const isLive = (f)=> !f.unmeasured && (f.imuMeasured || f.conf!=='imu');
  const cnt = { strong:0, dev:0, focus:0 }; allF.forEach(f=>{ if(isLive(f)) cnt[f.band]++; });
  const nOpen = allF.length - (cnt.strong+cnt.dev+cnt.focus);
  const scoreboard = `<div class="ea-panel" style="margin-top:16px;">
    <div class="ea-head act"><span class="t">All 20 factors at a glance</span><span class="tag" style="background:var(--ink);color:#fff;">${cnt.strong} strong · ${cnt.dev} developing · ${cnt.focus} focus${nOpen?' · '+nOpen+' —':''}</span></div>
    <div class="fscore-grid">${allF.map(f=>`<span class="fscore ${f.band}"${isLive(f)?'':' style="opacity:.45;filter:grayscale(.55)"'}><b>${String(f.n).padStart(2,'0')}</b><span class="fs-nm">${esc(f.name)}</span><i>${isLive(f)?f.score.toFixed(1):'—'}</i></span>`).join('')}</div>
  </div>`;
  pages.push(`<section class="page" data-screen-label="Expected vs Actual">
    ${head(imu?'The Sample · What we read':'The Sample · What we read')}
    <div class="sec-title"><div><div class="eyebrow">Detected, recognised &amp; mapped</div><h2>What we read</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
    <p class="lead" style="max-width:82%;margin-bottom:18px;">${introLine}</p>
    <div class="ea-grid">
      <div class="ea-panel">
        <div class="ea-head exp"><span class="t">${showText?'Detected &amp; recognised text':'Text recognition'}</span><span class="tag">${readTag}</span></div>
        ${showText
          ? `<div style="padding:16px 20px;min-height:188px;background:var(--card);"><div style="font-family:var(--sans);font-size:15px;line-height:1.85;color:var(--ink);letter-spacing:.01em;">${shownLines.map(esc).join('<br>')}</div></div>
        <div class="ea-cap">${imu?'Reconstructed from the captured pen path.':recCap}</div>`
          : `<div style="padding:22px 20px;min-height:188px;background:var(--card);display:flex;flex-direction:column;justify-content:center;gap:9px;"><div style="font-family:var(--serif);font-weight:600;color:var(--ink);font-size:17px;">Text recognition not yet enabled for this scan</div><div style="font-size:13px;color:var(--ink-2);line-height:1.6;">This report measures the <b>geometry</b> of the writing — size, spacing, slant, alignment and baseline. Reading the actual words (and the letter-by-letter checks) turns on with the recognition server.</div></div>
        <div class="ea-cap">We don’t print words we didn’t truly read.</div>`}
      </div>
      <div class="ea-panel">
        <div class="ea-head act"><span class="t">${actLabel}</span><span class="tag">${actTag}</span></div>
        <div class="ea-imgslot" style="padding:0;background:#fff;"><img src="${detURL}" style="width:100%;height:210px;object-fit:contain;display:block;background:#fff;" alt="detected sample"></div>
        <div class="ea-cap">${cap2}</div>
      </div>
    </div>
    ${imu?'':recNote}
    ${scoreboard}
    ${qualityStrip(pipeline.quality, pipeline)}
    ${timingStrip(pipeline)}
    ${pipeline.docType ? docTypePanel(pipeline.docType) : ''}
    ${foot(pg)}
  </section>`);

  /* ---------- FACTOR PAGES (by section) ---------- */
  analysis.sections.forEach((s)=>{
    pg=P();
    const cards = s.factors.map(f=>{
      const cf = f.imuMeasured ? CONF_IMU_MEASURED : (CONF[f.conf]||CONF.measured);
      const fx = focusSVG(f);
      const N = window.VahiniNarrate ? window.VahiniNarrate.narrate(f) : null;
      const whyLabel = N ? N.label : (f.band==='strong'?'Why it scored well':f.band==='dev'?'Why it’s developing':'Why this is a focus');
      const why = N ? N.body : plainText(f.evidence);
      const act = N ? N.action : plainText(f.tip);
      const valMap = { 'image proxy':'estimated', 'IMU-pending':'awaits the Battu', 'embedding-pending':'estimated', 'composite':'blended', 'aggregate':'blended' };
      const valShown = valMap[f.value] || plainText(f.value);
      const cr = crops && crops[f.n];
      const penCard = !imu && f.conf==='imu' && !f.imuMeasured;   // photo mode: pen-pending
      const unmeas = f.unmeasured && !penCard;                     // validity gate failed (#8)
      const blank = penCard || unmeas;
      const isM = f.imuMeasured || f.conf==='measured';
      const valNum = blank ? '—' : (isM ? f.score.toFixed(1) : '≈'+Math.round(f.score));
      const valSub = penCard ? ' measured by the Battu' : (unmeas ? ' couldn’t be read from this photo' : ('/10 · '+valShown));
      const bandChip = penCard ? `<span class="f-band" style="background:#E1E3F7;color:#3A45B0;">Not scored</span>`
        : unmeas ? `<span class="f-band" style="background:#F3E7D6;color:#8A5410;">Couldn’t read</span>`
        : `<span class="f-band ${f.band}">${BAND_LABEL[f.band]}</span>`;
      const whyLabelShown = penCard ? 'What this means' : unmeas ? 'Why no score' : whyLabel;
      const whyShown = unmeas
        ? esc(f.unmeasuredReason || 'The measurements for this factor came back outside the plausible range for real handwriting, so the engine will not report a score it cannot stand behind.')
        : why;
      const actShown = penCard ? `Capture a session with the Battu to measure this precisely — a good hand typically lands at <b>${esc(f.target)}</b>.`
        : unmeas ? (f.unmeasuredKind==='writing'
            ? `Nothing to fix in the photo — this simply doesn’t apply to how this sample is written. It will read once the writing has clear, separable ${f.n===9?'letters':'words'}.`
            : `We couldn’t measure this reliably from this photo — re-scan in even, glare-free light with the whole page flat and filling the frame, in sharp focus.`)
        : `<b>Try this&nbsp;·&nbsp;</b>${esc(act)}`;
      const lookShown = cr ? `<b>From your writing</b> — ${esc(cr.caption)}`
        : penCard ? `This lives in the motion of the hand — a photo cannot show it`
        : unmeas ? (f.unmeasuredKind==='writing' ? `Doesn’t apply to this writing style` : `Couldn’t read this reliably from this photo`)
        : `We look at ${esc(fx.look)}`;
      return `<div class="factor">
        <div class="f-top">
          <span class="f-no">${String(f.n).padStart(2,'0')}</span>
          <span class="f-name">${f.name}<small>${unmeas?'<span class="conf-chip" style="color:#8A5410;background:#F3E7D6">Unverified</span>':`<span class="conf-chip" style="color:${cf.c};background:${cf.bg}">${cf.t}</span>`}</small></span>
          ${bandChip}
        </div>
        <div class="f-focus">${cr?`<img class="f-crop" src="${cr.url}" alt="from your writing">`:fx.svg}</div>
        <div class="f-look"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4-4"/></svg>${lookShown}${f.basedOn&&!blank?` · ${esc(f.basedOn)}`:''}</div>
        <div class="f-metric">
          <span class="f-val">${valNum}<small>${valSub}</small></span>
          <span class="f-ideal">Target&nbsp; <b>${esc(f.target)}</b></span>
        </div>
        <div class="f-scorebar"><i style="width:${blank?0:f.score100}%;background:${BAND_COLOR[f.band]}"></i></div>
        <p class="f-why"><b>${whyLabelShown}:</b> ${esc(whyShown)}</p>
        <div class="f-tip">${actShown}</div>
      </div>`;
    }).join('');
    pages.push(`<section class="page" data-screen-label="Factors — ${s.name}">
      ${head('The 20 Factors · '+s.name)}
      <div class="cat-band"><span class="cb-ico" style="color:var(--accent-deep)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${SEC_ICON[s.id]}</svg></span><span class="cb-no">SECTION</span><span class="cb-name">${s.name}</span><span class="cb-rule"></span><span class="cb-no" style="color:var(--muted)">avg ${s.avg100==null?'—':s.avg100} · ${Math.round(s.weight*100)}% weight</span></div>
      <p class="lead" style="margin:-4px 0 16px;max-width:82%;">${esc(s.blurb)}.</p>
      <div class="factor-grid">${cards}</div>
      ${foot(pg)}
    </section>`);
  });

  /* ---------- LETTER-LEVEL FINDINGS (what a coach checks) ---------- */
  if (ocrReal && letterFindings && letterFindings.ok){
    pg=P();
    const LF = letterFindings;
    const chipOf = (state)=> state==='good' ? '<span class="ll-chip good">Looks good</span>' : state==='check' ? '<span class="ll-chip check">Check this</span>' : '<span class="ll-chip info">Worth knowing</span>';

    // 1. style
    const styleState = LF.style.mixed ? 'check' : 'good';
    const styleBody = LF.style.mixed
      ? `Your sample mixes two styles — ${LF.style.printCount} word${LF.style.printCount!==1?'s':''} printed letter-by-letter and ${LF.style.joinedCount} written joined. Coaches recommend settling into <b>one</b> style: either neat print or fluent joined writing — mixing both mid-page slows you down and looks uneven${LF.style.exWords&&LF.style.exWords.length===2?` (compare “${esc(LF.style.exWords[0])}” and “${esc(LF.style.exWords[1])}” below)`:''}.`
      : `Your writing keeps to one style — ${LF.style.verdict==='joined'?'joined (cursive-leaning)':'clear print'} — across the sample. That consistency is exactly what coaches look for.`;

    // 2. capitals mid-word
    const caseState = LF.caseMix.count ? 'check' : 'good';
    const caseBody = LF.caseMix.count
      ? `${LF.caseMix.count} word${LF.caseMix.count!==1?'s':''} show a letter written much taller than its neighbours mid-word — often a capital slipping in (${LF.caseMix.examples.map(e=>`“${esc(e.ch)}” in “${esc(e.word)}”`).join(', ')}). Capitals belong at the start of names and sentences; mid-word they break the visual rhythm.`
      : `No capitals or oversized letters appear mid-word — your lowercase letters stay lowercase, exactly as they should.`;

    // 3. letter-form consistency
    let formState='info', formBody='', formTitle='Same letter, same shape?';
    if (LF.formVar && LF.formVar.cropURL){
      formState='check';
      formBody=`Your letter “<b>${esc(LF.formVar.ch)}</b>” appears ${LF.formVar.n} times and is written in noticeably different ways (narrowest → widest below). A letter that changes shape every time forces the reader to re-decode it — pick the form you like and repeat it until it’s automatic.`;
    } else if (LF.formVar){
      formState='good';
      formBody=`We compared every repeat of your most-used letters — “${esc(LF.formVar.ch)}” appears ${LF.formVar.n} times with essentially the same shape each time. Repeatable letterforms are the mark of a settled hand.`;
    } else { formBody='Not enough repeated letters in this sample to compare shapes — a longer passage lets us check this.'; }

    // 4. punctuation
    const pn = LF.punct;
    const punctState = pn.expected===0 ? 'info' : (pn.found >= pn.expected ? 'good' : 'check');
    const punctBody = pn.expected===0
      ? 'The passage has no punctuation to check in this sample.'
      : `The passage contains <b>${pn.expected}</b> punctuation mark${pn.expected!==1?'s':''} (${pn.stops} full stop${pn.stops!==1?'s':''}). We found <b>${pn.found}</b> dot-sized mark${pn.found!==1?'s':''} in your writing${pn.found<pn.expected?' — some full stops or commas may be missing or too faint. Tiny as they are, they are how a reader breathes':''}.`;

    // 5. word audit
    let auditBody, auditState;
    if (!LF.audit.length){ auditState='good'; auditBody = LF.auditMode==='ocr' ? 'AI text recognition read every word as expected — no spelling slips detected.' : 'Every print-style word has the expected number of letter pieces — nothing looks dropped or doubled.'; }
    else if (LF.auditMode==='ocr'){ auditState='check'; auditBody = `Recognition read ${LF.audit.length} word${LF.audit.length!==1?'s':''} differently from the passage: ${LF.audit.map(a=>`“${esc(a.got)}” for “${esc(a.expected)}”`).join(', ')} — worth checking whether it’s spelling or letter shapes confusing the reader.`; }
    else { auditState='check'; auditBody = `${LF.audit.length} word${LF.audit.length!==1?'s':''} have noticeably more or fewer letter pieces than expected (${LF.audit.map(a=>`“${esc(a.expected)}”`).join(', ')}) — a letter may be missing, doubled, or two letters may have merged. With the recognition server connected this becomes a true spelling check.`; }

    // 2b. sentence-start capitals
    const sc2 = LF.sentCaps || { checked:0, missing:0 };
    const sentState = sc2.checked===0 ? 'info' : (sc2.missing ? 'check' : 'good');
    const sentBody = sc2.checked===0
      ? 'No sentence starts could be matched in this sample.'
      : (sc2.missing
        ? `${sc2.missing} of ${sc2.checked} sentence${sc2.checked!==1?'s':''} start${sc2.missing===1?'s':''} without a clearly taller capital${sc2.example?` (“${esc(sc2.example.word)}” below)`:''}. A capital at every sentence start is the first thing examiners look for.`
        : `All ${sc2.checked} sentence starts open with a clearly taller capital letter — textbook.`);

    // craft of the words (merged from the former Writing Craft page)
    let craftState='info', craftBody='';
    if (window.VahiniCraft){
      const craft = window.VahiniCraft.analyze(recognizedText || expectedText, pipeline.docType && pipeline.docType.key);
      if (craft.runGrammar && craft.count){
        craftState='check';
        craftBody = `Reading the words themselves (${ocrEngine==='server'?'via AI text recognition':'against the reference passage'}): ${craft.findings.slice(0,2).map(f=>`<b>${esc(f.cat)}</b> — ${esc(f.msg)}`).join('; ')}${craft.count>2?` …and ${craft.count-2} more`:''}.`;
      } else if (craft.runGrammar){
        craftState='good';
        craftBody = `We also read the words themselves — no common slips (homophones, missing words, sign-off errors) in the recognised text.`;
      } else {
        craftBody = esc(craft.intro||'Content-level checks apply once the text is recognised.');
      }
    }

    const block = (no, title, state, body, img, cap)=>`<div class="ll-block">
      <div class="ll-head"><span class="ll-no">${no}</span><h4>${title}</h4>${chipOf(state)}</div>
      <p class="ll-body">${body}</p>
      ${img?`<div class="ll-evi"><img src="${img}" alt="from your writing"><span>${esc(cap||'from your writing')}</span></div>`:''}
    </div>`;

    pages.push(`<section class="page" data-screen-label="Letter-Level Findings">
      ${head('Letter-Level Findings · What a Coach Checks')}
      <div class="sec-title"><div><div class="eyebrow">Beyond the 20 factors · based on ${LF.basis} matched words</div><h2>Letter by letter</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
      <p class="lead" style="max-width:84%;margin-bottom:14px;">A handwriting coach doesn’t stop at measurements — they look at <b>each letter</b>: is the style consistent, do capitals stray mid-word, does the same letter keep the same shape, is the punctuation there? Because ${esc(name)} copied a known passage, we can check each of these against the ink itself.</p>
      ${block(1,'One style, or a mix?', styleState, styleBody, LF.style.cropURL, LF.style.exWords?`“${LF.style.exWords[0]}” (printed) · “${LF.style.exWords[1]}” (joined)`:'')}
      ${block(2,'Capitals in the middle of words', caseState, caseBody, LF.caseMix.examples[0]&&LF.caseMix.examples[0].url, LF.caseMix.examples[0]?`the tall letter is boxed — “${LF.caseMix.examples[0].word}”`:'')}
      ${block(3,'Capitals where sentences start', sentState, sentBody, sc2.example&&sc2.example.url, sc2.example?`first letter boxed — “${sc2.example.word}”`:'')}
      ${block(4, formTitle, formState, formBody, LF.formVar&&LF.formVar.cropURL, LF.formVar&&LF.formVar.cropURL?`your “${LF.formVar.ch}” — narrowest, typical, widest`:'')}
      ${block(5,'Punctuation — the small marks that matter', punctState, punctBody, null)}
      ${block(6,'Word check', auditState, auditBody, LF.audit[0]&&LF.audit[0].url, LF.audit[0]&&LF.audit[0].url?`“${LF.audit[0].expected}” as written`:'')}
      ${craftBody?block(7,'The craft of the words', craftState, craftBody, null):''}
      ${foot(pg, LF.auditMode==='ocr'?'Letter findings sharpened by AI text recognition':'Letter findings from geometry · recognition server sharpens them further')}
    </section>`);
  }

  /* ---------- EXERCISES (analysis-driven: only what's actually weak) ---------- */
  pg=P();
  // DRILL map + drills are computed at the top of render() and shared with the Scorecard.

  const strengths = analysis.topStrong.slice(0,2).map(f=>f.name.toLowerCase());
  const weakNames = prescribedFactors.slice(0,3).map(f=>f.name.toLowerCase());
  const joinList = (a)=> a.length<2 ? (a[0]||'') : a.slice(0,-1).join(', ')+' and '+a[a.length-1];
  const justify = maintenance
    ? `${esc(name)} is consistent across all four sections — there is no single weak spot. The light drills below simply keep the hand sharp; re-test in a few weeks to hold the gains.`
    : `${esc(name)}’s strengths — <b>${joinList(strengths)}</b> — are already solid and need no practice right now. The measurements show the score is held back most by <b>${joinList(weakNames)}</b>. We are not prescribing generic worksheets: each drill below was chosen to train exactly one of these, so a few focused minutes go straight to what will move the score.`;

  const exCards = drills.map(d=>{
    const allAddr = d.factors.map(f=>f.name);
    const addresses = allAddr.slice(0,2);              // cap each drill at 1–2 primary targets (#10)
    const extraAddr = allAddr.length - addresses.length;
    const why = `Because ${joinList(addresses.map(a=>a.toLowerCase()))} ${addresses.length>1?'are':'is'} below target, this drill builds ${DRILL[d.type].goal}.`;
    return `<div class="ex-card">
      <div class="ex-info">
        <div class="ex-head"><span class="ex-tag">${maintenance?'Maintain':'Priority'}</span><span class="ex-grp">addresses: ${esc(addresses.join(' · '))}${extraAddr>0?' (+'+extraAddr+' more)':''}</span></div>
        <div class="ex-title">${DRILL[d.type].title}</div>
        <p class="ex-why"><b>${d.low.toFixed(1)}/10 lowest.</b> ${esc(why)}</p>
        <span class="ex-reps"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M20 6 9 17l-5-5"/></svg>5–10 min · 3× a week</span>
      </div>
      <div class="ex-rail">${exDraw(d.type)}<div class="rl-cap"><span>${EX_CAP[d.type][0]}</span><span>${EX_CAP[d.type][1]}</span></div></div>
    </div>`;
  }).join('');
  const roleBlock = rc.show==='kid' ?
    `<div class="mascot-strip"><svg class="m-svg" viewBox="0 0 120 120" fill="none"><rect x="46" y="20" width="28" height="62" rx="14" fill="var(--accent)"/><rect x="46" y="20" width="28" height="14" rx="13" fill="#E6A23C"/><path d="M46 82 h28 l-14 18 z" fill="#F2D8A7"/><path d="M60 100 l-5 -7 h10 z" fill="#1C2236"/><circle cx="55" cy="48" r="3.4" fill="#fff"/><circle cx="65" cy="48" r="3.4" fill="#fff"/><circle cx="55" cy="48" r="1.6" fill="#1C2236"/><circle cx="65" cy="48" r="1.6" fill="#1C2236"/><path d="M54 58 q6 5 12 0" stroke="#1C2236" stroke-width="2.2" fill="none" stroke-linecap="round"/></svg><div><h4>${esc(rc.greet(name))} ✏️</h4><p>Practise just these ${drills.length} drill${drills.length>1?'s':''} — nothing else — for a few minutes, ${drills.length>1?'a different one each day':'three times a week'}. Re-scan in a week to watch ${rc.you==='you'?'your':rc.you+'\u2019s'} score climb!</p></div></div>` :
    rc.show==='coach' ?
    `<div class="coach-block"><div class="coach-notes"><h4>Instructor observations</h4><div class="note-lines"></div></div><div class="coach-notes"><h4>Plan &amp; sign-off</h4><div class="note-lines" style="height:84px;"></div><div class="sign-row"><div class="sl">${esc(intake.org||'Instructor')} signature</div><div class="sl">Date</div></div></div></div>` :
    `<div class="mascot-strip" style="grid-template-columns:1fr;background:linear-gradient(135deg,var(--paper-2),var(--accent-soft));"><div><h4>Your practice, your pace</h4><p>Work only the drills above — they target your actual weak spots. Re-test whenever you like and track how the score moves.</p></div></div>`;
  pages.push(`<section class="page ex-page" data-screen-label="Exercises">
    ${head('Personalized Exercises')}
    <div class="sec-title"><div><div class="eyebrow">Chosen from ${esc(name)}’s own results</div><h2>Your drill prescription</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
    <div class="ex-banner"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 8v5M12 16h.01"/></svg><span>${justify}</span></div>
    <div class="ex-list">${exCards}</div>
    <div class="ex-foundations" style="margin-top:16px;border:1px solid rgba(0,0,0,.09);border-radius:14px;padding:16px 20px;background:var(--paper-2);page-break-inside:avoid;">
      <div style="display:flex;align-items:center;gap:9px;font-weight:700;font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:var(--accent-deep);margin-bottom:12px;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;"><path d="M12 2 2 7l10 5 10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/></svg>Before any drill — the four foundations</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;">
        <div><b style="display:block;font-size:13.5px;margin-bottom:3px;">Grip</b><span style="font-size:11.5px;line-height:1.5;color:#4b5563;">Dynamic tripod — hold an inch above the tip, middle finger underneath, thumb left, index right.</span></div>
        <div><b style="display:block;font-size:13.5px;margin-bottom:3px;">Posture</b><span style="font-size:11.5px;line-height:1.5;color:#4b5563;">Spine straight; keep the page 25–30 cm from the eyes and tilted slightly left (right-handers).</span></div>
        <div><b style="display:block;font-size:13.5px;margin-bottom:3px;">Pressure</b><span style="font-size:11.5px;line-height:1.5;color:#4b5563;">Write light — about 20% force. If the fingertip whitens or the page embosses, ease off.</span></div>
        <div><b style="display:block;font-size:13.5px;margin-bottom:3px;">Warm-up</b><span style="font-size:11.5px;line-height:1.5;color:#4b5563;">2 minutes of clockwise + anticlockwise circles and figure-8s — the strokes every script shares.</span></div>
      </div>
      <p style="margin:12px 0 0;font-size:10.5px;color:#6b7280;">Foundations follow established handwriting-coaching practice — grip, posture, pen pressure and pre-writing strokes — the basics every legible hand is built on.</p>
    </div>
    ${roleBlock}
    <div class="ex-contact"><span class="ec-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6" stroke-linecap="round"/></svg></span><div><h4>Need a personalized PDF exercise pack?</h4><p>For a printable workbook tailored to these focus areas, contact <a href="mailto:info@vahinitech.com">info@vahinitech.com</a>.</p></div></div>
    ${foot(pg,'Personalized packs: info@vahinitech.com')}
  </section>`);

  /* ---------- GROWTH FORECAST (prediction) ---------- */
  if (window.VahiniForecast){
    pg=P();
    const fc = window.VahiniForecast.compute(analysis, imu, pipeline, overall);
    const fluentLine = fc.fluency.imageOnly
      ? 'image-based estimate — motion not yet measured'
      : (fc.fluency.alreadyFluent
        ? 'Already fast &amp; efficient'
        : (fc.fluency.weeksToFluent!=null ? `~${fc.fluency.weeksToFluent} weeks to fluent` : 'with steady practice'));
    const card = (k,big,sub,accent)=>`<div style="background:var(--card);border:1px solid var(--hair);border-radius:14px;padding:17px 18px;">
      <div style="font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:700;">${k}</div>
      <div style="font-family:var(--serif);font-size:27px;line-height:1.05;margin:7px 0 4px;color:${accent||'var(--ink)'};">${big}</div>
      <div style="font-size:11px;color:var(--ink-2);line-height:1.4;">${sub}</div></div>`;
    const upliftRows = fc.factorUplift.map(u=>{
      const nowPct=u.now*10, projPct=u.proj*10;
      return `<div style="display:grid;grid-template-columns:150px 1fr auto;align-items:center;gap:12px;margin-bottom:9px;">
        <span style="font-size:11.5px;font-weight:700;color:var(--ink);">${u.name}</span>
        <span style="position:relative;height:9px;border-radius:99px;background:var(--paper-2);overflow:hidden;">
          <i style="position:absolute;left:0;top:0;height:100%;width:${projPct}%;background:var(--accent);opacity:.28;border-radius:99px;"></i>
          <i style="position:absolute;left:0;top:0;height:100%;width:${nowPct}%;background:var(--grow);border-radius:99px;"></i>
        </span>
        <span style="font-family:var(--serif);font-size:13px;color:var(--ink);min-width:74px;text-align:right;">${u.now.toFixed(1)} <span style="color:var(--muted);">→</span> <b style="color:var(--accent-deep);">${u.proj.toFixed(1)}</b></span>
      </div>`;
    }).join('');
    pages.push(`<section class="page" data-screen-label="Growth Forecast">
      ${head('Growth Forecast · Prediction')}
      <div class="sec-title"><div><div class="eyebrow">If ${esc(name)} practises the prescribed drills</div><h2>The road ahead</h2></div><div class="sec-no">Page ${String(pg).padStart(2,'0')}</div></div>
      <p class="lead" style="max-width:84%;margin-bottom:16px;">Based on ${fc.source==='imu'?'the live pen dynamics and':'the'} measured consistency in this sample, here is a projection of where ${rc.you==='you'?'your':rc.you+'\u2019s'} writing is heading over <b>${fc.horizon} weeks</b> of steady practice — and when it becomes <b>fast &amp; efficient</b>.</p>

      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:18px;">
        ${card('Projected overall', `${fc.overallNow} <span style="color:var(--muted);font-size:20px;">→</span> ${fc.projLow}–${fc.projHigh}`, `<b style="color:var(--grow);">+${fc.projLow-fc.overallNow} to +${fc.projHigh-fc.overallNow} points</b> projected over ${fc.horizon} weeks`, 'var(--ink)')}
        ${card('Writing fluency', fc.fluency.bandNow, `${fluentLine} · maturity ${fc.fluency.maturityNow}% <span style="color:var(--muted);">→</span> ${fc.fluency.maturityProj}%`, 'var(--accent-deep)')}
        ${card('Next milestone', `${MILESTONE}<span style="font-size:18px;color:var(--muted);"> /100</span>`, `reachable by lifting ${esc(topWeakNames.join(' and '))}`, 'var(--grow)')}
      </div>

      <div class="ea-panel" style="margin-bottom:16px;">
        <div class="ea-head act"><span class="t">Projected overall score · ${fc.horizon}-week trajectory</span><span class="tag">estimate</span></div>
        <div style="padding:10px 14px 4px;">${trajectoryChart(fc.curve, fc.overallNow, fc.overallProj)}</div>
      </div>

      <div class="cat-band"><span class="cb-no" style="color:var(--accent-deep)">UPLIFT</span><span class="cb-name" style="font-size:17px;">Where the gains come from</span><span class="cb-rule"></span><span class="cb-no" style="color:var(--muted)"><span style="color:var(--grow);">●</span> now &nbsp; <span style="color:var(--accent);opacity:.5;">●</span> projected</span></div>
      ${upliftRows}

      <div style="margin-top:14px;font-size:10.5px;color:var(--muted);line-height:1.5;background:var(--paper-2);border-radius:10px;padding:11px 15px;">
        <b style="color:var(--ink-2);">How to read this:</b> projections assume ~10 minutes of the prescribed drills, 3× a week. They model a normal learning curve (fast early gains, then levelling off) and are a motivational estimate — not a guarantee. Re-test with Vahini to track the real curve against this one.
      </div>
      ${foot(pg,'Projection — assumes consistent practice')}
    </section>`);
  }
  /* ---------- CERTIFICATE (student tier — one colourful page) ---------- */
  if (rc.show==='kid'){
    pg=P();
    const stars = Math.max(1, Math.min(5, Math.round(overall/20)));
    const starRow = [1,2,3,4,5].map(i=>`<svg viewBox="0 0 24 24" width="34" height="34" ${i<=stars?'fill="#C29A45"':'fill="none" stroke="#C29A45" stroke-width="2"'}><path d="M12 2l3 6.5 7 .7-5.2 4.7 1.5 6.9L12 17l-6.3 3.8L7.2 14 2 9.2l7-.7z"/></svg>`).join('');
    pages.push(`<section class="page cert-page" data-screen-label="Certificate">
      <div class="cert-frame">
        <div class="cert-top"><img src="${logo}" alt="">${orgLogo?`<img src="${orgLogo}" alt="" style="border-radius:8px;">`:''}</div>
        <div class="cert-kicker">Vahini Handwriting Explorer</div>
        <h1 class="cert-name">${esc(name)}</h1>
        <p class="cert-line">completed a 20-factor handwriting analysis and earned</p>
        <div class="cert-score">${overall}<small>/100</small></div>
        <div class="cert-stars">${starRow}</div>
        <p class="cert-line">Your next missions — a few fun minutes, three times a week:</p>
        <div class="cert-drills">${drills.map(d=>`<span class="cert-drill">✏️ ${DRILL[d.type].title}</span>`).join('')}</div>
        <svg class="m-svg cert-mascot" viewBox="0 0 120 120" fill="none"><rect x="46" y="20" width="28" height="62" rx="14" fill="var(--accent)"/><rect x="46" y="20" width="28" height="14" rx="13" fill="#E6A23C"/><path d="M46 82 h28 l-14 18 z" fill="#F2D8A7"/><path d="M60 100 l-5 -7 h10 z" fill="#1C2236"/><circle cx="55" cy="48" r="3.4" fill="#fff"/><circle cx="65" cy="48" r="3.4" fill="#fff"/><circle cx="55" cy="48" r="1.6" fill="#1C2236"/><circle cx="65" cy="48" r="1.6" fill="#1C2236"/><path d="M54 58 q6 5 12 0" stroke="#1C2236" stroke-width="2.2" fill="none" stroke-linecap="round"/></svg>
        <div class="cert-foot"><span>${today}</span><span class="cert-sign">— the Vahini team</span></div>
      </div>
      ${foot(pg,'Re-scan in 2–4 weeks to earn more stars')}
    </section>`);
  }

  pg=P();
  pages.push(`<section class="page" data-screen-label="About & Disclaimer">
    ${head('About & Important Notes')}
    <div class="about-hero">
      <div><div class="eyebrow">About the technology</div><h2>Handwriting, measured with care.</h2>
        <p>Vahini turns handwriting into clear, kind insight. Most of the twenty factors are <b style="color:var(--ink)">measured</b> by deterministic computer vision — spacing, baseline, slant, size, margins — not predicted. The IMU sensor pen adds the dynamics factors (speed, pressure, pen-lifts) that a static image cannot see.</p>
        <p style="margin-top:10px;"><b style="color:var(--ink)">Vahini IMU Sensor Pen</b> — protected under <b style="color:var(--ink)">Patent No. 584433</b>.</p></div>
      <div class="pen-figure"><svg viewBox="0 0 120 120" fill="none"><rect x="54" y="14" width="14" height="74" rx="7" fill="#fff"/><rect x="54" y="14" width="14" height="20" rx="7" fill="var(--accent)"/><path d="M54 88 h14 l-7 16 z" fill="#E9DEC8"/><path d="M61 104 l-3 -6 h6 z" fill="#1C2236"/><circle cx="61" cy="44" r="2.5" fill="#1C2236"/></svg></div>
    </div>
    <div class="contact-grid">
      ${[['Website','vahinitech.com','https://vahinitech.com','Learn about the pen, the science and how to re-test.'],['General queries','info@vahinitech.com','mailto:info@vahinitech.com','Questions about this report or your pen.'],['Personalized support','info@vahinitech.com','mailto:info@vahinitech.com','One-to-one coaching plans and tailored guidance.']].map(c=>`<div class="contact-card"><div class="cc-ico" style="color:var(--accent-deep)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6" stroke-linecap="round"/></svg></div><div class="cc-k">${c[0]}</div><div class="cc-v"><a href="${c[2]}">${c[1]}</a></div><div class="cc-s">${c[3]}</div></div>`).join('')}
    </div>
    <div class="methods-cite">
      <div class="mc-h"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h12a2 2 0 0 1 2 2v12a2 2 0 0 0-2-2H4zM4 5v12a2 2 0 0 0 2 2h12" transform="translate(1 0)"/></svg> Methods &amp; research foundations</div>
      <p>The analysis builds on established, peer-reviewed handwriting science rather than guesswork. Letter, line and word geometry use standard document-analysis methods (Otsu and adaptive thresholding; connected-component segmentation; least-squares baseline fitting; projection-profile <b>shear deslanting</b> for slant). The IMU pen's motion analysis follows the handwriting <b>motor-model</b> tradition — segmenting writing into ballistic strokes at <b>velocity minima</b>. The practice guidance pairs this with established handwriting-coaching pedagogy — dynamic-tripod grip, posture, light pen pressure and the clockwise/anticlockwise pre-writing strokes shared across Telugu, Hindi, Tamil, Kannada and English.</p>
      <div class="mc-refs">
        <span>Otsu (1979), <i>Threshold selection from gray-level histograms</i></span>
        <span>Bradley &amp; Roth (2007), <i>Adaptive thresholding via the integral image</i></span>
        <span>Schomaker (1993), <i>Stroke/character self-organizing maps for on-line cursive script</i>, Pattern Recognition 26(3)</span>
        <span>Schomaker &amp; Teulings (1990), <i>A handwriting recognition system based on the human motor system</i>, IWFHR</span>
      </div>
    </div>
    <div class="disclaimer">
      <h4><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg> Important — please read</h4>
      <p>This report is intended <b>solely for personal handwriting improvement, education and skill-building</b>. The twenty factors describe measurable features of writing form, spacing and motion; the notes are general, encouraging guidance — not statements about a person's health, intelligence, personality or character.</p>
      <p>This report is <b>not a medical, psychological, neurological or diagnostic assessment</b> and must not be used to diagnose, screen for, or rule out any condition (including dysgraphia or learning differences). If you have such concerns, please consult a qualified professional. Results may vary with the writing sample, pen, surface and lighting.</p>
    </div>
    <div class="patent-strip"><span>© ${new Date().getFullYear()} Vahini Technologies</span><span class="ps-dot"></span><span>IMU Sensor Pen · Patent No. 584433</span><span class="ps-dot"></span><span>vahinitech.com</span></div>
    ${foot(pg,'info@vahinitech.com')}
  </section>`);

  // ---- build the Table of Contents into the reserved slot ----
  const tocRows = [];
  pages.forEach((p)=>{
    if (!p) return;
    const lm = p.match(/data-screen-label="([^"]+)"/);
    const nm = p.match(/class="pg-num">(\d+)</);
    if (lm && nm){
      let label = lm[1].replace(/Factors — /,'').replace(/&amp;/g,'&');
      if (label==='Cover') return;
      tocRows.push({ label, pg: nm[1] });
    }
  });
  const tocHTML = `<section class="page toc-page" data-screen-label="Contents">
    ${head('Contents')}
    <div class="sec-title"><div><div class="eyebrow">What’s inside</div><h2>Contents</h2></div><div class="sec-no">Page ${String(tocPg).padStart(2,'0')}</div></div>
    <p class="lead" style="max-width:80%;margin-bottom:18px;">A measurement-based handwriting report in ${tocRows.length+1} parts — from the at-a-glance summary, through all 20 factors with a visual of exactly what each one looks at, to a personalised practice plan and growth forecast.</p>
    <div class="toc-list">
      ${tocRows.map((r,i)=>`<div class="toc-row"><span class="toc-n">${String(i+1).padStart(2,'0')}</span><span class="toc-label">${esc(r.label)}</span><span class="toc-dots"></span><span class="toc-pg">${r.pg}</span></div>`).join('')}
    </div>
    <div class="toc-legend">
      <div class="tl-h">How to read each factor</div>
      <div class="tl-items">
        <span class="tl"><span class="sw" style="background:var(--grow)"></span>Strong — matches the model</span>
        <span class="tl"><span class="sw" style="background:var(--gold)"></span>Developing — room to refine</span>
        <span class="tl"><span class="sw" style="background:var(--band-focus)"></span>Focus area — practise next</span>
        <span class="tl"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="var(--accent-deep)" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4-4"/></svg>“We look at…” shows the exact part of the writing measured</span>
      </div>
    </div>
    ${foot(tocPg)}
  </section>`;
  pages[tocIdx] = tocHTML;

  host.innerHTML = pages.join('');
}

global.VahiniReport = { render };
})(window);
