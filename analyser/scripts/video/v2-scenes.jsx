/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
// @ds-adherence-ignore -- animation scene file; brand tokens via video-helpers
/* Vahini — Video 2 · HOW IT WORKS (~52s)
   write → capture → score 20 factors → one drill → progress over time */

function FadeWrap({ dur, fin=0.5, fout=0.5, children }){
  const t = useLocal();
  const o = Math.min(tw(t,0,1,0,fin,EZ.easeOutCubic), tw(t,1,0,dur-fout,dur,EZ.easeInCubic));
  return <div style={{ position:'absolute', inset:0, opacity:o }}>{children}</div>;
}
function StepBadge({ n, total=4, label, t, appear=0 }){
  const op = tw(t,0,1,appear,appear+0.45,EZ.easeOutCubic);
  const tx = tw(t,-24,0,appear,appear+0.55,EZ.easeOutBack);
  return (
    <div style={{ position:'absolute', left:150, top:130, opacity:op, transform:`translateX(${tx}px)` }}>
      <div style={{ display:'flex', alignItems:'center', gap:14 }}>
        <span style={{ fontFamily:V.serif, fontSize:64, fontWeight:700, color:V.accent, lineHeight:1 }}>{n}</span>
        <span style={{ fontFamily:V.sans, fontSize:17, fontWeight:700, color:V.hint }}>/ {total}</span>
        <span style={{ fontFamily:V.sans, fontSize:24, fontWeight:600, color:'#fff', marginLeft:6 }}>{label}</span>
      </div>
    </div>
  );
}

/* 1 — write */
function W_Write({ dur }){
  const t = useLocal();
  const px=460, py=360, pw=1000, ph=300;
  const prog = tw(t,0,1,1.2,5.0,EZ.easeInOutSine);
  return (
    <FadeWrap dur={dur}>
      <StepBadge n={1} label="Write on paper" t={t} appear={0.2}/>
      <Paper x={px} y={py} w={pw} h={ph} ruled lineTop={150} lineGap={130}><div/></Paper>
      <WriteLine text="writing" x={px+90} y={py+212} size={150} color={V.ink} progress={prog}/>
      <Caption text="Write naturally with the Battu pen — any notebook, any script."
        x={960} y={py+ph+70} size={36} color={V.ivory} align="center" width={1200} opacity={tw(t,0,1,1.4,2.2)}/>
    </FadeWrap>
  );
}

/* 2 — capture motion */
function W_Capture({ dur }){
  const t = useLocal();
  const px=460, py=300, pw=1000, ph=270;
  return (
    <FadeWrap dur={dur}>
      <StepBadge n={2} label="The pen captures the motion" t={t} appear={0.2}/>
      <Paper x={px} y={py} w={pw} h={ph} ruled lineTop={140} lineGap={120}><div/></Paper>
      <WriteLine text="writing" x={px+90} y={py+196} size={140} color={V.ink} progress={1} showPen={false}/>
      <Pen tipX={px+pw-160} tipY={py+196} size={240} angle={-32} lift={8}/>
      <div style={{ position:'absolute', left:px+24, top:py+20, display:'flex', alignItems:'center', gap:9,
        fontFamily:V.sans, fontSize:18, fontWeight:700, letterSpacing:'.06em', color:V.accentDeep }}>
        <span style={{ width:10, height:10, borderRadius:'50%', background:V.hot }}/>16 axes · 208 Hz
      </div>
      <SignalWave x={px} y={py+ph+44} w={310} h={118} color="#4F8BFF" label="Force" phase={t*4} freq={2} amp={0.5} grow={tw(t,0,1,1.6,2.4)}/>
      <SignalWave x={px+345} y={py+ph+44} w={310} h={118} color={V.accentLite} label="Tilt" phase={t*5+1} freq={3} amp={0.62} grow={tw(t,0,1,2.0,2.8)}/>
      <SignalWave x={px+690} y={py+ph+44} w={310} h={118} color="#6FD08C" label="Speed" phase={t*6+2} freq={4} amp={0.55} grow={tw(t,0,1,2.4,3.2)}/>
      <Caption text="Two IMUs, a magnetometer and a force tip stream the invisible motion behind every stroke."
        x={960} y={py+ph+200} size={32} color={V.ivory} align="center" width={1300} opacity={tw(t,0,1,3.4,4.2)}/>
    </FadeWrap>
  );
}

