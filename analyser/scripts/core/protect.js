/* SPDX-License-Identifier: AGPL-3.0-only
   © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
   Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json */
/* Vahini — access deterrent for the analyser.
   Discourages casual inspection of the packed engine: disables the context
   menu and the common view-source / devtools keyboard shortcuts.
   NOTE: client-side code can never be fully hidden from a determined user;
   this is a deterrent, not encryption. */
(function () {
  "use strict";
  document.addEventListener("contextmenu", function (e) { e.preventDefault(); }, { capture: true });
  document.addEventListener("keydown", function (e) {
    var k = (e.key || "").toLowerCase();
    var block =
      e.key === "F12" ||
      (e.ctrlKey && e.shiftKey && (k === "i" || k === "j" || k === "c")) ||
      (e.metaKey && e.altKey && (k === "i" || k === "j" || k === "c")) ||
      ((e.ctrlKey || e.metaKey) && (k === "u" || k === "s"));
    if (block) { e.preventDefault(); e.stopPropagation(); return false; }
  }, { capture: true });
})();
