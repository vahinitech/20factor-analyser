/* SPDX-License-Identifier: AGPL-3.0-only
   (c) 2026 Vahini Technologies. */
// The check page's "What's new" line (owner, 2026-10-24): the newest change
// first, then the next of the latest ten every 5 seconds on the same line,
// with "1 of 10" beside it, over the list build_bundle.py writes from
// whats-new.json. It waits while the pointer or keyboard is on it or the
// list is open, and stays on the newest for people who turn off motion.
// Before this runs, the line shows the newest change.
(function () {
  var box = document.getElementById('whats-new');
  if (!box) return;
  var items = Array.prototype.slice.call(box.querySelectorAll('.wn-list li'), 0, 10);
  var line = box.querySelector('.wn-line');
  if (!items.length || !line) return;
  var EVERY_MS = 5000;
  var count = box.querySelector('.wn-count');
  if (!count) {
    count = document.createElement('span');
    count.className = 'wn-count';
    line.parentNode.insertBefore(count, line.nextSibling);
  }
  var shown = 0;
  function show(i) {
    shown = i;
    line.replaceChildren.apply(line, Array.prototype.map.call(
      items[i].childNodes, function (node) { return node.cloneNode(true); }));
    count.textContent = (i + 1) + ' of ' + items.length;
    line.classList.remove('wn-in');
    void line.offsetWidth;   // restart the slide-in
    line.classList.add('wn-in');
  }
  show(0);
  var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (still || items.length < 2) return;
  var held = false;
  function hold() { held = true; }
  function free() { held = box.matches(':hover') || box.contains(document.activeElement); }
  box.addEventListener('mouseenter', hold);
  box.addEventListener('mouseleave', free);
  box.addEventListener('focusin', hold);
  box.addEventListener('focusout', function () { setTimeout(free, 0); });
  window.VAHINI_WHATS_NEW = {
    next: function () { show((shown + 1) % items.length); return shown; },
    timer: setInterval(function () {
      if (held || box.open || document.hidden) return;
      show((shown + 1) % items.length);
    }, EVERY_MS),
  };
})();
