import { spawn } from 'node:child_process';
import { checkReportLayout, checkPracticePrint, useDesign } from './report-layout.mjs';
import { setTimeout as delay } from 'node:timers/promises';

const PORT = 4173;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const TEST_URL = `${BASE_URL}/tests/print-vs-handwriting.test.html`;

function startServer() {
  const server = spawn('./node_modules/.bin/http-server', ['.', '-p', String(PORT), '-c-1'], {
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let startupLog = '';
  server.stdout.on('data', (chunk) => {
    startupLog += chunk.toString();
  });
  server.stderr.on('data', (chunk) => {
    startupLog += chunk.toString();
  });
  return { server, getLog: () => startupLog };
}

async function isServerUp() {
  try {
    const res = await fetch(`${BASE_URL}/tests/print-vs-handwriting.test.html`, { method: 'HEAD' });
    return res.ok;
  } catch {
    return false;
  }
}

async function waitForServer() {
  for (let i = 0; i < 50; i += 1) {
    try {
      const res = await fetch(`${BASE_URL}/tests/print-vs-handwriting.test.html`, { method: 'HEAD' });
      if (res.ok) return;
    } catch {
      // server may still be starting
    }
    await delay(200);
  }
  throw new Error('Timed out waiting for local server');
}

async function runHeadlessChecks() {
  const { chromium } = await import('playwright');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await useDesign(page);

    // Print-fit checks measure .page against its @media print sizing (the
    // print rules aren't applied under the default screen media), and the
    // wirePrintFit checks dispatch real beforeprint/afterprint events -- both
    // need the page actually in print media, not just simulated. This must
    // run BEFORE goto: the test page's own checks fire from DOMContentLoaded
    // (+ a setTimeout(0)), which resolves before Playwright's 'load' wait
    // does, so emulating print media only after goto left the checks running
    // under screen media's .page sizing (297mm/17mm pad, not print's
    // 296mm/13mm) despite the emulation call being present.
    await page.emulateMedia({ media: 'print' });
    await page.goto(TEST_URL, { waitUntil: 'load' });

    await page.waitForFunction(() => {
      const t = window.__testResults;
      return !!(t && typeof t.total === 'number' && t.total > 0);
    }, { timeout: 120000 });

    const result=await page.evaluate(() => window.__testResults);
    const layout=await checkReportLayout(page);
    result.results.push(...layout);
    // Free access (five factors, crops from the visitor's photo) must get the same illustrated
    // pages as the stylesheet expects, not a separate unstyled summary.
    const free=await browser.newPage();
    await useDesign(free);
    await free.goto(`${BASE_URL}/frontend/sample-report.html?example=free`, { waitUntil: 'load' });
    await free.waitForSelector('#report-host .free-report', { timeout: 30000 });
    const freeReport=await free.evaluate(()=>{
      const pages=[...document.querySelectorAll('#report-host .free-report.compact-report')];
      const host=document.getElementById('report-host');
      const svg=host.querySelector('.sn-zoom svg');
      const view=svg?svg.getAttribute('viewBox').split(' ').map(Number):null;
      const boxes=[...host.querySelectorAll('.sn-mark rect')].map(r=>['x','y','width','height'].map(k=>Number(r.getAttribute(k))));
      const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
      const rgb=hex=>{const d=document.createElement('i');d.style.color=hex;document.body.append(d);const c=getComputedStyle(d).color;d.remove();return c;};
      const pill=host.querySelector('.sn-score');
      const qr=host.querySelector('.sn-qr-code');
      const firstSheet=(window.VahiniWorksheetCatalog||[]).find(w=>w.factors.includes(Number(host.querySelector('.sn-start').dataset.factor)));
      return {
        pages:pages.length,
        paper:pages[0]?getComputedStyle(pages[0]).backgroundColor:'',
        inline:[...document.querySelectorAll('#report-host [style]')].filter(e=>/grid-template-columns|max-width/.test(e.getAttribute('style'))).length,
        brand:!!host.querySelector('.sn-top img.sn-logo[src$="assets/vahini-logo.png"]') && /vahinitech\.com/.test(host.querySelector('.sn-top').textContent) && /Your writing snapshot/i.test(host.querySelector('.sn-eyebrow').textContent),
        pill:pill?{band:pill.dataset.band,bg:getComputedStyle(pill).backgroundColor,want:rgb(getComputedStyle(pill).getPropertyValue('--sn-'+pill.dataset.band).trim()),text:pill.textContent}:null,
        numbers:(t=>(t.match(/out of 100|\/100|\d\.\d\/10|\b\d\.\d\b/)||[null])[0])(pages.map(p=>p.textContent).join(' ')),
        headline:host.querySelector('.sn-title').textContent,
        rings:host.querySelectorAll('.sn-m[data-measure=read] ellipse.sn-m-ring').length,
        readText:host.querySelector('.sn-m[data-measure=read] .sn-m-what p')?.textContent||'',
        teacher:host.querySelector('.sn-teacher')?{grow:[...host.querySelectorAll('.sn-note-table tr')].map(r=>[...r.children].map(c=>c.textContent.trim())),open:host.querySelector('.sn-keep').textContent,grade:host.querySelector('.sn-grade')?.textContent||'',sign:host.querySelector('.sn-sign').textContent}:null,
        keep:host.querySelector('.sn-keep')?host.querySelector('.sn-keep').dataset.factor:null,
        start:host.querySelector('.sn-start')?host.querySelector('.sn-start').dataset.factor:null,
        tryCall:!!host.querySelector('.sn-start .sn-try'),
        look:[...host.querySelectorAll('.sn-look')].map(r=>({f:r.dataset.factor,crop:!!r.querySelector('img.sn-look-crop'),sheet:(r.querySelector('a.sn-sheet')||{}).href||''})),
        photo:!!(svg&&svg.querySelector('image')),
        boxesInView:view&&boxes.length?boxes.every(([x,y,w,h])=>x>=view[0]-0.5&&y>=view[1]-0.5&&x+w<=view[0]+view[2]+0.5&&y+h<=view[1]+view[3]+0.5):false,
        marks:boxes.length,
        chips:[...host.querySelectorAll('.sn-chip')].map(c=>c.dataset.factor),
        measured:[...host.querySelectorAll('.sn-m')].map(r=>r.dataset.measure),
        strips:host.querySelectorAll('.sn-m svg image').length,
        locked:host.querySelectorAll('.sn-lockchip').length,
        chipColours:[...host.querySelectorAll('.sn-chip b')].every(b=>getComputedStyle(b).backgroundColor===rgb(getComputedStyle(b).getPropertyValue('--sn-'+b.dataset.band).trim())),
        steps:host.querySelectorAll('.sn-steps li').length,
        trace:!!host.querySelector('.sn-guide .md-hand') && host.querySelectorAll('.sn-guide').length===2,
        check:!!host.querySelector('.sn-chk i'),
        qr:qr?qr.dataset.qr:'',
        qrWant:firstSheet?'https://vahinitech.com/assets/worksheets/'+firstSheet.id+'.pdf':'',
        cta:[...host.querySelectorAll('.sn-cta a')].map(a=>a.textContent.trim()),
        foot:host.querySelector('.snapshot-page .run-foot').textContent,
        practiceFactors:[...document.querySelectorAll('#report-host .coaching-card')].map(c=>c.dataset.factor).filter(f=>/^\d+$/.test(f)),
        // The strongest skill and the first to grow, from the sample's own
        // scores (the four skills page 1 ranks; 18 is a blend), so a
        // regenerated sample cannot leave the check behind (#316).
        wantKeep:(r=>String(r.slice().sort((a,b)=>b.score-a.score||a.n-b.n)[0].n))(window.VAHINI_SAMPLE_REPORT.analysis.results.filter(f=>[1,5,7,8].includes(f.n))),
        wantStart:(r=>String(r.filter(f=>f.score<8.5).sort((a,b)=>a.score-b.score||a.n-b.n)[0].n))(window.VAHINI_SAMPLE_REPORT.analysis.results.filter(f=>[1,5,7,8].includes(f.n))),
        pro:document.querySelector('#report-host .pro-note')?.textContent||''
      };
    });
    // #84: each practice card for a factor links that skill's worksheet PDF.
    const sheets = await free.evaluate(() => {
      const cards = [...document.querySelectorAll('#report-host .coaching-card')].filter(c => /^\d+$/.test(c.dataset.factor));
      return { cards: cards.length, linked: cards.filter(c => /\/assets\/worksheets\/[\w-]+\.pdf$/.test(c.querySelector('.practice-sheet a')?.href || '')).length };
    });
    // #82: re-render the sample's real data with an earlier check; only rises
    // of 0.3 or more get a badge (+0.8 and +0.4 here, not +0.1).
    const better = await free.evaluate(() => {
      const d = window.VAHINI_SAMPLE_REPORT;
      const analysis = { ...d.analysis, access: { tier: 'free' }, results: d.analysis.results.filter(f => [1, 5, 7, 8, 18].includes(f.n)) };
      const score = n => analysis.results.find(f => f.n === n).score;
      const host = document.createElement('div');
      document.body.append(host);
      VahiniReport.render(host, { analysis, intake: {}, crops: {}, detURL: null, history: {
        date: '2026-09-30', overall: (analysis.overallMeasured ?? analysis.overall) - 4,
        factors: [{ n: 5, score: score(5) - 0.8 }, { n: 8, score: score(8) - 0.4 }, { n: 7, score: score(7) - 0.1 }] } });
      const out = {
        badges: [...host.querySelectorAll('.sn-chip')].filter(c => c.querySelector('.sn-up')).map(c => c.dataset.factor).sort(),
        text: host.querySelector('.since-last')?.textContent || '',
      };
      host.remove();
      return out;
    });
    await free.close();
    result.results.push(...await checkPracticePrint(browser, BASE_URL));
    result.results.push(
      {ok:freeReport.pages===2 && freeReport.paper==='rgb(253, 252, 246)' && freeReport.inline===0, name:'Free report renders the two styled report pages on the theme paper', detail:JSON.stringify({pages:freeReport.pages,paper:freeReport.paper})},
      // Page 1, version C (owner approval 2026-10-11).
      {ok:freeReport.brand && freeReport.headline==='A note from your teacher', name:'Page 1: Vahini logo, vahinitech.com, "Your writing snapshot" and Vidhya\'s note', detail:freeReport.headline},
      // The two letters the reader found hardest, circled on the hardest line
      // (letter_boxes.hardest_letters, owner 2026-10-14).
      {ok:freeReport.rings===2 && /the circled letters most of all/.test(freeReport.readText), name:'Reading row circles the two hardest letters', detail:{rings:freeReport.rings,text:freeReport.readText}},
      // Vidhya's note (owner, 2026-10-14): the skills to work on, her score
      // for the page and her name.
      // No score on the report (owner, 2026-10-23): Vidhya names the skills
      // and signs; there is no overall pill and no score line.
      // The sentences follow the regenerated sample (#316): letter shapes
      // first, then size and the line.
      {ok:!!freeReport.teacher && JSON.stringify(freeReport.teacher.grow)===JSON.stringify([['You are a master at','To improve next'],['Your letters are clear and well shaped.','Make your small letters the same height.'],['','Keep your words sitting on the line.']]) && /^Hello! Your handwriting is nice to read\.$/.test(freeReport.teacher.open) && freeReport.teacher.grade==='' && freeReport.teacher.sign==='Vidhya, your handwriting expert teacher', name:'Page 1: Vidhya\'s note, in words: what the writer is a master at beside what to improve next, and her name, with no score', detail:freeReport.teacher},
      {ok:freeReport.pill===null && !freeReport.numbers, name:'Page 1: no overall score and no score numbers on the report', detail:JSON.stringify({pill:freeReport.pill,numbers:freeReport.numbers})},
      {ok:freeReport.keep===freeReport.wantKeep && freeReport.start===freeReport.wantStart && freeReport.tryCall, name:'Page 1: keep doing the strongest skill, start with the first skill to grow', detail:JSON.stringify({keep:freeReport.keep,start:freeReport.start,wantKeep:freeReport.wantKeep,wantStart:freeReport.wantStart})},
      {ok:freeReport.photo && freeReport.marks===0, name:'Page 1: the photo is shown whole, without numbered boxes (the rows below draw each measurement)', detail:JSON.stringify({photo:freeReport.photo,marks:freeReport.marks})},
      // Strongest first on the regenerated sample (#316): reading (1),
      // gaps (8) and slope (7) tie at 5.8 and keep page order, size (5).
      {ok:JSON.stringify(freeReport.measured)==='["read","gaps","slope","size","margin"]' && freeReport.look.length===0 && freeReport.strips===5 && freeReport.locked>0, name:'Page 1: what we measured, strongest first, each row drawn on the photo, with the scores outside Free named', detail:JSON.stringify({measured:freeReport.measured,strips:freeReport.strips,locked:freeReport.locked})},
      {ok:JSON.stringify(freeReport.chips.slice().sort((a,b)=>a-b))==='["1","5","7","8","18"]' && freeReport.chipColours, name:'Page 1: a chip per scored skill, its score in its band colour', detail:JSON.stringify(freeReport.chips)},
      // A step list of one to three steps (the catalogue's limit): the
      // letter-size exercise the regenerated sample starts with has two.
      {ok:freeReport.steps>=1 && freeReport.steps<=3 && freeReport.trace && freeReport.check && freeReport.qr===freeReport.qrWant && freeReport.qrWant!=='', name:'Page 1: the exercise\'s steps, a line to trace, a tick box and a QR code for the first skill\'s worksheet', detail:JSON.stringify({steps:freeReport.steps,qr:freeReport.qr,want:freeReport.qrWant})},
      {ok:freeReport.cta.length===2 && /Indian Patents No\. 584433 and 604895/.test(freeReport.foot) && /vahinitech\.com/.test(freeReport.foot) && /not a school mark/.test(freeReport.foot) && /Spelling/.test(freeReport.foot), name:'Page 1: the two screen buttons and the footer with patents, vahinitech.com and the spelling note', detail:freeReport.foot},
      {ok:freeReport.practiceFactors.includes(freeReport.start) && freeReport.look.every(l=>freeReport.practiceFactors.includes(l.f)), name:'Free report pairs each skill to grow with practice space', detail:JSON.stringify({start:freeReport.start,practice:freeReport.practiceFactors})},
      {ok:/Pro checks 15 more skills/.test(freeReport.pro) && !/₹|price/i.test(freeReport.pro), name:'Free report explains what Pro adds, with no price'},
      {ok:sheets.cards>0 && sheets.linked===sheets.cards, name:'Each practice card links its skill worksheet', detail:JSON.stringify(sheets)},
      {ok:JSON.stringify(better.badges)==='["5","8"]' && /2 skills got better/.test(better.text), name:'Skills that rose by 0.3 or more get an up arrow', detail:JSON.stringify(better)}
    );
    result.total=result.results.length;
    result.passed=result.results.filter(r=>r.ok).length;
    result.allOk=result.total===result.passed;
    return result;
  } finally {
    // Always close, not just on the success path -- an unclosed browser
    // process (e.g. after a waitForFunction timeout) keeps Node's event
    // loop alive and the script hangs instead of exiting on failure.
    await browser.close().catch(() => {});
  }
}

async function main() {
  const alreadyUp = await isServerUp();
  const local = alreadyUp ? null : startServer();
  const server = local ? local.server : null;
  const getLog = local ? local.getLog : (() => '');
  try {
    await waitForServer();

    const result = await runHeadlessChecks();
    const passed = result?.passed ?? 0;
    const total = result?.total ?? 0;
    const allOk = !!result?.allOk;
    const rows = Array.isArray(result?.results) ? result.results : [];

    for (const r of rows) {
      const icon = r.ok ? 'PASS' : 'FAIL';
      const detail = r.detail ? ` :: ${r.detail}` : '';
      console.log(`${icon} ${r.name}${detail}`);
    }

    console.log(`\nSummary: ${passed}/${total} checks passing`);

    if (!allOk) {
      process.exitCode = 1;
    }
  } catch (err) {
    const log = getLog().trim();
    if (log) {
      console.error(log);
    }
    const msg = String(err && err.message ? err.message : err);
    if (msg.includes('libatk-1.0.so.0') || msg.includes('error while loading shared libraries')) {
      console.error('Missing Linux browser dependencies for Playwright Chromium.');
      console.error('Run: sudo ./node_modules/.bin/playwright install-deps chromium');
    }
    console.error(`Headless regression failed: ${err.message}`);
    process.exitCode = 1;
  } finally {
    if (server) server.kill('SIGTERM');
  }
}

// Explicit exit as a backstop: a lingering handle must never make this
// hang past its own printed summary (see runHeadlessChecks' browser.close
// fix above).
main().finally(() => process.exit(process.exitCode ?? 0));
