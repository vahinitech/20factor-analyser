/**
 * Vahini — feedback → email backend (Google Apps Script)
 * ======================================================
 * This makes the website feedback widget email vahinitechfirm@gmail.com
 * automatically (no visitor action), and also logs every submission to a
 * Google Sheet. It is free and you own it.
 *
 * ONE-TIME SETUP (≈5 minutes)
 * 1. Go to https://script.google.com  →  New project.
 * 2. Delete the sample code, paste THIS whole file in.
 * 3. (optional) create a Google Sheet, copy its ID from the URL, and paste it
 *    into SHEET_ID below. Leave "" to skip sheet logging and only email.
 * 4. Click Deploy ▸ New deployment ▸ type "Web app".
 *      - Execute as: Me
 *      - Who has access: Anyone
 *    Deploy, authorise, and COPY the Web-app URL it gives you
 *    (looks like https://script.google.com/macros/s/AKfy..../exec).
 * 5. On the website, set that URL once — add this line before
 *    vahini-insights.js loads (e.g. in theme.config.js or a <script> in <head>):
 *
 *      window.VAHINI_INSIGHTS = { endpoint: "PASTE_THE_WEB_APP_URL_HERE" };
 *
 * That's it. Every feedback submission now emails you and appends a row.
 */

var EMAIL_TO = "vahinitechfirm@gmail.com";
var SHEET_ID = ""; // optional: paste a Google Sheet ID to also log rows

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents || "{}");
    // the site posts { kind, ts, vid, page, data:{...feedback fields...} }
    var d = body.data || body;
    if (body.kind && body.kind !== "feedback") {
      // ignore pageview/profile beacons for email; (optionally log them)
      return json({ ok: true, skipped: body.kind });
    }

    var label = ({ love: "I like it", bug: "Bug report", feature: "Feature request", other: "Feedback" })[d.type] || "Feedback";
    var subject = "Vahini feedback — " + label + (d.name ? " from " + d.name : "");
    var p = d.profile || {};
    var lines = [
      "Type: " + label,
      "Happiness: " + (d.happiness ? d.happiness + "/5" : "—"),
      "Scoring accuracy: " + (d.algo_rating ? d.algo_rating + "/5" : "—"),
      "",
      "Message:",
      (d.message || "(none)"),
      "",
      "Name:  " + (d.name || "—"),
      "Email: " + (d.email || "—"),
      "Place: " + (d.place || "—"),
      "Context: " + (d.context || "general"),
      "Report ID: " + (d.report_id || "—"),
      "",
      "— visitor profile —",
      "Locale/Country: " + (p.locale || "—") + " / " + (p.country || "—"),
      "Timezone: " + (p.timezone || "—"),
      "Visits: " + (p.visits || "—") + "   Last topic: " + (p.last_topic || "—"),
      "Referrer: " + (p.referrer || "—"),
      "Page: " + (body.page || "—"),
      "Time: " + (body.ts || new Date().toISOString())
    ];

    MailApp.sendEmail({
      to: EMAIL_TO,
      subject: subject,
      body: lines.join("\n"),
      replyTo: d.email || EMAIL_TO
    });

    if (SHEET_ID) {
      var sh = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
      sh.appendRow([
        new Date(), label, d.happiness || "", d.algo_rating || "",
        d.message || "", d.name || "", d.email || "", d.place || "",
        d.context || "", d.report_id || "",
        (p.country || ""), (p.timezone || ""), (p.visits || ""), (body.page || "")
      ]);
    }
    return json({ ok: true });
  } catch (err) {
    return json({ ok: false, error: String(err) });
  }
}

// Apps Script web apps can't return real CORS headers; the site posts with
// sendBeacon / no-cors and does not read the response, so a simple body is fine.
function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
