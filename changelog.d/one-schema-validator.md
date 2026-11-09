- One JSON Schema draft and one validator. Every schema in the analyser is
  draft-07 now: the four language-pack, stage, ladder and profile schemas
  moved from 2020-12 (`$defs` is `definitions`), and the five places that
  built their own validator go through `backend/report/json_schema.py`,
  which refuses a schema that declares any other draft. Draft-07 skips any
  rule written beside a `$ref`, so the four such rules in
  `profile.schema.json` (three `minItems`, one `propertyNames`) sit in an
  `allOf` with their `$ref`; a test fails on a rule beside a `$ref` in any
  schema. The API contracts do not change apart from one description that
  named `$defs`.
