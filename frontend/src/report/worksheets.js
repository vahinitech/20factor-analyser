/* SPDX-License-Identifier: AGPL-3.0-only */
/* Original Vahini practice links. Scores and writing samples stay in the report. */
(function(global){
  'use strict';
  function recommend(results){
    const catalog=global.VahiniWorksheetCatalog||[];
    const valid=(Array.isArray(results)?results:[]).filter(f=>f && Number.isInteger(f.n) && Number.isFinite(f.score) && f.score>=0 && f.score<7 && !f.unmeasured && (f.conf==='measured'||f.imuMeasured===true));
    valid.sort((a,b)=>a.score-b.score||a.n-b.n);
    const out=[];
    for(const factor of valid){
      const sheet=catalog.find(w=>w.factors.includes(factor.n));
      if(sheet&&!out.some(w=>w.id===sheet.id))out.push(sheet);
      if(out.length===3)break;
    }
    return out;
  }
  function base(){return global.location.hostname==='stage.vahinitech.com'?'https://stage.vahinitech.com':'https://vahinitech.com';}
  function mount(host,results){
    const selected=recommend(results),section=document.createElement('aside');
    section.className='worksheet-downloads';section.setAttribute('data-html2canvas-ignore','true');
    section.style.cssText='max-width:210mm;margin:18px auto;padding:22px;background:#fff;border:1px solid #cbd6e5;border-radius:12px;color:#253348';
    const title=document.createElement('h2');title.textContent=selected.length?'Your practice worksheets':'Choose a practice worksheet';section.append(title);
    const intro=document.createElement('p');intro.textContent=selected.length?'Selected from lower measured factors in this report. Start with one sheet and compare your next sample.':'There are no suitable lower measured factors to select from. Browse the starter guide or choose an exercise yourself.';section.append(intro);
    for(const w of selected){const a=document.createElement('a');a.href=base()+'/assets/worksheets/'+w.id+'.pdf';a.textContent=w.title+' · PDF';a.download=w.id+'.pdf';a.target='_blank';a.rel='noopener';a.style.cssText='display:inline-block;margin:10px 18px 10px 0;color:#205f9e';section.append(a);}
    const browse=document.createElement('a');browse.href=base()+'/practice.html'+(selected.length?'#worksheets='+selected.map(w=>w.id).join(','):'');browse.textContent='Open my practice library →';browse.target='_blank';browse.rel='noopener';browse.style.display='block';section.append(browse);
    const privacy=document.createElement('small');privacy.textContent='Only worksheet choices are included in the link. Your name, scan and scores are not shared with the download page.';privacy.style.display='block';section.append(privacy);
    const style=document.createElement('style');style.textContent='@media print{.worksheet-downloads{display:none!important}}';section.append(style);host.prepend(section);
    return section;
  }
  global.VahiniWorksheets={recommend,mount};
})(window);
