// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// The check page and the explainer it frames ask no outside host for a
// script, stylesheet, font, picture or frame (India's DPDP Act, sections
// 8(2) and 9): a child's parent opens this page, and a file fetched from
// someone else's server gives that server the visitor's IP address before
// any choice is made. The explainer used to load React and Babel from
// unpkg and three fonts from Google. They are now files in
// frontend/scripts/vendor (listed in sources.json there) and the website's
// own fonts. A plain link a visitor may press (<a href>) and the canonical
// address are not loads and are allowed.
import assert from 'node:assert/strict';
import fs from 'node:fs';

const root = new URL('../', import.meta.url);
const read = (rel) => fs.readFileSync(new URL(rel, root), 'utf8');
const PAGES = ['frontend/analyser.html', 'frontend/20-factors-explained.html'];
const LOADS = /<(script|img|iframe|source|video|audio|embed)\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']/gi;
const LINKS = /<link\b[^>]*>/gi;
const OUTSIDE = /^(https?:)?\/\//i;

const vendor = JSON.parse(read('frontend/scripts/vendor/sources.json')).map((entry) => entry.file);

for (const page of PAGES) {
  const html = read(page);
  for (const [, tag, src] of html.matchAll(LOADS)) {
    assert.ok(!OUTSIDE.test(src), `${page}: <${tag}> loads ${src} from an outside host`);
    const local = /^scripts\/vendor\/([\w.-]+)/.exec(src);
    if (local) {
      assert.ok(vendor.includes(local[1]), `${page}: ${local[1]} is not listed in scripts/vendor/sources.json`);
      assert.ok(fs.existsSync(new URL(`frontend/scripts/vendor/${local[1]}`, root)), `${page}: ${local[1]} is missing from scripts/vendor`);
    }
  }
  for (const [link] of html.matchAll(LINKS)) {
    const rel = (/\brel\s*=\s*["']([^"']+)["']/i.exec(link) || [])[1] || '';
    const href = (/\bhref\s*=\s*["']([^"']+)["']/i.exec(link) || [])[1] || '';
    if (/\bcanonical\b/i.test(rel)) continue;
    assert.ok(!OUTSIDE.test(href), `${page}: <link rel="${rel}"> asks ${href}, an outside host`);
  }
  assert.ok(!/@import\s+(url\()?["']?(https?:)?\/\//i.test(html), `${page}: a stylesheet import asks an outside host`);
}

// The explainer needs all three libraries, each from this repository.
const explainer = read('frontend/20-factors-explained.html');
for (const file of ['react.development.js', 'react-dom.development.js', 'babel.min.js']) {
  assert.ok(explainer.includes(`src="scripts/vendor/${file}"`), `the explainer loads ${file} from scripts/vendor`);
}

console.log('outside-hosts: ok');
