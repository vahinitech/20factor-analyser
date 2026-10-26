// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// The line finder behind the sweep on the check page (owner, 2026-10-25;
// frontend/src/app/scan-sweep.js), on drawn pages with known lines:
// - each line of writing is found once, top to bottom, with its groups of
//   letters, and nothing between the lines;
// - a dark desk around the page and ruled lines are not writing;
// - a blank page has no lines, so the page shows the photo still;
// - at most twelve lines.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { runSource } from './run-source.mjs';

// A page of w x h grey levels, drawn by the test, served through a fake
// canvas at the 400 px the finder asks for.
function page(h, draw) {
  const w = 400;
  const g = new Uint8ClampedArray(w * h).fill(235);
  draw((x0, y0, x1, y1, v) => { for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) g[y * w + x] = v; });
  const data = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { data[i * 4] = data[i * 4 + 1] = data[i * 4 + 2] = g[i]; data[i * 4 + 3] = 255; }
  return { naturalWidth: w, naturalHeight: h, data };
}
const context = vm.createContext({
  window: {},
  document: {
    createElement: () => {
      const canvas = { width: 0, height: 0, img: null };
      canvas.getContext = () => ({ drawImage(img) { canvas.img = img; }, getImageData() { return { data: canvas.img.data }; } });
      return canvas;
    },
  },
});
context.window.document = context.document;
runSource('frontend/src/app/scan-sweep.js', context);
const { findLines } = context.window.VahiniScanSweep;

// Words of letters 6 px wide with 2 px between letters and 14 px between
// words, on lines 16 px tall.
const words = (fill, top, count) => {
  let x = 30;
  for (let w = 0; w < count; w++) {
    for (let l = 0; l < 4; l++) { fill(x, top, x + 6, top + 16, 40); x += 8; }
    x += 14;
  }
};
{
  const tops = [40, 90, 140, 190];
  const lines = findLines(page(300, (fill) => tops.forEach((t) => words(fill, t, 6))));
  assert.equal(lines.length, 4, `four lines of writing, found ${lines.length}`);
  lines.forEach((line, i) => {
    assert.ok(Math.abs(line.top * 300 - tops[i]) <= 2 && Math.abs(line.bottom * 300 - (tops[i] + 16)) <= 2, `line ${i + 1} where it was written`);
    assert.equal(line.groups.length, 6, `line ${i + 1}: its six words, letters joined into groups`);
    assert.ok(line.groups[0][0] > 0.07 && line.groups[5][1] < 0.8, `line ${i + 1}: from its first word to its last`);
  });
}
{
  // A dark desk on both sides and ruled lines across the page.
  const lines = findLines(page(300, (fill) => {
    fill(0, 0, 60, 300, 30); fill(340, 0, 400, 300, 30);
    for (let y = 30; y < 300; y += 50) fill(60, y, 340, y + 1, 150);
    [60, 110, 160].forEach((t) => words((a, b, c, d, v) => fill(a + 50, b, c + 50, d, v), t, 4));
  }));
  assert.equal(lines.length, 3, `the desk and the rules are not writing, found ${lines.length} lines`);
  for (const line of lines) assert.ok(line.groups[0][0] >= 0.15 && line.groups[line.groups.length - 1][1] <= 0.85, 'the groups are on the page');
}
{
  assert.deepEqual(Array.from(findLines(page(300, () => {}))), [], 'a blank page has no lines');
}
{
  const lines = findLines(page(800, (fill) => { for (let i = 0; i < 20; i++) words(fill, 20 + i * 38, 3); }));
  assert.equal(lines.length, 12, 'at most twelve lines');
}
console.log('scan-sweep: lines and letter groups found on drawn pages; desk, rules and blank pages left alone');
