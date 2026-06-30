/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
// @ds-adherence-ignore -- animation scene file; brand tokens via video-helpers
/* Vahini — 20 Factors explainer · Scenes 1–3
   S1 vague verdict · S2 the reframe (measure) · S3 four families */

const SAMPLE = 'the quick brown fox';

function FadeWrap({ dur, fin=0.5, fout=0.5, children }){
  const t = useLocal();
  const o = Math.min(tw(t,0,1,0,fin,EZ.easeOutCubic), tw(t,1,0,dur-fout,dur,EZ.easeInCubic));
  return <div style={{ position:'absolute', inset:0, opacity:o }}>{children}</div>;
}

/* ============ SCENE 1 — the vague verdict ============ */
function SceneVerdict({ dur }){
  const t = useLocal();
  // handwriting draws in 0.3–1.8 (mask reveal via width), messy posture
  const reveal = tw(t,0,1,0.3,2.0,EZ.easeInOutCubic);
  // stamp slams in at 3.0
  const st = clamp((t-3.0)/0.5,0,1);
  const stScale = t<3.0 ? 1.7 : (3.0+0.5> t ? interpolate([0,1],[1.7,1],EZ.easeOutBack)(st) : 1);
  const stOp = tw(t,0,1,3.0,3.18,EZ.easeOutCubic);
  const capOp = tw(t,0,1,4.3,5.1,EZ.easeOutCubic);
  const px=360, py=290, pw=1200, ph=400;
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="Every report card, ever" x={px} y={py-70} color={V.hint}/>
      <Paper x={px} y={py} w={pw} h={ph} ruled lineTop={180} lineGap={130}>
        <div style={{ position:'absolute', left:0, top:0, width:`${reveal*100}%`, height:'100%', overflow:'hidden' }}>
          <HandLetters text={SAMPLE} x={80} y={200} size={112} color={V.ink}
            jitter={15} sizeVar={0.16} rot={6} seed={3} letterSpace={2}/>
        </div>
      </Paper>
      {/* red verdict stamp */}
      <div style={{ position:'absolute', left:px+pw-360, top:py+200, opacity:stOp,
        transform:`rotate(-8deg) scale(${stScale})`, transformOrigin:'center' }}>
        <div style={{ border:`7px solid ${V.hot}`, color:V.hot, borderRadius:14, padding:'8px 36px',
          fontFamily:V.serif, fontSize:84, fontWeight:700, fontStyle:'italic', letterSpacing:'.01em',
          background:'rgba(255,255,255,0.04)', boxShadow:`0 0 0 3px rgba(192,8,11,0.15)` }}>messy</div>
      </div>
      <Caption text="“Messy.” It’s the most common note on a child’s page — and the least useful." 
        x={960} y={py+ph+58} size={34} color={V.ivory} align="center" width={1500} opacity={capOp} weight={500}/>
      <Caption text="You cannot improve what no one will measure." x={960} y={py+ph+128} size={30}
        color={V.accentLite} align="center" width={1100} opacity={tw(t,0,1,5.6,6.3,EZ.easeOutCubic)} weight={600}/>
    </FadeWrap>
  );
}

/* ============ SCENE 2 — the reframe: measure it ============ */
function SceneMeasure({ dur }){
  const t = useLocal();
  const px=360, py=320, pw=1200, ph=400;
  // settle handwriting from messy → neat as overlays appear
  const settle = tw(t,0,1,1.2,3.2,EZ.easeInOutCubic);
  const baseY = py+300;
  // overlays draw sequentially
  const gBase = tw(t,0,1,2.0,2.9,EZ.easeOutCubic);     // baseline
  const gBrk  = tw(t,0,1,3.0,3.8,EZ.easeOutCubic);     // height brackets
  const gGap  = tw(t,0,1,3.9,4.6,EZ.easeOutCubic);     // gap ticks
  const gSlant= tw(t,0,1,4.7,5.4,EZ.easeOutCubic);     // slant
  const titleOp = tw(t,0,1,5.8,6.6,EZ.easeOutBack);
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="The Vahini method" x={960} y={py-120} color={V.accentLite} align="center"/>
      <Paper x={px} y={py} w={pw} h={ph} ruled lineTop={180} lineGap={130}>
        <HandLetters text={SAMPLE} x={80} y={200} size={112} color={V.ink}
          jitter={15*(1-settle)} sizeVar={0.16*(1-settle)} rot={6*(1-settle)} seed={3} letterSpace={2}/>
      </Paper>
      {/* baseline */}
      <MeasureLine x={px+60} y={baseY} w={pw-120} color={V.accent} grow={gBase} label="baseline"/>
      {/* height brackets on two tall letters */}
      <Bracket x={px+290} top={py+196} h={112} color={V.green} grow={gBrk} label="x-height"/>
      <Bracket x={px+150} top={py+170} h={138} color={V.green} grow={gBrk} side="left"/>
      {/* gap ticks between words */}
      {gGap>0.05 && [px+320, px+600, px+900].map((gx,i)=>(
        <div key={i} style={{ position:'absolute', left:gx, top:baseY-118, width:tw(t,0,38,3.9,4.6)*1, height:118,
          background:'rgba(192,8,11,0.10)', borderLeft:`3px solid ${V.hot}`, borderRight:`3px solid ${V.hot}`,
          opacity:gGap }}/>
      ))}
      {/* slant guide */}
      {gSlant>0.05 && <div style={{ position:'absolute', left:px+740, top:py+196, width:3, height:128,
        background:V.amberWarm, transform:'rotate(-12deg)', transformOrigin:'bottom', opacity:gSlant }}/>}
      {gSlant>0.5 && <span style={{ position:'absolute', left:px+760, top:py+168, fontFamily:V.sans, fontSize:16,
        fontWeight:700, color:V.amberWarm, opacity:gSlant }}>slant</span>}

      <Title text={<span><span style={{color:V.accentLite}}>20</span> factors.</span>} x={960} y={py+ph+56}
        size={120} align="center"/>
      <Caption text="We turn one vague word into twenty things you can actually see, score, and fix." 
        x={960} y={py+ph+200} size={36} color={V.ivory} align="center" width={1280} opacity={titleOp}/>
    </FadeWrap>
  );
}

