# Vahini report API, version 2

The server owns access. Apps send a customer credential; they cannot choose their subscription by sending `tier=pro`. Billing secrets and the provisioning tool belong on the server, never in an Android or iPhone build.

## Endpoints

`GET /api/v2/me` returns the caller's effective tier, stored plan, subscription status, expiry and capabilities. No credential means anonymous Free. A supplied invalid or revoked key returns HTTP 401. An unavailable subscription database returns HTTP 503 for authenticated calls.

`POST /api/v2/reports` accepts multipart fields `image` (required), `lang` (default `auto`) and `expected_text` (optional copied reference passage). Send `Authorization: Bearer <customer-key>` for an identified customer. Do not set multipart Content-Type manually in app clients; the HTTP library must include the boundary.

```bash
curl --max-time 120 https://stage.vahinitech.com/api/v2/reports \
  -F 'image=@handwriting.jpg' -F 'lang=auto'
```

Use the same request with the customer's Bearer header for Pro. Never put credentials in query strings or bundle a shared Pro credential in the app. Each customer has their own revocable key.

## Access policy

| Output | Free | Pro |
| --- | --- | --- |
| Factor scores | 1, 5, 7, 8, 18 | All 20 |
| Brief score reason | Yes | Yes |
| Detailed evidence and scoring inputs | No | Yes |
| Targets and coaching | No | Yes |
| Personalised worksheet links | No | Up to three |
| Public worksheet library | Available | Available |

The five Free factors cover formation, size, baseline, word spacing and legibility. Locked factors contain their stable IDs and required tier, without scores, evidence, targets or crops. The response is projected from an allowlist after every inference or cache hit. Expiry and revocation are checked again after inference.

Responses contain:

- `schema_version`: `2.0`.
- `scoring_version`: identifies the existing Python scoring implementation. This change does not recalibrate its formulas.
- `access`: `customer_id`, `authenticated`, `tier` (effective access), `plan_tier` (stored plan), `subscription_status`, `expires_at` (UTC Unix seconds or null), and `capabilities`.
- `summary`: legacy overall score out of 100, factor counts and score-basis description. The legacy aggregate can include image proxies.
- `factors`: stable `id`, `number`, `name`, `section_id`, `status`, `score`, `reason` and `measurement`. Pro also gets `practice`.
- `locked_factors`: IDs and `required_tier`, without restricted data.
- `recognition`: recognized text; Pro also receives recognition metadata.
- Pro-only `evidence`, `coaching` and `worksheets`. PDF paths resolve against the website origin.
- `limitations`: interpretation limits that clients should retain.

Each factor score includes the original 0–10 value, normalized 0–100 value, scale boundaries and band. A missing or invalid score is null, never substituted with zero. Status is `estimated`, `proxy`, `measured` (sensor-supplied) or `unavailable`. The image endpoint does not accept sensor measurements. Pressure, speed, stroke order and pen lifts explicitly disclose what a still image cannot measure.

Pro `reason.scoring_inputs` contains the actual inputs supplied by the scoring engine. Feature names ending in `_cv` are coefficients of variation, slope values are degrees, `n_chars`/`n_words` are counts, `_ratio` values are fractions, and `avg_score` is OCR confidence. Zone geometry includes its own profile. Composite factors list their component scores. These inputs and normalized scores are not clinically validated confidence probabilities. `confidence_probability` remains null because the current model does not produce one.

Check both HTTP status and JSON `ok`. An analysis failure returns `ok:false` with an error code; authentication failures use HTTP 401/503. The gateway applies the existing 25 MB upload and request-rate limits. There are no paid usage quotas or usage-based charges in this implementation.

## Server provisioning

Configure a persistent private path with `VAHINI_ENTITLEMENTS_DB`. Customer records, key digests and subscription changes are stored in SQLite. The ledger contains no student name, image or report. Raw API keys are returned only at issuance and are never stored in the database.

```bash
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite init
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite create-customer
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite issue-key CUSTOMER_ID --secret-file /private/new-customer-key
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite subscription CUSTOMER_ID --tier pro --status active --expires-at UTC_UNIX_SECONDS
python subscription_admin.py --db /data/entitlements/subscriptions.sqlite revoke-key KEY_ID
```

Key output files must not already exist and are created with mode 0600. Do not publish them or send them to logs. Back up the ledger using SQLite's backup API before migrations. Staging and production compose projects use separate named volumes.

Active Pro requires an explicit expiry. Cancelled Pro retains access until expiry; expired or revoked subscriptions use Free. Revoked API keys are rejected. Customer creation and subscription changes are operator-only commands; there is no public upgrade or receipt-acceptance endpoint.

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
  "catalog_version": "e2f97703fbde1939b150",
  "ok": true,
  "access": {"tier": "pro", "plan_tier": "pro", "subscription_status": "active", "expires_at": 1800000000},
  "summary": {"score": 62, "factor_count": 1},
  "factors": [{"n": 8, "s": 6.2, "st": "e"}],
  "locked": []
}
```

This abbreviated illustration shows one factor. A successful Pro report normally returns 20; Free returns five. `n` is the stable factor number, `s` the original score out of ten (or null), and `st` the status code: `e` estimated, `p` image proxy, `m` sensor measured, `u` unavailable. The overall score is out of 100. Do not interpret these scores as diagnostic probabilities.

Fetch `GET /api/v2/catalog/{catalog_version}` once to obtain factor names, generic explanation templates, score bands, practice definitions and limitations. Cache by version. The endpoint supplies an ETag and a one-year immutable cache policy. Old catalogues stay in `backend/catalogs` so saved reports remain readable. Run `python backend/compact_reports.py` when definitions change and commit the new catalogue; CI checks it. The JavaScript adapter is `frontend/src/engine/compact-client.js`. Native clients can implement the same mapping and bundle or cache the catalogue. Unknown versions must be fetched before rendering, never silently decoded with stale definitions.

Generic definitions are public educational content. They contain no customer scores, personalized evidence or private reports. Access to paid scan results is enforced on the server, regardless of what labels the client has cached. Reports use `Cache-Control: no-store`.

| Optional `include` value | Access | Adds |
| --- | --- | --- |
| `text` | Free / Pro | Recognized text, line count and recognition metadata |
| `inputs` | Pro | Actual per-factor evidence, score basis and numeric inputs |
| `coaching` | Pro | Scan-specific coaching tips |
| `evidence` | Pro | Image dimensions and factor evidence regions, including previews |

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
