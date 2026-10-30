// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// The report PDF asks for nothing (owner, 2026-10-30, India's DPDP Act):
// Print / Save as PDF prints at once, and a card opens after it, at most
// once a day. Its two questions (what the report is for, and what a full
// report would be worth, owner 2026-10-16) are optional and go as one
// anonymous "report_pdf_answer" event. An email goes only when its own
// "Email me practice tips" box is ticked, as a "report_pdf_lead" with no
// name and no price. Rupees for a browser in India, dollars elsewhere;
// vahini-web's Friday report counts the same values.
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

// Opens the analyser page with print() counted and every post caught.
// `before` runs in the page before its scripts (to seed localStorage).
async function openPage(browser, timezoneId = 'Asia/Kolkata', before = null) {
  const context = await browser.newContext({ timezoneId, viewport: { width: 1200, height: 900 } });
  const page = await context.newPage();
  const posts = [];
  await page.route('**/persist/**', (route) => {
    try { posts.push(JSON.parse(route.request().postData() || '{}')); } catch { posts.push({ raw: route.request().postData() }); }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
  });
  await page.route('**/health', (r) => r.fulfill({ json: { ok: true } }));
  await page.addInitScript(() => {
    // The card must not be open when the print starts.
    window.print = () => { window.__printed = (window.__printed || 0) + 1; window.__cardAtPrint = document.getElementById('vgate').classList.contains('on'); };
    try { localStorage.setItem('vahini_guide_check', '1'); localStorage.setItem('vahini_guide_report', '1'); } catch {}   // Pihu's guide seen
  });
  if (before) await page.addInitScript(before);
  await page.goto(BASE + '/frontend/analyser.html', { waitUntil: 'load' });
  return { context, page, posts };
}

const print = (page) => page.evaluate(() => document.getElementById('print-report').click());
// What the card sent: the anonymous answer and the email, if any. A post
// from elsewhere on the page (a generated-report count) is not the card's.
const answerOf = (posts) => posts.filter((p) => p.kind === 'report_pdf_answer');
const leadOf = (posts) => posts.filter((p) => p.type === 'report_pdf_lead' || p.kind === 'report_pdf_lead' || (p.data && p.data.type === 'report_pdf_lead'));
const sentEmail = (posts) => posts.some((p) => JSON.stringify(p).includes('@example.com'));

// Prints, answers what is given, and returns what was posted.
async function answer(browser, timezoneId, { purpose = '', price = '', email = '', tick = false } = {}) {
  const { context, page, posts } = await openPage(browser, timezoneId);
  await print(page);
  await page.waitForSelector('#vgate.on');
  const options = await page.locator('#vg-price option').allTextContents();
  if (purpose) await page.selectOption('#vg-purpose', purpose);
  if (price) await page.selectOption('#vg-price', price);
  if (tick) await page.check('#vg-tips');
  if (email) await page.fill('#vg-email', email);
  await page.click('#vg-go');
  await delay(300);
  const thanks = await page.isVisible('#vgate-thanks');
  const thanksText = await page.textContent('#vg-thanks-text');
  await context.close();
  return { options, posts, thanks, thanksText };
}

