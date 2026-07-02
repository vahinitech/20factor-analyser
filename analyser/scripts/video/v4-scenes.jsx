/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
// @ds-adherence-ignore -- animation scene file; brand tokens via video-helpers
/* Vahini — Video 4 · WHY INDIC SCRIPTS (the data story, ~50s)
   the gap → why it matters → the pen builds it → invitation */

function FadeWrap({ dur, fin=0.5, fout=0.5, children }){
  const t = useLocal();
  const o = Math.min(tw(t,0,1,0,fin,EZ.easeOutCubic), tw(t,1,0,dur-fout,dur,EZ.easeInCubic));
  return <div style={{ position:'absolute', inset:0, opacity:o }}>{children}</div>;
}

/* 1 — the world has English data; India's scripts don't */
function D_Gap({ dur }){
  const t = useLocal();
  const enFill = tw(t,0,1,1.0,2.2,EZ.easeOutCubic);
  const inAppear = tw(t,0,1,2.6,3.4,EZ.easeOutCubic);
  const chips = [
    {name:'Telugu', sample:'తెలుగు', font:'inherit', d:3.0},
    {name:'Hindi', sample:'हिन्दी', font:'inherit', d:3.3},
    {name:'Tamil', sample:'தமிழ்', font:'inherit', d:3.6},
    {name:'Kannada', sample:'ಕನ್ನಡ', font:'inherit', d:3.9},
  ];
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="The honest gap" x={960} y={130} color={V.accentLite} align="center"/>
      <Title text="Machines learned to read English. Not how India writes." x={960} y={172}
        size={56} align="center" width={1500}/>
      {/* English bar — full */}
      <div style={{ position:'absolute', left:360, top:360, width:1200 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:10 }}>
          <span style={{ fontFamily:V.sans, fontSize:26, fontWeight:600, color:'#fff' }}>English handwriting data</span>
          <span style={{ fontFamily:V.sans, fontSize:22, fontWeight:700, color:V.accentLite }}>decades of it</span>
        </div>
        <div style={{ height:34, background:'rgba(255,255,255,.08)', borderRadius:10, overflow:'hidden' }}>
          <div style={{ height:'100%', width:`${enFill*100}%`, background:V.accent, borderRadius:10 }}/>
        </div>
      </div>
      {/* Indic scripts — near empty */}
      <div style={{ position:'absolute', left:360, top:470, width:1200, opacity:inAppear }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:10 }}>
          <span style={{ fontFamily:V.sans, fontSize:26, fontWeight:600, color:'#fff' }}>Indic-script handwriting-motion data</span>
          <span style={{ fontFamily:V.sans, fontSize:22, fontWeight:700, color:V.hot }}>almost none</span>
        </div>
        <div style={{ height:34, background:'rgba(255,255,255,.08)', borderRadius:10, overflow:'hidden' }}>
          <div style={{ height:'100%', width:`${1.5}%`, background:V.hot, borderRadius:10 }}/>
        </div>
      </div>
      {/* script chips */}
      {chips.map((c,i)=>(
        <ScriptChip key={i} x={360+i*308} y={600} w={284} name={c.name} sample={c.sample}
          on={tw(t,0,1,c.d,c.d+0.5)} fill={0}/>
      ))}
      <Caption text="There is no large dataset of how Telugu, Hindi or Tamil are actually written by hand."
        x={960} y={830} size={30} color={V.hint} align="center" width={1400} opacity={tw(t,0,1,4.4,5.2)}/>
    </FadeWrap>
  );
}

/* 2 — why it matters */
function D_Why({ dur }){
  const t = useLocal();
  const items = [
    {t:'Every child in India', d:'learns to write in a script no model was trained to understand.', appear:0.6},
    {t:'Dysgraphia, fine-motor delays', d:'show up in handwriting first — but only if something can read it.', appear:1.6},
    {t:'A measuring tool', d:'is only as fair as the data behind it. English-only isn’t fair to Bharat.', appear:2.6},
  ];
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="Why it matters" x={960} y={150} color={V.accentLite} align="center"/>
      <Title text="A gap with real consequences." x={960} y={188} size={64} align="center"/>
      <div style={{ position:'absolute', left:360, top:360, width:1200, display:'flex', flexDirection:'column', gap:26 }}>
        {items.map((it,i)=>{
          const op = tw(t,0,1,it.appear,it.appear+0.6,EZ.easeOutCubic);
          const tx = tw(t,-30,0,it.appear,it.appear+0.7,EZ.easeOutBack);
          return (
            <div key={i} style={{ opacity:op, transform:`translateX(${tx}px)`, display:'flex', gap:22, alignItems:'flex-start',
              background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,.10)', borderRadius:18, padding:'26px 30px' }}>
              <span style={{ width:14, height:14, borderRadius:'50%', background:V.accent, marginTop:10, flex:'0 0 auto' }}/>
              <div>
                <div style={{ fontFamily:V.serif, fontSize:34, fontWeight:600, color:'#fff' }}>{it.t}</div>
                <div style={{ fontFamily:V.sans, fontSize:26, color:V.ivory, marginTop:6, lineHeight:1.45 }}>{it.d}</div>
              </div>
            </div>
          );
        })}
      </div>
    </FadeWrap>
  );
}

