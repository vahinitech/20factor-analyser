/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   VAHINI Report, data + rendering
   ========================================================================= */

/* ---- Category icons (inline SVG, stroke=currentColor) ------------------- */
const ICONS = {
  slant: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M9 20 15 4M5 20 11 4M13 20 19 4"/></svg>',
  zone:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/><path d="M8 4v16" stroke-dasharray="2 2"/></svg>',
  space: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6v12M18 6v12"/><path d="M9 12h6M9 12l2-2M9 12l2 2M15 12l-2-2M15 12l-2 2"/></svg>',
  margin:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 3v18" stroke-dasharray="2 2"/></svg>',
  press: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 19h14"/><circle cx="9" cy="13" r="2.5"/><circle cx="15" cy="11" r="3.5"/></svg>',
};

/* ---- Category definitions ---------------------------------------------- */
const CATS = [
  { id:'slant', no:'A', name:'Slant & Baseline', sub:'Direction, tilt & form', icon:'slant',
    blurb:'How letters lean and how steadily the writing rides the line.' },
  { id:'size',  no:'B', name:'Size & Zones',     sub:'Proportion of the three zones', icon:'zone',
    blurb:'Letter height and the balance between upper, middle and lower zones.' },
  { id:'space', no:'C', name:'Spacing & Rhythm', sub:'Breathing room & flow', icon:'space',
    blurb:'The white space between letters, words and lines.' },
  { id:'margin',no:'D', name:'Margins & Layout', sub:'How the page is framed', icon:'margin',
    blurb:'Use of the page edges, planning, pacing and presentation.' },
  { id:'press', no:'E', name:'Pressure & Stroke',sub:'Captured by the IMU pen', icon:'press',
    blurb:'Pen force and ink width, measured live by the Vahini sensor pen.' },
];

