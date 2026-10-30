/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Beside the report, on screen only (the side panel never prints):
   - "I am" and "Report in" above the check (#who-bar, owner, 2026-10-25):
     a student gets the student view; a parent or guardian (the default), a
     teacher or someone checking their own writing gets the parent report.
     "Report in" and "Print in" are one choice. Both stay in this browser
     and are never sent.
   - Under the report, "Student view" or "Parent report" (#view-switch)
     redraws the other view of the same check, with no new scan.
   - "Print in" (#report-lang): redraws the report and "Your progress" in
     the chosen language. Scores, crops, the page photo and the pictures do
     not change, only the words. The choice is kept in this browser.
   - "Share PDF on WhatsApp" (#share-pdf): makes the two report pages into
     a two-page A4 PDF in this browser and shares the file. The PDF holds
     what the report shows, in the chosen language (with the name the
     family typed, if any); it is made here and nothing goes to Vahini.
     html2canvas and jsPDF (MIT, scripts/vendor/, sources.json there) are
     loaded only when the button is pressed: their URLs come from the
     page's <template id="pdf-libs">, which the build stamps like every
     other asset. A phone that can share files (Web Share Level 2) gets the
     share sheet, where the family picks WhatsApp; anything else saves the
     PDF and opens https://wa.me/ with a note to attach it.
   - The PDF also carries, for the Pro comparison of two PDFs (owner,
     2026-10-16), data nobody sees on the printed pages: the stored
     report's read-only receipt (backend/server/report_store.py) in the PDF's XMP
     metadata, which opens the record only through the Pro comparison
     (POST /api/v2/compare) and can never renew or delete it; the full
     token stays in this browser's saved checks (progress.js);
     and the page photo, at most 1600 px and re-encoded so no camera data
     goes with it, as an embedded file. The vendored jsPDF has XMP
     (addMetadata) but no attachments, so the file is written through the
     same object hooks its metadata plugin uses. Neither names the child.
   docs/10-practice-framework.md sections 9 and 10.
   ========================================================================= */
(function (global) {
'use strict';
const doc = global.document;
/* The file carries the brand, never the child (owner, 2026-10-11): the
   same name and metadata in every language, and no name the family typed
   in either. */
const FILE_PREFIX = 'Vahini-handwriting-snapshot-';
function fileName(date){
  const d = date || new Date();
  const two = n=>String(n).padStart(2, '0');
  return `${FILE_PREFIX}${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}.pdf`;
}
const PDF_META = { title: 'Vahini handwriting snapshot', author: 'Vahini Technologies · vahinitech.com', creator: 'Vahini Technologies · vahinitech.com' };
const SUBJECT = { free: 'Free handwriting review', pro: 'Handwriting review' };
const DEFAULT_LIBS = ['scripts/vendor/html2canvas.min.js', 'scripts/vendor/jspdf.umd.min.js'];
const A4 = { w: 210, h: 297 };
/* Pixels per CSS pixel in the PDF images: 2 gives about 190 dots per
   inch on A4, sharp for print and small enough for WhatsApp. */
const SCALE = 2;

/* What the Pro comparison reads back (20factor-analyser-pro web/compare.html).
   A new field is a new namespace version. */
const EMBED = { ns: 'https://vahinitech.com/ns/report-pdf/1/', photo: 'vahini-page.jpg', maxSide: 1600, quality: 0.85 };
const RECEIPT_ID = /^[0-9a-f]{32}$/;
const RECEIPT_TOKEN = /^[A-Za-z0-9_-]{43}$/;
/* The check the report on screen came from: its receipt and a promise of
   the photo as JPEG bytes. Set by app.js after each check; never a sample. */
let check = null;
function photoBytes(image){
  const w0 = image.naturalWidth || image.width, h0 = image.naturalHeight || image.height;
  if (!(w0 > 0 && h0 > 0)) return Promise.resolve(null);
  const s = Math.min(1, EMBED.maxSide / Math.max(w0, h0));
  const c = doc.createElement('canvas');
  c.width = Math.max(1, Math.round(w0 * s));
  c.height = Math.max(1, Math.round(h0 * s));
  const g = c.getContext('2d');
  g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height);
  g.drawImage(image, 0, 0, c.width, c.height);
  return new Promise(res=>{
    if (!c.toBlob) return res(null);
    c.toBlob(b=>res(b || null), 'image/jpeg', EMBED.quality);
  }).then(b=>b ? b.arrayBuffer() : null).then(buf=>buf ? new Uint8Array(buf) : null).catch(()=>null);
}
function setCheck(c){
  ready = null;
  if (!c){ check = null; return; }
  const r = c.receipt;
  check = {
    /* The read-only token, never the full one: whoever the PDF reaches
       must not be able to delete the family's record. No read token, no
       receipt in the PDF. */
    receipt: r && RECEIPT_ID.test(r.id) && RECEIPT_TOKEN.test(r.read_token) ? { id: r.id, token: r.read_token } : null,
    photo: c.image ? photoBytes(c.image) : Promise.resolve(null),
  };
}
function xmlEsc(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c])); }
/* The receipt as XMP: the id, the token and the photo's file name, nothing
   else. */
function receiptXMP(receipt, photo){
  const v = (k, val)=>`<vahini:${k}>${xmlEsc(val)}</vahini:${k}>`;
  return '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    + `<rdf:Description rdf:about="" xmlns:vahini="${EMBED.ns}">`
    + (receipt ? v('receiptId', receipt.id) + v('receiptToken', receipt.token) : '')
    + (photo ? v('photo', EMBED.photo) : '')
    + '</rdf:Description></rdf:RDF></x:xmpmeta>';
}
function binary(bytes){
  let out = '';
  for (let i = 0; i < bytes.length; i += 0x8000) out += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return out;
}
/* A PDF embedded file (ISO 32000-1, 7.11.4): a stream, its file
   specification and the catalogue's EmbeddedFiles name tree. A viewer
   lists it as an attachment; it is not a page and never prints. */
function attachFile(pdf, name, bytes, mime){
  const data = binary(bytes);
  const out = pdf.internal.write;
  let spec = 0;
  pdf.internal.events.subscribe('postPutResources', ()=>{
    const file = pdf.internal.newObject();
    out(`<< /Type /EmbeddedFile /Subtype /${mime.replace('/', '#2F')} /Params << /Size ${data.length} >> /Length ${data.length} >>`);
    out('stream'); out(data); out('endstream'); out('endobj');
    spec = pdf.internal.newObject();
    out(`<< /Type /Filespec /F (${name}) /UF (${name}) /AFRelationship /Data /EF << /F ${file} 0 R >> >>`);
    out('endobj');
  });
  pdf.internal.events.subscribe('putCatalog', ()=>{
    if (spec) out(`/Names << /EmbeddedFiles << /Names [(${name}) ${spec} 0 R] >> >>`);
  });
}
async function embedCheck(pdf){
  if (!check) return;
  const photo = await check.photo;
  if (!check.receipt && !photo) return;
  pdf.addMetadata(receiptXMP(check.receipt, photo), true);
  if (photo) attachFile(pdf, EMBED.photo, photo, 'image/jpeg');
}

function tr(){
  const i18n = global.VahiniI18n;
  return i18n ? i18n.translator(i18n.language()) : (id=>id);
}
/* The side panel's own words follow "Print in" too. */
function translatePanel(){
  switchLabel();
  const t = tr();
  doc.querySelectorAll('[data-i18n]').forEach(el=>{
    const id = el.getAttribute('data-i18n');
    if (t.has && t.has(id)) el.textContent = t(id);
  });
}
function applyLanguage(lang){
  if (!global.VahiniI18n) return;
  global.VahiniI18n.setLanguage(lang);
  ready = null;
  if (global.VahiniReport) global.VahiniReport.rerender();
  if (global.VahiniProgress) global.VahiniProgress.remount();
  translatePanel();
}

/* ---- loading the PDF libraries, once, on the first press --------------- */
function libURLs(){
  const tpl = doc.getElementById('pdf-libs');
  const list = tpl && tpl.content ? [...tpl.content.querySelectorAll('script[src]')].map(s=>s.getAttribute('src')) : [];
  return list.length ? list : DEFAULT_LIBS;
}
const loading = {};
function loadScript(src){
  if (!loading[src]) loading[src] = new Promise((resolve, reject)=>{
    const s = doc.createElement('script');
    s.src = src; s.async = false;
    s.onload = ()=>resolve();
    s.onerror = ()=>{ delete loading[src]; reject(new Error('could not load ' + src)); };
    doc.head.appendChild(s);
  });
  return loading[src];
}
async function loadLibs(){
  for (const src of libURLs()) await loadScript(src);
  const jsPDF = global.jspdf && global.jspdf.jsPDF;
  if (typeof global.html2canvas !== 'function' || typeof jsPDF !== 'function') throw new Error('PDF libraries missing');
  return { html2canvas: global.html2canvas, jsPDF };
}

/* html2canvas draws an inline SVG as a picture of its markup, without the
   page's stylesheets, so the theme colours set by class would be lost.
   In its copy of the page, write each SVG part's computed paint into its
   own style first. */
const SVG_PAINT = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity', 'fill-opacity', 'stroke-opacity', 'color',
  'font-family', 'font-size', 'font-weight'];
function inlineSvgPaint(clone){
  const view = clone.defaultView || global;
  clone.querySelectorAll('svg, svg *').forEach(el=>{
    const cs = view.getComputedStyle(el);
    el.setAttribute('style', SVG_PAINT.map(p=>`${p}:${cs.getPropertyValue(p)}`).join(';'));
  });
}
/* The two report pages as one A4 PDF (a Blob). */
async function makePDF(host){
  const { html2canvas, jsPDF } = await loadLibs();
  if (doc.fonts && doc.fonts.ready) await doc.fonts.ready;
  const pages = [...host.querySelectorAll('section.page')];
  if (!pages.length) throw new Error('no report');
  const pdf = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait', compress: true });
  pdf.setProperties({ ...PDF_META, subject: host.querySelector('.practice-pro') ? SUBJECT.pro : SUBJECT.free });
  doc.documentElement.classList.add('pdf-busy');
  try{
  for (let i = 0; i < pages.length; i++){
    const canvas = await html2canvas(pages[i], {
      scale: SCALE, useCORS: true, logging: false, backgroundColor: null,
      // A phone lays the page out narrow; the PDF uses the A4 layout.
      windowWidth: 1280,
      onclone: clone=>{
        clone.documentElement.classList.add('pdf-capture');
        inlineSvgPaint(clone);
      },
    });
    const ratio = canvas.height / canvas.width;
    let w = A4.w, h = A4.w * ratio;
    if (h > A4.h){ h = A4.h; w = A4.h / ratio; }
    if (i) pdf.addPage('a4', 'portrait');
    pdf.addImage(canvas.toDataURL('image/jpeg', 0.9), 'JPEG', (A4.w - w) / 2, 0, w, h, undefined, 'FAST');
  }
  } finally { doc.documentElement.classList.remove('pdf-busy'); }
  await embedCheck(pdf);
  return pdf.output('blob');
}

/* ---- sharing -------------------------------------------------------------*/
function waLink(text){ return 'https://wa.me/?text=' + encodeURIComponent(text); }
function status(html){
  const s = doc.getElementById('share-status');
  if (s){ s.innerHTML = html || ''; s.hidden = !html; }
}
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function save(blob){
  const a = doc.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = blob.name || fileName();
  doc.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href), 4000);
}
/* A PDF made but not yet shared: the share sheet needs a fresh tap when
   making the file took longer than the browser's tap allowance. */
