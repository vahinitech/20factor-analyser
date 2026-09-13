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