/* ---- The 20 factors ----------------------------------------------------- */
const FACTORS = [
  // --- A: Slant & baseline ---
  { n:1, cat:'slant', name:'Slant Angle', sys:'_01_slant_angle', val:'6°', unit:'right', ideal:'5°–8° right', band:'strong', score:88, viz:'slant', vmode:'even',
    mean:'Letters lean a gentle 6° to the right, a warm, forward-moving slant that reads as engaged and friendly.',
    tip:'Keep this lovely, steady lean. Try not to let it tip past 12° when writing quickly.' },
  { n:2, cat:'slant', name:'Slant Consistency', sys:'_02_slant_consistency', val:'82%', unit:'uniform', ideal:'above 80%', band:'strong', score:84, viz:'slant', vmode:'mixed',
    mean:'Most letters point the same way. A few capitals stand a little straighter, which is completely normal at this stage.',
    tip:'Practise the letters b, d and k slowly, these are the ones drifting upright.' },
  { n:3, cat:'slant', name:'Baseline Angle', sys:'_03_baseline_angle', val:'+3°', unit:'rising', ideal:'within ±2°', band:'dev', score:70, viz:'base', vmode:'rise',
    mean:'Lines climb slightly uphill as they cross the page, often a sign of optimism and energy, but it can make longer pieces look uneven.',
    tip:'Use a lightly lined sheet and pause at the right margin to reset your hand to the line.' },
  { n:4, cat:'slant', name:'Baseline Curvature', sys:'_04_baseline_curvature', val:'Low', unit:'gentle dip', ideal:'near flat', band:'dev', score:66, viz:'base', vmode:'wave',
    mean:'Words sag a touch in the middle of each line before lifting at the end, the hand is tiring slightly mid-line.',
    tip:'Rest your forearm fully on the desk so the whole arm glides, not just the fingers.' },

  // --- B: Size & zones ---
  { n:5, cat:'size', name:'Letter Size (Mean)', sys:'_05_letter_size_mean', val:'3.1', unit:'mm x-height', ideal:'2.5–3.5 mm', band:'strong', score:86, viz:'size', vmode:'even',
    mean:'A comfortable, readable middle-zone height, neither cramped nor sprawling. Great control for this age.',
    tip:'Nothing to change. Keep matching this height to the ruled lines you write on.' },
  { n:6, cat:'size', name:'Letter Size Variability', sys:'_06_letter_size_variability', val:'22%', unit:'variation', ideal:'below 18%', band:'focus', score:58, viz:'size', vmode:'varied',
    mean:'Some letters jump larger than their neighbours, so words look a little bouncy. This is the biggest single thing to smooth out.',
    tip:'Try "two-finger" sizing: keep every middle-zone letter as tall as two stacked fingertips.' },
  { n:18, cat:'size', name:'Upper Zone Ratio', sys:'_18_upper_zone_ratio', val:'34%', unit:'of height', ideal:'~33%', band:'strong', score:85, viz:'zone', vmode:'upper',
    mean:'Tall letters (l, h, t, b) reach a healthy height, a sign of confidence and imagination in graphology.',
    tip:'Beautifully balanced. Make sure loops on l and h stay open, not pinched.' },
  { n:19, cat:'size', name:'Middle Zone Ratio', sys:'_19_middle_zone_ratio', val:'41%', unit:'of height', ideal:'~34%', band:'dev', score:68, viz:'zone', vmode:'middle',
    mean:'The middle body of letters is a little dominant, which can crowd the ascenders and descenders.',
    tip:'Give a touch more length to tails (g, y, p) so the three zones share space evenly.' },
  { n:20, cat:'size', name:'Lower Zone Ratio', sys:'_20_lower_zone_ratio', val:'25%', unit:'of height', ideal:'~33%', band:'focus', score:60, viz:'zone', vmode:'lower',
    mean:'Descenders (g, j, y, p) are running short, so the writing sits high on the line. Lengthening them adds rhythm and flow.',
    tip:'Practise rows of g and y, letting the tail dip a full zone below the line.' },

  // --- C: Spacing & rhythm ---
  { n:7, cat:'space', name:'Word Spacing', sys:'_07_word_spacing', val:'1.0×', unit:'letter width', ideal:'~1.0×', band:'strong', score:84, viz:'space', vmode:'word',
    mean:'Gaps between words are just right, about one lowercase "o" wide. This makes the writing very easy to read.',
    tip:'Keep using the "one finger gap" trick between words. It is working perfectly.' },
  { n:8, cat:'space', name:'Letter Spacing', sys:'_08_letter_spacing', val:'0.6×', unit:'tight', ideal:'0.8–1.0×', band:'dev', score:64, viz:'space', vmode:'letter',
    mean:'Letters sit a little close together, so words can look squeezed. Opening them up will instantly look neater.',
    tip:'Imagine a thin matchstick could stand between each letter, and leave just that much room.' },
  { n:9, cat:'space', name:'Line Spacing', sys:'_09_line_spacing', val:'1.6×', unit:'line height', ideal:'1.5–1.8×', band:'strong', score:88, viz:'line', vmode:'line',
    mean:'Lines are well separated, with no tangling between descenders and the row below. Excellent page hygiene.',
    tip:'No change needed, this clarity is a real strength.' },

  // --- D: Margins & layout ---
  { n:10, cat:'margin', name:'Top Margin', sys:'_10_margin_top', val:'18', unit:'mm', ideal:'15–20 mm', band:'strong', score:86, viz:'margin', vmode:'top',
    mean:'A generous, confident start from the top of the page, shows good planning before writing begins.',
    tip:'Keep starting here. It frames the work beautifully.' },
  { n:11, cat:'margin', name:'Bottom Margin', sys:'_11_margin_bottom', val:'9', unit:'mm', ideal:'12–18 mm', band:'focus', score:56, viz:'margin', vmode:'bottom',
    mean:'Writing runs quite far down the page, leaving little breathing room at the foot. Often a sign of squeezing work in at the end.',
    tip:'Plan to stop two lines earlier. Leaving a footer of space makes any page look polished.' },
  { n:12, cat:'margin', name:'Left Margin', sys:'_12_margin_left', val:'16', unit:'mm even', ideal:'15–20 mm', band:'strong', score:90, viz:'margin', vmode:'left',
    mean:'A crisp, even left margin down the whole page, one of the clearest signs of an organised, steady hand.',
    tip:'Outstanding. This consistency is genuinely advanced.' },
  { n:13, cat:'margin', name:'Right Margin', sys:'_13_margin_right', val:'5', unit:'mm ragged', ideal:'8–12 mm', band:'dev', score:66, viz:'margin', vmode:'right',
    mean:'The right edge is a little ragged and runs close to the page edge, with some words crowding to fit.',
    tip:'Glance ahead: if a word will not fit comfortably, start it on the next line instead.' },

  // --- E: Pressure & stroke (IMU) ---
  { n:14, cat:'press', name:'Pen Pressure (Mean)', sys:'_14_pen_pressure_mean', val:'2.4', unit:'N force', ideal:'1.8–2.6 N', band:'strong', score:85, viz:'press', vmode:'even',
    mean:'A relaxed, even grip force measured live by the IMU sensor, not too heavy, not too light. The hand is comfortable.',
    tip:'Lovely control. Shake out the hand every paragraph to keep it this relaxed.' },
  { n:15, cat:'press', name:'Pen Pressure Variation', sys:'_15_pen_pressure_variation', val:'31%', unit:'variation', ideal:'below 25%', band:'focus', score:58, viz:'press', vmode:'varied',
    mean:'Pressure rises and dips through the sample, the sensor shows heavier pressing at the start of words, easing off by the end.',
    tip:'Try writing to a slow count of three per word to keep the force smooth and even.' },
  { n:16, cat:'press', name:'Stroke Width (Mean)', sys:'_16_stroke_width_mean', val:'0.42', unit:'mm', ideal:'0.35–0.50 mm', band:'strong', score:82, viz:'stroke', vmode:'even',
    mean:'A clean, consistent line weight that keeps letters crisp and legible.',
    tip:'A medium-tip pen suits this hand well, keep using one.' },
  { n:17, cat:'press', name:'Stroke Width Variation', sys:'_17_stroke_width_variation', val:'19%', unit:'variation', ideal:'below 20%', band:'dev', score:74, viz:'stroke', vmode:'varied',
    mean:'Line weight is mostly even, with a little thickening on downstrokes, a natural, almost calligraphic touch.',
    tip:'This is fine as-is; only smooth it if you want a more uniform, printed look.' },
];

