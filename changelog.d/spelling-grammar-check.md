- A spelling and grammar check on English handwriting (#317), sent in the
  report's new `language` section and not shown on the report yet. Spelling
  uses the SCOWL word list and checks each unlisted word against the
  reader's own letter scores, so a misread is never reported as the child's
  spelling; it reads at most six rows again, so a scan stays fast. Grammar
  is a set of fixed rules for children's common slips, run only on
  sentences the check trusts. Measured on 223 pages: no correctly spelt
  word was reported, and few misspellings were found
  (`docs/history/spelling-grammar-2026-10-24.md`). No score changed.
- With a copied or dictated sentence (`expected_text`), each word read
  differently from the sentence is checked against the sentence's own word
  on the ink. On planted pages this found 9 to 16% of the misspellings
  where free writing found under 1%, and flagged nothing on pages copied
  correctly.
