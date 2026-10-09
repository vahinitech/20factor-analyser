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

function serverFactorCrops(vl){
  const m = (vl && vl.factor_regions) ? vl.factor_regions : null;
  if (!m || typeof m !== 'object') return {};
  const out = {};
  Object.keys(m).forEach(k=>{
    const n = Number(k);
    const v = m[k] || {};
    if (!Number.isFinite(n) || n < 1 || n > 20) return;
    // Keep a located region even without an image: a whole-page factor's
    // box still tells the report to say "measured across your whole page".
    if (!v.url && !(Array.isArray(v.bbox) && v.bbox.length === 4)) return;
    out[n] = { ...v, caption: v.caption || 'server vision evidence' };
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
/* A photo the browser cannot open used to do nothing at all: no preview,
   no message, "Run analysis" left greyed out. On 2026-10-06 a visitor on
   Chrome for Mac, between JPEG uploads that worked, tried one iPhone HEIC
   photo five times and saw nothing happen each time. Chrome and Firefox
   cannot decode HEIC; Safari can. Where the browser cannot, heicToJpeg
   converts it; if that fails too, the upload box says what to do. */
function isHeic(file){ return /^image\/hei[cf]/i.test(file.type || '') || /\.(heic|heif)$/i.test(file.name || ''); }
function readImageFile(file, cb, onFail){
  const fail = ()=>{ if (onFail) onFail(); };
  if(!file) return;
  if(!(file.type || '').startsWith('image/') && !isHeic(file)) return fail();
  const fr = new FileReader();
  fr.onerror = fail;
  fr.onload = e=>{ const img=new Image(); img.onload=()=>cb(img, e.target.result); img.onerror=fail; img.src=e.target.result; };
  fr.readAsDataURL(file);
}

/* HEIC to JPEG for browsers without a HEIC decoder. libheif (LGPL-3.0,
   https://github.com/strukturag/libheif) as built by libheif-js, loaded from
   a pinned jsDelivr URL only when such a photo is picked: about 520 KB
   compressed. The script carries SRI; the wasm file is checked against its
   own SHA-384 before it runs. One conversion per file. The photo and its
   JPEG stay in this tab: photos are never stored. */
const LIBHEIF = {
  js: 'https://cdn.jsdelivr.net/npm/libheif-js@1.23.5/libheif-wasm/libheif.js',
  jsSri: 'sha384-VEbrgTthZ3xiJrRrD1QszeA+mvSzQAazOjulZBOV9mXAH+SfRdtQWjzL6E0JYlmP',
  wasm: 'https://cdn.jsdelivr.net/npm/libheif-js@1.23.5/libheif-wasm/libheif.wasm',
  wasmSha384: 'ykFVIusV2Vzqq7NMzIk4GpbFlKHmcCbdhLPI50qMGtV14CpMr+A+5ry6npw4e8z7',
};
const HEIC_MAX_SIDE = 4000;      // same cap as the upload store's own conversion
let libheifPromise = null;
const heicJpegs = new WeakMap();

function loadLibheif(){
  if (!libheifPromise){
    const script = new Promise((res, rej)=>{
      if (window.libheif) return res();
      const s = document.createElement('script');
      s.src = LIBHEIF.js; s.integrity = LIBHEIF.jsSri; s.crossOrigin = 'anonymous';
      s.onload = ()=>res(); s.onerror = ()=>rej(new Error('HEIC reader did not load'));
      document.head.appendChild(s);
    });
    const wasm = fetch(LIBHEIF.wasm).then(r=>{
      if (!r.ok) throw new Error('HEIC reader did not load');
      return r.arrayBuffer();
    }).then(async buf=>{
      // crypto.subtle exists only on https (and localhost) pages.
      if (!(window.crypto && crypto.subtle)) throw new Error('HEIC reader needs an https page for its integrity check');
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-384', buf));
      if (btoa(String.fromCharCode(...digest)) !== LIBHEIF.wasmSha384) throw new Error('HEIC reader failed its integrity check');
      return buf;
    });
    libheifPromise = Promise.all([script, wasm]).then(([, wasmBinary])=>new Promise(res=>{
      // libheif fills in the object it is given and calls back when ready.
      const mod = { wasmBinary, onRuntimeInitialized: ()=>res(mod) };
      window.libheif(mod);
    })).catch(err=>{ libheifPromise = null; throw err; });
  }
  return libheifPromise;
}

function heicToJpeg(file){
  if (!heicJpegs.has(file)){
    const job = (async ()=>{
      const [lib, buf] = await Promise.all([loadLibheif(), file.arrayBuffer()]);
      const decoder = new lib.HeifDecoder();
      let images = [];
      try{
        images = decoder.decode(new Uint8Array(buf));
        const image = images.find(i=>i.is_primary()) || images[0];
        if (!image) throw new Error('not a HEIC photo');
        const w = image.get_width(), h = image.get_height();
        const full = document.createElement('canvas'); full.width = w; full.height = h;
        const fctx = full.getContext('2d');
        const pixels = fctx.createImageData(w, h);
        await new Promise((res, rej)=>image.display(pixels, d=>d ? res() : rej(new Error('HEIC decode failed'))));
        fctx.putImageData(pixels, 0, 0);
        const scale = Math.min(1, HEIC_MAX_SIDE / Math.max(w, h));
        let out = full;
        if (scale < 1){
          out = document.createElement('canvas');
          out.width = Math.round(w * scale); out.height = Math.round(h * scale);
          out.getContext('2d').drawImage(full, 0, 0, out.width, out.height);
        }
        const blob = await new Promise(res=>out.toBlob(res, 'image/jpeg', 0.92));
        if (!blob) throw new Error('HEIC decode failed');
        return new File([blob], String(file.name || 'photo').replace(/\.[^.]*$/, '') + '.jpg', { type:'image/jpeg', lastModified: file.lastModified || Date.now() });
      } finally {
        images.forEach(i=>i.free());
        if (decoder.decoder) lib.heif_context_free(decoder.decoder);
      }
    })();
    job.catch(()=>heicJpegs.delete(file));
    heicJpegs.set(file, job);
  }
  return heicJpegs.get(file);
}

/* A page photo never needs more: what reaches the server is at most 2600 px
   as JPEG (imageToBlob), and the largest of 127 real uploads was 5.8 MB
   (2026-10-09). A bigger file is refused here, before it is decoded. */
const MAX_PICK_BYTES = 10 * 1024 * 1024;

/* The upload box's notice for a photo that could not be used: a bold line,
   then what to do. Built from text nodes only. */
function showDzNotice(file, tooBig){
  const box = $('#dz-notice'); if (!box) return;
  box.textContent = '';
  const add = (tag, text, parent)=>{ const el = document.createElement(tag); el.textContent = text; (parent || box).appendChild(el); return el; };
  if (tooBig){
    add('strong', 'This file is ' + (file.size / 1048576).toFixed(1) + ' MB, over the 10 MB limit.');
    add('p', 'One page needs much less. A photo straight from the phone camera is usually 1 to 5 MB; for a PDF, save just the page with the writing.');
  } else if (isHeic(file)){
    add('strong', 'This is an iPhone photo (HEIC), and it could not be opened here.');
    add('p', 'Send a JPEG copy instead:');
    const ul = add('ul', '');
    add('li', 'On a Mac: open it in Preview, then File, Export, Format: JPEG.', ul);
    add('li', 'On an iPhone: Settings, Camera, Formats, Most Compatible. New photos are then JPEG.', ul);
  } else {
    add('strong', 'This file could not be opened as a photo.');
    add('p', 'Please choose a JPEG or PNG picture of the page.');
  }
  box.hidden = false;
}
function clearDzNotice(){ const box = $('#dz-notice'); if (box){ box.hidden = true; box.textContent = ''; } }

function setupUploadDrop(){
  const dz = $('#dropzone'), input = $('#file-input');
  dz.addEventListener('click', ()=>input.click());
  ['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.add('drag');}));
  ['dragleave','drop'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.remove('drag');}));
  dz.addEventListener('drop', e=>{ const f=e.dataTransfer.files[0]; handleSample(f); });
  input.addEventListener('change', e=>handleSample(e.target.files[0]));
  $('#dz-clear').addEventListener('click', e=>{ e.stopPropagation(); clearSample(); });
  // Buttons inside the dropzone must not also trigger its own click-to-browse.
  const choose = $('#choose-photo'), take = $('#take-photo'), camera = $('#camera-input'), trySample = $('#try-sample');
  if (choose) choose.addEventListener('click', e=>{ e.stopPropagation(); input.click(); });
  if (take && camera) take.addEventListener('click', e=>{ e.stopPropagation(); camera.click(); });
  // A camera photo goes through #file-input, so it is handled and stored like any other upload.
  if (camera) camera.addEventListener('change', ()=>{
    const f = camera.files && camera.files[0]; if (!f) return;
    const dt = new DataTransfer(); dt.items.add(f); input.files = dt.files;
    camera.value = '';
    input.dispatchEvent(new Event('change', { bubbles:true }));
  });
  if (trySample) trySample.addEventListener('click', e=>{ e.preventDefault(); e.stopPropagation(); loadBundledSample(); });
}

/* "Try a sample": our own photo, loaded straight into the preview. It never
   passes through #file-input, so it is not stored as a visitor's upload, and
   VAHINI_SAMPLE_RUN stops a printed sample report from being stored too. */
async function loadBundledSample(){
  if (serviceUp === false) return;
  setDzStatus('Loading the sample page…');
  try{
    const res = await fetch('assets/samples/handwriting-sample.jpg');
    if (!res.ok) throw new Error('sample unavailable');
    const blob = await res.blob();
    readImageFile(new File([blob], 'handwriting-sample.jpg', { type:'image/jpeg' }), (img, url)=>{
      window.VAHINI_SAMPLE_RUN = true;
      showSample(img, url);
      setDzStatus('Sample page loaded. Press Run analysis to see its report.');
    });
  }catch(_e){ setDzStatus('The sample page could not be loaded. Try your own photo.'); }
}

function setDzStatus(text){
  const s = $('#dz-status'); if (s) s.textContent = text || '';
}
/* Load the PDF reader only for PDF uploads; retry after a failed load. */
let pdfJsPromise = null;
function loadPdfJs(){
  if (!pdfJsPromise){
    pdfJsPromise = import('https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.min.mjs')
      .then(lib=>{
        lib.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.worker.min.mjs';
        return lib;
      }).catch(error=>{ pdfJsPromise = null; throw error; });
  }
  return pdfJsPromise;
}

/* Render page 1 only, and release the reader's worker after each upload. */
async function pdfFirstPageToImage(file){
  const lib = await loadPdfJs();
  const task = lib.getDocument({ data: await file.arrayBuffer(), isEvalSupported: false });
  try{
    const pdf = await task.promise;
    const page = await pdf.getPage(1);
    const viewport = page.getViewport({ scale: 2.0 });
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(viewport.width);
    canvas.height = Math.round(viewport.height);
    await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
    const url = canvas.toDataURL('image/png');
    const img = await new Promise((res, rej)=>{ const i=new Image(); i.onload=()=>res(i); i.onerror=rej; i.src=url; });
    return { img, url, pages: pdf.numPages };
  } finally {
    await task.destroy();
  }
}

function showSample(img, url){
  state.imageEl = img;
  $('#dz-preview').src = url; $('#dz-preview').style.display='block';
  $('#dz-clear').style.display='block';
  $('#dz-prompt').style.display='none';
  if (!window.VAHINI_SAMPLE_RUN) setDzStatus(photoWarning(img));
  applyServiceGate();
}

function handleSample(file){
  if (!file || serviceUp === false) return;
  window.VAHINI_SAMPLE_RUN = false;
  setDzStatus(''); clearDzNotice();
  if (file.size > MAX_PICK_BYTES){
    clearSample();
    showDzNotice(file, true);
    reportOutcome('too_big');
    return;
  }
  const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
  if (isPdf){
    setDzStatus('Reading PDF…');
    pdfFirstPageToImage(file).then(({ img, url, pages })=>{
      showSample(img, url);
      if (pages > 1) setDzStatus('PDF has ' + pages + ' pages: only page 1 is analysed.');
    }).catch(err=>{
      setDzStatus((err && err.message) ? err.message : 'Could not read this PDF.');
    });
    return;
  }
  const unreadable = ()=>{
    clearSample();
    showDzNotice(file);
    reportOutcome(isHeic(file) ? 'heic' : 'unreadable');
  };
  readImageFile(file, (img, url)=>showSample(img, url), ()=>{
    if (!isHeic(file)) return unreadable();
    setDzStatus('Converting your iPhone photo (HEIC) to JPEG…');
    heicToJpeg(file).then(jpeg=>readImageFile(jpeg, (img, url)=>{
      showSample(img, url);
      if (!$('#dz-status').textContent) setDzStatus('Converted your iPhone photo (HEIC) to JPEG. Press Run analysis.');
    }, unreadable)).catch(unreadable);
  });
}
function clearSample(){
  state.imageEl=null; $('#dz-preview').style.display='none'; $('#dz-clear').style.display='none';
  $('#dz-prompt').style.display='block'; $('#file-input').value='';
  window.VAHINI_SAMPLE_RUN = false; setDzStatus(''); clearDzNotice();
  applyServiceGate();
}

/* How each check ended, for vahinitech.com's Friday report
   (window.VahiniInsights.check in the site's vahini-insights.js, loaded by
   site.js). Failed checks never reach the persist API otherwise. Sample runs
   are not the visitor's page and are not reported; without the site script
   (self-hosted) this does nothing. */
function reportOutcome(outcome){
  if (!outcome || window.VAHINI_SAMPLE_RUN) return;
  try{ if (window.VahiniInsights && typeof VahiniInsights.check === 'function') VahiniInsights.check(outcome); }catch(_e){}
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

/* Developer instructions (docker compose, ppocr-server.py) only make sense on
   the machine running the server; visitors on vahinitech.com get plain words. */
function onLocalHost(){
  return ['localhost','127.0.0.1','[::1]'].includes(location.hostname);
}
function serverDownTips(devTips){
  return onLocalHost() ? devTips : [
    'Wait a minute, then try again',
    'If it keeps failing, tell us with the Feedback button',
  ];
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
      : (onLocalHost()
        ? 'Start it with docker compose up -d, or python backend/ppocr-server.py. It reconnects automatically.'
        : 'The analyser is busy or offline. It reconnects by itself, or press Retry now.');
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
/* Earlier checks, kept only in this browser's localStorage. A visitor who
   gives no name has one anonymous history. "Try a sample" runs are neither
   compared nor saved: they are not the visitor's handwriting. */
function loadHistory(name){
  if (window.VAHINI_SAMPLE_RUN) return null;
  try{ const h=JSON.parse(localStorage.getItem('vahini_history')||'[]');
    const key=(name||'').toLowerCase();
    const mine=h.filter(e=>(e.name||'').toLowerCase()===key);
    return mine.length? mine[mine.length-1] : null; }catch(e){ return null; }
}
function saveHistory(name, overall, sections, results){
  if (window.VAHINI_SAMPLE_RUN) return;
  try{ const h=JSON.parse(localStorage.getItem('vahini_history')||'[]');
    h.push({ name:name||'', date:new Date().toISOString().slice(0,10), overall,
      sections:(sections||[]).map(s=>({id:s.id,avg100:s.avg100})),
      factors:(results||[]).filter(f=>!f.unmeasured && Number.isFinite(f.score)).map(f=>({n:f.n,score:f.score})) });
    localStorage.setItem('vahini_history', JSON.stringify(h.slice(-60))); }catch(e){}
}

/* ---------- the pipeline ---------- */
const STEPS = [
  { id:'load', t:'Prepare your photo', d:'Resized in your browser for a quick upload' },
  { id:'ocr',  t:'Read and measure your page', d:'On Vahini\u2019s server: lines, words, letters and the 20 factors' },
  { id:'meas', t:'Review handwriting factors', d:'Scores for the skills in your report' },
  { id:'score',t:'Build your report', d:'Priorities, examples and practice' },
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
  reportOutcome(rej.outcome);
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
  if (rej.classification && window.VahiniReport){
    panel.insertAdjacentHTML('beforeend', VahiniReport.classificationPanels(rej.classification).join(''));
  }
  const retry = $('#reject-retry');
  if(retry) retry.addEventListener('click', ()=>{ clearSample(); go('upload'); });
}

/* The photo as uploaded: JPEG, long side capped at the server's own working
   size (VAHINI_OCR_MAX_SIDE, 2600), which it would resize to anyway. A full-
   size PNG was 1.2 MB for a 960x1280 photo and 6.1 MB for 3024x4032; the JPEG
   is 236 KB and 757 KB with the same overall scores (74/74, 73/73) and
   factor scores within 0.2 (measured on stage, 2026-10-07). */
const UPLOAD_MAX_SIDE = 2600;
function imageToBlob(img){
  const w0 = img.naturalWidth || img.width, h0 = img.naturalHeight || img.height;
  const s = Math.min(1, UPLOAD_MAX_SIDE / Math.max(w0, h0));
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(w0 * s));
  c.height = Math.max(1, Math.round(h0 * s));
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);  // transparent PNGs
  ctx.drawImage(img, 0, 0, c.width, c.height);
  return new Promise(res=>{
    if (!c.toBlob) return res(null);
    c.toBlob(b=>res(b || null), 'image/jpeg', 0.92);
  }).then(b=>b || VahiniOCR.canvasToBlob(c));
}

/* Warn, before upload, about the two photo problems that measurably change
   the scores. Calibrated on stage (2026-10-07): a blurred copy of the test
   page scored 68 or 49 against 73 and a quarter-size copy 53, while a dark
   copy still scored 73, so darkness is not flagged. Sharpness is the
   variance of the Laplacian on a grey copy 800 px on its long side, divided
   by that copy's own variance so a dark photo (lower contrast) does not
   read as blurred: 13 good photos scored 0.17-5.6, dark copies 0.18-0.35,
   the blurred copies that changed scores 0.020 and 0.002, and a blurred
   12 MP photo the server still read fine 0.049. */
const MIN_LONG_SIDE = 500, MIN_SHARPNESS = 0.04;
function photoQuality(img){
  const w0 = img.naturalWidth || img.width, h0 = img.naturalHeight || img.height;
  const s = Math.min(1, 800 / Math.max(w0, h0));
  const w = Math.max(3, Math.round(w0 * s)), h = Math.max(3, Math.round(h0 * s));
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, w, h);
  const d = ctx.getImageData(0, 0, w, h).data, g = new Float32Array(w * h);
  let total = 0;
  for (let i = 0, p = 0; p < g.length; i += 4, p++){ g[p] = 0.299*d[i] + 0.587*d[i+1] + 0.114*d[i+2]; total += g[p]; }
  const grey = total / g.length;
  let contrast = 0;
  for (let p = 0; p < g.length; p++){ const dv = g[p] - grey; contrast += dv * dv; }
  contrast /= g.length;
  let n = 0, mean = 0, m2 = 0;
  for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++){
    const p = y*w + x, lap = 4*g[p] - g[p-1] - g[p+1] - g[p-w] - g[p+w];
    n++; const delta = lap - mean; mean += delta / n; m2 += delta * (lap - mean);
  }
  return { longSide: Math.max(w0, h0), sharpness: (m2 / Math.max(1, n - 1)) / Math.max(1, contrast) };
}
function photoWarning(img){
  try{
    const q = photoQuality(img);
    if (q.longSide < MIN_LONG_SIDE) return 'This photo is small (' + q.longSide + ' px on its long side), which lowers the scores. A photo straight from the phone camera works best. You can still run it.';
    if (q.sharpness < MIN_SHARPNESS) return 'This photo looks blurry, which lowers the scores. Hold the phone still and tap the writing to focus, then take it again. You can still run it.';
  }catch(_e){ /* a check that cannot run never blocks the upload */ }
  return '';
}

