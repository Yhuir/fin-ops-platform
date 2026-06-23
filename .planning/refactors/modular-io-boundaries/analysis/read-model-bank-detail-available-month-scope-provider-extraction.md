# Bank Detail Available Month Scope Provider Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:bank-detail-available-month-scope-provider-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Scope

This slice removes the app-level available-month scope helper and replaces it with a services-layer provider.

Implemented:

- added `BankDetailAvailableMonthScopeProvider`;
- moved import transaction scanning and `YYYY-MM` scope extraction into the provider;
- changed App Status/stale smoke support to call `self._bank_detail_available_month_scope_provider().scope_keys()`;
- changed `BankDetailsApplicationService` wiring to inject the provider's `scope_keys`;
- changed derived lifecycle bank detail all-scope fan-out to use the provider;
- removed `Application._bank_detail_available_month_scope_keys(...)`;
- added guard coverage preventing the old app helper from returning.

Out of scope:

- extracting `Application._derived_lifecycle_bank_detail_executor(...)`;
- reducing the broad `Application._bank_details_application_service(...)` dependency factory;
- Go/Fiber/Go Worker;
- production state changes.

## Contract Preserved

- The provider tries `import_service.list_transactions(month="all")`.
- If the import service does not support `month`, it falls back to `list_transactions()`.
- It inspects `txn_date`, `trade_time`, `pay_receive_time`, `business_date` and `transaction_at`.
- It returns sorted unique `YYYY-MM` scopes.
- If no month is found or the loader fails, it returns `["all"]`.

API response shape, permissions, audit behavior, operation-barrier targets and read model freshness behavior are unchanged.

## Remaining Gaps

`bank_detail` remains `implementation-gap-open` because these local boundaries remain:

- `Application._derived_lifecycle_bank_detail_executor(...)`;
- `Application._bank_details_application_service(...)` retained collaborator injection.

Production PostgreSQL/worker/App Status/high-row evidence remains deferred.

## Tests

Added/updated:

- `tests/test_bank_detail_available_month_scope_provider.py`
  - covers known date-field month extraction, sorted unique scopes, month-loader fallback and `["all"]` fallback.
- `tests/test_platform_runtime_boundary_guards.py`
  - prevents the old app-level available-month helper from returning and requires explicit provider construction.
- Targeted read model refresh tests were run to preserve all-scope fan-out behavior.

## Verification

Commands run for this slice:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_detail_available_month_scope_provider -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime.BankDetailReadModelRefreshServiceTests.test_all_scope_fans_out_to_month_shards_without_sync_history_rebuild tests.test_bank_details_sql_runtime.BankDetailReadModelRefreshServiceTests.test_month_scope_rebuilds_and_completes_matching_source_version -v`

Additional verification before commit:

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Seven Test Categories

- Business core unit tests: not applicable; business classification rules did not change.
- Service-layer tests: covered by `tests/test_bank_detail_available_month_scope_provider.py`.
- API contract tests: not directly changed; API response shapes are untouched.
- Read model/cache/background job tests: covered by available-month provider tests and bank detail refresh all-scope fan-out tests.
- Frontend component and interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: not added; this is a narrow backend provider extraction with service/read-model regression coverage.
- Existing feature regression tests: covered by runtime boundary guard and bank detail refresh regression tests.

