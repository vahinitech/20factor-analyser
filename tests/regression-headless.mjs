import { spawn } from 'node:child_process';
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

    await page.goto(TEST_URL, { waitUntil: 'load' });

    await page.waitForFunction(() => {
      const t = window.__testResults;
      return !!(t && typeof t.total === 'number' && t.total > 0);
    }, { timeout: 120000 });

    return await page.evaluate(() => window.__testResults);
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
