# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-account-balance-refresh-freshness-operation-barrier-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-account-balance-refresh-freshness-operation-barrier-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_account_balance` is the thirteenth non-Go read model pilot and remains `implementation-gap-open`.
- `BankAccountBalanceReadModelRepositoryPort` owns manifest-listed scope summary/list/save methods.
- Projection save and Bank Details accounts SQL read paths use the explicit account-balance port.
- The audit found the next concrete implementation gap: account-balance refresh enqueue is still owned by `Application._enqueue_bank_account_balance_read_model_refresh(...)`.
- Additional gaps remain after producer extraction: app-owned derived lifecycle executor, runtime import-state generic fan-out, all-only worker/storage vs month/all scope policy, missing dedicated operation barrier regression, and Bank Detail port compatibility fallback classification/removal.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:bank-account-balance-refresh-producer-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-repository-port-extraction.md`
   - `docs/modules/bank-account-balance/README.md`
   - `docs/modules/bank-account-balance/state-machine.md`
   - `docs/modules/bank-account-balance/tests.md`
   - `docs/modules/bank-account-balance/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/bank_details_application_service.py`
   - `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
   - `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_bank_account_balance_read_model.py`
   - `tests/test_bank_details_sql_runtime.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - `tests/test_runtime_worker_read_model_refresh_scopes.py`

## Boundary Scope

Target:

- Add `BankAccountBalanceReadModelRefreshProducer`.
- Keep all non-transactional enqueue behind `ReadModelRefreshGateway`.
- Preserve the current all-only contract by enqueueing only `bank_account_balance:all`.
- Route `Application._enqueue_bank_account_balance_read_model_refresh(...)` callers through the producer or remove the app helper if all callers can use the producer directly.
- Update `BankDetailsApplicationService` injection so API miss/stale/migration-missing enqueue uses the producer boundary.
- Route import-state account-balance refresh in `Application` through the producer.
- Include runtime import-state fan-out through the producer if the change is still small and testable; otherwise queue it as the immediate next boundary.
- Add tests proving account-balance refresh enqueue uses the producer/gateway boundary and old direct app-owned helper behavior cannot return.
- Update analysis/state/docs after implementation.

Non-goals:

- Do not change balance calculation, account identity, latest balance selection, API response shape, permissions, audit behavior, frontend behavior, queue schema or worker event type.
- Do not introduce month/account scoped projection.
- Do not change the `bank_account_balance:all` worker publish scope.
- Do not implement Go/Fiber/Go Worker.

Expected verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry -v`
- Add any new focused producer/static/runtime tests to that command.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified producer extraction implementation slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
