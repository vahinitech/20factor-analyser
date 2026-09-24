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
    // Free access (five factors, no crops) must get the same illustrated
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
        heading:[...document.querySelectorAll('#report-host h3')].map(h=>h.textContent).find(t=>/to practise|strengths/.test(t))||'',
        pro:document.querySelector('#report-host .pro-note')?.textContent||''
      };
    });
    await free.close();
    result.results.push(
      {ok:freeReport.pages===2 && freeReport.paper==='rgb(255, 253, 248)' && freeReport.inline===0, name:'Free report renders the two styled report pages', detail:JSON.stringify(freeReport)},
      {ok:freeReport.cards>0 && freeReport.cards===freeReport.practice, name:'Free report pairs each priority with practice space'},
      {ok:!/three/.test(freeReport.heading) || freeReport.cards===3, name:'Free priority heading matches the number of cards', detail:freeReport.heading},
      {ok:/Pro adds the other 15 skills/.test(freeReport.pro), name:'Free report explains what Pro adds'}
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
