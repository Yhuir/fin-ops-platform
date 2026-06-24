# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-account-balance-derived-lifecycle-executor-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-account-balance-derived-lifecycle-executor-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_account_balance` is the thirteenth non-Go read model pilot and remains `implementation-gap-open`.
- `BankAccountBalanceReadModelRepositoryPort` owns manifest-listed scope summary/list/save methods.
- `BankAccountBalanceReadModelRefreshProducer` owns gateway-backed all-only refresh enqueue.
- `BankAccountBalanceDerivedLifecycleExecutor` owns account-balance derived lifecycle response assembly.
- Remaining gaps include all-only worker/storage vs month/all scope policy accounting, missing dedicated operation barrier regression, and Bank Detail port compatibility fallback classification/removal.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:bank-account-balance-all-only-scope-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-derived-lifecycle-executor-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-producer-extraction.md`
   - `docs/modules/bank-account-balance/README.md`
   - `docs/modules/bank-account-balance/state-machine.md`
   - `docs/modules/bank-account-balance/tests.md`
   - `docs/modules/bank-account-balance/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh_producer.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
   - `tests/test_read_model_refresh_gateway.py`
   - `tests/test_bank_account_balance_read_model.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Tighten or explicitly guard `bank_account_balance` scope policy to all-only.
- `ReadModelRefreshGateway` must reject month/account scopes for `bank_account_balance` before durable enqueue.
- Keep `BankAccountBalanceReadModelRefreshProducer` normalizing to `["all"]`.
- Add tests proving gateway rejects non-all account-balance scopes while still accepting `all`.
- Update manifest/docs only if contract wording changes.
- Update analysis/state/docs after implementation.

Non-goals:

- Do not introduce month/account scoped projection.
- Do not change `bank_account_balance:all` as the only publish scope.
- Do not change balance calculation, API response shape, worker event type, queue schema, permissions, audit behavior, frontend behavior or storage table behavior.
- Do not implement Go/Fiber/Go Worker.

Expected verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_bank_account_balance_read_model tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_refresh_producer_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_derived_lifecycle_uses_explicit_executor_boundary -v`
- Add any new focused scope-policy tests to that command.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified all-only scope contract slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
