# Bank Detail Suggestion Provider Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:bank-detail-suggestion-provider-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Scope

This slice removes the latest auto-category suggestion callback from `Application` and replaces it with an explicit provider owned by the services layer.

In scope:

- add `BankDetailAutoCategorySuggestionProvider`;
- expose `BankDetailsService.auto_category_input_row(...)` as the public row-shaping method for suggestion input;
- keep `BankDetailsApplicationService` suggestion behavior unchanged;
- change `Application._bank_details_application_service(...)` to inject the explicit provider instead of an app-level callback;
- update tests to use `_bank_detail_auto_category_suggestion_provider` as the injection seam;
- guard that `Application._latest_bank_detail_auto_category_suggestion(...)` cannot return.

Out of scope:

- refresh/wakeup wrapper extraction;
- available-month scope helper extraction;
- derived lifecycle executor extraction;
- Go/Fiber/Go Worker work;
- production state changes.

## Contract Preserved

The provider preserves the old suggestion semantics:

1. normalize `transaction_id`;
2. load the transaction through the import service;
3. serialize/shape the transaction row;
4. force the normalized transaction id into the row;
5. build the auto-category input row through `BankDetailsService.auto_category_input_row(...)`;
6. call `BankTransactionAutoCategoryService.suggest_for_rows(...)`;
7. return the suggestion for the normalized transaction id.

API response shape, permissions, audit action names, category matching rules, read model freshness behavior and frontend behavior are unchanged.

## Remaining Gaps

`bank_detail` is still not module-closed. Remaining local implementation boundaries:

- `Application._enqueue_bank_detail_read_model_refreshes(...)`;
- `Application._delete_bank_detail_redis_cache(...)`;
- `Application._bank_detail_available_month_scope_keys(...)`;
- `Application._derived_lifecycle_bank_detail_executor(...)`;
- `Application._bank_details_application_service(...)` still injects several retained collaborators.

Production PostgreSQL/worker/App Status/high-row evidence also remains deferred.

## Tests

Added/updated:

- `tests/test_bank_detail_auto_category_suggestion_provider.py`
  - proves normalized transaction id, service-owned input row shaping and `suggest_for_rows(...)` behavior.
- `tests/test_bank_auto_tag_rules_api.py`
  - updates category confirmation/manual assignment tests to inject the new provider seam.
- `tests/test_platform_runtime_boundary_guards.py`
  - prevents the removed app-level callback from returning and requires the explicit provider wiring.

## Verification

Commands run for this slice:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_detail_auto_category_suggestion_provider -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_confirmation_endpoint_rejects_single_auto_match_candidate tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_confirmation_endpoint_uses_only_current_needs_confirmation_candidates tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_confirmation_endpoint_allows_external_turnover_third_label_candidate tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_manual_assignment_endpoint_allows_unmatched_row_to_choose_active_tag -v`

Additional verification before commit:

- full targeted bank auto-tag API category suite;
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`;
- `bash scripts/verify.sh docs`;
- `git diff --check`.

## Seven Test Categories

- Business core unit tests: covered by provider test because suggestion input shaping and category suggestion dispatch are business classification prerequisites.
- Service-layer tests: covered by provider test and service boundary guard.
- API contract tests: covered by updated bank auto-tag/category API tests.
- Read model/cache/background job tests: not directly changed; freshness semantics and refresh enqueue behavior were not modified.
- Frontend component and interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: not added; this is a narrow backend provider extraction and existing API flow tests cover the affected path.
- Existing feature regression tests: covered by category confirmation/manual assignment API regressions and platform boundary guard.