const BAND_LABEL = { strong:'Strong', dev:'Developing', focus:'Focus area' };
const BAND_COLOR = { strong:'var(--grow)', dev:'var(--gold)', focus:'var(--band-focus)' };

/* ---- Mini visualisations (inline SVG) ---------------------------------- */
function viz(f){
  const A='#27406b', G='#9fb0cb';
  switch(f.viz){
    case 'slant':{
      const angs = f.vmode==='mixed' ? [16,14,4,15,13,2,15] : [16,16,16,16,16,16,16];
      let s='';
      angs.forEach((a,i)=>{ const x=14+i*16; s+=`<line x1="${x}" y1="40" x2="${x+ a*0.5}" y2="14" stroke="${A}" stroke-width="3" stroke-linecap="round"/>`; });
      return svg(s);
    }
    case 'base':{
      const d = f.vmode==='rise'
        ? 'M10 36 L130 18'
        : 'M10 24 Q70 40 130 24';
      return svg(`<path d="${d}" fill="none" stroke="${A}" stroke-width="3" stroke-linecap="round"/>
        <line x1="10" y1="40" x2="130" y2="40" stroke="${G}" stroke-width="1.5" stroke-dasharray="3 3"/>`);
    }
    case 'size':{
      const hs = f.vmode==='varied' ? [16,26,14,30,18,24,13] : [20,21,20,22,20,21,20];
      let s=''; hs.forEach((h,i)=>{ const x=14+i*16; s+=`<rect x="${x}" y="${40-h}" width="9" height="${h}" rx="2" fill="${A}"/>`; });
      s+=`<line x1="8" y1="40" x2="132" y2="40" stroke="${G}" stroke-width="1.5"/>`;
      return svg(s);
    }
    case 'zone':{
      const hi = f.vmode; // upper/middle/lower
      const c=(z)=> hi===z ? A : '#cdd6e6';
      return svg(`
        <rect x="20" y="6"  width="100" height="11" rx="2" fill="${c('upper')}"/>
        <rect x="20" y="19" width="100" height="11" rx="2" fill="${c('middle')}"/>
        <rect x="20" y="32" width="100" height="11" rx="2" fill="${c('lower')}"/>`);
    }
    case 'space':{
      const gap = f.vmode==='letter' ? 5 : 13;
      let s=''; for(let i=0;i<6;i++){ const x=14+i*(11+gap); s+=`<rect x="${x}" y="14" width="11" height="20" rx="2" fill="${A}"/>`; }
      return svg(s);
    }
    case 'line':{
      let s=''; [12,24,36].forEach(y=>{ s+=`<line x1="14" y1="${y}" x2="126" y2="${y}" stroke="${A}" stroke-width="3" stroke-linecap="round"/>`; });
      return svg(s);
    }
    case 'margin':{
      const m=f.vmode;
      const band = {
        top:   '<rect x="14" y="6"  width="112" height="8" rx="2" fill="#27406b"/>',
        bottom:'<rect x="14" y="32" width="112" height="8" rx="2" fill="#27406b"/>',
        left:  '<rect x="14" y="6"  width="8"   height="34" rx="2" fill="#27406b"/>',
        right: '<rect x="118" y="6" width="8"   height="34" rx="2" fill="#27406b"/>',
      }[m];
      return svg(`<rect x="14" y="6" width="112" height="34" rx="3" fill="none" stroke="${G}" stroke-width="1.5"/>${band}
        <line x1="22" y1="12" x2="60" y2="12" stroke="#bcc7da" stroke-width="2"/>
        <line x1="22" y1="18" x2="78" y2="18" stroke="#bcc7da" stroke-width="2"/>
        <line x1="22" y1="24" x2="52" y2="24" stroke="#bcc7da" stroke-width="2"/>`);
    }
    case 'press':{
      const rs = f.vmode==='varied' ? [4,7,3,8,5,6,3] : [5,5,6,5,6,5,5];
      let s=''; rs.forEach((r,i)=>{ const x=18+i*16; s+=`<circle cx="${x}" cy="24" r="${r}" fill="${A}" opacity="${0.55+r/16}"/>`; });
      return svg(s);
    }
    case 'stroke':{
      const ws = f.vmode==='varied' ? [2,5,3,6,2,4] : [3,3,4,3,4,3];
      let s=''; ws.forEach((w,i)=>{ const y=12+i*5; s+=`<line x1="16" y1="${y}" x2="124" y2="${y}" stroke="${A}" stroke-width="${w}" stroke-linecap="round"/>`; });
      return svg(s);
    }
  }
  return '';
}
function svg(inner){ return `<svg viewBox="0 0 140 48" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">${inner}</svg>`; }

