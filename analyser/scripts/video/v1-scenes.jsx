/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
// @ds-adherence-ignore -- animation scene file; brand tokens via video-helpers
/* Vahini — Video 1 · THE CONCEPT (~23s)
   A pen that records your handwriting on ordinary paper. */

function FadeWrap({ dur, fin=0.5, fout=0.5, children }){
  const t = useLocal();
  const o = Math.min(tw(t,0,1,0,fin,EZ.easeOutCubic), tw(t,1,0,dur-fout,dur,EZ.easeInCubic));
  return <div style={{ position:'absolute', inset:0, opacity:o }}>{children}</div>;
}
const WORD = 'namaste';

/* A — write on ordinary paper */
function C_Write({ dur }){
  const t = useLocal();
  const px=460, py=360, pw=1000, ph=320;
  const prog = tw(t,0,1,0.8,4.6,EZ.easeInOutSine);
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="The whole idea, in one minute" x={960} y={150} color={V.accentLite} align="center"/>
      <Paper x={px} y={py} w={pw} h={ph} ruled lineTop={170} lineGap={130}>
        <div/>
      </Paper>
      <WriteLine text={WORD} x={px+70} y={py+232} size={150} color={V.ink} progress={prog}/>
      <Caption text="Start with ordinary paper. Any notebook, any page — and the Battu pen."
        x={960} y={py+ph+70} size={38} color={V.ivory} align="center" width={1300}
        opacity={tw(t,0,1,1.2,2.0)}/>
    </FadeWrap>
  );
}

/* B — the pen captures motion */
function C_Capture({ dur }){
  const t = useLocal();
  const px=460, py=300, pw=1000, ph=300;
  const wEnt = tw(t,0,1,1.6,2.4,EZ.easeOutCubic);
  return (
    <FadeWrap dur={dur}>
      <Paper x={px} y={py} w={pw} h={ph} ruled lineTop={150} lineGap={130}>
        <div/>
      </Paper>
      <WriteLine text={WORD} x={px+70} y={py+212} size={140} color={V.ink} progress={1} showPen={false}/>
      {/* resting pen with glowing sensors */}
      <Pen tipX={px+pw-150} tipY={py+212} size={250} angle={-32} lift={10}/>
      {/* 208 Hz badge */}
      <div style={{ position:'absolute', left:px+24, top:py+22, display:'flex', alignItems:'center', gap:9,
        fontFamily:V.sans, fontSize:18, fontWeight:700, letterSpacing:'.06em', color:V.accentDeep, opacity:wEnt }}>
        <span style={{ width:10, height:10, borderRadius:'50%', background:V.hot }}/>REC · 208&nbsp;Hz
      </div>
      {/* three live signals */}
      <SignalWave x={px} y={py+ph+40} w={310} h={120} color="#4F8BFF" label="Tip force" phase={t*4} freq={2.0} amp={0.5} grow={tw(t,0,1,2.0,2.8)}/>
      <SignalWave x={px+345} y={py+ph+40} w={310} h={120} color={V.accentLite} label="Tilt" phase={t*5+1} freq={3.0} amp={0.62} grow={tw(t,0,1,2.4,3.2)}/>
      <SignalWave x={px+690} y={py+ph+40} w={310} h={120} color="#6FD08C" label="Speed" phase={t*6+2} freq={4.0} amp={0.55} grow={tw(t,0,1,2.8,3.6)}/>
      <Caption text="The pen feels the motion behind every stroke — 208 times a second."
        x={960} y={py+ph+200} size={36} color={V.ivory} align="center" width={1300}
        opacity={tw(t,0,1,3.6,4.4)}/>
    </FadeWrap>
  );
}

