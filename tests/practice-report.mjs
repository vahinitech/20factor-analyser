// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// The practice report and "Your progress" (owner approval 2026-10-11, #122):
// page 2's rows, exercises, tips and plans come from the practice catalogue;
// characters only from a same-site host map; saved checks stay on the
// device. Runs the packed bundle (python frontend/build_bundle.py) in
// Chromium against a static server on a free port.
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { readFile } from 'node:fs/promises';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright';
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

async function waitUp() {
  for (let i = 0; i < 50; i++) {
    try { if ((await fetch(BASE + '/frontend/sample-report.html', { method: 'HEAD' })).ok) return; } catch { /* starting */ }
    await delay(200);
  }
  throw new Error('static server did not start');
}

/* Render the sample's real run with the given changes, in the page. */
const RENDER = `window.__render = (opts) => {
  const d = window.VAHINI_SAMPLE_REPORT;
  const o = opts || {};
  let results = d.analysis.results.map(f => ({ ...f }));
  if (o.free) results = results.filter(f => [1, 5, 7, 8, 18].includes(f.n));
  if (o.scores) results.forEach(f => { if (o.scores[f.n] != null) { f.score = o.scores[f.n]; } });
  const analysis = { ...d.analysis, results, recognition: { ...(d.analysis.recognition || {}), level: o.spelling ? 'high' : 'low' } };
  if (o.free) analysis.access = { tier: 'free' };
  if (o.text) delete analysis.textClassification;   // read this text instead of the sample's
  if (o.limits) analysis.practiceLimits = o.limits;
  window.VahiniCraft = { ...window.__craft, checkSpelling: t => (o.spelling && t) ? [{ word: 'recieve', suggestion: 'receive', context: 'I recieve it' }] : [] };
  const host = document.getElementById('report-host');
  const out = VahiniReport.render(host, { analysis, intake: {}, recognizedText: o.text || 'I recieve it', crops: d.factor_regions || {}, detURL: d.photo, history: o.history || null });
  const rows = [...host.querySelectorAll('.practice-row')].map(r => ({
    factor: r.dataset.factor,
    badge: r.querySelector('.pr-badge') ? r.querySelector('.pr-badge').textContent : '',
    now: r.querySelector('.pr-stage.now') ? r.querySelector('.pr-stage.now').textContent : '',
    done: [...r.querySelectorAll('.pr-stage.done')].map(e => e.textContent),
    exercises: [...r.querySelectorAll('[data-exercise]')].map(e => e.dataset.exercise),
    tips: [...r.querySelectorAll('[data-tip]')].map(e => e.dataset.tip),
    plan: r.querySelector('.pr-plan') ? r.querySelector('.pr-plan').textContent : '',
    tipLabels: [...r.querySelectorAll('.pr-tip b')].every(b => b.textContent === "Pihu's tip:"),
    crop: !!r.querySelector('.pr-crop'),
    cropSrc: r.querySelector('.pr-crop') ? r.querySelector('.pr-crop').getAttribute('src') : null,
    model: [...r.querySelectorAll('[data-exercise]')].every(e => e.querySelector('.pr-model .md')),
    models: [...r.querySelectorAll('[data-exercise]')].map(e => e.dataset.model),
    saw: r.querySelector('.pr-saw') ? r.querySelector('.pr-saw').textContent : '',
    sheet: r.querySelector('.pr-skill a[href*="/worksheets/"]') ? r.querySelector('.pr-skill a[href*="/worksheets/"]').getAttribute('href') : null,
    why: r.querySelector('.pr-skill .pr-why') ? r.querySelector('.pr-skill .pr-why').lastChild.textContent : null,
    win: r.querySelector('.pr-skill .pr-win') ? r.querySelector('.pr-skill .pr-win').lastChild.textContent.trim() : null,
    more: r.querySelector('.pr-skill .pr-more a') ? r.querySelector('.pr-skill .pr-more a').getAttribute('href') : null,
    moreText: r.querySelector('.pr-skill .pr-more a') ? r.querySelector('.pr-skill .pr-more a').textContent : null,
  }));
  return {
    out, rows,
    start: host.querySelector('.sn-start') ? host.querySelector('.sn-start').dataset.factor : null,
    look: [...host.querySelectorAll('.sn-look')].map(e => e.dataset.factor),
    chips: [...host.querySelectorAll('.sn-chip')].map(e => e.dataset.factor),
    bands: [...host.querySelectorAll('.sn-start .sn-meta, .pr-badge')].map(e => e.textContent),
    keep: host.querySelector('.sn-keep') ? host.querySelector('.sn-keep').textContent : '',
    others: [...host.querySelectorAll('.other-skills [data-factor]')].map(e => e.dataset.factor),
    proNote: host.querySelector('.pro-note') ? host.querySelector('.pro-note').textContent : '',
    closing: host.querySelector('.p2-close') ? host.querySelector('.p2-close').textContent : '',
    hard: host.querySelector('.p2-hard') ? host.querySelector('.p2-hard').textContent : '',
    hardLink: host.querySelector('.p2-hard a') ? host.querySelector('.p2-hard a').getAttribute('href') : '',
    hardText: host.querySelector('.p2-hard a') ? host.querySelector('.p2-hard a').textContent : '',
    hardBeforeClose: !!host.querySelector('.p2-hard + .p2-close'),
    art: [...host.querySelectorAll('img.rp-art')].map(i => i.getAttribute('src')),
    text: host.textContent,
  };
};`;

