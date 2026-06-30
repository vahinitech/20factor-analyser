/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
// @ds-adherence-ignore -- animation scene file; brand tokens via video-helpers
/* Vahini — 20 Factors explainer · Scenes 4–6
   S4 three factors measured live · S5 diagnosis → one drill · S6 payoff */

function bandColor(v){ return v<4 ? V.hot : v<7 ? V.amberWarm : V.green; }

function FactorHeader({ num, name, fam, t, appear=0 }){
  const f = FAM[fam];
  const op = tw(t,0,1,appear,appear+0.5,EZ.easeOutCubic);
  const tx = tw(t,-30,0,appear,appear+0.6,EZ.easeOutBack);
  return (
    <div style={{ position:'absolute', left:460, top:175, opacity:op, transform:`translateX(${tx}px)`,
      display:'flex', alignItems:'center', gap:22 }}>
      <span style={{ fontFamily:V.serif, fontSize:78, fontWeight:600, color:f.color, lineHeight:1,
        fontVariantNumeric:'tabular-nums' }}>{String(num).padStart(2,'0')}</span>
      <div>
        <div style={{ fontFamily:V.sans, fontSize:18, fontWeight:700, letterSpacing:'.18em',
          textTransform:'uppercase', color:f.color }}>{f.name}</div>
        <div style={{ fontFamily:V.serif, fontSize:46, fontWeight:600, color:'#fff', marginTop:2 }}>{name}</div>
      </div>
    </div>
  );
}

function ScorePill({ value, t, appear }){
  const op = tw(t,0,1,appear,appear+0.5,EZ.easeOutBack);
  const c = bandColor(value);
  return (
    <div style={{ position:'absolute', left:1300, top:158, width:160, opacity:op, textAlign:'center' }}>
      <div style={{ fontFamily:V.sans, fontSize:16, fontWeight:700, letterSpacing:'.16em',
        textTransform:'uppercase', color:V.hint, marginBottom:6 }}>Score</div>
      <div style={{ fontFamily:V.serif, fontSize:88, fontWeight:600, color:c, lineHeight:1,
        fontVariantNumeric:'tabular-nums' }}>{value.toFixed(1)}<span style={{ fontSize:34, color:V.hint }}>/10</span></div>
    </div>
  );
}

function Readout({ label, value, unit, t, appear }){
  const op = tw(t,0,1,appear,appear+0.5,EZ.easeOutCubic);
  return (
    <div style={{ position:'absolute', left:460, top:712, opacity:op }}>
      <span style={{ fontFamily:V.sans, fontSize:30, color:V.ivory, fontWeight:500 }}>{label}&nbsp;&nbsp;</span>
      <span style={{ fontFamily:V.sans, fontSize:30, color:V.accentLite, fontWeight:700,
        fontVariantNumeric:'tabular-nums' }}>{value}{unit}</span>
    </div>
  );
}

const PX=440, PY=320, PW=1040, PH=330;

/* ---- 4a · Baseline Alignment ---- */
function DemoBaseline({ dur }){
  const t = useLocal();
  const settle = tw(t,0,1,3.4,5.0,EZ.easeInOutCubic);
  const drift = 24*(1-settle);
  const baseY = PY+232;
  const gLine = tw(t,0,1,2.0,2.8,EZ.easeOutCubic);
  const score = tw(t,3.6,8.9,3.6,5.2,EZ.easeOutCubic);
  const metric = (0.46 - 0.40*settle);
  const ticks=[PX+150,PX+330,PX+520,PX+710,PX+900];
  return (
    <FadeWrap dur={dur}>
      <FactorHeader num={7} name="Baseline Alignment" fam="spatial" t={t} appear={0.2}/>
      <ScorePill value={score} t={t} appear={3.4}/>
      <Paper x={PX} y={PY} w={PW} h={PH} radius={18}>
        <HandLetters text="morning light" x={70} y={70} size={150} color={V.ink}
          jitter={drift} sizeVar={0} rot={2*(1-settle)} seed={5} letterSpace={3}/>
      </Paper>
      {/* the invisible line, revealed */}
      <MeasureLine x={PX+50} y={baseY} w={PW-100} color={V.accent} grow={gLine} label="the line"/>
      {/* drift ticks */}
      {gLine>0.7 && ticks.map((tx,i)=>{
        const dir = rng(i,5)>0?1:-1; const h=drift*1.1;
        return <div key={i} style={{ position:'absolute', left:tx, top: dir<0?baseY-h:baseY, width:3, height:h,
          background:V.hot, borderRadius:2, opacity:0.85 }}/>;
      })}
      <Readout label="Drift off the line —" value={metric.toFixed(2)} unit=" x-h" t={t} appear={2.9}/>
      <Caption text={settle>0.9 ? "Settled. Letters now sit on one line — the page reads calm." 
        : "We draw the invisible line your words sit on, then measure every wobble above and below it."}
        x={960} y={812} size={28} color={V.hint} align="center" width={1300} opacity={tw(t,0,1,2.9,3.5)}/>
    </FadeWrap>
  );
}

