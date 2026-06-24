# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-account-balance-all-only-scope-contract` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-account-balance-all-only-scope-contract`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_account_balance` is the thirteenth non-Go read model pilot and remains `implementation-gap-open`.
- `BankAccountBalanceReadModelRepositoryPort` owns manifest-listed scope summary/list/save methods.
- `BankAccountBalanceReadModelRefreshProducer` owns gateway-backed all-only refresh enqueue.
- `BankAccountBalanceDerivedLifecycleExecutor` owns account-balance derived lifecycle response assembly.
- `ReadModelRefreshGateway` now rejects non-`all` `bank_account_balance` scopes before durable enqueue.
- Remaining gaps include missing dedicated operation barrier regression and Bank Detail port compatibility fallback classification/removal.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:bank-account-balance-operation-barrier-regression`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-all-only-scope-contract.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-freshness-operation-barrier-audit.md`
   - `docs/modules/bank-account-balance/README.md`
   - `docs/modules/bank-account-balance/state-machine.md`
   - `docs/modules/bank-account-balance/tests.md`
   - `docs/modules/bank-account-balance/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
   - `backend/src/fin_ops_platform/services/bank_details_application_service.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
   - `tests/test_operation_freshness_barrier.py`
   - `tests/test_bank_details_sql_runtime.py`
   - `tests/test_bank_account_balance_read_model.py`

## Boundary Scope

Target:

- Add a dedicated regression proving `bank_account_balance:all` operation barrier behavior.
- Pending dirty/outbox state for `bank_account_balance:all` must keep the relevant Bank Details accounts freshness target refreshing/not-yet-synced.
- Fresh or completed account-balance state must not be blocked by unrelated read model scopes.
- Preserve current API payload shape; add tests at the service/barrier layer unless code inspection proves an API contract test is required.
- Update analysis/state/docs after implementation.

Non-goals:

- Do not introduce month/account scoped projection.
- Do not change `bank_account_balance:all` as the only publish scope.
- Do not change balance calculation, API response shape, worker event type, queue schema, permissions, audit behavior, frontend behavior or storage table behavior.
- Do not implement Go/Fiber/Go Worker.

Expected verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_read_model_refresh_gateway -v`
- Add any new focused barrier tests to that command.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified operation barrier regression slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
