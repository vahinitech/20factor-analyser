/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Beside the report, on screen only (the side panel never prints):
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
   docs/PRACTICE-FRAMEWORK.md sections 9 and 10.
   ========================================================================= */
(function (global) {
'use strict';
const doc = global.document;
const FILE_NAME = 'vahini-handwriting-report.pdf';
const DEFAULT_LIBS = ['scripts/vendor/html2canvas.min.js', 'scripts/vendor/jspdf.umd.min.js'];
const A4 = { w: 210, h: 297 };
/* Pixels per CSS pixel in the PDF images: 2 gives about 190 dots per
   inch on A4, sharp for print and small enough for WhatsApp. */
const SCALE = 2;

function tr(){
  const i18n = global.VahiniI18n;
  return i18n ? i18n.translator(i18n.language()) : (id=>id);
}
/* The side panel's own words follow "Print in" too. */
function translatePanel(){
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
  a.href = URL.createObjectURL(blob); a.download = FILE_NAME;
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
      file = new File([blob], FILE_NAME, { type: 'application/pdf' });
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

function init(){
  const pick = doc.getElementById('report-lang');
  if (pick && global.VahiniI18n){
    pick.value = global.VahiniI18n.language();
    pick.addEventListener('change', ()=>applyLanguage(pick.value));
  }
  const btn = doc.getElementById('share-pdf');
  if (btn) btn.addEventListener('click', ()=>{ sharePDF(); });
  translatePanel();
}
if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', init);
else init();

global.VahiniReportShare = { applyLanguage, sharePDF, makePDF, loadLibs, waLink, FILE_NAME, invalidate: ()=>{ ready = null; } };
})(window);