/* ---- 4b · Size Consistency ---- */
function DemoSize({ dur }){
  const t = useLocal();
  const settle = tw(t,0,1,3.2,5.0,EZ.easeInOutCubic);
  const gBrk = tw(t,0,1,2.0,2.9,EZ.easeOutCubic);
  const score = tw(t,3.4,8.3,3.4,5.2,EZ.easeOutCubic);
  const metric = (0.34 - 0.24*settle);
  const baseY = PY+250;
  const brackets=[
    {x:PX+110, h0:120}, {x:PX+300, h0:190}, {x:PX+500, h0:95},
    {x:PX+690, h0:170}, {x:PX+880, h0:135},
  ];
  const target=150;
  return (
    <FadeWrap dur={dur}>
      <FactorHeader num={5} name="Size Consistency" fam="structure" t={t} appear={0.2}/>
      <ScorePill value={score} t={t} appear={3.4}/>
      <Paper x={PX} y={PY} w={PW} h={PH} radius={18}>
        <HandLetters text="handwriting" x={70} y={66} size={150} color={V.ink}
          jitter={0} sizeVar={0.26*(1-settle)} rot={0} seed={7} letterSpace={4}/>
      </Paper>
      {gBrk>0.05 && brackets.map((b,i)=>{
        const h=(b.h0+(target-b.h0)*settle)*gBrk;
        return <Bracket key={i} x={b.x} top={baseY-h} h={h} color={V.green} grow={1}/>;
      })}
      {/* the even band guides, appear as it settles */}
      {settle>0.4 && [baseY-target, baseY].map((yy,i)=>(
        <div key={i} style={{ position:'absolute', left:PX+50, top:yy, width:PW-100, height:2,
          borderTop:`2px dashed ${V.accent}`, opacity:(settle-0.4)/0.6 }}/>
      ))}
      <Readout label="Height variation —" value={metric.toFixed(2)} unit=" CV" t={t} appear={2.9}/>
      <Caption text={settle>0.9 ? "Every letter now lands in one even band — the single biggest driver of neat writing."
        : "We measure the height of every letter. Wildly uneven sizes are what make a page look restless."}
        x={960} y={812} size={28} color={V.hint} align="center" width={1320} opacity={tw(t,0,1,2.9,3.5)}/>
    </FadeWrap>
  );
}