/* ============ SCENE 3 — four families ============ */
const FAM_FACTORS = {
  structure:['Letter formation','Stroke order','Loop closure','Line quality','Size consistency','Ascender / descender'],
  spatial:['Baseline alignment','Word spacing','Letter spacing','Margin discipline','Line straightness','Vertical alignment'],
  dynamics:['Speed consistency','Pressure','Stroke continuity','Pen-lift frequency'],
  style:['Slant consistency','Legibility','Character distinction','Overall neatness'],
};
function FamilyCol({ famKey, x, w, appear, t }){
  const f = FAM[famKey]; const items = FAM_FACTORS[famKey];
  const op = tw(t,0,1,appear,appear+0.5,EZ.easeOutCubic);
  const ty = tw(t,40,0,appear,appear+0.6,EZ.easeOutBack);
  return (
    <div style={{ position:'absolute', left:x, top:300, width:w, opacity:op, transform:`translateY(${ty}px)` }}>
      <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', marginBottom:18 }}>
        <span style={{ fontFamily:V.serif, fontSize:34, fontWeight:600, color:'#fff' }}>{f.name}</span>
        <span style={{ fontFamily:V.sans, fontSize:22, fontWeight:700, color:f.color }}>{f.weight}</span>
      </div>
      <div style={{ height:5, background:f.color, borderRadius:3, marginBottom:22,
        width:`${tw(t,0,100,appear+0.2,appear+0.9)}%` }}/>
      <div style={{ display:'flex', flexDirection:'column', gap:13 }}>
        {items.map((it,i)=>{
          const io = tw(t,0,1,appear+0.4+i*0.08,appear+0.8+i*0.08,EZ.easeOutCubic);
          return (
            <div key={i} style={{ display:'flex', alignItems:'center', gap:12, opacity:io }}>
              <span style={{ width:11, height:11, borderRadius:'50%', background:f.color, flex:'0 0 auto' }}/>
              <span style={{ fontFamily:V.sans, fontSize:24, color:V.ivory, fontWeight:500 }}>{it}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
function SceneFamilies({ dur }){
  const t = useLocal();
  const colW=400, gap=48, total=4*colW+3*gap, x0=(1920-total)/2;
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="How the score is built" x={960} y={120} color={V.accentLite} align="center"/>
      <Title text="Twenty factors, four families." x={960} y={160} size={76} align="center"/>
      <FamilyCol famKey="structure" x={x0+0*(colW+gap)} w={colW} appear={0.8} t={t}/>
      <FamilyCol famKey="spatial"   x={x0+1*(colW+gap)} w={colW} appear={1.5} t={t}/>
      <FamilyCol famKey="dynamics"  x={x0+2*(colW+gap)} w={colW} appear={2.2} t={t}/>
      <FamilyCol famKey="style"     x={x0+3*(colW+gap)} w={colW} appear={2.9} t={t}/>
      <Caption text="Structure and space carry the most weight — Dynamics needs the Battu pen to measure speed, pressure and flow as you write."
        x={960} y={930} size={28} color={V.hint} align="center" width={1500} opacity={tw(t,0,1,4.4,5.2)}/>
    </FadeWrap>
  );
}

Object.assign(window, { SAMPLE, FadeWrap, SceneVerdict, SceneMeasure, SceneFamilies });
