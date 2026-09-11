// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
import {mkdir} from 'node:fs/promises';
export async function checkReportLayout(page){
  const results=[];
  const add=(ok,name,detail='')=>results.push({ok,name,detail});
  // Use the real report produced by the functional fixture, including long
  // evidence lines. Deliberately enlarge host typography to catch leakage.
  await page.evaluate(()=>{
    const host=document.getElementById('host');
    for(const child of [...document.body.children])if(child!==host)child.remove();
    host.style.cssText='display:block !important';
    document.body.style.cssText='margin:0;padding:0;font-size:20px';
    const sheet=document.createElement('style');sheet.textContent='body p { font-size:20px; }';document.head.append(sheet);
  });
  await page.evaluate(()=>document.fonts.ready);
  await mkdir('test-results/report-layout',{recursive:true});
  for(const mode of ['desktop','mobile','print']){
    await page.setViewportSize({width:mode==='mobile'?390:1200,height:1000});
    await page.emulateMedia({media:mode==='print'?'print':'screen'});
    if(mode==='print')await page.evaluate(()=>VahiniReport.fitPrintPages(document.getElementById('host')));
    const metrics=await page.evaluate(()=>{
      const pages=[...document.querySelectorAll('.free-report')];
      return {
        pages:pages.length,
        fonts:[...document.querySelectorAll('.priority-card > p,.factor-instruction')].map(e=>parseFloat(getComputedStyle(e).fontSize)),
        fits:pages.every(p=>p.scrollWidth<=p.clientWidth+1),
        heights:pages.map(p=>p.getBoundingClientRect().height),
        overlap:pages.some(p=>{
          const children=[...p.children];
          return children.some((c,i)=>i>0 && c.getBoundingClientRect().top < children[i-1].getBoundingClientRect().bottom-1);
        }),
        priorities:document.querySelectorAll('.priority-card').length,
        cardsIntact:[...document.querySelectorAll('.priority-card,.coaching-card,.practice-card')].every(c=>c.scrollHeight<=c.clientHeight+1),
        crops:[...document.querySelectorAll('.f-crop')].every(e=>getComputedStyle(e).objectFit==='contain'&&e.getBoundingClientRect().height>=70)
      };
    });
    add(metrics.pages===3 && metrics.priorities===3,mode+': all stages and three priorities remain visible');
    add(metrics.fonts.every(n=>n<=13),mode+': report typography is isolated from oversized host text');
    add(metrics.fits && !metrics.overlap && metrics.cardsIntact,mode+': no horizontal overflow, overlapping blocks or clipped cards',JSON.stringify(metrics.heights));
    add(metrics.crops,mode+': readable evidence images preserve complete crops');
    if(mode==='print')add(metrics.heights.every(h=>h<=1120), 'print: each standard report stage fits one A4 sheet',JSON.stringify(metrics.heights));
    await page.screenshot({path:'test-results/report-layout/'+mode+'.png',fullPage:true});
  }
  await page.pdf({path:'test-results/report-layout/report.pdf',format:'A4',printBackground:true});
  return results;
}
