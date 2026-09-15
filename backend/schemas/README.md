# Version-2 API contract as JSON Schema (draft-07)

These files describe what the analyser sends and accepts on `/api/v2/*`.
They are generated from the same constants the server uses
(`report_contract.FACTOR_IDS`, `entitlements.FREE_FACTORS`) and checked in
CI by `backend/tests/test_schemas.py`, so a change to the server that alters
a response shape fails the build until the schema is updated too.

| File | Message |
| --- | --- |
| `common.schema.json` | Shared definitions: factor numbers and IDs, tiers, statuses, bands, `access`, coaching cards, evidence regions |
| `me.schema.json` | `GET /api/v2/me` |
| `report-request.schema.json` | `POST /api/v2/reports` request, modelled as an object (`headers`, `query`, `form`, `image` metadata) |
| `report-expanded.schema.json` | `POST /api/v2/reports` default response, schema 2.0 |
| `report-compact.schema.json` | `POST /api/v2/reports?format=compact` response, schema 2.1 |
| `catalog.schema.json` | `GET /api/v2/catalog/{version}` |
| `error.schema.json` | HTTP 401, 403, 404, 413, 422 and 503 bodies |
| `health.schema.json` | `GET /health` |

## What the schemas enforce

- A Free body never contains Pro material: only factors 1, 5, 7, 8 and 18,
  fifteen locked entries, no `practice`, `inputs`, `coaching`, `evidence` or
  `worksheets`. A Pro body has no locked factors.
- A missing score is `null` with status `unavailable` (`u`); it can never
  be `0`. Factors 2, 13, 14 and 16 are never `estimated` from a still image.
- `number` and `id` always name the same factor; `catalog_version` is 20
  hex characters; `ok:false` requires an `error` block and `ok:true`
  forbids one.
- The compact `text`, `counts` and `recognition` blocks come together.
- The request model rejects unknown `include` values and any credential
  outside the `Authorization` header.

## Using them

```bash
# From the repository (needs jsonschema, in requirements-core.txt)
python backend/contract_schemas.py report-compact response.json
curl -s https://stage.vahinitech.com/api/v2/me | python backend/contract_schemas.py me -
```

```python
import contract_schemas
contract_schemas.validate("report-compact", body)   # raises ValueError with paths
```

Client repositories (Android, web) can vendor this directory and validate
recorded fixtures in their own tests with any draft-07 validator. Resolve
`$ref` links to `common.schema.json` offline: every file carries an `$id`
under `https://vahinitech.com/schemas/analyser/v2/`, and the files are not
served from that URL. Validation checks shape and access invariants only;
the server decides access.

## Updating

Change the server, then edit the schema file by hand or regenerate it and
run `python -m unittest backend.tests.test_schemas`. When a response gains a
field, add it as optional first so older clients keep validating. A change to
`schema_version` is a new contract and needs a new file, not an edit.
