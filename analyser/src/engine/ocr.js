/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini OCR / analysis server client.
   Recognition AND the 20-factor scoring run on the PP-OCRv5 server (see
   ppocr-server.py — PaddleOCR v5, runs fully on your own machine), or any
   endpoint set via window.VAHINI_OCR_ENDPOINT. The browser only sends the
   image and renders the returned analysis; there is no in-browser scorer.
   ========================================================================= */
(function (global) {
'use strict';

/* Candidate endpoints, tried in order:
   1. an explicit window.VAHINI_OCR_ENDPOINT
   2. the local PP-OCRv5 helper server (ppocr-server.py) on this machine */
const CANDIDATES = [
  window.VAHINI_OCR_ENDPOINT || null,
  '/ocr',
  'http://127.0.0.1:8080/ocr',
].filter(Boolean);

const VL_CANDIDATES = CANDIDATES.map(u=>String(u).replace(/\/ocr$/, '/analyze-vl'));
const REPORT_CANDIDATES = CANDIDATES.map(u=>String(u).replace(/\/ocr$/, '/report-python'));
const HEALTH_CANDIDATES = CANDIDATES.map(u=>String(u).replace(/\/ocr$/, '/health'));

let activeEndpoint = null;   // remembered after the first success
let endpointAttempts = Object.create(null); // first-hit warmup can be slow
let lastServerError = '';

/* Cheap reachability probe for the recognition server, used by the app
   controller to gate the upload UI: since scoring runs entirely server-side
   now, there is no point letting someone start a scan that can only fail.
   Returns { ok, endpoint }: ok is true as soon as ANY candidate answers. */
async function checkHealth(timeoutMs){
  timeoutMs = timeoutMs || 4000;
  for (const url of HEALTH_CANDIDATES){
    const ctrl = new AbortController();
    const t = setTimeout(()=>ctrl.abort(), timeoutMs);
    try{
      const res = await fetch(url, { method:'GET', signal:ctrl.signal });
      clearTimeout(t);
      if (!res.ok) continue;
      let healthy = true;
      try{ const j = await res.json(); if (j && j.ok === false) healthy = false; }catch(_e){ /* non-JSON 200 still counts as up */ }
      if (healthy) return { ok:true, endpoint:url };
    }catch(_e){ clearTimeout(t); }
  }
  return { ok:false, endpoint:null };
}

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

async function canvasToBlob(canvas){
  return new Promise(res=>{ if(canvas.toBlob) canvas.toBlob(res,'image/png'); else res(null); });
}

global.VahiniOCR = { serverOCR, serverVLAnalyze, serverPythonReport, getLastServerError, checkHealth, canvasToBlob };
})(window);
