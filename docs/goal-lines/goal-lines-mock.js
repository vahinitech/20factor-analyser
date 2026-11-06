/* MOCK-UP ONLY (docs/goal-lines). Not loaded by any shipped page.

   Adds one proposed way of showing "goal-ready lines" to the sample report
   after the shipped renderer has drawn it. Every number below is read from
   window.VAHINI_SAMPLE_REPORT, the real run of the fixture photo, using the
   same rules as backend/scoring_parts/features.py and
   backend/vision/letter_geometry.py. Nothing is invented: where the server
   sends a share but not its count, the count is worked back from the share
   and the README says so.

   ?option=a  teacher card above the two pages (screen only)
   ?option=b  a copyable line in each "What your page shows" row (screen only)
   ?option=c  a third printed sheet of measurements (breaks the two-A4 rule)
   &example=free  the Free report: lines only for its five factors */
(function () {
  "use strict";
  var q = new URLSearchParams(location.search);
  var option = (q.get("option") || "a").toLowerCase();
  var free = q.get("example") === "free";
  var R = window.VAHINI_SAMPLE_REPORT;
  if (!R) return;
  var A = R.analysis;

  function factor(n) {
    for (var i = 0; i < A.results.length; i++) if (A.results[i].n === n) return A.results[i];
    return null;
  }
  function feat(n) {
    var f = factor(n);
    return (f && f.scoringInputs && f.scoringInputs.features) || {};
  }
  function pct(k, n) { return Math.round((100 * k) / n); }
  function one(x) { return (Math.round(x * 10) / 10).toFixed(1); }

  var M = R.measurements || {};
  var rows = M.lines;
  var FREE = [1, 5, 7, 8, 18];

  // Each line: the factor, the skill name the report already uses, the
  // sentence to copy, and what it rests on (shown under "How it was measured").
  function goalLines() {
    var out = [];
    // 5 Size Consistency: words whose small letters are 30% or more off the
    // page's median small-letter height (features.SIZE_OFF).
    var n5 = parseInt(factor(5).basedOn, 10);
    var off5 = Math.round(feat(5).words_off_size * n5);
    out.push({
      n: 5, skill: "Letter size",
      line: "Small letters were within 30% of the page's usual small-letter height in " +
        (n5 - off5) + " of " + n5 + " words measured (" + pct(n5 - off5, n5) + "%).",
      how: "Each word's small-letter height, measured along its own baseline. A word counts as off size when it is 30% or more taller or shorter than the page's middle value."
    });
    // 7 Baseline Alignment: words whose baseline sits 0.35 small letters or
    // more off their line's (letter_geometry.WORD_DROP_LOOK).
    var n7 = R.sample.nWords;
    var off7 = Math.round(feat(7).words_off_line * n7);
    out.push({
      n: 7, skill: "Writing on the line",
      line: (n7 - off7) + " of " + n7 + " words sat on their row's baseline, less than a third of a small-letter height above or below it (" +
        pct(n7 - off7, n7) + "%).",
      how: "Each word's baseline compared with the baseline of its row. A word counts as off the line at 0.35 of a small-letter height or more."
    });
    // 8 Word Spacing: gaps under half or over twice the page's median word
    // gap stand out (features.NARROW_WORD_GAP, ODD_GAP).
    var n8 = feat(8).word_gap_count;
    var odd8 = Math.round(feat(8).word_gaps_odd * n8);
    out.push({
      n: 8, skill: "Spaces between words",
      line: (n8 - odd8) + " of " + n8 + " gaps between words were between half and twice the page's usual word gap (" +
        pct(n8 - odd8, n8) + "%).",
      how: "Every gap between words, measured in the ink and compared with the page's middle gap. Narrower than half or wider than twice it counts as uneven."
    });
    // 10 Margin Discipline: mean distance of row starts from the median
    // start, as a share of page width (features._margin_spread).
    out.push({
      n: 10, skill: "Where rows begin",
      line: "Rows began on average " + one(feat(10).left_spread * 100) +
        "% of the page width from the usual left edge, over " + rows + " rows.",
      how: "The left edge of each row against the middle left edge. A row starting far to the right (15% of the page width or more) is taken as a title or date and left out."
    });
    // 11 Line Straightness: mean and steepest absolute row angle, as the
    // report's own measurement row draws them (marked_places.page_measurements).
    out.push({
      n: 11, skill: "Level rows",
      line: "Rows sloped " + one(M.slope.mean_deg) + "° on average over " + rows +
        " rows; the steepest sloped " + one(M.slope.line.angle) + "°.",
      how: "The angle of each row of writing against level. A photo taken at an angle adds to every row's slope, so compare pages photographed flat."
    });
    // 6 Ascender / Descender Control: zone bands from ink profiles.
    var z = A.zoneProfile || {};
    out.push({
      n: 6, skill: "Tall letters and tails",
      line: "Over " + rows + " rows, tall letters reached " + one(z.ascenderReach) +
        " times the small-letter height and tails reached " + one(z.descenderReach) +
        " times (the guide the analyser uses is " + one(z.targetReach) + " times).",
      how: "The height of the ink above and below the small-letter band in each row, from the page's ink profile."
    });
    // 17 Slant Consistency: spread of the words' lean (features._stroke_features).
    out.push({
      n: 17, skill: "Slant",
      line: "The lean of the words varied by " + one(feat(17).slant_std) +
        "° (standard deviation) across the words measured.",
      how: "The lean of each word's upright strokes. Needs a count of words to be a good goal line; the server does not send it yet."
    });
    return free ? out.filter(function (g) { return FREE.indexOf(g.n) >= 0; }) : out;
  }

  var NO_LINE_PRO = [
    ["Letter shapes, Clear letters", "built from how sure the text reader was, not from the shapes themselves"],
    ["Closed letters", "compares bowls in the ink with letters the reader guessed, not letter by letter"],
    ["Letter spacing", "an estimate; it gives our own neat practice page its lowest mark"],
    ["Stroke order, Smooth lines", "built from the widths of rows and letters, which a photo cannot tie to the skill"],
    ["Upright strokes", "measures how much row angles vary, not how upright the strokes are"],
    ["Readability, Neat page", "blends of other scores, with no count of their own"],
    ["Writing speed, Pen pressure, Smooth joins, Pen lifts", "need the Vahini sensor pen"]
  ];
  var NO_LINE_FREE = [
    ["Letter shapes", "built from how sure the text reader was, not from the shapes themselves"],
    ["Readability", "a blend of other scores, with no count of its own"]
  ];

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function today() {
    return new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  }
  function header() {
    return "Handwriting measured from a photo of one page (Vahini check, " + today() + "; " +
      rows + " rows, " + R.sample.nWords + " words).";
  }
  var CAVEAT = "These counts describe the writing on this page only. They are not a standard test or a clinical assessment.";
  function copyText(lines) {
    return [header()].concat(lines.map(function (g) { return "- " + g.skill + ": " + g.line; }), [CAVEAT]).join("\n");
  }
  function copyButton(label, text) {
    var b = el("button", "gl-copy");
    b.type = "button";
    b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
    b.appendChild(document.createTextNode(label));
    b.addEventListener("click", function () {
      if (navigator.clipboard) navigator.clipboard.writeText(text).catch(function () {});
      b.lastChild.textContent = "Copied";
    });
    return b;
  }
  function mockFlag(text) {
    return el("p", "gl-flag", text);
  }

  // Option A: a card above the two pages, shown when the check page's
  // "I am" is Teacher. Screen only; the two A4 sheets do not change.
  function optionA(host, firstPage) {
    var lines = goalLines();
    var card = el("section", "gl-card");
    card.setAttribute("aria-labelledby", "gl-title");
    card.appendChild(mockFlag("Option A · proposed · shown for “I am: Teacher” · screen only, never printed"));
    var top = el("div", "gl-top");
    var h = el("h2", "gl-title", "Measured on this page, for your notes");
    h.id = "gl-title";
    top.appendChild(h);
    top.appendChild(copyButton("Copy all", copyText(lines)));
    card.appendChild(top);
    card.appendChild(el("p", "gl-sub", header() + " " + CAVEAT));
    var t = el("table", "gl-table");
    var thead = el("thead");
    var tr = el("tr");
    ["Skill", "Line you can copy", ""].forEach(function (x) { tr.appendChild(el("th", null, x)); });
    thead.appendChild(tr);
    t.appendChild(thead);
    var tb = el("tbody");
    lines.forEach(function (g) {
      var r = el("tr");
      r.appendChild(el("th", "gl-skill", g.skill));
      var td = el("td");
      td.appendChild(el("p", "gl-line", g.line));
      var d = el("details", "gl-how");
      d.appendChild(el("summary", null, "How it was measured"));
      d.appendChild(el("p", null, g.how));
      td.appendChild(d);
      r.appendChild(td);
      var c = el("td", "gl-c");
      c.appendChild(copyButton("Copy", g.skill + ": " + g.line));
      r.appendChild(c);
      tb.appendChild(r);
    });
    t.appendChild(tb);
    card.appendChild(t);
    var none = el("div", "gl-none");
    none.appendChild(el("h3", null, "No line for these skills, and why"));
    var ul = el("ul");
    (free ? NO_LINE_FREE : NO_LINE_PRO).forEach(function (x) {
      var li = el("li");
      li.appendChild(el("b", null, x[0] + ": "));
      li.appendChild(document.createTextNode(x[1] + "."));
      ul.appendChild(li);
    });
    none.appendChild(ul);
    if (free) none.appendChild(el("p", "gl-more", "The full review adds lines for where rows begin, level rows, tall letters and tails, and slant."));
    card.appendChild(none);
    host.insertBefore(card, firstPage);
  }

  // Option B: under each "What your page shows" row, a dashed line with the
  // sentence and a Copy button. Hidden in print, but page 1 on screen grows.
  var ROW_FACTORS = {
    "How easy your writing is to read": [],
    "Writing along the line": [7, 11, 17],
    "Spaces between your words": [8],
    "The size of your small letters": [5, 6],
    "Where your lines begin": [10]
  };
  function optionB(host) {
    var byN = {};
    goalLines().forEach(function (g) { byN[g.n] = g; });
    var first = true;
    host.querySelectorAll(".sn-m").forEach(function (row) {
      var h4 = row.querySelector(".sn-m-what h4");
      if (!h4) return;
      var ns = ROW_FACTORS[h4.textContent.trim()];
      if (!ns) return;
      var box = el("div", "gl-row");
      if (first) { box.appendChild(mockFlag("Option B · screen only")); first = false; }
      var lines = ns.map(function (n) { return byN[n]; }).filter(Boolean);
      if (!lines.length) {
        box.appendChild(el("p", "gl-row-none", "For your notes: no measured line for this row (it rests on how sure the text reader was)."));
      } else {
        lines.forEach(function (g) {
          var p = el("p", "gl-row-line");
          p.appendChild(el("span", null, g.line));
          p.appendChild(copyButton("Copy", g.skill + ": " + g.line));
          box.appendChild(p);
        });
      }
      row.querySelector(".sn-m-what").appendChild(box);
    });
  }

  // Option C: a third sheet after page 2 that prints. The report rule is
  // two A4 sheets, so this option needs the owner to change that rule.
  function optionC(host) {
    var lines = goalLines();
    var pages = host.querySelectorAll("section.page");
    var last = pages[pages.length - 1];
    var sheet = el("section", "page gl-sheet");
    var top = el("div", "sn-top");
    top.innerHTML = '<span class="sn-brand"><img class="sn-logo" src="' + LOGO + '" alt="" width="40" height="40"><span><b class="sn-brandname">Vahini</b><span class="sn-site">vahinitech.com</span></span></span><div class="sn-right"><span class="sn-eyebrow">For school records</span></div>';
    sheet.appendChild(top);
    sheet.appendChild(mockFlag("Option C · a third printed sheet · breaks the two-A4 rule"));
    sheet.appendChild(el("h2", "gl-sheet-title", "Measured on this page"));
    sheet.appendChild(el("p", "gl-sub", header()));
    var t = el("table", "gl-table gl-table--print");
    var thead = el("thead");
    var tr = el("tr");
    ["Skill", "What was measured on this page", "How it was measured"].forEach(function (x) { tr.appendChild(el("th", null, x)); });
    thead.appendChild(tr);
    t.appendChild(thead);
    var tb = el("tbody");
    lines.forEach(function (g) {
      var r = el("tr");
      r.appendChild(el("th", "gl-skill", g.skill));
      r.appendChild(el("td", "gl-line", g.line));
      r.appendChild(el("td", "gl-howcell", g.how));
      tb.appendChild(r);
    });
    t.appendChild(tb);
    sheet.appendChild(t);
    var none = el("p", "gl-sub", "No measured line: " + (free ? NO_LINE_FREE : NO_LINE_PRO).map(function (x) { return x[0]; }).join("; ") + ".");
    sheet.appendChild(none);
    sheet.appendChild(el("p", "gl-sub", CAVEAT));
    var foot = el("p", "gl-foot", (free ? "Free handwriting review" : "Handwriting review") + " · vahinitech.com");
    sheet.appendChild(foot);
    last.parentNode.insertBefore(sheet, last.nextSibling);
  }

  // The renderer's logo path is relative to frontend/; this page sits two
  // folders away, so point it back (the shipped pages are unaffected).
  var LOGO = "../../frontend/assets/vahini-logo.png";
  function fixLogos(host) {
    host.querySelectorAll("img.sn-logo").forEach(function (img) { img.src = LOGO; });
  }

  function apply() {
    var host = document.getElementById("report-host");
    var firstPage = host && host.querySelector("section.page");
    if (!firstPage) return false;
    fixLogos(host);
    if (option === "none" || host.querySelector(".gl-card, .gl-row, .gl-sheet")) return true;
    document.documentElement.setAttribute("data-gl-option", option);
    if (option === "a") optionA(host, firstPage);
    else if (option === "b") optionB(host);
    else if (option === "c") optionC(host);
    return true;
  }
  var tries = 0;
  var timer = setInterval(function () {
    if (apply() || ++tries > 80) clearInterval(timer);
  }, 100);
})();
