/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Vahini — Share / QR (demo only)
   Turns a Google Drive share link into a scannable QR. Because uploading to
   Drive already requires internet, the QR image is fetched from a public QR
   service; the link is shown as a fallback if it can't load.
   ========================================================================= */
(function(){
'use strict';
function $(s){ return document.querySelector(s); }

function qrURL(data, size){
  size = size || 300;
  return 'https://api.qrserver.com/v1/create-qr-code/?size='+size+'x'+size+'&margin=8&data='+encodeURIComponent(data);
}

// Only http/https may ever reach a real DOM sink (href/src): a typed-in
// "javascript:" or "data:" URL would otherwise execute in the page when the
// link is opened. Returns '' for anything else, including unparseable input.
function safeHttpUrl(raw){
  try{
    const u = new URL(raw, location.href);
    return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : '';
  }catch(e){ return ''; }
}

function init(){
  const overlay = $('#share-overlay');
  if(!overlay) return;
  const open  = ()=>{ overlay.hidden=false; document.body.style.overflow='hidden'; };
  const close = ()=>{ overlay.hidden=true; document.body.style.overflow=''; };

  const sBtn = $('#share-report'); if(sBtn) sBtn.addEventListener('click', open);
  $('#share-close').addEventListener('click', close);
  overlay.addEventListener('click', e=>{ if(e.target===overlay) close(); });
  document.addEventListener('keydown', e=>{ if(e.key==='Escape' && !overlay.hidden) close(); });

  $('#share-save').addEventListener('click', ()=>window.print());

  function generate(){
    const raw = ($('#share-link').value||'').trim();
    const link = safeHttpUrl(raw);
    if(!link){ $('#share-link').focus(); return; }
    const img = $('#share-qr-img');
    img.onerror = ()=>{ img.alt='QR unavailable offline — share the link directly.'; };
    img.src = qrURL(link, 300);
    $('#share-open').href = link;
    $('#share-qr').hidden = false;
    $('#share-qr').scrollIntoView({ block:'nearest' });
  }
  $('#share-gen').addEventListener('click', generate);
  $('#share-link').addEventListener('keydown', e=>{ if(e.key==='Enter') generate(); });

  $('#share-copy').addEventListener('click', async ()=>{
    const link = ($('#share-link').value||'').trim(); if(!link) return;
    try{ await navigator.clipboard.writeText(link); const b=$('#share-copy'); const t=b.textContent; b.textContent='Copied!'; setTimeout(()=>b.textContent=t,1400); }
    catch(e){ $('#share-link').select(); }
  });
}
document.addEventListener('DOMContentLoaded', init);
})();
