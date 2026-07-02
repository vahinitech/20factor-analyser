/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
// @ds-adherence-ignore -- animation scene file; uses brand tokens from V below
/* Vahini — 20 Factors explainer · shared helpers & primitives
   Brand: space-teal theme (theme.css). Fonts: Spectral, Hanken Grotesk, Caveat. */

const V = {
  ink:'#222831', ink2:'#1A1E24', elephant:'#393E46', muted:'#565D66', hint:'#828A93',
  ivory:'#EEEEEE', ivory2:'#F5F5F4', surface:'#FFFFFF', surface2:'#E3E5E7',
  accent:'#00ADB5', accentDeep:'#048A91', accentLite:'#3FD0D6', accentSoft:'#DCF3F4', accentInk:'#075E63',
  hot:'#C0080B', hotDeep:'#A80016', hotSoft:'#F8E5E1',
  green:'#0F6E56', greenBg:'#DCF1E8', amber:'#8A5410', amberWarm:'#B57211', amberBg:'#F6E9D4',
  serif:'"Spectral", Georgia, serif',
  sans:'"Hanken Grotesk", system-ui, sans-serif',
  hand:'"Caveat", cursive',
};
// family palette (all grounded in space-teal tokens)
const FAM = {
  structure:{ name:'Structure',  weight:'30%', color:V.accent,  ink:V.accentInk,  bg:V.accentSoft },
  spatial:  { name:'Spatial',    weight:'30%', color:V.green,   ink:'#0A4D3C',    bg:V.greenBg },
  dynamics: { name:'Dynamics',   weight:'20%', color:V.amberWarm, ink:V.amber,    bg:V.amberBg },
  style:    { name:'Style & Readability', weight:'20%', color:V.accentDeep, ink:V.accentInk, bg:V.accentSoft },
};

const EZ = Easing;
const useLocal = () => useSprite().localTime;
// eased tween on a local clock
function tw(t, from, to, start, end, ease=EZ.easeInOutCubic){
  if(t<=start) return from; if(t>=end) return to;
  return from + (to-from)*ease((t-start)/(end-start));
}
// deterministic pseudo-random in [-1,1]
function rng(i, seed=1){ const x=Math.sin((i+1)*12.9898*seed)*43758.5453; return (x-Math.floor(x))*2-1; }

/* ---------- Paper surface ---------- */
function Paper({ x, y, w, h, ruled=false, lineGap=120, lineTop=140, radius=22, tilt=0, children, shadow=true }){
  return (
    <div style={{ position:'absolute', left:x, top:y, width:w, height:h, background:V.surface,
      borderRadius:radius, transform:`rotate(${tilt}deg)`, transformOrigin:'center',
      boxShadow: shadow?'0 40px 90px rgba(0,0,0,0.45), 0 8px 24px rgba(0,0,0,0.25)':'none', overflow:'hidden' }}>
      {ruled && Array.from({length: Math.floor((h-lineTop)/lineGap)+1}).map((_,i)=>(
        <div key={i} style={{ position:'absolute', left:48, right:48, top:lineTop+i*lineGap, height:2,
          background:'rgba(34,40,49,0.07)' }}/>
      ))}
      {/* faint left margin rule */}
      {ruled && <div style={{ position:'absolute', left:120, top:24, bottom:24, width:2, background:V.hotSoft }}/>}
      {children}
    </div>
  );
}

