# Access and trials: giving, changing and taking back Pro

How an operator gives a family or a teacher a Pro trial, turns it into paid
Pro, renews it, moves the person back to Free, replaces a lost key and
answers "my key stopped working". Every step uses the commands in
[`backend/server/subscription_admin.py`](../backend/server/subscription_admin.py) and
follows the rules in [`backend/server/entitlements.py`](../backend/server/entitlements.py)
and [`backend/API-V2.md`](../backend/API-V2.md). Read
[13 API and capacity](13-api-and-capacity.md) and
[15 Persistence](15-persistence.md) first if the stack is new to you.

## Quick start

On the deploy server, as the deploying user, from a checkout of this
repository:

```bash
deployment/grant-pro.sh stage "test, Seetha" 2026-11-21
deployment/grant-pro.sh prod "who it is for" 2026-11-21
```

It runs "Give a family or teacher a Pro trial" below as one command: it
backs up the ledger, creates the customer, issues a random key, grants Pro
until the end of that day in India time, checks the key and asks the site
what the key gets. The key is never printed; it lands in a 0600 file under
`~/secrets/pro-keys/`, and one line (date, customer id, label, end date,
never the key) goes to `~/secrets/pro-register.txt`, or to the file
`VAHINI_PRO_REGISTER` names. Hand the key over as "How the key reaches the
person" says. Try a new kind of grant on stage first. To look up, renew,
move back to Free or revoke, use the commands in "Running the command" and
the procedures below.

Production runs the image of its last release. Until that release includes
the backend folder sort (#282), the tool there is
`/app/backend/subscription_admin.py`, not
`/app/backend/server/subscription_admin.py`. The script finds either; in
the commands below, use the path the container has.

Items marked **OWNER DECISION** have no value yet. Do not fill them in from
this page, a chat or a competitor's site; ask the owner.

## The rules the code enforces

- There are two tiers, `free` and `pro`. There is no `trial` tier: a trial
  is a Pro grant with a short expiry. The ledger cannot tell a trial from a
  paid grant except by its audit history.
- A Pro grant needs an explicit expiry in UTC Unix seconds.
  `set_subscription` refuses `--tier pro` without `--expires-at`, whatever
  the status.
- Status is one of `active`, `cancelled`, `expired`, `revoked`. Pro access
  is given only when the plan is `pro`, the status is `active` or
  `cancelled`, and the expiry is in the future. `cancelled` keeps access
  until the expiry; `expired` and `revoked` give Free at once.
- When the expiry passes, the same key falls back to Free on the next
  request. Nobody has to run anything. `/api/v2/me` then reports
  `tier: free`, `plan_tier: pro`, `subscription_status: expired`.
- A production key is `vh_` followed by 43 random characters; a stage key
  is `vh_test_` followed by 43 (owner, 2026-10-22), so a key shows where it
  works. The stage analyser has `VAHINI_ENVIRONMENT=stage`; production does
  not set it. Production refuses a `vh_test_` key with HTTP 401 and "This is
  a stage test key", and stage still takes the plain `vh_` keys it issued
  before the change, until they expire. The secret is shown once,
  written to a new file with mode 0600, and only its SHA-256 digest enters
  the ledger. A lost key cannot be recovered from the ledger, only replaced.
- A revoked key is refused (HTTP 401) on its next lookup, including a scan
  already running: access is checked again after inference.
- The browser keeps the key in the tab's memory only. Reloading the page,
  closing the tab or pressing disconnect clears it, and the person types it
  again. The key travels only in an `Authorization` header to the same
  HTTPS origin, never in a URL or browser storage.
- A Pro key is never subject to the free tier's 3 checks a day per IP
  address. When Pro lapses, the limit applies again.
- No public route changes a subscription. Only the operator command does.

## Who may do this

Only the owner, or a person the owner names, runs these commands, on the
deploy server, as the deploying user. Never from a laptop copy of the
ledger, never from a mobile app build, never from CI.

**OWNER DECISION:** who besides the owner may grant, extend or revoke Pro.

## What gets recorded, and where

The ledger (`subscriptions.sqlite`) holds three tables:

| Table | What it holds |
| --- | --- |
| `customers` | Opaque id (`cus_` + 24 hex), tier, status, expiry, last change time |
| `api_keys` | Key id (`key_` + 24 hex), customer id, SHA-256 digest, revoked flag, creation time |
| `audit` | Customer id, action, time. `subscription:<tier>:<status>:<expiry>` for every `subscription` command, `key:issue:<key id>` and `key:revoke:<key id>` for every key issued or revoked |

It holds no name, email, phone number, school, child's name, photo or
report, and must stay that way. The audit rows for keys name the key id
only, never the secret or its digest.

The operator still needs to know which customer id belongs to which family
or teacher, to renew or answer them later. Keep that link outside the
ledger and outside every repository: the customer id, the adult's contact,
whether it is a trial, and the dates. Never a child's name.

**OWNER DECISION:** where that private register lives and who can read it.
Until decided, `deployment/grant-pro.sh` appends to
`~/secrets/pro-register.txt` (mode 0600) on the deploy server.

## Stage and production have separate ledgers

Each compose project mounts its own named volume at `/data/entitlements`:
`vahini-stage_analyser-entitlements` and `vahini-prod_analyser-entitlements`
(`deploy/release.sh` in vahini-web). A key issued on stage does not work on
vahinitech.com, and the other way round. Try a new procedure on stage first,
with a made-up customer, then repeat it on production. Never copy a ledger
from one to the other.

## Running the command

The analyser container holds the tool and the ledger path. It runs as user
10001 with a read-only filesystem; `/tmp` is a private in-memory scratch
space, and `/data/entitlements` is the writable volume. On the server, set
one of these for the session:

```bash
C=vahini-analyser-stage   # or vahini-analyser-prod
admin() { docker exec "$C" python /app/backend/server/subscription_admin.py --db /data/entitlements/subscriptions.sqlite "$@"; }
```

Two commands look without changing anything; both open the ledger
read-only.

`admin show-customer cus_...` prints the customer's plan (`tier`, `status`,
`expires_at`), the access a key for this customer gets right now
(`effective`, worked out by the same code the analyser runs on every
request), each key id with its `revoked` flag and `created_at`, and the
audit history in order. It never prints a key digest. Look up the customer
id in the private register first.

