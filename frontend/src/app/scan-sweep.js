/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   While the server checks the photo, the page sweeps it line by line
   (owner, 2026-10-25): finished lines turn green, the current line gets a
   box on each group of letters as the sweep passes, and under the photo
   "Reading line 3 of 4" with one bar a line.

   The lines are the photo's own: rows with enough dark pixels on a 400 px
   copy, found here in the browser. The timing is the page's, not the
   server's reading. The sweep goes over the lines again until the answer
   comes, and stops when the screen changes. For people who turn off
   motion, the current line is marked without the moving sweep. Nothing is
   sent and nothing is kept.
   ========================================================================= */
(function (global) {
'use strict';
const doc = global.document;
const WIDTH = 400;          // the copy the lines are found on
const LINE_MS = 1400;       // one line's sweep
const TICK_MS = 70;
const MAX_LINES = 12;

/* Lines and the groups of letters on each, as fractions of the photo. */
function findLines(img){
  const w = WIDTH, h = Math.max(1, Math.round(img.naturalHeight * WIDTH / Math.max(1, img.naturalWidth)));
  const canvas = doc.createElement('canvas'); canvas.width = w; canvas.height = h;
  const cx = canvas.getContext('2d', { willReadFrequently: true });
  if (!cx) return [];
  cx.drawImage(img, 0, 0, w, h);
  let px;
  try{ px = cx.getImageData(0, 0, w, h).data; }catch(_e){ return []; }
  const lum = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) lum[i] = (px[i*4] + px[i*4+1] + px[i*4+2]) / 3;
  // Ink is clearly darker than its own surroundings (a 17 px square), so a
  // shadow or pale paper texture is not ink.
  const sat = new Float64Array((w + 1) * (h + 1));
  for (let y = 0; y < h; y++){
    let run = 0;
    for (let x = 0; x < w; x++){ run += lum[y * w + x]; sat[(y + 1) * (w + 1) + x + 1] = sat[y * (w + 1) + x + 1] + run; }
  }
  const mean = (x, y, r) => {
    const xa = Math.max(0, x - r), xb = Math.min(w, x + r + 1), ya = Math.max(0, y - r), yb = Math.min(h, y + r + 1);
    return (sat[yb * (w + 1) + xb] - sat[ya * (w + 1) + xb] - sat[yb * (w + 1) + xa] + sat[ya * (w + 1) + xa]) / ((yb - ya) * (xb - xa));
  };
  // Only on the paper: what is bright over a wider square (49 px), so a
  // dark desk is left out but dense writing is not.
  const wide = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) wide[y * w + x] = mean(x, y, 24);
  const light = Float32Array.from(wide).sort();
  const paper = 0.6 * light[Math.floor(light.length * 0.9)];
  const ink = new Uint8Array(w * h);
  for (let y = 0; y < h; y++){
    for (let x = 0; x < w; x++){
      const i = y * w + x;
      if (wide[i] < paper) continue;
      const bg = mean(x, y, 8);
      ink[i] = lum[i] < bg - Math.max(18, bg * 0.12) ? 1 : 0;
    }
  }
  const dark = (x, y) => ink[y * w + x] === 1;
  const x0 = Math.round(w * 0.02), x1 = w - x0;
  const rows = [];
  for (let y = 0; y < h; y++){ let n = 0; for (let x = x0; x < x1; x++) n += ink[y * w + x]; rows.push(n); }
  // A row of writing stands well above the page's usual row, which a
  // binding, ruled lines or a margin keep above nothing.
  const sorted = rows.slice().sort((p, q) => p - q);
  const base = sorted[Math.floor(h * 0.5)], high = sorted[Math.floor(h * 0.95)];
  const rowMin = Math.max(3, base + 0.3 * (high - base));
  const bands = [];
  let start = -1, gap = 0;
  for (let y = 0; y <= h; y++){
    const on = y < h && rows[y] >= rowMin;
    if (on){ if (start < 0) start = y; gap = 0; continue; }
    if (start >= 0 && ++gap > 2){
      const end = y - gap + 1;
      if (end - start >= 4 && end - start < h / 4) bands.push([start, end]);
      start = -1; gap = 0;
    }
  }
  return bands.slice(0, MAX_LINES).map(([a, b]) => {
    const groups = [];
    let c = -1;
    for (let x = x0; x <= x1; x++){
      let on = false;
      if (x < x1) for (let y = a; y < b && !on; y++) on = dark(x, y);
      if (on && c < 0) c = x;
      if (!on && c >= 0){
        const last = groups[groups.length - 1];
        if (last && c - last[1] <= 3) last[1] = x; else groups.push([c, x]);
        c = -1;
      }
    }
    return { top: a / h, bottom: b / h, groups: groups.map(([l, r]) => [l / w, r / w]) };
  }).filter((line) => line.groups.length);
}

