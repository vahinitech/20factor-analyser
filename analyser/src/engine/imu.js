/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Battu — IMU sensor simulation & live capture.
   NOTE: no training dataset yet — this STREAMS a physically-plausible
   simulation of the 16-axis pen so the UX, signal processing (Kalman),
   and dynamics-factor formulas (§4C F13–F16) can be demonstrated live.
   16 axes = 9-axis IMU (accel+gyro+mag, 9) + 6-axis IMU (accel+gyro, 6) + tip force (1).
   ========================================================================= */
(function (global) {
'use strict';
/* Small stats helpers used by the live-capture summary. These used to live in
   the browser CV engine (engine.js); scoring moved server-side, so the handful
   the pen simulation needs are inlined here to keep this module self-contained. */
const E = (function(){
  const mean = a => a.length ? a.reduce((s,x)=>s+x,0)/a.length : 0;
  const std  = a => { if(a.length<2) return 0; const m=mean(a); return Math.sqrt(mean(a.map(x=>(x-m)*(x-m)))); };
  const cv   = a => { const m=mean(a); return m ? std(a)/Math.abs(m) : Infinity; };
  const scoreFromError = (error, tolGood, tolBad) => {
    if (error <= tolGood) return 10;
    if (error >= tolBad)  return 0;
    return 10 * (tolBad - error) / (tolBad - tolGood);
  };
  const scoreFromConsistency = (values, cvGood, cvBad) =>
    (values.length<2 || mean(values)===0) ? 5 : scoreFromError(cv(values), cvGood, cvBad);
  return { mean, std, cv, scoreFromError, scoreFromConsistency };
})();

/* ---- 16-axis sensor map (for the schematic + breakdown) --------------- */
const SENSOR_GROUPS = [
  { key:'front', label:'9-axis IMU', sub:'accel · gyro · mag · nib end', axes:['Aₓ','A_y','A_z','Gₓ','G_y','G_z','Mₓ','M_y','M_z'], color:'#D4633A' },
  { key:'rear',  label:'6-axis IMU', sub:'accel · gyro · grip end', axes:['Aₓ','A_y','A_z','Gₓ','G_y','G_z'], color:'#2F8F7F' },
  { key:'force', label:'Force analog', sub:'tip pressure', axes:['Tip'], color:'#4F5BD5' },
];
const TOTAL_AXES = SENSOR_GROUPS.reduce((s,g)=>s+g.axes.length,0); // 16

/* ---- 1-D Kalman filter (constant-position model) ---------------------- */
function Kalman(q, r){ // q=process noise, r=measurement noise
  let x=null, p=1;
  return function(z){
    if (x===null){ x=z; return x; }
    p += q;                    // predict
    const k = p/(p+r);         // gain
    x += k*(z-x);              // update
    p *= (1-k);
    return x;
  };
}

/* ---- ring buffer ------------------------------------------------------- */
function Ring(n){ const b=new Float32Array(n); let i=0,full=false;
  return { push(v){ b[i]=v; i=(i+1)%n; if(i===0) full=true; },
    toArray(){ const out=[]; const N=full?n:i; for(let k=0;k<N;k++){ out.push(b[(i+k+ (full?0:0))% n]); } 
      // ordered oldest->newest
      const ord=[]; const start=full?i:0; const len=full?n:i; for(let k=0;k<len;k++) ord.push(b[(start+k)%n]); return ord; },
    last(){ return b[(i-1+n)%n]; } };
}

/* =========================================================================
   Session controller
   ========================================================================= */
function createSession(){
  const FS = 208;                 // sample rate (Hz) — spec
  const SUB = 7;                  // samples generated per tick
  let t = 0;                      // simulated seconds
  let timer = null, running = false;
  let onTick = null;

  // signal state
  const kForce = Kalman(0.02, 6), kTilt = Kalman(0.03, 5), kVel = Kalman(0.04, 7);
  const bufForce = Ring(260), bufForceRaw = Ring(260),
        bufTilt = Ring(260), bufTiltRaw = Ring(260),
        bufVel = Ring(260), bufGyro = Ring(260), bufMag = Ring(260);

  // accumulators for the summary
  const samplesForce=[], samplesTilt=[], samplesVel=[];
  const strokePeakVel=[], strokeMeanForce=[];
  let curStrokeVel=[], curStrokeForce=[];
  let strokes=0, lifts=0, chars=0, nSamp=0;
  let penDown=true, downTime=0;
  // full pen-down velocity & force series (for velocity-minima segmentation)
  const velSeries=[], forceSeries=[];

  // pen trajectory (for the live trail)
  let px=0.08, py=0.5, heading=0; const trail=[];

  // stroke timing model: word = 4 strokes (~0.34s each), then a lift gap
  const STROKE_T = 0.34, LIFT_T = 0.16, STROKES_PER_WORD = 4;
  function phaseInfo(tt){
    const unit = STROKE_T*STROKES_PER_WORD + LIFT_T; // one word cycle
    const inWord = tt % unit;
    const wordIdx = Math.floor(tt / unit);
    if (inWord >= STROKE_T*STROKES_PER_WORD){ return { down:false, wordIdx, strokeIdx:-1, local:0 }; }
    const sIdx = Math.floor(inWord / STROKE_T);
    const local = (inWord - sIdx*STROKE_T)/STROKE_T; // 0..1 within stroke
    return { down:true, wordIdx, strokeIdx: wordIdx*STROKES_PER_WORD+sIdx, local };
  }

  let lastStroke = -1, baselineDrift = 0;
  function genSample(){
    const ph = phaseInfo(t);
    const down = ph.down;
    // ---- force / pressure (analog tip) ----
    let force;
    if (down){
      // bell within stroke + writer-specific base + slow fatigue rise
      const bell = Math.sin(Math.PI*ph.local);
      const base = 2.1 + 0.25*Math.sin(t*0.7) + t*0.004; // gentle drift/fatigue
      force = base*0.55 + bell*1.4 + (Math.random()-0.5)*0.18;
    } else {
      force = Math.max(0, 0.06 + (Math.random()-0.5)*0.05); // lifted
    }
    // ---- tilt / slant from fused IMU orientation ----
    const tilt = -6 + 2.6*Math.sin(t*0.9 + ph.wordIdx) + (down?0:0) + (Math.random()-0.5)*2.2;
    // ---- velocity (accel-decel pulse per stroke) ----
    let vel;
    if (down){ const bell = Math.sin(Math.PI*ph.local); vel = (28 + 8*Math.sin(t*1.3))*bell + (Math.random()-0.5)*3; }
    else vel = Math.max(0,(Math.random()-0.5)*2);
    // ---- gyro magnitude & mag heading ----
    const gyro = (down? 40*Math.abs(Math.cos(Math.PI*ph.local)) : 4) + (Math.random()-0.5)*6;
    const mag = 18*Math.sin(t*0.25) + (Math.random()-0.5)*3; // heading proxy (deg)

    // ---- Kalman-filtered ----
    const fF = kForce(force), fT = kTilt(tilt), fV = kVel(vel);

    // push buffers
    bufForceRaw.push(force); bufForce.push(fF);
    bufTiltRaw.push(tilt);   bufTilt.push(fT);
    bufVel.push(fV); bufGyro.push(gyro); bufMag.push(mag);

    // accumulate
    samplesForce.push(fF); samplesTilt.push(fT); samplesVel.push(fV); nSamp++;

    // stroke / lift bookkeeping
    if (down){
      if (ph.strokeIdx !== lastStroke){ // new stroke begins
        if (curStrokeVel.length){ strokePeakVel.push(Math.max(...curStrokeVel)); strokeMeanForce.push(E.mean(curStrokeForce)); }
        curStrokeVel=[]; curStrokeForce=[]; strokes++; chars++; lastStroke=ph.strokeIdx;
      }
      curStrokeVel.push(fV); curStrokeForce.push(fF);
      velSeries.push(fV); forceSeries.push(fF);   // contiguous pen-down series
      if (!penDown){ penDown=true; }
    } else {
      if (penDown){ penDown=false; lifts++; }
    }

    // trajectory trail (advance pen by velocity along heading with slant)
    if (down){
      heading = (-tilt*0.6)*Math.PI/180;
      const step = vel*0.00016;
      px += step*Math.cos(heading)*1.0 + 0.00018;
      py += step*Math.sin(heading)*0.25 + Math.sin(t*6)*0.0006;
      if (px>0.96){ px=0.08; py += 0.16; } // wrap to next line
      if (py>0.9) py=0.5;
      trail.push({x:px,y:py,f:fF});
      if (trail.length>1400) trail.shift();
    } else {
      trail.push(null); // pen-up marker (break)
    }

    t += 1/FS;
  }

  function frame(){
    if (!running) return;
    for (let i=0;i<SUB;i++) genSample();
    if (onTick) onTick(snapshot());
  }

  function snapshot(){
    return {
      t, nSamp, strokes, lifts, chars, fs:FS,
      force: bufForce.last(), tilt: bufTilt.last(), vel: bufVel.last(), gyro: bufGyro.last(),
      buffers: { force:bufForce, forceRaw:bufForceRaw, tilt:bufTilt, tiltRaw:bufTiltRaw, vel:bufVel, gyro:bufGyro, mag:bufMag },
      trail,
    };
  }

  function start(tickCb){ onTick=tickCb; running=true; t=0; if(timer) clearInterval(timer); timer=setInterval(frame, 33); }
  function stop(){ running=false; if(timer){ clearInterval(timer); timer=null; } }

  /* ---- velocity-based stroke segmentation (Schomaker/NICI motor model) --
     Handwriting is a chain of ballistic strokes separated by velocity minima.
     Detect those minima with the classic 5-point test (calc_vbs): a sample is
     a segmentation point when it is a local minimum across its 2 neighbours
     each side. Each interval between minima is one physical stroke, whose peak
     velocity is its ballistic amplitude — a far more meaningful unit than a
     fixed time-grid. Ref: Schomaker (1993); Schomaker & Teulings (1990). */
  function velocityMinima(v){
    const idx=[]; const n=v.length;
    if (n<5) return idx;
    if (v[0] < v[1]) idx.push(0);
    for (let i=2;i<n-2;i++){
      if ((v[i] <= v[i-2] && v[i] <= v[i-1] && v[i] < v[i+1] && v[i] < v[i+2]) ||
          (v[i] <  v[i-2] && v[i] <  v[i-1] && v[i] <= v[i+1] && v[i] <= v[i+2])){
        idx.push(i);
      }
    }
    return idx;
  }
  function segmentStrokes(){
    const v=velSeries, f=forceSeries;
    const minima = velocityMinima(v);
    const peaks=[], means=[];
    if (minima.length>=2){
      for (let k=0;k<minima.length-1;k++){
        const a=minima[k], b=minima[k+1];
        if (b-a < 2) continue;
        let pk=0, sum=0; for (let i=a;i<b;i++){ if (v[i]>pk) pk=v[i]; sum+=f[i]; }
        peaks.push(pk); means.push(sum/(b-a));
      }
    }
    return { peaks, means, nSeg: peaks.length, nMin: minima.length };
  }

  /* ---- summary -> dynamics metrics (per §4C F13–F16) ------------------- */
  function summary(){
    // flush current stroke
    if (curStrokeVel.length){ strokePeakVel.push(Math.max(...curStrokeVel)); strokeMeanForce.push(E.mean(curStrokeForce)); }

    // velocity-minima segmentation (preferred); fall back to the running buckets
    const seg = segmentStrokes();
    const peakVel = seg.peaks.length>=4 ? seg.peaks : strokePeakVel;
    const segForce = seg.means.length>=4 ? seg.means : strokeMeanForce;
    const segStrokes = seg.nSeg>=4 ? seg.nSeg : strokes;
    const segMethod = seg.nSeg>=4 ? 'velocity-minima' : 'time-grid';

    const forceCV = E.cv(segForce.length?segForce:samplesForce);
    const velCV   = E.cv(peakVel.length?peakVel:samplesVel);
    const liftsPerChar = lifts/Math.max(1,chars);
    const meanForce = E.mean(samplesForce), meanTilt = E.mean(samplesTilt), meanVel = E.mean(peakVel);
    const dur = t;
    // downsample buffers for the report charts
    const ds = (buf,n=70)=>{ const a=buf.toArray(); if(a.length<=n) return a; const out=[]; const step=a.length/n; for(let i=0;i<n;i++) out.push(a[Math.floor(i*step)]); return out; };
    return {
      fs:FS, nSamp, dur, strokes:segStrokes, segMethod, nMinima:seg.nMin, lifts, chars,
      forceCV, velCV, liftsPerChar, meanForce, meanTilt, meanVel,
      axes: TOTAL_AXES,
      charts: { force: ds(bufForce), tilt: ds(bufTilt), vel: ds(bufVel) },
      trail: trail.slice(),
      // factor overrides (scores via the guide's helpers)
      dynamics: {
        13: { score: E.scoreFromConsistency(peakVel,0.20,0.60), value:'vel CV '+velCV.toFixed(2),
              evidence:'per-stroke peak-velocity consistency, strokes segmented at velocity minima (motor-model)' },
        14: { score: E.scoreFromConsistency(segForce,0.20,0.55), value:'force CV '+forceCV.toFixed(2),
              evidence:'per-stroke force-channel consistency, Kalman-filtered' },
        15: { score: E.scoreFromError(Math.max(0,liftsPerChar-0.3),0.1,1.5), value:segStrokes+' strokes · '+(chars/Math.max(1,strokes-lifts)).toFixed(1)+' parts/word',
              evidence:'stroke connectivity from velocity-minima segmentation &amp; pen-contact events' },
        16: { score: E.scoreFromError(liftsPerChar,0.3,2.0), value:liftsPerChar.toFixed(2)+' lifts/char',
              evidence:'pen-up events detected directly by the IMU contact sensing' },
      }
    };
  }

  /* ---- render a handwriting canvas from the captured trajectory -------- */
  /* (posted to the server so the geometry/structure/spatial factors can be
     measured from the reconstructed writing) */
  function traceCanvas(passage){
    // Render the passage with tremor & slant consistent with the captured tilt,
    // so the recognition server can measure the product factors from it.
    const W=900,H=520; const c=document.createElement('canvas'); c.width=W;c.height=H;
    const ctx=c.getContext('2d'); ctx.fillStyle='#fbfaf4'; ctx.fillRect(0,0,W,H);
    const meanTilt = E.mean(samplesTilt)||-6;
    const slant = Math.tan(meanTilt*Math.PI/180); // shear
    const lines=(passage||'The quick brown fox\njumps over the lazy dog.\nPack five dozen jugs.').split('\n');
    ctx.fillStyle='#16244a';
    lines.forEach((tx,i)=>{ const baseY=110+i*95; let x=70;
      tx.split(' ').forEach(w=>{ const size=42+Math.sin(i*2+x)*4;
        ctx.font=`${size}px "Comic Sans MS", cursive`;
        ctx.save(); ctx.translate(x, baseY+Math.sin(x/110)*3); ctx.transform(1,0,slant,1,0,0); ctx.fillText(w,0,0); ctx.restore();
        x+=ctx.measureText(w).width+26; });
    });
    return c;
  }

  return { start, stop, summary, snapshot, traceCanvas, SENSOR_GROUPS, TOTAL_AXES, FS };
}

global.VahiniIMU = { createSession, SENSOR_GROUPS, TOTAL_AXES, Kalman };
})(window);