/* 3 — score 20 factors */
const SC_ROWS = [['Size consistency',88],['Word spacing',64],['Baseline',79],['Slant',91],['Loop closure',32]];
function W_Score({ dur }){
  const t = useLocal();
  const px=170, py=350, pw=780, ph=270;
  const settle = tw(t,0,1,1.0,2.6,EZ.easeInOutCubic);
  const baseY = py+ph-40;
  const cardOp = tw(t,0,1,2.6,3.3,EZ.easeOutBack);
  const bars = tw(t,0,1,3.2,4.6,EZ.easeOutCubic);
  const overall = tw(t,0,81,3.2,4.8,EZ.easeOutCubic);
  return (
    <FadeWrap dur={dur}>
      <StepBadge n={3} label="Vahini scores 20 factors" t={t} appear={0.2}/>
      <Paper x={px} y={py} w={pw} h={ph} radius={16}><div/></Paper>
      <HandLetters text="writing" x={px+56} y={py+150} size={120} color={V.ink}
        jitter={0} sizeVar={0.22*(1-settle)} rot={0} seed={7} letterSpace={4}/>
      <MeasureLine x={px+40} y={baseY} w={pw-80} color={V.accent} grow={tw(t,0,1,1.0,1.8)}/>
      {[px+150,px+330,px+520].map((bx,i)=>(
        <Bracket key={i} x={bx} top={py+70} h={110} color={V.green} grow={tw(t,0,1,1.4,2.2)}/>
      ))}
      {/* scorecard */}
      <div style={{ position:'absolute', left:1040, top:300, width:680, opacity:cardOp, background:V.surface,
        borderRadius:20, padding:'30px 34px', boxShadow:'0 30px 70px rgba(0,0,0,.4)' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline',
          borderBottom:`1px solid ${V.surface2}`, paddingBottom:16, marginBottom:18 }}>
          <span style={{ fontFamily:V.serif, fontSize:24, fontWeight:600, color:V.ink }}>20-Factor scorecard</span>
          <span style={{ fontFamily:V.serif, fontSize:40, fontWeight:700, color:V.accentDeep }}>{Math.round(overall)}<span style={{ fontSize:18, color:V.hint }}>/100</span></span>
        </div>
        {SC_ROWS.map(([lbl,w],i)=>(
          <div key={i} style={{ display:'grid', gridTemplateColumns:'190px 1fr 44px', gap:14, alignItems:'center', marginBottom:14 }}>
            <span style={{ fontFamily:V.sans, fontSize:19, color:V.elephant }}>{lbl}</span>
            <span style={{ height:9, background:V.surface2, borderRadius:6, overflow:'hidden' }}>
              <span style={{ display:'block', height:'100%', borderRadius:6, width:`${w*bars}%`,
                background: w<40?V.hot : w<70?V.amberWarm : V.accent }}/>
            </span>
            <span style={{ fontFamily:V.sans, fontSize:18, fontWeight:700, color:V.ink, textAlign:'right' }}>{Math.round(w*bars)}</span>
          </div>
        ))}
      </div>
      <Caption text="The engine measures the geometry of every letter — honestly reporting only what it can stand behind."
        x={960} y={770} size={30} color={V.hint} align="center" width={1500} opacity={tw(t,0,1,4.8,5.6)}/>
    </FadeWrap>
  );
}

