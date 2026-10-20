/* SPDX-License-Identifier: AGPL-3.0-only */
// Runs a frontend source file in a vm context under its absolute path.
// V8 names a script by the filename it was compiled with; without one the
// script is "evalmachine.<anonymous>" and c8 cannot tell which file its
// lines belong to, so the coverage report (#232) would miss the file.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

export function runSource(file, context) {
  const filename = path.resolve(file instanceof URL ? fileURLToPath(file) : file);
  return vm.runInContext(fs.readFileSync(filename, 'utf8'), context, { filename });
}
