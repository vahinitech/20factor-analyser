/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Beside Print / Save as PDF, on screen only (the toolbar never prints):
   - "Print in" (#report-lang): redraws the report and "Your progress" in
     the chosen language. Scores, crops, the page photo and the pictures do
     not change, only the words. The choice is kept in this browser.
   - "Share on WhatsApp" (#share-whatsapp): a short summary in the chosen
     language (VahiniReport.shareText: score, a strength, this week's plan,
     the first exercise and the link to the free check). On a phone it opens
     the share sheet, elsewhere https://wa.me/?text=. It never carries the
     writer's name, the photo, a crop or an id, and nothing goes to Vahini.
   docs/PRACTICE-FRAMEWORK.md sections 9 and 10.
   ========================================================================= */
(function (global) {
'use strict';
const doc = global.document;

function applyLanguage(lang){
  if (!global.VahiniI18n) return;
  global.VahiniI18n.setLanguage(lang);
  if (global.VahiniReport) global.VahiniReport.rerender();
  if (global.VahiniProgress) global.VahiniProgress.remount();
}

/* A phone (touch first) with a share sheet uses it; anything else, or a
   share sheet that fails, opens WhatsApp's own link. */
function waLink(text){ return 'https://wa.me/?text=' + encodeURIComponent(text); }
async function shareReport(){
  const text = global.VahiniReport && global.VahiniReport.shareText();
  if (!text) return '';
  const phone = typeof global.matchMedia === 'function' && global.matchMedia('(pointer: coarse)').matches;
  if (phone && global.navigator && typeof global.navigator.share === 'function'){
    try{ await global.navigator.share({ text }); return 'share'; }
    catch(err){ if (err && err.name === 'AbortError') return 'cancelled'; }
  }
  global.open(waLink(text), '_blank', 'noopener');
  return 'wa.me';
}

function init(){
  const pick = doc.getElementById('report-lang');
  if (pick && global.VahiniI18n){
    pick.value = global.VahiniI18n.language();
    pick.addEventListener('change', ()=>applyLanguage(pick.value));
  }
  const btn = doc.getElementById('share-whatsapp');
  if (btn) btn.addEventListener('click', ()=>{ shareReport(); });
}
if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', init);
else init();

global.VahiniReportShare = { applyLanguage, shareReport, waLink };
})(window);
