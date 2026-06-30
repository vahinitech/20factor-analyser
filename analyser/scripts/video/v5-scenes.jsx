/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
// @ds-adherence-ignore -- animation scene file; brand tokens via video-helpers
/* Vahini — "Why messy handwriting matters" (~33s)
   messy line → reveal the hidden problems one by one → all fixable → CTA */

function WMFade({ dur, fin=0.5, fout=0.5, children }){
  const t = useLocal();
  const o = Math.min(tw(t,0,1,0,fin,EZ.easeOutCubic), tw(t,1,0,dur-fout,dur,EZ.easeInCubic));
  return <div style={{ position:'absolute', inset:0, opacity:o }}>{children}</div>;
}

/* ---- A · "so what?" ---- */
function WM_Hook({ dur }){
  const t = useLocal();
  const px=460, py=350, pw=1000, ph=300;
  return (
    <WMFade dur={dur}>
      <Paper x={px} y={py} w={pw} h={ph} ruled lineTop={180} lineGap={130}><div/></Paper>
      <HandLetters text="my writing" x={px+80} y={py+85} size={130} color={V.ink}
        jitter={18} sizeVar={0.26} rot={9} seed={4} letterSpace={3}/>
      <Title text="It looks messy." x={960} y={py-150} size={84} align="center" width={1200}/>
      <Caption text="Most people stop right there — “just untidy.” But messy is never one thing."
        x={960} y={py+ph+70} size={36} color={V.ivory} align="center" width={1300} opacity={tw(t,0,1,1.6,2.6)}/>
    </WMFade>
  );
}

/* ---- B · reveal the hidden problems ---- */
const FINDINGS = [
  { k:'Sizes jump around', c:V.green,    at:1.4 },
  { k:'Letters slide off the line', c:V.accent, at:4.0 },
  { k:'Spacing is all over', c:V.hot,    at:6.6 },
  { k:'Each letter leans its own way', c:V.amberWarm, at:9.2 },
];
function WM_Reveal({ dur }){
  const t = useLocal();
  const px=140, py=330, pw=760, ph=300;
  const TEXTY = py+58;          // top of the handwriting block
  const BASE  = TEXTY+112;      // baseline the letters sit on (size 120)
  // which finding is "active" (drives the on-line overlay)
  const active = FINDINGS.reduce((a,f,i)=> t>=f.at ? i : a, -1);
  const win = (at)=> tw(t,0,1,at,at+0.5,EZ.easeOutCubic) * tw(t,1,0,at+2.2,at+2.6,EZ.easeInCubic); // pulse window
  return (
    <WMFade dur={dur}>
      <Eyebrow text="Look closer" x={px} y={py-86} color={V.accentLite}/>
      <Paper x={px} y={py} w={pw} h={ph} radius={16}><div/></Paper>
      <HandLetters text="my writing" x={px+56} y={TEXTY} size={120} color={V.ink}
        jitter={16} sizeVar={0.26} rot={8} seed={4} letterSpace={3}/>

      {/* overlay 0 — size brackets hugging the letters */}
      {(()=>{const o=win(FINDINGS[0].at); if(o<0.02)return null; const hs=[128,82,150,104,124];
        return [px+120,px+250,px+430,px+560,px+680].map((x,i)=>(
          <div key={i} style={{opacity:o}}><Bracket x={x} top={BASE-hs[i]} h={hs[i]} color={V.green} grow={1} /></div>
        ));})()}
      {/* overlay 1 — baseline drift */}
      {(()=>{const o=win(FINDINGS[1].at); if(o<0.02)return null;
        return (<div style={{opacity:o}}>
          <MeasureLine x={px+40} y={BASE} w={pw-80} color={V.accent} grow={1}/>
          {[px+150,px+320,px+500,px+660].map((x,i)=>{const dir=rng(i,9)>0?1:-1,h=24;
            return <div key={i} style={{position:'absolute',left:x,top:dir<0?BASE-h:BASE,width:3,height:h,background:V.hot,borderRadius:2}}/>;})}
        </div>);})()}
      {/* overlay 2 — spacing gap between the two words */}
      {(()=>{const o=win(FINDINGS[2].at); if(o<0.02)return null;
        return (<div style={{opacity:o, position:'absolute', left:px+250, top:BASE-150, width:66, height:150,
          background:'rgba(192,8,11,.14)', borderLeft:`3px solid ${V.hot}`, borderRight:`3px solid ${V.hot}`}}/>);})()}
      {/* overlay 3 — slant guides */}
      {(()=>{const o=win(FINDINGS[3].at); if(o<0.02)return null;
        return (<div style={{opacity:o}}>{[px+130,px+300,px+500,px+660].map((x,i)=>{const ang=rng(i,3)*22;
          return <div key={i} style={{position:'absolute',left:x,top:BASE-140,width:3,height:140,background:V.amberWarm,
            transform:`rotate(${ang}deg)`,transformOrigin:'bottom'}}/>;})}</div>);})()}

      {/* findings checklist */}
      <div style={{ position:'absolute', left:1010, top:300, width:760 }}>
        <div style={{ fontFamily:V.sans, fontSize:18, fontWeight:700, letterSpacing:'.14em',
          textTransform:'uppercase', color:V.hint, marginBottom:22 }}>What’s really going on</div>
        {FINDINGS.map((f,i)=>{
          const on=tw(t,0,1,f.at,f.at+0.45,EZ.easeOutBack);
          return (
            <div key={i} style={{ display:'flex', alignItems:'center', gap:18, marginBottom:20, opacity:0.18+0.82*on,
              transform:`translateX(${(1-on)*-20}px)` }}>
              <span style={{ width:34, height:34, borderRadius:'50%', flex:'0 0 auto', background: on>0.5?f.c:'transparent',
                border:`2.5px solid ${on>0.5?f.c:'rgba(255,255,255,.25)'}`, display:'grid', placeItems:'center',
                color:'#fff', fontSize:18, fontWeight:800 }}>{on>0.5?'!':''}</span>
              <span style={{ fontFamily:V.serif, fontSize:34, fontWeight:600, color:'#fff' }}>{f.k}</span>
            </div>
          );
        })}
      </div>
      <Caption text="Four separate problems — hiding inside one word everyone just calls “messy.”"
        x={960} y={760} size={30} color={V.hint} align="center" width={1500} opacity={tw(t,0,1,12.0,13.0)}/>
    </WMFade>
  );
}

