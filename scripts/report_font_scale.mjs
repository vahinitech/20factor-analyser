// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// How much a script's report face must be scaled (its @font-face
// size-adjust in frontend/styles/report-fonts.css) so its letters draw at
// the size of the English face they sit beside (docs/12-report-rules.md,
// "Every language keeps the English report"). A script letter's body,
// measured on base letters without vowel signs, is matched to the English
// face's capital height for text faces: script letters are read like
// capitals, and at the English small-letter height they are too small to
// read. A handwriting face (Caveat) is written mostly in small letters with
// capitals far above them, so its script partner is matched to the middle
// of its small-letter and capital heights.
//
//     node scripts/report_font_scale.mjs          # print the table
//     node scripts/report_font_scale.mjs --check  # fail if the CSS differs by over 2%
//
// Needs Playwright's Chromium (the CI browser image has it).
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';

const FONTS = new URL('../frontend/assets/fonts/', import.meta.url);
// Each script face, the English face it sits beside, and the letters
// its body is measured on. A new script adds one row per face here.
export const FACES = [
  { family: 'Vahini Script Serif', script: 'telugu', file: 'NotoSerifTelugu-Regular.woff2', partner: 'Spectral-Regular.ttf', letters: 'మనవచరసలదబ', match: 'cap' },
  { family: 'Vahini Script Sans', script: 'telugu', file: 'NotoSansTelugu-Regular.woff2', partner: 'HankenGrotesk.ttf', letters: 'మనవచరసలదబ', match: 'cap' },
  { family: 'Vahini Script Hand', script: 'telugu', file: 'NotoSansTelugu-Regular.woff2', partner: 'Caveat.ttf', letters: 'మనవచరసలదబ', match: 'middle' },
];
const b64 = f => readFileSync(new URL(f, FONTS)).toString('base64');

export async function measure(browser) {
  const page = await browser.newPage();
  const out = await page.evaluate(async faces => {
    const c = document.createElement('canvas').getContext('2d');
    const h = (fam, s) => { c.font = `100px "${fam}"`; const m = c.measureText(s); return m.actualBoundingBoxAscent + m.actualBoundingBoxDescent; };
    const rows = [];
    for (const f of faces) {
      const script = new FontFace('script-' + f.file, `url(data:font/woff2;base64,${f.data})`);
      const latin = new FontFace('latin-' + f.partner, `url(data:font/ttf;base64,${f.pdata})`);
      document.fonts.add(await script.load()); document.fonts.add(await latin.load());
      const body = h('script-' + f.file, f.letters), cap = h('latin-' + f.partner, 'HEIMNXZ');
      const small = h('latin-' + f.partner, 'xzvwnmuraceos');
      const want = f.match === 'middle' ? (cap + small) / 2 : cap;
      rows.push({ family: f.family, script: f.script, scale: Math.round(100 * want / body) });
    }
    return rows;
  }, FACES.map(f => ({ ...f, data: b64(f.file), pdata: b64(f.partner) })));
  await page.close();
  return out;
}

export function declared() {
  const css = readFileSync(new URL('../frontend/styles/report-fonts.css', import.meta.url), 'utf8');
  const out = {};
  for (const m of css.matchAll(/@font-face\s*\{[^}]*font-family:'([^']+)'[^}]*size-adjust:(\d+)%[^}]*\}/g)) out[m[1]] = Number(m[2]);
  return out;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const browser = await chromium.launch();
  try {
    const rows = await measure(browser), css = declared();
    let bad = 0;
    for (const r of rows) {
      const have = css[r.family];
      const ok = have != null && Math.abs(have - r.scale) <= 2;
      if (!ok) bad += 1;
      console.log(`${r.family} (${r.script}): measured ${r.scale}%, report-fonts.css ${have ?? 'none'}%${ok ? '' : '  <- differs'}`);
    }
    if (process.argv.includes('--check') && bad) process.exit(1);
  } finally { await browser.close(); }
}