/* ---- Exercise drills: CSS/SVG stroke patterns with direction arrows ----- */
/* ink = handwriting blue, currentColor = brand accent (arrows/labels)      */
function rail(){ // three guide lines across a 340x86 box
  return `<line x1="14" y1="20" x2="326" y2="20" stroke="#cdd6e6" stroke-width="1.4"/>
    <line x1="14" y1="44" x2="326" y2="44" stroke="#cdd6e6" stroke-width="1.2" stroke-dasharray="4 4"/>
    <line x1="14" y1="68" x2="326" y2="68" stroke="#9fb0cb" stroke-width="1.6"/>`;
}
function arrowDefs(id){
  return `<defs><marker id="${id}" markerWidth="7" markerHeight="7" refX="5.5" refY="3" orient="auto">
    <path d="M0 0 L6 3 L0 6 Z" fill="currentColor"/></marker></defs>`;
}
function exDraw(type){
  const INK='#27406b';
  const wrap = inner => `<svg viewBox="0 0 340 86" preserveAspectRatio="xMidYMid meet">${arrowDefs('ah_'+type)}${rail()}${inner}</svg>`;
  const AR = 'stroke="currentColor" stroke-width="1.6" stroke-dasharray="3 3" fill="none" stroke-linecap="round" marker-end="url(#ah_'+type+')"';
  let s='';
  switch(type){
    case 'slant':{ // forward "/" (left) + backward "\" (right)
      s+='<line x1="170" y1="14" x2="170" y2="74" stroke="#e3d6bd" stroke-width="1.2" stroke-dasharray="3 3"/>';
      for(let i=0;i<6;i++){ const x=26+i*22; s+=`<line x1="${x}" y1="68" x2="${x+13}" y2="20" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`; }
      for(let i=0;i<6;i++){ const x=190+i*22; s+=`<line x1="${x}" y1="20" x2="${x+13}" y2="68" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`; }
      s+=`<path d="M24 80 L40 80" ${AR}/><path d="M198 80 L214 80" ${AR}/>`;
      return wrap(s);
    }
    case 'round':{ // right-leaning ovals (left) + circles (right)
      for(let i=0;i<5;i++){ const cx=40+i*26; s+=`<ellipse cx="${cx}" cy="44" rx="9" ry="17" transform="rotate(-16 ${cx} 44)" fill="none" stroke="${INK}" stroke-width="2.6"/>`; }
      for(let i=0;i<5;i++){ const cx=200+i*26; s+=`<circle cx="${cx}" cy="44" r="13" fill="none" stroke="${INK}" stroke-width="2.6"/>`; }
      s+='<line x1="170" y1="14" x2="170" y2="74" stroke="#e3d6bd" stroke-width="1.2" stroke-dasharray="3 3"/>';
      // anticlockwise motion cue
      s+=`<path d="M44 30 A14 14 0 1 0 30 47" ${AR}/>`;
      s+=`<path d="M204 30 A14 14 0 1 0 190 47" ${AR}/>`;
      return wrap(s);
    }
    case 'rhythm':{ // zigzag (left) + garland loops (right)
      let pts=''; for(let i=0;i<8;i++){ const x=24+i*18; const y=i%2? 64:24; pts+=`${x},${y} `; }
      s+=`<polyline points="${pts.trim()}" fill="none" stroke="${INK}" stroke-width="2.8" stroke-linejoin="round"/>`;
      let g='M186 44 '; for(let i=0;i<5;i++){ g+=`q 13 26 26 0 `; } // garland scallops
      s+=`<path d="${g}" fill="none" stroke="${INK}" stroke-width="2.8" stroke-linecap="round"/>`;
      s+='<line x1="170" y1="14" x2="170" y2="74" stroke="#e3d6bd" stroke-width="1.2" stroke-dasharray="3 3"/>';
      s+=`<path d="M150 80 L168 80" ${AR}/><path d="M300 80 L318 80" ${AR}/>`;
      return wrap(s);
    }
    case 'frame':{ // page-framing drill
      s+=`<rect x="40" y="12" width="260" height="62" rx="3" fill="none" stroke="${INK}" stroke-width="2"/>`;
      s+=`<rect x="58" y="22" width="224" height="42" rx="2" fill="none" stroke="#cdd6e6" stroke-width="1.4" stroke-dasharray="4 3"/>`;
      for(let i=0;i<4;i++){ const y=30+i*9; s+=`<line x1="66" y1="${y}" x2="${200+(i%2?40:0)}" y2="${y}" stroke="#bcc7da" stroke-width="2"/>`; }
      // framing arrows on top + left margins
      s+=`<path d="M58 17 L98 17" ${AR}/><path d="M52 22 L52 50" ${AR}/>`;
      return wrap(s);
    }
    case 'wave':{ // smooth pressure wave, light -> heavy
      s+=`<path d="M22 44 Q52 16 82 44 T142 44 T202 44 T262 44 T322 44" fill="none" stroke="${INK}" stroke-width="2" stroke-linecap="round" opacity=".9"/>`;
      // thickening blobs showing pressure build
      const ws=[2,3,4,5,6,7]; ws.forEach((w,i)=>{ const x=40+i*48; s+=`<line x1="${x}" y1="70" x2="${x+22}" y2="70" stroke="${INK}" stroke-width="${w}" stroke-linecap="round"/>`; });
      s+=`<path d="M30 80 L300 80" ${AR}/>`;
      s+=`<text x="40" y="64" font-size="8" font-family="Hanken Grotesk" fill="currentColor" font-weight="700">light</text>`;
      s+=`<text x="280" y="64" font-size="8" font-family="Hanken Grotesk" fill="currentColor" font-weight="700">heavy</text>`;
      return wrap(s);
    }
  }
  return wrap(s);
}

