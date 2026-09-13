# Report changes and review invariants

Read `backend/API-V2.md` for the current request/response specification and `CLAUDE.md` for repository conventions. These rules capture failures encountered in the hosted Free/Pro rollout. Verify the implementation when changing a policy; do not treat this file as a second source of score formulas.

## Access and subscription ownership

- Free returns factors 1, 5, 7, 8 and 18. Pro returns all 20. Keep API, browser, examples and printable reports aligned. The three selected coaching priorities are not the number of Free factors.
- `backend/entitlements.py` resolves access from the server ledger and hashed, revocable customer keys. Client parameters or locally stored app state must never grant Pro. Recheck expiry/revocation after inference and apply an allowlist after cache hits.
- The hosted `VAHINI_ENFORCE_TIERS=1` setting protects legacy `/report-python` and Pro-only evidence access through `/analyze-vl`. A standalone unrestricted legacy installation is not a protected paid service. New routes must not bypass the same policy.
- Operator grants exist. Store verification, purchase ownership, renewal/refund integration, login/recovery and metered usage are not implemented by that ledger. Do not claim automatic Android/iPhone subscriptions without a verified integration.
- Preserve private persistent subscription data across deployments. Never put shared Pro credentials in a frontend, query string, log, fixture or public catalogue. Use synthetic records and clean up temporary grants when testing.

## Compact API and client compatibility

- `/api/v2/reports` defaults to expanded schema 2.0 for existing clients. Compact schema 2.1 is opt-in with `format=compact`; the hosted browser uses it. Do not silently change the default or mix schema fields.
- Compact rows carry stable factor number `n`, score `s` out of ten (nullable), and status `st`. Null is unavailable, not zero. Preserve image-proxy limitations; normalized scores are not confidence or diagnostic probabilities.
- `backend/compact_reports.py` projects directly from the scoring payload. Do not build a full expanded DTO just to discard its text and images.
- Public definitions are in immutable, versioned `backend/catalogs/*.json`. Generate with `python backend/compact_reports.py`; verify with `--check`. Retain old versions for saved reports. Do not edit an existing version in place or decode new reports using stale definitions.
- The browser decoder is `frontend/src/engine/compact-client.js`. Keep factor identity, status, scale, limitations and version checks consistent. Cache public definitions, not private reports. Public generic practice definitions are not private customer results.
- Dictionary responses have ETag and immutable caching; gzip gateways can weaken ETags. Conditional GET must handle weak validators. Private report responses remain `no-store`.
- Optional `text` is available to both tiers; `inputs`, `coaching` and `evidence` require Pro. Unknown includes return 422; unauthorized includes return 403 before inference. Reauthorization after inference must prevent a just-expired subscription from receiving paid fields.
- Basic compact scans skip crop-preview generation and base64 encoding while retaining scoring inputs. Evidence/basic cache keys differ. There is no stored-report detail GET endpoint; a later evidence request can require another processing pass.
- Request-size, upload and inference protections still apply. Payload benchmarks must name the fixture, included fields, gzip setting and excluded work. Do not extrapolate a serialization test into 10,000 concurrent OCR users.

## Browser, worksheets and PDF

- Browser keys stay in page memory only. Resolve access through `/api/v2/me` before choosing paid includes, and never send credentials to fallback hosts or follow credentialed redirects.
- Rebuild `frontend/scripts/core/engine.bundle.js` with `python frontend/build_bundle.py` after source changes. Do not patch the packed bundle directly.
- Free renderer: five factors, no hidden paid values in HTML, same policy when printed. `sample-report.html` defaults to the five-factor synthetic example. `?example=pro` selects only a synthetic preview and never changes server entitlement.
- A Free PDF should fit one A4 page for the ordinary sample, include all five scores and the Vahini logo, and avoid an empty trailing sheet. Long content must remain readable rather than being clipped to force one page.
- Use the existing `.page` print contract and print-fit hook. Disable the report screen's entrance transform/animation in print; it caused a blank second sheet even when the report content fitted. Never use fixed-height clipping to hide overflow.
- Existing Pro summaries can highlight three priorities while the scorecard includes all available factors. Do not restore the obsolete email upsell or three-factor Free wording.
- Worksheet recommendations use eligible returned factors and the shared catalogue, without student identity in download URLs. Generic worksheet access is distinct from personalised Pro recommendations.

## Checks and consumer handoff

Use the actual CI workflow for current commands. Relevant checks include the core backend suite, `node tests/compact-client.test.mjs`, `node tests/worksheets.test.mjs`, bundle regeneration, and `npm run test:regression:headless`. Add/adjust meaningful checks for changed access or serialization behavior.

Use no-Paddle core conditions when testing core logic; full OCR recognition is a separate integration check with model/runtime prerequisites. State which ran. Test APIs with synthetic images and credentials. Inspect actual PDFs for print changes.

The consumer is `vahinitech/vahini-web`, pinned by commit, not necessarily a release tag. Push the companion analyser branch, then update the web gitlink and `input-manifest.yaml` together. The web manifest checker reads the committed tree, so verify the resulting commit. Do not claim native app changes without its source and validation. Deployment belongs to the consuming website's authorized workflow; do not start a standalone compose stack on a shared server as a shortcut.
