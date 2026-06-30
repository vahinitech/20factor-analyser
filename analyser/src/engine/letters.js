/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini Letters — coach-grade letter-level findings.
   Because the writer copies a KNOWN passage, we can align the expected
   letters to the detected ink and check the things a human coach checks:
     • style mixing (print vs joined/cursive within one sample)
     • capital letters appearing mid-word
     • the same letter written in different ways (e.g. three kinds of 'r')
     • punctuation present or missing (full stops, commas, hyphens)
     • word-level audit (letters missing/extra; spelling via OCR server)
   All geometry-based and honestly labelled; OCR server sharpens it further.
   ========================================================================= */
(function (global) {
'use strict';

const XH_CLASS = 'acemnorsuvwxz';           // letters that live in the middle zone
const ASC = 'bdfhklt';
const PUNCT = '.,;:!?-\'"';

function cleanWord(w){ let s=w, trail=[]; while(s && PUNCT.includes(s[s.length-1])){ trail.push(s[s.length-1]); s=s.slice(0,-1); } return { core:s, trail }; }

/* ---- tiny crop helpers (self-contained) -------------------------------- */
function crop(src, x, y, w, h, pad, outH){
  pad=pad==null?7:pad; outH=outH||60;
  const x0=Math.max(0,Math.round(x-pad)), y0=Math.max(0,Math.round(y-pad));
  const cw=Math.min(src.width-x0, Math.round(w+pad*2)), ch=Math.min(src.height-y0, Math.round(h+pad*2));
  if(cw<4||ch<4) return null;
  const s=outH/ch, c=document.createElement('canvas');
  c.width=Math.max(8,Math.round(cw*s)); c.height=outH;
  const ctx=c.getContext('2d');
  ctx.fillStyle='#fff'; ctx.fillRect(0,0,c.width,c.height);
  ctx.drawImage(src,x0,y0,cw,ch,0,0,c.width,c.height);
  return { c, ctx, s, x0, y0 };
}
function mark(r, b, color){ r.ctx.strokeStyle=color; r.ctx.lineWidth=2; r.ctx.strokeRect((b.x-r.x0)*r.s,(b.y-r.y0)*r.s,b.w*r.s,b.h*r.s); }
function join(canvases, gap){
  gap=gap==null?12:gap;
  const H=Math.max(...canvases.map(c=>c.height));
  const W=canvases.reduce((a,c)=>a+c.width,0)+gap*(canvases.length-1);
  const c=document.createElement('canvas'); c.width=W; c.height=H;
  const ctx=c.getContext('2d'); ctx.fillStyle='#fff'; ctx.fillRect(0,0,W,H);
  let x=0; canvases.forEach((cv,i)=>{ ctx.drawImage(cv,x,Math.round((H-cv.height)/2)); x+=cv.width; if(i<canvases.length-1){ ctx.strokeStyle='#E8DECB'; ctx.beginPath(); ctx.moveTo(x+gap/2,4); ctx.lineTo(x+gap/2,H-4); ctx.stroke(); } x+=gap; });
  return c;
}
const url = c => c.toDataURL('image/jpeg', 0.8);

/* ---- MAIN --------------------------------------------------------------- */
function build(overlay, metrics, expectedText, recognizedText, ocrEngine){
  const out = { ok:false };
  try{
    const src = overlay.canvas;
    const lines = overlay.scoreLines || overlay.lines || [];
    const xH = metrics.xHeight || 12;
    if (!src || !lines.length || !expectedText) return out;
    const expLines = expectedText.split(/\n+/).filter(Boolean);

    /* align: expected word k of line i ↔ detected word k of line i */
    const wordPairs = [];          // { exp, comps[], joined, lineIdx }
    const n = Math.min(lines.length, expLines.length);
    for (let i=0;i<n;i++){
      const expWords = expLines[i].trim().split(/\s+/);
      const detWords = lines[i].words || [];
      const m = Math.min(expWords.length, detWords.length);
      for (let j=0;j<m;j++){
        const { core, trail } = cleanWord(expWords[j]);
        if (!core) continue;
        const comps = [...detWords[j]].sort((a,b)=>a.x-b.x);
        const ratio = comps.length / core.length;
        wordPairs.push({ exp:core, trail, comps, lineIdx:i,
          joined: ratio <= 0.62,                       // most letters connected
          mapped: comps.length === core.length });     // 1:1 letter map possible
      }
    }
    if (!wordPairs.length) return out;
    const basis = wordPairs.length;

    /* ---- 1. style mixing (print vs joined) ------------------------------ */
    const joined = wordPairs.filter(p=>p.joined), print = wordPairs.filter(p=>!p.joined);
    const mixRatio = Math.min(joined.length, print.length) / wordPairs.length;
    const style = {
      joinedCount: joined.length, printCount: print.length,
      verdict: mixRatio >= 0.25 ? 'mixed' : (joined.length>print.length ? 'joined' : 'print'),
      mixed: mixRatio >= 0.25,
    };
    if (style.mixed){
      const ex1 = print[0], ex2 = joined[0];
      const mk = p => { const x0=Math.min(...p.comps.map(b=>b.x)), x1=Math.max(...p.comps.map(b=>b.x+b.w)), y0=Math.min(...p.comps.map(b=>b.y)), y1=Math.max(...p.comps.map(b=>b.y+b.h)); const r=crop(src,x0,y0,x1-x0,y1-y0,8,56); return r&&r.c; };
      const a=ex1&&mk(ex1), b=ex2&&mk(ex2);
      if (a&&b) style.cropURL = url(join([a,b]));
      style.exWords = [ex1&&ex1.exp, ex2&&ex2.exp].filter(Boolean);
    }

    /* ---- 2. capitals / oversized letters mid-word ----------------------- */
    const caseHits = [];
    wordPairs.forEach(p=>{
      if (!p.mapped || p.exp.length<3) return;
      for (let k=1;k<p.exp.length;k++){
        const ch = p.exp[k];
        if (!XH_CLASS.includes(ch)) continue;        // only letters that should be small
        const b = p.comps[k];
        if (b.h > 1.55*xH){ caseHits.push({ word:p.exp, ch, k, b, comps:p.comps }); break; }
      }
    });
    let caseMix = { count: caseHits.length, examples: [] };
    caseHits.slice(0,2).forEach(hit=>{
      const x0=Math.min(...hit.comps.map(b=>b.x)), x1=Math.max(...hit.comps.map(b=>b.x+b.w));
      const y0=Math.min(...hit.comps.map(b=>b.y)), y1=Math.max(...hit.comps.map(b=>b.y+b.h));
      const r=crop(src,x0,y0,x1-x0,y1-y0,8,56);
      if (r){ mark(r,hit.b,'#C85A3C'); caseMix.examples.push({ word:hit.word, ch:hit.ch, url:url(r.c) }); }
    });

    /* ---- 2b. sentence-start capitals -------------------------------------- */
    const sentStarts = [];
    let prevTrail = ['.'];                       // first word of passage starts a sentence
    wordPairs.forEach(p=>{
      const startsSentence = prevTrail.some(t=>'.!?'.includes(t));
      prevTrail = p.trail.length ? p.trail : [];
      if (!startsSentence || !/[A-Z]/.test(p.exp[0]) || !p.comps.length) return;
      const first = p.comps[0];
      sentStarts.push({ word:p.exp, ok: first.h >= 1.35*xH, comps:p.comps, b:first });
    });
    const sentMissing = sentStarts.filter(s=>!s.ok);
    const sentCaps = { checked: sentStarts.length, missing: sentMissing.length, example:null };
    if (sentMissing.length){
      const hit = sentMissing[0];
      const x0=Math.min(...hit.comps.map(b=>b.x)), x1=Math.max(...hit.comps.map(b=>b.x+b.w));
      const y0=Math.min(...hit.comps.map(b=>b.y)), y1=Math.max(...hit.comps.map(b=>b.y+b.h));
      const r=crop(src,x0,y0,x1-x0,y1-y0,8,52);
      if (r){ mark(r,hit.b,'#C85A3C'); sentCaps.example={ word:hit.word, url:url(r.c) }; }
    }

    /* ---- 3. same letter, different shapes -------------------------------- */
    const byChar = {};
    wordPairs.forEach(p=>{ if(!p.mapped) return; p.exp.split('').forEach((ch,k)=>{ if(/[a-z]/.test(ch)) (byChar[ch]=byChar[ch]||[]).push(p.comps[k]); }); });
    let formVar = null;
    Object.keys(byChar).forEach(ch=>{
      const arr=byChar[ch]; if (arr.length<3) return;
      const aspects=arr.map(b=>b.w/Math.max(1,b.h));
      const mean=aspects.reduce((a,x)=>a+x,0)/aspects.length;
      const cv=Math.sqrt(aspects.reduce((a,x)=>a+(x-mean)*(x-mean),0)/aspects.length)/Math.max(.01,mean);
      if (!formVar || cv>formVar.cv) formVar={ ch, cv, arr };
    });
    if (formVar && formVar.cv>0.22){
      const sorted=[...formVar.arr].sort((a,b)=>(a.w/a.h)-(b.w/b.h));
      const picks=[sorted[0], sorted[Math.floor(sorted.length/2)], sorted[sorted.length-1]];
      const cs=picks.map(b=>{ const r=crop(src,b.x,b.y,b.w,b.h,7,56); return r&&r.c; }).filter(Boolean);
      if (cs.length>=2) formVar.cropURL=url(join(cs));
      formVar.n=formVar.arr.length;
    } else formVar = formVar ? { ch:formVar.ch, cv:formVar.cv, consistent:true, n:formVar.arr.length } : null;

    /* ---- 4. punctuation audit -------------------------------------------- */
    const expPunct = (expectedText.match(/[.,;:!?-]/g)||[]);
    const expStops = expPunct.filter(c=>c==='.').length;
    const marks = (overlay.smallMarks||[]).length;
    const punct = { expected: expPunct.length, stops: expStops, found: Math.min(marks, expPunct.length), marksSeen: marks };

    /* ---- 5. word audit (letters missing / spelling) ----------------------- */
    const audit = [];
    if (ocrEngine==='server' && recognizedText && recognizedText.trim()){
      const expW = expectedText.toLowerCase().match(/[a-z']+/g)||[];
      const recW = recognizedText.toLowerCase().match(/[a-z']+/g)||[];
      const m=Math.min(expW.length, recW.length);
      for(let i=0;i<m && audit.length<4;i++) if(expW[i]!==recW[i]) audit.push({ expected:expW[i], got:recW[i], kind:'spelling' });
      out.auditMode='ocr';
    } else {
      wordPairs.forEach(p=>{
        if (p.joined || audit.length>=3) return;
        const diff = p.comps.length - p.exp.length;
        if (Math.abs(diff)>=2){
          const x0=Math.min(...p.comps.map(b=>b.x)), x1=Math.max(...p.comps.map(b=>b.x+b.w));
          const y0=Math.min(...p.comps.map(b=>b.y)), y1=Math.max(...p.comps.map(b=>b.y+b.h));
          const r=crop(src,x0,y0,x1-x0,y1-y0,8,52);
          audit.push({ expected:p.exp, diff, url:r?url(r.c):null, kind:'parts' });
        }
      });
      out.auditMode='geometry';
    }

    out.ok = true;
    out.basis = basis;
    out.style = style;
    out.caseMix = caseMix;
    out.sentCaps = sentCaps;
    out.formVar = formVar;
    out.punct = punct;
    out.audit = audit;
  }catch(e){ /* never block the report */ }
  return out;
}

global.VahiniLetters = { build };
})(window);
