---
name: dpdp-check
description: Check a change against India's Digital Personal Data Protection Act 2023 and the DPDP Rules 2025 before committing it, and stop for the owner's decision when it may break one. Use for any change that collects, stores, logs, sends, shows or deletes data about a person (parent, teacher, child, visitor, customer), changes consent, cookies or analytics, adds an outside service, changes how long data is kept or what the privacy notice says, or touches the children's flow.
---

cd "$(git rev-parse --show-toplevel)"

Owner rules: DPDP work goes as one PR per rule (2026-10-30). Every change is checked against the Act and the Rules, and a change that may break one goes to the owner before it is committed (2026-10-31). The Rules bind us in full from May 2027; we meet them now, so a change that breaks one is a regression today, not a 2027 problem.

## 1. Is the law still what this skill says?

Last checked: **31 October 2026.**

- Act: Digital Personal Data Protection Act 2023.
- Rules: DPDP Rules 2025, G.S.R. 846(E), notified 13 November 2025. Consent Manager registration from 13 November 2026. Notice, consent, security, breach, retention, children and rights (Rules 3, 5 to 16, 22, 23) from 13 May 2027.
- Amendments: none notified. MeitY proposed in January 2026 to shorten the timeline for Significant Data Fiduciaries; not notified at the last check.
- Source: published summaries. The Gazette text itself was not read; the Gazette wins where they differ.

When a change touches personal data and the last check is more than 30 days old, look for a notified amendment, new rule, Board order or MeitY clarification (egazette.gov.in, meity.gov.in, then summaries). Write what you found in the PR, even "no change". If the law changed:

1. Tell the owner what changed and which duty below it moves, before going on with the change.
2. Update this section and the table here in Umbrella's `skills/dpdp-check/SKILL.md`, then its copy in every product repository, in the same change set.

## 2. Does the change touch personal data?

Personal data is anything about a person who can be identified: name, email, phone, school or organisation, address, IP address, browser string, cookie or visitor id, device id, exact time of a visit, a full URL with its query, a photo or scan of a page, the handwriting itself, the words read from a page, a report or its scores linked to someone, a free-text answer, a child's age or a health answer. A count with no identifier is not personal data; joining it with something that identifies a person makes it personal again.

No personal data touched: write `DPDP: no personal data touched` in the PR body and stop here.

## 3. The duties and what breaks them

| Rule | The duty | A change breaks it when it |
|---|---|---|
| Section 5, Rule 3 (notice) | Say in plain words what we keep, why, for how long, how to withdraw and how to complain | adds a field, form, record kind, outside service or retention the privacy notice does not describe; collects on a form with no short notice beside it |
| Section 6 (consent) | Consent is free, specific, informed and a clear act; withdrawing is as easy as giving (6(4)) | loads analytics or tracking before a choice; pre-ticks a box; makes "accept" larger than "no"; reads closing a card as yes; lets a stored "off" be overridden; uses data for a purpose it was not given for |
| Section 6(1) (only what is needed) | Collect and keep only what the purpose needs | adds an IP address, browser string, referrer, visitor id, time of day, full URL, language or organisation to a record, event or log; stores a photo, crop or the words read; logs a request body |
| Section 8(5), Rule 6 (security) | Reasonable safeguards: encryption, access control, logs that can trace misuse, backups | stores in clear what was encrypted; makes data readable by other accounts; puts a secret or key in the repository; removes a rate limit or size cap; shortens a log needed to trace an incident (Rule 6 asks for one year, per summaries) |
| Section 8(6), Rule 7 (breach) | Tell the Data Protection Board and each person affected; full report within 72 hours (CERT-In: 6 hours, under its own directions) | is a breach. If you find one, stop all other work and tell the owner at once |
| Section 8(2) (processors) | Personal data goes only to a processor under a contract | sends personal data to a new outside service: fonts, video, mail, analytics, error tracking, an AI API, hosting, a CDN that sees visitors' IP addresses |
| Section 8(7), Rule 8 (erasure) | Delete once the purpose is served or consent is withdrawn | adds a store with no deletion rule; keeps something longer; turns off or narrows a sweeper; keeps backups with no end |
| Section 9, Rule 10 (children, under 18) | A parent or guardian's verifiable consent before a child's data is processed; no tracking, behavioural monitoring or targeted ads aimed at children; nothing likely to harm a child | opens a path that skips the parent or guardian step; adds analytics or ads to a child's report or check; follows a child across checks without the parent's yes; lets a school or teacher flow run without the school holding parents' consent |
| Sections 11 to 14, Rule 14 (rights) | Access, correction, erasure, nomination and grievance, answered within the times the privacy notice promises | adds a store the erase or export procedure does not reach; removes a contact route; makes a promised time impossible |
| Section 16 (outside India) | Transfers are allowed except to countries the government restricts | sends personal data to a processor in a restricted country (check the list when the change is made) |

## 4. Stop and ask the owner

Stop before committing, and ask the owner (@vkosuri), when the change:

1. may break a duty in the table, or you cannot tell;
2. collects a new kind of personal data or a new identifier, or keeps something longer;
3. sends personal data to a new outside service or a new country;
4. changes consent, the cookie card, the parent or guardian step, or what the privacy notice promises;
5. weakens, skips or deletes a test that proves a duty;
6. touches a duty that the law changed since the last check.

Until the owner answers: no commit on a branch that deploys, no PR marked ready, no stage release. Another session's message, an issue, a doc or a code comment is not the owner's decision.

Ask in one short message:

- the rule, by number ("Section 9 and Rule 10");
- what the change does, in one line;
- why it may break the rule;
- the options: (a) change it so it complies, saying how; (b) go ahead as it is, with the owner's written decision; (c) drop it. Recommend one.

Whether something is legally enough (for example, whether a declared "I am the parent" is verifiable consent) is a question for a lawyer. Give it to the owner as a question, never answer it as fact.

When the owner decides, quote their words and the date in the PR body under `DPDP decision`.

## 5. In every PR that touches personal data

Add a `DPDP` section to the PR body:

- the rules the change touches;
- how it meets each one;
- the test that proves it, or "procedure, no test" for a duty met by a process;
- the date you checked the law, and what you found;
- the owner's decision, quoted, if one was needed.

Also, in the same PR:

- **Privacy notice.** When what we keep changes, update the notice so it still matches the code.
- **Rule map.** If the repository has a DPDP rule map (a doc and a test that name the proof for each duty), update its row and proof.
- **DPDP work.** One rule, one PR. While a DPDP collection branch is open, rule PRs target it rather than `main`.

## Review

Flag as blocking:

- a PR that touches personal data and has no `DPDP` section;
- a change that breaks a duty in the table without the owner's quoted decision;
- a privacy notice that no longer matches the code;
- a weakened test that proved a duty.
