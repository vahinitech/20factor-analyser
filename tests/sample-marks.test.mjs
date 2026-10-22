/* SPDX-License-Identifier: AGPL-3.0-only */
// The circles on the analyser page's sample (frontend/analyser.html) are the
// places the analyser itself marked on that page: each one a "look" place in
// scripts/core/sample-report-data.js (factor_regions[n].places), drawn on the
// same 960x1280 image. Regenerating the sample without moving the circles
// fails here instead of circling the wrong words.
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const html = readFileSync('frontend/analyser.html', 'utf8');
const dataText = readFileSync('frontend/scripts/core/sample-report-data.js', 'utf8');
const data = JSON.parse(dataText.slice(dataText.indexOf('{'), dataText.lastIndexOf('}') + 1));

const marks = [...html.matchAll(/<ellipse class="mark-[a-z]+" data-factor="(\d+)" data-bbox="([\d,]+)" cx="([\d.]+)" cy="([\d.]+)"/g)]
  .map((m) => ({ factor: m[1], bbox: m[2].split(',').map(Number), cx: Number(m[3]), cy: Number(m[4]) }));
assert.ok(marks.length >= 3, 'the sample shows at least three circled places');

for (const mark of marks) {
  const region = data.factor_regions[mark.factor];
  assert.ok(region, `factor ${mark.factor} has marked places in the sample`);
  assert.equal(region.coordinate_space, 'processed-image');
  assert.deepEqual(region.source_size, [960, 1280]);
  const place = (region.places || []).find((p) => p.role === 'look' && p.bbox.join(',') === mark.bbox.join(','));
  assert.ok(place, `factor ${mark.factor}: ${mark.bbox} is a "look" place in the sample data`);
  const [x, y, w, h] = mark.bbox;
  assert.equal(mark.cx, x + w / 2, 'circle centred on its place');
  assert.equal(mark.cy, y + h / 2, 'circle centred on its place');
}
console.log(`PASS ${marks.length} circles are places the analyser marked on the sample`);

// The SVG draws the photo at 960x1280, the sample's processed-image size.
assert.match(html, /<image href="assets\/samples\/handwriting-sample\.jpg" x="0" y="0" width="960" height="1280"\/>/);
const jpg = readFileSync('frontend/assets/samples/handwriting-sample.jpg');
let i = 2, size = null;
while (i < jpg.length) {
  const marker = jpg[i + 1], len = jpg.readUInt16BE(i + 2);
  if (marker >= 0xc0 && marker <= 0xc3) { size = [jpg.readUInt16BE(i + 7), jpg.readUInt16BE(i + 5)]; break; }
  i += 2 + len;
}
assert.deepEqual(size, [960, 1280], 'the sample photo is 960x1280, the space the circles use');
console.log('PASS the photo is the 960x1280 image the places were measured on');
