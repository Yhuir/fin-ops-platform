# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-account-balance-operation-barrier-regression` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-account-balance-operation-barrier-regression`
- Last status: `regression-guard-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_account_balance` is the thirteenth non-Go read model pilot and remains `implementation-gap-open`.
- `BankAccountBalanceReadModelRepositoryPort` owns manifest-listed scope summary/list/save methods.
- `BankAccountBalanceReadModelRefreshProducer` owns gateway-backed all-only refresh enqueue.
- `BankAccountBalanceDerivedLifecycleExecutor` owns account-balance derived lifecycle response assembly.
- `ReadModelRefreshGateway` rejects non-`all` `bank_account_balance` scopes before durable enqueue.
- Dedicated operation barrier regressions cover `bank_account_balance:all` dirty/readiness and outbox pending behavior.
- Remaining gap: `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` compatibility fallback classification/removal.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:bank-account-balance-bank-detail-fallback-quarantine`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-operation-barrier-regression.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-repository-port-extraction.md`
   - `docs/modules/bank-account-balance/README.md`
   - `docs/modules/bank-account-balance/state-machine.md`
   - `docs/modules/bank-account-balance/tests.md`
   - `docs/modules/bank-account-balance/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/bank_details_application_service.py`
   - `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
   - `tests/test_bank_details_sql_runtime.py`
   - `tests/test_bank_account_balance_read_model.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Classify `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` as removable or compat-only.
- Prefer removal if current app/service/test wiring proves explicit `BankAccountBalanceReadModelRepositoryPort` is always available for normal Bank Details accounts reads.
- If it must stay, document owner/caller/deletion condition and add a guard that it cannot become the normal account-balance owner.
- Do not alter balance calculation, account identity, API shape, worker event, queue schema, permissions, audit or frontend behavior.
- Update analysis/state/docs after implementation.

Non-goals:

- Do not introduce month/account scoped projection.
- Do not change `bank_account_balance:all` as the only publish scope.
- Do not implement Go/Fiber/Go Worker.
- Do not perform production writes or require PGSQL_URL/staging DB.

Expected verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_platform_runtime_boundary_guards -v`
- Narrow the platform guard command if unrelated pre-existing guards fail; record any unrelated failures.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified fallback quarantine/removal slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
