/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini OCR + pipeline orchestration.
   Recognition runs on a LOCAL PP-OCRv5 server when available (see
   ppocr-server.py — PaddleOCR v5, runs fully on your own machine), or any
   endpoint set via window.VAHINI_OCR_ENDPOINT. If neither is reachable,
   the in-browser deterministic detector keeps the demo fully offline.
   ========================================================================= */
(function (global) {
'use strict';

/* Candidate endpoints, tried in order:
   1. an explicit window.VAHINI_OCR_ENDPOINT
   2. the local PP-OCRv5 helper server (ppocr-server.py) on this machine */
const CANDIDATES = [
  window.VAHINI_OCR_ENDPOINT || null,
  '/ocr',
  'http://127.0.0.1:8868/ocr',
].filter(Boolean);

const VL_CANDIDATES = CANDIDATES.map(u=>String(u).replace(/\/ocr$/, '/analyze-vl'));
const REPORT_CANDIDATES = CANDIDATES.map(u=>String(u).replace(/\/ocr$/, '/report-python'));

let activeEndpoint = null;   // remembered after the first success
let endpointAttempts = Object.create(null); // first-hit warmup can be slow
let lastServerError = '';

/* Normalise any supported server response to { lines:[{text,box,score}], full_text }.
   Accepts: our native shape, or raw PaddleOCR/PP-OCRv5 result arrays
   (rec_texts + rec_polys/rec_boxes, or [[poly, [text, score]], …]). */
function normalize(j){
  if (!j) return null;
  if (Array.isArray(j.lines)) return j;
  if (Array.isArray(j.hand_lines)){
    const lines = j.hand_lines.map(l=>({
      text: l.text || '',
      box: Array.isArray(l.box) ? l.box : [0,0,0,0],
      score: l.score || 0,
      lang: l.lang || null,
      printed_hint: !!l.printed_hint,
    }));
    return { lines, full_text: lines.map(x=>x.text).filter(Boolean).join('\n'), engine: j.engine || 'pp-ocrv5' };
  }
  // PP-OCRv5 predict() style: { rec_texts:[], rec_polys:[[[x,y]..]], rec_scores:[] }
  if (Array.isArray(j.rec_texts)){
    const polys = j.rec_polys || j.rec_boxes || [];
    const lines = j.rec_texts.map((text,i)=>{
      const p = polys[i] || [];
      const xs = p.map(pt=>pt[0]), ys = p.map(pt=>pt[1]);
      const box = xs.length ? [Math.min(...xs), Math.min(...ys), Math.max(...xs)-Math.min(...xs), Math.max(...ys)-Math.min(...ys)] : [0,0,0,0];
      return { text, box, score:(j.rec_scores||[])[i] || 0, lang:(j.rec_langs||[])[i]||null, printed_hint:(j.printed_hints||[])[i]||false };
    });
    return { lines, full_text: j.rec_texts.join('\n'), engine: j.engine || 'pp-ocrv5' };
  }
  // classic ocr() list style: [ [poly, [text, score]], … ]
  if (Array.isArray(j) && j.length && Array.isArray(j[0])){
    const lines = j.map(item=>{
      const p=item[0]||[], t=item[1]||['',0];
      const xs=p.map(pt=>pt[0]), ys=p.map(pt=>pt[1]);
      return { text:t[0], score:t[1], box:[Math.min(...xs),Math.min(...ys),Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys)] };
    });
    return { lines, full_text: lines.map(l=>l.text).join('\n') };
  }
  return null;
}

async function tryEndpoint(url, blob){
  const fd = new FormData();
  fd.append('image', blob, 'sample.png');
  fd.append('det', 'true'); fd.append('rec', 'true');
  fd.append('lang', window.VAHINI_OCR_LANG || 'auto');
  // NB: do NOT pin a language — let the server run every script it has loaded
  // (English + Telugu by default) and merge, so mixed pages read fully.
  const ctrl = new AbortController();
  const attempt = (endpointAttempts[url] || 0) + 1;
  endpointAttempts[url] = attempt;
  // First call can include model warm-up/download on OCR servers.
  // Keep local dev responsive afterwards with a shorter steady-state timeout.
  const warmup = attempt === 1;
  const timeoutMs = warmup
    ? (url.includes('127.0.0.1') ? 30000 : 45000)
    : (url.includes('127.0.0.1') ? 12000 : 16000);
  const t = setTimeout(()=>ctrl.abort(), timeoutMs);
  try{
    const res = await fetch(url, { method:'POST', body:fd, signal:ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error('HTTP '+res.status);
    return normalize(await res.json());
  } finally { clearTimeout(t); }
}

async function tryVLEndpoint(url, blob){
  const fd = new FormData();
  fd.append('image', blob, 'sample.png');
  fd.append('lang', window.VAHINI_OCR_LANG || 'auto');
  const ctrl = new AbortController();
  const attempt = (endpointAttempts[url] || 0) + 1;
  endpointAttempts[url] = attempt;
  const warmup = attempt === 1;
  const timeoutMs = warmup
    ? (url.includes('127.0.0.1') ? 30000 : 45000)
    : (url.includes('127.0.0.1') ? 12000 : 18000);
  const t = setTimeout(()=>ctrl.abort(), timeoutMs);
  try{
    const res = await fetch(url, { method:'POST', body:fd, signal:ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error('HTTP '+res.status);
    const j = await res.json();
    const n = normalize(j);
    if (!n) return null;
    return { ...j, ...n };
  } finally { clearTimeout(t); }
}

async function serverOCR(blob){
  const order = activeEndpoint ? [activeEndpoint] : CANDIDATES;
  lastServerError = '';
  for (const url of order){
    try{
      const out = await tryEndpoint(url, blob);
      if (out && out.lines && out.lines.length){ activeEndpoint = url; out.endpoint = url; return out; }
      if (out && out.error) lastServerError = out.error;
    }catch(e){ lastServerError = (e && e.message) ? e.message : 'request failed'; }
  }
  if (CANDIDATES.length) console.info('[Vahini] no recognition server reachable — using on-device detector (run ppocr-server.py for PP-OCRv5 recognition)', lastServerError || '');
  return null;
}

function getLastServerError(){ return lastServerError || ''; }

async function serverVLAnalyze(blob){
  const order = VL_CANDIDATES;
  for (const url of order){
    try{
      const out = await tryVLEndpoint(url, blob);
      if (out && out.ok !== false){
        return {
          engine: out.engine || 'pp-ocrv5+opencv-context',
          lines: out.lines || [],
          full_text: out.full_text || '',
          document_context: out.document_context || null,
          layout: out.layout || null,
          regions: Array.isArray(out.regions) ? out.regions : [],
          factor_regions: out.factor_regions || {},
        };
      }
    }catch(_e){ /* try next */ }
  }
  return null;
}

async function serverPythonReport(blob, expectedText){
  const order = REPORT_CANDIDATES;
  for (const url of order){
    try{
      const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
      const fd = new FormData();
      fd.append('image', blob, 'sample.png');
      fd.append('lang', window.VAHINI_OCR_LANG || 'auto');
      fd.append('expected_text', expectedText || '');
      const ctrl = new AbortController();
      // Dense, multi-line pages take longer to OCR on CPU; allow generous time
      // before falling back to geometry-only so recognition isn't dropped.
      const t = setTimeout(()=>ctrl.abort(), 120000);
      const res = await fetch(url, { method:'POST', body:fd, signal:ctrl.signal });
      clearTimeout(t);
      const raw = await res.text();
      if (!res.ok) throw new Error('HTTP '+res.status+' '+raw.slice(0,120));
      let j = null;
      try { j = JSON.parse(raw); } catch(_e){ throw new Error('Non-JSON /report-python response: '+raw.slice(0,120)); }
      if (j && j.ok !== false && j.analysis && Array.isArray(j.analysis.results)){
        const t1 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
        const netMs = Math.max(0, Math.round(t1 - t0));
        const backendMs = Math.max(0, Number((((j||{})._meta||{}).elapsed_ms) || 0));
        j._timing = { network_ms: netMs, backend_ms: backendMs, wiring_ms: Math.max(0, netMs - backendMs) };
        return j;
      }
    }catch(_e){ /* try next */ }
  }
  return null;
}

/* Local detector: turn engine overlay (real CC boxes grouped to lines/words)
   into a recognition-shaped det result. Recognition text is taken from the
   chosen reference passage aligned by line (rec stub for offline demo). */
function localDetect(overlay, expectedText){
  const expLines = (expectedText||'').split(/\n+/).filter(Boolean);
  const lines = overlay.lines.map((L,i)=>{
    const x0=Math.min(...L.boxes.map(b=>b.x)), x1=Math.max(...L.boxes.map(b=>b.x+b.w));
    const y0=Math.min(...L.boxes.map(b=>b.y)), y1=Math.max(...L.boxes.map(b=>b.y+b.h));
    return { box:[x0,y0,x1-x0,y1-y0], text: expLines[i] || '', score: 0.0, words:(L.words||[]).length };
  });
  return { engine:'local-cc', det:true, rec:false, lines,
    nWords: overlay.words.length, nChars: overlay.letters.length };
}

function wordGroupsToBoxes(wordGroups){
  const boxes = [];
  (wordGroups || []).forEach(word=>{
    if (!Array.isArray(word) || !word.length) return;
    const x0 = Math.min(...word.map(b=>b.x));
    const x1 = Math.max(...word.map(b=>b.x+b.w));
    const y0 = Math.min(...word.map(b=>b.y));
    const y1 = Math.max(...word.map(b=>b.y+b.h));
    boxes.push({ x:x0, y:y0, w:x1-x0, h:y1-y0 });
  });
  return boxes;
}

/* Prefer handwriting-only words from non-printed lines whenever available.
   Fallback order:
   1) non-printed line words
   2) scoreLines words
   3) overlay.words (legacy flat list)
*/
function handwritingWordBoxes(overlay){
  if (!overlay) return [];

  const lines = Array.isArray(overlay.lines) ? overlay.lines : [];
  if (lines.length){
    const hasPrintedLabels = lines.some(L=>L && L.printed===true);
    if (hasPrintedLabels){
      const fromHandLines = [];
      lines.forEach(L=>{ if (L && !L.printed && Array.isArray(L.words)) fromHandLines.push(...wordGroupsToBoxes(L.words)); });
      if (fromHandLines.length) return fromHandLines;
    }
  }

  const scoreLines = Array.isArray(overlay.scoreLines) ? overlay.scoreLines : [];
  if (scoreLines.length){
    const fromScore = [];
    scoreLines.forEach(L=>{ if (L && Array.isArray(L.words)) fromScore.push(...wordGroupsToBoxes(L.words)); });
    if (fromScore.length) return fromScore;
  }

  return Array.isArray(overlay.words) ? overlay.words : [];
}

/* Keep only OCR lines that overlap local word boxes (orange boxes).
   This aligns recognition output with the exact regions the detector marked
   as words, and drops text from margins/background artifacts. */
function restrictToWordBoxes(lines, words){
  if (!Array.isArray(lines) || !lines.length || !Array.isArray(words) || !words.length) return lines || [];

  const expanded = words.map(w=>{
    const pad = Math.max(2, Math.round(Math.min(w.w||0, w.h||0) * 0.15));
    return { x:(w.x||0)-pad, y:(w.y||0)-pad, w:(w.w||0)+pad*2, h:(w.h||0)+pad*2 };
  });

  const interArea = (a, b)=>{
    const ax0=a[0], ay0=a[1], ax1=ax0+Math.max(0,a[2]||0), ay1=ay0+Math.max(0,a[3]||0);
    const bx0=b.x, by0=b.y, bx1=bx0+Math.max(0,b.w||0), by1=by0+Math.max(0,b.h||0);
    const ix = Math.max(0, Math.min(ax1, bx1) - Math.max(ax0, bx0));
    const iy = Math.max(0, Math.min(ay1, by1) - Math.max(ay0, by0));
    return ix * iy;
  };

  const inside = (cx, cy, b)=> cx>=b.x && cx<=b.x+b.w && cy>=b.y && cy<=b.y+b.h;

  const kept = lines.filter(l=>{
    const box = Array.isArray(l.box) ? l.box : [0,0,0,0];
    const area = Math.max(1, Math.max(0, box[2]||0) * Math.max(0, box[3]||0));
    const cx = (box[0]||0) + (box[2]||0)/2;
    const cy = (box[1]||0) + (box[3]||0)/2;

    for (const w of expanded){
      if (inside(cx, cy, w)) return true;
      if ((interArea(box, w) / area) >= 0.18) return true;
    }
    return false;
  });

  // Printed hints are heuristic. Prefer non-printed lines only if enough remain;
  // otherwise keep all kept lines to avoid dropping valid handwriting entirely.
  const unprinted = kept.filter(l=>!(l && l.printed_hint));
  if (unprinted.length >= Math.max(2, Math.ceil(kept.length * 0.4))) return unprinted;

  // Fail open: if OCR and detector disagree on geometry, keep original lines.
  return kept.length ? kept : lines;
}

/* Convert server handwriting lines (boxes in the processed-image pixel space the
   server received) into orange-box geometry scaled to the destination canvas.
   The server already classified printed vs handwriting; we draw HANDWRITING
   ONLY, which is the fix for orange boxes landing on printed text in mixed
   (printed + handwritten) pages. */
function serverHandBoxes(lines, procW, procH, dstW, dstH){
  if (!Array.isArray(lines) || !lines.length) return [];
  const sx = (procW>0 && dstW>0) ? dstW/procW : 1;
  const sy = (procH>0 && dstH>0) ? dstH/procH : 1;
  const out = [];
  lines.forEach(l=>{
    if (l && l.printed_hint) return;            // belt-and-suspenders
    const b = Array.isArray(l && l.box) ? l.box : null;
    if (!b || b.length < 4) return;
    const w = (b[2]||0)*sx, h = (b[3]||0)*sy;
    if (w <= 1 || h <= 1) return;
    out.push({ x:(b[0]||0)*sx, y:(b[1]||0)*sy, w, h });
  });
  return out;
}

/* Draw the detection overlay onto a canvas (boxes for lines + words).
   When `serverBoxes` (handwriting boxes from the server) is supplied, the orange
   boxes come from the server's print/handwriting classification instead of the
   local connected-component split — far more reliable on mixed pages. */
function renderDetection(srcCanvas, overlay, mode, serverBoxes){
  const c = document.createElement('canvas');
  c.width = overlay.w; c.height = overlay.h;
  const ctx = c.getContext('2d');
  if (mode === 'binary'){
    const id = ctx.createImageData(overlay.w, overlay.h);
    for (let i=0;i<overlay.ink.length;i++){ const v=overlay.ink[i]?20:251; id.data[i*4]=v;id.data[i*4+1]=v;id.data[i*4+2]=v+ (overlay.ink[i]?40:0);id.data[i*4+3]=255; }
    ctx.putImageData(id,0,0);
  } else {
    ctx.drawImage(srcCanvas, 0, 0);
  }
  if (mode === 'detect' || mode === 'words'){
    ctx.lineWidth = Math.max(1.5, overlay.w/500);
    const useServer = Array.isArray(serverBoxes) && serverBoxes.length > 0;
    const boxes = useServer ? serverBoxes : overlay.words;
    boxes.forEach(b=>{
      ctx.strokeStyle = 'rgba(212,99,58,.9)';
      ctx.fillStyle = 'rgba(212,99,58,.10)';
      ctx.fillRect(b.x,b.y,b.w,b.h); ctx.strokeRect(b.x,b.y,b.w,b.h);
    });
    // Local baseline regression lines only make sense with local boxes.
    if (!useServer){
      overlay.lines.forEach(L=>{
        if(!L.reg) return;
        const xs=L.boxes.map(b=>b.cx); if(!xs.length) return;
        const x0=Math.min(...xs), x1=Math.max(...xs);
        ctx.strokeStyle='rgba(47,143,127,.9)'; ctx.lineWidth=Math.max(1,overlay.w/650);
        ctx.beginPath(); ctx.moveTo(x0, L.reg.m*x0+L.reg.c); ctx.lineTo(x1, L.reg.m*x1+L.reg.c); ctx.stroke();
      });
    }
  }
  return c;
}

/* crop the actual handwriting region (bounding box of all ink) for the report */
function cropActual(srcCanvas, overlay){
  if (!overlay.letters.length) return srcCanvas;
  const x0=Math.min(...overlay.letters.map(b=>b.x))-6;
  const y0=Math.min(...overlay.letters.map(b=>b.y))-6;
  const x1=Math.max(...overlay.letters.map(b=>b.x+b.w))+6;
  const y1=Math.max(...overlay.letters.map(b=>b.y+b.h))+6;
  const w=Math.max(10,x1-x0), h=Math.max(10,y1-y0);
  const c=document.createElement('canvas'); c.width=w; c.height=h;
  const ctx=c.getContext('2d'); ctx.fillStyle='#fff'; ctx.fillRect(0,0,w,h);
  ctx.drawImage(srcCanvas, x0,y0,w,h, 0,0,w,h);
  return c;
}

async function canvasToBlob(canvas){
  return new Promise(res=>{ if(canvas.toBlob) canvas.toBlob(res,'image/png'); else res(null); });
}

global.VahiniOCR = { serverOCR, serverVLAnalyze, serverPythonReport, getLastServerError, localDetect, handwritingWordBoxes, restrictToWordBoxes, renderDetection, serverHandBoxes, cropActual, canvasToBlob };
})(window);