/* Sample size for the cover / summary, derived from the server's recognised
   handwriting lines (the CV geometry itself lives server-side now). */
function sampleCounts(pyReport){
  const lines = Array.isArray(pyReport.hand_lines) ? pyReport.hand_lines : [];
  const text = pyReport.full_text || lines.map(l=>l.text).filter(Boolean).join('\n') || '';
  const nWords = (text.match(/\S+/g) || []).length;
  const nChars = text.replace(/\s+/g, '').length;
  return { nLines: Number.isInteger(pyReport.counts?.lines) ? pyReport.counts.lines : lines.length, nWords, nChars };
}

/* Server-only pipeline: the recognition server computes every report (OCR +
   the 20-factor analysis). The browser sends the image and renders the result;
   there is no in-browser scorer or offline fallback. */
async function runPipeline(){
  window.VAHINI_CHECK_FACTS = null;   // facts belong to one report; a new run starts with none
  keepStatus('');
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
      outcome: 'server_down',
      reason: 'Recognition server not reachable',
      detail: 'This analyser computes every report on the Vahini recognition server, which isn’t responding right now.',
      tips: serverDownTips([
        'Run the server: docker compose up -d (serves the app + OCR on the same origin)',
        'Or start it directly: python backend/ppocr-server.py',
        'Then reload this page and upload the photo again',
      ]),
    });
    return;
  }

  // 1 load: rasterise the upload and show it as the sample
  stepState('load','active');
  const blob = await imageToBlob(img);
  let detURL = await compressImageURL(img.src, 1100, 0.72);
  showProcStagePreview(img);
  stepState('load','done', `<b>${img.naturalWidth}×${img.naturalHeight}</b> photo, sent as ${Math.max(1, Math.round((blob && blob.size || 0)/1024))} KB`);

  // Grayscale, binarisation, segmentation, OCR and scoring all run on the
  // server inside the one request below; the page used to animate them with
  // ~2 s of fixed pauses before and after it.

  // 5 recognise + score (single server call returns OCR + the 20-factor analysis)
  // Measured on the deploy box: 4-6 s alone, up to ~20 s while others queue.
  stepState('ocr','active', 'On Vahini\u2019s server. This usually takes 5 to 20 seconds.');
  let pyReport = null;
  if (blob && window.VahiniOCR && typeof VahiniOCR.serverPythonReport === 'function'){
    pyReport = await VahiniOCR.serverPythonReport(blob, state.expected || '');
  }
  if (pyReport && pyReport.error_code === 'busy'){
    showReject({
      outcome: 'busy',
      reason: 'The analyser is busy right now',
      detail: 'Several people are checking their handwriting at the same moment, so yours could not start yet. Your photo is fine.',
      tips: [
        'Wait about ' + (pyReport.retry_after || 20) + ' seconds, then upload the photo again',
        'If it keeps happening, tell us with the Feedback button',
      ],
    });
    return;
  }
  if (pyReport && pyReport.error_code === 'no_handwriting'){
    // The server found text but ALL of it is printed. The analyser scores
    // pen handwriting only: refusing here (instead of scoring machine
    // type) is the whole credibility rule of the product.
    const n = Number(pyReport.printed_lines) || 0;
    showReject({
      outcome: 'no_handwriting',
      reason: 'No handwriting found on this page',
      classification: pyReport.text_classification,
      detail: n ? 'This page looks fully printed (' + n + ' printed regions detected). Printed text is shown below for identification and is not scored.'
        : 'No usable handwriting was detected. Upload a clear photo of a handwritten page.',
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
      outcome: 'server_down',
      reason: 'Recognition server not reachable',
      detail: 'This analyser computes every report on the Vahini recognition server, which isn’t responding right now'
        + (why && onLocalHost() ? ' (' + why + ')' : '') + (onLocalHost() ? '. Start the server and try again.' : '.'),
      tips: serverDownTips([
        'Run the server: docker compose up -d (serves the app + OCR on the same origin)',
        'Or start it directly: python backend/ppocr-server.py',
        'Then reload this page and upload the photo again',
      ]),
    });
    return;
  }
  const pyTiming = pyReport._timing || null;
  const vlResult = {
    document_context: pyReport.document_context || null,
    layout: pyReport.layout || null,
    regions: Array.isArray(pyReport.regions) ? pyReport.regions : [],
    factor_regions: pyReport.factor_regions || {},
    ambiguous_word_gaps: Array.isArray(pyReport.ambiguous_word_gaps) ? pyReport.ambiguous_word_gaps : [],
  };
  // Redraw the sample with the detected word boxes (orange) + baselines
  // (teal): the detection view shown on the report's first page.
  const boxedURL = drawDetectionOverlay(img, pyReport);
  if (boxedURL) detURL = boxedURL;
  const ctxTag = vlResult.document_context ? ' + context model' : '';
  stepState('ocr','done', 'Recognition server: <b>detect + recognise</b>' + ctxTag);

  // 6 measure: the analysis is already computed server-side
  stepState('meas','active');
  const analysis = pyReport.analysis;
  stepState('meas','done', `${analysis.results.length} factors in your report · overall <b>${analysis.overall}/100</b>`);

  // 7 render
  stepState('score','active');
  const counts = sampleCounts(pyReport);
  const recognizedText = pyReport.full_text
    || (Array.isArray(pyReport.hand_lines) ? pyReport.hand_lines.map(l=>l.text).filter(Boolean).join('\n') : '');
  const pipeline = { nLines:counts.nLines, nWords:counts.nWords, nChars:counts.nChars, ocrEngine:'server', vl:vlResult, timing: pyTiming };
  const crops = serverFactorCrops(vlResult);
  const history = loadHistory(state.intake.writerName);
  VahiniReport.render($('#report-host'), { intake:state.intake, analysis, expectedText:state.expected, recognizedText, ocrEngine:'server', detURL, pipeline, crops, letterFindings:null, history });
  saveHistory(state.intake.writerName, analysis.overallMeasured!=null?analysis.overallMeasured:analysis.overall, analysis.sections, analysis.results);
  stepState('score','done', `Report ready`);
  window.VAHINI_CHECK_FACTS = checkFacts(analysis, counts, img);
  keepIfAsked(blob, window.VAHINI_CHECK_FACTS);
  renderNextSteps(analysis);
  // A report the reader could not read any text for is the silent failure
  // found on 2026-10-07 (cv-fallback after ~19 s under memory pressure).
  reportOutcome(((analysis.recognition || {}).backend === 'cv-fallback') ? 'no_text' : 'report');
  go('report');
}

