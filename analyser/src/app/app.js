/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini Studio — flow controller (intake → upload → process → report)
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

function renderVLInsights(vl){
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
  return `<section class="vl-insights" style="max-width:210mm;margin:18px auto 0;background:#fff;border:1px solid rgba(34,40,49,.12);border-radius:14px;padding:14px 16px;">
    <div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline;flex-wrap:wrap;">
      <h3 style="margin:0;font-family:Spectral,serif;font-size:20px;color:#1d2938;">Context-aware document understanding</h3>
      <span style="font-size:12px;font-weight:700;color:#075E63;background:#DCF3F4;border-radius:999px;padding:4px 10px;">${dt}${conf!=null?` · ${conf}%`:''}</span>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 12px;">${chips.map(c=>`<span style="font-size:11px;background:#F5F7FA;border:1px solid rgba(34,40,49,.1);border-radius:999px;padding:4px 9px;color:#354052;">${c}</span>`).join('')}</div>
    ${regions.length ? `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;">${regions.map(r=>`<figure style="margin:0;border:1px solid rgba(34,40,49,.12);border-radius:10px;overflow:hidden;background:#fafafa;">
      <img src="${r.preview||''}" alt="Detected region" style="display:block;width:100%;height:86px;object-fit:cover;background:#fff;" />
      <figcaption style="padding:6px 8px;font-size:10.5px;color:#4a5568;line-height:1.35;">${esc((r.text||'').slice(0,48) || 'Region')}</figcaption>
    </figure>`).join('')}</div>` : ''}
  </section>`;
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

/* ---------- role selection (personas removed — always the individual) ---------- */
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
  $('#go-process').disabled = false;
}

function handleSample(file){
  if (!file) return;
  const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
  if (isPdf){
    $('#dz-prompt').textContent = 'Reading PDF…';
    pdfFirstPageToImage(file).then(({ img, url, pages })=>{
      showSample(img, url);
      if (pages > 1){
        const p = $('#dz-prompt');
        if (p){ p.style.display='block'; p.textContent = 'PDF has ' + pages + ' pages — only page 1 is analysed.'; }
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
  $('#dz-prompt').style.display='block'; $('#go-process').disabled=true; $('#file-input').value='';
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
  { id:'bin',  t:'Binarization', d:'Otsu / adaptive threshold — ink vs paper' },
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
function showStage(canvas, tag){
  const host = $('#proc-stage'); host.querySelector('.stage-tag').textContent = tag;
  const old = host.querySelector('canvas'); if(old) old.remove();
  host.appendChild(canvas);
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

async function runPipeline(){
  go('process');
  // restore the pipeline panel + heading if a previous run replaced them with a rejection
  if (processPanelHTML !== null){ const pp=$('#screen-process .panel'); if(pp) pp.innerHTML = processPanelHTML; }
  const ph=$('#screen-process .screen-head'); if(ph) ph.style.display='';
  renderLog();
  const img = state.imageEl;
  collectIntake();

  // 1 load
  stepState('load','active'); await sleep(420);
  const { metrics, overlay } = VahiniEngine.analyze(img);
  // Validity gate: refuse non-handwriting / insufficient samples outright,
  // rather than emit a confident-looking but meaningless 20-factor report.
  if (metrics.reject && metrics.reject.rejected){ showReject(metrics.reject); return; }
  showStage(VahiniOCR.renderDetection(overlay.canvas, overlay, 'src'), 'Input');
  stepState('load','done', `<b>${overlay.w}×${overlay.h}</b> working resolution`);

  // 2 gray
  stepState('gray','active'); await sleep(480);
  stepState('gray','done', 'Luminance + corner-lighting check');

  // 3 binarize
  stepState('bin','active'); await sleep(360);
  showStage(VahiniOCR.renderDetection(overlay.canvas, overlay, 'binary'), 'Binarized ink map');
  stepState('bin','done', `Method: <b>${metrics.binMethod}</b>`);

  // 4 segment
  stepState('seg','active'); await sleep(560);
  showStage(VahiniOCR.renderDetection(overlay.canvas, overlay, 'words'), 'Lines · words · letters');
  stepState('seg','done', `<b>${metrics.nLines}</b> lines · <b>${metrics.nWords}</b> words · <b>${metrics.nChars}</b> letters`);

  // 5 OCR (server first, fallback local)
  stepState('ocr','active'); await sleep(300);
  let ocrEngine='local', ocrResult=null;
  let vlResult = null;
  let pyReport = null;
  let pyTiming = null;
  let procW = null, procH = null;   // processed-image dims the server worked on
  const blob = await VahiniOCR.canvasToBlob(overlay.canvas);
  if (blob){
    if (window.VAHINI_PYTHON_REPORT === true && window.VahiniOCR && typeof VahiniOCR.serverPythonReport === 'function'){
      pyReport = await VahiniOCR.serverPythonReport(blob, state.expected || '');
      if (pyReport && pyReport.ok !== false){
        ocrEngine = 'server';
        pyTiming = pyReport._timing || null;
        procW = pyReport.proc_w || null; procH = pyReport.proc_h || null;
        const pyLines = Array.isArray(pyReport.hand_lines) ? pyReport.hand_lines : [];
        // The Python server already separates handwriting from printed text with
        // CV features (stroke-width / confidence / letterhead band). Trust that
        // set directly — re-filtering it through the weaker in-browser detector
        // (restrictToWordBoxes) was discarding most real handwriting on photos,
        // leaving the recognised-text panel almost empty.
        ocrResult = { lines: pyLines, full_text: pyLines.map(l=>l.text).filter(Boolean).join('\n') };
        vlResult = {
          document_context: pyReport.document_context || null,
          layout: pyReport.layout || null,
          regions: Array.isArray(pyReport.regions) ? pyReport.regions : [],
          factor_regions: pyReport.factor_regions || {},
        };
      }
    }

    if (!ocrResult){
      if (window.VahiniOCR && typeof VahiniOCR.serverVLAnalyze === 'function'){
        vlResult = await VahiniOCR.serverVLAnalyze(blob);
      }
      const srv = await VahiniOCR.serverOCR(blob);
      if(srv){
        ocrEngine='server';
        if (window.VahiniOCR && typeof VahiniOCR.restrictToWordBoxes === 'function'){
          const hwBoxes = (typeof VahiniOCR.handwritingWordBoxes === 'function')
            ? VahiniOCR.handwritingWordBoxes(overlay)
            : (overlay.words || []);
          const filteredLines = VahiniOCR.restrictToWordBoxes(srv.lines || [], hwBoxes);
          ocrResult = { ...srv, lines: filteredLines, full_text: filteredLines.map(l=>l.text).filter(Boolean).join('\n') };
        } else {
          ocrResult = srv;
        }
      } else {
        ocrResult = null;
      }
    }
  }
  // Keep the chosen reference passage intact.
  // OCR text is passed separately as recognizedText for report checks.
  if (!ocrResult) ocrResult = VahiniOCR.localDetect(overlay, state.expected);
  // On mixed pages, draw the orange boxes from the SERVER's handwriting
  // classification (printed text excluded) when we have it; else local boxes.
  let serverBoxesForDet = null;
  if (ocrEngine==='server' && ocrResult && Array.isArray(ocrResult.lines) && typeof VahiniOCR.serverHandBoxes === 'function'){
    serverBoxesForDet = VahiniOCR.serverHandBoxes(ocrResult.lines, procW||overlay.w, procH||overlay.h, overlay.w, overlay.h);
  }
  const detCanvas = VahiniOCR.renderDetection(overlay.canvas, overlay, 'detect', serverBoxesForDet);
  showStage(detCanvas, ocrEngine==='server'?'Text detection (server)':'Detection (local)');
  if (ocrEngine==='server'){
    const ctxTag = vlResult && vlResult.document_context ? ' + context model' : '';
    stepState('ocr','done', 'Recognition server: <b>detect + recognise</b>' + ctxTag);
  } else {
    const why = (window.VahiniOCR && typeof VahiniOCR.getLastServerError === 'function') ? VahiniOCR.getLastServerError() : '';
    const detail = why ? ('Local detector (<b>server offline</b>) · ' + why) : 'Local detector (<b>server offline</b>)';
    stepState('ocr','done', detail);
  }

  // 6 measure
  stepState('meas','active'); await sleep(620);
  if(!metrics.ok){ stepState('meas','done','⚠ weak signal — using best-effort'); }
  let analysis = null;
  if (pyReport && pyReport.analysis) analysis = pyReport.analysis;
  if (!analysis && window.VAHINI_PYTHON_REPORT === true && blob && window.VahiniOCR && typeof VahiniOCR.serverPythonReport === 'function'){
    const py = await VahiniOCR.serverPythonReport(blob, state.expected || '');
    if (py && py.analysis){
      analysis = py.analysis;
      if (!vlResult){
        vlResult = {
          document_context: py.document_context || null,
          layout: py.layout || null,
          regions: Array.isArray(py.regions) ? py.regions : [],
          factor_regions: py.factor_regions || {},
        };
      }
    }
  }
  if (!analysis) analysis = VahiniFactors.scoreAll(metrics);
  stepState('meas','done', `20 factors · overall <b>${analysis.overall}/100</b>`);

  // 7 score + render
  stepState('score','active'); await sleep(520);
  const detURL = detCanvas.toDataURL ? compressCanvas(detCanvas, 900, 0.7) : '';
  const recognizedText = (ocrResult.lines||[]).map(l=>l.text).filter(Boolean).join('\n');
  const pipeline = { binMethod:metrics.binMethod, nLines:metrics.nLines, nWords:metrics.nWords, nChars:metrics.nChars, ocrEngine, weak:!metrics.ok, docType:metrics.docType, quality:metrics.quality, vl:vlResult, timing: pyTiming };
  const localCrops = window.VahiniCrops ? VahiniCrops.build(overlay, metrics) : {};
  const vlCrops = serverFactorCrops(vlResult);
  const backendFirst = window.VAHINI_BACKEND_FIRST === true;
  const crops = backendFirst ? { ...localCrops, ...vlCrops } : { ...vlCrops, ...localCrops };
  const letterFindings = window.VahiniLetters ? VahiniLetters.build(overlay, metrics, state.expected, recognizedText, ocrEngine) : null;
  const history = loadHistory(state.intake.writerName);
  VahiniReport.render($('#report-host'), { intake:state.intake, analysis, expectedText:state.expected, recognizedText, ocrEngine, detURL, pipeline, crops, letterFindings, history });
  if (vlResult){
    const html = renderVLInsights(vlResult);
    if (html) $('#report-host').insertAdjacentHTML('beforeend', html);
  }
  saveHistory(state.intake.writerName, analysis.overallMeasured!=null?analysis.overallMeasured:analysis.overall, analysis.sections);
  // warning banner if weak signal
  if(!metrics.ok){
    $('#report-host').insertAdjacentHTML('afterbegin', `<div class="warn-banner" style="max-width:210mm;margin:0 auto 18px;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg><p>The uploaded image had a weak handwriting signal (few clear letters detected). Scores are best-effort — for a precise analysis, upload a sharp, well-lit photo of a few lines of handwriting on plain or lightly-ruled paper.</p></div>`);
  }
  stepState('score','done', `Report ready`);
  await sleep(450);
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
function canvasToImg(canvas){ return new Promise(r=>{ const i=new Image(); i.onload=()=>r(i); i.src=canvas.toDataURL('image/png'); }); }
async function finishIMU(){
  if(!imuSession) return;
  imuSession.stop();
  const summary = imuSession.summary();
  state.expected = state.expected || PASSAGES[0].text;
  const traceCanvas = imuSession.traceCanvas(state.expected);
  const img = await canvasToImg(traceCanvas);
  const { metrics, overlay } = VahiniEngine.analyze(img);
  const analysis = VahiniFactors.scoreAll(metrics, summary);
  const det = VahiniOCR.renderDetection(overlay.canvas, overlay, 'detect');
  VahiniReport.render($('#report-host'), {
    intake: state.intake, analysis, expectedText: state.expected, recognizedText: state.expected,
    detURL: compressCanvas(det, 900, 0.7),
    crops: (window.VahiniCrops ? VahiniCrops.build(overlay, metrics) : null),
    letterFindings: (window.VahiniLetters ? VahiniLetters.build(overlay, metrics, state.expected, state.expected, 'imu') : null),
    history: loadHistory(state.intake.writerName),
    pipeline: { binMethod:metrics.binMethod, nLines:metrics.nLines, nWords:metrics.nWords, nChars:metrics.nChars, ocrEngine:'imu', mode:'imu', docType:metrics.docType, quality:metrics.quality },
    imu: summary,
  });
  saveHistory(state.intake.writerName, analysis.overall, analysis.sections);
  imuSession = null;
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
  // upload is step 1 — straight to analysis
  const goProcess = $('#go-process'); if(goProcess) goProcess.addEventListener('click', runPipeline);
  // optional: capture live with the sensor pen instead
  const usePen = $('#use-pen'); if(usePen) usePen.addEventListener('click', e=>{ e.preventDefault(); collectIntake(); startIMU(); });
  // imu screen
  const bm3 = $('#back-mode3'); if(bm3) bm3.addEventListener('click', cancelIMU);
  const fin = $('#finish-imu'); if(fin) fin.addEventListener('click', finishIMU);
  // chrome
  const reset = $('#st-reset'); if(reset) reset.addEventListener('click', ()=>{ if(imuSession){imuSession.stop();imuSession=null;} clearSample(); go('upload'); });
  const printBtn = $('#print-report'); if(printBtn) printBtn.addEventListener('click', ()=>window.print());
  const newRep = $('#new-report'); if(newRep) newRep.addEventListener('click', ()=>{ if(imuSession){imuSession.stop();imuSession=null;} clearSample(); go('upload'); });

  go('upload');

  // demo helpers (testing / "try sample")
  window.runDemo = async function(_role, instant){
    const img = new Image();
    await new Promise(r=>{ img.onload=r; img.onerror=r; img.src='uploads/test-handwriting.png'; });
    state.imageEl = img;
    state.expected = PASSAGES[0].text;
    if (instant){
      collectIntake();
      const { metrics, overlay } = VahiniEngine.analyze(img);
      const analysis = VahiniFactors.scoreAll(metrics);
      const det = VahiniOCR.renderDetection(overlay.canvas, overlay, 'detect');
      VahiniReport.render($('#report-host'), { intake:state.intake, analysis, expectedText:state.expected, recognizedText:state.expected,
        detURL: compressCanvas(det, 900, 0.7),
        crops: (window.VahiniCrops ? VahiniCrops.build(overlay, metrics) : null),
        letterFindings: (window.VahiniLetters ? VahiniLetters.build(overlay, metrics, state.expected, state.expected, 'local') : null),
        history: loadHistory(state.intake.writerName),
        pipeline:{ binMethod:metrics.binMethod, nLines:metrics.nLines, nWords:metrics.nWords, nChars:metrics.nChars, ocrEngine:'local', docType:metrics.docType, quality:metrics.quality } });
      go('report');
      return $$('#report-host .page').length;
    }
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
