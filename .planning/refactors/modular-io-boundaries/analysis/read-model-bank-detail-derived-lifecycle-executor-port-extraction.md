# Bank Detail Derived Lifecycle Executor Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:bank-detail-derived-lifecycle-executor-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Scope

This slice removes the bank detail derived lifecycle executor from `Application` and replaces it with an explicit services-layer executor.

Implemented:

- added `BankDetailDerivedLifecycleExecutor`;
- moved bank detail domain-plan scope parsing, month extraction, refresh metadata filtering, target scope selection and output payload construction into the executor;
- changed the derived lifecycle registry to use `self._bank_detail_derived_lifecycle_executor().execute`;
- kept `Application` responsible only for dependency registration and wiring;
- removed `Application._derived_lifecycle_bank_detail_executor(...)`;
- added guard coverage preventing the old app-level business executor from returning.

Out of scope:

- broad `Application._bank_details_application_service(...)` factory reduction;
- Go/Fiber/Go Worker;
- production state changes.

## Contract Preserved

- Explicit month scopes win over `all`.
- `all` expands through `BankDetailAvailableMonthScopeProvider`.
- No usable scope defaults to `["all"]`.
- Refresh enqueue goes through `BankDetailReadModelRefreshProducer`.
- Refresh metadata preserves the existing allowed keys.
- Return payload shape remains:
  - `deleted_counts.bank_detail_read_models`;
  - `invalidated_scopes`;
  - `enqueued_jobs` with `bank_detail.read_model.refresh` only when enqueue succeeds.

API response shape, permissions, audit behavior, operation-barrier targets and read model freshness behavior are unchanged.

## Remaining Gaps

`bank_detail` remains `implementation-gap-open` until a closure audit proves whether the remaining broad `Application._bank_details_application_service(...)` dependency factory is acceptable as wiring or needs another extraction slice.

Production PostgreSQL/worker/App Status/high-row evidence remains deferred.

## Tests

Added/updated:

- `tests/test_bank_detail_derived_lifecycle_executor.py`
  - covers explicit month priority, all-scope expansion, fallback `["all"]`, metadata filtering, enqueue result and payload shape.
- `tests/test_platform_runtime_boundary_guards.py`
  - prevents the old app-level derived lifecycle executor from returning and requires registry use of the explicit executor.

## Verification

Commands run for this slice:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_detail_derived_lifecycle_executor -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`

Additional verification before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Seven Test Categories

- Business core unit tests: not applicable; business classification rules did not change.
- Service-layer tests: covered by `tests/test_bank_detail_derived_lifecycle_executor.py`.
- API contract tests: not directly changed; API response shapes are untouched.
- Read model/cache/background job tests: covered by executor tests because the slice controls read model lifecycle fan-out and enqueue payloads.
- Frontend component and interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: not added; this is a narrow backend executor extraction with service/lifecycle regression coverage.
- Existing feature regression tests: covered by `tests.test_derived_data_lifecycle_service` and platform runtime boundary guard.