let ready = null;
let busy = false;
async function shareFile(file){
  const nav = global.navigator;
  if (!(nav && typeof nav.canShare === 'function' && typeof nav.share === 'function' && nav.canShare({ files: [file] }))) return 'unsupported';
  try{ await nav.share({ files: [file], title: tr()('side.title') }); return 'share'; }
  catch(err){
    if (err && err.name === 'AbortError') return 'cancelled';
    if (err && err.name === 'NotAllowedError') return 'again';
    return 'unsupported';
  }
}
async function sharePDF(){
  if (busy) return 'busy';
  const t = tr();
  const host = doc.getElementById('report-host');
  if (!host) return 'no-report';
  busy = true;
  try{
    let file = ready;
    if (!file){
      status(esc(t('side.making')));
      let blob;
      try{ blob = await makePDF(host); }
      catch(_e){ status(esc(t('side.nopdf'))); return 'no-pdf'; }
      file = new File([blob], fileName(), { type: 'application/pdf' });
    }
    const shared = await shareFile(file);
    if (shared === 'again'){ ready = file; status(esc(t('side.ready'))); return 'again'; }
    ready = null;
    if (shared === 'share' || shared === 'cancelled'){ status(''); return shared; }
    save(file);
    const link = waLink(t('share.note'));
    status(`${esc(t('side.saved'))} <a href="${esc(link)}" target="_blank" rel="noopener">${esc(t('side.open'))}</a>`);
    global.open(link, '_blank', 'noopener');
    return 'download';
  } finally { busy = false; }
}

