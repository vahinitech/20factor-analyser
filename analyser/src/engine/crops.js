/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini Crops — annotated snippets of the writer's OWN handwriting,
   cropped from the uploaded image, one per factor where the geometry
   identifies a concrete best/worst example. The most persuasive evidence
   a report can show: "this is YOUR letter".
   Returns { [factorN]: { url, caption } } — JPEG data URLs, kept small.
   ========================================================================= */
(function (global) {
'use strict';

const ORANGE='#C85A3C', TEAL='#2F8F7F', GOLD='#C29A45';

function makeCanvas(w,h){ const c=document.createElement('canvas'); c.width=w; c.height=h; return c; }

/* crop a region from src with padding, scaled to fit target height */
function cropRegion(src, x, y, w, h, pad, outH){
  pad = pad==null?6:pad; outH = outH||72;
  const x0=Math.max(0,Math.round(x-pad)), y0=Math.max(0,Math.round(y-pad));
  const cw=Math.min(src.width-x0, Math.round(w+pad*2)), ch=Math.min(src.height-y0, Math.round(h+pad*2));
  if (cw<4||ch<4) return null;
  const scale = outH/ch;
  const c = makeCanvas(Math.max(8,Math.round(cw*scale)), outH);
  const ctx = c.getContext('2d');
  ctx.fillStyle='#fff'; ctx.fillRect(0,0,c.width,c.height);
  ctx.drawImage(src, x0, y0, cw, ch, 0, 0, c.width, c.height);
  return { c, ctx, scale, x0, y0 };
}

/* draw a labelled box on a cropped canvas (coords in source space) */
function box(r, x, y, w, h, color, label){
  const ctx=r.ctx, s=r.scale;
  ctx.strokeStyle=color; ctx.lineWidth=2;
  ctx.strokeRect((x-r.x0)*s, (y-r.y0)*s, w*s, h*s);
  if(label){
    ctx.font='700 10px Hanken Grotesk, sans-serif';
    const tw=ctx.measureText(label).width+8;
    let lx=(x-r.x0)*s, ly=Math.max(11,(y-r.y0)*s-3);
    ctx.fillStyle=color; ctx.fillRect(lx-1, ly-10, tw, 13);
    ctx.fillStyle='#fff'; ctx.fillText(label, lx+3, ly);
  }
}

function toURL(c){ return c.toDataURL('image/jpeg', 0.8); }
function join19(cs){ return sideBySide(cs[0], cs[1]); }

/* compose two crops side by side with a divider */
function sideBySide(a, b){
  const H = Math.max(a.height, b.height);
  const c = makeCanvas(a.width+b.width+14, H);
  const ctx=c.getContext('2d');
  ctx.fillStyle='#fff'; ctx.fillRect(0,0,c.width,H);
  ctx.drawImage(a, 0, Math.round((H-a.height)/2));
  ctx.drawImage(b, a.width+14, Math.round((H-b.height)/2));
  ctx.strokeStyle='#E8DECB'; ctx.lineWidth=1.5;
  ctx.beginPath(); ctx.moveTo(a.width+7,4); ctx.lineTo(a.width+7,H-4); ctx.stroke();
  return c;
}

function build(overlay, metrics){
  const out = {};
  try{
    const src = overlay.canvas;
    const lines = overlay.scoreLines || overlay.lines || [];
    const letters = overlay.letters || [];
    if (!src || letters.length < 6 || !lines.length) return out;

    /* ---- F5 Size Consistency: tallest vs shortest letter ---------------- */
    try{
      const sorted=[...letters].filter(b=>b.h>3).sort((a,b)=>a.h-b.h);
      if (sorted.length>=6){
        const lo=sorted[0], hi=sorted[sorted.length-1];
        if (hi.h > lo.h*1.25){
          const rl=cropRegion(src, lo.x, lo.y, lo.w, lo.h, 8, 64);
          const rh=cropRegion(src, hi.x, hi.y, hi.w, hi.h, 8, 64);
          if (rl&&rh){
            box(rl, lo.x, lo.y, lo.w, lo.h, GOLD, lo.h+'px');
            box(rh, hi.x, hi.y, hi.w, hi.h, ORANGE, hi.h+'px');
            out[5]={ url: toURL(sideBySide(rl.c, rh.c)), caption:'your shortest and tallest letters' };
          }
        }
      }
    }catch(e){}

    /* ---- F7 Baseline: the wobbliest line with its fitted baseline ------- */
    try{
      const rms = metrics.baselineRMSnorm||[];
      if (rms.length && lines.length===rms.length){
        let wi=0; rms.forEach((v,i)=>{ if(v>rms[wi]) wi=i; });
        const L=lines[wi];
        if (L && L.reg && L.boxes && L.boxes.length>=3){
          const x0=Math.min(...L.boxes.map(b=>b.x)), x1=Math.max(...L.boxes.map(b=>b.x+b.w));
          const y0=Math.min(...L.boxes.map(b=>b.y)), y1=Math.max(...L.boxes.map(b=>b.y+b.h));
          const r=cropRegion(src, x0, y0, x1-x0, y1-y0, 8, 64);
          if (r){
            const s=r.scale, ctx=r.ctx;
            ctx.strokeStyle=TEAL; ctx.lineWidth=2; ctx.setLineDash([5,4]);
            ctx.beginPath();
            ctx.moveTo((x0-r.x0)*s, (L.reg.m*x0+L.reg.c-r.y0)*s);
            ctx.lineTo((x1-r.x0)*s, (L.reg.m*x1+L.reg.c-r.y0)*s);
            ctx.stroke(); ctx.setLineDash([]);
            out[7]={ url: toURL(r.c), caption:'your line with its true baseline (dashed)' };
          }
        }
      }
    }catch(e){}

    /* ---- F8 Word Spacing: the widest gap in a line ----------------------- */
    try{
      let best=null;
      lines.forEach(L=>{
        (L.words||[]).forEach((wd,i)=>{
          if(i===0) return;
          const prev=L.words[i-1];
          const ar=Math.max(...prev.map(b=>b.x+b.w)), bl=Math.min(...wd.map(b=>b.x));
          const gap=bl-ar;
          if (gap>0 && (!best || gap>best.gap)){
            const y0=Math.min(...prev.concat(wd).map(b=>b.y)), y1=Math.max(...prev.concat(wd).map(b=>b.y+b.h));
            best={ gap, ar, bl, y0, y1, x0:Math.min(...prev.map(b=>b.x)), x1:Math.max(...wd.map(b=>b.x+b.w)) };
          }
        });
      });
      if (best){
        const r=cropRegion(src, best.x0, best.y0, best.x1-best.x0, best.y1-best.y0, 8, 64);
        if (r){
          const ctx=r.ctx, s=r.scale;
          ctx.fillStyle='rgba(200,90,60,.22)';
          ctx.fillRect((best.ar-r.x0)*s, 2, (best.bl-best.ar)*s, r.c.height-4);
          out[8]={ url: toURL(r.c), caption:'your widest word gap (shaded)' };
        }
      }
    }catch(e){}

    /* ---- F10 Margin: per-line margin strips, joined wide ------------------ */
    try{
      const lx = metrics.leftX||[];
      if (lx.length>=3){
        const xHh = metrics.xHeight||12;
        const med=[...lx].sort((a,b)=>a-b)[Math.floor(lx.length/2)];
        const minL=Math.min(...lx);
        // one short strip per line: margin zone + the opening word(s)
        const strips=[];
        lines.slice(0,4).forEach((L,i)=>{
          if (lx[i]==null || !L.boxes || !L.boxes.length) return;
          const ys0=Math.min(...L.boxes.map(b=>b.y)), ys1=Math.max(...L.boxes.map(b=>b.y+b.h));
          const sx0=Math.max(0, minL-10);
          const sx1=Math.min(src.width, lx[i] + xHh*7);
          const r=cropRegion(src, sx0, ys0, sx1-sx0, ys1-ys0, 5, 42);
          if (!r) return;
          const ctx=r.ctx, s=r.scale;
          ctx.strokeStyle=ORANGE; ctx.lineWidth=1.8; ctx.setLineDash([4,3]);
          ctx.beginPath(); ctx.moveTo((med-r.x0)*s, 2); ctx.lineTo((med-r.x0)*s, r.c.height-2); ctx.stroke(); ctx.setLineDash([]);
          ctx.fillStyle=TEAL; ctx.beginPath(); ctx.arc((lx[i]-r.x0)*s, r.c.height/2, 3.5, 0, 7); ctx.fill();
          strips.push(r.c);
        });
        if (strips.length>=2){
          const gap=10, H=Math.max(...strips.map(c=>c.height));
          const W=strips.reduce((a,c)=>a+c.width,0)+gap*(strips.length-1);
          const cc=makeCanvas(W,H); const cx2=cc.getContext('2d');
          cx2.fillStyle='#fff'; cx2.fillRect(0,0,W,H);
          let xx=0;
          strips.forEach((c,i)=>{ cx2.drawImage(c, xx, Math.round((H-c.height)/2)); xx+=c.width;
            if(i<strips.length-1){ cx2.strokeStyle='#E8DECB'; cx2.lineWidth=1.5; cx2.beginPath(); cx2.moveTo(xx+gap/2,3); cx2.lineTo(xx+gap/2,H-3); cx2.stroke(); }
            xx+=gap; });
          out[10]={ url: toURL(cc), caption:'each line\u2019s start, side by side \u2014 dot = where it begins, dashed = an even margin' };
        }
      }
    }catch(e){}

    /* ---- F2 Stroke order: the finished marks (order lives in time) -------- */
    try{
      let big=null; lines.forEach(L=>(L.words||[]).forEach(w=>{ if(!big||w.length>big.length) big=w; }));
      if (big && big.length>=2){
        const x0=Math.min(...big.map(b=>b.x)), x1=Math.max(...big.map(b=>b.x+b.w));
        const y0=Math.min(...big.map(b=>b.y)), y1=Math.max(...big.map(b=>b.y+b.h));
        const r=cropRegion(src,x0,y0,x1-x0,y1-y0,9,58);
        if (r){
          // number the letters in left-to-right order — the only order a photo can see
          const ctx=r.ctx, s=r.scale;
          ctx.font='700 9px Hanken Grotesk, sans-serif';
          big.slice(0,8).forEach((b,i)=>{
            const cx=(b.cx-r.x0)*s;
            ctx.fillStyle='#2F8F7F'; ctx.beginPath(); ctx.arc(cx, 8, 6.5, 0, 7); ctx.fill();
            ctx.fillStyle='#fff'; ctx.textAlign='center'; ctx.fillText(String(i+1), cx, 11);
          });
          out[2]={ url:toURL(r.c), caption:'your finished letters in page order — the stroke order *within* each letter happens in time, which the Battu records' };
        }
      }
    }catch(e){}

    /* ---- F6 Ascender/Descender: a line with baseline + body-height guides -- */
    try{
      const xHh=metrics.xHeight||12;
      const L=[...lines].sort((a,b)=>b.boxes.length-a.boxes.length)[0];
      if (L && L.reg && L.boxes.length>=3){
        const x0=Math.min(...L.boxes.map(b=>b.x)), x1=Math.max(...L.boxes.map(b=>b.x+b.w));
        const y0=Math.min(...L.boxes.map(b=>b.y)), y1=Math.max(...L.boxes.map(b=>b.y+b.h));
        const r=cropRegion(src,x0,y0,x1-x0,y1-y0,10,66);
        if (r){
          const s=r.scale, ctx=r.ctx;
          const ln=(yAt,color,dash)=>{ ctx.strokeStyle=color; ctx.lineWidth=1.6; ctx.setLineDash(dash||[]); ctx.beginPath(); ctx.moveTo((x0-r.x0)*s,(yAt(x0)-r.y0)*s); ctx.lineTo((x1-r.x0)*s,(yAt(x1)-r.y0)*s); ctx.stroke(); ctx.setLineDash([]); };
          ln(x=>L.reg.m*x+L.reg.c, TEAL);                 // baseline
          ln(x=>L.reg.m*x+L.reg.c - xHh, GOLD, [5,4]);    // body height
          out[6]={ url:toURL(r.c), caption:'your line with baseline (teal) and letter-body height (dashed) — talls reach above, tails below' };
        }
      }
    }catch(e){}

    /* ---- F12 Vertical alignment: a word against upright guides ------------ */
    try{
      let big=null; lines.forEach(L=>(L.words||[]).forEach(w=>{ if(!big||w.length>big.length) big=w; }));
      if (big && big.length>=3){
        const x0=Math.min(...big.map(b=>b.x)), x1=Math.max(...big.map(b=>b.x+b.w));
        const y0=Math.min(...big.map(b=>b.y)), y1=Math.max(...big.map(b=>b.y+b.h));
        const r=cropRegion(src,x0,y0,x1-x0,y1-y0,9,62);
        if (r){
          const s=r.scale, ctx=r.ctx;
          ctx.strokeStyle=TEAL; ctx.lineWidth=1.4; ctx.setLineDash([4,4]);
          big.slice(0,5).forEach(b=>{ const cx=(b.cx-r.x0)*s; ctx.beginPath(); ctx.moveTo(cx,3); ctx.lineTo(cx,r.c.height-3); ctx.stroke(); });
          ctx.setLineDash([]);
          out[12]={ url:toURL(r.c), caption:'your strokes against true-upright guides (dashed)' };
        }
      }
    }catch(e){}

    /* ---- F17 Slant: your average lean drawn through your own word --------- */
    try{
      const sw=metrics.slantWord||[];
      let big=null; lines.forEach(L=>(L.words||[]).forEach(w=>{ if(!big||w.length>big.length) big=w; }));
      if (big && big.length>=2){
        const meanLean = sw.length? sw.reduce((a,x)=>a+x,0)/sw.length : 0;
        const x0=Math.min(...big.map(b=>b.x)), x1=Math.max(...big.map(b=>b.x+b.w));
        const y0=Math.min(...big.map(b=>b.y)), y1=Math.max(...big.map(b=>b.y+b.h));
        const r=cropRegion(src,x0,y0,x1-x0,y1-y0,10,62);
        if (r){
          const s=r.scale, ctx=r.ctx, H=r.c.height;
          const t=Math.tan(meanLean*Math.PI/180);
          ctx.strokeStyle=ORANGE; ctx.lineWidth=2;
          [0.28,0.72].forEach(fr=>{ const cx=((x0+(x1-x0)*fr)-r.x0)*s; ctx.beginPath(); ctx.moveTo(cx+t*H/2, 3); ctx.lineTo(cx-t*H/2, H-3); ctx.stroke(); });
          out[17]={ url:toURL(r.c), caption:'your average lean ('+(meanLean>=0?'+':'')+meanLean.toFixed(0)+'°) drawn through your own word' };
        }
      }
    }catch(e){}

    /* ---- F18 Legibility: a full line exactly as a reader sees it ---------- */
    try{
      const L=lines[0];
      if (L && L.boxes.length>=3){
        const x0=Math.min(...L.boxes.map(b=>b.x)), x1=Math.max(...L.boxes.map(b=>b.x+b.w));
        const y0=Math.min(...L.boxes.map(b=>b.y)), y1=Math.max(...L.boxes.map(b=>b.y+b.h));
        const r=cropRegion(src,x0,y0,x1-x0,y1-y0,8,56);
        if (r) out[18]={ url:toURL(r.c), caption:'your first line, exactly as a reader meets it' };
      }
    }catch(e){}

    /* ---- F19 Character distinction: two near-identical letter shapes ------ */
    try{
      const cands=letters.filter(b=>b.h<=1.7*(metrics.xHeight||12) && b.h>5 && b.w>4);
      let pair=null, bestSim=Infinity;
      for(let i=0;i<cands.length && i<60;i++) for(let j=i+1;j<cands.length && j<60;j++){
        const a=cands[i], b=cands[j];
        if (Math.abs(a.cx-b.cx)<a.w*1.5 && Math.abs(a.cy-b.cy)<a.h) continue; // skip adjacent (same word neighbours ok to skip)
        const sim=Math.abs(a.h-b.h)/Math.max(a.h,b.h) + Math.abs(a.w/a.h - b.w/b.h);
        if (sim<bestSim){ bestSim=sim; pair=[a,b]; }
      }
      if (pair && bestSim<0.18){
        const cs=pair.map(b=>{ const r=cropRegion(src,b.x,b.y,b.w,b.h,7,58); return r&&r.c; }).filter(Boolean);
        if (cs.length===2) out[19]={ url:toURL(join19(cs)), caption:'two of your letters with near-identical outlines — are they the same letter? keep look-alikes distinct' };
      }
    }catch(e){}

    /* ---- F20 Overall neatness: the whole sample at a reader's glance ------ */
    try{
      const x0=Math.min(...letters.map(b=>b.x)), x1=Math.max(...letters.map(b=>b.x+b.w));
      const y0=Math.min(...letters.map(b=>b.y)), y1=Math.max(...letters.map(b=>b.y+b.h));
      const r=cropRegion(src,x0,y0,x1-x0,y1-y0,10,88);
      if (r) out[20]={ url:toURL(r.c), caption:'the whole sample at a glance — what all the habits add up to' };
    }catch(e){}

    /* ---- F1 Letter Formation: steadiest vs roughest letter --------------- */
    try{
      const hs=[...letters].map(b=>b.h).sort((a,b)=>a-b);
      const medH2=hs[Math.floor(hs.length/2)]||10;
      const asps=[...letters].map(b=>b.w/Math.max(1,b.h)).sort((a,b)=>a-b);
      const medA=asps[Math.floor(asps.length/2)]||1;
      const dev=b=> Math.abs(b.h-medH2)/medH2 + Math.abs(b.w/Math.max(1,b.h)-medA)/Math.max(.2,medA);
      const sorted=[...letters].filter(b=>b.h>4&&b.w>3).sort((a,b)=>dev(a)-dev(b));
      if (sorted.length>=6){
        const good=sorted[0], rough=sorted[sorted.length-1];
        const rg=cropRegion(src,good.x,good.y,good.w,good.h,8,64);
        const rr=cropRegion(src,rough.x,rough.y,rough.w,rough.h,8,64);
        if (rg&&rr){
          box(rg,good.x,good.y,good.w,good.h,TEAL,'steady');
          box(rr,rough.x,rough.y,rough.w,rough.h,ORANGE,'rough');
          out[1]={ url: toURL(sideBySide(rg.c,rr.c)), caption:'your steadiest letterform next to your roughest' };
        }
      }
    }catch(e){}

    /* ---- F3 Loop Closure: a closed bowl vs an open one ------------------- */
    try{
      const ink=overlay.ink, W=overlay.w;
      const hasHole=(c)=>{
        if(c.w<6||c.h<6||c.w*c.h>12000) return false;
        // background pixels inside bbox not reachable from bbox border = hole
        const bw=c.w+2, bh=c.h+2;
        const vis=new Uint8Array(bw*bh); const stk=[];
        const at=(x,y)=> ink[(c.y-1+y)*W + (c.x-1+x)];
        for(let x=0;x<bw;x++){ stk.push(x); stk.push((bh-1)*bw+x); }
        for(let y=0;y<bh;y++){ stk.push(y*bw); stk.push(y*bw+bw-1); }
        while(stk.length){ const p=stk.pop(); if(vis[p]) continue;
          const x=p%bw, y=(p/bw)|0;
          const gx=c.x-1+x, gy=c.y-1+y;
          if(gx>=0&&gy>=0&&gx<overlay.w&&gy<overlay.h&&ink[gy*W+gx]) continue;
          vis[p]=1;
          if(x>0)stk.push(p-1); if(x<bw-1)stk.push(p+1); if(y>0)stk.push(p-bw); if(y<bh-1)stk.push(p+bw);
        }
        for(let y=1;y<bh-1;y++) for(let x=1;x<bw-1;x++){
          const p=y*bw+x; if(vis[p]) continue;
          const gx=c.x-1+x, gy=c.y-1+y;
          if(!ink[gy*W+gx]) return true;
        }
        return false;
      };
      const roundish=letters.filter(b=>b.h<=1.8*(metrics.xHeight||12) && b.w/Math.max(1,b.h)>0.55 && b.w/Math.max(1,b.h)<1.6);
      let closed=null, open=null;
      for(const b of roundish){ if(!closed && hasHole(b)) closed=b; else if(!open && !hasHole(b)) open=b; if(closed&&open) break; }
      if (closed){
        const rc1=cropRegion(src,closed.x,closed.y,closed.w,closed.h,8,64);
        if (rc1){
          box(rc1,closed.x,closed.y,closed.w,closed.h,TEAL,'closed');
          if (open){
            const ro=cropRegion(src,open.x,open.y,open.w,open.h,8,64);
            if (ro){ box(ro,open.x,open.y,open.w,open.h,ORANGE,'open?'); out[3]={ url:toURL(sideBySide(rc1.c,ro.c)), caption:'a fully closed bowl beside one that may be open' }; }
          }
          if (!out[3]) out[3]={ url:toURL(rc1.c), caption:'one of your fully closed letter bowls' };
        }
      }
    }catch(e){}

    /* ---- F4 Line Quality: lightest vs heaviest stroke -------------------- */
    try{
      const sw=metrics.strokeWidths||[];
      if (sw.length===letters.length && sw.length>=6){
        let lo=0, hi=0; sw.forEach((v,i)=>{ if(v<sw[lo])lo=i; if(v>sw[hi])hi=i; });
        const a=letters[lo], b=letters[hi];
        const ra=cropRegion(src,a.x,a.y,a.w,a.h,8,64), rb=cropRegion(src,b.x,b.y,b.w,b.h,8,64);
        if (ra&&rb&&hi!==lo){
          box(ra,a.x,a.y,a.w,a.h,GOLD,'lightest');
          box(rb,b.x,b.y,b.w,b.h,ORANGE,'heaviest');
          out[4]={ url:toURL(sideBySide(ra.c,rb.c)), caption:'your lightest stroke beside your heaviest' };
        }
      }
    }catch(e){}

    /* ---- F11 Line Straightness: show a REAL sample line + a level guide --- */
    try{
      const slopes=metrics.lineSlopesDeg||[];
      if (slopes.length && lines.length===slopes.length){
        // only consider lines with enough letters to fit a trustworthy baseline
        const cand = lines.map((L,i)=>({L, slope:slopes[i]||0, n:(L.boxes?L.boxes.length:0)}))
                          .filter(o=>o.n>=4 && o.L && o.L.reg);
        if (cand.length){
          cand.sort((a,b)=>b.slope-a.slope);
          let pick = cand[0];
          const tilted = pick.slope>0.8;
          if (!tilted){ pick = cand.slice().sort((a,b)=>b.n-a.n)[0]; }  // all level → longest line
          const L=pick.L;
          const x0=Math.min(...L.boxes.map(b=>b.x)), x1=Math.max(...L.boxes.map(b=>b.x+b.w));
          const y0=Math.min(...L.boxes.map(b=>b.y)), y1=Math.max(...L.boxes.map(b=>b.y+b.h));
          const r=cropRegion(src,x0,y0,x1-x0,y1-y0,8,60);
          if (r){
            const s=r.scale, ctx=r.ctx;
            const yref=(L.reg.m*x0+L.reg.c-r.y0)*s;
            if (tilted){
              ctx.strokeStyle=ORANGE; ctx.lineWidth=2;
              ctx.beginPath(); ctx.moveTo((x0-r.x0)*s,yref); ctx.lineTo((x1-r.x0)*s,(L.reg.m*x1+L.reg.c-r.y0)*s); ctx.stroke();
            }
            ctx.strokeStyle=TEAL; ctx.lineWidth=2; ctx.setLineDash([5,4]);
            ctx.beginPath(); ctx.moveTo((x0-r.x0)*s,yref); ctx.lineTo((x1-r.x0)*s,yref); ctx.stroke(); ctx.setLineDash([]);
            out[11]={ url:toURL(r.c), caption: tilted ? 'your most tilted line (solid) vs level (dashed)' : 'your line against a level guide (dashed)' };
          }
        }
      }
    }catch(e){}

    /* ---- F9 Letter Spacing: tightest letter pair ------------------------- */
    try{
      let bestP=null;
      lines.forEach(L=>{
        (L.words||[]).forEach(wd=>{
          for(let i=1;i<wd.length;i++){
            const a=wd[i-1], b=wd[i];
            const gap=b.x-(a.x+a.w);
            if (gap>=0 && (!bestP || gap<bestP.gap)) bestP={ gap, a, b };
          }
        });
      });
      if (bestP){
        const {a,b}=bestP;
        const y0=Math.min(a.y,b.y), y1=Math.max(a.y+a.h,b.y+b.h);
        const r=cropRegion(src, a.x, y0, (b.x+b.w)-a.x, y1-y0, 9, 64);
        if (r){
          box(r, a.x, a.y, a.w, a.h, TEAL);
          box(r, b.x, b.y, b.w, b.h, ORANGE);
          out[9]={ url: toURL(r.c), caption:'your closest two letters' };
        }
      }
    }catch(e){}
  }catch(e){ /* crops are best-effort; never block the report */ }
  return out;
}

global.VahiniCrops = { build };
})(window);
