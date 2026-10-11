// SPDX-License-Identifier: AGPL-3.0-only
// (c) 2026 Vahini Technologies.
// The report pages link the website theme at /site/design/v1/vahini.css
// (served by vahinitech.com, not by this repository). Browser tests serve
// the committed copy in tests/fixtures/ at that path, so the report is
// rendered and checked with the real theme tokens.
import { readFileSync } from 'node:fs';
const CSS = readFileSync(new URL('./fixtures/vahini-design-v1.css', import.meta.url));
export async function useDesign(target){
  await target.route('**/site/design/v1/vahini.css', route => route.fulfill({ status: 200, contentType: 'text/css', body: CSS }));
}
