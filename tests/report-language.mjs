// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// "Print in" and "Share on WhatsApp" (docs/PRACTICE-FRAMEWORK.md, sections
// 9 and 10; owner request 2026-10-11): choosing Telugu redraws the same
// report in Telugu (scores, crops, the page photo, exercises and pictures
// unchanged), English comes back exactly as it was, the choice is kept in
// this browser, "Your progress" follows, the Telugu font loads and is
// embedded in the PDF, and the WhatsApp summary carries no name, no image
// and no link but the free check's. Runs the packed bundle
// (python frontend/build_bundle.py) in Chromium on a free port.
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { readFileSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright';
import { renderLongest, REPORT_ART } from './report-layout.mjs';

const freePort = () => new Promise((resolve, reject) => {
  const s = createServer(); s.once('error', reject);
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)); });
});
const PORT = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', String(PORT), '-a', '127.0.0.1', '-c-1', '-s'], { stdio: 'ignore' });
const results = [];
const add = (ok, name, detail = '') => results.push({ ok: !!ok, name, detail: typeof detail === 'string' ? detail : JSON.stringify(detail) });
const SHARE_LINK = 'https://vahinitech.com/analyser/analyser.html?from=whatsapp';
const TELUGU = /[ఀ-౿]/;
const python = readFileSync('backend/practice_catalog.py', 'utf8');
const AVOID_TE = [...python.match(/AVOID_WORDS_TE = \(([\s\S]*?)\)/)[1].matchAll(/"([^"]+)"/g)].map(m => m[1]);
const AVOID = /\b(weak|poor|bad|wrong|problem|inadequate|fail|lowest|mistake)/i;

async function waitUp() {
  for (let i = 0; i < 50; i++) {
    try { if ((await fetch(BASE + '/frontend/sample-report.html', { method: 'HEAD' })).ok) return; } catch { /* starting */ }
    await delay(200);
  }
  throw new Error('static server did not start');
}
/* What the report shows that must not change with the language. */
const SNAPSHOT = `(() => {
  const host = document.getElementById('report-host');
  return {
    lang: host.getAttribute('lang'),
    scores: [...host.querySelectorAll('.sk-score, .priority-score, .compact-score b')].map(e => (e.textContent.match(/[\\d.]+/) || [''])[0]),
    badges: [...host.querySelectorAll('.pr-badge')].map(e => (e.textContent.match(/[\\d.]+\\/10/) || [''])[0]),
    images: [...host.querySelectorAll('img')].map(i => i.getAttribute('src')),
    exercises: [...host.querySelectorAll('[data-exercise]')].map(e => e.dataset.exercise),
    tips: [...host.querySelectorAll('[data-tip]')].map(e => e.dataset.tip),
    rows: [...host.querySelectorAll('.practice-row')].map(e => e.dataset.factor),
    cards: [...host.querySelectorAll('.skill-card, .priority-card')].map(e => e.dataset.factor),
    stages: [...host.querySelectorAll('.sk-band, .pr-stage.now')].map(e => e.textContent),
    text: host.textContent,
    html: host.innerHTML,
  };
})()`;

