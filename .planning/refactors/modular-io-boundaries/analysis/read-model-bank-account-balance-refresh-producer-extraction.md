# Read Model Bank Account Balance Refresh Producer Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:bank-account-balance-refresh-producer-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `bank_account_balance` non-transactional refresh enqueue ownership out of app/runtime generic helpers and into an explicit account-balance producer boundary.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-repository-port-extraction.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/modules/bank-account-balance/state-machine.md`
- `docs/modules/bank-account-balance/tests.md`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh_producer.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- `backend/src/fin_ops_platform/app/bank_account_balance_backfill.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_bank_account_balance_read_model.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for `BankAccountBalanceReadModelRefreshService` and producer patterns.

## Changes

- Added `BankAccountBalanceReadModelRefreshProducer`.
- The producer is the module-specific enqueue boundary for `bank_account_balance`.
- The producer always normalizes target scopes to `["all"]`, preserving the current worker/storage all-only contract.
- `Application._bank_details_application_service(...)` injects `BankAccountBalanceReadModelRefreshProducer.enqueue_all` for API miss/stale/migration-missing refresh.
- Import-state account-balance refresh paths in `Application` now use the producer.
- `_derived_lifecycle_bank_account_balance_executor(...)` now uses the producer for enqueue while still owning derived lifecycle response assembly.
- Removed `Application._enqueue_bank_account_balance_read_model_refresh(...)`.
- Runtime import-state and runtime derived lifecycle bank-account-balance refresh now use the producer instead of generic `_enqueue_scopes("bank_account_balance", ...)`.
- Backfill CLI enqueue now uses the producer instead of direct `ReadModelRefreshGateway.enqueue_one(...)`.

## Preserved Behavior

- `bank_account_balance.read_model.refresh` event type is unchanged.
- `bank_account_balance:all` remains the only publish scope.
- Balance calculation, account identity, latest balance selection, currency normalization, API shape, permissions, audit behavior, Redis/cache behavior, queue schema and frontend behavior are unchanged.
- No month/account projection scope was introduced.

## Remaining Local Gaps

- `_derived_lifecycle_bank_account_balance_executor(...)` still lives in `Application`; it now uses the producer, but ownership and response assembly should move to a dedicated executor.
- Scope policy still accepts month/all while the producer and worker enforce all-only behavior.
- Dedicated `bank_account_balance:all` operation barrier regression is still missing.
- `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` remains a transition compatibility fallback.
- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No balance/account identity/currency/sorting/filtering rules changed. |
| 2. Service-layer tests | Applies | Added producer tests proving gateway-backed all-only enqueue and unavailable gateway behavior. |
| 3. API contract tests | Existing coverage applies | Bank Details SQL runtime tests preserve accounts response behavior; no route/API shape changed. |
| 4. Read model/cache/background job tests | Applies | Runtime worker import-state and derived lifecycle tests prove producer boundary usage; backfill CLI tests were rerun. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Environment evidence deferred | Bank import -> durable refresh -> account balance fresh still requires real PostgreSQL/worker evidence. |
| 7. Existing feature regression tests | Applies | Bank Details SQL runtime, account balance read model, runtime worker and static boundary guard tests cover regressions. |

## State Machine Impact

- `read-models:bank-account-balance-refresh-producer-extraction` transitions to `implementation-closed`.
- `bank_account_balance` remains `implementation-gap-open`.
- Insert next boundary `read-models:bank-account-balance-derived-lifecycle-executor-extraction`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_runtime_worker_read_model_refresh_scopes tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_refresh_producer_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_read_model_refresh_producers_use_scope_gateway_boundary tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli -v
```

Known unrelated failure from broader guard suite:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v
```

This broader command currently fails on pre-existing guard issues unrelated to `bank_account_balance`:

- `repair_submitted_etc_invoice_overlaps.py` direct invoice update guard.
- OA attachment invoice create permission guard.
- `_no_oa_bank_batch_source_versions` relation source-version provider guard.
