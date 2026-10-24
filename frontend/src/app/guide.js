/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: info@vahinitech.com.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* =========================================================================
   Pihu shows the buttons that matter (owner, 2026-10-25). On a first visit
   to the check page Pihu flies to four stops in turn: "I am", the photo
   button, "Try a sample" and "Analyse". After the first report, two more:
   Print and the other view's link. At each stop the rest of the page dims
   and a short note says what the button does, with Next and Skip. Once per
   browser for each set; "Show me around" brings it back. Escape, Skip, a
   chosen photo or a new screen ends it. With motion turned off Pihu
   appears beside each button without flying.

   Pihu is the drawings library's original bird, from the host's map: the
   cut layers (window.VAHINI_GUIDE_ART: body, wingBack, wingFront) so the
   wings beat from the shoulders, else the whole bird
   (window.VAHINI_REPORT_ART.tip). Only motion is added. Same-site paths
   only, as for the report's pictures. Nothing is sent.
   ========================================================================= */
(function (global) {
'use strict';
const doc = global.document;
const KEYS = { check: 'vahini_guide_check', report: 'vahini_guide_report' };
const FLY_MS = 900;
const SAME_SITE = /^\/(?!\/)[\w\-./%]+$/;

const visible = (sel) => { const el = doc.querySelector(sel); return !!(el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden'); };
const still = () => !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);

function stops(kind){
  if (kind === 'report'){
    const student = global.VahiniReport && global.VahiniReport.audience && global.VahiniReport.audience() === 'student';
    return [
      { sel: '#print-report', title: 'Your report is ready', text: 'Print it, or share the PDF on WhatsApp.' },
      student
        ? { sel: '#view-switch', title: 'For the grown-ups', text: 'The full report for parents and teachers.' }
        : { sel: '#view-switch', title: 'For the child', text: 'Show them the student view of their own writing.' },
    ].filter((s) => visible(s.sel));
  }
  return [
    { sel: '#who-bar', title: 'Hello! I am Pihu.', text: 'Tell us who is checking. A student gets a report made for them.' },
    { sel: visible('#take-photo') ? '#take-photo' : '#choose-photo', title: 'Add one page', text: 'A photo of four to six lines of writing.' },
    { sel: '#try-sample', title: 'No page handy?', text: 'Try our sample page first.' },
    { sel: '#go-process', title: 'Then press here', text: 'Your report usually comes in 5 to 20 seconds.' },
  ].filter((s) => visible(s.sel));
}

function seen(kind){ try{ return global.localStorage.getItem(KEYS[kind]) === '1'; }catch(_e){ return true; } }
function remember(kind){ try{ global.localStorage.setItem(KEYS[kind], '1'); }catch(_e){ /* this visit only */ } }

function bird(){
  const layers = global.VAHINI_GUIDE_ART || {};
  const whole = (global.VAHINI_REPORT_ART || {}).tip;
  const el = doc.createElement('div'); el.className = 'pg-bird'; el.setAttribute('aria-hidden', 'true');
  const img = (src, cls) => { const i = doc.createElement('img'); i.src = src; i.alt = ''; i.className = cls; i.decoding = 'async'; el.appendChild(i); };
  if ([layers.body, layers.wingBack, layers.wingFront].every((u) => typeof u === 'string' && SAME_SITE.test(u))){
    img(layers.wingBack, 'pg-wb'); img(layers.body, 'pg-body'); img(layers.wingFront, 'pg-wf');
    el.classList.add('pg-bird--layers');
  } else if (typeof whole === 'string' && SAME_SITE.test(whole)){
    img(whole, 'pg-body');
  } else return null;
  return el;
}

let open = null;   // the running guide

function close(done){
  if (!open) return;
  const g = open; open = null;
  global.cancelAnimationFrame(g.frame);
  global.removeEventListener('resize', g.place);
  global.removeEventListener('scroll', g.place, true);
  doc.removeEventListener('keydown', g.key, true);
  doc.removeEventListener('change', g.picked, true);
  if (done) remember(g.kind);
  g.root.remove();
}

function start(kind){
  close(false);
  const list = stops(kind);
  if (!list.length) return false;
  const root = doc.createElement('div'); root.id = 'pihu-guide'; root.className = 'pg on';
  const ring = doc.createElement('div'); ring.className = 'pg-ring';
  const say = doc.createElement('div'); say.className = 'pg-say';
  say.setAttribute('role', 'dialog'); say.setAttribute('aria-labelledby', 'pg-title'); say.setAttribute('aria-describedby', 'pg-text');
  say.innerHTML = '<p class="pg-n"></p><h2 id="pg-title"></h2><p id="pg-text"></p>'
    + '<div class="pg-act"><button type="button" class="pg-skip">Skip</button><button type="button" class="pg-next">Next</button></div>';
  const pihu = bird();
  root.append(ring, say);
  if (pihu) root.appendChild(pihu);
  doc.body.appendChild(root);

  const g = { kind, root, frame: 0, at: null, i: -1 };
  open = g;
  const size = () => (global.innerWidth < 560 ? 64 : 84);
  function perch(r){
    const s = size();
    return { x: Math.max(4, Math.min(global.innerWidth - s - 4, r.right - s * 0.55)) + global.scrollX, y: r.top + global.scrollY - s * 0.8 };
  }
  function put(p){ if (pihu){ pihu.style.width = size() + 'px'; pihu.style.transform = `translate(${p.x}px, ${p.y}px)`; } g.at = p; }
  function fly(to){
    if (!pihu) return;
    const from = g.at;
    if (!from || still()){ put(to); return; }
    const top = Math.min(from.y, to.y) - 120;
    const ctl = { x: (from.x + to.x) / 2, y: top };
    const t0 = global.performance.now();
    pihu.classList.add('is-flying');
    global.cancelAnimationFrame(g.frame);
    const step = (now) => {
      if (open !== g) return;
      const t = Math.min(1, (now - t0) / FLY_MS), e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const a = 1 - e;
      put({ x: a * a * from.x + 2 * a * e * ctl.x + e * e * to.x, y: a * a * from.y + 2 * a * e * ctl.y + e * e * to.y });
      if (t < 1) g.frame = global.requestAnimationFrame(step);
      else { pihu.classList.remove('is-flying'); put(to); }
    };
    g.frame = global.requestAnimationFrame(step);
  }
  g.place = function (){
    if (open !== g) return;
    const s = list[g.i], el = doc.querySelector(s.sel);
    if (!el){ close(false); return; }
    const r = el.getBoundingClientRect();
    Object.assign(ring.style, { left: r.left + global.scrollX - 8 + 'px', top: r.top + global.scrollY - 8 + 'px', width: r.width + 16 + 'px', height: r.height + 16 + 'px' });
    const w = Math.min(300, global.innerWidth - 32), h = say.offsetHeight || 160;
    const below = r.bottom + 18 + h < global.innerHeight || r.top - 18 - h < 0;
    say.style.width = w + 'px';
    say.style.left = Math.max(16, Math.min(global.innerWidth - w - 16, r.left)) + global.scrollX + 'px';
    say.style.top = (below ? r.bottom + 18 : r.top - 18 - h) + global.scrollY + 'px';
    if (pihu && !pihu.classList.contains('is-flying')) put(perch(r));
  };
  function go(i){
    if (i >= list.length){ close(true); return; }
    g.i = i;
    const s = list[i], el = doc.querySelector(s.sel);
    if (!el){ go(i + 1); return; }
    el.scrollIntoView({ block: 'center', behavior: still() ? 'auto' : 'smooth' });
    say.querySelector('.pg-n').textContent = `${i + 1} of ${list.length}`;
    say.querySelector('#pg-title').textContent = s.title;
    say.querySelector('#pg-text').textContent = s.text;
    say.querySelector('.pg-next').textContent = i === list.length - 1 ? 'Done' : 'Next';
    global.setTimeout(() => {
      if (open !== g || g.i !== i) return;
      g.place();
      fly(perch(el.getBoundingClientRect()));
      say.querySelector('.pg-next').focus({ preventScroll: true });
    }, still() ? 0 : 350);
  }
  g.key = (e) => { if (e.key === 'Escape'){ e.stopPropagation(); close(true); } };
  g.picked = (e) => { if (e.target && /^(file|camera)-input$/.test(e.target.id)) close(true); };
  say.querySelector('.pg-next').addEventListener('click', () => go(g.i + 1));
  say.querySelector('.pg-skip').addEventListener('click', () => close(true));
  global.addEventListener('resize', g.place);
  global.addEventListener('scroll', g.place, true);
  doc.addEventListener('keydown', g.key, true);
  doc.addEventListener('change', g.picked, true);
  // Pihu flies in from the left edge to the first stop.
  if (pihu) put({ x: global.scrollX - size(), y: global.scrollY + global.innerHeight * 0.25 });
  go(0);
  return true;
}

const onScreen = (id) => { const s = doc.getElementById(id); return !!(s && s.classList.contains('on')); };
/* It never interrupts: a visitor who has already clicked, tapped or typed
   since the page or the report appeared is busy, so the guide waits for
   another visit (or "Show me around"). */
let touchedAt = 0;
['pointerdown', 'keydown'].forEach((t) => doc.addEventListener(t, () => { touchedAt = Date.now(); }, true));
const idleSince = (t0) => touchedAt < t0;
const otherPopup = () => onScreen('vgate') || onScreen('vfb-ov') || (doc.getElementById('report-feedback') && !doc.getElementById('report-feedback').hidden);

/* After a report is on screen (app.js): the two stops, once per browser. */
function report(){
  if (seen('report')) return;
  const t0 = Date.now();
  global.setTimeout(() => { if (onScreen('screen-report') && !open && idleSince(t0) && !otherPopup()) start('report'); }, 1200);
}

function init(){
  const again = doc.getElementById('guide-again');
  if (again) again.addEventListener('click', (e) => { e.preventDefault(); start('check'); });
  const againReport = doc.getElementById('guide-again-report');
  if (againReport) againReport.addEventListener('click', (e) => { e.preventDefault(); start('report'); });
  if (!doc.getElementById('who-bar') || seen('check')) return;
  const t0 = Date.now();
  global.setTimeout(() => { if (onScreen('screen-upload') && !open && idleSince(t0) && !otherPopup()) start('check'); }, 900);
}
if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', init);
else init();

/* A new screen ends the guide; the visitor has moved on, so it counts as seen. */
global.VahiniGuide = { start, close: () => close(true), report, isOpen: () => !!open, stops };
})(window);
