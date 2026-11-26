// Class screening mock-ups: made-up results for one class of 25 pupils,
// named by pupil code only. Not product code. Each row is the stage of the
// five Free skills (server/entitlements.py FREE_FACTORS 1, 5, 7, 8, 18):
// s Strong, m Mastering, i Improving, l Learning, or a refusal code.
(function () {
  var SKILLS = [
    { k: "Letter shapes", short: "Shapes", why: "many letters are formed a different way each time" },
    { k: "Letter size", short: "Size", why: "letters vary a lot in size" },
    { k: "Writing on the line", short: "Line", why: "the writing drifts well above and below the line" },
    { k: "Word spacing", short: "Spacing", why: "words often run into each other" },
    { k: "Readability", short: "Reading", why: "our reader could not read many of the words" }
  ];
  var STAGE = { s: "Strong", m: "Mastering", i: "Improving", l: "Learning" };
  // Shortened from the analyser's own refusal messages (server/app.py).
  var REFUSED = {
    turned: ["Sideways page", "The lines run up and down and we could not tell which way is up. Turn the photo so the lines run across, then add it again."],
    numbers: ["Mostly numbers", "This page is mostly numbers and sums. Add a page with four lines of English in sentences."],
    printed: ["No handwriting found", "This page looks printed. Add a page the child wrote by hand."],
    unread: ["Could not read the writing", "A sharper photo in daylight, held straight above the page, usually fixes this."]
  };
  var ROWS = [
    "mmsms", "sssms", "ilmli", "turned", "mimmm", "smsss", "llimm", "mmmim",
    "numbers", "imiim", "ssmss", "mmmmm", "iilli", "msmmm", "smssm", "iiimi",
    "printed", "mmmim", "mimmm", "ilmml", "sssss", "mmimm", "mmsmm", "immii", "mmmms"
  ];
  function code(n) { return "3B-" + String(n).padStart(2, "0"); }
  function flagOf(r) {
    var lows = [];
    for (var j = 0; j < 5; j++) if (r[j] === "l") lows.push(SKILLS[j].why);
    if (lows.length < 2) return null;
    lows = lows.slice(0, 2);
    var t = lows[0].charAt(0).toUpperCase() + lows[0].slice(1) + ", and " + lows[1] + ".";
    return t;
  }
  function stageCell(c, j) {
    return '<td class="c-st" data-k="' + SKILLS[j].short + '"><span class="stage ' + c + '">' + STAGE[c] + "</span></td>";
  }
  function head(withOpen) {
    var h = '<thead><tr><th class="sorted">Pupil code</th>';
    SKILLS.forEach(function (s) { h += "<th>" + s.k + "</th>"; });
    h += '<th style="width:30%">Worth a therapist\'s look?</th>';
    if (withOpen) h += "<th>Report</th>";
    return h + "</tr></thead>";
  }

  // opts.done: how many pages are finished (in order); opts.run: running
  // index; opts.order: "flag" sorts flagged, then refused, then the rest.
  function rows(opts) {
    var list = ROWS.map(function (r, i) { return { i: i, r: r }; });
    var done = opts.done == null ? 25 : opts.done;
    if (opts.replaced) list[3].r = "mimmm";
    if (opts.order === "flag") {
      var rank = function (o) {
        if (o.i >= done) return 3;
        if (REFUSED[o.r]) return 1;
        return flagOf(o.r) ? 0 : 2;
      };
      list.sort(function (a, b) { return rank(a) - rank(b) || a.i - b.i; });
    }
    if (opts.only === "refused") list = list.filter(function (o) { return REFUSED[o.r]; });
    if (opts.limit) list = list.slice(0, opts.limit);
    var html = "";
    list.forEach(function (o) {
      var c = code(o.i + 1), r = o.r;
      var open = opts.open ? '<td class="c-open"><a href="#">Open</a></td>' : "";
      if (o.i === opts.run) {
        html += '<tr class="is-run"><td class="c-code"><span class="code">' + c + '</span></td><td class="c-wide" colspan="' + (opts.open ? 7 : 6) + '"><span class="running">Reading the writing</span> <span class="waiting">&middot; about 8 seconds</span></td></tr>';
        return;
      }
      if (o.i >= done) {
        html += '<tr class="is-wait"><td class="c-code"><span class="code">' + c + '</span></td><td class="c-wide" colspan="' + (opts.open ? 7 : 6) + '"><span class="waiting">' + (opts.waitText || "Waiting") + "</span></td></tr>";
        return;
      }
      if (REFUSED[r]) {
        var f = REFUSED[r];
        var btn = opts.fix ? ' <a href="#" class="btn btn--ghost btn--sm" style="margin-left:6px">Add a new photo</a>' : "";
        html += '<tr class="is-refused"><td class="c-code"><span class="code">' + c + '</span></td><td class="c-wide" colspan="5"><span class="refusal"><b>Not checked: ' + f[0].toLowerCase() + ".</b> " + f[1] + "</span>" + btn + '</td><td class="c-flag"><span class="noflag">Not counted</span></td>' + (opts.open ? '<td class="c-open"></td>' : "") + "</tr>";
        return;
      }
      var fl = flagOf(r);
      var cls = fl ? "is-flag" : "";
      if (opts.fresh && o.i === opts.fresh) cls += " is-new";
      html += '<tr class="' + cls + '"><td class="c-code"><span class="code">' + c + "</span></td>";
      for (var j = 0; j < 5; j++) html += stageCell(r[j], j);
      html += '<td class="c-flag">' + (fl ? '<span class="flag"><span><b>Worth a look.</b> ' + fl + "</span></span>" : '<span class="noflag">No flag</span>') + "</td>" + open + "</tr>";
    });
    return html;
  }

  function practiseMost() {
    var counts = SKILLS.map(function () { return 0; });
    ROWS.forEach(function (r) {
      if (REFUSED[r]) return;
      for (var j = 0; j < 5; j++) if (r[j] === "i" || r[j] === "l") counts[j]++;
    });
    var best = 0;
    counts.forEach(function (n, j) { if (n > counts[best]) best = j; });
    return { skill: SKILLS[best].k, n: counts[best] };
  }

  function csv() {
    var out = "pupil_code,checked_on,letter_shapes,letter_size,writing_on_the_line,word_spacing,readability,worth_a_look,reason,status\n";
    ROWS.forEach(function (r, i) {
      var c = code(i + 1);
      if (REFUSED[r]) { out += c + ",2026-10-28,,,,,,,,\"not checked: " + REFUSED[r][0].toLowerCase() + "\"\n"; return; }
      var fl = flagOf(r);
      out += c + ",2026-10-28";
      for (var j = 0; j < 5; j++) out += "," + STAGE[r[j]];
      out += "," + (fl ? "yes" : "no") + "," + (fl ? '"' + fl + '"' : "") + ",checked\n";
    });
    return out;
  }

  window.MOCK = {
    SKILLS: SKILLS, head: head, rows: rows, csv: csv, practiseMost: practiseMost,
    fill: function (id, opts) {
      var el = document.getElementById(id);
      if (el) el.innerHTML = head(opts.open) + "<tbody>" + rows(opts) + "</tbody>";
    }
  };
})();