/* ---------- Handwriting: per-letter spans with offset / scale / rotation ---------- */
function HandLetters({ text, size=120, color=V.ink, x=0, y=0, baseline,
  jitter=0, sizeVar=0, rot=0, seed=2, letterSpace=2, weight=600, opacity=1 }){
  const chars=[...text];
  return (
    <div style={{ position:'absolute', left:x, top:y, display:'flex', alignItems:'flex-end',
      fontFamily:V.hand, fontSize:size, color, fontWeight:weight, lineHeight:1, opacity }}>
      {chars.map((c,i)=>{
        const dy = c===' ' ? 0 : rng(i,seed)*jitter;
        const sc = c===' ' ? 1 : 1 + rng(i,seed*1.7)*sizeVar;
        const rz = c===' ' ? 0 : rng(i,seed*2.3)*rot;
        return <span key={i} style={{ display:'inline-block', transform:`translateY(${dy}px) scale(${sc}) rotate(${rz}deg)`,
          transformOrigin:'bottom center', marginRight:c===' '?size*0.28:letterSpace, willChange:'transform' }}>{c==='\u0020'?'\u00A0':c}</span>;
      })}
    </div>
  );
}

/* ---------- Measurement overlays ---------- */
function MeasureLine({ x, y, w, color=V.accent, dash=true, grow=1, label, thick=3 }){
  return (
    <div style={{ position:'absolute', left:x, top:y, width:w*grow, height:thick, background: dash?'none':color,
      borderTop: dash?`${thick}px dashed ${color}`:'none', willChange:'width' }}>
      {label && grow>0.9 && <span style={{ position:'absolute', right:0, top:-34, fontFamily:V.sans, fontSize:20,
        fontWeight:700, color, letterSpacing:'.04em' }}>{label}</span>}
    </div>
  );
}
function Tick({ x, y, h, color=V.hot, grow=1 }){
  return <div style={{ position:'absolute', left:x, top:y, width:3, height:Math.abs(h)*grow,
    transform: h<0?'translateY(-100%)':'none', background:color, borderRadius:2 }}/>;
}
// vertical bracket measuring a height span
function Bracket({ x, top, h, color=V.accent, label, grow=1, side='left' }){
  const H=h*grow;
  return (
    <div style={{ position:'absolute', left:x, top, width:14, height:H }}>
      <div style={{ position:'absolute', left: side==='left'?0:'auto', right: side==='left'?'auto':0, top:0, width:12, height:3, background:color }}/>
      <div style={{ position:'absolute', left: side==='left'?0:'auto', right: side==='left'?'auto':0, bottom:0, width:12, height:3, background:color }}/>
      <div style={{ position:'absolute', left: side==='left'?0:11, top:0, width:3, height:'100%', background:color }}/>
      {label && grow>0.85 && <span style={{ position:'absolute', left: side==='left'?-8:20, top:'50%',
        transform: side==='left'?'transl(-100%,-50%)':'translateY(-50%)', fontFamily:V.sans, fontSize:16, fontWeight:700, color, whiteSpace:'nowrap' }}>{label}</span>}
    </div>
  );
}

/* ---------- Typographic UI ---------- */
function Eyebrow({ text, x, y, color=V.accentLite, align='left' }){
  return <div style={{ position:'absolute', left:x, top:y, fontFamily:V.sans, fontSize:22, fontWeight:700,
    letterSpacing:'.22em', textTransform:'uppercase', color, transform: align==='center'?'translateX(-50%)':'none' }}>{text}</div>;
}
function Title({ text, x, y, size=104, color='#fff', align='left', weight:wt=600, width }){
  return <div style={{ position:'absolute', left:x, top:y, fontFamily:V.serif, fontSize:size, fontWeight:wt,
    color, lineHeight:1.04, letterSpacing:'-.02em', textAlign:align, width,
    transform: align==='center'?'translateX(-50%)':'none' }}>{text}</div>;
}
function Caption({ text, x, y, size=34, color=V.ivory, align='left', width, weight:wt=500, opacity=1 }){
  return <div style={{ position:'absolute', left:x, top:y, fontFamily:V.sans, fontSize:size, fontWeight:wt,
    color, lineHeight:1.45, textAlign:align, width, opacity,
    transform: align==='center'?'translateX(-50%)':'none' }}>{text}</div>;
}