/* What a printed report is stored as on vahinitech.com (analyser.html
   persistReport; the store's own schema is vahini-web
   services/persist-api/lib/records.js): the scores and quality facts only.
   Numbers and short codes, no text, so no name or recognised words go with
   it; the photo's size and sharpness in bands, not exact values. */
function checkFacts(analysis, counts, img){
  const rec = analysis.recognition || {};
  let photo = { size:null, sharp:null };
  try{
    const q = photoQuality(img);
    photo = {
      size: q.longSide < 1000 ? 'small' : q.longSide < 2000 ? 'medium' : q.longSide < 3500 ? 'large' : 'very-large',
      sharp: q.sharpness < MIN_SHARPNESS ? 'blurry' : q.sharpness < 2 * MIN_SHARPNESS ? 'soft' : 'sharp',
    };
  }catch(_e){ /* the facts go without photo quality */ }
  const num = v=>(typeof v === 'number' && isFinite(v)) ? Math.round(v) : null;
  return {
    overall: num(analysis.overallMeasured != null ? analysis.overallMeasured : analysis.overall),
    tier: (analysis.access && analysis.access.tier) || null,
    factors: (analysis.results || []).map(f=>({ n:f.n, score: f.unmeasured ? null : num(f.score100), band: f.band || null, measured: !f.unmeasured })),
    priorities: (analysis.topWeak || []).slice(0, 3).map(f=>f.n),
    recognition: { backend: rec.backend || null, level: rec.level || null, confidence: num(rec.confidence_pct), handLines: num(rec.hand_lines), printedLines: num(rec.printed_lines) },
    words: num(counts && counts.nWords),
    photo,
  };
}