`admin list-customers` prints every customer: plan (`tier`, `status`,
`expires_at`, `updated_at`), the access a key gets right now
(`effective_tier`, `subscription_status`, from the same code as
`show-customer`) and how many keys are active and revoked. Soonest expiry
first, customers with no expiry last. `--tier pro` or `--tier free` keeps
one effective tier; `--expiring-within-days 7` keeps the Pro customers whose
period ends within a week, which is the renewal list. It opens the ledger
read-only and prints no key ids, digests or audit rows. Customer ids are
opaque, so match them to people in the private register.

`admin check-key --secret-file PATH` says which customer and key id a key
belongs to, whether it is revoked, and the access it gets, without printing
the key. It reads the key from a file, never from the command line, so the
key stays out of shell history and the process list. The file must be a
regular file owned by the user running the tool, mode 0600 or stricter. It
exits 1 when no key matches. A key just issued to `/tmp/newkey` is already
such a file. For a key you hold some other way (one reported as leaked, for
example), type it without echo into a file in the container, check it and
delete the file:

```bash
read -rs KEY && printf '%s\n' "$KEY" | docker exec -i "$C" sh -c 'umask 077; rm -f /tmp/checkkey; cat > /tmp/checkkey'; unset KEY
admin check-key --secret-file /tmp/checkkey
docker exec "$C" rm /tmp/checkkey
```

Use it only on a key you already hold. Never ask a customer to send their
key so you can check it; look up their customer id instead.

An expiry is a UTC Unix time. Pick the end of the last day in India time and
convert it:

```bash
TZ=Asia/Kolkata date -d '2026-11-15 23:59:59' +%s
```

The `docker exec` route above follows the hardened compose settings and the
code, and `deployment/grant-pro.sh` runs the same steps. The script ran end
to end on stage on 22 October 2026: backup, customer, key, Pro until the
chosen day, the key check and `/api/v2/me` answering `tier: pro`, every step
as written here. Correct this page if a later run differs.

The commands keep working. A service on the private network can make the
same changes through the analyser's internal access API instead of the
command line or the ledger file: a grant (customer, key and Pro in one
step), a subscription change, a new key, a revocation and the two lookups.
It is off until the server has a token file, and it refuses any request
that came through the public gateway. Routes and rules:
[API-V2.md, "Internal access API"](../backend/API-V2.md#internal-access-api).
No service other than the analyser opens the ledger.

## Back up before every change

Take a copy with SQLite's backup API (not `cp`, which can catch a write half
done) before any change on production:

```bash
docker exec "$C" python -c "import os,sqlite3,sys; os.umask(0o077); s=sqlite3.connect('/data/entitlements/subscriptions.sqlite'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close()" \
  "/data/entitlements/backup-$(date -u +%Y%m%dT%H%M%SZ).sqlite"
```

A backup holds key digests and customer ids, so keep it as private as the
ledger. It sits in the same volume, which protects against a bad command but
not against losing the volume.

**OWNER DECISION:** whether, where and how often a copy goes off the server.

## Procedures

### First time only: create the ledger

```bash
admin init
```

Creates the file with mode 0600. The analyser never creates it; until it
exists, every request that carries a key gets HTTP 503.

### Give a family or teacher a Pro trial

1. Confirm the person qualifies. **OWNER DECISION:** who is eligible for a
   trial, and whether a trial needs a sign-up first (and what that collects).
2. Back up the ledger.
3. Create the customer: `admin create-customer` prints
   `{"customer_id": "cus_..."}`.
4. Issue a key into the container's private scratch space:
   `admin issue-key cus_... --secret-file /tmp/newkey` prints the key id.
   The file must not exist already; the tool refuses to overwrite one. If
   writing it fails, the tool revokes the key it just made.
5. Grant Pro until the trial ends:
   `admin subscription cus_... --tier pro --status active --expires-at <end>`.
   **OWNER DECISION:** trial length.
6. Confirm the key maps to the new customer with `tier: pro`:
   `admin check-key --secret-file /tmp/newkey`. Then read the key once,
   hand it over (next section), and delete the file:
   `docker exec "$C" cat /tmp/newkey`, then
   `docker exec "$C" rm /tmp/newkey`. A container restart also clears `/tmp`.
7. Write the customer id, the adult's contact, "trial" and the end date in
   the private register.
8. Check: ask the person to connect the key on the analyser page and confirm
   the full 20-factor report, or call `/api/v2/me` yourself with the key in
   an `Authorization: Bearer` header before handing it over.

### A key for a group

A school visit, a workshop or a pilot class can share one key. Grant it the
same way, with the group as the label and a short end date:

```bash
deployment/grant-pro.sh prod "pilot class, shared" 2026-11-21
```

- The key is random, like every key. The admin tool cannot make a key from
  a chosen word on purpose: a memorable key (`vh_` and a city or a number)
  can be guessed, and a Pro key is never held to the free daily limit, so
  whoever guesses it gets unlimited checks on a server that runs one scan
  at a time.
- Everyone the key reaches has Pro until it ends. Choose the end date to
  match the visit or the pilot, and end it early with `admin revoke-key`
  when the group is done.
- If the key turns up somewhere it should not (a group chat, a photo of a
  whiteboard, a public page), revoke it and issue a new one, as "A lost or
  leaked key" says. Only the customer's key changes.
- Write in the private register that the key is shared, with whom, and by
  which channel it went out.

### How the key reaches the person

The key is a password to a paid service. Treat it as one.

- Send it over a different channel from the one that carries the person's
  name or the customer id. If the email says "Hello Seetha, your trial is
  ready", the key does not go in that email.
- Never put the key in a URL, a link, a QR code that encodes a URL, a
  screenshot of a report, a support ticket, a log, a commit, a PR or a chat
  with others in it.
- Never paste a customer's key into the analyser page on a shared or
  recorded screen.
- Tell the person the page forgets the key when the tab closes, so they
  should keep it somewhere safe, such as a password manager.

**OWNER DECISION:** the approved channel (for example a phone call, an SMS,
or a password-protected message), and the wording of the hand-over message.

### Turn a trial into paid Pro

No new customer and no new key: the same key keeps working. Back up, then:

```bash
admin subscription cus_... --tier pro --status active --expires-at <paid end>
```

Note "paid" and the new end in the private register. Payment is taken and
checked outside this system (see the gaps below); grant only after the owner
confirms the payment. **OWNER DECISION:** prices, plan lengths, and how a
payment is confirmed. Nothing about prices or paid features goes on the
website until the owner sets them.

### Renew

Back up, then run the same command with the next end date. The expiry is
replaced, not added to, so compute the new end from the current one when
renewing early.

### The person cancels

To keep access until the paid period ends, keep the same end date:

```bash
admin subscription cus_... --tier pro --status cancelled --expires-at <current end>
```

When the date passes, the key falls back to Free on its own.

### Move back to Free now

```bash
admin subscription cus_... --tier free --status active
```

The key still identifies the person, with Free access and the daily limit.
To end Pro at once while keeping the record of the plan, use
`--tier pro --status revoked --expires-at <current end>` instead; access is
Free from the next request either way.

### A lost or leaked key

1. Back up.
2. Find the customer's key ids with `admin show-customer cus_...` and
   revoke the lost one: `admin revoke-key key_...`. It is refused from the
   next request, and the audit history records the revoke.
3. Issue a new key for the same customer and hand it over as above. The
   subscription is on the customer, so nothing else changes.

Before issuing a replacement, confirm the request comes from the person in
the private register, through the contact recorded there, not from whoever
asked.

### "My key stopped working"

Ask what the page shows; the server's answer tells you which case it is.

| What they see | Cause | What to do |
| --- | --- | --- |
| The key box is empty after a reload or a new tab | The page keeps the key in the tab's memory only | Type the key again. Nothing is wrong |
| Five factors instead of twenty, and the key is accepted | The Pro period ended (`subscription_status: expired`), or the plan was moved to Free or revoked | `admin show-customer cus_...` shows the plan, the effective access and the audit history. Renew if that is what was agreed |
| "Today's free checks are used" | Same as above: without Pro the 3-a-day limit applies | As above |
| The key is refused (HTTP 401, "Invalid API credential") | Revoked, mistyped, from the stage ledger, or missing the `vh_` start | `admin show-customer cus_...` lists the customer's key ids and which are revoked. If it was revoked or lost, issue a new one |
| "Subscription service is not configured" or "unavailable" (HTTP 503) | The ledger is missing, unreadable or the volume is not mounted | Server problem, not the customer's: check the container and volume, and restore from a backup if the file is damaged |

Never ask the person to send the key back to you to check it. Have them
connect it on the page, and look up their customer id instead.

## Gaps, and where each is planned

| Gap | Today | Where it is planned |
| --- | --- | --- |
| No self-service sign-up or trial button | Every trial is created by hand on the server | Pro product blueprint, [20factor-analyser-pro#1](https://github.com/vahinitech/20factor-analyser-pro/issues/1) section 7 (parent self-serve tier, accounts) |
| No login and no key recovery | A lost key is replaced by the operator; "Website sign-in and self-service account recovery are not provided" (API-V2.md) | 20factor-analyser-pro#1, sections 5 and 7 (accounts, parent portal) |
| No billing and no store verification | Payment is checked by hand; grants come only from the operator tool | API-V2.md, "Billing integration still required" (Google Play and App Store verification), and 20factor-analyser-pro#1 section 7 |
| The key is typed again on every visit | Tab memory only, by design, so the key never sits in browser storage | Goes away with sign-in; not planned separately |

## Requests and what people would pay

- **Request Pro.** The "See all 20 skills" card under a Free report links to
  vahinitech.com's `reach.html?topic=pro&from=report`, a short form (email,
  who will use Pro, an optional note). Requests are kept and mailed to the
  team by vahini-web's persist service and listed in its Friday report. Grant
  access with the commands above.
- **Price.** The print popup ("Get your report PDF") asks, optionally, what a
  report with all 20 skills would be worth: in rupees for a browser in India,
  dollars elsewhere (from the time zone). The answer goes with that lead as
  `price` and `currency`; the Friday report counts the answers per currency.
  The values (`nothing`, `up_to_50`, `100`, `200`, `more`; `up_to_3`, `5`,
  `10`, `more`) are matched in vahini-web's `tools/weekly-report.mjs`, so a
  change here changes there in the same order of PRs. `tests/print-popup.mjs`.

## Owner decisions still open

- Trial length.
- Whether a trial needs a sign-up, and what it collects.
- Who is eligible for a trial (families, teachers, schools, therapists).
- Prices and paid plan lengths, and how a payment is confirmed.
- Who besides the owner may grant, extend or revoke.
- The approved channel for handing over a key.
- Where the private register lives.
- Off-server backups of the ledger.

Background: the subscription work landed on 13 September 2026; the
website's dated note is `docs/history/API-SUBSCRIPTIONS-2026-09-13.md` in
vahinitech/vahini-web.
