# P006 Implementation Report

## Result

Final validation drift closed.

- `AppSettingsService.update_bank_flow_rule_batch_tag_rules(...)` now rejects legacy `selected_tag_codes` / `selectedTagCodes` at service boundary.
- Duplicate `rules[].tag_code` now fails fast with `duplicate_bank_flow_rule_batch_tag_rule` before normalization can overwrite earlier rules.
- no-OA legacy `selected_tag_codes` behavior is unchanged and remains owned by `no-oa-bank-batches`.
- Long-term module docs now describe the current modular closure state and validation coverage.

## Tests Added Or Changed

- `tests/test_app_settings_service.py::AppSettingsServiceTests::test_bank_flow_rule_batch_tag_rules_reject_legacy_selection_and_duplicate_rules`
- `tests/test_bank_flow_rule_batch_routes.py::BankFlowRuleBatchRoutesTests::test_tag_rules_reject_legacy_selection_and_duplicate_rules`
- Existing app settings replacement test now writes bank-flow rules through `rules`, not legacy `selected_tag_codes`.

## Verification

Run after implementation:

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_app_settings_service.py tests/test_bank_flow_rule_batch_routes.py -q` -> 41 passed.
- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_app_settings_service.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_state_store.py -q` -> 194 passed, 15 subtests passed.
- `npm --prefix web test -- --run BankFlowRuleBatchPage.test.tsx BankFlowRuleBatchApi.test.ts BankFlowRuleBatchPolicy.test.ts CandidateGroupGrid.test.tsx` -> 80 passed.
- `npm --prefix web run build` -> passed with existing CSS minifier/chunk-size warnings.
- `npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium` -> 9 passed.
- `npm --prefix web run e2e -- e2e/permissions-role-matrix.spec.ts --project=chromium` -> 6 passed, 1 failed on unrelated ETC ticket read-export warning text assertion.
- `git diff --check` on touched module scope -> passed.