/* ---- 4c · Word Spacing ---- */
function DemoSpacing({ dur }){
  const t = useLocal();
  const settle = tw(t,0,1,3.2,5.0,EZ.easeInOutCubic);
  const score = tw(t,3.4,7.8,3.4,5.2,EZ.easeOutCubic);
  const metric = (0.41 - 0.31*settle);
  const sz=140, top=80;
  // word x positions: uneven → even
  const oneX = PX+70;
  const twoX = PX + tw(t,300,360,0,1) * 1; // ~constant
  const twoXa = PX + (300 + (360-300)*settle);
  const threeXa = PX + (730 + (610-730)*settle);
  const oneEnd=oneX+196, twoEnd=PX+(300+(360-300)*settle)+208;
  const gMark = tw(t,0,1,2.0,2.8,EZ.easeOutCubic);
  return (
    <FadeWrap dur={dur}>
      <FactorHeader num={8} name="Word Spacing" fam="spatial" t={t} appear={0.2}/>
      <ScorePill value={score} t={t} appear={3.4}/>
      <Paper x={PX} y={PY} w={PW} h={PH} radius={18}>
        <HandLetters text="one" x={70} y={top} size={sz} color={V.ink} seed={2} letterSpace={3}/>
        <HandLetters text="two" x={(300+(360-300)*settle)} y={top} size={sz} color={V.ink} seed={4} letterSpace={3}/>
        <HandLetters text="three" x={(730+(610-730)*settle)} y={top} size={sz} color={V.ink} seed={6} letterSpace={3}/>
      </Paper>
      {/* gap highlight rects */}
      {gMark>0.05 && (()=>{
        const g1L=PX+250, g1R=PX+(300+(360-300)*settle); // gap after "one"
        const g2L=PX+(300+(360-300)*settle)+205, g2R=PX+(730+(610-730)*settle); // gap after "two"
        const even = settle>0.85;
        const col = even? V.accent : V.hot;
        const box=(L,R,key)=>(<div key={key} style={{ position:'absolute', left:L, top:PY+96, width:Math.max(0,R-L),
          height:150, background: even?'rgba(0,173,181,0.12)':'rgba(192,8,11,0.10)',
          borderLeft:`3px solid ${col}`, borderRight:`3px solid ${col}`, opacity:gMark }}/>);
        return [box(g1L,g1R,'g1'), box(g2L,g2R,'g2')];
      })()}
      <Readout label="Gap evenness —" value={metric.toFixed(2)} unit=" CV" t={t} appear={2.9}/>
      <Caption text={settle>0.9 ? "Even gaps — about one letter wide — the fastest single win for readability."
        : "Some words touch, others gape. We measure the gap between every pair of words."}
        x={960} y={812} size={28} color={V.hint} align="center" width={1300} opacity={tw(t,0,1,2.9,3.5)}/>
    </FadeWrap>
  );
}

