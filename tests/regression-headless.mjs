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
    await free.goto(`${BASE_URL}/frontend/sample-report.html`, { waitUntil: 'load' });
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
        headline:host.querySelector('.sn-title').textContent+' | '+host.querySelector('.sn-sub').textContent,
        keep:host.querySelector('.sn-keep')?host.querySelector('.sn-keep').dataset.factor:null,
        start:host.querySelector('.sn-start')?host.querySelector('.sn-start').dataset.factor:null,
        tryCall:!!host.querySelector('.sn-start .sn-try'),
        look:[...host.querySelectorAll('.sn-look')].map(r=>({f:r.dataset.factor,crop:!!r.querySelector('img.sn-look-crop'),sheet:(r.querySelector('a.sn-sheet')||{}).href||''})),
        photo:!!(svg&&svg.querySelector('image')),
        boxesInView:view&&boxes.length?boxes.every(([x,y,w,h])=>x>=view[0]-0.5&&y>=view[1]-0.5&&x+w<=view[0]+view[2]+0.5&&y+h<=view[1]+view[3]+0.5):false,
        marks:boxes.length,
        chips:[...host.querySelectorAll('.sn-chip')].map(c=>c.dataset.factor),
        chipColours:[...host.querySelectorAll('.sn-chip b')].every(b=>getComputedStyle(b).backgroundColor===rgb(getComputedStyle(b).getPropertyValue('--sn-'+b.dataset.band).trim())),
        steps:host.querySelectorAll('.sn-steps li').length,
        trace:!!host.querySelector('.sn-guide .md-hand') && host.querySelectorAll('.sn-guide').length===2,
        check:!!host.querySelector('.sn-chk i'),
        qr:qr?qr.dataset.qr:'',
        qrWant:firstSheet?'https://vahinitech.com/assets/worksheets/'+firstSheet.id+'.pdf':'',
        cta:[...host.querySelectorAll('.sn-cta a')].map(a=>a.textContent.trim()),
        foot:host.querySelector('.snapshot-page .run-foot').textContent,
        practiceFactors:[...document.querySelectorAll('#report-host .coaching-card')].map(c=>c.dataset.factor).filter(f=>/^\d+$/.test(f)),
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
      {ok:freeReport.brand && freeReport.headline==='Small changes. Clearer writing. | One page, one strength, one useful next step.', name:'Page 1: Vahini logo, vahinitech.com, "Your writing snapshot" and the headline', detail:freeReport.headline},
      {ok:!!freeReport.pill && freeReport.pill.band==='good' && freeReport.pill.bg===freeReport.pill.want && /74\/100 · Mastering/.test(freeReport.pill.text), name:'Page 1: the overall score pill takes its band colour and stage (74: yellow, Mastering)', detail:JSON.stringify(freeReport.pill)},
      {ok:freeReport.keep==='1' && freeReport.start==='5' && freeReport.tryCall, name:'Page 1: keep doing the strongest skill, start with the first skill to grow', detail:JSON.stringify({keep:freeReport.keep,start:freeReport.start})},
      {ok:freeReport.photo && freeReport.marks===2 && freeReport.boxesInView, name:'Page 1: the photo is zoomed to the marked parts and every numbered box stays whole', detail:JSON.stringify({photo:freeReport.photo,marks:freeReport.marks,inView:freeReport.boxesInView})},
      {ok:JSON.stringify(freeReport.look.map(l=>l.f))==='["5","8"]' && freeReport.look.every(l=>l.crop && /\/assets\/worksheets\/[\w-]+\.pdf$/.test(l.sheet)), name:'Page 1: two look-closer rows, each with its crop and its worksheet link', detail:JSON.stringify(freeReport.look)},
      {ok:JSON.stringify(freeReport.chips)==='["1","5","7","8","18"]' && freeReport.chipColours, name:'Page 1: a chip per scored skill, its score in its band colour', detail:JSON.stringify(freeReport.chips)},
      {ok:freeReport.steps===3 && freeReport.trace && freeReport.check && freeReport.qr===freeReport.qrWant && freeReport.qrWant!=='', name:'Page 1: three steps, a line to trace, a tick box and a QR code for the first skill\'s worksheet', detail:JSON.stringify({steps:freeReport.steps,qr:freeReport.qr,want:freeReport.qrWant})},
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
