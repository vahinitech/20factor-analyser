/* SPDX-License-Identifier: AGPL-3.0-only */
import fs from 'node:fs';
import vm from 'node:vm';
import { runSource } from './run-source.mjs';
import assert from 'node:assert/strict';
const context={};vm.createContext(context);
runSource('frontend/src/engine/compact-client.js',context);
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
// A page the server set upright (#297) says how far it turned it; anything
// but a quarter, half or three-quarter turn is drawn as sent.
for(const turned of [90,180,270])assert.equal(context.VahiniCompact.decode({...response,turned},catalog).turned,turned);
for(const turned of [undefined,0,45,'90',-90,360])assert.equal(context.VahiniCompact.decode({...response,turned},catalog).turned,0);
console.log('PASS compact client: turned is 90, 180 or 270, otherwise 0');
// Practice report (#122): the catalogue's exercises, tips and settings reach
// the renderer; an archived catalogue without them gives none.
for(const name of fs.readdirSync('backend/catalogs')){
  const each=JSON.parse(fs.readFileSync('backend/catalogs/'+name));
  const practice=context.VahiniCompact.decode({...response,catalog_version:each.version},each).analysis.practice;
  if(each.practice){
    assert.deepEqual(JSON.parse(JSON.stringify(practice.factors['5'].exercises)),each.factors.find(f=>f.n===5).exercises);
    assert.deepEqual(JSON.parse(JSON.stringify(practice.tiers)),each.practice.tiers);
  }else assert.equal(practice,null);
}
console.log('PASS compact client: practice catalogue passed to the report when the dictionary has one');

let requests=0;
context.URL=URL;
context.location={href:'https://stage.vahinitech.com/analyser/analyser.html'};
context.fetch=async(url,options)=>{requests++;assert.equal(url.pathname,'/api/v2/catalog/'+catalog.version);assert.equal(options.cache,'force-cache');return {ok:true,json:async()=>catalog};};
await context.VahiniCompact.expand(response,'/api/v2/reports');
await context.VahiniCompact.expand(response,'/api/v2/reports');
assert.equal(requests,1);
console.log('PASS dictionary fetched once and reused for subsequent scans');