/* ============ SCENE 5 — diagnosis → one drill ============ */
function SceneDrill({ dur }){
  const t = useLocal();
  const cardA = tw(t,0,1,0.6,1.3,EZ.easeOutBack);
  const arrow = tw(t,0,1,2.0,2.6,EZ.easeOutCubic);
  const cardB = tw(t,0,1,2.6,3.3,EZ.easeOutBack);
  const head  = tw(t,0,1,4.2,5.0,EZ.easeOutCubic);
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="Diagnosis → action" x={960} y={150} color={V.accentLite} align="center"/>
      <Title text="A score you can act on." x={960} y={188} size={70} align="center"/>
      {/* card A — the weak factor */}
      <div style={{ position:'absolute', left:300, top:380, width:560, opacity:cardA,
        transform:`scale(${0.92+0.08*cardA})`, transformOrigin:'center',
        background:V.surface, borderRadius:20, padding:'34px 38px', boxShadow:'0 30px 70px rgba(0,0,0,.4)' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline' }}>
          <span style={{ fontFamily:V.sans, fontSize:16, fontWeight:700, letterSpacing:'.16em',
            textTransform:'uppercase', color:V.hot }}>Focus · Structure</span>
          <span style={{ fontFamily:V.serif, fontSize:64, fontWeight:600, color:V.hot }}>3.0<span style={{fontSize:26,color:V.hint}}>/10</span></span>
        </div>
        <div style={{ fontFamily:V.serif, fontSize:42, fontWeight:600, color:V.ink, margin:'6px 0 14px' }}>Loop Closure</div>
        <div style={{ fontFamily:V.sans, fontSize:25, color:V.muted, lineHeight:1.5 }}>
          Only a third of your round letters close. An open <i>a</i> starts to read as a <i>u</i>.</div>
      </div>
      {/* arrow */}
      <div style={{ position:'absolute', left:880, top:520, width:160, height:8, opacity:arrow }}>
        <div style={{ width:`${arrow*100}%`, height:6, background:V.accent, borderRadius:3 }}/>
        <div style={{ position:'absolute', right:0, top:-9, width:0, height:0,
          borderTop:'12px solid transparent', borderBottom:'12px solid transparent',
          borderLeft:`18px solid ${V.accent}`, opacity:arrow>0.8?1:0 }}/>
      </div>
      {/* card B — the one drill */}
      <div style={{ position:'absolute', left:1060, top:380, width:560, opacity:cardB,
        transform:`scale(${0.92+0.08*cardB})`, transformOrigin:'center',
        background:V.accentSoft, borderRadius:20, padding:'34px 38px', boxShadow:'0 30px 70px rgba(0,0,0,.4)' }}>
        <span style={{ fontFamily:V.sans, fontSize:16, fontWeight:700, letterSpacing:'.16em',
          textTransform:'uppercase', color:V.accentInk }}>Your one drill</span>
        <div style={{ fontFamily:V.serif, fontSize:34, fontWeight:600, color:V.ink, margin:'10px 0 18px', lineHeight:1.25 }}>
          Rows of <i>oooo</i> and <i>aaaa</i> — close every circle.</div>
        <div style={{ fontFamily:V.hand, fontSize:84, color:V.accentDeep, lineHeight:1 }}>oooo aaaa</div>
      </div>
      <Caption text="You can’t fix “messy.” You can fix “close your loops.”" x={960} y={840}
        size={44} color="#fff" align="center" width={1300} opacity={head} weight={600}/>
    </FadeWrap>
  );
}

/* ============ SCENE 6 — payoff ============ */
function ScenePayoff({ dur }){
  const t = useLocal();
  const score = tw(t,4.2,8.6,0.6,2.6,EZ.easeOutCubic);
  const settle = tw(t,0,1,0.4,2.2,EZ.easeInOutCubic);
  const logo = tw(t,0,1,3.0,3.8,EZ.easeOutBack);
  const tag  = tw(t,0,1,3.6,4.4,EZ.easeOutCubic);
  return (
    <FadeWrap dur={dur}>
      <Paper x={360} y={210} w={1200} h={300} radius={18}>
        <HandLetters text="the quick brown fox" x={80} y={70} size={112} color={V.ink}
          jitter={15*(1-settle)} sizeVar={0.16*(1-settle)} rot={6*(1-settle)} seed={3} letterSpace={2}/>
      </Paper>
      <div style={{ position:'absolute', left:0, right:0, top:560, textAlign:'center' }}>
        <span style={{ fontFamily:V.sans, fontSize:24, fontWeight:700, letterSpacing:'.16em',
          textTransform:'uppercase', color:V.hint }}>Overall</span>
        <div style={{ fontFamily:V.serif, fontSize:150, fontWeight:600, color:bandColor(score), lineHeight:1,
          fontVariantNumeric:'tabular-nums', marginTop:6 }}>{score.toFixed(1)}<span style={{fontSize:60,color:V.hint}}>/10</span></div>
      </div>
      <div style={{ position:'absolute', left:0, right:0, top:830, textAlign:'center', opacity:logo }}>
        <div style={{ display:'inline-flex', alignItems:'center', gap:18 }}>
          <img src="site/assets/vahini-logo.png" alt="" style={{ width:56, height:56, borderRadius:'50%' }}/>
          <span style={{ fontFamily:V.serif, fontSize:70, fontWeight:600, color:'#fff', letterSpacing:'.01em' }}>Vahini</span>
        </div>
      </div>
      <Caption text="Handwriting, made measurable." x={960} y={930} size={34} color={V.accentLite}
        align="center" opacity={tag} weight={500}/>
    </FadeWrap>
  );
}

Object.assign(window, { bandColor, DemoBaseline, DemoSize, DemoSpacing, SceneDrill, ScenePayoff });