try {
  await waitUp();
  const catalogue = await (async () => {
    // The same data the bundle carries, read here from the backend module's
    // served form via the committed catalogue file.
    const fs = await import('node:fs');
    // The version docs/11-practice-map.md names: the one serving it today.
    const current = fs.readFileSync('docs/11-practice-map.md', 'utf8').match(/catalogue version `([0-9a-f]+)`/)[1];
    return JSON.parse(fs.readFileSync(`backend/catalogs/${current}.json`, 'utf8'));
  })();
  add(!!catalogue, 'A committed catalogue version carries the practice block');
  const owner = {};
  catalogue.factors.forEach(f => { (f.exercises || []).forEach(e => { owner[e.id] = f.n; }); (f.tips || []).forEach(t => { owner[t.id] = f.n; }); });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
  await useDesign(page);
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(BASE + '/frontend/sample-report.html?example=free', { waitUntil: 'load' });
  await page.waitForSelector('#report-host .practice-page');
  await page.evaluate(src => { window.__craft = window.VahiniCraft; (0, eval)(src); }, RENDER);
  // The heading names the tier the example shows.
  const freeTitle = await page.textContent('#sample-title');
  const proPage = await browser.newPage();
  await useDesign(proPage);
  await proPage.goto(BASE + '/frontend/sample-report.html?example=pro', { waitUntil: 'load' });
  await proPage.waitForSelector('#report-host .practice-page');
  const proTitle = await proPage.textContent('#sample-title');
  await proPage.close();
  add(freeTitle === 'What your Free handwriting report looks like' && proTitle === 'All 20 handwriting factors, from one sample page',
    'The sample heading names Free, or all 20 factors on the 20-factor example', { freeTitle, proTitle });

  // Bundled catalogue matches the committed one.
  const bundled = await page.evaluate(() => window.VahiniPracticeCatalog);
  add(JSON.stringify(bundled.tiers) === JSON.stringify(catalogue.practice.tiers) && JSON.stringify(bundled.dosage) === JSON.stringify(catalogue.practice.dosage)
    && catalogue.factors.every(f => JSON.stringify((bundled.factors[String(f.n)] || {}).exercises) === JSON.stringify(f.exercises)),
    'The bundle carries the same practice catalogue the server serves');

  const row5first = r => (r.rows.find(x => x.factor === '5') || { exercises: [] }).exercises[0];
  // Free: rows follow the priorities; one exercise and one tip each.
  const free = await page.evaluate(() => window.__render({ free: true }));
  const freeFactors = free.rows.map(r => r.factor);
  // Letter size is scored from word heights since 2026-10-13 (#135): the
  // sample's lowest skill is now word spacing (5.7), then size (6.1).
  add(JSON.stringify(freeFactors) === '["8","5","1"]' && free.start === '8' && free.look.length === 0,
    'Free rows are the lowest measured skills below 8.5; page 1 starts with the first, and shows what was measured instead of look-closer rows', { freeFactors, start: free.start, look: free.look });
  add(free.rows.every(r => r.exercises.length === 1 && r.tips.length === 1 && r.tipLabels),
    'Free shows one exercise and one tip per skill', free.rows);
  add(free.rows.every(r => r.exercises.concat(r.tips).every(id => String(owner[id]) === r.factor)),
    'Every exercise and tip belongs to its row\'s factor', free.rows);
  add(row5first(free) === 'size.two-line-ladder' && free.rows.every(r => r.model && r.models.every(m => m !== 'focus')),
    'A first check picks by need (the two-line ladder for letter size) and draws each exercise\'s own model', free.rows.map(r => [r.exercises, r.models]));
  const row = n => free.rows.find(r => r.factor === n);
  add(/6\.1\/10 · Improving/.test(row('5').badge) && row('5').now === 'Improving' && JSON.stringify(row('5').done) === '["Learning ✓"]'
    && row('1').now === 'Mastering' && row('1').done.length === 2, 'Rows show score, stage and the stage path', free.rows);
  // Tries follow the row's own skill (owner, 2026-10-11): letter size is
  // Improving (6.1), so 10 a day; letter shapes is Mastering (7.0), so 5.
  add(/10 tries a day, for 7 days\./.test(row('5').plan) && /5 tries a day, for 7 days/.test(row('1').plan),
    'Tries follow the row\'s own skill, not a weaker skill its exercise also helps', free.rows.map(r => r.plan));
  const solo7 = await page.evaluate(() => window.__render({ free: true, scores: { 1: 9.5, 5: 9.5, 8: 9.5, 18: 9.5 } }));
  add(/5 tries a day, for 7 days/.test(solo7.rows[0].plan), 'A Mastering skill on its own asks 5 a day', solo7.rows.map(r => r.plan));
  add(!free.bands.some(b => /Needs support|Developing|Good\b/.test(b)) && free.bands.some(b => /Improving/.test(b)) && free.bands.some(b => /Mastering/.test(b)),
    'Both pages use the stage names', free.bands);
  // When writing feels hard: before the closing line, encouraging, with
  // the website's page; never a diagnosis or a cure.
  add(/Every child learns to write at their own pace\./.test(free.hard) && /occupational therapist/.test(free.hard)
    && free.hardLink === 'https://vahinitech.com/signs-child-needs-handwriting-help.html' && free.hardText === 'vahinitech.com/signs-child-needs-handwriting-help' && free.hardBeforeClose
    && !/\b(cur(e|es|ed|ing)|overcom\w*|disorder\w*|diagnos\w*|dyslexi\w*|dysgraphi\w*)\b/i.test(free.text),
    'Page 2 has the "when writing feels hard" note with its link, before the closing line, and no diagnosis words', { hard: free.hard, link: free.hardLink });
  add(catalogue.factors.every(f => typeof f.why === 'string' && (bundled.factors[String(f.n)] || {}).why === f.why && (bundled.factors[String(f.n)] || {}).page === f.page),
    'The bundle and the served catalogue carry each skill\'s why, win and page');
  add(/Your words sit on the line\./.test(free.keep) && /You are getting better with every page!/.test(free.closing),
    'Page 1 opens with a strength and page 2 closes with encouragement', free.keep);
  add(JSON.stringify(free.others) === '["18","7"]' && /Pro checks 15 more skills/.test(free.proNote) && !/₹|price/i.test(free.proNote),
    'Other skills we checked lists the rest, then what Pro adds, with no price', { others: free.others, note: free.proNote });
  add(!free.rows.some(r => r.factor === 'spelling'), 'No spelling row without a finding');
  add(free.art.length === 0, 'Without a picture map the report has no pictures');

  // Page 2 draws what each exercise's steps say: one drawing per kind, the
  // one the catalogue names for the exercise.
  const drawings = await page.evaluate(() => VahiniReport.MODEL_KINDS.map(k => [k, (VahiniReport.modelHTML(k, 'a o') || '').includes('md-' + (k === 'start-dots' ? 'dots' : k))]));
  add(drawings.length === 13 && drawings.every(([, ok]) => ok), 'Every drawing kind renders its own model', drawings);
  const modelOf = {}; catalogue.factors.forEach(f => (f.exercises || []).forEach(e => { modelOf[e.id] = e.model; }));
  add(free.rows.every(r => r.exercises.every((id, i) => r.models[i] === modelOf[id])), 'Each exercise shows the drawing the catalogue names for it', free.rows.map(r => [r.exercises, r.models]));
  add(await page.evaluate(() => [...document.querySelectorAll('.practice-row')].every(r => r.querySelector('.pr-turn-row .yt'))), 'Each skill has lines to try it, matching its drawing');

  // Spelling row only when the limited check found a word; extra to the skills.
  const spelled = await page.evaluate(() => window.__render({ free: true, spelling: true }));
  add(JSON.stringify(spelled.rows.map(r => r.factor)) === '["8","5","1","spelling"]' && /We read recieve\. Did you mean receive\?/.test(spelled.text)
    && /1 word to check/.test(spelled.rows[3].badge) && spelled.rows[3].exercises[0] === 'spell.look-cover-write',
    'A spelling finding adds its own row after the skills', spelled.rows.map(r => r.factor));

  // Pro: band decides (up to 2), tier caps; a Mastering skill gets one.
  const pro = await page.evaluate(() => window.__render({ scores: { 3: 3.0, 6: 7.6 } }));
  add(pro.rows.length === 3 && pro.rows.every(r => r.tips.length === 2), 'Pro shows two tips per skill', pro.rows);
  const pr3 = pro.rows.find(r => r.factor === '3');
  add(pr3 && pr3.exercises.length === 2 && /15 tries a day in all/.test(pr3.plan) && pr3.now === 'Learning', 'Pro, Learning band: two exercises and 15 tries a day', pr3);
  const mastering = await page.evaluate(() => window.__render({ scores: Object.fromEntries(Array.from({ length: 20 }, (_, i) => [i + 1, 9]).concat([[6, 7.6]])) }));
  add(mastering.rows.length === 1 && mastering.rows[0].exercises.length === 1 && mastering.rows[0].factor === '6', 'A Mastering skill gets one exercise even on Pro', mastering.rows);
  add(pro.others.length > 0 && !/Pro checks/.test(pro.text), 'Pro lists its other skills and no Pro note');
  // /api/v2/me numbers win over the catalogue defaults; junk is ignored.
  const limited = await page.evaluate(() => window.__render({ limits: { areas_max: 2, exercises_max: 1, tips_max: 0 } }));
  add(limited.rows.length === 2 && limited.rows.every(r => r.exercises.length === 1 && r.tips.length === 0), 'The tier numbers from /api/v2/me decide how many', limited.rows);
  const junk = await page.evaluate(() => window.__render({ free: true, limits: { areas_max: 'all', exercises_max: 99, tips_max: -1 } }));
  add(junk.rows.length === 3 && junk.rows.every(r => r.exercises.length === 1 && r.tips.length === 1), 'Invalid tier numbers fall back to the catalogue');
  // Latin-only exercises are skipped on another script.
  const telugu = await page.evaluate(() => window.__render({ scores: { 1: 3.0 }, text: 'అమ్మ ఆవు ఇల్లు ఈగ ఉడుత' }));
  add(telugu.rows.flatMap(r => r.exercises).every(id => catalogue.factors.some(f => (f.exercises || []).some(e => e.id === id && e.script !== 'latin'))),
    'Latin-only exercises are skipped when the page is in another script');

  // Rotation: the next check starts after last time's exercises and wraps.
  const first = await page.evaluate(() => window.__render({ free: true }));
  const second = await page.evaluate(p => window.__render({ free: true, history: { date: '2026-10-01', overall: 70, factors: [], practice: p } }), first.out.practice);
  const list5 = catalogue.factors.find(f => f.n === 5).exercises.map(e => e.id);
  add(second.rows.find(r => r.factor === '5').exercises[0] !== first.rows.find(r => r.factor === '5').exercises[0] && list5.includes(second.rows.find(r => r.factor === '5').exercises[0]) && second.rows.find(r => r.factor === '5').tips[0] !== first.rows.find(r => r.factor === '5').tips[0],
    'A re-check moves on to the next exercise and tip', { first: first.out.practice, second: second.out.practice });
  const wrapped = await page.evaluate(id => window.__render({ free: true, history: { date: '2026-10-01', overall: 70, factors: [], practice: { exercises: { 5: [id] }, tips: {} } } }), list5[list5.length - 1]);
  add(wrapped.rows.find(r => r.factor === '5').exercises[0] !== list5[list5.length - 1] && list5.includes(wrapped.rows.find(r => r.factor === '5').exercises[0]), 'Last time\'s exercise gives way to another of the same skill');

  // Mapping, skill by skill: make one skill the only one to grow and check
  // that its row carries only its own exercises, tips, crop, worksheet and
  // words, in Free (its five skills) and in Pro (every photo-scored skill),
  // in English and in Telugu ("Print in"; the words change, the mapping
  // must not).
  const regions = await page.evaluate(() => window.VAHINI_SAMPLE_REPORT.factor_regions || {});
  const sheets = await page.evaluate(() => window.VahiniWorksheetCatalog || []);
  const photoSkills = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 17, 19];
  const teText = {};
  catalogue.factors.forEach(f => (f.exercises || []).concat(f.tips || []).forEach(e => { teText[e.id] = e.i18n.te.title || e.i18n.te.text; }));
  for (const lang of ['en', 'te']) {
    await page.evaluate(l => VahiniI18n.setLanguage(l), lang);
    const L = lang === 'en' ? '' : ' (Telugu)';
    for (const [tier, skills] of [['free', [1, 5, 7, 8]], ['pro', photoSkills]]) {
      for (const n of skills) {
        const all = {}; for (let k = 1; k <= 20; k++) all[k] = 9.5;
        all[n] = 5.0;
        const r = await page.evaluate(o => window.__render(o), { free: tier === 'free', scores: all });
        const row = r.rows.find(x => x.factor === String(n));
        const rows = r.rows.filter(x => x.factor !== 'spelling').map(x => x.factor);
        add(row && JSON.stringify(rows) === JSON.stringify([String(n)]), `${tier}${L}: skill ${n} alone to grow gives exactly its row`, rows);
        if (!row) continue;
        // Under the skill: why it helps, the win and its website page, from
        // the catalogue, in the report's language (owner, 2026-10-11).
        const fa = catalogue.factors.find(f => f.n === n);
        const local = k => (lang === 'en' ? fa[k] : fa.i18n[lang][k]);
        add(row.why === local('why') && row.win === local('win') && row.more === `https://vahinitech.com/${fa.page}.html` && row.moreText === `vahinitech.com/${fa.page}`,
          `${tier}${L}: skill ${n}'s row says why it helps, the win and its page`, { why: row.why, win: row.win, more: row.more });
        const foreign = row.exercises.concat(row.tips).filter(id => String(owner[id]) !== String(n));
        add(row.exercises.length > 0 && row.tips.length > 0 && foreign.length === 0, `${tier}${L}: skill ${n} shows only its own exercises and tips`, { foreign, row });
        if (lang === 'te') {
          const words = row.exercises.concat(row.tips).filter(id => !r.text.includes(teText[id]));
          add(words.length === 0 && /[\u0C00-\u0C7F]/.test(row.badge), `te: skill ${n} prints its own exercise and tip in Telugu`, words);
        }
        add(!row.cropSrc && !row.saw, `${tier}${L}: skill ${n} does not repeat page 1's crop and words on page 2`, row);
        add(row.model, `${tier}${L}: skill ${n} has a drawn model to copy`, row);
        const sheet = sheets.find(w => w.factors.includes(n));
        add(sheet ? (row.sheet || '').includes('/worksheets/' + sheet.id + '.pdf') : !row.sheet, `${tier}${L}: skill ${n} links its own worksheet`, { want: sheet && sheet.id, got: row.sheet });
        add(r.start === String(n) && r.look.length === 0, `${tier}${L}: page 1 starts with skill ${n}`, { start: r.start, look: r.look });
      }
    }
  }
  await page.evaluate(() => VahiniI18n.setLanguage('en'));

  // Rotation never crosses skills: four re-checks in a row stay with each row's skill.
  let hist = null, crossed = [];
  for (let k = 0; k < 4; k++) {
    const r = await page.evaluate(h => window.__render({ history: h }), hist);
    r.rows.filter(x => x.factor !== 'spelling').forEach(x => x.exercises.concat(x.tips).forEach(id => { if (String(owner[id]) !== x.factor) crossed.push([k, x.factor, id]); }));
    hist = { date: '2026-10-0' + (k + 1), overall: 70, factors: [], practice: r.out.practice };
  }
  add(crossed.length === 0, 'Four re-checks in a row never show another skill\'s exercise or tip', crossed);

  // Characters: only from a same-site map.
  await page.evaluate(() => { window.VAHINI_REPORT_ART = { teacher: 'https://evil.example/a.png', buddy: '//evil.example/b.png', tip: 'javascript:alert(1)', encourage: '/frontend/assets/vahini-logo.png' }; });
  const art = await page.evaluate(() => window.__render({ free: true }));
  add(JSON.stringify(art.art) === '["/frontend/assets/vahini-logo.png"]', 'Pictures other than same-site paths are ignored', art.art);
  await page.evaluate(() => { delete window.VAHINI_REPORT_ART; });
  // A host that sets the map after the report rendered (the sample page loads
  // site.js async): the empty slots fill in, and only from a same-site path.
  const late = await page.evaluate(() => {
    window.__render({ free: true });
    const host = document.querySelector('#report-host') || document.body;
    const before = host.querySelectorAll('img.rp-art').length, slots = host.querySelectorAll('[data-art-slot]').length;
    window.VAHINI_REPORT_ART = { teacher: '/frontend/assets/vahini-logo.png', buddy: 'https://evil.example/b.png', tip: '/frontend/assets/vahini-logo.png', encourage: '/frontend/assets/vahini-logo.png' };
    VahiniReport.fillReportArt(document);
    const after = [...host.querySelectorAll('img.rp-art')].map(i => i.getAttribute('data-art'));
    delete window.VAHINI_REPORT_ART;
    return { before, slots, after };
  });
  add(late.before === 0 && late.slots > 0 && late.after.includes('teacher') && late.after.includes('encourage') && !late.after.includes('buddy'),
    'A picture map set after the report fills the empty slots, same-site only', late);

  // Words for children: nothing rendered uses an avoided word.
  const avoid = /\b(weak|poor|bad|wrong|problem|inadequate|fail|lowest|mistake)/i;
  add([free, spelled, pro, mastering].every(r => !avoid.test(r.text)) && !/—/.test(free.text + pro.text), 'Rendered report text avoids the listed words and em dashes');
  add(errors.length === 0, 'No page errors', errors);

  // ---- Your progress: save, compare, rotation input, export, import, forget
  await page.evaluate(() => {
    localStorage.clear();
    const f = (scores) => Object.entries(scores).map(([n, score]) => ({ n: Number(n), score }));
    localStorage.setItem('vahini_history', JSON.stringify([
      { name: 'Asha', date: '2026-09-20', overall: 60, factors: f({ 1: 6.0, 5: 4.0, 7: 7.0, 8: 5.0 }) },
      { name: 'Ravi', date: '2026-09-25', overall: 50, factors: f({ 1: 5.0 }) },
      { name: 'Asha', date: '2026-10-01', overall: 66, factors: f({ 1: 7.2, 5: 4.4, 7: 7.1, 8: 5.6 }) },
    ]));
    const results = [1, 5, 7, 8].map(n => ({ n, score: { 1: 7.5, 5: 5.0, 7: 6.6, 8: 5.7 }[n] }));
    const entry = VahiniProgress.entryFrom('Asha', 70, [{ id: 'structure', avg100: 60 }], results, { exercises: { 5: ['size.two-line-ladder'] }, tips: { 5: ['size.match-the-x'] } });
    VahiniProgress.save(entry);
    VahiniProgress.mount(document.getElementById('report-host'), { name: 'Asha', current: entry });
  });
  const panel = await page.evaluate(() => {
    const p = document.getElementById('progress-panel');
    return {
      intro: p.querySelector('p').textContent,
      list: [...p.querySelectorAll('.pp-list li')].map(e => e.textContent),
      options: [...p.querySelectorAll('#pp-compare option')].map(o => o.textContent),
      rows: [...p.querySelectorAll('.pp-compare li')].map(e => [e.dataset.factor, e.dataset.kind, e.textContent]),
      keep: p.querySelector('.pp-keep a').getAttribute('href'),
      saved: VahiniProgress.last('Asha'),
    };
  });
  add(/saved on this device/.test(panel.intro) && /The name stays here\. Vahini keeps only the scores/.test(panel.intro) && panel.list.length === 3 && /this check/.test(panel.list[0]),
    'The panel lists this writer\'s saved checks, newest first', panel.list);
  add(panel.options.length === 2 && /1 October/.test(panel.options[0]), 'Compare defaults to the previous check', panel.options);
  const kinds = Object.fromEntries(panel.rows.map(r => [r[0], r[1]]));
  add(kinds[5] === 'up' && /↑ \+0\.6/.test(panel.rows.find(r => r[0] === '5')[2]) && kinds[8] === 'same' && kinds[7] === 'tries'
    && /needs a few more tries/.test(panel.rows.find(r => r[0] === '7')[2]) && !panel.rows.some(r => /↓/.test(r[2])),
    'Rises of 0.3 get an up arrow; a fall says it needs a few more tries, never a down arrow', panel.rows);
  add(panel.keep === '/progress.html', 'The panel points to Keep my pages for other devices');
  add(JSON.stringify(panel.saved.practice) === JSON.stringify({ exercises: { 5: ['size.two-line-ladder'] }, tips: { 5: ['size.match-the-x'] } }),
    'A saved check keeps the exercise and tip ids it printed');
  await page.selectOption('#pp-compare', '1');
  const older = await page.evaluate(() => [...document.querySelectorAll('.pp-compare li')].map(e => [e.dataset.factor, e.dataset.kind]));
  add(JSON.stringify(Object.fromEntries(older)) === JSON.stringify({ 1: 'up', 5: 'up', 7: 'tries', 8: 'up' }), 'Choosing an earlier check changes the comparison', older);
  add(await page.evaluate(() => getComputedStyle(document.getElementById('progress-panel')).display) !== 'none', 'The panel shows on screen');
  await page.emulateMedia({ media: 'print' });
  add(await page.evaluate(() => getComputedStyle(document.getElementById('progress-panel')).display) === 'none', 'The panel is never printed');
  await page.emulateMedia({ media: 'screen' });

  const [download] = await Promise.all([page.waitForEvent('download'), page.click('#pp-download')]);
  const file = JSON.parse(await readFile(await download.path(), 'utf8'));
  add(file.format === 'vahini-progress' && file.version === 1 && file.checks.length === 3 && file.checks.every(c => c.name === 'Asha')
    && !/photo|data:image|url/i.test(JSON.stringify(file)), 'The progress file holds only this writer\'s checks, no photo', { checks: file.checks.length });

  await page.click('#pp-forget');
  add(await page.evaluate(() => !document.getElementById('pp-confirm').hidden && VahiniProgress.forName('Asha').length === 3), 'Forget asks before removing anything');
  await page.click('#pp-forget-yes');
  add(await page.evaluate(() => VahiniProgress.forName('Asha').length === 0 && VahiniProgress.forName('Ravi').length === 1), 'Forget removes only this writer\'s checks');

  const extra = { ...file, checks: [...file.checks, file.checks[0], { ...file.checks[1], unknown: 'kept out' }] };
  await page.setInputFiles('#pp-file', { name: 'progress.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(extra)) });
  await page.waitForFunction(() => /Loaded/.test(document.getElementById('pp-status').textContent));
  const merged = await page.evaluate(() => ({ asha: VahiniProgress.forName('Asha'), status: document.getElementById('pp-status').textContent }));
  add(merged.asha.length === 3 && merged.asha.every(e => !('unknown' in e)) && /Loaded 3/.test(merged.status), 'Loading merges, removes repeats and drops unknown fields', merged);
  await page.setInputFiles('#pp-file', { name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ ...file, checks: [{ ...file.checks[0], factors: [{ n: 99, score: 4 }] }] })) });
  await page.waitForFunction(() => /could not read/.test(document.getElementById('pp-status').textContent));
  add(await page.evaluate(() => VahiniProgress.forName('Asha').length === 3), 'A file with a malformed check loads nothing');
  await page.setInputFiles('#pp-file', { name: 'other.json', mimeType: 'application/json', buffer: Buffer.from('{"hello":1}') });
  await page.waitForFunction(() => /not a Vahini progress file/.test(document.getElementById('pp-status').textContent));
  add(true, 'A file of another kind is refused');
  const capped = await page.evaluate(() => {
    const many = Array.from({ length: 70 }, (_, i) => ({ name: 'Cap', date: '2026-0' + (1 + (i % 9)) + '-' + String(1 + (i % 28)).padStart(2, '0'), overall: i, factors: [] }));
    VahiniProgress.merge(many.map(VahiniProgress.clean));
    return VahiniProgress.load().length;
  });
  add(capped === 60, 'Saved checks are capped at 60', capped);

  // ---- Receipts for stored reports (backend/report_store.py, 2026-10-16)
  const calls = [];
  await page.route('**/api/v2/reports/**', (route) => {
    const req = route.request();
    calls.push({ method: req.method(), path: new URL(req.url()).pathname, token: req.headers()['x-report-token'] || null, body: req.postData() || '' });
    route.fulfill({ status: req.method() === 'DELETE' ? 204 : 200, contentType: 'application/json', body: '{"renewed":1}' });
  });
  const receiptId = 'a'.repeat(32);
  const receiptToken = 'B'.repeat(43);
  const kept = await page.evaluate(([id, token]) => {
    localStorage.clear();
    VahiniProgress.receiptFor({ id, token, expires: '2027-10-03', note: 'Bheema' });
    const first = VahiniProgress.save(VahiniProgress.entryFrom('Tara', 70, [], [{ n: 1, score: 7 }], null));
    const second = VahiniProgress.save(VahiniProgress.entryFrom('Tara', 72, [], [{ n: 1, score: 7.2 }], null));
    VahiniProgress.renew(location.href);
    return {
      first, second,
      bad: VahiniProgress.clean({ ...first, receipt: { id: '../x', token } }),
    };
  }, [receiptId, receiptToken]);
  add(kept.first.receipt && kept.first.receipt.id === receiptId && kept.first.receipt.token === receiptToken
    && !('note' in kept.first.receipt) && !('receipt' in kept.second) && kept.bad === null,
    'A check keeps only its own receipt, rebuilt from known fields', kept);
  await page.evaluate(() => VahiniProgress.forget('Tara'));
  await delay(300);
  const renewCall = calls.find((c) => c.method === 'POST' && c.path === '/api/v2/reports/renew');
  const deleteCall = calls.find((c) => c.method === 'DELETE');
  add(renewCall && JSON.stringify(JSON.parse(renewCall.body)) === JSON.stringify({ receipts: [{ id: receiptId, token: receiptToken }] }),
    'A new check renews the earlier receipts and sends nothing else', calls);
  add(deleteCall && deleteCall.path === '/api/v2/reports/' + receiptId && deleteCall.token === receiptToken,
    'Forget deletes the stored reports with their receipts', calls);
  add(!calls.some((c) => /Tara|Asha|Bheema/.test(c.body + c.path)), 'No name ever goes with a receipt', calls);
  await browser.close();
} catch (error) {
  add(false, 'Practice report checks ran', String(error && error.stack || error));
} finally {
  server.kill('SIGTERM');
}
for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.name}${r.ok || !r.detail ? '' : ' :: ' + r.detail}`);
const failed = results.filter(r => !r.ok).length;
console.log(`\nSummary: ${results.length - failed}/${results.length} checks passing`);
process.exit(failed ? 1 : 0);