/* ---------- Score number (counts up) ---------- */
function ScoreNum({ x, y, value, size=120, color=V.accent, suffix='', align='left' }){
  return <div style={{ position:'absolute', left:x, top:y, fontFamily:V.serif, fontSize:size, fontWeight:600,
    color, letterSpacing:'-.02em', fontVariantNumeric:'tabular-nums',
    transform: align==='center'?'translateX(-50%)':'none' }}>{value.toFixed(1)}<span style={{fontSize:size*0.4, color:V.hint}}>{suffix}</span></div>;
}

/* ---------- Animated ballpoint pen (tip-anchored) ---------- */
function Pen({ tipX, tipY, size=230, angle=-36, lift=0 }){
  const s = size/240, w=80*s, h=240*s;
  return (
    <div style={{ position:'absolute', left:tipX, top:tipY-lift, transformOrigin:'0 0',
      transform:`rotate(${angle}deg) translate(${-40*s}px, ${-236*s}px)`, willChange:'transform',
      filter:'drop-shadow(0 8px 14px rgba(0,0,0,.35))' }}>
      <svg width={w} height={h} viewBox="0 0 80 240">
        <polygon points="33,206 47,206 40,236" fill="#11151b"/>
        <circle cx="40" cy="232" r="3.2" fill={V.accentLite}/>
        <rect x="20" y="186" width="40" height="22" rx="5" fill={V.accent}/>
        <rect x="20" y="190" width="40" height="3" fill="rgba(255,255,255,.5)"/>
        <rect x="18" y="120" width="44" height="70" rx="14" fill="#2E3640"/>
        <circle cx="40" cy="150" r="5.5" fill={V.accentLite}/>
        <rect x="20" y="22" width="40" height="102" rx="16" fill="#222831"/>
        <rect x="26" y="30" width="9" height="86" rx="4" fill="rgba(255,255,255,.10)"/>
        <rect x="44" y="26" width="6" height="58" rx="3" fill="#3FD0D6"/>
        <rect x="22" y="14" width="36" height="14" rx="7" fill="#11151b"/>
      </svg>
    </div>
  );
}

/* ---------- Writing reveal with a moving pen (left→right); y = baseline ---------- */
function WriteLine({ text, x, y, size=120, color=V.ink, progress=1, font=V.hand,
  weight=600, letterSpace=2, showPen=true, penAngle=-34 }){
  const ref = React.useRef(null);
  const [w, setW] = React.useState(0);
  React.useEffect(()=>{ if(ref.current) setW(ref.current.scrollWidth); }, [text, size, letterSpace]);
  const clipW = w*progress;
  const tipX = x + clipW;
  const writing = progress>0.002 && progress<0.998;
  return (
    <React.Fragment>
      <span ref={ref} style={{ position:'absolute', visibility:'hidden', whiteSpace:'nowrap',
        fontFamily:font, fontSize:size, fontWeight:weight, letterSpacing:letterSpace }}>{text}</span>
      <div style={{ position:'absolute', left:x, top:y-size, width:Math.max(0,clipW), height:size*1.5,
        overflow:'hidden' }}>
        <div style={{ position:'absolute', left:0, top:0, whiteSpace:'nowrap', fontFamily:font,
          fontSize:size, fontWeight:weight, color, letterSpacing:letterSpace, lineHeight:1 }}>{text}</div>
      </div>
      {showPen && progress>0.001 && <Pen tipX={tipX} tipY={y} size={size*1.7} angle={penAngle} lift={writing?0:size*0.5}/>}
    </React.Fragment>
  );
}

