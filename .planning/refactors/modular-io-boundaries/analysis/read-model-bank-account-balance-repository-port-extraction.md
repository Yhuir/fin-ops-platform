# Read Model Bank Account Balance Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:bank-account-balance-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Add a narrow repository port for `bank_account_balance` and route the projection save path plus Bank Details accounts SQL read path through the explicit account-balance boundary.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-search.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-and-bank-account-balance-contract.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/modules/bank-account-balance/state-machine.md`
- `docs/modules/bank-account-balance/tests.md`
- `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_bank_account_balance_read_model.py`
- `tests/test_bank_details_sql_runtime.py`
- `tests/test_read_model_manifest.py`
- CodeGraph impact for `BankDetailReadModelRepositoryPort`.

## Changes

- Added `BankAccountBalanceReadModelRepositoryPort` with only manifest-listed methods:
  - `bank_account_balance_scope_summary(...)`
  - `list_bank_account_balances(...)`
  - `save_bank_account_balances(...)`
- `BankAccountBalanceProjectionBuilder` now wraps its repository dependency with the account-balance port before saving projection rows.
- `PostgresStateStore` now exposes `bank_account_balance_sql_read_repository`.
- `Application._initialize_runtime_services(...)` stores `_bank_account_balance_sql_read_repository`.
- `Application._bank_details_application_service(...)` passes the account-balance repository explicitly.
- `BankDetailsApplicationService.accounts_payload(...)` now prefers the explicit account-balance repository; the old Bank Detail read port method remains only as a compatibility fallback when no explicit account-balance port is injected.
- `READ_MODEL_MANIFEST["bank_account_balance"].repository_owner` now names `BankAccountBalanceReadModelRepositoryPort`.

## Preserved Behavior

- Balance calculation, account identity, latest balance selection, currency normalization and SQL table owner behavior are unchanged.
- `/api/bank-details/accounts` response shape and fresh/refreshing handling are unchanged.
- `bank_account_balance.read_model.refresh`, `bank_account_balance:all`, queue schema, permissions, audit behavior, frontend behavior and backfill CLI behavior are unchanged.
- No month/account shard semantics were introduced.

## Remaining Local Gaps

- `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` remains as a transition compatibility method. It is no longer the normal `Application` injection path, but a later audit should decide whether it can be removed or must stay compat-only with stronger static guards.
- `Application._enqueue_bank_account_balance_read_model_refresh(...)` and `_derived_lifecycle_bank_account_balance_executor(...)` remain app-owned helpers.
- Scope policy still accepts month/all while the worker/storage contract is all-only.
- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Existing coverage applies | No balance/account identity rules changed; existing projection tests were rerun. |
| 2. Service-layer tests | Applies | Added account-balance port guard and service test proving accounts query uses the explicit account-balance repository port. |
| 3. API contract tests | Existing coverage applies | Bank Details SQL runtime tests preserve accounts response behavior; no route/API shape changed. |
| 4. Read model/cache/background job tests | Applies | Projection save path and manifest owner coverage were rerun; worker/backfill tests are part of full verification. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this narrow slice | Bank import -> account balance drain remains deferred environment evidence. |
| 7. Existing feature regression tests | Applies | Bank details SQL runtime, account balance read model, manifest and runtime worker tests are the regression net. |

## State Machine Impact

- `read-models:bank-account-balance-repository-port-extraction` transitions to `implementation-closed`.
- `bank_account_balance` remains `implementation-gap-open`.
- Insert next boundary: `read-models:bank-account-balance-refresh-freshness-operation-barrier-audit`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
