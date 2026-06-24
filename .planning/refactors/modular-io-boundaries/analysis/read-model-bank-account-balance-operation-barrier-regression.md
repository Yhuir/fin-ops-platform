# Read Model Bank Account Balance Operation Barrier Regression

**Date:** 2026-06-24
**Boundary:** `read-models:bank-account-balance-operation-barrier-regression`
**Slice status:** `regression-guard-closed`
**Module closure:** `implementation-gap-open`

## Goal

Add dedicated regression coverage proving Bank Details accounts cannot be treated as synchronized while the `bank_account_balance:all` read model target is still refreshing or pending.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-all-only-scope-contract.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-freshness-operation-barrier-audit.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/modules/bank-account-balance/state-machine.md`
- `docs/modules/bank-account-balance/tests.md`
- `docs/modules/bank-account-balance/implementation-notes.md`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
- `tests/test_operation_freshness_barrier.py`
- `tests/test_bank_account_balance_read_model.py`

## Changes

- Added `test_bank_account_balance_all_dirty_scope_keeps_accounts_target_refreshing`.
- Added `test_bank_account_balance_all_outbox_pending_keeps_accounts_target_refreshing`.
- Added `test_other_read_model_outbox_pending_does_not_block_bank_account_balance_all_target`.
- No production service code changed; existing `OperationFreshnessBarrierService` already matched the required contract.

## Preserved Behavior

- `bank_account_balance:all` remains the only operation barrier scope for account-balance refresh.
- No API, worker event, queue schema, storage, permission, audit, frontend or balance calculation behavior changed.
- Other read model operation barrier behavior is unchanged.

## Remaining Local Gaps

- `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` remains a transition compatibility fallback and must be classified, removed, or quarantined.
- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No balance/account business rule changed. |
| 2. Service-layer tests | Applies | Added service-level operation barrier regressions. |
| 3. API contract tests | Existing coverage applies | No route or response shape changed. |
| 4. Read model/cache/background job tests | Applies | Tests cover dirty/readiness and outbox pending barrier behavior for `bank_account_balance:all`. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Environment evidence deferred | Real bank import -> worker drain -> accounts fresh requires PostgreSQL/worker evidence. |
| 7. Existing feature regression tests | Applies | Tests prove unrelated read model outbox state does not block account-balance targets. |

## State Machine Impact

- `read-models:bank-account-balance-operation-barrier-regression` transitions to `regression-guard-closed`.
- `bank_account_balance` remains `implementation-gap-open`.
- Insert next boundary `read-models:bank-account-balance-bank-detail-fallback-quarantine`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier -v
PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_read_model_refresh_gateway -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
