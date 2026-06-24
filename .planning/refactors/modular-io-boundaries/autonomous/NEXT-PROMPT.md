# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-search` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-search`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `search` local implementation support is accounted for and remains `production-evidence-deferred`, not globally closed.
- `bank_account_balance` is now the thirteenth non-Go read model pilot.
- `bank_account_balance` is user-visible through `/api/bank-details/accounts`, participates in bank import write-operation SLO, and must keep balance amount/readiness independent from `bank_detail` rows.
- Current implementation gaps:
  - `BankAccountBalanceProjectionBuilder` saves through broad `PostgresReadModelRepository`.
  - `BankDetailReadModelRepositoryPort` still exposes `list_bank_account_balances(...)`.
  - `BankDetailsApplicationService.accounts_payload(...)` reads account-balance payloads through the bank detail SQL repository surface.
  - `Application._enqueue_bank_account_balance_read_model_refresh(...)` and `_derived_lifecycle_bank_account_balance_executor(...)` remain app-owned helpers for later slices.
  - Scope policy accepts month/all while current worker/storage only accepts `bank_account_balance:all`; do not introduce month/account shards without a separate design.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:bank-account-balance-repository-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-search.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-and-bank-account-balance-contract.md`
   - `docs/modules/bank-account-balance/README.md`
   - `docs/modules/bank-account-balance/state-machine.md`
   - `docs/modules/bank-account-balance/tests.md`
   - `docs/modules/bank-account-balance/implementation-notes.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/bank_details_application_service.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_bank_account_balance_read_model.py`
   - `tests/test_bank_details_sql_runtime.py`
   - `tests/test_bankdetail_backfill_cli.py`
   - `tests/test_read_model_manifest.py`
   - `tests/test_runtime_worker_registry.py`

## Boundary Scope

Target:

- Add `BankAccountBalanceReadModelRepositoryPort` exposing only manifest-listed methods:
  - `bank_account_balance_scope_summary(...)`
  - `list_bank_account_balances(...)`
  - `save_bank_account_balances(...)`
- Route `BankAccountBalanceProjectionBuilder` save path through the narrow port.
- Route Bank Details accounts SQL read path through an explicit account-balance port while preserving response shape and current refreshing/fresh behavior.
- Remove `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` if call graph/tests prove no callers remain; otherwise classify it as compat-only with a guard preventing it from becoming the owner.
- Update `READ_MODEL_MANIFEST["bank_account_balance"].repository_owner` if a new port becomes the owner.
- Add/extend tests proving the account-balance port excludes unrelated read model methods and existing Bank Details accounts behavior remains compatible.

Constraints:

- Do not change balance calculation, account identity, latest balance selection, currency normalization, API shape, worker event names, queue schema, permissions, audit behavior, frontend behavior, or Go/Fiber/Go Worker.
- Do not introduce month/account scoped projection in this slice.
- Keep SQL/table knowledge in repository; the port should delegate only.
- Keep `server.py` as dependency wiring only.

Expected verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified repository-port extraction slice for `bank_account_balance`, commit and push to `origin/dev`, then continue to the next selected boundary unless a hard stop gate is hit.
