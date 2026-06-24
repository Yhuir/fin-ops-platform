# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:search-post-all-scope-worker-fanout-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:search-post-all-scope-worker-fanout-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `search` is the twelfth non-Go read model pilot.
- Search local implementation support is accounted for after:
  - `SearchReadModelRepositoryPort`
  - `SearchQueryFreshnessService`
  - `SearchIndexSourceVersionsProvider`
  - `SearchReadModelRefreshProducer`
  - app rebuild helper quarantine
  - production PostgreSQL repository-unavailable fail-closed behavior
  - OA projection sync Search fan-out producer boundary
  - runtime import-state Search fan-out producer boundary
  - Search worker `search:all` fan-out producer boundary
- `search` is not globally closed; real PostgreSQL/worker/App Status/high-row/browser evidence remains `production-evidence-deferred`.
- `bank_account_balance` is the remaining known read model candidate, but it must be confirmed from current docs/code evidence before implementation.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-search`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-post-all-scope-worker-fanout-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-and-bank-account-balance-contract.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/search/README.md`
   - `docs/modules/search/state-machine.md`
   - `docs/modules/search/tests.md`
   - `docs/modules/search/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
   - `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
   - `backend/src/fin_ops_platform/app/bank_account_balance_backfill.py`
   - `backend/src/fin_ops_platform/postgres/migrations/0039_bank_account_balance_read_model.sql`
   - `tests/test_bank_account_balance_read_model.py`
   - `tests/test_read_model_manifest.py`
   - `tests/test_runtime_worker_registry.py`
   - `tests/test_read_model_slo_smoke.py`

## Boundary Scope

Target:

- Select the next non-Go read model pilot after Search local support is accounted for.
- Confirm whether `bank_account_balance` is the correct next candidate from current manifest, registry, scope policy, code paths, tests and module docs.
- If `bank_account_balance` is selected, insert the first narrow implementation boundary based on current evidence. Prefer a repository/freshness/operation-barrier audit boundary before any implementation if the first concrete gap is not yet proven.
- Do not implement Go/Fiber/Go Worker.
- Do not claim full module closure for any prior module.

Expected verification:

- `bash scripts/verify.sh docs`
- `git diff --check`
- Add targeted tests only if this selection slice changes code or test contracts.

## Stop Condition

Complete one verified next-pilot selection/accounting slice, commit and push to `origin/dev`, then continue to the selected first implementation or audit boundary unless a hard stop gate is hit.
