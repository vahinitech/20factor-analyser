// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// "What's new" on the check page (owner, 2026-10-24). The lines in
// frontend/whats-new.json are what a parent or teacher would notice, each
// taken from the changelog fragments it names; build_bundle.py writes them
// into the page at build time. This holds the list to that:
// - at most ten, newest first, each with a real date and a source fragment
//   that exists (changelog.d/, or its PRs in CHANGELOG.md once released);
// - one plain line each: no em dashes, nothing internal (CI, tests, docs,
//   refactors), no prices or paid tiers, no Telugu scoring, no diagnosis;
// - the committed page carries only the empty markers, and the built block
//   shows every line in order, the newest on the line and in "Updated".
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';

const root = new URL('../', import.meta.url);
const read = (rel) => fs.readFileSync(new URL(rel, root), 'utf8');
const { items } = JSON.parse(read('frontend/whats-new.json'));

assert.ok(Array.isArray(items) && items.length >= 1 && items.length <= 10, `1 to 10 items, got ${items?.length}`);

const today = new Date().toISOString().slice(0, 10);
const INTERNAL = /\b(CI|refactor\w*|tests?|docs?|benchmarks?|API|endpoint|schema|PR|commits?|lint|coverage|debug|OCR|EXIF|JSON|stage|fixture|factor \d+)\b/i;
const PAID = /(₹|\$|£|€|\bprices?\b|\bpaid\b|\brupees?\b|\bpremium\b|\bpro\b|subscription)/i;
const CLAIMS = /(diagnos|\bcures?\b|dyslexi|dysgraph|ADHD|guarantee|100\s?%)/i;
const changelog = read('CHANGELOG.md');

let previous = '9999-12-31';
for (const item of items) {
  const { date, text, prs, changelog: topics } = item;
  assert.match(date, /^\d{4}-\d{2}-\d{2}$/, `a YYYY-MM-DD date: ${date}`);
  assert.ok(!Number.isNaN(Date.parse(date)) && date <= today, `a real date, not in the future: ${date}`);
  assert.ok(date <= previous, `newest first: ${date} after ${previous}`);
  previous = date;

  assert.equal(typeof text, 'string');
  assert.ok(!/[\n\r]/.test(text) && text.length >= 30 && text.length <= 90, `one line of 30 to 90 characters (${text.length}): ${text}`);
  assert.match(text, /^[A-Z][^]*\.$/, `a sentence: ${text}`);
  assert.ok(!/[—–]/.test(text), `no em or en dashes: ${text}`);
  assert.ok(!INTERNAL.test(text), `nothing internal: ${text} (${text.match(INTERNAL)?.[0]})`);
  assert.ok(!PAID.test(text), `no prices or paid tiers: ${text}`);
  assert.ok(!/telugu/i.test(text), `nothing about Telugu until it is tested: ${text}`);
  assert.ok(!CLAIMS.test(text), `no diagnosis or cure claims: ${text}`);

  assert.ok(Array.isArray(prs) && prs.length && prs.every(Number.isInteger), `PR numbers for: ${text}`);
  assert.ok(Array.isArray(topics) && topics.length, `changelog fragments for: ${text}`);
  for (const topic of topics) {
    assert.match(topic, /^[\w.-]+$/, `a fragment name: ${topic}`);
    const unreleased = fs.existsSync(new URL(`changelog.d/${topic}.md`, root));
    const released = prs.every((pr) => changelog.includes(`#${pr}`));
    assert.ok(unreleased || released, `changelog.d/${topic}.md exists, or ${prs.map((p) => '#' + p).join(', ')} are in CHANGELOG.md`);
  }
}

// The date is a merge date of one of its PRs, wherever the history is
// there to check (CI checks out two commits, a local clone all of them).
const merged = new Map();
try {
  const log = execFileSync('git', ['log', '--format=%cs %s', 'HEAD'], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  for (const line of log.split('\n')) {
    const [day, ...rest] = line.split(' ');
    for (const m of rest.join(' ').matchAll(/\(#(\d+)\)/g)) if (!merged.has(+m[1])) merged.set(+m[1], day);
  }
} catch { /* no git: the dates were checked above for shape only */ }
let dated = 0;
for (const { date, prs, text } of items) {
  const days = prs.filter((pr) => merged.has(pr)).map((pr) => merged.get(pr));
  if (!days.length) continue;
  dated++;
  assert.ok(days.includes(date), `${text} is dated ${date}; its PRs merged on ${days.join(', ')}`);
}

// Build output, never committed: the page carries only the empty markers.
const page = read('frontend/analyser.html');
const region = page.match(/<!-- whats-new:begin[^>]*-->([\s\S]*?)<!-- whats-new:end -->/);
assert.ok(region, 'analyser.html has the whats-new markers');
assert.equal(region[1].trim(), '', "the What's new block is build output; run 'python frontend/build_bundle.py --strip'");
assert.ok(region.index < page.indexOf('id="start-check"'), 'the line sits above the upload');
assert.match(page, /<script src="scripts\/core\/whats-new\.js(\?v=[0-9a-f]+)?" defer><\/script>/, 'the page loads the line script');

const block = execFileSync('python3', ['frontend/build_bundle.py', '--whats-new'], { cwd: root, encoding: 'utf8' });
// Text as a reader sees it: tags removed until none are left, then each
// entity decoded once, in a single pass (so "&amp;lt;" stays "&lt;").
const ENTITIES = { '&amp;': '&', '&lt;': '<', '&gt;': '>' };
const plain = (s) => {
  let text = s, before;
  do { before = text; text = text.replace(/<[^<>]*>/g, ''); } while (text !== before);
  return text.replace(/&(?:amp|lt|gt);/g, (e) => ENTITIES[e]).replace(/\s+/g, ' ').trim();
};
const listed = [...block.matchAll(/<li><time datetime="([\d-]+)">[^<]+<\/time> <span>([^<]*)<\/span><\/li>/g)].map((m) => [m[1], plain(m[2])]);
assert.deepEqual(listed, items.map((i) => [i.date, i.text]), 'the built list is the JSON, in order');
const line = block.match(/<span class="wn-line">([\s\S]*?)<\/span><span class="wn-count">1 of (\d+)<\/span><span class="wn-all">/);
assert.ok(line && plain(line[1]).endsWith(items[0].text), 'the line shows the newest change before the script runs');
assert.equal(+line[2], items.length, '"1 of" counts every change on the list');
const [y, m, d] = items[0].date.split('-');
const month = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(' ')[+m - 1];
assert.ok(block.includes(`Updated ${+d} ${month} ${y}.`), `"Updated ${+d} ${month} ${y}" in the list`);
assert.ok(!/[—]/.test(block), 'no em dashes in the block');

console.log(`whats-new: ${items.length} lines, newest ${items[0].date}; ${dated} dated against git history`);