/* ---------- Live signal wave (oscilloscope line on a dark panel) ---------- */
function SignalWave({ x, y, w, h, color=V.accentLite, label, phase=0, amp=0.62, freq=2.4, grow=1 }){
  const pts=[]; const N=80;
  for(let i=0;i<=N;i++){ const px=(i/N)*w; const env=Math.sin((i/N)*Math.PI);
    const py=h/2 - Math.sin((i/N)*freq*Math.PI*2 + phase)*(h*0.5*amp)*env; pts.push(`${px.toFixed(1)},${py.toFixed(1)}`); }
  const d='M'+pts.join(' L');
  return (
    <div style={{ position:'absolute', left:x, top:y, width:w, height:h, background:V.ink2,
      borderRadius:14, overflow:'hidden', border:`1px solid rgba(255,255,255,.08)` }}>
      {label && <span style={{ position:'absolute', left:14, top:10, fontFamily:V.sans, fontSize:14,
        fontWeight:700, letterSpacing:'.08em', textTransform:'uppercase', color }}>{label}</span>}
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ position:'absolute', inset:0 }}>
        <line x1="0" y1={h/2} x2={w*grow} y2={h/2} stroke="rgba(255,255,255,.10)" strokeWidth="1"/>
        <path d={d} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
          style={{ strokeDasharray:w*2, strokeDashoffset:(w*2)*(1-grow) }}/>
      </svg>
    </div>
  );
}

/* ---------- Phone frame ---------- */
function Phone({ x, y, w=440, h=900, children, scale=1 }){
  return (
    <div style={{ position:'absolute', left:x, top:y, width:w, height:h, transform:`scale(${scale})`,
      transformOrigin:'top center', background:'#0c0f14', borderRadius:54, padding:14,
      boxShadow:'0 40px 90px rgba(0,0,0,.5), inset 0 0 0 2px rgba(255,255,255,.06)' }}>
      <div style={{ position:'absolute', left:'50%', top:24, transform:'translateX(-50%)', width:120, height:8,
        background:'#000', borderRadius:8, zIndex:5 }}/>
      <div style={{ position:'relative', width:'100%', height:'100%', background:V.surface, borderRadius:42,
        overflow:'hidden' }}>{children}</div>
    </div>
  );
}

/* ---------- Script chip (data story) ---------- */
function ScriptChip({ x, y, w=300, name, sample, sampleFont, color=V.accent, on=1, fill=0 }){
  return (
    <div style={{ position:'absolute', left:x, top:y, width:w, opacity:0.35+0.65*on,
      transform:`translateY(${(1-on)*18}px)`, background:'rgba(255,255,255,0.04)',
      border:`1.5px solid ${fill>0.5?color:'rgba(255,255,255,.14)'}`, borderRadius:16, padding:'20px 24px' }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <span style={{ fontFamily:sampleFont||V.sans, fontSize:52, color:'#fff', lineHeight:1 }}>{sample}</span>
        <span style={{ width:13, height:13, borderRadius:'50%', background: fill>0.5?color:'rgba(255,255,255,.18)' }}/>
      </div>
      <div style={{ fontFamily:V.sans, fontSize:20, color:V.hint, marginTop:12, fontWeight:600 }}>{name}</div>
    </div>
  );
}

/* ---------- Big counter ---------- */
function Counter({ x, y, value, label, color=V.accentLite, size=110, align='center' }){
  const v = Math.round(value);
  return (
    <div style={{ position:'absolute', left:x, top:y, textAlign:align,
      transform: align==='center'?'translateX(-50%)':'none' }}>
      <div style={{ fontFamily:V.serif, fontSize:size, fontWeight:700, color, lineHeight:1,
        fontVariantNumeric:'tabular-nums', letterSpacing:'-.02em' }}>{v.toLocaleString()}</div>
      {label && <div style={{ fontFamily:V.sans, fontSize:24, color:V.hint, marginTop:10, fontWeight:600 }}>{label}</div>}
    </div>
  );
}

Object.assign(window, { V, FAM, EZ, useLocal, tw, rng,
  Paper, HandLetters, MeasureLine, Tick, Bracket, Eyebrow, Title, Caption, ScoreNum,
  Pen, WriteLine, SignalWave, Phone, ScriptChip, Counter });
