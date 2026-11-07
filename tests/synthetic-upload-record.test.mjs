/* SPDX-License-Identifier: AGPL-3.0-only */
import assert from 'node:assert/strict';
import { isSyntheticUploadRecord } from './helpers/synthetic-upload-record.mjs';

const valid = { fileName: 'photo.png', mimeType: 'image/png', source: 'file-input', meta: { size: 123, modified: 0, page: '/frontend/analyser.html', consent: null } };
assert.equal(isSyntheticUploadRecord(valid), true);
for (const invalid of [null, {}, [], { ...valid, fileName: 'original-name.png' }, { ...valid, photo: 'data:image/png;base64,example' }, { ...valid, text: 'Recognised test words' }, { ...valid, meta: { ...valid.meta, image: 'example' } }, { ...valid, meta: { ...valid.meta, size: 'photo bytes' } }, { ...valid, meta: { ...valid.meta, consent: { decision: 'accept' } } }, { ...valid, meta: { ...valid.meta, page: '/frontend/analyser.html?extra=example' } }]) {
  assert.equal(isSyntheticUploadRecord(invalid), false, 'unexpected content or fields are not metadata-only');
}
console.log('PASS synthetic upload record: exact sanitized metadata only, never a photo, original filename or recognised text');