/* C — motion becomes digital */
function C_Digital({ dur }){
  const t = useLocal();
  const arrow = tw(t,0,1,1.4,2.2,EZ.easeOutCubic);
  const phone = tw(t,0,1,1.8,2.6,EZ.easeOutBack);
  const dProg = tw(t,0,1,2.4,4.4,EZ.easeInOutSine);
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="Paper → data, instantly" x={960} y={150} color={V.accentLite} align="center"/>
      {/* left: paper ink */}
      <Paper x={150} y={420} w={720} h={250} radius={18}>
        <div/>
      </Paper>
      <WriteLine text={WORD} x={210} y={585} size={120} color={V.ink} progress={1} showPen={false}/>
      <Caption text="on paper" x={510} y={695} size={24} color={V.hint} align="center"/>
      {/* arrow */}
      <div style={{ position:'absolute', left:905, top:540, width:140, height:8, opacity:arrow }}>
        <div style={{ width:`${arrow*100}%`, height:6, background:V.accent, borderRadius:3 }}/>
        <div style={{ position:'absolute', right:0, top:-9, width:0, height:0, borderTop:'12px solid transparent',
          borderBottom:'12px solid transparent', borderLeft:`18px solid ${V.accent}`, opacity:arrow>0.8?1:0 }}/>
      </div>
      {/* right: phone with digital reconstruction */}
      <div style={{ opacity:phone, transform:`scale(${0.9+0.1*phone})`, transformOrigin:'1240px 230px' }}>
        <Phone x={1090} y={210} w={420} h={620}>
          <div style={{ padding:'30px 26px', height:'100%', display:'flex', flexDirection:'column' }}>
            <div style={{ fontFamily:V.sans, fontSize:15, fontWeight:700, letterSpacing:'.1em',
              textTransform:'uppercase', color:V.accentDeep }}>Vahini · live</div>
            <div style={{ marginTop:34, fontFamily:V.hand, fontSize:96, color:V.accentDeep, lineHeight:1,
              borderBottom:`3px dashed ${V.accent}`, paddingBottom:14, width:`${dProg*100}%`, overflow:'hidden', whiteSpace:'nowrap' }}>{WORD}</div>
            <div style={{ marginTop:26 }}>
              <SignalWave x={0} y={0} w={368} h={92} color={V.accentLite} phase={t*6} freq={3} grow={tw(t,0,1,3.0,4.0)}/>
            </div>
            <div style={{ marginTop:'auto', display:'flex', gap:10 }}>
              {['Size','Spacing','Slant'].map((k,i)=>(
                <div key={i} style={{ flex:1, background:V.accentSoft, borderRadius:12, padding:'14px 0', textAlign:'center',
                  opacity:tw(t,0,1,3.6+i*0.2,4.2+i*0.2) }}>
                  <div style={{ fontFamily:V.serif, fontSize:26, fontWeight:700, color:V.accentInk }}>✓</div>
                  <div style={{ fontFamily:V.sans, fontSize:14, color:V.muted, marginTop:2 }}>{k}</div>
                </div>
              ))}
            </div>
          </div>
        </Phone>
      </div>
      <Caption text="It becomes data the instant you write — ready to measure."
        x={620} y={760} size={32} color={V.ivory} align="center" width={900} opacity={tw(t,0,1,4.4,5.0)}/>
    </FadeWrap>
  );
}

/* D — payoff */
function C_Payoff({ dur }){
  const t = useLocal();
  const l1 = tw(t,0,1,0.4,1.2,EZ.easeOutCubic);
  const logo = tw(t,0,1,2.2,3.0,EZ.easeOutBack);
  return (
    <FadeWrap dur={dur}>
      <div style={{ position:'absolute', left:0, right:0, top:330, textAlign:'center', opacity:l1 }}>
        <div style={{ fontFamily:V.serif, fontSize:96, fontWeight:600, color:'#fff', lineHeight:1.1, letterSpacing:'-.02em' }}>
          No tablet. No special paper.<br/><span style={{ color:V.accentLite }}>Just a pen.</span></div>
      </div>
      <div style={{ position:'absolute', left:0, right:0, top:660, textAlign:'center', opacity:logo }}>
        <div style={{ display:'inline-flex', alignItems:'center', gap:18 }}>
          <img src="site/assets/vahini-logo.png" alt="" style={{ width:60, height:60, borderRadius:'50%' }}/>
          <span style={{ fontFamily:V.serif, fontSize:74, fontWeight:600, color:'#fff' }}>Vahini</span>
        </div>
        <div style={{ fontFamily:V.sans, fontSize:32, color:V.accentLite, marginTop:14, fontWeight:500 }}>
          The pen that reads <i>how</i> you write.</div>
      </div>
    </FadeWrap>
  );
}

Object.assign(window, { FadeWrap, C_Write, C_Capture, C_Digital, C_Payoff });
