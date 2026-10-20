/* SPDX-License-Identifier: AGPL-3.0-only */
// The English writing-craft checks run only on a page the server read as
// English (#221). Counting non-ASCII characters is the fallback for a
// response with no language information.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const context={};context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/src/engine/craft.js','utf8'),context);
vm.runInContext(fs.readFileSync('frontend/src/engine/compact-client.js','utf8'),context);
const craft=context.VahiniCraft;
const reading=(script,...languages)=>({script,languages});

// German: mostly ASCII, and "u." (und) looks like the English text-speak "u".
const german='Wir kaufen Brot u. Butter für das Frühstück.';
assert.equal(craft.kindOf(german,null),'prose','the ASCII count alone takes German for English');
assert.ok(craft.analyze(german,null).findings.length>0,'without language information the English rules fire on German');
const de=craft.analyze(german,null,reading('latin','de'));
assert.equal(de.kind,'nonlatin');
assert.equal(de.runGrammar,false);
assert.equal(de.findings.length,0);
assert.equal(de.title,'Writing-craft (English) not applied');
assert.match(de.intro,/not to be in English/);
console.log('PASS German read as de: English writing-craft not applied');

// English: the checks still run.
const english='Dear Sir,\nI look forward to hear from you.\nYours Sincerely,\nMalli';
const en=craft.analyze(english,null,reading('latin','en'));
assert.equal(en.kind,'letter');
assert.equal(en.runGrammar,true);
assert.ok(en.findings.some(f=>/look forward to/.test(f.msg)));
assert.ok(en.findings.some(f=>/sign-off/.test(f.msg)));
assert.equal(craft.analyze(english,null,reading('latin','en-IN')).kind,'letter','a regional English tag is English');
console.log('PASS English read as en: writing-craft runs');

// Telugu written in Latin letters, read by the Telugu reader.
const romanTelugu='Maa ammamma ur lo undi. Nenu repu velthanu.';
assert.equal(craft.kindOf(romanTelugu,null),'prose','the ASCII count alone takes Telugu in Latin letters for English');
const te=craft.analyze(romanTelugu,null,reading('latin','te'));
assert.equal(te.kind,'nonlatin');
assert.equal(te.findings.length,0);
console.log('PASS Telugu in Latin letters read as te: English writing-craft not applied');

// A page read partly in another language is not an English page, and
// neither is Latin text in another script's majority.
assert.equal(craft.readsEnglish(reading('latin','en','te')),false);
assert.equal(craft.readsEnglish(reading('telugu','en')),false);
assert.equal(craft.readsEnglish(reading('mixed','en')),false);
assert.equal(craft.readsEnglish(reading('latin','en')),true);

// Spelling: the same misspelling is checked only on an English reading.
const misspelt='I recieve the letter.';
assert.equal(craft.checkSpelling(misspelt,reading('latin','en')).length,1);
assert.equal(craft.checkSpelling(misspelt,reading('latin','de')).length,0);
assert.equal(craft.checkSpelling(misspelt,reading('latin','te')).length,0);
console.log('PASS spelling runs only on a page read as English');

// No language information (an older cached response, or nothing read):
// the ASCII count decides, as before.
for(const none of [undefined,null,{},reading(null),reading('latin'),reading(null,'en')]){
  assert.equal(craft.readsEnglish(none),null);
  assert.equal(craft.checkSpelling(misspelt,none).length,1);
}
assert.equal(craft.kindOf('నేను రేపు బడికి వెళ్తాను',null),'nonlatin');
assert.equal(craft.kindOf(english,null),'letter');
console.log('PASS no language information: non-ASCII count is the fallback');

// The compact report's comparability reaches the analysis the report reads.
const file=fs.readdirSync('backend/catalogs').find(n=>n.endsWith('.json'));
const catalog=JSON.parse(fs.readFileSync('backend/catalogs/'+file));
const response={schema_version:'2.1',format:'compact',catalog_version:catalog.version,ok:true,access:{tier:'free'},summary:{score:60},factors:[1,5,7,8,18].map(n=>({n,s:6,st:'e'}))};
const decoded=context.VahiniCompact.decode({...response,comparability:{script:'latin',languages:['te']}},catalog);
assert.deepEqual(JSON.parse(JSON.stringify(decoded.analysis.comparability)),{script:'latin',languages:['te']});
assert.equal(context.VahiniCompact.decode(response,catalog).analysis.comparability,null);
console.log('PASS compact client passes the reading languages to the report');
