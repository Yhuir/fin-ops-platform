# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-account-balance-bank-detail-fallback-quarantine` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-account-balance-bank-detail-fallback-quarantine`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_account_balance` is the thirteenth non-Go read model pilot and remains `implementation-gap-open` until local closure audit confirms otherwise.
- `BankAccountBalanceReadModelRepositoryPort` owns manifest-listed scope summary/list/save methods.
- `BankAccountBalanceReadModelRefreshProducer` owns gateway-backed all-only refresh enqueue.
- `BankAccountBalanceDerivedLifecycleExecutor` owns account-balance derived lifecycle response assembly.
- `ReadModelRefreshGateway` rejects non-`all` `bank_account_balance` scopes before durable enqueue.
- Dedicated operation barrier regressions cover `bank_account_balance:all` dirty/readiness and outbox pending behavior.
- Bank Detail port account-balance compatibility fallback has been removed.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:bank-account-balance-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-bank-detail-fallback-quarantine.md`
   - `docs/modules/bank-account-balance/README.md`
   - `docs/modules/bank-account-balance/state-machine.md`
   - `docs/modules/bank-account-balance/tests.md`
   - `docs/modules/bank-account-balance/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/bank_details_application_service.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh_producer.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `tests/test_bank_details_sql_runtime.py`
   - `tests/test_bank_account_balance_read_model.py`
   - `tests/test_read_model_refresh_gateway.py`
   - `tests/test_operation_freshness_barrier.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Re-audit account-balance routes, service, repository port, projection save, refresh producer, worker handler, scope policy, operation barrier and docs/tests.
- If no local implementation gaps remain, move local support to `production-evidence-deferred` without claiming module closure.
- If a local gap remains, insert the next narrow implementation boundary before Go candidates.
- Do not mark full module closure without real PostgreSQL/worker/App Status/high-row/browser evidence.
- Do not implement Go/Fiber/Go Worker.

Expected verification:

- Run the existing account-balance/read-model targeted suite selected by the audit.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified local closure audit/accounting slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
