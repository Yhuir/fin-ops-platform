# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-account-balance-refresh-producer-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-account-balance-refresh-producer-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_account_balance` is the thirteenth non-Go read model pilot and remains `implementation-gap-open`.
- `BankAccountBalanceReadModelRepositoryPort` owns manifest-listed scope summary/list/save methods.
- `BankAccountBalanceReadModelRefreshProducer` owns gateway-backed all-only refresh enqueue.
- Application import-state paths, Bank Details service injection, runtime import-state fan-out, runtime derived lifecycle fan-out and backfill enqueue now use the account-balance producer.
- Remaining gaps include app-owned derived lifecycle response assembly, all-only worker/storage vs month/all scope policy accounting, missing dedicated operation barrier regression, and Bank Detail port compatibility fallback classification/removal.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:bank-account-balance-derived-lifecycle-executor-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-producer-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-freshness-operation-barrier-audit.md`
   - `docs/modules/bank-account-balance/README.md`
   - `docs/modules/bank-account-balance/state-machine.md`
   - `docs/modules/bank-account-balance/tests.md`
   - `docs/modules/bank-account-balance/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh_producer.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
   - `tests/test_bank_account_balance_read_model.py`
   - `tests/test_runtime_worker_read_model_refresh_scopes.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Add a dedicated `BankAccountBalanceDerivedLifecycleExecutor`.
- Move `_derived_lifecycle_bank_account_balance_executor(...)` response assembly out of `Application`.
- Use `BankAccountBalanceReadModelRefreshProducer` as the explicit enqueue dependency.
- Preserve current payload shape:
  - `deleted_counts={"bank_account_balance_read_models": 0}`
  - `invalidated_scopes=["all"]`
  - `enqueued_jobs=["bank_account_balance.read_model.refresh"]` only when enqueue succeeds.
- Guard that the removed app-owned helper cannot return.
- Update analysis/state/docs after implementation.

Non-goals:

- Do not change balance calculation, account identity, API response shape, worker event type, queue schema, permissions, audit behavior, frontend behavior or storage table behavior.
- Do not introduce month/account scoped projection.
- Do not change `bank_account_balance:all` as the only publish scope.
- Do not implement Go/Fiber/Go Worker.

Expected verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_runtime_worker_read_model_refresh_scopes tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_refresh_producer_helpers_stay_out_of_application tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli -v`
- Add any new focused executor/static tests to that command.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified derived lifecycle executor extraction slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