/* "Keep my pages" (vahinitech.com services/persist-api/lib/keepstore.js).
   Only when the box is ticked, and never for the sample: after the report,
   the same JPEG the analyser received and the check's facts go to the keep
   store, which mails the address a link. Nothing is kept until it is
   opened. The report itself is the same either way. */
const KEEP_EMAIL_RE = /^[^\s@<>()",;:\\]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,}$/;
function setupKeepPages(){
  const box = $('#keep-pages'), row = $('#keep-email-row');
  if (!box || !row) return;
  box.addEventListener('change', ()=>{ row.hidden = !box.checked; if (box.checked){ const i = $('#keep-email'); if (i) i.focus(); } });
}
function keepStatus(text, error){
  const s = $('#keep-status'); if (!s) return;
  s.textContent = text || ''; s.hidden = !text; s.classList.toggle('is-error', !!error);
}
async function keepIfAsked(blob, facts){
  const box = $('#keep-pages');
  if (!box || !box.checked || window.VAHINI_SAMPLE_RUN || !facts) return;
  const email = String(($('#keep-email') || {}).value || '').trim();
  if (!KEEP_EMAIL_RE.test(email)){ keepStatus('This page was not kept: the email address looks wrong. Run the check again to keep it.', true); return; }
  if (!blob || blob.type !== 'image/jpeg'){ keepStatus('This page could not be kept. Your report is below.', true); return; }
  const base = String(window.VAHINI_PERSIST_ENDPOINT || '/persist').replace(/\/+$/, '') + '/keep/';
  try{
    const start = await fetch(base + 'start', { method:'POST', headers:{ 'Content-Type':'application/json' }, body: JSON.stringify({ email, facts, consent:{ keep:true } }) });
    const s = await start.json().catch(()=>({}));
    if (!start.ok || !s.id) throw new Error(s.error || ('keep ' + start.status));
    const put = await fetch(base + 'image/' + s.id, { method:'POST', headers:{ 'Content-Type':'image/jpeg', 'X-Upload-Token': s.uploadToken }, body: blob });
    if (!put.ok) throw new Error('keep ' + put.status);
    keepStatus('Check your email: we sent a link to ' + email + '. Open it within 24 hours to keep this page; until then nothing is kept.');
  }catch(_e){
    keepStatus('This page could not be kept right now. Your report is below; try keeping it again later.', true);
  }
}

/* The "next step" block under a photo report (outside the report pages, not
   printed): the worksheet for the lowest measured score, a calendar reminder
   to check again in a week, and what the pen would add. */
function renderNextSteps(analysis){
  const box = $('#next-steps'); if (!box) return;
  const ws = window.VahiniWorksheets;
  const sheet = ws ? ws.recommend(analysis && analysis.results)[0] : null;
  const link = $('#ns-practice-link');
  if (sheet && link){
    $('#ns-practice-title').textContent = '1. Practise: ' + sheet.title;
    $('#ns-practice-text').textContent = 'Matched to your lowest score. Print the sheet and do one page a day for a week.';
    link.href = ws.base() + '/assets/worksheets/' + sheet.id + '.pdf';
    link.textContent = 'Download the worksheet (PDF)';
  }
  const when = new Date(Date.now() + 7*864e5);
  $('#ns-again-title').textContent = '2. Check again on ' + when.toLocaleDateString('en-GB', { day:'numeric', month:'long' });
  const cal = $('#ns-calendar');
  if (cal){
    if (cal.dataset.url) URL.revokeObjectURL(cal.dataset.url);
    const ymd = d=>d.toISOString().slice(0,10).replace(/-/g,'');
    const ics = ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Vahini//Handwriting check//EN','BEGIN:VEVENT',
      'UID:' + Date.now() + '-' + Math.random().toString(36).slice(2) + '@vahinitech.com',
      'DTSTAMP:' + new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d+/,''),
      'DTSTART;VALUE=DATE:' + ymd(when), 'DTEND;VALUE=DATE:' + ymd(new Date(when.getTime() + 864e5)),
      'SUMMARY:Check your handwriting again',
      'DESCRIPTION:Same pen\\, same paper. Upload a new photo and compare it with last week\'s report.',
      'URL:https://vahinitech.com/analyser/analyser.html','END:VEVENT','END:VCALENDAR'].join('\r\n');
    cal.dataset.url = URL.createObjectURL(new Blob([ics], { type:'text/calendar' }));
    cal.href = cal.dataset.url;
  }
  box.hidden = false;
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
      outcome: 'server_down',
      reason: 'Recognition server not reachable',
      detail: 'The pen report is computed on the Vahini recognition server, which isn’t responding right now.'
        + (onLocalHost() ? ' Start the server and capture again.' : ''),
      tips: serverDownTips([
        'Run the server: docker compose up -d',
        'Or start it directly: python backend/ppocr-server.py',
      ]),
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
    ambiguous_word_gaps: Array.isArray(pyReport.ambiguous_word_gaps) ? pyReport.ambiguous_word_gaps : [],
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
  saveHistory(state.intake.writerName, analysis.overall, analysis.sections, analysis.results);
  const ns = $('#next-steps'); if (ns) ns.hidden = true;
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

