# Read Model Bank Account Balance Bank Detail Fallback Quarantine

**Date:** 2026-06-24
**Boundary:** `read-models:bank-account-balance-bank-detail-fallback-quarantine`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove the transition fallback where Bank Details accounts could read account-balance payloads through `BankDetailReadModelRepositoryPort`.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-operation-barrier-regression.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-repository-port-extraction.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/modules/bank-account-balance/state-machine.md`
- `docs/modules/bank-account-balance/tests.md`
- `docs/modules/bank-account-balance/implementation-notes.md`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_bank_details_sql_runtime.py`
- `tests/test_bank_account_balance_read_model.py`
- `tests/test_runtime_bootstrap.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Changes

- `BankDetailsApplicationService._accounts_from_sql_read_model(...)` now uses only `bank_account_balance_read_model_repository` for account-balance reads.
- `BankDetailReadModelRepositoryPort` no longer exposes `list_bank_account_balances(...)`.
- Runtime bootstrap missing-table regression now injects the missing table repository through the account-balance repository slot.
- Added a platform boundary guard preventing the Bank Detail port account-balance fallback from returning.
- Hardened Bank Details route dependency assembly for object-constructed runtime bootstrap tests: optional auto-category suggestion and available-month providers no longer require `_import_service` when those paths are not used.

## Preserved Behavior

- Bank Details accounts still returns refreshing and enqueues `bank_account_balance:all` when the account-balance repository is unavailable or missing.
- Normal account-balance reads still use `BankAccountBalanceReadModelRepositoryPort`.
- No balance calculation, account identity, API shape, worker event, queue schema, permissions, audit or frontend behavior changed.

## Remaining Local Gaps

- Run a local closure audit to confirm no further `bank_account_balance` implementation gaps remain.
- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No balance/account rule changed. |
| 2. Service-layer tests | Applies | Bank Details service and repository port tests prove explicit account-balance port ownership. |
| 3. API contract tests | Applies | Runtime bootstrap API tests prove production accounts reads do not fallback to legacy service and handle missing account-balance table as refreshing. |
| 4. Read model/cache/background job tests | Applies | Tests cover account-balance repository miss/migration handling and durable refresh enqueue reason. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Environment evidence deferred | Real PostgreSQL/worker/browser evidence remains unavailable locally. |
| 7. Existing feature regression tests | Applies | Static guard prevents Bank Detail port from regaining account-balance read access. |

## State Machine Impact

- `read-models:bank-account-balance-bank-detail-fallback-quarantine` transitions to `implementation-closed`.
- `bank_account_balance` remains `implementation-gap-open` pending local closure audit.
- Insert next boundary `read-models:bank-account-balance-local-implementation-closure-audit`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_accounts_path_does_not_fallback_to_bank_detail_port tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_runtime_bootstrap -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_accounts_path_does_not_fallback_to_bank_detail_port tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_runtime_bootstrap tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
