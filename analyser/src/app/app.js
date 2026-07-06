/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini Studio: flow controller (intake → upload → process → report)
   ========================================================================= */
(function(){
'use strict';
const $ = s=>document.querySelector(s);
const $$ = s=>[...document.querySelectorAll(s)];
const sleep = ms=>new Promise(r=>setTimeout(r,ms));

function serverFactorCrops(vl){
  const m = (vl && vl.factor_regions) ? vl.factor_regions : null;
  if (!m || typeof m !== 'object') return {};
  const out = {};
  Object.keys(m).forEach(k=>{
    const n = Number(k);
    const v = m[k] || {};
    if (!Number.isFinite(n) || n < 1 || n > 20) return;
    if (!v.url) return;
    out[n] = { url: v.url, caption: v.caption || 'server vision evidence' };
  });
  return out;
}

/* Compress a canvas to a small JPEG data URL (downscale + lossy) so the
   saved PDF stays light. The detection image is shown ~210px tall in the
   report, so ~900px wide at q0.7 is plenty and cuts size ~10×. */
function compressCanvas(canvas, maxW, q){
  maxW = maxW || 900; q = q || 0.7;
  const scale = Math.min(1, maxW / canvas.width);
  if (scale === 1) return canvas.toDataURL('image/jpeg', q);
  const c = document.createElement('canvas');
  c.width = Math.round(canvas.width * scale);
  c.height = Math.round(canvas.height * scale);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0,0,c.width,c.height);
  ctx.drawImage(canvas, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', q);
}
/* Compress a logo/image data URL to a bounded JPEG (keeps PDF small). */
function compressImageURL(url, maxW, q){
  return new Promise(res=>{
    const img = new Image();
    img.onload = ()=>{
      const scale = Math.min(1, (maxW||320) / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.max(1, Math.round(img.width * scale));
      c.height = Math.max(1, Math.round(img.height * scale));
      const ctx = c.getContext('2d');
      ctx.fillStyle = '#fff'; ctx.fillRect(0,0,c.width,c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      res(c.toDataURL('image/jpeg', q||0.8));
    };
    img.onerror = ()=>res(url);
    img.src = url;
  });
}

function renderVLInsights(vl, recInfo){
  if (!vl || !vl.document_context) return '';
  const esc = s => String(s==null?'':s).replace(/[&<>\"]/g, c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
  const doc = vl.document_context || {};
  const dt = (doc.document_type && doc.document_type.type) ? doc.document_type.type : 'unknown';
  const conf = (doc.document_type && Number.isFinite(doc.document_type.confidence))
    ? Math.round(doc.document_type.confidence * 100)
    : null;
  const layout = vl.layout || {};
  const regions = Array.isArray(vl.regions) ? vl.regions.slice(0, 6) : [];
  const chips = [
    doc.purpose ? `Purpose: ${doc.purpose}` : '',
    doc.intended_audience ? `Audience: ${doc.intended_audience}` : '',
    Number.isFinite(doc.formality_level) ? `Formality: ${Math.round(doc.formality_level*100)}%` : '',
    Number.isFinite(doc.content_coherence) ? `Coherence: ${Math.round(doc.content_coherence*100)}%` : '',
    Number.isFinite(layout.layout_complexity) ? `Layout complexity: ${Math.round(layout.layout_complexity*100)}%` : '',
  ].filter(Boolean);
  // Caption honesty: garbled low-confidence readings under each crop erode
  // trust. Show the recognised text only when the engine was actually
  // confident in it; otherwise label the region neutrally: always with the
  // confidence percentage in brackets.
  const regionCaption = (r)=>{
    const sc = Math.round(((r && r.score) || 0) * 100);
    const t = String((r && r.text) || '').trim();
    return (r && r.score >= 0.8 && t) ? `“${esc(t.slice(0,42))}” (${sc}%)` : `handwriting region (${sc}%)`;
  };
  const recPct = (recInfo && Number.isFinite(recInfo.confidence_pct)) ? recInfo.confidence_pct : null;
  const printedN = (recInfo && Number.isFinite(recInfo.printed_lines)) ? recInfo.printed_lines : 0;
  return `<section class="vl-insights" style="max-width:210mm;margin:18px auto 0;background:#fff;border:1px solid rgba(34,40,49,.12);border-radius:14px;padding:14px 16px;">
    <div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline;flex-wrap:wrap;">
      <h3 style="margin:0;font-family:Spectral,serif;font-size:20px;color:#1d2938;">What kind of page is this?</h3>
      <span style="font-size:12px;font-weight:700;color:#075E63;background:#DCF3F4;border-radius:999px;padding:4px 10px;">${dt}${conf!=null?` · ${conf}%`:''}</span>
    </div>
    <p style="margin:6px 0 0;font-size:11.5px;line-height:1.55;color:#4a5568;">
      <b>Why this section:</b> before scoring, the analyser works out what your page is (a letter, an exam answer, a form) and which parts are pen handwriting.
      That is how it keeps printed text out of your scores and compares your writing against the right kind of page.
      ${printedN?`On this page it found and <b>excluded ${printedN} printed line${printedN>1?'s':''}</b>: only your handwriting was analysed.`:''}
    </p>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 12px;">${chips.map(c=>`<span style="font-size:11px;background:#F5F7FA;border:1px solid rgba(34,40,49,.1);border-radius:999px;padding:4px 9px;color:#354052;">${c}</span>`).join('')}</div>
    ${regions.length ? `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;">${regions.map(r=>`<figure style="margin:0;border:1px solid rgba(34,40,49,.12);border-radius:10px;overflow:hidden;background:#fafafa;">
      <img src="${r.preview||''}" alt="Detected region" style="display:block;width:100%;height:86px;object-fit:cover;background:#fff;" />
      <figcaption style="padding:6px 8px;font-size:10.5px;color:#4a5568;line-height:1.35;">${regionCaption(r)}</figcaption>
    </figure>`).join('')}</div>` : ''}
    <p style="margin:12px 0 0;font-size:11px;line-height:1.55;color:#4a5568;background:#F5F7FA;border-radius:9px;padding:9px 12px;">
      <b>Note · text recognition is under progress and will improve soon</b>: accuracy rises with every update, delivered in increments${recPct!=null?` (current reading confidence: ${recPct}%)`:''}. A wrong word here never changes the 20 factor scores: they are measured from the geometry of the writing, not from reading it.
      Spotted a problem or have an idea? Please report it at <a href="https://github.com/vahinitech/20factor-analyser/issues" style="color:#075E63;font-weight:700;">github.com/vahinitech/20factor-analyser</a>.
    </p>
  </section>`;
}

/* Draw the server-detected word boxes (orange) and their fitted baselines
   (teal) over the uploaded photo: the detection view users know from
   earlier releases. Boxes arrive in the server's processing resolution
   (proc_w × proc_h) and are scaled onto the canvas. */
function drawDetectionOverlay(img, pyReport, maxW){
  try{
    const lines = Array.isArray(pyReport.hand_lines) ? pyReport.hand_lines : [];
    if (!lines.length) return null;
    maxW = maxW || 1100;
    const w0 = img.naturalWidth || img.width, h0 = img.naturalHeight || img.height;
    const pw = Number(pyReport.proc_w) || w0, ph = Number(pyReport.proc_h) || h0;
    // Zoom to the writing: crop to the union of the detected boxes (plus
    // padding) so the boxes read clearly even from a tall phone photo of a
    // whole page.
    let ux0 = Infinity, uy0 = Infinity, ux1 = -Infinity, uy1 = -Infinity;
    lines.forEach(l=>{
      const b = l.box || [0,0,0,0];
      if (!(b[2] > 2 && b[3] > 2)) return;
      ux0 = Math.min(ux0, b[0]); uy0 = Math.min(uy0, b[1]);
      ux1 = Math.max(ux1, b[0]+b[2]); uy1 = Math.max(uy1, b[1]+b[3]);
    });
    if (!(ux1 > ux0 && uy1 > uy0)){ ux0 = 0; uy0 = 0; ux1 = pw; uy1 = ph; }
    const padX = (ux1-ux0)*0.05 + pw*0.01, padY = (uy1-uy0)*0.06 + ph*0.01;
    ux0 = Math.max(0, ux0-padX); uy0 = Math.max(0, uy0-padY);
    ux1 = Math.min(pw, ux1+padX); uy1 = Math.min(ph, uy1+padY);
    // proc-space crop -> source-image pixels
    const kx = w0 / Math.max(1, pw), ky = h0 / Math.max(1, ph);
    const sx0 = ux0*kx, sy0 = uy0*ky, sw = (ux1-ux0)*kx, sh = (uy1-uy0)*ky;
    const scale = Math.min(1.6, maxW / Math.max(1, sw));
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(sw * scale));
    c.height = Math.max(1, Math.round(sh * scale));
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(img, sx0, sy0, sw, sh, 0, 0, c.width, c.height);
    const bx = (v)=> (v - ux0) * kx * scale;   // proc x -> canvas x
    const by = (v)=> (v - uy0) * ky * scale;   // proc y -> canvas y
    lines.forEach(l=>{
      const b = l.box || [0,0,0,0];
      if (!(b[2] > 2 && b[3] > 2)) return;
      const x = bx(b[0]), y = by(b[1]);
      const w = b[2]*kx*scale, h = b[3]*ky*scale;
      ctx.strokeStyle = '#D4633A';                       // orange word box
      ctx.lineWidth = Math.max(2, c.width / 450);
      ctx.strokeRect(x, y, w, h);
      ctx.strokeStyle = 'rgba(47,143,127,.9)';           // teal baseline
      ctx.lineWidth = Math.max(1.5, c.width / 700);
      ctx.beginPath(); ctx.moveTo(x, y + h); ctx.lineTo(x + w, y + h); ctx.stroke();
    });
    return c.toDataURL('image/jpeg', 0.74);
  }catch(_e){ return null; }
}

const state = {
  role:'individual',
  intake:{},
  imageEl:null,        // HTMLImageElement of the uploaded sample
  logoData:null,
  expected:'',
};

const PASSAGES = [
  { id:'fox', title:'Classic pangram', text:'The quick brown fox\njumps over the lazy dog.\nPack five dozen jugs.' },
  { id:'garden', title:'Primary practice', text:'The sun is bright today.\nWe play in the green garden.\nBirds sing in the tall trees.' },
  { id:'quote', title:'Cursive flow', text:'Practice makes progress.\nEvery letter tells a story.\nWrite a little every day.' },
];

/* ---------- screens / steps ---------- */
const STEP_OF = { upload:0, imu:0, process:1, report:2 };
function go(name){
  $$('.screen').forEach(s=>s.classList.remove('on'));
  $('#screen-'+name).classList.add('on');
  const idx = STEP_OF[name] != null ? STEP_OF[name] : 0;
  $$('.steps .step').forEach((el,i)=>{
    el.classList.toggle('on', i===idx);
    el.classList.toggle('done', i<idx);
  });
  $$('.steps .sep').forEach((el,i)=>el.classList.toggle('done', i<idx));
  window.scrollTo(0,0);
}

/* ---------- role selection (personas removed: always the individual) ---------- */
function selectRole(){ state.role = 'individual'; }

/* ---------- intake (no personal details collected) ---------- */
function collectIntake(){
  state.intake = { role:'individual', writerName:'', grade:'', age:'', org:'', orgContact:'', email:'', logoData:null };
}

/* ---------- file inputs ---------- */
function readImageFile(file, cb){
  if(!file || !file.type.startsWith('image/')) return;
  const fr = new FileReader();
  fr.onload = e=>{ const img=new Image(); img.onload=()=>cb(img, e.target.result); img.src=e.target.result; };
  fr.readAsDataURL(file);
}

function setupUploadDrop(){
  const dz = $('#dropzone'), input = $('#file-input');
  dz.addEventListener('click', ()=>input.click());
  ['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.add('drag');}));
  ['dragleave','drop'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.remove('drag');}));
  dz.addEventListener('drop', e=>{ const f=e.dataTransfer.files[0]; handleSample(f); });
  input.addEventListener('change', e=>handleSample(e.target.files[0]));
  $('#dz-clear').addEventListener('click', e=>{ e.stopPropagation(); clearSample(); });
}
/* Lazy-load pdf.js (UMD) only when a PDF is actually uploaded. */
function loadPdfJs(){
  if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
  return new Promise((res, rej)=>{
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
    s.onload = ()=>{
      try { window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js'; } catch(_e){}
      res(window.pdfjsLib);
    };
    s.onerror = ()=>rej(new Error('Could not load the PDF reader (offline?)'));
    document.head.appendChild(s);
  });
}

/* Render ONLY the first page of a PDF to an image. Multi-page PDFs are
   restricted to page 1, matching the server. */
async function pdfFirstPageToImage(file){
  const lib = await loadPdfJs();
  const buf = await file.arrayBuffer();
  const pdf = await lib.getDocument({ data: buf }).promise;
  const page = await pdf.getPage(1);
  const viewport = page.getViewport({ scale: 2.0 });
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(viewport.width);
  canvas.height = Math.round(viewport.height);
  await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
  const url = canvas.toDataURL('image/png');
  const img = await new Promise((res)=>{ const i=new Image(); i.onload=()=>res(i); i.src=url; });
  return { img, url, pages: pdf.numPages };
}

function showSample(img, url){
  state.imageEl = img;
  $('#dz-preview').src = url; $('#dz-preview').style.display='block';
  $('#dz-clear').style.display='block';
  $('#dz-prompt').style.display='none';
  applyServiceGate();
}

function handleSample(file){
  if (!file || serviceUp === false) return;
  const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
  if (isPdf){
    $('#dz-prompt').textContent = 'Reading PDF…';
    pdfFirstPageToImage(file).then(({ img, url, pages })=>{
      showSample(img, url);
      if (pages > 1){
        const p = $('#dz-prompt');
        if (p){ p.style.display='block'; p.textContent = 'PDF has ' + pages + ' pages: only page 1 is analysed.'; }
      }
    }).catch(err=>{
      const p = $('#dz-prompt'); if (p){ p.style.display='block'; p.textContent = (err && err.message) ? err.message : 'Could not read this PDF.'; }
    });
    return;
  }
  readImageFile(file, (img, url)=>showSample(img, url));
}
function clearSample(){
  state.imageEl=null; $('#dz-preview').style.display='none'; $('#dz-clear').style.display='none';
  $('#dz-prompt').style.display='block'; $('#file-input').value='';
  applyServiceGate();
}

/* ---------- recognition-server availability gate -----------------------
   Scoring runs entirely on the recognition server (see ocr.js); there is
   no offline fallback. Rather than let someone upload and sit through the
   pipeline animation only to hit a rejection after the request times out,
   probe the server up front and keep uploads disabled with a clear reason
   until it answers, re-checking periodically so it recovers on its own. */
let serviceUp = null;            // null = not checked yet
let serviceCheckTimer = null;

function applyServiceGate(){
  const down = serviceUp === false;
  const banner = $('#service-banner');
  const dz = $('#dropzone'), input = $('#file-input'), go = $('#go-process'), pen = $('#use-pen');
  if (banner) banner.style.display = down ? 'flex' : 'none';
  if (dz) dz.classList.toggle('disabled', down);
  if (input) input.disabled = down;
  if (pen) pen.classList.toggle('disabled', down);
  if (go) go.disabled = down || !state.imageEl;
}

async function checkService(){
  const detail = $('#service-banner-detail');
  if (detail && serviceUp === null) detail.textContent = 'Checking connection…';
  if (!(window.VahiniOCR && typeof VahiniOCR.checkHealth === 'function')){ serviceUp = true; applyServiceGate(); return; }
  const res = await VahiniOCR.checkHealth();
  serviceUp = !!(res && res.ok);
  if (detail){
    detail.textContent = serviceUp
      ? 'Connected.'
      : 'Start it with docker compose up -d, or python analyser/server/ppocr-server.py. It reconnects automatically.';
  }
  applyServiceGate();
}

function startServicePolling(){
  checkService();
  if (serviceCheckTimer) clearInterval(serviceCheckTimer);
  serviceCheckTimer = setInterval(checkService, 10000);
}

/* Preview the uploaded photo in the process screen. Scoring runs server-side
   now, so there is no in-browser detection overlay to draw; without this
   the stage box would sit empty (and visibly black) for the whole pipeline. */
function showProcStagePreview(img){
  const host = $('#proc-stage');
  if (!host) return;
  const old = host.querySelector('img.proc-preview'); if (old) old.remove();
  const el = document.createElement('img');
  el.className = 'proc-preview';
  el.alt = 'uploaded handwriting sample';
  el.src = img.src;
  host.appendChild(el);
}

/* ---------- expected passage ---------- */
function setupPassages(){
  const list = $('#passage-list');
  list.innerHTML = PASSAGES.map((p,i)=>`<div class="passage ${i===0?'sel':''}" data-id="${p.id}">
    <div class="pt">${p.title}</div><div class="pp">${p.text.replace(/\n/g,'<br>')}</div></div>`).join('')
    + `<div class="passage" data-id="custom"><div class="pt">Custom passage</div><textarea id="custom-text" placeholder="Type the exact text the writer copied…"></textarea></div>`;
  state.expected = PASSAGES[0].text;
  list.addEventListener('click', e=>{
    const card = e.target.closest('.passage'); if(!card) return;
    $$('.passage').forEach(c=>c.classList.remove('sel')); card.classList.add('sel');
    const id = card.dataset.id;
    if(id==='custom'){ state.expected = $('#custom-text').value || ''; $('#custom-text').focus(); }
    else state.expected = PASSAGES.find(p=>p.id===id).text;
  });
  list.addEventListener('input', e=>{ if(e.target.id==='custom-text') state.expected = e.target.value; });
}

/* ---- scan history (progress vs last scan) ------------------------------ */
function loadHistory(name){
  try{ const h=JSON.parse(localStorage.getItem('vahini_history')||'[]');
    const mine=h.filter(e=>e.name && name && e.name.toLowerCase()===name.toLowerCase());
    return mine.length? mine[mine.length-1] : null; }catch(e){ return null; }
}
function saveHistory(name, overall, sections){
  try{ const h=JSON.parse(localStorage.getItem('vahini_history')||'[]');
    h.push({ name, date:new Date().toISOString().slice(0,10), overall,
      sections:(sections||[]).map(s=>({id:s.id,avg100:s.avg100})) });
    localStorage.setItem('vahini_history', JSON.stringify(h.slice(-60))); }catch(e){}
}

/* ---------- the pipeline ---------- */
const STEPS = [
  { id:'load', t:'Capture & normalise', d:'Decoding photo, downscaling for analysis' },
  { id:'gray', t:'Grayscale + denoise', d:'Luminance conversion (§4 step 1)' },
  { id:'bin',  t:'Binarization', d:'Otsu / adaptive threshold: ink vs paper' },
  { id:'seg',  t:'Segment lines & words', d:'Connected components + gap thresholding' },
  { id:'ocr',  t:'Text detect + recognise', d:'Detection boxes & recognition' },
  { id:'meas', t:'Measure 20 factors', d:'Deterministic CV geometry (§4C)' },
  { id:'score',t:'Aggregate & narrate', d:'Section weights → overall → report' },
];
function renderLog(){
  $('#proc-log-steps').innerHTML = STEPS.map(s=>`<div class="log-step" id="ls-${s.id}">
    <span class="ls-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/></svg></span>
    <div><div class="ls-t">${s.t}</div><div class="ls-d">${s.d}</div></div></div>`).join('');
}
function stepState(id, st, detail){
  const el = $('#ls-'+id); if(!el) return;
  el.classList.remove('active','done'); el.classList.add(st);
  const ico = el.querySelector('.ls-ico');
  if(st==='active') ico.innerHTML='<span class="spinner"></span>';
  else if(st==='done') ico.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
  if(detail){ const d=el.querySelector('.ls-d'); d.innerHTML=detail; }
}

/* The engine refused the image (not handwriting / not enough of it). Replace
   the pipeline panel with a clear, honest rejection instead of a fake report. */
let processPanelHTML = null;
function showReject(rej){
  const panel = $('#screen-process .panel');
  if(!panel) return;
  if (processPanelHTML === null) processPanelHTML = panel.innerHTML;
  const head = $('#screen-process .screen-head'); if(head) head.style.display='none';
  const tips = (rej.tips||[]).map(t=>`<li>${t}</li>`).join('');
  panel.innerHTML = `
    <div class="reject-card">
      <div class="reject-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10"/><path d="m3 17 5-5 3 3"/><circle cx="9" cy="9" r="1.6"/><path d="M16 16l5 5M21 16l-5 5"/></svg></div>
      <h2>${rej.reason||"Couldn't analyse this image"}</h2>
      <p class="reject-detail">${rej.detail||''}</p>
      <ul class="reject-tips">${tips}</ul>
      <button class="btn btn-primary" id="reject-retry"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5M12 3v13"/></svg>Upload another photo</button>
    </div>`;
  const retry = $('#reject-retry');
  if(retry) retry.addEventListener('click', ()=>{ clearSample(); go('upload'); });
}

/* Rasterise an HTMLImageElement to a PNG blob to POST to the server. */
function imageToBlob(img){
  const c = document.createElement('canvas');
  c.width = img.naturalWidth || img.width;
  c.height = img.naturalHeight || img.height;
  const ctx = c.getContext('2d');
  ctx.drawImage(img, 0, 0);
  return VahiniOCR.canvasToBlob(c);
}

/* Sample size for the cover / summary, derived from the server's recognised
   handwriting lines (the CV geometry itself lives server-side now). */
function sampleCounts(pyReport){
  const lines = Array.isArray(pyReport.hand_lines) ? pyReport.hand_lines : [];
  const text = pyReport.full_text || lines.map(l=>l.text).filter(Boolean).join('\n') || '';
  const nWords = (text.match(/\S+/g) || []).length;
  const nChars = text.replace(/\s+/g, '').length;
  return { nLines: lines.length, nWords, nChars };
}

/* Server-only pipeline: the recognition server computes every report (OCR +
   the 20-factor analysis). The browser sends the image and renders the result;
   there is no in-browser scorer or offline fallback. */
async function runPipeline(){
  go('process');
  // restore the pipeline panel + heading if a previous run replaced them with a rejection
  if (processPanelHTML !== null){ const pp=$('#screen-process .panel'); if(pp) pp.innerHTML = processPanelHTML; }
  const ph=$('#screen-process .screen-head'); if(ph) ph.style.display='';
  renderLog();
  const img = state.imageEl;
  collectIntake();

  // Defensive re-check: the "Run analysis" button is normally disabled while
  // the server is down, but re-verify here too (it may have dropped since the
  // last poll) so a bad connection fails fast instead of animating through
  // steps that would just time out two minutes later.
  if (serviceUp === false) await checkService();
  if (serviceUp === false){
    showReject({
      reason: 'Recognition server not reachable',
      detail: 'This analyser computes every report on the Vahini recognition server, which isn’t responding right now.',
      tips: [
        'Run the server: docker compose up -d (serves the app + OCR on the same origin)',
        'Or start it directly: python analyser/server/ppocr-server.py',
        'Then reload this page and upload the photo again',
      ],
    });
    return;
  }

  // 1 load: rasterise the upload and show it as the sample
  stepState('load','active'); await sleep(300);
  const blob = await imageToBlob(img);
  let detURL = await compressImageURL(img.src, 1100, 0.72);
  showProcStagePreview(img);
  stepState('load','done', `<b>${img.naturalWidth}×${img.naturalHeight}</b> uploaded`);

  // 2-4 the heavy CV (grayscale, binarize, segment) now runs on the server.
  stepState('gray','active'); await sleep(220); stepState('gray','done', 'Uploading to the recognition server');
  stepState('bin','active');  await sleep(220); stepState('bin','done',  'Server binarizes ink vs paper');
  stepState('seg','active');  await sleep(220); stepState('seg','done',  'Server segments lines · words · letters');

  // 5 recognise + score (single server call returns OCR + the 20-factor analysis)
  stepState('ocr','active');
  let pyReport = null;
  if (blob && window.VahiniOCR && typeof VahiniOCR.serverPythonReport === 'function'){
    pyReport = await VahiniOCR.serverPythonReport(blob, state.expected || '');
  }
  if (pyReport && pyReport.error_code === 'no_handwriting'){
    // The server found text but ALL of it is printed. The analyser scores
    // pen handwriting only: refusing here (instead of scoring machine
    // type) is the whole credibility rule of the product.
    const n = Number(pyReport.printed_lines) || 0;
    showReject({
      reason: 'No handwriting found on this page',
      detail: 'This page looks fully printed' + (n ? ' (' + n + ' printed line' + (n>1?'s':'') + ' detected)' : '')
        + '. The analyser measures pen handwriting only, so printed text is never analysed or scored.',
      tips: [
        'Upload a page written by hand with a pen or pencil',
        'Mixed pages are fine: printed parts are detected and ignored, only the handwriting is scored',
        'For best results photograph the page straight-on in good light',
      ],
    });
    return;
  }
  if (!pyReport || pyReport.ok === false || !pyReport.analysis){
    const why = (window.VahiniOCR && typeof VahiniOCR.getLastServerError === 'function') ? VahiniOCR.getLastServerError() : '';
    showReject({
      reason: 'Recognition server not reachable',
      detail: 'This analyser computes every report on the Vahini recognition server, which isn’t responding right now'
        + (why ? ' (' + why + ')' : '') + '. Start the server and try again.',
      tips: [
        'Run the server: docker compose up -d (serves the app + OCR on the same origin)',
        'Or start it directly: python analyser/server/ppocr-server.py',
        'Then reload this page and upload the photo again',
      ],
    });
    return;
  }
  const pyTiming = pyReport._timing || null;
  const vlResult = {
    document_context: pyReport.document_context || null,
    layout: pyReport.layout || null,
    regions: Array.isArray(pyReport.regions) ? pyReport.regions : [],
    factor_regions: pyReport.factor_regions || {},
  };
  // Redraw the sample with the detected word boxes (orange) + baselines
  // (teal): the detection view shown on the report's first page.
  const boxedURL = drawDetectionOverlay(img, pyReport);
  if (boxedURL) detURL = boxedURL;
  const ctxTag = vlResult.document_context ? ' + context model' : '';
  stepState('ocr','done', 'Recognition server: <b>detect + recognise</b>' + ctxTag);

  // 6 measure: the analysis is already computed server-side
  stepState('meas','active'); await sleep(300);
  const analysis = pyReport.analysis;
  stepState('meas','done', `20 factors · overall <b>${analysis.overall}/100</b>`);

  // 7 render
  stepState('score','active'); await sleep(300);
  const counts = sampleCounts(pyReport);
  const recognizedText = pyReport.full_text
    || (Array.isArray(pyReport.hand_lines) ? pyReport.hand_lines.map(l=>l.text).filter(Boolean).join('\n') : '');
  const pipeline = { nLines:counts.nLines, nWords:counts.nWords, nChars:counts.nChars, ocrEngine:'server', vl:vlResult, timing: pyTiming };
  const crops = serverFactorCrops(vlResult);
  const history = loadHistory(state.intake.writerName);
  VahiniReport.render($('#report-host'), { intake:state.intake, analysis, expectedText:state.expected, recognizedText, ocrEngine:'server', detURL, pipeline, crops, letterFindings:null, history });
  if (vlResult){
    const html = renderVLInsights(vlResult, analysis && analysis.recognition);
    if (html) $('#report-host').insertAdjacentHTML('beforeend', html);
  }
  saveHistory(state.intake.writerName, analysis.overallMeasured!=null?analysis.overallMeasured:analysis.overall, analysis.sections);
  stepState('score','done', `Report ready`);
  await sleep(400);
  go('report');
}

/* ---------- IMU live capture ---------- */
let imuSession=null;

function buildSensorGrid(){
  const groups = VahiniIMU.SENSOR_GROUPS;
  $('#sensor-grid').innerHTML = groups.map(g=>`<div class="sensor-cell">
    <div class="sh"><i style="background:${g.color}"></i><b>${g.label}</b></div>
    <div class="ss">${g.sub}</div>
    <div class="sa">${g.axes.map(a=>`<span style="color:${g.color};background:${g.color}1a">${a}</span>`).join('')}</div>
  </div>`).join('');
}
function drawScope(ctx, buf, bufRaw, color){
  const w=ctx.canvas.width, h=ctx.canvas.height;
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle='rgba(255,255,255,.06)'; ctx.lineWidth=1;
  for(let gx=0; gx<=w; gx+=w/6){ ctx.beginPath(); ctx.moveTo(gx,0); ctx.lineTo(gx,h); ctx.stroke(); }
  const arr=buf.toArray(); if(arr.length<2) return;
  const all = bufRaw ? arr.concat(bufRaw.toArray()) : arr;
  const min=Math.min(...all), max=Math.max(...all), rng=(max-min)||1;
  const plot=(a,wd,alpha)=>{ ctx.globalAlpha=alpha; ctx.strokeStyle=color; ctx.lineWidth=wd; ctx.lineJoin='round'; ctx.beginPath();
    a.forEach((v,i)=>{ const x=(i/(a.length-1))*w, y=h-4-((v-min)/rng)*(h-8); i?ctx.lineTo(x,y):ctx.moveTo(x,y); }); ctx.stroke(); ctx.globalAlpha=1; };
  if(bufRaw) plot(bufRaw.toArray(), 1, .28);
  plot(arr, 2.2, 1);
}
function drawTrace(ctx, trail){
  const w=ctx.canvas.width, h=ctx.canvas.height;
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle='#e6ecf5'; ctx.lineWidth=1;
  for(let y=h*0.42; y<h; y+=h*0.18){ ctx.beginPath(); ctx.moveTo(12,y); ctx.lineTo(w-12,y); ctx.stroke(); }
  ctx.strokeStyle='#16244a'; ctx.lineWidth=2.4; ctx.lineCap='round'; ctx.lineJoin='round';
  ctx.beginPath(); let pen=false;
  trail.forEach(p=>{ if(!p){ pen=false; return; } const x=p.x*w, y=p.y*h; if(!pen){ ctx.moveTo(x,y); pen=true; } else ctx.lineTo(x,y); });
  ctx.stroke();
  for(let i=trail.length-1;i>=0;i--){ if(trail[i]){ ctx.fillStyle='#D4633A'; ctx.beginPath(); ctx.arc(trail[i].x*w, trail[i].y*h, 4.5, 0, 7); ctx.fill(); break; } }
}
function pulseNodes(snap){
  const set=(id,v)=>{ const n=document.querySelector('#'+id+' circle'); if(n) n.setAttribute('opacity', Math.min(0.9, 0.25+v).toFixed(2)); };
  set('node-force', Math.abs(snap.force)/3);
  set('node-front', Math.abs(snap.vel)/40);
  set('node-rear', Math.abs(snap.gyro)/60);
  set('node-mag', 0.35+0.3*Math.abs(Math.sin(snap.t*3)));
}
function startIMU(){
  collectIntake();
  go('imu');
  buildSensorGrid();
  const tctx = $('#imu-trace').getContext('2d');
  const cF = $('#chart-force').getContext('2d'), cT = $('#chart-tilt').getContext('2d'), cV = $('#chart-vel').getContext('2d');
  imuSession = VahiniIMU.createSession();
  imuSession.start(snap=>{
    drawTrace(tctx, snap.trail);
    drawScope(cF, snap.buffers.force, snap.buffers.forceRaw, '#7d86ff');
    drawScope(cT, snap.buffers.tilt, snap.buffers.tiltRaw, '#4fc7b4');
    drawScope(cV, snap.buffers.vel, null, '#f0936a');
    $('#rd-force').textContent = Math.max(0,snap.force).toFixed(2)+' N';
    $('#rd-tilt').textContent = snap.tilt.toFixed(1)+'°';
    $('#rd-vel').textContent = Math.max(0,snap.vel).toFixed(0)+' mm/s';
    $('#st-samples').textContent = snap.nSamp.toLocaleString();
    $('#st-strokes').textContent = snap.strokes;
    $('#st-lifts').textContent = snap.lifts;
    pulseNodes(snap);
  });
}
function cancelIMU(){ if(imuSession){ imuSession.stop(); imuSession=null; } go('upload'); }
async function finishIMU(){
  if(!imuSession) return;
  imuSession.stop();
  const summary = imuSession.summary();
  state.expected = state.expected || PASSAGES[0].text;
  const traceCanvas = imuSession.traceCanvas(state.expected);
  const detURL = compressCanvas(traceCanvas, 900, 0.7);
  const blob = await VahiniOCR.canvasToBlob(traceCanvas);
  imuSession = null;
  // The 20-factor analysis is computed by the server from the reconstructed
  // trace image; the pen's live dynamics remain the on-screen visualisation.
  let pyReport = null;
  if (blob && window.VahiniOCR && typeof VahiniOCR.serverPythonReport === 'function'){
    pyReport = await VahiniOCR.serverPythonReport(blob, state.expected || '');
  }
  if (!pyReport || pyReport.ok === false || !pyReport.analysis){
    go('process');
    showReject({
      reason: 'Recognition server not reachable',
      detail: 'The pen report is computed on the Vahini recognition server, which isn’t responding right now. Start the server and capture again.',
      tips: [
        'Run the server: docker compose up -d',
        'Or start it directly: python analyser/server/ppocr-server.py',
      ],
    });
    return;
  }
  const counts = sampleCounts(pyReport);
  const analysis = pyReport.analysis;
  const vlResult = {
    document_context: pyReport.document_context || null,
    layout: pyReport.layout || null,
    regions: Array.isArray(pyReport.regions) ? pyReport.regions : [],
    factor_regions: pyReport.factor_regions || {},
  };
  VahiniReport.render($('#report-host'), {
    intake: state.intake, analysis, expectedText: state.expected, recognizedText: state.expected,
    detURL,
    crops: serverFactorCrops(vlResult),
    letterFindings: null,
    history: loadHistory(state.intake.writerName),
    pipeline: { nLines:counts.nLines, nWords:counts.nWords, nChars:counts.nChars, ocrEngine:'imu', mode:'imu', vl:vlResult, timing: pyReport._timing||null },
    imu: summary,
  });
  saveHistory(state.intake.writerName, analysis.overall, analysis.sections);
  go('report');
}

/* ---------- logo upload ---------- */
function setupLogo(){
  const input = $('#logo-input');
  if(!input) return;
  input.addEventListener('change', e=>{
    readImageFile(e.target.files[0], async (img,url)=>{ state.logoData=await compressImageURL(url, 300, 0.85); $('#logo-preview').src=state.logoData; $('#logo-preview').style.display='block'; $('#logo-ph').style.display='none'; });
  });
  $('#logo-box').addEventListener('click', ()=>input.click());
}

/* ---------- wire up ---------- */
function init(){
  setupUploadDrop(); setupPassages(); setupLogo();
  // upload is step 1: straight to analysis
  const goProcess = $('#go-process'); if(goProcess) goProcess.addEventListener('click', runPipeline);
  // optional: capture live with the sensor pen instead
  const usePen = $('#use-pen'); if(usePen) usePen.addEventListener('click', e=>{ e.preventDefault(); if (serviceUp === false) return; collectIntake(); startIMU(); });
  const serviceRetry = $('#service-retry'); if(serviceRetry) serviceRetry.addEventListener('click', checkService);
  // imu screen
  const bm3 = $('#back-mode3'); if(bm3) bm3.addEventListener('click', cancelIMU);
  const fin = $('#finish-imu'); if(fin) fin.addEventListener('click', finishIMU);
  // chrome
  const reset = $('#st-reset'); if(reset) reset.addEventListener('click', ()=>{ if(imuSession){imuSession.stop();imuSession=null;} clearSample(); go('upload'); });
  const printBtn = $('#print-report'); if(printBtn) printBtn.addEventListener('click', ()=>window.print());
  const newRep = $('#new-report'); if(newRep) newRep.addEventListener('click', ()=>{ if(imuSession){imuSession.stop();imuSession=null;} clearSample(); go('upload'); });

  go('upload');
  startServicePolling();

  // demo helper (testing / "try sample"): always runs the server pipeline.
  window.runDemo = async function(_role, _instant){
    const img = new Image();
    await new Promise(r=>{ img.onload=r; img.onerror=r; img.src='uploads/test-handwriting.png'; });
    state.imageEl = img;
    state.expected = PASSAGES[0].text;
    await runPipeline();
    return $$('#report-host .page').length;
  };
  // IMU demo: start the live capture, optionally auto-finish to land on the report
  window.runIMUDemo = async function(_role, finish){
    state.mode='imu'; collectIntake(); startIMU();
    if (finish){ await new Promise(r=>setTimeout(r,1400)); await finishIMU(); return $$('#report-host .page').length; }
    return 'streaming';
  };
  const dm = location.search.match(/demo=([\w-]+)/);
  if (dm){
    const v = dm[1];
    setTimeout(()=>{
      if (v==='imu') window.runIMUDemo(null, false);
      else if (v==='imureport') window.runIMUDemo(null, true);
      else window.runDemo(null, v==='report');
    }, 250);
  }
}
document.addEventListener('DOMContentLoaded', init);
})();