const pct = (v) => (v * 100).toFixed(2) + '%';
function box(cls, left, top, width, height){
  const el = doc.createElement('span');
  el.className = cls;
  el.style.left = pct(left); el.style.top = pct(top); el.style.width = pct(width); el.style.height = pct(height);
  return el;
}

/* Start the sweep over the photo shown in `host`; returns stop(). */
function start(host, img){
  const none = () => {};
  if (!host || !img || !img.naturalWidth) return none;
  const lines = findLines(img);
  if (!lines.length) return none;
  const still = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const frame = doc.createElement('div'); frame.className = 'scan-sweep';
  img.replaceWith(frame); frame.appendChild(img);
  const layer = doc.createElement('div'); layer.className = 'scan-layer'; layer.setAttribute('aria-hidden', 'true');
  frame.appendChild(layer);
  const cap = doc.createElement('p'); cap.className = 'scan-cap';
  const bars = doc.createElement('div'); bars.className = 'scan-bars'; bars.setAttribute('aria-hidden', 'true');
  lines.forEach(() => bars.appendChild(doc.createElement('span')));
  host.classList.add('is-scanning');
  host.append(cap, bars);

  const bands = lines.map((line) => {
    const left = Math.max(0, line.groups[0][0] - 0.01), right = Math.min(1, line.groups[line.groups.length - 1][1] + 0.01);
    const el = box('scan-line', left, line.top - 0.006, right - left, line.bottom - line.top + 0.012);
    layer.appendChild(el);
    return el;
  });
  let now = -1, marks = [], sweep = null, started = 0;
  function enter(i){
    now = i; started = Date.now();
    marks.forEach((m) => m.remove()); marks = [];
    if (sweep) { sweep.remove(); sweep = null; }
    bands.forEach((el, j) => { el.classList.toggle('done', j < i); el.classList.toggle('now', j === i); });
    [...bars.children].forEach((el, j) => { el.className = j < i ? 'done' : j === i ? 'now' : ''; });
    cap.textContent = `Reading line ${i + 1} of ${lines.length}`;
    if (!still){ sweep = box('scan-beam', 0, lines[i].top - 0.01, 0, lines[i].bottom - lines[i].top + 0.02); layer.appendChild(sweep); }
  }
  function tick(){
    if (!host.isConnected || !host.closest('.screen.on')) { stop(); return; }
    const line = lines[now];
    const done = Math.min(1, (Date.now() - started) / LINE_MS);
    if (!still){
      const edge = line.groups[0][0] + done * (line.groups[line.groups.length - 1][1] - line.groups[0][0]);
      sweep.style.left = pct(edge);
      while (marks.length < line.groups.length && line.groups[marks.length][1] <= edge){
        const [l, r] = line.groups[marks.length];
        const m = box('scan-letters', l, line.top, r - l, line.bottom - line.top);
        layer.appendChild(m); marks.push(m);
      }
    }
    if (done >= 1) enter((now + 1) % lines.length);
  }
  enter(0);
  const timer = global.setInterval(tick, TICK_MS);
  function stop(){ global.clearInterval(timer); }
  return stop;
}

global.VahiniScanSweep = { start, findLines };
})(window);
