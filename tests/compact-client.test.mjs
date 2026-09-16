/* SPDX-License-Identifier: AGPL-3.0-only */
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const context={};vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/src/engine/compact-client.js','utf8'),context);
const file=fs.readdirSync('backend/catalogs').find(n=>n.endsWith('.json'));
const catalog=JSON.parse(fs.readFileSync('backend/catalogs/'+file));
const response={schema_version:'2.1',format:'compact',catalog_version:catalog.version,ok:true,access:{tier:'free'},summary:{score:60},factors:[1,5,7,8,18].map(n=>({n,s:6,st:'e'}))};
const decoded=context.VahiniCompact.decode(response,catalog);
assert.deepEqual(Array.from(decoded.analysis.results,f=>f.n),[1,5,7,8,18]);
assert(decoded.analysis.results.every(f=>f.score===6&&f.name&&f.evidence));
assert.equal(decoded.analysis.access.tier,'free');
assert.throws(()=>context.VahiniCompact.decode({...response,catalog_version:'wrong'},catalog));
assert.throws(()=>context.VahiniCompact.decode({...response,factors:[{n:99,s:6,st:'e'}]},catalog));
const missing=context.VahiniCompact.decode({...response,factors:[{n:1,s:null,st:'u'}]},catalog);
assert.equal(missing.analysis.results[0].score,null);
assert.equal(missing.analysis.results[0].unmeasured,true);
console.log('PASS compact client: five Free factors, preserved scores, null handling and version validation');

let requests=0;
context.URL=URL;
context.location={href:'https://stage.vahinitech.com/analyser/analyser.html'};
context.fetch=async(url,options)=>{requests++;assert.equal(url.pathname,'/api/v2/catalog/'+catalog.version);assert.equal(options.cache,'force-cache');return {ok:true,json:async()=>catalog};};
await context.VahiniCompact.expand(response,'/api/v2/reports');
await context.VahiniCompact.expand(response,'/api/v2/reports');
assert.equal(requests,1);
console.log('PASS dictionary fetched once and reused for subsequent scans');
