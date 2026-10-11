/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Saved checks and "Your progress" (owner request with the practice report,
   2026-10-11, #122). Every check is kept in this browser's localStorage
   ("vahini_history", the last 60, by writer name); sample runs are never
   saved. Nothing here makes a network call: the panel, the progress file
   and "forget" all work on this device only. The panel is screen-only and
   never printed; the printed report keeps comparing with the previous
   check.
   ========================================================================= */
(function (global) {
'use strict';
const KEY = 'vahini_history';
const MAX_ENTRIES = 60;
const SHOWN = 10;
const BETTER_BY = 0.3;   /* #82: smaller moves can be photo noise */
const FILE_FORMAT = 'vahini-progress';
const FILE_VERSION = 1;
const SECTION_IDS = ['structure', 'spatial', 'dynamics', 'style'];
/* Words come from the report's string tables in the chosen "Print in"
   language (strings/<lang>.js, through VahiniI18n), English by default. */
function tr(){
  const i18n = global.VahiniI18n;
  return i18n ? i18n.translator(i18n.language()) : null;
}

function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
const keyOf = name => String(name || '').slice(0, 80).toLowerCase();

/* ---- the store ---------------------------------------------------------- */
function load(){
  try{ const h = JSON.parse(global.localStorage.getItem(KEY) || '[]'); return Array.isArray(h) ? h : []; }
  catch(_e){ return []; }
}
function store(entries){
  try{ global.localStorage.setItem(KEY, JSON.stringify(entries.slice(-MAX_ENTRIES))); return true; }
  catch(_e){ return false; }
}
function forName(name){ const k = keyOf(name); return load().filter(e=>keyOf(e && e.name)===k); }
function last(name){ const mine = forName(name); return mine.length ? mine[mine.length-1] : null; }

/* One saved check, from the report: scores, and the exercise and tip ids
   the report printed so the next one moves on. No text, no photo. */
function entryFrom(name, overall, sections, results, practice){
  return clean({
    name: String(name || '').slice(0, 80), date: new Date().toISOString().slice(0,10),
    overall: Number.isFinite(overall) ? overall : null,
    sections: (sections||[]).filter(s=>s && SECTION_IDS.includes(s.id))
      .map(s=>({id:s.id, avg100:Number.isFinite(s.avg100) ? s.avg100 : null})),
    factors: (results||[]).filter(f=>!f.unmeasured && Number.isFinite(f.score)).map(f=>({n:f.n, score:f.score})),
    practice: practice || undefined,
  });
}
function save(entry){
  if (!entry) return null;
  const all = load(); all.push(entry);
  return store(all) ? entry : null;
}

/* ---- strict shape of a saved check (also what a progress file holds) --- */
const ID_RE = /^[a-z]+\.[a-z0-9-]+$/;
function cleanIds(map){
  if (!map || typeof map !== 'object' || Array.isArray(map)) return null;
  const out = {};
  for (const [k, v] of Object.entries(map)){
    if (!(/^([1-9]|1[0-9]|20|spelling)$/.test(k)) || !Array.isArray(v) || v.length > 5) return null;
    if (!v.every(id=>typeof id === 'string' && ID_RE.test(id))) return null;
    out[k] = v.slice();
  }
  return out;
}
/* A valid entry rebuilt from known fields only, or null. */
function clean(e){
  if (!e || typeof e !== 'object' || Array.isArray(e)) return null;
  if (typeof e.name !== 'string' || e.name.length > 80) return null;
  if (typeof e.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(e.date) || Number.isNaN(Date.parse(e.date))) return null;
  if (!(e.overall === null || (Number.isFinite(e.overall) && e.overall >= 0 && e.overall <= 100))) return null;
  if (!Array.isArray(e.factors) || e.factors.length > 20) return null;
  const seen = new Set();
  const factors = [];
  for (const f of e.factors){
    if (!f || !Number.isInteger(f.n) || f.n < 1 || f.n > 20 || seen.has(f.n)) return null;
    if (!Number.isFinite(f.score) || f.score < 0 || f.score > 10) return null;
    seen.add(f.n); factors.push({n:f.n, score:f.score});
  }
  const out = { name:e.name, date:e.date, overall:e.overall, factors };
  if (e.sections !== undefined){
    if (!Array.isArray(e.sections) || e.sections.length > 4) return null;
    for (const s of e.sections){
      if (!s || !SECTION_IDS.includes(s.id) || !(s.avg100 === null || (Number.isFinite(s.avg100) && s.avg100 >= 0 && s.avg100 <= 100))) return null;
    }
    out.sections = e.sections.map(s=>({id:s.id, avg100:s.avg100}));
  }
  if (e.practice !== undefined){
    const p = e.practice;
    if (!p || typeof p !== 'object') return null;
    const exercises = p.exercises === undefined ? {} : cleanIds(p.exercises);
    const tips = p.tips === undefined ? {} : cleanIds(p.tips);
    if (!exercises || !tips) return null;
    out.practice = { exercises, tips };
  }
  return out;
}
const sameCheck = (a, b)=>JSON.stringify([keyOf(a.name), a.date, a.overall, a.factors]) === JSON.stringify([keyOf(b.name), b.date, b.overall, b.factors]);

/* ---- the progress file -------------------------------------------------- */
function exportFile(name){
  return { format:FILE_FORMAT, version:FILE_VERSION, name:name || '', checks:forName(name).map(clean).filter(Boolean) };
}
/* Throws a message for the visitor when the file is not a progress file. */
function readFile(text){
  let data;
  const t = tr();
  try{ data = JSON.parse(text); }catch(_e){ throw new Error(t('pp.file.not')); }
  if (!data || data.format !== FILE_FORMAT || data.version !== FILE_VERSION || !Array.isArray(data.checks))
    throw new Error(t('pp.file.not'));
  if (data.checks.length > 200) throw new Error(t('pp.file.many'));
  const checks = data.checks.map(clean);
  if (checks.some(c=>!c)) throw new Error(t('pp.file.unreadable'));
  return checks;
}
/* Merge by date, drop repeats, keep the newest 60. Returns how many were new. */
function merge(checks){
  const all = load().map(clean).filter(Boolean);
  let added = 0;
  checks.forEach(c=>{ if (!all.some(e=>sameCheck(e, c))){ all.push(c); added++; } });
  all.sort((a,b)=>a.date.localeCompare(b.date));
  return store(all) ? added : -1;
}
function forget(name){
  const k = keyOf(name);
  return store(load().filter(e=>keyOf(e && e.name)!==k));
}

/* ---- comparison ----------------------------------------------------------
   Up arrows only: a rise of 0.3 or more is named, anything smaller is about
   the same, and a fall is "needs a few more tries", never red or a down
   arrow. */
function compare(now, earlier){
  const t = tr();
  const before = Object.fromEntries((earlier && earlier.factors || []).map(f=>[f.n, f.score]));
  return (now && now.factors || []).filter(f=>Number.isFinite(before[f.n])).map(f=>{
    const d = Math.round((f.score - before[f.n]) * 10) / 10;
    return { n:f.n, name:t('name.'+f.n), was:before[f.n], now:f.score,
      kind: d >= BETTER_BY - 1e-9 ? 'up' : d <= -BETTER_BY + 1e-9 ? 'tries' : 'same', change:d };
  });
}

/* ---- the panel (screen only) ------------------------------------------- */
function fmtDay(d, locale){ const day = new Date(d+'T00:00:00'); return Number.isNaN(day.getTime()) ? d : day.toLocaleDateString(locale || 'en-GB', {day:'numeric', month:'long', year:'numeric'}); }
let lastMount = null;
function mount(after, opts){
  lastMount = { after, opts };
  const t = tr();
  const name = (opts && opts.name) || '';
  const current = opts && opts.current;
  const who = name ? name : t('pp.noname');
  const old = global.document.getElementById('progress-panel'); if (old) old.remove();
  const panel = global.document.createElement('section');
  panel.id = 'progress-panel'; panel.className = 'progress-panel';
  panel.setAttribute('aria-labelledby', 'pp-title');
  panel.setAttribute('lang', t.lang);
  // Beside the report on a wide screen (the side panel's slot), else
  // under the report.
  const slot = global.document.getElementById('side-progress');
  if (slot) { slot.appendChild(panel); slot.hidden = false; }
  else after.insertAdjacentElement('afterend', panel);
  let compareWith = null;
  const day = d=>fmtDay(d, t.locale);
  const draw = (status)=>{
    const mine = forName(name).map(clean).filter(Boolean);
    const now = current && mine.find(e=>sameCheck(e, current)) || mine[mine.length-1] || null;
    const earlier = mine.filter(e=>e!==now).reverse();
    if (!compareWith || !earlier.some(e=>sameCheck(e, compareWith))) compareWith = earlier[0] || null;
    const shown = mine.slice().reverse().slice(0, SHOWN);
    const rows = compareWith && now ? compare(now, compareWith) : [];
    const word = r=>r.kind==='up' ? `<span class="pp-up">↑ +${esc(r.change.toFixed(1))}</span>`
      : r.kind==='same' ? `<span class="pp-same">${esc(t('pp.same'))}</span>` : `<span class="pp-tries">${esc(t('pp.tries'))}</span>`;
    panel.innerHTML = `<h2 id="pp-title">${esc(t('pp.title'))}</h2>
      <p>${esc(now ? t('pp.saved.now') : t('pp.saved.none'))} ${esc(t('pp.private'))}</p>
      ${shown.length ? `<ol class="pp-list">${shown.map(e=>`<li>${esc(e.overall==null?t('pp.list.noscore',{date:day(e.date)}):t('pp.list.score',{date:day(e.date),score:e.overall}))}${e===now?` <b>${esc(t('pp.list.this'))}</b>`:''}</li>`).join('')}</ol>`
        : `<p class="pp-empty">${esc(t('pp.empty'))}</p>`}
      ${earlier.length ? `<label class="pp-pick">${esc(t('pp.compare'))} <select id="pp-compare">${earlier.map((e,i)=>`<option value="${i}"${sameCheck(e, compareWith)?' selected':''}>${esc(e.overall==null?t('pp.option.noscore',{date:day(e.date)}):t('pp.option.score',{date:day(e.date),score:e.overall}))}</option>`).join('')}</select></label>
        <ul class="pp-compare">${rows.map(r=>`<li data-factor="${r.n}" data-kind="${r.kind}"><span class="pp-name">${esc(r.name)}</span> ${esc(r.was.toFixed(1))} → ${esc(r.now.toFixed(1))} ${word(r)}</li>`).join('')}</ul>`
        : now ? `<p class="pp-first">${esc(t('pp.first',{who}))}</p>` : ''}
      <p class="pp-keep">${esc(t('pp.keep'))} <a href="/progress.html">${esc(t('pp.keep.link'))}</a></p>
      <div class="pp-actions">
        <button type="button" class="btn btn-ghost" id="pp-download"${mine.length?'':' disabled'}>${esc(t('pp.download'))}</button>
        <label class="btn btn-ghost pp-load">${esc(t('pp.load'))}<input type="file" id="pp-file" accept="application/json,.json"></label>
        <button type="button" class="btn btn-ghost" id="pp-forget"${mine.length?'':' disabled'}>${esc(t('pp.forget',{who}))}</button>
      </div>
      <div class="pp-confirm" id="pp-confirm" hidden><p>${esc(t.n('pp.confirm',mine.length,{who}))}</p>
        <button type="button" class="btn btn-dark" id="pp-forget-yes">${esc(t('pp.confirm.yes'))}</button> <button type="button" class="btn btn-ghost" id="pp-forget-no">${esc(t('pp.confirm.no'))}</button></div>
      <p class="pp-status" id="pp-status" role="status" aria-live="polite">${esc(status || '')}</p>`;
    const $ = sel=>panel.querySelector(sel);
    const pick = $('#pp-compare');
    if (pick) pick.addEventListener('change', ()=>{ compareWith = earlier[Number(pick.value)] || null; draw(); });
    $('#pp-download').addEventListener('click', ()=>{
      const blob = new Blob([JSON.stringify(exportFile(name), null, 2)], {type:'application/json'});
      const a = global.document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'vahini-progress' + (name ? '-' + name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') : '') + '.json';
      global.document.body.appendChild(a); a.click(); a.remove();
      setTimeout(()=>URL.revokeObjectURL(a.href), 1000);
    });
    $('#pp-file').addEventListener('change', async e=>{
      const file = e.target.files && e.target.files[0]; if (!file) return;
      let message;
      try{
        if (file.size > 1048576) throw new Error(t('pp.file.big'));
        const added = merge(readFile(await file.text()));
        message = added < 0 ? t('pp.file.nosave') : added ? t.n('pp.file.loaded', added) : t('pp.file.already');
      }catch(err){ message = err.message; }
      draw(message);
    });
    $('#pp-forget').addEventListener('click', ()=>{ $('#pp-confirm').hidden = false; $('#pp-forget-yes').focus(); });
    $('#pp-forget-no').addEventListener('click', ()=>{ $('#pp-confirm').hidden = true; });
    $('#pp-forget-yes').addEventListener('click', ()=>{ compareWith = null; draw(forget(name) ? t('pp.forgot', {who}) : t('pp.noforget')); });
  };
  draw();
  return panel;
}
/* Redraw the panel in the language just chosen in "Print in". */
function remount(){
  if (!lastMount || !global.document.getElementById('progress-panel')) return null;
  return mount(lastMount.after, lastMount.opts);
}

global.VahiniProgress = { load, forName, last, entryFrom, save, clean, readFile, merge, forget, exportFile, compare, mount, remount, MAX_ENTRIES };
})(window);
