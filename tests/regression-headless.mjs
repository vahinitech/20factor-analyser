import { spawn } from 'node:child_process';
import { checkReportLayout } from './report-layout.mjs';
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
    await free.goto(`${BASE_URL}/frontend/sample-report.html`, { waitUntil: 'load' });
    await free.waitForSelector('#report-host .free-report', { timeout: 30000 });
    const freeReport=await free.evaluate(()=>{
      const pages=[...document.querySelectorAll('#report-host .free-report.compact-report')];
      return {
        pages:pages.length,
        paper:pages[0]?getComputedStyle(pages[0]).backgroundColor:'',
        inline:[...document.querySelectorAll('#report-host [style]')].filter(e=>/grid-template-columns|max-width/.test(e.getAttribute('style'))).length,
        cards:document.querySelectorAll('#report-host .priority-card').length,
        practice:document.querySelectorAll('#report-host .coaching-card .writing-lines').length,
        // Free page 1 (owner-approved 2026-10-06): five skill cards, each with a
        // crop from the visitor's photo or a note saying why there is none.
        skills:document.querySelectorAll('#report-host .skill-card').length,
        skillsExplained:[...document.querySelectorAll('#report-host .skill-card')].every(c=>c.querySelector('.sk-crop,.sk-none,.sk-why')),
        photo:!!document.querySelector('#report-host .page-photo img'),
        crops:document.querySelectorAll('#report-host .skill-card .sk-crop').length,
        firstFactors:[...document.querySelectorAll('#report-host .skill-card')].filter(c=>c.querySelector('.sk-tag')).map(c=>c.dataset.factor).sort(),
        practiceFactors:[...document.querySelectorAll('#report-host .coaching-card')].map(c=>c.dataset.factor).filter(f=>/^\d+$/.test(f)).sort(),
        heading:[...document.querySelectorAll('#report-host h3')].map(h=>h.textContent).find(t=>/to practise|strengths/.test(t))||'',
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
        badges: [...host.querySelectorAll('.skill-card')].filter(c => c.querySelector('.sk-better')).map(c => c.dataset.factor).sort(),
        text: host.querySelector('.since-last')?.textContent || '',
      };
      host.remove();
      return out;
    });
    await free.close();
    result.results.push(
      {ok:freeReport.pages===2 && freeReport.paper==='rgb(255, 253, 248)' && freeReport.inline===0, name:'Free report renders the two styled report pages', detail:JSON.stringify(freeReport)},
      {ok:freeReport.practice>0 && freeReport.firstFactors.length>0 && JSON.stringify(freeReport.firstFactors)===JSON.stringify(freeReport.practiceFactors), name:'Free report pairs each priority with practice space', detail:JSON.stringify({first:freeReport.firstFactors,practice:freeReport.practiceFactors})},
      // The sample report is a real run of the fixture photo, so it must show
      // the photo and at least one crop cut from it, like a visitor's report.
      {ok:freeReport.skills===5 && freeReport.skillsExplained && freeReport.photo && freeReport.crops>0, name:'Free report shows the photo and all five skills, each with its example or a reason', detail:JSON.stringify({skills:freeReport.skills,explained:freeReport.skillsExplained,photo:freeReport.photo,crops:freeReport.crops})},
      {ok:!/three/.test(freeReport.heading) || freeReport.cards===3, name:'Free priority heading matches the number of cards', detail:freeReport.heading},
      {ok:/Pro adds the other 15 skills/.test(freeReport.pro), name:'Free report explains what Pro adds'},
      {ok:sheets.cards>0 && sheets.linked===sheets.cards, name:'Each practice card links its skill worksheet', detail:JSON.stringify(sheets)},
      {ok:JSON.stringify(better.badges)==='["5","8"]' && /2 skills got better/.test(better.text), name:'Skills that rose by 0.3 or more get a badge', detail:JSON.stringify(better)}
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