/* "I am" (owner, 2026-10-25). Kept in this browser (localStorage) so the
   next check starts the same way; ?for=student on the address still opens
   the student view. Never sent with a check. */
const WHO_KEY = 'vahini_check_who';
const WHO = ['parent', 'student', 'teacher', 'self'];
/* Who is checking (DPDP Rules, rule 10). Nothing is chosen until the
   visitor chooses. A grown-up's earlier answer in this browser comes back;
   "Student" never does, so a child on a family device answers again, and
   ?for=student only starts on Student, with the adult's tick still to do. */
const ADULT = ['parent', 'teacher', 'self'];
function savedWho(){
  try{ if (new URLSearchParams(global.location.search).get('for') === 'student') return 'student'; }catch(_e){ /* no address */ }
  let v = null;
  try{ v = global.localStorage.getItem(WHO_KEY); }catch(_e){ /* blocked */ }
  return ADULT.includes(v) ? v : null;
}
function chosenWho(){
  const r = doc.querySelector('input[name="check-who"]:checked');
  return r && WHO.includes(r.value) ? r.value : null;
}
function adultSaysYes(){ const t = doc.getElementById('who-adult'); return !!(t && t.checked); }
function whoError(text){
  const e = doc.getElementById('who-error'), bar = doc.getElementById('who-bar');
  if (e){ e.textContent = text || ''; e.hidden = !text; }
  if (bar) bar.classList.toggle('is-missing', !!text);
}
/* The one word sent with the photo, or null while the answer is missing. */
function whoForCheck(){
  if (global.VAHINI_SAMPLE_RUN) return 'sample';
  const who = chosenWho();
  if (!who || (who === 'student' && !adultSaysYes())) return null;
  return who;
}
/* Before a check: true when the answer is missing, after saying what to do. */
function whoMissing(){
  if (whoForCheck()) { whoError(''); return false; }
  const who = chosenWho();
  whoError(who === 'student'
    ? 'Ask a parent, guardian or teacher to say yes, then tick the box.'
    : 'Choose who is checking this page first.');
  const focus = who === 'student' ? doc.getElementById('who-adult') : doc.querySelector('input[name="check-who"]');
  const bar = doc.getElementById('who-bar');
  if (bar && bar.scrollIntoView) bar.scrollIntoView({ block:'center' });
  if (focus) focus.focus();
  return true;
}
function showAdultTick(who){
  const row = doc.getElementById('who-adult-row');
  if (row) row.hidden = who !== 'student';
  if (who !== 'student'){ const t = doc.getElementById('who-adult'); if (t) t.checked = false; }
}
function viewFor(who){ return who === 'student' ? 'student' : 'parent'; }
function switchLabel(){
  const btn = doc.getElementById('view-switch');
  if (!btn || !global.VahiniReport) return;
  const id = global.VahiniReport.audience() === 'student' ? 'side.view.parent' : 'side.view.student';
  btn.setAttribute('data-i18n', id);
  const t = tr();
  btn.textContent = t(id);
}
function wireWho(){
  const R = global.VahiniReport;
  if (!R || !R.setAudience) return;
  const radios = [...doc.querySelectorAll('input[name="check-who"]')];
  const who = savedWho();
  radios.forEach(r=>{
    r.checked = r.value === who;
    r.addEventListener('change', ()=>{
      if (!r.checked) return;
      try{
        if (ADULT.includes(r.value)) global.localStorage.setItem(WHO_KEY, r.value);
        else global.localStorage.removeItem(WHO_KEY);
      }catch(_e){ /* this visit only */ }
      showAdultTick(r.value);
      whoError('');
      R.setAudience(viewFor(r.value));
      switchLabel();
    });
  });
  showAdultTick(who);
  const tick = doc.getElementById('who-adult');
  if (tick) tick.addEventListener('change', ()=>{ if (tick.checked) whoError(''); });
  if (radios.length) R.setAudience(viewFor(who || 'parent'));
  const btn = doc.getElementById('view-switch');
  if (btn) btn.addEventListener('click', ()=>{
    R.setAudience(R.audience() === 'student' ? 'parent' : 'student');
    R.rerender();
    ready = null;
    switchLabel();
  });
  switchLabel();
}

function init(){
  const pick = doc.getElementById('report-lang');
  if (pick && global.VahiniI18n){
    pick.value = global.VahiniI18n.language();
    pick.addEventListener('change', ()=>applyLanguage(pick.value));
  }
  wireWho();
  const topLang = doc.getElementById('check-lang');
  if (topLang && global.VahiniI18n){
    topLang.value = global.VahiniI18n.language();
    topLang.addEventListener('change', ()=>{ if (pick) pick.value = topLang.value; applyLanguage(topLang.value); });
    if (pick) pick.addEventListener('change', ()=>{ topLang.value = pick.value; });
  }
  const btn = doc.getElementById('share-pdf');
  if (btn) btn.addEventListener('click', ()=>{ sharePDF(); });
  translatePanel();
}
if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', init);
else init();

global.VahiniWho = { forCheck: whoForCheck, missing: whoMissing };
global.VahiniReportShare = { applyLanguage, sharePDF, makePDF, loadLibs, waLink, fileName, setCheck, PDF_META, SUBJECT, EMBED, invalidate: ()=>{ ready = null; } };
})(window);