/* ---------- sample report page (sample-report.html) ----------
   The page carries no upload/process UI: it feeds the committed sample
   analysis (real build_analysis output on a synthetic practice page,
   regenerated by docs/examples/generate_examples.py) through the same
   renderer the live pipeline uses, so a visitor sees a full report
   before scanning anything. No detection photo or evidence crops exist
   for it: there is no uploaded page, and the renderer already shows its
   placeholder wording for both. */
function renderSampleReport(){
  const data = window.VAHINI_SAMPLE_REPORT;
  const host = $('#report-host');
  if (!host || !data || !data.analysis) return;
  collectIntake();
  const s = data.sample || {};
  const proExample = new URLSearchParams(location.search).get('example') === 'pro';
  const sampleAnalysis = proExample ? data.analysis : {...data.analysis, access:{tier:'free'}, results:data.analysis.results.filter(f=>[1,5,7,8,18].includes(f.n))};
  VahiniReport.render(host, {
    intake: state.intake,
    analysis: sampleAnalysis,
    expectedText: '',
    recognizedText: s.text || '',
    ocrEngine: 'server',
    // A real run of the fixture photo (docs/examples/generate_photo_sample.py):
    // the photo and the crops cut from it, as a visitor's report shows them.
    detURL: data.photo || null,
    pipeline: { nLines: s.nLines||0, nWords: s.nWords||0, nChars: s.nChars||0, ocrEngine: 'server' },
    crops: serverFactorCrops({ factor_regions: data.factor_regions || {} }),
    letterFindings: null,
    history: null,
  });
  const printBtn = $('#print-report');
  if (printBtn) printBtn.addEventListener('click', ()=>window.print());
}