try {
  await waitUp();
  const browser = await chromium.launch();

  // 1. The PDF comes first and asks for nothing.
  {
    const { context, page, posts } = await openPage(browser);
    await print(page);
    const printed = await page.evaluate(() => window.__printed || 0);
    const atPrint = await page.evaluate(() => window.__cardAtPrint);
    add(printed === 1 && atPrint === false, 'Print / Save as PDF prints at once, before any card opens', { printed, atPrint });
    await page.waitForSelector('#vgate.on', { timeout: 3000 });
    const fields = await page.evaluate(() => ({
      name: !!document.getElementById('vg-name'),
      org: !!document.getElementById('vg-org'),
      required: document.querySelectorAll('#vgate [required], #vgate .req').length,
      ticked: document.getElementById('vg-tips').checked,
      mailHidden: document.getElementById('vg-mail').hidden,
      bundled: /By continuing you agree/i.test(document.getElementById('vgate').textContent),
    }));
    add(!fields.name && !fields.org && fields.required === 0, 'The card asks for no name, no organisation and nothing required', fields);
    add(fields.ticked === false && fields.mailHidden === true, '"Email me practice tips" starts unticked, with the email field hidden', fields);
    add(!fields.bundled, 'No "By continuing you agree" line', fields);
    const lines = await page.textContent('#vg-tips-what');
    add(/Optional/.test(lines) && /PDF does not depend on it/.test(lines), 'One line says what we send and that it is optional', lines);
    await page.click('#vg-cancel');
    add(!(await page.isVisible('#vgate')), '"No thanks" closes the card');
    add(answerOf(posts).length === 0 && leadOf(posts).length === 0, '"No thanks" sends nothing', posts);
    // Once a day: a second print the same day opens no card.
    await print(page);
    await delay(200);
    add(!(await page.isVisible('#vgate')) && (await page.evaluate(() => window.__printed)) === 2,
      'A second print the same day prints and opens no card');
    await context.close();
  }

  // 2. The price question, in rupees and in dollars, and anonymous answers.
  const india = await answer(browser, 'Asia/Kolkata', { purpose: 'child', price: '100' });
  add(india.options.join('|') === 'Choose one…|Nothing, the free report is enough|Up to ₹50|₹100|₹200|More than ₹200',
    'In India the price question is in rupees', india.options);
  const a = answerOf(india.posts);
  add(a.length === 1 && a[0].data.price === '100' && a[0].data.currency === 'INR' && a[0].data.purpose === 'child',
    'The answers go as one report_pdf_answer event, with the currency', a);
  add(a.length === 1 && Object.keys(a[0]).sort().join() === 'data,kind,page' && Object.keys(a[0].data).sort().join() === 'currency,price,purpose',
    'The answer event carries nothing but the answers and the page', a);
  add(leadOf(india.posts).length === 0 && !sentEmail(india.posts), 'Answers without the box ticked send no lead and no email', india.posts);
  const us = await answer(browser, 'America/New_York', { price: '5' });
  add(us.options.join('|') === 'Choose one…|Nothing, the free report is enough|Up to $3|$5|$10|More than $10',
    'Elsewhere it is in dollars', us.options);
  const u = answerOf(us.posts);
  add(u.length === 1 && u[0].data.price === '5' && u[0].data.currency === 'USD' && !('purpose' in u[0].data),
    'A dollar answer goes with its currency; a skipped question is left out', u);

  // 3. An email only with its own tick.
  const ticked = await answer(browser, 'Asia/Kolkata', { purpose: 'teaching', price: '200', tick: true, email: 'vahini.parent@example.com' });
  const lead = leadOf(ticked.posts);
  add(lead.length === 1 && lead[0].email === 'vahini.parent@example.com' && lead[0].tips === true && lead[0].type === 'report_pdf_lead',
    'Ticked with an email: one report_pdf_lead with the address', lead);
  add(lead.length === 1 && !('name' in lead[0]) && !('org' in lead[0]) && !('price' in lead[0]) && !('ua' in lead[0]) && lead[0].consent,
    'The lead has no name, organisation, price or browser string, and records the consent line', lead);
  add(answerOf(ticked.posts).length === 1 && !sentEmail(answerOf(ticked.posts)), 'The price still goes in the anonymous event, never with the email', ticked.posts);
  add(ticked.thanks && /vahini\.parent@example\.com/.test(ticked.thanksText), 'The thank-you says where the tips will go', ticked.thanksText);

  // 4. A bad address with the box ticked is refused and sends nothing.
  {
    const { context, page, posts } = await openPage(browser);
    await print(page);
    await page.waitForSelector('#vgate.on');
    await page.check('#vg-tips');
    await page.fill('#vg-email', 'not an address');
    await page.click('#vg-go');
    await delay(300);
    const err = await page.isVisible('#vg-email-err');
    add(err && posts.filter((p) => p.kind === 'report_pdf_answer' || leadOf([p]).length).length === 0,
      'A ticked box with a bad address shows the error and sends nothing', posts);
    // Unticking takes the email back out: the answers alone are sent.
    await page.uncheck('#vg-tips');
    await page.selectOption('#vg-price', 'nothing');
    await page.click('#vg-go');
    await delay(300);
    add(answerOf(posts).length === 1 && leadOf(posts).length === 0 && !sentEmail(posts),
      'An email typed and then unticked is never sent', posts);
    await context.close();
  }

  // 5. Nothing answered: Send just closes, and nothing goes.
  const none = await answer(browser, 'Asia/Kolkata', {});
  add(answerOf(none.posts).length === 0 && leadOf(none.posts).length === 0 && !none.thanks, 'Send with nothing answered closes and sends nothing', none.posts);

  // 6. Names and emails the old form kept in this browser are cleared.
  {
    const { context, page } = await openPage(browser, 'Asia/Kolkata', () => {
      if (!sessionStorage.getItem('seeded')) {
        sessionStorage.setItem('seeded', '1');
        localStorage.setItem('vahini_leads', '[{"name":"Vahini","email":"v@example.com"}]');
        localStorage.setItem('vahini_report_lead', '{"name":"Vahini","email":"v@example.com"}');
      }
    });
    const left = await page.evaluate(() => [localStorage.getItem('vahini_leads'), localStorage.getItem('vahini_report_lead')]);
    add(left[0] === null && left[1] === null, 'Names and emails the old form saved in the browser are removed', left);
    const card = await page.evaluate(() => {
      const el = document.getElementById('ns-pro-link');
      return el && { href: el.getAttribute('href'), text: el.textContent, title: el.closest('.ns-card').querySelector('h3').textContent };
    });
    add(card && card.href === '/reach.html?topic=pro&from=report' && card.text === 'Request Pro' && /all 20 skills/.test(card.title),
      'The "See all 20 skills" card links to Request Pro, tagged from=report', card);
    await context.close();
  }
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