/* 3 — the pen builds the dataset */
function D_Build({ dur }){
  const t = useLocal();
  const prog = tw(t,0,1,1.0,4.2,EZ.easeInOutSine);
  const count = tw(t,0,128450,1.0,4.6,EZ.easeOutCubic);
  const chips = [
    {name:'Telugu', sample:'తెలుగు', d:2.6},
    {name:'Hindi', sample:'हिन्दी', d:2.9},
    {name:'Tamil', sample:'தமிழ்', d:3.2},
    {name:'English', sample:'Aa', d:3.5},
  ];
  return (
    <FadeWrap dur={dur}>
      <Eyebrow text="The turn" x={960} y={130} color={V.accentLite} align="center"/>
      <Title text="Every stroke written builds the first one." x={960} y={172} size={58} align="center" width={1400}/>
      {/* pen writing Telugu */}
      <Paper x={460} y={310} w={1000} h={250} radius={18}><div/></Paper>
      <WriteLine text="తెలుగు" x={540} y={490} size={150} color={V.ink} progress={prog} font="inherit" weight={500}/>
      {/* live counter */}
      <Counter x={960} y={610} value={count} label="strokes captured & labelled, and counting" color={V.accentLite} size={96}/>
      {/* filling chips */}
      {chips.map((c,i)=>(
        <ScriptChip key={i} x={360+i*308} y={760} w={284} name={c.name} sample={c.sample}
          on={1} fill={tw(t,0,1,c.d,c.d+0.4)}/>
      ))}
      <Caption text="The Battu pen isn’t just a measuring tool — it’s the instrument building India’s first handwriting-motion dataset."
        x={960} y={980} size={26} color={V.hint} align="center" width={1500} opacity={tw(t,0,1,4.0,4.8)}/>
    </FadeWrap>
  );
}

/* 4 — invitation */
function D_Invite({ dur }){
  const t = useLocal();
  const l1 = tw(t,0,1,0.4,1.3,EZ.easeOutCubic);
  const l2 = tw(t,0,1,1.4,2.2,EZ.easeOutCubic);
  const logo = tw(t,0,1,2.6,3.4,EZ.easeOutBack);
  return (
    <FadeWrap dur={dur}>
      <div style={{ position:'absolute', left:0, right:0, top:300, textAlign:'center', opacity:l1 }}>
        <div style={{ fontFamily:V.serif, fontSize:84, fontWeight:600, color:'#fff', lineHeight:1.12, letterSpacing:'-.02em' }}>
          Every writer makes the<br/>next reading <span style={{ color:V.accentLite }}>smarter.</span></div>
      </div>
      <div style={{ position:'absolute', left:0, right:0, top:560, textAlign:'center', opacity:l2 }}>
        <div style={{ fontFamily:V.sans, fontSize:34, color:V.ivory, fontWeight:500, lineHeight:1.5 }}>
          Schools, clinics & researchers — help build handwriting AI<br/>that finally understands how India writes.</div>
      </div>
      <div style={{ position:'absolute', left:0, right:0, top:790, textAlign:'center', opacity:logo }}>
        <div style={{ display:'inline-flex', alignItems:'center', gap:18 }}>
          <img src="site/assets/vahini-logo.png" alt="" style={{ width:56, height:56, borderRadius:'50%' }}/>
          <span style={{ fontFamily:V.serif, fontSize:64, fontWeight:600, color:'#fff' }}>Vahini</span>
        </div>
        <div style={{ fontFamily:V.sans, fontSize:26, color:V.accentLite, marginTop:12 }}>Built in India, for how India writes.</div>
      </div>
    </FadeWrap>
  );
}

Object.assign(window, { FadeWrap, D_Gap, D_Why, D_Build, D_Invite });