const EXERCISES = [
  { cat:'slant', tag:'Group A', title:'Slant rails, forward & back', drill:'slant',
    capL:'forward  /  →', capR:'back  \\  →',
    why:'<b>Group A · avg 77.</b> Lines drift upward and a few letters stand upright.',
    steps:['Pull each <b>/</b> up to the right at one steady angle.','Fill a row of <b>\\</b> the other way to feel both leans.'],
    reps:'2 rows each way · 3× a week' },
  { cat:'size', tag:'Group B', title:'Oval & circle roll', drill:'round',
    capL:'right-leaning ovals', capR:'round circles',
    why:'<b>Group B · avg 71</b>, your top focus. Letter sizes vary in height.',
    steps:['Roll ovals leaning right, anti-clockwise, without lifting.','Then even circles, every shape the same height.'],
    reps:'1 minute non-stop · daily' },
  { cat:'space', tag:'Group C', title:'Zigzag rhythm run', drill:'rhythm',
    capL:'zigzag', capR:'garland loops',
    why:'<b>Group C · avg 79.</b> Letters sit a little tight together.',
    steps:['Zigzag to a steady 1-2-3 beat, touching both lines.','Flow into garland “u” loops with equal gaps.'],
    reps:'2 rows · 3× a week' },
  { cat:'margin', tag:'Group D', title:'Frame the page', drill:'frame',
    capL:'draw the frame first', capR:'write inside it',
    why:'<b>Group D · avg 75.</b> The foot and right edge crowd the page.',
    steps:['Pencil a light box one finger inside every edge.','Keep all writing inside it; stop early at the foot.'],
    reps:'Every practice page' },
  { cat:'press', tag:'Group E', title:'Pressure waves', drill:'wave',
    capL:'glide light → heavy', capR:'then even out',
    why:'<b>Group E · avg 75.</b> The IMU pen shows pressure swinging mid-word.',
    steps:['Glide a wave: gentle, then firmer, then gentle again.','Repeat aiming for one even, relaxed pressure.'],
    reps:'1 row · 3× a week' },
];

