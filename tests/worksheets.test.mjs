/* SPDX-License-Identifier: AGPL-3.0-only */
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const ctx={window:{}};vm.createContext(ctx);
for(const file of ['worksheet-catalog','worksheets'])vm.runInContext(fs.readFileSync(new URL('../frontend/src/report/'+file+'.js',import.meta.url),'utf8'),ctx);
const ids=results=>Array.from(ctx.window.VahiniWorksheets.recommend(results),x=>x.id);
assert.deepEqual(ids([{n:8,score:2,conf:'measured'},{n:9,score:3,conf:'measured'},{n:5,score:4,conf:'measured'}]),['word-spacing','letter-size']);
assert.deepEqual(ids([{n:8,score:0,conf:'low'},{n:1,score:0,conf:'measured',unmeasured:true},{n:5,score:NaN,conf:'measured'},{n:3,score:null,conf:'measured'},{n:13,score:0,conf:'imu'},{n:14,score:0,conf:'measured'}]),[]);
assert.deepEqual(ids([{n:8,score:7,conf:'measured'}]),[]);
assert.equal(ids([1,5,8,7,17].map((n,i)=>({n,score:i,conf:'measured'}))).length,3);
assert.deepEqual(ids(null),[]);
console.log('PASS worksheet ranking, deduplication, confidence, missing measurements and selection limit');
