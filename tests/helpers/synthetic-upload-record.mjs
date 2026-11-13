/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// analyser.html records sanitized upload metadata separately from the
// opt-in /persist/keep/* photo store. This synthetic fixture has no saved
// consent decision. Do not accept an arbitrary /persist/* write here.
export function isSyntheticUploadRecord(record) {
  const hasKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
  return !!(hasKeys(record, ['fileName', 'mimeType', 'source', 'meta'])
    && record.fileName === 'photo.png'
    && record.mimeType === 'image/png'
    && record.source === 'file-input'
    && hasKeys(record.meta, ['size', 'modified', 'page', 'consent'])
    && Number.isSafeInteger(record.meta.size) && record.meta.size > 0
    && Number.isSafeInteger(record.meta.modified) && record.meta.modified >= 0
    && record.meta.page === '/frontend/analyser.html'
    && record.meta.consent === null);
}
