/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// The check page's "What's new" line (owner, 2026-10-24): one of the latest
// changes, the next one on each visit, newest first, over the full list
// that build_bundle.py writes from whats-new.json. Without storage, or
// before this runs, the line shows the newest change.
(function () {
  var box = document.getElementById('whats-new');
  if (!box) return;
  var items = box.querySelectorAll('.wn-list li');
  var line = box.querySelector('.wn-line');
  if (!items.length || !line) return;
  var KEY = 'vahini_whats_new';
  var shown = 0;
  try {
    var last = parseInt(localStorage.getItem(KEY), 10);
    shown = isNaN(last) ? 0 : (last + 1) % items.length;
    localStorage.setItem(KEY, String(shown));
  } catch (e) { /* private window or blocked storage: keep the newest */ }
  line.replaceChildren.apply(line, Array.prototype.map.call(
    items[shown].childNodes, function (node) { return node.cloneNode(true); }));
})();
