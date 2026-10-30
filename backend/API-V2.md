# Vahini report API, version 2

The server owns access. Apps send a customer credential; they cannot choose their subscription by sending `tier=pro`. Billing secrets and the provisioning tool belong on the server, never in an Android or iPhone build.

## Endpoints

`GET /api/v2/me` returns the caller's effective tier, stored plan, subscription status, expiry and capabilities, plus `practice: {areas_max, exercises_max, tips_max}`: how many skills get practice in one report and how many exercises and tips each shows (Free 3, 1, 1; Pro 3, 2, 2). Those numbers live in one place, `backend/report/practice_catalog.py` `TIERS`, so a new plan can change them without a frontend release; the browser falls back to the catalogue's `practice.tiers` when it has none. No credential means anonymous Free. A supplied invalid or revoked key returns HTTP 401. An unavailable subscription database returns HTTP 503 for authenticated calls.

`POST /api/v2/reports` accepts multipart fields `image` (required), `lang` (default `auto`) and `expected_text` (optional copied reference passage). Send `Authorization: Bearer <customer-key>` for an identified customer. Do not set multipart Content-Type manually in app clients; the HTTP library must include the boundary.

```bash
curl --max-time 120 https://stage.vahinitech.com/api/v2/reports \
  -F 'image=@handwriting.jpg' -F 'lang=auto'
```

`lang` is `auto` or one or more BCP 47 tags separated by commas, with no spaces: `en`, `te`, `en,te`, `te-Telu-IN`, `en-Latn-GB,te`. A tag is a language subtag (2 to 8 lowercase letters), then an optional script (`Latn`, `Telu`) and an optional region (`IN`, `GB`). The server reads each tag by its language subtag (`backend/languages/tags.py`), so `te-Telu-IN` is read, cached and answered exactly as `te`, and the response's `lang` and `langs` give the short form. `EN`, `en_US` and `en-latn` do not match the schema. Every value the old pattern `^([a-z]{2,8}|auto)$` allowed still does, and still reads the same way. A language the server has not loaded (`VAHINI_OCR_LANGS`) is read with the languages it has, as before.

