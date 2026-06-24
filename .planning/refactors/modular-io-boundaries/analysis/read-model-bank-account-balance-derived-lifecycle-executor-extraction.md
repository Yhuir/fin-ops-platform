# Read Model Bank Account Balance Derived Lifecycle Executor Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:bank-account-balance-derived-lifecycle-executor-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `bank_account_balance` derived lifecycle response assembly out of `Application` into an explicit executor while preserving all existing payload semantics.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-producer-extraction.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/modules/bank-account-balance/state-machine.md`
- `docs/modules/bank-account-balance/tests.md`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh_producer.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/services/bank_detail_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_bank_account_balance_derived_lifecycle_executor.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Changes

- Added `BankAccountBalanceDerivedLifecycleExecutor`.
- The executor receives an explicit `enqueue_refresh` dependency.
- `Application` now assembles the executor and maps `bank_account_balance_read_model` derived lifecycle execution to `.execute`.
- Removed app-owned `_derived_lifecycle_bank_account_balance_executor(...)`.
- Added executor unit tests and a static guard proving the app helper cannot return.

## Preserved Behavior

- `deleted_counts` remains `{"bank_account_balance_read_models": 0}`.
- `invalidated_scopes` remains `["all"]`.
- `enqueued_jobs` remains `["bank_account_balance.read_model.refresh"]` only when enqueue succeeds.
- `bank_account_balance:all` remains the only publish scope.
- No API, worker event, queue schema, permission, audit, frontend or balance calculation behavior changed.

## Remaining Local Gaps

- Scope policy still accepts month/all while producer and worker enforce all-only behavior.
- Dedicated `bank_account_balance:all` operation barrier regression is still missing.
- `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` remains a transition compatibility fallback.
- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No balance or account classification rules changed. |
| 2. Service-layer tests | Applies | Added executor unit tests for enqueue success/failure payloads. |
| 3. API contract tests | Existing coverage applies | No route or response shape changed. |
| 4. Read model/cache/background job tests | Applies | Existing producer/runtime/backfill tests continue to cover enqueue behavior. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Environment evidence deferred | Bank import -> durable refresh -> account balance fresh still requires real PostgreSQL/worker evidence. |
| 7. Existing feature regression tests | Applies | Static guard prevents app-owned derived lifecycle helper from returning. |

## State Machine Impact

- `read-models:bank-account-balance-derived-lifecycle-executor-extraction` transitions to `implementation-closed`.
- `bank_account_balance` remains `implementation-gap-open`.
- Insert next boundary `read-models:bank-account-balance-all-only-scope-contract`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_derived_lifecycle_executor tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_derived_lifecycle_uses_explicit_executor_boundary tests.test_bank_account_balance_read_model tests.test_runtime_worker_read_model_refresh_scopes tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
