// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// The free-check page's questions (SEO step 1, owner 2026-10-14): the
// FAQPage structured data holds exactly the questions a visitor sees, with
// the same answers, so search engines are never told something the page
// does not show. The page keeps its title short enough for a results page.
import assert from 'node:assert/strict';
import fs from 'node:fs';

const page = fs.readFileSync(new URL('../frontend/analyser.html', import.meta.url), 'utf8');
// Text as a reader sees it: tags removed until none are left, then each
// entity decoded once, in a single pass (so "&amp;lt;" stays "&lt;").
const ENTITIES = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#x27;': "'", '&#39;': "'" };
const plain = (s) => {
  let text = s, before;
  do { before = text; text = text.replace(/<[^<>]*>/g, ''); } while (text !== before);
  return text.replace(/&(?:amp|lt|gt|quot|#x27|#39);/g, (e) => ENTITIES[e]).trim();
};

const visible = [...page.matchAll(/<details(?: open)?><summary>([\s\S]*?)<\/summary>\s*<p>([\s\S]*?)<\/p><\/details>/g)]
  .map(m => [plain(m[1]), plain(m[2])]);
const blocks = [...page.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map(m => JSON.parse(m[1]));
const faq = blocks.find(b => b['@type'] === 'FAQPage');
assert.ok(faq, 'an FAQPage block');
const marked = faq.mainEntity.map(q => [q.name, q.acceptedAnswer.text]);
assert.deepEqual(marked, visible, 'FAQPage questions and answers match the page');
assert.ok(visible.length >= 15, `at least 15 questions, got ${visible.length}`);

const service = blocks.find(b => b['@type'] === 'Service');
assert.ok(service && !service.offers && !service.aggregateRating, 'a Service block with no invented price or rating');

const title = plain(page.match(/<title>([\s\S]*?)<\/title>/)[1]);
assert.ok(title.length <= 55, `title fits a results page: ${title.length} characters`);
assert.ok(!/—/.test(page.split('<script')[0] + visible.flat().join(' ')), 'no em dashes');
console.log(`check-page-faq: ${visible.length} questions marked up as shown; title ${title.length} characters`);