try {
  await waitUp();
  const browser = await chromium.launch();
  const catalogue = JSON.parse(readFileSync('backend/catalogs/' + readFileSync('docs/PRACTICE-MAP.md', 'utf8').match(/catalogue version `(\w+)`/)[1] + '.json', 'utf8'));
  const owner = {}, teTitle = {};
  catalogue.factors.forEach(f => {
    (f.exercises || []).forEach(e => { owner[e.id] = f.n; teTitle[e.id] = e.i18n.te.title; });
    (f.tips || []).forEach(t => { owner[t.id] = f.n; });
  });

  for (const pro of [false, true]) {
    const tier = pro ? 'Pro' : 'Free';
    const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(BASE + '/frontend/sample-report.html' + (pro ? '?example=pro' : ''), { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    const en = await page.evaluate(SNAPSHOT);
    add(en.lang === 'en' && !TELUGU.test(en.text) && await page.inputValue('#report-lang') === 'en', `${tier}: English by default, lang="en"`);

    await page.selectOption('#report-lang', 'te');
    const te = await page.evaluate(SNAPSHOT);
    add(te.lang === 'te' && TELUGU.test(te.text), `${tier}: choosing తెలుగు redraws the report in Telugu with lang="te"`);
    const same = ['scores', 'badges', 'images', 'exercises', 'tips', 'rows', 'cards'].filter(k => JSON.stringify(en[k]) !== JSON.stringify(te[k]));
    add(!same.length, `${tier}: scores, crops, the page photo, exercises, tips and rows do not change`, same);
    const STAGES = ['నేర్చుకుంటోంది', 'మెరుగవుతోంది', 'పట్టు సాధిస్తోంది', 'బలంగా ఉంది'];
    add(te.stages.length > 0 && te.stages.every(s => STAGES.includes(s)), `${tier}: Telugu stage names`, te.stages);
    const names = await page.evaluate(() => ({
      p1: [...document.querySelectorAll('.page:first-of-type .skill-card h3, .page:first-of-type .priority-card h3')].map(e => e.textContent),
      p2: [...document.querySelectorAll('.practice-row:not(.spelling-row) h3')].map(e => e.textContent),
      open: document.querySelector('.p2-open') ? document.querySelector('.p2-open').textContent : '',
      others: [...document.querySelectorAll('.other-skills li')].map(e => e.textContent),
      titles: [...document.querySelectorAll('[data-exercise]')].map(e => [e.dataset.exercise, e.querySelector('.pr-ex-title b').textContent]),
    }));
    const bracket = /[ఀ-౿][^()]*\([A-Z][A-Za-z ]+\)/;
    add(names.p1.length > 0 && names.p1.every(n => /స్పెల్లింగ్/.test(n) || bracket.test(n)) && names.p2.every(n => bracket.test(n)),
      `${tier}: each skill name carries its English name in brackets on first use on each page`, names);
    const bracketsOnPage2 = (names.open + names.p2.join('') + names.others.join('')).match(/\([A-Z][A-Za-z ]+\)/g) || [];
    add(new Set(bracketsOnPage2).size === bracketsOnPage2.length, `${tier}: only the first use on page 2 has the brackets`, bracketsOnPage2);
    add(names.titles.length > 0 && names.titles.every(([id, title]) => title === teTitle[id]), `${tier}: exercise titles come from the catalogue's Telugu`, names.titles);
    const rowsOwn = await page.evaluate(() => [...document.querySelectorAll('.practice-row:not(.spelling-row)')].map(r => [r.dataset.factor, [...r.querySelectorAll('[data-exercise],[data-tip]')].map(e => e.dataset.exercise || e.dataset.tip)]));
    add(rowsOwn.every(([n, ids]) => ids.every(id => String(owner[id]) === n)), `${tier}: every Telugu exercise and tip belongs to its row's factor`, rowsOwn);
    add(!AVOID.test(te.text) && !AVOID_TE.some(w => te.text.includes(w)) && !te.text.includes('—'), `${tier}: no avoided word (English or Telugu) and no em dash in the Telugu report`,
      AVOID_TE.filter(w => te.text.includes(w)));
    const font = await page.evaluate(async () => {
      await document.fonts.ready;
      const h = document.querySelector('#report-host .page h2');
      return { family: getComputedStyle(h).fontFamily, loaded: [...document.fonts].some(f => f.family.replace(/"/g, '') === 'Noto Sans Telugu' && f.status === 'loaded'), check: document.fonts.check("16px 'Noto Sans Telugu'", 'అక్షరం') };
    });
    add(/^"?Noto Sans Telugu/.test(font.family) && font.loaded && font.check, `${tier}: the bundled Noto Sans Telugu loads and leads the Telugu faces`, font);
    await page.emulateMedia({ media: 'print' });
    const pdf = (await page.pdf({ format: 'A4', printBackground: true })).toString('latin1');
    add(/NotoSansTelugu/.test(pdf), `${tier}: the saved PDF embeds Noto Sans Telugu`);
    add(await page.evaluate(() => ['#report-lang', '#share-whatsapp'].every(s => getComputedStyle(document.querySelector(s)).display === 'none' || !document.querySelector(s).offsetParent)),
      `${tier}: "Print in" and "Share on WhatsApp" never print`);
    await page.emulateMedia({ media: 'screen' });

    // Back to English: exactly the report it was.
    await page.selectOption('#report-lang', 'en');
    const back = await page.evaluate(SNAPSHOT);
    add(back.html === en.html && back.lang === 'en', `${tier}: back to English gives the same report, character for character`);
    // The choice is kept in this browser.
    await page.selectOption('#report-lang', 'te');
    await page.reload({ waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    add(await page.evaluate(() => document.getElementById('report-host').getAttribute('lang')) === 'te' && await page.inputValue('#report-lang') === 'te',
      `${tier}: the choice is remembered in this browser`);
    await page.selectOption('#report-lang', 'en');
    add(errors.length === 0, `${tier}: no page errors`, errors);
    await page.close();
  }

  // Blocked storage: the page still works, in English, and the choice lasts for the page.
  {
    const page = await browser.newPage();
    await page.addInitScript(() => {
      Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });
    });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(BASE + '/frontend/sample-report.html', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    await page.selectOption('#report-lang', 'te');
    add(await page.evaluate(() => document.getElementById('report-host').getAttribute('lang')) === 'te' && errors.length === 0,
      'With storage blocked the report still renders and switches language', errors);
    await page.close();
  }

  // A missing Telugu sentence prints in English, for that sentence only.
  {
    const page = await browser.newPage();
    await page.goto(BASE + '/frontend/sample-report.html', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    const r = await page.evaluate(() => {
      delete window.VahiniReportStrings.te['p2.title'];
      VahiniReportShare.applyLanguage('te');
      return { h2: document.querySelector('.practice-page h2').textContent, head: document.querySelector('.practice-page .run-head').textContent, missing: VahiniI18n.missing('te') };
    });
    add(r.h2 === 'Your next small step' && /[ఀ-౿]/.test(r.head) && JSON.stringify(r.missing) === '["p2.title"]', 'A missing Telugu id falls back to English for that sentence only', r);
    await page.evaluate(() => VahiniReportShare.applyLanguage('en'));
    await page.close();
  }

  // "Your progress" follows the language.
  {
    const page = await browser.newPage();
    await page.goto(BASE + '/frontend/sample-report.html', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    const p = await page.evaluate(() => {
      localStorage.clear();
      const e = VahiniProgress.entryFrom('Asha', 70, [], [{ n: 5, score: 5.0 }], null);
      VahiniProgress.save(VahiniProgress.entryFrom('Asha', 60, [], [{ n: 5, score: 4.4 }], null));
      VahiniProgress.save(e);
      VahiniProgress.mount(document.getElementById('report-host'), { name: 'Asha', current: e });
      VahiniReportShare.applyLanguage('te');
      const panel = document.getElementById('progress-panel');
      const out = { lang: panel.getAttribute('lang'), title: panel.querySelector('h2').textContent, text: panel.textContent, buttons: !!panel.querySelector('#pp-download') };
      VahiniReportShare.applyLanguage('en');
      out.back = document.getElementById('progress-panel').querySelector('h2').textContent;
      localStorage.clear();
      return out;
    });
    add(p.lang === 'te' && p.title === 'మీ ప్రగతి' && p.buttons && /అక్షరాల పరిమాణం సమానంగా/.test(p.text) && p.back === 'Your progress', '"Your progress" redraws in the chosen language and keeps working', p);
    await page.close();
  }

  // Telugu, longest content, Free and Pro, pictures on and off: two A4 sheets.
  for (const pro of [false, true]) for (const art of [true, false]) {
    const label = `Telugu ${pro ? 'Pro' : 'Free'}, pictures ${art ? 'on' : 'off'}`;
    const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
    await page.addInitScript(() => { localStorage.setItem('vahini_report_lang', 'te'); });
    if (art) await page.addInitScript(a => { window.VAHINI_REPORT_ART = a; }, REPORT_ART);
    await page.goto(BASE + '/frontend/sample-report.html' + (pro ? '?example=pro' : ''), { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    await renderLongest(page, pro);
    const pages = async () => ((await page.pdf({ format: 'A4', printBackground: true })).toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
    const rows = await page.evaluate(() => ({ lang: document.getElementById('report-host').getAttribute('lang'), rows: document.querySelectorAll('.practice-row').length, spelling: document.querySelector('.spelling-row .pr-saw').textContent }));
    add(rows.lang === 'te' && rows.rows === 4 && /ఇంగ్లీష్ పదాలను మాత్రమే/.test(rows.spelling), `${label}: longest case in Telugu, the spelling row says it checked English words only`, rows);
    await page.emulateMedia({ media: 'print' });
    add(await pages() === 2, `${label}: prints on exactly two A4 pages`);
    await page.evaluate(() => {
      const sheets = [...document.querySelectorAll('#report-host .free-report')];
      [1119, 1335].forEach((target, i) => { const pad = document.createElement('div'); pad.className = 'layout-stretch'; pad.style.height = Math.max(0, target - sheets[i].scrollHeight) + 'px'; sheets[i].append(pad); });
    });
    add(await pages() === 2, `${label}: stretched sheets still print on two pages`);
    await page.close();
  }

  // Share on WhatsApp: the chosen language, no name, no image, one link.
  for (const lang of ['en', 'te']) {
    const page = await browser.newPage();
    const requests = []; page.on('request', r => requests.push(r.url()));
    await page.addInitScript(l => { localStorage.setItem('vahini_report_lang', l); window.__opened = []; window.open = (u, ...rest) => { window.__opened.push([u, ...rest]); return null; }; }, lang);
    await page.goto(BASE + '/frontend/sample-report.html', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    await page.evaluate(() => {
      const d = window.VAHINI_SAMPLE_REPORT;
      window.VahiniCraft = { ...window.VahiniCraft, checkSpelling: t => t ? [{ word: 'recieve', suggestion: 'receive', context: 'I recieve it' }] : [] };
      const analysis = { ...d.analysis, access: { tier: 'free' }, recognition: { ...d.analysis.recognition, level: 'high' }, results: d.analysis.results.filter(f => [1, 5, 7, 8, 18].includes(f.n)) };
      VahiniReport.render(document.getElementById('report-host'), { analysis, intake: { writerName: 'Asha Rao' }, recognizedText: 'I recieve it', crops: d.factor_regions || {}, detURL: d.photo, history: null });
      try { Object.defineProperty(navigator, 'share', { value: undefined, configurable: true }); } catch { /* absent */ }
    });
    const before = requests.length;
    await page.click('#share-whatsapp');
    await page.waitForFunction(() => window.__opened.length > 0);
    const opened = await page.evaluate(() => window.__opened[0]);
    const url = new URL(opened[0]);
    const text = url.searchParams.get('text') || '';
    const links = text.match(/https?:\/\/\S+/g) || [];
    add(url.origin + url.pathname === 'https://wa.me/' && opened[1] === '_blank', `${lang}: without a share sheet it opens wa.me`, opened);
    add(!/Asha|Rao/.test(text) && !/data:|blob:|\.png|\.jpe?g|\.webp|region_|line_\d|recieve/i.test(text), `${lang}: no name, no image, no id and no word from the page`, text);
    add(links.length === 1 && links[0] === SHARE_LINK, `${lang}: the only link is the free check's`, links);
    add(/74/.test(text) && (lang === 'te' ? TELUGU.test(text) && /పట్టు|మెరుగ|రోజుకు/.test(text) : !TELUGU.test(text) && /tries a day/.test(text)), `${lang}: the summary is in the chosen language, with the score and this week's plan`, text);
    add(requests.length === before, `${lang}: sharing sends nothing to any server`, requests.slice(before));
    await page.close();
  }
  // On a phone with a share sheet, it is used with the text only.
  {
    const context = await browser.newContext({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 800 } });
    const page = await context.newPage();
    await page.addInitScript(() => {
      window.__shared = []; window.__opened = [];
      Object.defineProperty(navigator, 'share', { value: d => { window.__shared.push(d); return Promise.resolve(); }, configurable: true });
      window.open = u => { window.__opened.push(u); return null; };
    });
    await page.goto(BASE + '/frontend/sample-report.html', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    await page.click('#share-whatsapp');
    await page.waitForFunction(() => window.__shared.length > 0);
    const r = await page.evaluate(() => ({ shared: window.__shared, opened: window.__opened }));
    add(r.shared.length === 1 && JSON.stringify(Object.keys(r.shared[0])) === '["text"]' && r.opened.length === 0 && r.shared[0].text.includes(SHARE_LINK),
      'On a phone the share sheet gets the text only', r);
    await context.close();
  }
  await browser.close();
} catch (error) {
  add(false, 'Report language checks ran', String(error && error.stack || error));
} finally {
  server.kill('SIGTERM');
}
for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.name}${r.ok || !r.detail ? '' : ' :: ' + r.detail}`);
const failed = results.filter(r => !r.ok).length;
console.log(`\nSummary: ${results.length - failed}/${results.length} checks passing`);
process.exit(failed ? 1 : 0);
