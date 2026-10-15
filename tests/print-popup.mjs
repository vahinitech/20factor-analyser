// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// The print popup's price question (owner, 2026-10-16): "what would a full
// report be worth to you?", asked right after a report so Pro prices
// follow real answers. Rupees for a browser in India, dollars elsewhere;
// optional, so a visitor who skips it still gets the PDF and the lead
// carries no price. vahini-web's Friday report counts the same values.
// Also: the "See all 20 skills" card links to Request Pro, tagged
// ?from=report so the Friday report can count it.
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright';

const freePort = () => new Promise((resolve, reject) => {
  const s = createServer(); s.once('error', reject);
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)); });
});
const PORT = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', String(PORT), '-a', '127.0.0.1', '-c-1', '-s'], { stdio: 'ignore' });
const results = [];
const add = (ok, name, detail = '') => results.push({ ok: !!ok, name, detail: typeof detail === 'string' ? detail : JSON.stringify(detail) });

async function waitUp() {
  for (let i = 0; i < 50; i++) {
    try { if ((await fetch(BASE + '/frontend/analyser.html', { method: 'HEAD' })).ok) return; } catch { /* starting */ }
    await delay(200);
  }
  throw new Error('static server did not start');
}

// Opens the popup the way a visitor does (the print button, intercepted),
// fills it in, and returns the options shown and the lead that was posted.
async function printWith(browser, timezoneId, price) {
  const context = await browser.newContext({ timezoneId, viewport: { width: 1200, height: 900 } });
  const page = await context.newPage();
  const leads = [];
  await page.route('**/persist/feedback', (route) => {
    try { leads.push(JSON.parse(route.request().postData() || '{}')); } catch { /* not JSON */ }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
  });
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.addInitScript(() => { window.print = () => { window.__printed = (window.__printed || 0) + 1; }; });
  await page.goto(BASE + '/frontend/analyser.html', { waitUntil: 'load' });
  await page.evaluate(() => document.getElementById('print-report').click());
  await page.waitForSelector('#vgate.on');
  const options = await page.locator('#vg-price option').allTextContents();
  await page.fill('#vg-name', 'Vahini');
  await page.fill('#vg-email', 'vahini.parent@example.com');
  await page.selectOption('#vg-purpose', 'Helping my child improve');
  if (price) await page.selectOption('#vg-price', price);
  await page.click('#vg-go');
  await page.waitForFunction(() => window.__printed > 0, null, { timeout: 5000 });
  const lead = leads.find((l) => l.kind === 'report_pdf_lead');
  const card = await page.evaluate(() => {
    const a = document.getElementById('ns-pro-link');
    return a && { href: a.getAttribute('href'), text: a.textContent, title: a.closest('.ns-card').querySelector('h3').textContent };
  });
  await context.close();
  return { options, lead: lead && lead.data, card };
}

try {
  await waitUp();
  const browser = await chromium.launch();
  const india = await printWith(browser, 'Asia/Kolkata', '100');
  add(india.options.join('|') === 'Choose one…|Nothing, the free report is enough|Up to ₹50|₹100|₹200|More than ₹200',
    'In India the price question is in rupees', india.options);
  add(india.lead && india.lead.price === '100' && india.lead.currency === 'INR', 'The answer goes with the lead, with its currency', india.lead);
  const us = await printWith(browser, 'America/New_York', '5');
  add(us.options.join('|') === 'Choose one…|Nothing, the free report is enough|Up to $3|$5|$10|More than $10',
    'Elsewhere it is in dollars', us.options);
  add(us.lead && us.lead.price === '5' && us.lead.currency === 'USD', 'A dollar answer goes with its currency', us.lead);
  const skipped = await printWith(browser, 'Asia/Kolkata', '');
  add(skipped.lead && !('price' in skipped.lead) && !('currency' in skipped.lead),
    'The question is optional: skipping it still prints, and the lead carries no price', skipped.lead);
  add(india.card && india.card.href === '/reach.html?topic=pro&from=report' && india.card.text === 'Request Pro' && /all 20 skills/.test(india.card.title),
    'The "See all 20 skills" card links to Request Pro, tagged from=report', india.card);
  await browser.close();
} catch (e) {
  add(false, 'test run', e.stack || String(e));
} finally {
  server.kill();
}
let failed = 0;
for (const r of results) {
  if (!r.ok) failed++;
  console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.ok || !r.detail ? '' : '\n      ' + r.detail}`);
}
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
