/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Report language ("Print in", docs/10-practice-framework.md section 9).
   Looks up report words by id in strings/<lang>.js, falling back to
   English for any id a language lacks, and keeps the visitor's choice in
   this browser only (localStorage, which may be blocked: then the choice
   lasts for this page). Nothing here leaves the browser.
   ========================================================================= */
(function (global) {
'use strict';
const LANGS = ['en', 'te'];
const KEY = 'vahini_report_lang';
const has = (o, k) => !!o && Object.prototype.hasOwnProperty.call(o, k);
let current = null;

function tables(){ return global.VahiniReportStrings || {}; }
function saved(){
  try{ const v = global.localStorage.getItem(KEY); return LANGS.includes(v) ? v : 'en'; }
  catch(_e){ return 'en'; }
}
function language(){ if (!current) current = saved(); return current; }
function setLanguage(lang){
  current = LANGS.includes(lang) ? lang : 'en';
  try{ global.localStorage.setItem(KEY, current); }catch(_e){ /* this page only */ }
  return current;
}
/* The raw entry for an id: the language's own, else English's. */
function lookup(id, lang){
  const all = tables();
  if (has(all[lang], id)) return all[lang][id];
  return has(all.en, id) ? all.en[id] : undefined;
}
function pick(value, n){
  if (value && typeof value === 'object') return n === 1 && value.one != null ? value.one : value.other;
  return value;
}
function fill(template, vars){
  return String(template).replace(/\{(\w+)\}/g, (m, k)=>(vars && has(vars, k) ? String(vars[k]) : m));
}
function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

/* A translator for one language:
     t(id, vars)          plain text
     t.n(id, n, vars)     with a count: the "one" form when n is 1
     t.html(id, vars)     escaped text, with vars inserted as given HTML
     t.has(id)            whether English defines the id
     t.en(id, vars)       the English text, whatever the language */
function translator(lang){
  const lng = LANGS.includes(lang) ? lang : 'en';
  const raw = (id, n)=>{ const v = pick(lookup(id, lng), n); return v == null ? id : v; };
  const t = (id, vars)=>fill(raw(id), vars);
  t.n = (id, n, vars)=>fill(raw(id, n), { n, ...(vars || {}) });
  t.html = (id, vars)=>esc(raw(id)).replace(/\{(\w+)\}/g, (m, k)=>(vars && has(vars, k) ? String(vars[k]) : m));
  t.has = id=>has(tables().en, id);
  t.en = (id, vars)=>fill(pick(lookup(id, 'en')) ?? id, vars);
  t.lang = lng;
  t.locale = String(lookup('meta.locale', lng) || 'en-GB');
  return t;
}
/* Ids English has and a language lacks (the completeness test reads it). */
function missing(lang){
  const all = tables();
  return Object.keys(all.en || {}).filter(id=>!has(all[lang], id));
}

global.VahiniI18n = { LANGS, language, setLanguage, translator, missing };
})(window);
