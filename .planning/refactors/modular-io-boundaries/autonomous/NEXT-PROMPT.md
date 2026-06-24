# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-account-balance-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-account-balance-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_account_balance` is the thirteenth non-Go read model pilot and remains `implementation-gap-open`.
- `BankAccountBalanceReadModelRepositoryPort` now owns manifest-listed scope summary/list/save methods.
- `BankAccountBalanceProjectionBuilder` saves through the account-balance port.
- `PostgresStateStore.bank_account_balance_sql_read_repository` exposes the account-balance port.
- `Application` injects the account-balance port into `BankDetailsApplicationService`.
- Bank Details accounts SQL read path now prefers the explicit account-balance port.
- `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` remains a transition compatibility fallback only.
- Remaining gaps include app-owned refresh enqueue/derived lifecycle helpers, all-only worker/storage vs month/all scope policy accounting, operation barrier evidence and compatibility fallback classification/removal.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:bank-account-balance-refresh-freshness-operation-barrier-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-repository-port-extraction.md`
   - `docs/modules/bank-account-balance/README.md`
   - `docs/modules/bank-account-balance/state-machine.md`
   - `docs/modules/bank-account-balance/tests.md`
   - `docs/modules/bank-account-balance/implementation-notes.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/imports-bank-transactions/README.md`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
   - `backend/src/fin_ops_platform/services/bank_details_application_service.py`
   - `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_bank_account_balance_read_model.py`
   - `tests/test_bank_details_sql_runtime.py`
   - `tests/test_bankdetail_backfill_cli.py`
   - `tests/test_operation_freshness_barrier.py`
   - `tests/test_read_model_refresh_gateway.py`

## Boundary Scope

Target:

- Audit `bank_account_balance` refresh enqueue paths, derived lifecycle executor, force refresh behavior, operation barrier behavior and remaining Bank Detail port compatibility fallback.
- Decide whether the next concrete implementation slice should extract a `BankAccountBalanceReadModelRefreshProducer`, extract a derived lifecycle executor, tighten/classify the all-only scope contract, remove the Bank Detail port fallback, or another narrower gap.
- Do not implement until the audit proves the first concrete gap.
- Do not introduce month/account scoped projection without an explicit scope contract design.
- Do not implement Go/Fiber/Go Worker.

Expected verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified freshness/operation-barrier audit or split the first proven implementation gap, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
