// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// Every language keeps the English report (owner, 2026-10-23;
// docs/12-report-rules.md). The report will come in many languages, and
// it is only credible if every one of them looks like the English one:
// the same elements, font sizes, weights, line heights and font lists,
// every block in the same place and width, two A4 pages in print, script
// letters drawn at the size of the English letters beside them, and every
// character a language's report words use covered by a report font. Only
// the words may change. A new language in VahiniI18n.LANGS is checked here
// with nothing to add.
import { readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import { useDesign } from './design-route.mjs';
import { measure, declared } from '../scripts/report_font_scale.mjs';

const PORT = 4196;
const BASE = `http://127.0.0.1:${PORT}`;
const results = [];
const add = (ok, name, detail = '') => {
  results.push({ ok, name });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok || !detail ? '' : ' :: ' + (typeof detail === 'string' ? detail : JSON.stringify(detail))}`);
};
const server = spawn('./node_modules/.bin/http-server', ['.', '-p', String(PORT), '-a', '127.0.0.1', '-c-1', '-s'], { stdio: 'ignore' });
const up = async () => {
  for (let i = 0; i < 50; i += 1) {
    try { if ((await fetch(BASE + '/frontend/sample-report.html', { method: 'HEAD' })).ok) return; } catch { /* starting */ }
    await new Promise(r => setTimeout(r, 200));
  }
  throw new Error('server did not start');
};

// What a language may not change, element by element, and where each
// block sits. Text, and so heights, may change.
const snapshot = () => {
  const host = document.getElementById('report-host');
  const els = [...host.querySelectorAll('.page, .page *')].filter(e => !(e.closest('svg') && e.tagName.toLowerCase() !== 'svg'));
  const style = els.map(e => {
    const cs = getComputedStyle(e);
    // trim-* classes are the renderer making room for longer words; they
    // are reported apart (wordFit), not as a different report.
    const cls = (e.getAttribute('class') || '').split(/\s+/).filter(c => c && !/^trim-/.test(c)).join(' ');
    return { tag: e.tagName.toLowerCase(), cls, size: cs.fontSize, weight: cs.fontWeight, line: cs.lineHeight, family: cs.fontFamily, style: cs.fontStyle };
  });
  const zoomOf = e => Number(e.closest('.page').style.zoom || 1);
  const BLOCKS = '.page > *, .sn-mid > *, .sn-m, .sn-m > *, .sn-m-group, .sn-prac, .sn-cta, .practice-row, .practice-row > *, .other-skills, .p2-hard, .p2-close, .sn-note-table, .sn-note-table th, .sn-note-table td';
  const blocks = [...host.querySelectorAll(BLOCKS)].map(e => {
    const r = e.getBoundingClientRect(), p = e.closest('.page').getBoundingClientRect();
    // Measured in the page's own pixels: print may zoom a page to fit A4.
    const z = zoomOf(e);
    return { page: [...host.querySelectorAll('.page')].indexOf(e.closest('.page')), cls: (e.getAttribute('class') || e.tagName.toLowerCase()).split(/\s+/).filter(c => !/^trim-/.test(c)).join(' '), left: Math.round((r.left - p.left) / z), width: Math.round(r.width / z) };
  });
  const pages = [...host.querySelectorAll('.page')];
  const wordFit = {
    trimmed: [...host.querySelectorAll('.practice-row[data-trim]')].map(r => `${r.dataset.factor}:${r.dataset.trim}`),
    zoom: pages.map(p => Number(p.style.zoom || 1)),
  };
  return { style, blocks, pages: pages.length, wordFit };
};

const render = async (browser, tier, lang, print) => {
  const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
  await useDesign(page);
  await page.goto(BASE + '/frontend/sample-report.html' + (tier === 'free' ? '?example=free' : ''), { waitUntil: 'load' });
  await page.waitForSelector('#report-host .page');
  await page.selectOption('#report-lang', lang);
  await page.waitForFunction(l => document.getElementById('report-host').getAttribute('lang') === l, lang);
  await page.evaluate(() => document.fonts.ready);
  if (print) {
    await page.emulateMedia({ media: 'print' });
    await page.evaluate(() => VahiniReport.fitPrintPages(document.getElementById('report-host')));
  }
  const snap = await page.evaluate(snapshot);
  if (print) {
    const pdf = await page.pdf({ format: 'A4', printBackground: true });
    snap.pdfPages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  }
  await page.close();
  return snap;
};

const firstDiff = (a, b, keys, slack = 0) => {
  if (a.length !== b.length) return { count: [a.length, b.length] };
  for (let i = 0; i < a.length; i += 1) {
    for (const k of keys) {
      const same = typeof a[i][k] === 'number' ? Math.abs(a[i][k] - b[i][k]) <= slack : a[i][k] === b[i][k];
      if (!same) return { at: i, element: `${a[i].tag || ''}.${a[i].cls}`, key: k, english: a[i][k], other: b[i][k] };
    }
  }
  return null;
};
const warnings = [];
let langs = [];

await up();
const browser = await chromium.launch({ headless: true });
try {
  langs = await (async () => {
    const page = await browser.newPage();
    await page.goto(BASE + '/frontend/sample-report.html', { waitUntil: 'load' });
    const l = await page.evaluate(() => VahiniI18n.LANGS);
    await page.close();
    return l;
  })();
  add(langs[0] === 'en' && langs.length >= 2, 'The report has English and at least one other language', langs);
  for (const tier of ['pro', 'free']) {
    for (const print of [false, true]) {
      const mode = print ? 'print' : 'screen';
      const en = await render(browser, tier, 'en', print);
      for (const lang of langs.filter(l => l !== 'en')) {
        const other = await render(browser, tier, lang, print);
        const struct = firstDiff(en.style, other.style, ['tag', 'cls']);
        add(!struct, `${tier} ${mode} ${lang}: the same elements as English, in the same order`, struct);
        const fonts = struct ? null : firstDiff(en.style, other.style, ['size', 'weight', 'line', 'family', 'style']);
        add(!struct && !fonts, `${tier} ${mode} ${lang}: every element keeps the English font size, weight, line height and font list`, fonts);
        // A printed page zoomed differently from English is also widened
        // differently (fitPrintPages reflows it), so its blocks are compared
        // only on pages zoomed as in English; a page zoomed further is a
        // wording warning below.
        const sameZoom = i => Math.abs((other.wordFit.zoom[i] ?? 1) - (en.wordFit.zoom[i] ?? 1)) <= 0.001;
        const keep = list => list.filter(x => sameZoom(x.page));
        const place = firstDiff(keep(en.blocks), keep(other.blocks), ['cls', 'left', 'width'], 1);
        const skipped = en.wordFit.zoom.map((_, i) => i).filter(i => !sameZoom(i)).map(i => i + 1);
        add(!place, `${tier} ${mode} ${lang}: every block sits where it does in English, at the same width${skipped.length ? ` (page ${skipped.join(', ')} zoomed differently, see the warning)` : ''}`, place);
        if (print) add(other.pages === 2 && other.pdfPages === 2 && en.pdfPages === 2, `${tier} print ${lang}: two A4 pages, as English`, { pages: other.pages, pdf: other.pdfPages, english: en.pdfPages });
        // Words longer than English make the renderer hide a line in a
        // practice row or zoom a printed page to fit. That is wording to
        // shorten, listed here for the language's reviewer.
        const extraTrim = other.wordFit.trimmed.filter(x => !en.wordFit.trimmed.includes(x));
        const zoomed = other.wordFit.zoom.map((z, i) => [i + 1, z, en.wordFit.zoom[i]]).filter(([, z, e]) => Math.abs(z - e) > 0.001);
        if (extraTrim.length || zoomed.length) warnings.push(`${tier} ${mode} ${lang}: ${extraTrim.length ? `rows trimmed that English shows whole: ${extraTrim.join(', ')}` : ''}${extraTrim.length && zoomed.length ? '; ' : ''}${zoomed.length ? `pages zoomed differently from English to fit A4: ${zoomed.map(([p, z, e]) => `page ${p} ${z.toFixed(3)} (English ${e.toFixed(3)})`).join(', ')}` : ''}`);
      }
    }
  }
  // Script letters at the size of the English letters beside them.
  const rows = await measure(browser), css = declared();
  for (const r of rows) {
    add(css[r.family] != null && Math.abs(css[r.family] - r.scale) <= 2,
      `${r.family} (${r.script}) is scaled to its English face: measured ${r.scale}%, declared ${css[r.family] ?? 'none'}%`);
  }
} finally {
  await browser.close();
  server.kill();
}

// Every character a language's report words use has a report font: Latin
// letters the English faces carry, any other script a "Vahini Script" face
// whose unicode-range holds it.
const fontsCss = readFileSync('frontend/styles/report-fonts.css', 'utf8');
const ranges = [...fontsCss.matchAll(/@font-face\s*\{[^}]*font-family:'Vahini Script [^']+'[^}]*unicode-range:([^;]+);/g)]
  .flatMap(m => m[1].split(',').map(r => r.trim().replace(/^U\+/i, '').split('-').map(h => parseInt(h, 16))))
  .map(([a, b]) => [a, b ?? a]);
const covered = cp => cp < 0x0250 || (cp >= 0x2000 && cp <= 0x27BF) || ranges.some(([a, b]) => cp >= a && cp <= b);
const ctx = { window: {} };
// Every language in VahiniI18n.LANGS, so a new one is checked with nothing
// to add here.
for (const f of langs) new Function('window', readFileSync(`frontend/src/report/strings/${f}.js`, 'utf8'))(ctx.window);
add(langs.length > 0 && langs.every(l => ctx.window.VahiniReportStrings && ctx.window.VahiniReportStrings[l]), 'Every language in VahiniI18n.LANGS has its strings table', langs);
for (const lang of langs) {
  const text = JSON.stringify(ctx.window.VahiniReportStrings[lang] || {});
  const missing = [...new Set([...text].filter(ch => !covered(ch.codePointAt(0))))];
  add(missing.length === 0, `${lang}: every character of its report words has a report font`, missing.join(' '));
}

for (const w of warnings) console.log(`WARN words longer than English: ${w}`);
const failed = results.filter(r => !r.ok).length;
console.log(`Summary: ${results.length - failed}/${results.length} checks passing`);
process.exit(failed ? 1 : 0);
