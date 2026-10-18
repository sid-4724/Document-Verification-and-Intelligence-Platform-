# Learning exercises

Try these on a branch after running `.venv/bin/python scripts/verify.py`. The implementation was developed with AI assistance; these exercises help you understand and change it yourself.

## Exercises

1. **Add a unit alias.** Inspect `backend/app/services/verification.py:unit` and `backend/tests/test_verification.py:test_unit_aliases`. Add `kilogram` as an alias for `kg`. Verify that it compares quantities correctly and that `kg` versus `pcs` still requires review. Run `.venv/bin/python -m pytest backend/tests/test_verification.py -q`.
2. **Support one header spelling.** Inspect `extraction.py:FIELD_PATTERNS` and `test_extraction.py`. Support `Invoice #:` as a document-number label. Add a direct `parse_pages` regression and retain the existing unknown/conflicting-field tests. Run `.venv/bin/python -m pytest backend/tests/test_extraction.py -q`.
3. **Test another ambiguous match.** Inspect `matching.py:match_candidates` and `test_history_matching_scope.py`. Create one reference row and two targets with the same nonempty SKU but distinct descriptions. Assert that duplicate identifiers produce review, without confirmed quantity differences. Run `.venv/bin/python -m pytest backend/tests/test_history_matching_scope.py -q`.
4. **Measure a retrieval threshold change on validation only.** Inspect `scripts/evaluate_runtime.py:score` and `evaluation/runtime_dataset.json`. In a temporary Python session, compare thresholds 0.035 and 0.1 on cases with `split == "validation"`. Explain recall and unsupported-evidence hits before choosing a configuration. Do not tune to the test results. Run `PYTHONPATH=backend .venv/bin/python scripts/evaluate_runtime.py` to reproduce the fixed benchmark separately.
5. **Add a finding-type filter.** Inspect `frontend/components/findings-panel.tsx`. Add an accessible `Filter finding type` select built from actual finding kinds. Combine it with severity/review filters. Extend a Playwright test to select quantity_difference and assert that the price finding is absent while the quantity finding is visible. Run `npm --prefix frontend run typecheck`, then `cd frontend && npm run test:e2e` with the app running.

## Solutions and checks

1. Add `"kilogram": "kg"` to the alias dictionary and `("kg", "kilogram")` to parametrized compatible-unit cases. Keep the incompatible-unit assertion. The change adds a name alias, not a numeric conversion.
2. Extend only the document-number pattern with the explicit alternate label, for example `Invoice\s*#` before its colon separator. Test `"INVOICE\nInvoice #: INV-44"` returns INV-44 with page-one provenance. Do not broaden the regex to guess arbitrary unlabeled numbers.
3. Give both target rows the reference SKU. Their candidate list has length two even when one description is exact. Assert `ambiguous_match` and absence of `quantity_difference`; row IDs should remain distinct. This tests the business outcome rather than an internal dictionary shape.
4. Import `build_dataset` and `score`, filter the validation cases, and report both dictionaries. A larger threshold may reduce irrelevant hits while dropping supported passages. Commit a reasoned configuration only after validation; report a final untouched test once and do not keep tuning against it. Current test outcomes are documented observations, not a development target to optimize repeatedly.
5. Use `useState("all")`, derive unique kinds from `findings`, add `(type === "all" || finding.kind === type)` to the existing predicate, and label the select. Use `pretty(kind)` only for the label; store the stable kind string. A test should inspect visible finding cards rather than merely checking that the select changed value.