/* ---------- case studies page (case-studies.html) ----------
   Three before/after practice arcs. The prose mirrors
   docs/case-studies.md; every number is read from
   window.VAHINI_CASE_STUDIES (real build_analysis output pairs emitted
   by docs/examples/generate_examples.py), never typed into the page, so
   the docs, the JSONs and this page cannot disagree. */
const CASE_STORIES = [
  {
    id:'case1', title:'Lines that slide down the page',
    persona:'A nine year old copies homework onto plain paper with no ruled lines. Every line starts level, then slowly slides down. Some lines slide more than others.',
    drill:'Four weeks of the drills from the report: trace along the line on ruled sheets (the tip for factor 7), and stop at the right edge to come back to the line (the tip for factor 11). Then scan again.',
    highlights:[7,11,12,17,10],
    note:'One habit moved five scores. Baseline, line straightness, up and down alignment, and slant all measure the angle of the writing, each in its own way. The margin score also rises, because the sliding lines were getting mixed into the left edge measurement. Nothing is hidden: you can follow exactly why each score moved.',
  },
  {
    id:'case2', title:'Words too close together',
    persona:'A twelve year old writes fast before the school bell. In some places the words touch each other. In other places there are big empty gaps. The computer cannot tell where one word ends and the next one starts, so it reads each line as broken pieces.',
    drill:'The drill from the report: write "word word" with one finger of space between the words, until every line is read as one whole line again.',
    highlights:[8,10,4,13,9,16,20],
    note:'Before practice, Margin Discipline shows 0.0. The margin is not really that bad. The computer measures the left edge of every piece it finds, and broken pieces start in the middle of the page. After practice the gaps are even, the computer reads full lines again, and the margin score comes back. Word Spacing is measured from the gaps inside each line, so it goes from 0.0 to 9.6 once the gaps are even.',
  },
  {
    id:'case3', title:'All letters the same size',
    persona:'An older student writes fast, small and flat. Tall letters like l and h barely rise up. Tails like g and y barely hang down. The pen presses hard and unevenly, and the left margin wanders.',
    drill:'The drills from the report: tall and short letter patterns (bl bl bl), writing inside a margin box, and lines with the same pen pressure. Then scan again.',
    highlights:[6,14,10,5],
    note:'Also look at what did not move. Loop closure, slant, baseline and word spacing stay in the same bands in both scans. A score only moves when its own measurement moves. One good or bad habit never pulls the other scores up or down.',
  },
];

