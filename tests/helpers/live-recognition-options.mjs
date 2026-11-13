/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// Optional credentials may only reach the authorized staging host or a
// developer's local stack. This creates no key and grants no access.
export function liveRecognitionOptions(env = process.env) {
  let base;
  try { base = new URL(env.VAHINI_BASE_URL || 'http://localhost:8080'); }
  catch { throw new Error('The recognition base URL is invalid'); }
  if (base.username || base.password || base.search || base.hash || !['http:', 'https:'].includes(base.protocol)) {
    throw new Error('Use an HTTP(S) base URL without credentials, query or fragment');
  }
  const key = env.VAHINI_PRO_KEY || '';
  if (key) {
    const local = ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname);
    if (!local && base.origin !== 'https://stage.vahinitech.com') {
      throw new Error('A Pro test key is allowed only on https://stage.vahinitech.com or a local test stack');
    }
    if (!/^vh_[A-Za-z0-9_-]+$/.test(key)) throw new Error('The optional Pro test key has an invalid format');
  }
  return { base: base.href.replace(/\/$/, ''), key, tier: key ? 'pro' : 'free' };
}
