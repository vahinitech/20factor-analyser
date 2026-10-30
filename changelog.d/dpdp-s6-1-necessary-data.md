- DPDP section 6(1), only the data the purpose needs:
  - The report PDF no longer asks for anything. Print / Save as PDF prints
    at once; the full name, the email, "What will you use it for?" and the
    "By continuing you agree we may contact you" line were required before
    it, which made the PDF depend on data it does not need (India's DPDP
    Act, 2023). A card now opens after the print, at most once a day, with
    two optional questions that carry no name (what the report is for, and
    what a full report would be worth) and an unticked "Email me practice
    tips" box. The answers go as one anonymous `report_pdf_answer` event; an
    email goes only when its box is ticked, as a `report_pdf_lead` with no
    name, organisation or price. Names and emails the old form kept in the
    visitor's browser are deleted. The card uses the website's theme tokens.
  - Names, phone numbers, emails, roll numbers and school names in the text read from a page are blanked (`[name]`, `[phone]`, ...) before a scan is cached or returned (`backend/reading/identifiers.py`). Scores do not change.
