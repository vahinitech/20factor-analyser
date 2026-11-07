/* SPDX-License-Identifier: AGPL-3.0-only */
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { liveRecognitionOptions } from './helpers/live-recognition-options.mjs';

const key = 'vh_' + randomBytes(24).toString('hex');
assert.deepEqual(liveRecognitionOptions({}), { base: 'http://localhost:8080', key: '', tier: 'free' });
for (const base of ['https://stage.vahinitech.com', 'http://localhost:8080', 'http://127.0.0.1:8080', 'http://[::1]:8080']) {
  const opts = liveRecognitionOptions({ VAHINI_BASE_URL: base, VAHINI_PRO_KEY: key });
  assert.equal(opts.tier, 'pro');
  assert.ok(opts.key === key);
}
for (const base of ['https://vahinitech.com', 'https://stage.vahinitech.com.other.invalid', 'http://stage.vahinitech.com', 'https://other.invalid', 'https://user:password@stage.vahinitech.com', 'https://stage.vahinitech.com?key=example', 'https://stage.vahinitech.com#example', 'file:///tmp/report']) {
  assert.throws(() => liveRecognitionOptions({ VAHINI_BASE_URL: base, VAHINI_PRO_KEY: key }));
}
assert.throws(() => liveRecognitionOptions({ VAHINI_PRO_KEY: 'invalid' }));
console.log('PASS live Pro options: staging/local only; credentials, query URLs and insecure remote hosts rejected');