/* ---- C · all fixable ---- */
function WM_Fix({ dur }){
  const t = useLocal();
  const px=460, py=300, pw=1000, ph=280;
  const settle = tw(t,0,1,0.6,3.0,EZ.easeInOutCubic);
  const score = tw(t,4.1,8.4,1.0,3.4,EZ.easeOutCubic);
  const head = tw(t,0,1,3.4,4.2,EZ.easeOutCubic);
  const logo = tw(t,0,1,4.6,5.4,EZ.easeOutBack);
  return (
    <WMFade dur={dur}>
      <Title text={<span>And every one is <span style={{color:V.accentLite}}>fixable.</span></span>}
        x={960} y={py-130} size={68} align="center" width={1300}/>
      <Paper x={px} y={py} w={pw} h={ph} ruled lineTop={170} lineGap={120}><div/></Paper>
      <HandLetters text="my writing" x={px+80} y={py+72} size={120} color={V.ink}
        jitter={16*(1-settle)} sizeVar={0.26*(1-settle)} rot={8*(1-settle)} seed={4} letterSpace={3}/>
      <div style={{ position:'absolute', left:0, right:0, top:py+ph+50, textAlign:'center' }}>
        <span style={{ fontFamily:V.sans, fontSize:22, fontWeight:700, letterSpacing:'.14em',
          textTransform:'uppercase', color:V.hint }}>Overall</span>
        <div style={{ fontFamily:V.serif, fontSize:104, fontWeight:700, color: score<7?V.amberWarm:V.green, lineHeight:1,
          fontVariantNumeric:'tabular-nums', marginTop:4 }}>{score.toFixed(1)}<span style={{fontSize:42,color:V.hint}}>/10</span></div>
      </div>
      <Caption text="Vahini shows you exactly which ones — and what to practise first."
        x={960} y={py+ph+230} size={32} color={V.ivory} align="center" width={1200} opacity={head}/>
      <div style={{ position:'absolute', left:0, right:0, top:880, textAlign:'center', opacity:logo }}>
        <div style={{ display:'inline-flex', alignItems:'center', gap:16 }}>
          <img src="site/assets/vahini-logo.png" alt="" style={{ width:46, height:46, borderRadius:'50%' }}/>
          <span style={{ fontFamily:V.serif, fontSize:46, fontWeight:600, color:'#fff' }}>Vahini</span>
          <span style={{ fontFamily:V.sans, fontSize:24, color:V.accentLite, marginLeft:8 }}>· See the Pen in Action</span>
        </div>
      </div>
    </WMFade>
  );
}

Object.assign(window, { WMFade, WM_Hook, WM_Reveal, WM_Fix });
