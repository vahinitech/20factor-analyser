// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// An upload sends no reference passage unless the writer picks one. The
// server rewrites every read line that is close enough to the passage into
// the passage itself (backend/reading/recognizer.py align_to_expected), so a default
// passage would quietly replace a child's own words with the pangram.
import assert from 'node:assert/strict';
import fs from 'node:fs';

const app = fs.readFileSync(new URL('../frontend/src/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('function setupPassages(');
assert.ok(start >= 0, 'setupPassages() exists');
const body = app.slice(start, app.indexOf('\n}\n', start));

assert.match(body, /state\.expected = '';/, 'the passage starts empty');
assert.doesNotMatch(body, /state\.expected = PASSAGES\[0\]/, 'no default passage');
const cards = body.slice(body.indexOf('list.innerHTML'), body.indexOf("addEventListener"));
assert.doesNotMatch(cards, /'sel'|passage sel/, 'no passage card starts selected');
// Picking a passage still sends it.
assert.match(body, /state\.expected = PASSAGES\.find\(/, 'a picked passage is sent');

console.log('expected-text: an upload sends no passage unless one is picked');
