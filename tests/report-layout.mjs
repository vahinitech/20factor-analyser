// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
import {mkdir} from 'node:fs/promises';
import { useDesign } from './design-route.mjs';
export { useDesign };
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
  await page.evaluate(()=>Promise.all(['600 17px Spectral','400 12px "Hanken Grotesk"','500 20px Caveat','400 20px "Edu SA Beginner"'].map(font=>document.fonts.load(font))));
  const loaded=await page.evaluate(()=>[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family.replace(/"/g,'')));
  add(['Spectral','Hanken Grotesk','Caveat','Edu SA Beginner'].every(name=>loaded.includes(name)), 'All four report font families load from local assets');
  // The paper is the website theme's (--v-paper, #FDFCF6).
  add(await page.locator('.free-report').first().evaluate(e=>getComputedStyle(e).backgroundColor)==='rgb(253, 252, 246)', 'Paper background is the theme paper');
  await mkdir('test-results/report-layout',{recursive:true});
  for(const mode of ['desktop','mobile','print']){
    await page.setViewportSize({width:mode==='mobile'?390:1200,height:1000});
    await page.emulateMedia({media:mode==='print'?'print':'screen'});
    if(mode==='print')await page.evaluate(()=>VahiniReport.fitPrintPages(document.getElementById('host')));
    const metrics=await page.evaluate(()=>{
      const pages=[...document.querySelectorAll('.free-report')];
      return {
        pages:pages.length,
        fonts:[...document.querySelectorAll('.sn-start p:not(.sn-meta),.sn-steps li')].map(e=>parseFloat(getComputedStyle(e).fontSize)),
        fits:pages.every(p=>p.scrollWidth<=p.clientWidth+1),
        heights:pages.map(p=>p.getBoundingClientRect().height),
        overlap:pages.some(p=>{
          // Screen-only blocks (page 1's buttons) take no room in print.
          const children=[...p.children].filter(c=>c.getClientRects().length>0);
          return children.some((c,i)=>i>0 && c.getBoundingClientRect().top < children[i-1].getBoundingClientRect().bottom-1);
        }),
        priorities:document.querySelectorAll('.sn-look').length+document.querySelectorAll('.sn-start').length,
        cardsIntact:[...document.querySelectorAll('.sn-look,.sn-start,.sn-keep,.coaching-card')].every(c=>c.scrollHeight<=c.clientHeight+1),
        crops:[...document.querySelectorAll('.sn-look-crop')].every(e=>getComputedStyle(e).objectFit==='contain'&&e.getBoundingClientRect().height>=45)
      };
    });
    add(metrics.pages===2 && metrics.priorities===3,mode+': both pages, the place to start and the two parts to look at remain visible');
    add(metrics.fonts.length>0 && metrics.fonts.every(n=>n>=13 && n<=15),mode+': instructions keep their readable type, whatever the host page sets',JSON.stringify(metrics.fonts));
    add(metrics.fits && !metrics.overlap && metrics.cardsIntact,mode+': no horizontal overflow, overlapping blocks or clipped cards',JSON.stringify(metrics.heights));
    add(metrics.crops,mode+': readable evidence images preserve complete crops');
    if(mode==='print')add(metrics.heights.every(h=>h<=1120), 'print: each standard report stage fits one A4 sheet',JSON.stringify(metrics.heights));
    await page.screenshot({path:'test-results/report-layout/'+mode+'.png',fullPage:true});
  }
  await page.pdf({path:'test-results/report-layout/report.pdf',format:'A4',printBackground:true});
  // Count the printed pages, not only each sheet's height. Heights passed
  // while stage printed the free report as 3-4 pages with blank ones between
  // (2026-10-07): a real photo's text runs longer than this fixture's.
  const pdfPages=async()=>((await page.pdf({format:'A4',printBackground:true})).toString('latin1').match(/\/Type\s*\/Page[^s]/g)||[]).length;
  await page.emulateMedia({media:'print'});
  await page.evaluate(()=>VahiniReport.fitPrintPages(document.getElementById('host')));
  add(await pdfPages()===2,'print: the free report prints on exactly two A4 pages');
  // The heights stage measured before fitting: sheet 1 filled the sheet to
  // the pixel, sheet 2 was 1335px.
  const stretched=await page.evaluate(()=>{
    const sheets=[...document.querySelectorAll('.free-report')];
    sheets.forEach(p=>{p.style.zoom='';p.style.width='';p.style.minHeight='';});
    [1119,1335].forEach((target,i)=>{const pad=document.createElement('div');pad.className='layout-stretch';pad.style.height=Math.max(0,target-sheets[i].scrollHeight)+'px';sheets[i].append(pad);});
    const natural=sheets.map(p=>p.scrollHeight);
    VahiniReport.fitPrintPages(document.getElementById('host'));
    return natural;
  });
  add(await pdfPages()===2,'print: sheets as long as a real photo makes them still print on two pages',JSON.stringify(stretched));
  await page.evaluate(()=>document.querySelectorAll('.layout-stretch').forEach(e=>e.remove()));
  return results;
}

/* Practice report (owner approval 2026-10-11, #122): Free and Pro both
   print on exactly two A4 sheets in the longest case (three skills, a
   spelling row, Pro's two exercises and two tips each, the other-skills box
   and all four pictures), with and without the host's picture map, and
   when the sheets run as long as a real photo makes them. */
export const REPORT_ART = { cheer:'/frontend/assets/vahini-logo.png', tip:'/frontend/assets/vahini-logo.png', encourage:'/frontend/assets/vahini-logo.png' };
export async function renderLongest(page, pro){
  await page.evaluate(pro=>{
    const d=window.VAHINI_SAMPLE_REPORT;
    window.VahiniCraft={...window.VahiniCraft,checkSpelling:t=>t?[{word:'recieve',suggestion:'receive',context:'I recieve it'}]:[]};
    const recognition={...(d.analysis.recognition||{}),level:'high'};
    const analysis=pro?{...d.analysis,recognition}:{...d.analysis,access:{tier:'free'},recognition,results:d.analysis.results.filter(f=>[1,5,7,8,18].includes(f.n))};
    const crops={};
    Object.entries(d.factor_regions||{}).forEach(([k,v])=>{crops[k]=v;});
    VahiniReport.render(document.getElementById('report-host'),{analysis,intake:{},recognizedText:'I recieve it',crops,detURL:d.photo,history:null});
  },pro);
  await page.evaluate(()=>document.fonts.ready);
}
export async function checkPracticePrint(browser, baseUrl){
  const results=[];
  const add=(ok,name,detail='')=>results.push({ok,name,detail});
  const pdfPages=async page=>((await page.pdf({format:'A4',printBackground:true})).toString('latin1').match(/\/Type\s*\/Page[^s]/g)||[]).length;
  for(const pro of [false,true]){
    for(const art of [true,false]){
      const label=`${pro?'Pro':'Free'}, pictures ${art?'on':'off'}`;
      const page=await browser.newPage({viewport:{width:1200,height:1000}});
      await useDesign(page);
      if(art)await page.addInitScript(a=>{window.VAHINI_REPORT_ART=a;},REPORT_ART);
      await page.goto(baseUrl+'/frontend/sample-report.html'+(pro?'?example=pro':''),{waitUntil:'load'});
      await page.waitForSelector('#report-host .practice-page');
      await renderLongest(page,pro);
      const shape=await page.evaluate(()=>({
        rows:document.querySelectorAll('.practice-row').length,
        spelling:!!document.querySelector('.practice-row.spelling-row'),
        others:!!document.querySelector('.other-skills'),
        art:[...new Set([...document.querySelectorAll('#report-host img.rp-art')].map(i=>i.dataset.art))].sort().join(','),
        alt:[...document.querySelectorAll('#report-host img.rp-art')].every(i=>i.getAttribute('alt')===''),
        maxEx:Math.max(...[...document.querySelectorAll('.practice-row')].map(r=>r.querySelectorAll('[data-exercise]').length)),
        maxTips:Math.max(...[...document.querySelectorAll('.practice-row')].map(r=>r.querySelectorAll('.pr-tip').length)),
      }));
      add(shape.rows===4&&shape.spelling&&shape.others&&shape.maxEx===(pro?2:1)&&shape.maxTips===(pro?2:1),label+': longest case has three skills, spelling and the other skills',JSON.stringify(shape));
      add(art?shape.art==='cheer,encourage,tip'&&shape.alt:shape.art==='',label+': pictures come only from the host map',JSON.stringify(shape));
      await page.emulateMedia({media:'print'});
      add(await pdfPages(page)===2,label+': prints on exactly two A4 pages');
      // Page 2's left column (why, win, More) never makes a row taller than
      // its practice: printed, every row's skill side fits beside it.
      const cols=await page.evaluate(()=>{
        VahiniReport.fitPrintPages(document.getElementById('report-host'));
        return [...document.querySelectorAll('.practice-row:not(.spelling-row)')].map(r=>{
          const l=r.querySelector('.pr-skill'), p=r.querySelector('.pr-practice');
          l.style.alignSelf=p.style.alignSelf='start';
          const out={n:r.dataset.factor,left:Math.round(l.getBoundingClientRect().height),right:Math.round(p.getBoundingClientRect().height),trim:r.dataset.trim||'',about:!!r.querySelector('.pr-about'),sheet:!!r.querySelector('.practice-sheet')};
          l.style.alignSelf=p.style.alignSelf='';
          return out;
        });
      });
      add(cols.length===3&&cols.every(c=>c.about&&c.sheet&&c.left<=c.right+1),label+': printed, each skill\'s why, win and practice sheet fit beside its practice',JSON.stringify(cols));
      // Too much to fit: "More" goes first, then the "why" line.
      const order=await page.evaluate(()=>{
        const r=document.querySelector('.practice-row:not(.spelling-row)');
        const why=r.querySelector('.pr-why');
        const keep=why.lastChild.textContent;
        why.lastChild.textContent=keep.repeat(12);
        VahiniReport.trimSkillColumns(document.getElementById('report-host'));
        const shown=sel=>getComputedStyle(r.querySelector(sel)).display!=='none';
        const out={trim:r.dataset.trim,more:shown('.pr-more'),why:shown('.pr-why'),win:shown('.pr-win')};
        why.lastChild.textContent=keep;
        VahiniReport.fitPrintPages(document.getElementById('report-host'));
        return out;
      });
      add(order.trim==='why'&&!order.more&&!order.why&&order.win,label+': a skill side too tall drops "More" first, then the why line',JSON.stringify(order));
      // As long as a real photo makes the sheets (stage, 2026-10-07).
      const natural=await page.evaluate(()=>{
        const sheets=[...document.querySelectorAll('#report-host .free-report')];
        [1119,1335].forEach((target,i)=>{const pad=document.createElement('div');pad.className='layout-stretch';pad.style.height=Math.max(0,target-sheets[i].scrollHeight)+'px';sheets[i].append(pad);});
        return sheets.map(p=>p.scrollHeight);
      });
      add(await pdfPages(page)===2,label+': stretched sheets still print on two pages',JSON.stringify(natural));
      await page.close();
    }
  }
  return results;
}