/* Measured-evidence rows the narratives quote, read from the data. */
function caseEvidence(id, d){
  const rows = [];
  if (id==='case1' && d.before.drift && d.after.drift){
    rows.push(['How much the lines slide',
      d.before.drift.direction+' '+d.before.drift.degrees+'°',
      d.after.drift.direction+' '+d.after.drift.degrees+'°']);
  }
  if (id==='case3' && d.before.zones && d.after.zones){
    const t = Number(d.before.zones.targetReach) || 2.0;
    rows.push(['How tall the tall letters reach (goal '+t.toFixed(1)+'x)',
      d.before.zones.ascenderReach.toFixed(2)+'x', d.after.zones.ascenderReach.toFixed(2)+'x']);
    rows.push(['How deep the tails hang (goal '+t.toFixed(1)+'x)',
      d.before.zones.descenderReach.toFixed(2)+'x', d.after.zones.descenderReach.toFixed(2)+'x']);
    rows.push(['Letter size warnings',
      (d.before.zones.flags||[]).join(', ')||'none',
      (d.after.zones.flags||[]).join(', ')||'none']);
  }
  return rows;
}

function renderCaseStudies(){
  const data = window.VAHINI_CASE_STUDIES;
  const host = $('#case-studies-host');
  if (!host || !data) return;
  const esc = s => String(s==null?'':s).replace(/[&<>\"]/g, c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
  const byN = (r)=>{ const m={}; r.results.forEach(f=>{ m[f.n]=f; }); return m; };
  const frow = (f0, f1)=>{
    const delta = f1.score - f0.score;
    return `<div class="cs-frow">
      <span class="cs-fname">#${String(f0.n).padStart(2,'0')} ${esc(f0.name)}</span>
      <span class="cs-bar"><i class="bd-${f0.band}" style="width:${f0.score*10}%"></i></span>
      <b class="b-${f0.band}">${f0.score.toFixed(1)}</b>
      <span class="cs-arrow">→</span>
      <span class="cs-bar"><i class="bd-${f1.band}" style="width:${f1.score*10}%"></i></span>
      <b class="b-${f1.band}">${f1.score.toFixed(1)}</b>
      <em class="cs-delta${delta<0?' down':''}">${delta>=0?'+':''}${delta.toFixed(1)}</em>
    </div>`;
  };
  host.innerHTML = CASE_STORIES.map((c,i)=>{
    const d = data[c.id];
    if (!d) return '';
    const b = byN(d.before), a = byN(d.after);
    const overall0 = d.before.overallMeasured!=null ? d.before.overallMeasured : d.before.overall;
    const overall1 = d.after.overallMeasured!=null ? d.after.overallMeasured : d.after.overall;
    const evRows = caseEvidence(c.id, d).map(r=>
      `<div class="cs-evrow"><span>${esc(r[0])}</span><b>${esc(r[1])}</b><span class="cs-arrow">→</span><b>${esc(r[2])}</b></div>`).join('');
    const allRows = d.before.results.map(f0=>frow(f0, a[f0.n])).join('');
    return `<article class="cs-card">
      <div class="cs-head">
        <span class="cs-no">${String(i+1).padStart(2,'0')}</span>
        <div><h2>${esc(c.title)}</h2><p class="cs-persona">${esc(c.persona)}</p></div>
        <div class="cs-overall"><span class="cs-ov-label">Overall</span>
          <span class="cs-ov"><b>${overall0}</b><span class="cs-arrow">→</span><b class="cs-ov-after">${overall1}</b></span>
          <span class="cs-ov-delta">+${overall1-overall0}</span>
        </div>
      </div>
      <p class="cs-drill">${esc(c.drill)}</p>
      <div class="cs-frows">${c.highlights.map(n=>frow(b[n], a[n])).join('')}</div>
      ${evRows?`<div class="cs-evidence">${evRows}</div>`:''}
      <p class="cs-note">${esc(c.note)}</p>
      <details class="cs-all"><summary>Available factors, before → after</summary>
        <div class="cs-frows">${allRows}</div>
      </details>
    </article>`;
  }).join('');
}

/* ---------- wire up ---------- */
function init(){
  if (document.body.hasAttribute('data-sample-report')){ renderSampleReport(); return; }
  if (document.body.hasAttribute('data-case-studies')){ renderCaseStudies(); return; }
  setupUploadDrop(); setupKeepPages(); setupPassages(); setupLogo();
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
