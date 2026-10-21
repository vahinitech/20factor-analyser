// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// "Print in", "Share PDF on WhatsApp" and the side panel
// (docs/10-practice-framework.md, sections 9 and 10; owner approval of
// version C, 2026-10-11): choosing Telugu redraws the same report in Telugu
// (scores, crops, the page photo, exercises and pictures unchanged), English
// comes back exactly as it was, the choice is kept in this browser, "Your
// progress" follows, the Telugu font loads and is embedded in the PDF; the
// share button loads the PDF libraries only when pressed, makes a two-page
// A4 PDF in the browser and shares the file (or saves it and opens wa.me),
// with nothing sent to a server; the side panel sits beside the report on a
// wide screen, under it on a narrow one, and never prints. Runs the packed
// bundle (python frontend/build_bundle.py) in Chromium on a free port.
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { readFileSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright';
import { renderLongest, REPORT_ART } from './report-layout.mjs';

// The shared PDF's file name: brand and date, never a child's name.
const SNAPSHOT_NAME = /^Vahini-handwriting-snapshot-\d{4}-\d{2}-\d{2}\.pdf$/;
// The PDF's Info dictionary (jsPDF writes plain or UTF-16 strings).
function pdfInfo(buf){
  const text = buf.toString('latin1');
  const out = {};
  for (const key of ['Title', 'Author', 'Creator', 'Subject']) {
    const m = text.match(new RegExp('/' + key + ' \\((.*?)(?<!\\\\)\\)'));
    if (!m) continue;
    let v = m[1].replace(/\\([()\\])/g, '$1');
    if (v.startsWith('þÿ')) v = Buffer.from(v.slice(2), 'latin1').swap16().toString('utf16le');
    out[key] = v;
  }
  return out;
}
// Samples page 1's image in the PDF (the first JPEG jsPDF wrote) where the
// keep band and the start card sit on the page, as a 5 x 5 grid each.
async function themedPixels(page, buf){
  const start = buf.indexOf(Buffer.from([0xff, 0xd8, 0xff]));
  const end = buf.indexOf(Buffer.from([0xff, 0xd9]), start) + 2;
  const jpeg = buf.subarray(start, end).toString('base64');
  return page.evaluate(async b64 => {
    const img = new Image();
    img.src = 'data:image/jpeg;base64,' + b64;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const sheet = document.querySelector('#report-host section.page').getBoundingClientRect();
    const k = img.naturalWidth / sheet.width;
    const at = (x, y) => [...g.getImageData(Math.round(x * k), Math.round(y * k), 1, 1).data].slice(0, 3);
    // The paper, in the page's left margin beside the keep band.
    const keepBox = document.querySelector('.sn-keep').getBoundingClientRect();
    const paper = at(10, keepBox.top - sheet.top + keepBox.height / 2);
    const differs = px => Math.max(...px.map((v, i) => Math.abs(v - paper[i]))) > 10;
    const probe = sel => {
      const r = document.querySelector(sel).getBoundingClientRect();
      let coloured = 0, total = 0;
      for (let i = 1; i <= 5; i++) for (let j = 1; j <= 5; j++) {
        const px = at(r.left - sheet.left + r.width * i / 6, r.top - sheet.top + r.height * j / 6);
        total++; if (differs(px) && Math.min(...px) < 250) coloured++;
      }
      return { coloured: coloured >= total * 0.6, share: coloured / total };
    };
    return { paper, keep: probe('.sn-keep'), start: probe('.sn-start') };
  }, jpeg);
}
import { useDesign } from './design-route.mjs';

const freePort = () => new Promise((resolve, reject) => {
  const s = createServer(); s.once('error', reject);
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)); });
});
const PORT = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', String(PORT), '-a', '127.0.0.1', '-c-1', '-s'], { stdio: 'ignore' });
const results = [];
const add = (ok, name, detail = '') => results.push({ ok: !!ok, name, detail: typeof detail === 'string' ? detail : JSON.stringify(detail) });
const TELUGU = /[ఀ-౿]/;
const python = readFileSync('backend/report/practice_catalog.py', 'utf8');
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
    scores: [...host.querySelectorAll('.sn-score b, .sn-chip b')].map(e => (e.textContent.match(/[\\d.]+/) || [''])[0]),
    badges: [...host.querySelectorAll('.pr-badge')].map(e => (e.textContent.match(/[\\d.]+\\/10/) || [''])[0]),
    images: [...host.querySelectorAll('img')].map(i => i.getAttribute('src')),
    exercises: [...host.querySelectorAll('[data-exercise]')].map(e => e.dataset.exercise),
    tips: [...host.querySelectorAll('[data-tip]')].map(e => e.dataset.tip),
    rows: [...host.querySelectorAll('.practice-row')].map(e => e.dataset.factor),
    cards: [...host.querySelectorAll('.sn-look, .sn-chip, .sn-start, .sn-keep')].map(e => e.dataset.factor),
    stages: [...host.querySelectorAll('.pr-stage.now')].map(e => e.textContent),
    text: host.textContent,
    html: host.innerHTML,
  };
})()`;

try {
  await waitUp();
  const browser = await chromium.launch();
  const catalogue = JSON.parse(readFileSync('backend/catalogs/' + readFileSync('docs/11-practice-map.md', 'utf8').match(/catalogue version `(\w+)`/)[1] + '.json', 'utf8'));
  const owner = {}, teTitle = {};
  catalogue.factors.forEach(f => {
    (f.exercises || []).forEach(e => { owner[e.id] = f.n; teTitle[e.id] = e.i18n.te.title; });
    (f.tips || []).forEach(t => { owner[t.id] = f.n; });
  });

  for (const pro of [false, true]) {
    const tier = pro ? 'Pro' : 'Free';
    const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
    await useDesign(page);
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(BASE + '/frontend/sample-report.html' + (pro ? '' : '?example=free'), { waitUntil: 'load' });
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
      // Page 1 names a skill in full once, in "Start here"; the measured
      // rows use the short chip names (owner, 2026-10-13).
      p1: [...document.querySelectorAll('.sn-start .sn-meta')].map(e => e.textContent),
      p2: [...document.querySelectorAll('.practice-row:not(.spelling-row) h3')].map(e => e.textContent),
      open: '',
      others: [...document.querySelectorAll('.other-skills [data-factor]')].map(e => e.textContent),
      titles: [...document.querySelectorAll('.pr-ex[data-exercise]')].map(e => [e.dataset.exercise, e.querySelector('.pr-ex-title b').textContent]),
    }));
    const bracket = /[ఀ-౿][^()]*\([A-Z][A-Za-z ]+\)/;
    const p1Brackets = names.p1.join(' ').match(/\([A-Z][A-Za-z ]+\)/g) || [];
    add(bracket.test(names.p1[0]) && p1Brackets.length === 1 && names.p2.every(n => bracket.test(n)),
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
    add(await page.evaluate(() => ['#report-lang', '#share-pdf', '#report-side', '.sn-cta'].every(s => getComputedStyle(document.querySelector(s)).display === 'none' || !document.querySelector(s).offsetParent)),
      `${tier}: the side panel (Print in, Share PDF) and page 1's buttons never print`);
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
    await page.goto(BASE + '/frontend/sample-report.html?example=free', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    await page.selectOption('#report-lang', 'te');
    add(await page.evaluate(() => document.getElementById('report-host').getAttribute('lang')) === 'te' && errors.length === 0,
      'With storage blocked the report still renders and switches language', errors);
    await page.close();
  }

  // A missing Telugu sentence prints in English, for that sentence only.
  {
    const page = await browser.newPage();
    await page.goto(BASE + '/frontend/sample-report.html?example=free', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    const r = await page.evaluate(() => {
      delete window.VahiniReportStrings.te['p2.title'];
      VahiniReportShare.applyLanguage('te');
      return { h2: document.querySelector('.practice-page h2').textContent, head: document.querySelector('.practice-page .run-head').textContent, missing: VahiniI18n.missing('te') };
    });
    add(r.h2 === 'Practise for one week' && /[ఀ-౿]/.test(r.head) && JSON.stringify(r.missing) === '["p2.title"]', 'A missing Telugu id falls back to English for that sentence only', r);
    await page.evaluate(() => VahiniReportShare.applyLanguage('en'));
    await page.close();
  }

  // "Your progress" follows the language.
  {
    const page = await browser.newPage();
    await page.goto(BASE + '/frontend/sample-report.html?example=free', { waitUntil: 'load' });
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
    await page.goto(BASE + '/frontend/sample-report.html' + (pro ? '' : '?example=free'), { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    await renderLongest(page, pro);
    const pages = async () => ((await page.pdf({ format: 'A4', printBackground: true })).toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
    const rows = await page.evaluate(() => ({ lang: document.getElementById('report-host').getAttribute('lang'), rows: document.querySelectorAll('.practice-row').length, spelling: document.querySelector('.spelling-row .pr-saw').textContent }));
    add(rows.lang === 'te' && rows.rows === 4 && /ఇంగ్లీష్ పదాల/.test(rows.spelling), `${label}: longest case in Telugu, the spelling row says it checked English words only`, rows);
    await page.emulateMedia({ media: 'print' });
    add(await pages() === 2, `${label}: prints on exactly two A4 pages`);
    await page.evaluate(() => {
      const sheets = [...document.querySelectorAll('#report-host .free-report')];
      [1119, 1335].forEach((target, i) => { const pad = document.createElement('div'); pad.className = 'layout-stretch'; pad.style.height = Math.max(0, target - sheets[i].scrollHeight) + 'px'; sheets[i].append(pad); });
    });
    add(await pages() === 2, `${label}: stretched sheets still print on two pages`);
    await page.close();
  }

  // Share PDF on WhatsApp. The PDF libraries load only when the button is
  // pressed; the PDF is two A4 pages made in the browser; without a file
  // share sheet it is saved and wa.me opens with a note; nothing is posted.
  const pdfPages = buf => (buf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  for (const lang of ['en', 'te']) {
    const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    await useDesign(page);
    const requests = []; page.on('request', r => requests.push([r.method(), r.url()]));
    await page.addInitScript(l => { localStorage.setItem('vahini_report_lang', l); window.__opened = []; window.open = (u, ...rest) => { window.__opened.push([u, ...rest]); return null; };
      Object.defineProperty(navigator, 'canShare', { value: undefined, configurable: true }); }, lang);
    await page.goto(BASE + '/frontend/sample-report.html?example=free', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    await page.evaluate(() => {
      const d = window.VAHINI_SAMPLE_REPORT;
      const analysis = { ...d.analysis, access: { tier: 'free' }, results: d.analysis.results.filter(f => [1, 5, 7, 8, 18].includes(f.n)) };
      VahiniReport.render(document.getElementById('report-host'), { analysis, intake: { writerName: 'Asha Rao' }, crops: d.factor_regions || {}, detURL: d.photo, history: null });
    });
    const lazy = await page.evaluate(() => ({ h2c: typeof window.html2canvas, pdf: typeof window.jspdf }));
    add(lazy.h2c === 'undefined' && lazy.pdf === 'undefined' && !requests.some(([, u]) => /scripts\/vendor\/(html2canvas|jspdf)/.test(u)),
      `${lang}: the PDF libraries are not loaded before the button is pressed`, lazy);
    const before = requests.length;
    const [download] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), page.click('#share-pdf')]);
    const file = readFileSync(await download.path());
    await page.waitForFunction(() => window.__opened.length > 0);
    const opened = await page.evaluate(() => window.__opened[0]);
    const after = requests.slice(before);
    add(SNAPSHOT_NAME.test(download.suggestedFilename()) && file.subarray(0, 5).toString() === '%PDF-' && pdfPages(file) === 2,
      `${lang}: without a file share sheet the two-page PDF is saved as Vahini-handwriting-snapshot-<date>.pdf`, { name: download.suggestedFilename(), pages: pdfPages(file), bytes: file.length });
    // The file is branded and never names the child (owner, 2026-10-11).
    const meta = pdfInfo(file);
    add(meta.Title === 'Vahini handwriting snapshot' && meta.Author === 'Vahini Technologies · vahinitech.com' && meta.Creator === 'Vahini Technologies · vahinitech.com'
      && meta.Subject === 'Free handwriting review' && !/Asha|Rao/.test(JSON.stringify(meta) + download.suggestedFilename()),
      `${lang}: the PDF's title, author, creator and subject are Vahini's, with no child's name`, meta);
    // The website theme reaches the PDF: page 1's KEEP DOING THIS band and
    // START HERE card keep their coloured backgrounds (not white paper).
    const theme = await themedPixels(page, file);
    add(theme.keep.coloured && theme.start.coloured, `${lang}: the shared PDF keeps the theme colours of page 1`, theme);
    add(/A4|595\.2\d* 841\.8\d*/.test(file.toString('latin1').match(/MediaBox\s*\[[^\]]*\]/)?.[0] || '') || /MediaBox \[0 0 595\.2/.test(file.toString('latin1')), `${lang}: the PDF pages are A4`, file.toString('latin1').match(/MediaBox\s*\[[^\]]*\]/)?.[0]);
    add(after.some(([, u]) => /scripts\/vendor\/html2canvas\.min\.js/.test(u)) && after.some(([, u]) => /scripts\/vendor\/jspdf\.umd\.min\.js/.test(u)), `${lang}: pressing the button loads the libraries`, after);
    add(after.every(([m, u]) => m === 'GET' && u.startsWith(BASE)) && !after.some(([, u]) => /persist|\/api\/|\/ocr|report-python/.test(u)),
      `${lang}: making and sharing the PDF sends nothing to a server`, after);
    const wa = new URL(opened[0]);
    const note = wa.searchParams.get('text') || '';
    add(wa.origin + wa.pathname === 'https://wa.me/' && opened[1] === '_blank' && !/Asha|Rao|https?:/.test(note) && (lang === 'te' ? TELUGU.test(note) : /attach it/.test(note)),
      `${lang}: then wa.me opens with a note, in the chosen language, to attach the saved report`, opened);
    add(await page.evaluate(() => /WhatsApp/.test(document.getElementById('share-status').textContent)), `${lang}: the panel says the PDF is saved`);
    await context.close();
  }
  // A phone that can share files gets the PDF file through the share sheet.
  {
    const context = await browser.newContext({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 800 } });
    const page = await context.newPage();
    await useDesign(page);
    const posts = []; page.on('request', r => { if (r.method() !== 'GET') posts.push(r.url()); });
    await page.addInitScript(() => {
      window.__shared = []; window.__opened = [];
      Object.defineProperty(navigator, 'canShare', { value: d => !!(d && d.files && d.files.every(f => f.type === 'application/pdf')), configurable: true });
      Object.defineProperty(navigator, 'share', { value: d => { window.__shared.push({ keys: Object.keys(d), files: (d.files || []).map(f => ({ name: f.name, type: f.type, size: f.size })) }); return Promise.resolve(); }, configurable: true });
      window.open = u => { window.__opened.push(u); return null; };
    });
    await page.goto(BASE + '/frontend/sample-report.html?example=free', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    await page.click('#share-pdf');
    await page.waitForFunction(() => window.__shared.length > 0, null, { timeout: 60000 });
    const r = await page.evaluate(() => ({ shared: window.__shared, opened: window.__opened }));
    const f = r.shared[0].files[0] || {};
    add(r.shared.length === 1 && r.shared[0].files.length === 1 && f.type === 'application/pdf' && SNAPSHOT_NAME.test(f.name) && f.size > 50000 && r.opened.length === 0 && posts.length === 0,
      'On a phone that can share files, the share sheet gets the PDF file', r);
    await context.close();
  }

  // The side panel: beside the report from 1200px, under it below that,
  // never printed.
  {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await useDesign(page);
    await page.goto(BASE + '/frontend/sample-report.html?example=free', { waitUntil: 'load' });
    await page.waitForSelector('#report-host .practice-page');
    const box = () => page.evaluate(() => {
      const r = s => document.querySelector(s).getBoundingClientRect();
      return { host: r('#report-host .page'), side: r('#report-side'), shown: getComputedStyle(document.getElementById('report-side')).display !== 'none',
        parts: ['#report-lang', '#share-pdf', '#print-report', '#sample-about', '.ns-sponsor'].every(s => document.querySelector('#report-side ' + s)) };
    });
    // The sample's banner moved into the panel as "About this sample"
    // (owner, 2026-10-11): no dark toolbar, its note and four links in the
    // panel, the intro heading kept.
    const about = await page.evaluate(() => {
      const card = document.querySelector('#report-side #sample-about');
      const links = card ? [...card.querySelectorAll('a')].map(a => [a.textContent.trim(), a.getAttribute('href')]) : [];
      return { toolbar: !!document.querySelector('.report-toolbar'), note: !!(card && /How this sample was made/.test(card.textContent)), links,
        intro: !!document.querySelector('#sample-intro h1'), outside: [...document.querySelectorAll('a[href="case-studies.html"]')].filter(a => !a.closest('#report-side') && !a.closest('#site-footer') && !a.closest('#site-nav')).length };
    });
    add(!about.toolbar && about.note && about.intro && about.outside === 0 && JSON.stringify(about.links) === JSON.stringify([
      ['All 20 factors', 'sample-report.html'], ['Free check: five factors', 'sample-report.html?example=free'],
      ['Before and after stories', 'case-studies.html'], ['Analyse your own page', 'analyser.html']]),
      'The sample banner is gone; its note and four links are in the side panel', about);
    const wide = await box();
    add(wide.shown && wide.parts && wide.side.left >= wide.host.right && wide.side.top < wide.host.bottom, 'Wide screen: the panel (Print in, Share PDF, Print, Sponsors) sits beside the report', wide);
    await page.setViewportSize({ width: 900, height: 900 });
    const narrow = await box();
    add(narrow.shown && narrow.side.top >= narrow.host.bottom, 'Narrow screen: the same panel sits under the report', narrow);
    await page.emulateMedia({ media: 'print' });
    add(await page.evaluate(() => getComputedStyle(document.getElementById('report-side')).display === 'none'), 'The side panel never prints');
    await page.close();
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