/* 4 — one drill */
function W_Coach({ dur }){
  const t = useLocal();
  const cardA = tw(t,0,1,0.6,1.3,EZ.easeOutBack);
  const arrow = tw(t,0,1,1.8,2.5,EZ.easeOutCubic);
  const cardB = tw(t,0,1,2.5,3.2,EZ.easeOutBack);
  const head = tw(t,0,1,4.0,4.8,EZ.easeOutCubic);
  return (
    <FadeWrap dur={dur}>
      <StepBadge n={4} label="Practise one thing" t={t} appear={0.2}/>
      <div style={{ position:'absolute', left:300, top:380, width:560, opacity:cardA, transform:`scale(${0.92+0.08*cardA})`,
        transformOrigin:'center', background:V.surface, borderRadius:20, padding:'34px 38px', boxShadow:'0 30px 70px rgba(0,0,0,.4)' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline' }}>
          <span style={{ fontFamily:V.sans, fontSize:16, fontWeight:700, letterSpacing:'.16em', textTransform:'uppercase', color:V.hot }}>Lowest factor</span>
          <span style={{ fontFamily:V.serif, fontSize:60, fontWeight:600, color:V.hot }}>3.2<span style={{fontSize:24,color:V.hint}}>/10</span></span>
        </div>
        <div style={{ fontFamily:V.serif, fontSize:40, fontWeight:600, color:V.ink, margin:'6px 0 14px' }}>Loop Closure</div>
        <div style={{ fontFamily:V.sans, fontSize:24, color:V.muted, lineHeight:1.5 }}>Your round letters are left open — an <i>a</i> starts to read as a <i>u</i>.</div>
      </div>
      <div style={{ position:'absolute', left:880, top:520, width:160, height:8, opacity:arrow }}>
        <div style={{ width:`${arrow*100}%`, height:6, background:V.accent, borderRadius:3 }}/>
        <div style={{ position:'absolute', right:0, top:-9, width:0, height:0, borderTop:'12px solid transparent',
          borderBottom:'12px solid transparent', borderLeft:`18px solid ${V.accent}`, opacity:arrow>0.8?1:0 }}/>
      </div>
      <div style={{ position:'absolute', left:1060, top:380, width:560, opacity:cardB, transform:`scale(${0.92+0.08*cardB})`,
        transformOrigin:'center', background:V.accentSoft, borderRadius:20, padding:'34px 38px', boxShadow:'0 30px 70px rgba(0,0,0,.4)' }}>
        <span style={{ fontFamily:V.sans, fontSize:16, fontWeight:700, letterSpacing:'.16em', textTransform:'uppercase', color:V.accentInk }}>Your one drill</span>
        <div style={{ fontFamily:V.serif, fontSize:32, fontWeight:600, color:V.ink, margin:'10px 0 18px', lineHeight:1.25 }}>Rows of <i>oooo</i> and <i>aaaa</i> — close every circle.</div>
        <div style={{ fontFamily:V.hand, fontSize:82, color:V.accentDeep, lineHeight:1 }}>oooo aaaa</div>
      </div>
      <Caption text="No vague “try harder.” One precise habit that moves the score."
        x={960} y={830} size={40} color="#fff" align="center" width={1300} opacity={head} weight={600}/>
    </FadeWrap>
  );
}

/* 5 — progress over time */
function W_Progress({ dur }){
  const t = useLocal();
  const pts = [[0,4.1],[1,5.0],[2,5.8],[3,7.0],[4,8.6]];
  const W=1100, H=420, X0=420, Y0=300;
  const sx = i => X0 + (i/4)*W;
  const sy = v => Y0 + (1-(v-3)/6)*H;
  const reveal = tw(t,0,1,0.8,4.0,EZ.easeInOutCubic);
  const shown = reveal*4; // up to index
  const score = tw(t,4.1,8.6,0.8,4.0,EZ.easeOutCubic);
  let d='M'+sx(0)+','+sy(pts[0][1]);
  for(let i=1;i<pts.length;i++){ if(i<=shown+0.001){ d+=' L'+sx(i)+','+sy(pts[i][1]); } else { const f=shown-(i-1); if(f>0){ const x=sx(i-1)+(sx(i)-sx(i-1))*f, y=sy(pts[i-1][1])+(sy(pts[i][1])-sy(pts[i-1][1]))*f; d+=' L'+x+','+y; } break; } }
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="The payoff" x={960} y={150} color={V.accentLite} align="center"/>
      <Title text="Re-scan anytime. Watch it improve." x={960} y={186} size={64} align="center"/>
      <svg width={1920} height={760} style={{ position:'absolute', inset:0 }}>
        {[3,4.5,6,7.5,9].map((v,i)=>(<line key={i} x1={X0} y1={sy(v)} x2={X0+W} y2={sy(v)} stroke="rgba(255,255,255,.07)" strokeWidth="1"/>))}
        <path d={d} fill="none" stroke={V.accentLite} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/>
        {pts.map(([i,v],k)=> k<=shown+0.001 && (<circle key={k} cx={sx(i)} cy={sy(v)} r="9" fill={V.accent} stroke="#fff" strokeWidth="3"/>))}
      </svg>
      {pts.map(([i,v],k)=>(
        <div key={k} style={{ position:'absolute', left:sx(i), top:Y0+H+24, transform:'translateX(-50%)',
          fontFamily:V.sans, fontSize:22, color:V.hint, fontWeight:600, opacity: k<=shown+0.001?1:0 }}>Wk {k+1}</div>
      ))}
      <div style={{ position:'absolute', left:X0+W+30, top:sy(8.6)-60, opacity:tw(t,0,1,3.6,4.2) }}>
        <div style={{ fontFamily:V.serif, fontSize:96, fontWeight:700, color:V.green, lineHeight:1 }}>{score.toFixed(1)}</div>
        <div style={{ fontFamily:V.sans, fontSize:22, color:V.hint }}>overall</div>
      </div>
      <div style={{ position:'absolute', left:0, right:0, top:Y0+H+90, textAlign:'center', opacity:tw(t,0,1,4.4,5.2) }}>
        <div style={{ display:'inline-flex', alignItems:'center', gap:16 }}>
          <img src="site/assets/vahini-logo.png" alt="" style={{ width:48, height:48, borderRadius:'50%' }}/>
          <span style={{ fontFamily:V.serif, fontSize:54, fontWeight:600, color:'#fff' }}>Vahini</span>
        </div>
        <div style={{ fontFamily:V.sans, fontSize:28, color:V.accentLite, marginTop:10 }}>Every session, measurably better.</div>
      </div>
    </FadeWrap>
  );
}

Object.assign(window, { FadeWrap, StepBadge, W_Write, W_Capture, W_Score, W_Coach, W_Progress });
