/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// Deliberately invented browser data, not an OCR result or accuracy benchmark.
// Keep the six sensor-only skills unavailable on a still photo, including
// stroke order and smoothness (scoring_parts/needs.py), not just Dynamics.
import { readFileSync } from 'node:fs';

export const ALL_FACTORS = Array.from({ length: 20 }, (_, i) => i + 1);
export const FREE_FACTORS = [1, 5, 7, 8, 18];
export const SENSOR_FACTORS = [2, 4, 13, 14, 15, 16];
// Read the documented current dictionary, never whichever archived file
// happens to be first in a directory listing.
const version = readFileSync('docs/11-practice-map.md', 'utf8').match(/catalogue version `([a-f0-9]{20})`/)?.[1];
if (!version) throw new Error('The practice map must identify the current dictionary');
export const catalog = JSON.parse(readFileSync(`backend/catalogs/${version}.json`, 'utf8'));

export function syntheticReport(tier) {
  if (!['free', 'pro'].includes(tier)) throw new Error('Unknown synthetic tier');
  const numbers = tier === 'pro' ? ALL_FACTORS : FREE_FACTORS;
  const factors = numbers.map(n => ({ n, s: SENSOR_FACTORS.includes(n) ? null : 5 + n / 10, st: SENSOR_FACTORS.includes(n) ? 'u' : 'e' }));
  // Invented geometry matches the generated 1200 x 1600 test image. No
  // photo, crop or text from a customer or the real sample run is used.
  const line = { bbox: [100, 260, 900, 70], baseline: [[100, 325], [1000, 310]], midline: [[100, 280], [1000, 265]] };
  return {
    schema_version: '2.1', format: 'compact', catalog_version: catalog.version, ok: true,
    access: { tier, plan_tier: tier, subscription_status: tier === 'pro' ? 'active' : 'anonymous', expires_at: null },
    summary: { score: 61, factor_count: factors.length }, factors,
    locked: ALL_FACTORS.filter(n => !numbers.includes(n)),
    text: 'Synthetic letters on a test page. These words were not recognised by an OCR engine.',
    counts: { lines: 4 },
    recognition: { backend: 'synthetic-browser-fixture', level: 'low', confidence_pct: 70, mean_confidence: 0.7, hand_lines: 4, printed_lines: 0, reliable_lines: 4, assistive_only: true, passage_aligned: false },
    evidence: {
      width: 1200, height: 1600, photo_width: 1200, photo_height: 1600,
      factor_regions: Object.fromEntries(numbers.filter(n => !SENSOR_FACTORS.includes(n)).map(n => [String(n), {
        url: '', status: 'unavailable', bbox: [100, 260, 900, 70], source_size: [1200, 1600], caption: 'Synthetic test geometry',
        ...(n === 8 ? { places: [{ role: 'look', kind: 'gap', region_id: 'synthetic-line-1', measure: 'word_gap', value: 60, reference: 40, deviation: 0.5, line_confidence: 0.7, bbox: [380, 260, 60, 70], direction: 'wider' }] } : {}),
      }])),
      measurements: { lines: 4, slope: { mean_deg: 1, line }, size: { line }, margin: { usual_x: 100, top: 260, off: [] }, reading: { confidence_pct: 70, line } },
    },
  };
}

export async function syntheticPhoto(page) {
  const b64 = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 1200; canvas.height = 1600;
    const pen = canvas.getContext('2d');
    pen.fillStyle = 'white'; pen.fillRect(0, 0, canvas.width, canvas.height);
    pen.strokeStyle = 'black'; pen.lineWidth = 4;
    // Deterministic curves, not a child's handwriting or identifying text.
    for (let row = 0; row < 4; row++) {
      for (let x = 100; x < 1000; x += 55) {
        const y = 300 + row * 200;
        pen.beginPath(); pen.moveTo(x, y); pen.bezierCurveTo(x + 8, y - 60, x + 30, y - 50, x + 38, y); pen.stroke();
      }
    }
    return canvas.toDataURL('image/png').split(',')[1];
  });
  return { name: 'synthetic-browser-page.png', mimeType: 'image/png', buffer: Buffer.from(b64, 'base64') };
}