function renderExercises(){
  const root = document.getElementById('ex-root');
  if(!root) return;
  root.innerHTML = EXERCISES.map(e=>`
    <div class="ex-card">
      <div class="ex-info">
        <div class="ex-head"><span class="ex-tag">Suggested drill</span><span class="ex-grp">${e.tag}</span></div>
        <div class="ex-title">${e.title}</div>
        <p class="ex-why">${e.why}</p>
        <ul class="ex-steps">${e.steps.map((s,i)=>`<li><b>${i+1}</b>${s}</li>`).join('')}</ul>
        <span class="ex-reps"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M20 6 9 17l-5-5"/></svg>${e.reps}</span>
      </div>
      <div class="ex-rail">
        ${exDraw(e.drill)}
        <div class="rl-cap"><span>${e.capL}</span><span>${e.capR}</span></div>
      </div>
    </div>`).join('');
}

/* ---- Render factor cards: one category per page ------------------------ */
function cardHTML(f){
  return `<div class="factor">
    <div class="f-top">
      <span class="f-no">${String(f.n).padStart(2,'0')}</span>
      <span class="f-name">${f.name}<small>Factor ${String(f.n).padStart(2,'0')} · graphology</small></span>
      <span class="f-band ${f.band}">${BAND_LABEL[f.band]}</span>
    </div>
    <div class="f-viz">${viz(f)}</div>
    <div class="f-metric">
      <span class="f-val">${f.val} <small>${f.unit}</small></span>
      <span class="f-ideal">Target&nbsp; <b>${f.ideal}</b></span>
    </div>
    <div class="f-scorebar"><i style="width:${f.score}%;background:${BAND_COLOR[f.band]}"></i></div>
    <p class="f-mean">${f.mean}</p>
    <div class="f-tip"><b>Try this&nbsp;·&nbsp;</b>${f.tip}</div>
  </div>`;
}
function renderFactors(){
  CATS.forEach((cat)=>{
    const root = document.getElementById('cat-'+cat.id);
    if(!root) return;
    const list = FACTORS.filter(f=>f.cat===cat.id);
    root.innerHTML = '<div class="factor-grid">' + list.map(cardHTML).join('') + '</div>';
  });
}