`profile` (optional) carries a school, class and child profile as JSON text: teaching choices layered on the language packs, school first, then class, then child (`backend/languages/profile.schema.json`, `$defs/layers`; design in [docs/20-languages.md, section 18.1](../docs/20-languages.md#181-who-sets-what)). Each field says whether it sets, adds or removes: the letter model and the letter forms the class accepts (both only from the lists the language pack has reviewed; the Latin pack has none yet), the ruling, class word lists, exception words and what to skip (`digits`, `formulas`), and which language-skill checks run. A child's profile may only set the letter model. There is no field for health, diagnosis, ability or a name outside the exception words. Words are literals, never patterns.

```bash
curl --max-time 120 https://stage.vahinitech.com/api/v2/reports \
  -F 'image=@handwriting.jpg' -F 'lang=en' \
  -F 'profile={"class": {"exceptions": {"add": {"words": ["Pihu"]}}}}'
```

The profile is sent with every request and never stored, logged or sent to analytics: exception lists can hold children's names. Who may keep a profile on the server is the owner's decision still to make (docs/20-languages.md, open question 8). The response carries only `ruleset`, the hash of the language pack the scorer reads and the resolved profile; without a profile it is the pack's own hash and every score is what it was before profiles existed. The same photo with the same ruleset gives the same scores; a changed profile is a new ruleset, a new cache entry and a different `comparability.ruleset`.

What a profile changes today: a letter whose accepted forms are set to an empty list (`{"variants": {"set": {"o": []}}}`) is not taught yet. When every letter that factor 3 (loops and bowls) or factor 6 (tall letters) counts is untaught, that factor is "Not measured", with the profile's reason, never a higher score. A profile may not take out every letter, or every small letter. Exception words, skip rules, word lists, checks, ruling and letter model are checked, resolved and hashed but not yet used: the script decision and the language skills that will read them are not built, and exception words never change a geometry factor.

**Text that identifies the writer is blanked** (India's DPDP Act, section 6(1): only the data the purpose needs). Before a scan's answer is cached or returned, names after "My name is", "Name:", "I am" and "I'm", email addresses, phone numbers (ten digits or more), roll numbers and school names in every text field (`text`, the spelling and grammar tokens, `/ocr`'s texts) become `[name]`, `[email]`, `[phone]`, `[roll number]` and `[school]` (`backend/reading/identifiers.py`). Scores, boxes and counts do not change; a name written alone on a line is not recognisable and stays.

`age_band` (optional) is the writer's age as two whole-year ages from 3 to 18, the first below the second: `6-7`, `9-10`. It is never a birth date or a single exact age, so it says which age norms a page could be compared with and nothing more about the child. A band in any other form (`2019-05-01`, `7`, `7-6`, `06-07`) is HTTP 422 with `detail: {error_code: "age_band_invalid", error, field: "age_band"}`, before the photo is read or a free check is counted. A valid band is echoed as `age_band` at the top of the report, in both formats and on `/report-python`, and is not stored or logged. **No score uses it yet**: the age norms that will read it are #216, so the same photo gives the same scores and the same cache entry with any band or none.

```bash
curl --max-time 120 https://stage.vahinitech.com/api/v2/reports \
  -F 'image=@handwriting.jpg' -F 'lang=en' -F 'age_band=6-7'
```

A refused profile answers before the photo is read and does not count against the free checks: HTTP 413 with `detail: {error_code: "profile_too_large", error, field}` over 16384 bytes, otherwise HTTP 422 with `error_code` one of `profile_not_json`, `profile_field_not_allowed` (a field a profile may not hold), `profile_list_too_long` (a list over its limit, alone or with the layers together), `profile_not_in_pack` (a letter model or form the pack does not list), `profile_empties_class` or `profile_invalid`. `field` says where, such as `class.exceptions.add.words`; the error never repeats what the profile holds.

Use the same request with the customer's Bearer header for Pro. Production keys start `vh_`; stage keys start `vh_test_`, and production answers 401 to one with a message naming stage. Never put credentials in query strings or bundle a shared Pro credential in the app. Each customer has their own revocable key.

**Stored reports.** When the server keeps report records (`VAHINI_REPORT_STORE_DIR` set; `/health` says `report_store: true`), a successful `format=compact` report also carries `receipt: {id, token, expires}`. Keep it: it is the only way to read the record later, and it is never sent again. `GET /api/v2/reports/{id}` with header `X-Report-Token: <token>` returns the record (`schemas/stored-report.schema.json`): the day, tier, scores, sections, comparability counts and marks, never a photo or the words read. `DELETE` on the same URL with the same header deletes it. The receipt's `read_token` is for the shared PDF: it is refused by `GET`, `DELETE` and renew, and works only in `POST /api/v2/compare` (`Authorization: Bearer <Pro key>`, body `{"receipts": [{"id","token"}, {"id","token"}]}`, the earlier check first, either token), which returns `{before, after, notes}` (`schemas/compare.schema.json`). Without Pro it answers 403 before opening a record; 400 unless exactly two different receipts; 404 with `detail.side` when one opens nothing. It stores nothing. `POST /api/v2/reports/renew` with `{"receipts": [{"id", "token"}, ...]}` (at most 50) keeps each for another 12 months; send it after a new check. Unknown, expired or deleted records and a wrong token all answer 404. `format=expanded` keeps nothing. Details and the privacy rules: [docs/15-persistence.md](../docs/15-persistence.md#report-records-kept-for-every-family-no-personal-data).

## Access policy

| Output | Free | Pro |
| --- | --- | --- |
| Factor scores | 1, 5, 7, 8, 18 | All 20 |
| Brief score reason | Yes | Yes |
| Example crops from the visitor's photo (`evidence`) | Its five factors | All 20 |
| Scoring inputs (`inputs`) | No | Yes |
| Targets and coaching | No | Yes |
| Personalised worksheet links | No | Up to three |
| Public worksheet library | Available | Available |

The five Free factors cover formation, size, baseline, word spacing and legibility. Locked factors contain their stable IDs and required tier, without scores, evidence, targets or crops. The response is projected from an allowlist after every inference or cache hit. Expiry and revocation are checked again after inference.

Responses contain:

- `schema_version`: `2.0`.
- `scoring_version`: identifies the existing Python scoring implementation. This change does not recalibrate its formulas.
- `access`: `customer_id`, `authenticated`, `tier` (effective access), `plan_tier` (stored plan), `subscription_status`, `expires_at` (UTC Unix seconds or null), and `capabilities`.
- `summary`: overall score out of 100, factor counts and score-basis description. The overall counts five factors (letter formation 40 points, baseline 20, size 20, line straightness 10, slant 10); the others are practice findings.
- `factors`: stable `id`, `number`, `name`, `section_id`, `status`, `score`, `reason` and `measurement`. Pro also gets `practice`.
- `locked_factors`: IDs and `required_tier`, without restricted data.
- `recognition`: recognized text; Pro also receives recognition metadata. In it, `ink_rows` is true when the factors were measured on rows found from the ink instead of the reader's lines, and `ink_reason` says why: `language` (a language set in `VAHINI_INK_GEOMETRY_LANGS`) or `read_in_fragments` (the reader read the page in pieces, as it does joined cursive; #277). A code, no text.
- Pro-only `evidence`, `coaching` and `worksheets`. PDF paths resolve against the website origin.
- `limitations`: interpretation limits that clients should retain.
- Pro `sections`: the four section scores as the engine computed them for the overall score (`id`, `name`, `score` out of ten or null, `normalized`, `weight`, the section's share of the overall score, `factor_count`, `scored_factor_count`). Compact Pro reports carry `sections: [{id, s, w}]`. Free gets neither, because a section mean includes locked factors. Details for the before/after comparison: [docs/19-comparison-data.md](../docs/19-comparison-data.md).
- `comparability` on every successful report, both tiers and both formats: `lines`, `words` and `characters` read (null when nothing was read), the `script` of the letters read, reading-engine `languages`, `printed_lines` left out, `page` (`handwriting` or `handwriting_with_print`), the recognition level as `reading`, `passage_aligned`, and `ruleset`. Counts only, no text. A comparison uses them to warn that two pages are not alike.
- `age_band`: the request's age band as sent (for example `6-7`), only when the request sent one. Not used by any score yet.
- `turned`: 90, 180 or 270, only when the photo was taken sideways or upside down with no EXIF turn and the analyser read it turned that many degrees clockwise (#297). Every box, mark and size in the report (`evidence`, `photo_width`, `photo_height`) is on the turned photo, so a viewer turns its own copy the same way before drawing on it. A photo whose lines run up and down, when the analyser cannot tell which way up it is, is not scored: `ok: false` with error code `turned_page`.
- `ruleset`: the sha256 of the rules the page was scored by, the language pack and the request's `profile`, on every report the scan produced (both tiers, both formats). Never the profile itself.

Each factor score includes the original 0–10 value, normalized 0–100 value, scale boundaries and band. A missing or invalid score is null, never substituted with zero. Status is `estimated`, `proxy`, `measured` (sensor-supplied) or `unavailable`. The image endpoint does not accept sensor measurements. Pressure, speed, stroke order and pen lifts explicitly disclose what a still image cannot measure.

Pro `reason.scoring_inputs` contains the actual inputs supplied by the scoring engine. Feature names ending in `_cv` are coefficients of variation, slope values are degrees, `n_chars`/`n_words` are counts, `_ratio` values are fractions, and `avg_score` is OCR confidence. Zone geometry includes its own profile. Composite factors list their component scores. These inputs and normalized scores are not clinically validated confidence probabilities. `confidence_probability` remains null because the current model does not produce one.

Check both HTTP status and JSON `ok`. An analysis failure returns `ok:false` with an error code; authentication failures use HTTP 401/503. When the server cannot read the page at all (the OCR engine will not load, or a run fails), it answers HTTP 503 with `detail: {error_code: "ocr_unavailable", error}` and `Retry-After: 60`: try the same photo again later. It never scores such a page from OCR-free line shapes, because that gave the same photo different scores (#112). The answer is not cached and does not count against the daily free checks. Without `error_code`, a 503 is the scan cap (`Retry-After: 20`). The gateway applies the upload and request-rate limits described below. There are no paid usage quotas or usage-based charges in this implementation.

**Free tier: 3 checks a day per IP address** (`backend/server/daily_limit.py`, `VAHINI_DAILY_SCANS_PER_IP`; owner decision 2026-10-09). `/ocr`, `/analyze-vl`, `/report-python` and `/api/v2/reports` share one allowance per client address. Only a check that produced a result counts; a refusal (busy, too large, no handwriting) does not, and a repeat of a cached photo does. The day turns over at midnight India time. The fourth check gets HTTP 429 with `detail: {error_code: "daily_limit", error, limit}` and `Retry-After` in seconds. **A Pro access key is never limited.** Private and loopback addresses (CI, the docker network) and the addresses in `VAHINI_DAILY_LIMIT_EXEMPT` are not counted. Counts are kept in memory and start again when the analyser restarts.

## Server provisioning

Configure a persistent private path with `VAHINI_ENTITLEMENTS_DB`. Customer records, key digests and subscription changes are stored in SQLite. The ledger contains no student name, image or report. Raw API keys are returned only at issuance and are never stored in the database.

```bash
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite init
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite create-customer
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite issue-key CUSTOMER_ID --secret-file /private/new-customer-key
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite subscription CUSTOMER_ID --tier pro --status active --expires-at UTC_UNIX_SECONDS
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite revoke-key KEY_ID
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite show-customer CUSTOMER_ID
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite list-customers --expiring-within-days 14
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite check-key --secret-file /private/key-to-check
```

Key output files must not already exist and are created with mode 0600. Do not publish them or send them to logs. `show-customer` and `check-key` open the ledger read-only. `show-customer` prints the plan, the effective access (computed by the same function `access_for` uses), each key id with its revoked flag and creation time, and the audit history; it never prints a key digest. `check-key` reads one key from a regular file owned by the caller with mode 0600 or stricter (never from the command line), and prints the key id, customer id, revoked flag and effective access without the secret; it exits 1 when no key matches. Issuing and revoking a key write `key:issue:<key id>` and `key:revoke:<key id>` to the audit table, never the secret or its digest. Back up the ledger using SQLite's backup API before migrations. Staging and production compose projects use separate named volumes.

Active Pro requires an explicit expiry. Cancelled Pro retains access until expiry; expired or revoked subscriptions use Free. Revoked API keys are rejected. Customer creation and subscription changes are operator-only commands; there is no public upgrade or receipt-acceptance endpoint.

The step-by-step procedure for trials, paid Pro, renewals, moving back to Free, lost keys and "my key stopped working", with the open owner decisions: [docs/17-access-and-trials.md](../docs/17-access-and-trials.md).

## Internal access API

A service on the private network that gives, changes or takes back Pro (a code redemption page, an operator page, a billing hook) calls this API instead of opening the SQLite ledger. Only the analyser opens its ledger. The code is `backend/server/access_api.py`; the messages are `backend/schemas/access-*.schema.json`.

It is off by default. Three checks run on every request under `/internal/`, before routing or reading the body:

1. `VAHINI_ACCESS_API_TOKEN_FILE` must name a readable file holding a shared token of at least 32 characters. Otherwise every path answers 404, so the API cannot be found. The file is read on each request, so replacing it rotates the token without a restart.
2. A request with `X-Forwarded-For`, `X-Real-IP`, `Forwarded` or `CF-Connecting-IP` came through a proxy, and gets 404. The public gateway adds these headers; a service calling the container directly on the private network does not. Never route `/internal/` through a public gateway; this check is the second line of defence, not the first.
3. `Authorization: Bearer <token>` must match the file, compared in constant time. Otherwise 401.

| Route | Body | Answer |
| --- | --- | --- |
| `POST /internal/access/v1/grants` | `{"expires_at": UNIX}` | 201, `access-key`: a new customer with Pro until `expires_at` and its first key, written in one transaction |
| `GET /internal/access/v1/customers/{customer_id}` | none | 200, `access-customer` |
| `PUT /internal/access/v1/customers/{customer_id}/subscription` | `{"tier", "status", "expires_at"}` | 200, `access-customer` after the change |
| `POST /internal/access/v1/customers/{customer_id}/keys` | none | 201, `access-key`: another key for the customer |
| `POST /internal/access/v1/keys/{key_id}/revoke` | none | 200, `access-customer` of the key's owner |
| `POST /internal/access/v1/keys/lookup` | `{"key": "vh_..."}` | 200, `access-key-lookup` |

The rules are the operator tool's, from the same functions in `entitlements.py`: Pro needs an explicit expiry, a grant's expiry must be in the future, and `effective` is computed the way `/api/v2/me` computes access. A secret appears in one place only, the 201 answer that issues it; deliver it and do not log or store it. The lookup takes the secret in the body, never in a URL. No answer contains a key digest. Bodies are closed: an unknown field, a string where a number belongs or a `true` expiry is refused with 422. An unknown customer, key id or secret is 404, a body the ledger rules refuse is 422, and a missing or unreachable ledger is 503. Every answer carries `Cache-Control: no-store`. Error bodies use `error.schema.json`.

`ANALYSER` below is the container's address on the private network, never the public host.

```bash
TOKEN=$(cat "$VAHINI_ACCESS_API_TOKEN_FILE")
curl -s -X POST "$ANALYSER/internal/access/v1/grants" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"expires_at": 1795000000}'
```

The audit rows are the same as the command line's: `key:issue:<key id>`, `key:revoke:<key id>` and `subscription:<tier>:<status>:<expiry>`. A grant writes the key row first, then the subscription row. The command line keeps working alongside the API.

## Compatibility and rollout

Set `VAHINI_ENFORCE_TIERS=1` for a paid deployment. It applies the same restrictions to `/report-python` and makes detailed `/analyze-vl` evidence Pro-only, preventing an old-route bypass. The hosted stage/prod compose configurations set this flag. A standalone open-source installation can retain the previous unrestricted legacy contract by leaving it unset; such an installation is not a protected paid service. The version-2 endpoint always applies its access policy.

The web renderer recognises the Free legacy response and shows five factors plus a link to the public worksheet library. Full Pro reports retain their existing renderer. App clients should use version 2. Website sign-in and self-service account recovery are not provided by this API-key provisioner.

## Billing integration still required

There is no verified store connection in this repository. Pro grants currently come from the operator tool, not from an app asserting that a purchase succeeded. Before selling automatic Android subscriptions, connect Google Play purchase verification and renewal/refund notifications to the customer ledger, including purchase-to-account binding and replay/idempotency checks. The iPhone app will need the equivalent App Store verification. No real charges or store products were created here.

Primary guidance: [Google Play backend verification](https://developer.android.com/google/play/billing/security), [Google Play server integration](https://developer.android.com/google/play/billing/backend), [App Store Server API](https://developer.apple.com/documentation/appstoreserverapi).


## Compact responses for browsers and apps

Opt in with `POST /api/v2/reports?format=compact`. The existing default remains expanded version 2.0 for API compatibility. Compact reports use schema 2.1. Both formats use the same server subscription check and score values. Free reports and their printable PDFs show five factors, numbered 1, 5, 7, 8 and 18. The hosted browser now requests compact reports with `include=text`.

```json
{
  "schema_version": "2.1",
  "format": "compact",
  "catalog_version": "85108292a841082ce34e",
  "ok": true,
  "access": {"tier": "pro", "plan_tier": "pro", "subscription_status": "active", "expires_at": 1800000000},
  "summary": {"score": 62, "factor_count": 1},
  "factors": [{"n": 8, "s": 6.2, "st": "e"}],
  "locked": []
}
```

This abbreviated illustration shows one factor. A successful Pro report normally returns 20; Free returns five. `n` is the stable factor number, `s` the original score out of ten (or null), and `st` the status code: `e` estimated, `p` image proxy, `m` sensor measured, `u` unavailable. The overall score is out of 100. Do not interpret these scores as diagnostic probabilities.

Fetch `GET /api/v2/catalog/{catalog_version}` once to obtain factor names, generic explanation templates, score bands, practice definitions and limitations. Cache by version. The endpoint supplies an ETag and a one-year immutable cache policy. Old catalogues stay in `backend/catalogs` so saved reports remain readable. Run `python backend/report/compact_reports.py` when definitions change and commit the new catalogue; CI checks it. The JavaScript adapter is `frontend/src/engine/compact-client.js`. Native clients can implement the same mapping and bundle or cache the catalogue. Unknown versions must be fetched before rendering, never silently decoded with stale definitions.

Since the practice catalogue (docs/10-practice-framework.md, approved 2026-10-11 in #122) each factor also carries `exercises` (id, level, title, unit, script, needs, worksheet, steps, example, check) and `tips` (id, text), and the catalogue has a top-level `practice` block: `stages` (Learning, Improving, Mastering, Strong by band), `dosage` (tries a day or a week by band, and how many exercises the band asks for), `tiers` (the defaults above), `units` and the `spelling` exercise. Catalogues archived before it have neither; the schema treats both as optional for that reason. The content is `backend/report/practice_catalog.py`, checked when it is imported.

From catalogue `85108292a841082ce34e` every exercise and tip also carries `i18n`, its text by language code: `i18n.te` holds `title`, `steps` and `check` for an exercise and `text` for a tip, in Telugu (`example` only when it is not Latin practice text; today none is, since the child practises English letters). A missing language or field falls back to the English one. The Telugu is draft wording until a native speaker has checked it. `i18n` is optional in the schema, because older catalogues have none. The report's own sentences are not in the catalogue: the browser holds them in `frontend/src/report/strings/<lang>.js`.

From catalogue `cbe45138b323d5608d01` (owner approval of report version C, 2026-10-11) every exercise and tip also carries `helps`, which skills it develops by factor number with a weight from 0 to 1: its own factor at 1.0, others it truly helps from 0.3 to 0.8 (the two-line ladder: `{"5": 1.0, "6": 0.6}`; spelling entries carry `{}`). The highest weight is always the entry's own factor. Every exercise also carries `model`, the drawing the report shows under "Copy this" (`ladder`, `zones`, `baseline`, `gaps`, `letter-gaps`, `margin`, `slant`, `loops`, `trace`, `start-dots`, `pairs`, `waves`, `page`). Both are optional in the schema, because older catalogues have neither. The steps, checks and tips in this version are rewritten in short sentences (at most three per step, at most 14 words each; the catalogue's import check holds it), and a step's sentences are its numbered steps. How a report chooses among them: docs/10-practice-framework.md, "Many-to-many selection".

From catalogue `82ca133f7363f8489dd8` (owner, 2026-10-11) each factor also carries `why` (one short sentence: why the skill helps), `win` (finishes "You'll know it's working when ..."), `page` (the skill's page on vahinitech.com, `handwriting-<skill>`, without `.html`) and `i18n` with the Telugu of `why` and `win`. Page 2 prints them under each skill to grow. All four are optional in the schema, because older catalogues have none; a report rendered from an older catalogue takes them from the bundled copy.

Generic definitions are public educational content. They contain no customer scores, personalized evidence or private reports. Access to paid scan results is enforced on the server, regardless of what labels the client has cached. Reports use `Cache-Control: no-store`.

| Optional `include` value | Access | Adds |
| --- | --- | --- |
| `text` | Free / Pro | Recognized text, line count and recognition metadata |
| `inputs` | Pro | Actual per-factor evidence, score basis and numeric inputs |
| `coaching` | Pro | Scan-specific coaching tips |
| `evidence` | Free / Pro | Image dimensions and factor evidence regions, including previews cropped from the uploaded image. Free receives the regions of its five factors only. Each region also lists `marks` (boxes and lines where the factor was measured) in the uploaded photo's pixels, with that photo's `photo_width` and `photo_height`: [docs/19-comparison-data.md](../docs/19-comparison-data.md) |

With `text`, a compact report also carries `language` (#317): the words the writer spelt another way and the sentences a fixed English grammar rule would change, each with its place on the page in processed-image pixels. The expanded report carries it for every tier. Shape: `{"version": 1, "checked": true, "reason": null, "rows": {"read", "checked", "not_read", "over_cap", "unclear"}, "spelling": [{"written", "suggestion", "kind", "against", "places"}], "grammar": [{"rule", "written", "suggestion", "places"}]}`; `against` is `list` (free writing: the word is not in the word list) or `sentence` (the request's `expected_text`, copied or dictated: the suggestion is the sentence's word, and no grammar is run); a place is `{"line", "bbox", "placed"}` with `placed` `letters` (from the reader's letter columns) or `estimated` (from the share of the line's text). `checked` is false, with a `reason`, when the page was not checked. An empty list never means the page has no mistakes: the check reads at most six rows again and reports a spelling only when the reader's letter scores leave no doubt (docs/history/spelling-grammar-2026-10-24.md). It never changes a score and is never stored.

Combine values with commas, for example `?format=compact&include=text,inputs,coaching`. Request image evidence only when needed; it is the largest part of an expanded response. Unauthorized paid fields return 403 before inference. Compact scans without `evidence` skip crop-preview construction and base64 encoding. Evidence and basic scan cache entries are separate, so requesting evidence later can require another processing pass. This version does not provide a stored-report detail GET endpoint.

### Measured size and computation

Synthetic mixed-page fixture from `backend/tests/test_server_pipeline.py`, measured on 13 September 2026. JSON is minified UTF-8; gzip uses level 1. Compact measurements omit optional fields. Expanded Pro includes its evidence previews, so this is a useful delivery-mode comparison, not a claim that equivalent fields shrink by the same amount.

| Response | JSON bytes | Gzip bytes | Builder + JSON, ms per response |
| --- | ---: | ---: | ---: |
| Free expanded | 3,793 | 1,069 | 0.173 |
| Free compact | 419 | 258 | 0.013 |
| Pro expanded | 147,679 | 17,115 | 1.291 |
| Pro compact | 774 | 309 | 0.028 |

The shared catalogue is 6,182 bytes, or 2,249 with gzip. The server serializes it once per process. Timings average 100 iterations and exclude OCR, network latency and concurrency. The existing website gateway compresses JSON.

For 10,000 responses matching this fixture, compressed Pro bodies total about 171 MB expanded versus 3.09 MB compact, excluding HTTP headers, uploads and catalogue downloads. Each fresh client also downloads the catalogue; returning clients reuse it. Actual savings depend on scan content and requested fields. OCR and image uploads still need capacity planning. A bounded inference queue, per-customer scan quotas and asynchronous jobs are the next scaling steps; these are not implemented by this response-format change.

### Browser account access and upload bounds

The browser offers an optional private access-key connection. Keys remain only in the current tab's memory and are cleared by disconnect or reload. Before each same-origin scan, `/api/v2/me` resolves the current server entitlement. Free requests include `text`; Pro requests include `text,inputs,coaching,evidence` for the detailed printable report. The key is sent only in an Authorization header to the same HTTPS origin (HTTP loopback is allowed for development), never to fallback hosts, storage or a URL. Redirects are rejected. This is operator-issued key access, not store billing, signup or account recovery.

Backend limits apply without nginx: request bodies are counted before multipart parsing (6 MiB including framing), individual uploads are limited to 5 MiB (one page photo: the website sends at most 2600 px and the Android app 2200 px, both as JPEG), and decoded images or first-page PDF renders must not exceed 24 million pixels. PDFs must contain 1–100 pages; only the first is analysed. Decoding and entitlement database lookups run in worker threads. Cache hits still pass the post-processing entitlement check. These bounds do not replace inference concurrency limits or per-customer quotas.

## Machine-readable contract

`backend/schemas/` holds JSON Schema (draft-07) files for every version-2 message. `backend/report/contract_schemas.py` validates a body from Python or the command line, and `backend/tests/test_schemas.py` checks in CI that the committed examples, every archived catalogue and the live builder output for Free, Pro and failed reports still match. See [the schema README](schemas/README.md) for the file list and how a client repository uses them. The `profile` field's own shape is `backend/languages/profile.schema.json`.