/* ---- Category summary meters on dashboard ------------------------------ */
function catAverages(){
  return CATS.map(c=>{
    const list = FACTORS.filter(f=>f.cat===c.id);
    const avg = Math.round(list.reduce((s,f)=>s+f.score,0)/list.length);
    return {...c, avg};
  });
}
function renderDash(){
  const root = document.getElementById('cat-root');
  if(!root) return;
  root.innerHTML = catAverages().map(c=>{
    const band = c.avg>=80?'strong':c.avg>=66?'dev':'focus';
    return `<div class="cat-row">
      <span class="ci" style="color:var(--accent-deep)">${ICONS[c.icon]}</span>
      <span class="ct">${c.name}<small>${c.sub}</small></span>
      <span class="cmeter">
        <span class="meter"><i style="width:${c.avg}%;background:${BAND_COLOR[band]}"></i></span>
        <span class="cval">${c.avg}</span>
      </span>
    </div>`;
  }).join('');
}

/* ---- Score ring -------------------------------------------------------- */
function renderRing(){
  const el = document.getElementById('ring-svg');
  if(!el) return;
  const score = 76;
  const r=78, c=2*Math.PI*r, off=c*(1-score/100);
  const svgEl = `<svg viewBox="0 0 178 178" style="position:absolute;inset:0;">
    <circle cx="89" cy="89" r="${r}" fill="none" stroke="rgba(255,255,255,.14)" stroke-width="13"/>
    <circle cx="89" cy="89" r="${r}" fill="none" stroke="var(--accent)" stroke-width="13"
      stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}"
      transform="rotate(-90 89 89)"/>
  </svg>`;
  el.insertAdjacentHTML('afterbegin', svgEl);
}

/* ---- Control bar ------------------------------------------------------- */
const BRANDS = {
  terracotta:{ accent:'#D4633A', deep:'#B14A28', soft:'#F6E2D6' },
  indigo:    { accent:'#4F5BD5', deep:'#3A45B0', soft:'#E1E3F7' },
  plum:      { accent:'#9B4D8E', deep:'#7E3B73', soft:'#F0E0EE' },
  forest:    { accent:'#2F8F5B', deep:'#206B42', soft:'#DCEFE2' },
};
function setBrand(key){
  const b=BRANDS[key]; if(!b) return;
  const r=document.documentElement.style;
  r.setProperty('--accent', b.accent);
  r.setProperty('--accent-deep', b.deep);
  r.setProperty('--accent-soft', b.soft);
  document.querySelectorAll('.swatches button').forEach(x=>x.classList.toggle('on', x.dataset.brand===key));
  localStorage.setItem('vahini_brand', key);
}
function setAud(key){
  document.body.dataset.aud = key;
  document.querySelectorAll('.seg.aud button').forEach(x=>x.classList.toggle('on', x.dataset.aud===key));
  localStorage.setItem('vahini_aud', key);
}

function init(){
  renderFactors(); renderDash(); renderRing(); renderExercises();
  // chapter band icons (in CATS order)
  document.querySelectorAll('.cat-band .cb-ico').forEach((el,i)=>{ if(CATS[i]) el.innerHTML = ICONS[CATS[i].icon]; });
  // restore prefs
  setBrand(localStorage.getItem('vahini_brand') || 'terracotta');
  setAud(localStorage.getItem('vahini_aud') || 'kids');
  // wire bar
  document.querySelectorAll('.seg.aud button').forEach(b=> b.onclick=()=>setAud(b.dataset.aud));
  document.querySelectorAll('.swatches button').forEach(b=> b.onclick=()=>setBrand(b.dataset.brand));
  const pb=document.getElementById('print-btn'); if(pb) pb.onclick=()=>window.print();
}
document.addEventListener('DOMContentLoaded', init);
