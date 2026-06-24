# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:no-oa-bank-batch-full-state-snapshot-quarantine` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:no-oa-bank-batch-full-state-snapshot-quarantine`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `no_oa_bank_batch` is the eleventh non-Go read model implementation pilot.
- Implemented no-OA boundaries:
  - `NoOaBankBatchReadModelPersistencePort` owns worker refresh public snapshot persistence delegation.
  - `NoOaBankBatchReadModelRepositoryPort` owns list/query read model repository access.
  - `NoOaBankBatchDerivedLifecycleExecutor` owns derived lifecycle target scope selection, metadata forwarding and enqueued-job accounting.
  - `save_no_oa_bank_batch_mutation(...)` is required for mutation persistence; service-layer broad state-store fallback writes are removed.
  - Broad `Application._persist_state(...)` no longer serializes `no_oa_bank_batches`.
- Refresh enqueue goes through `ReadModelRefreshGateway`; scope policy accepts only `all` and month scopes.
- App Status, runtime worker registry and manifest contracts are registered for `no_oa_bank_batch`.
- Frontend submit/withdraw waits on concrete month operation barrier targets; tag selection waits on `all`.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:no-oa-bank-batch-post-full-state-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-full-state-snapshot-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-mutation-persistence-fallback-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-derived-lifecycle-executor-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_derived_lifecycle_executor.py`
   - relevant no-OA/read model/frontend operation barrier tests.
6. Use CodeGraph for structural lookup and impact before deciding closure.

## Boundary Scope

Target:

- Re-audit no-OA local route/service/repository/read model/worker/frontend/API surfaces after full-state snapshot quarantine.
- Classify remaining old no-OA route/service/repository/read model/frontend API/worker paths as removed, quarantined, compat-only, production-evidence-deferred, or implementation-gap-open.
- Verify no local app-owned helper still owns read model refresh persistence, list repository access, derived lifecycle execution, mutation persistence fallback, or broad full-state no-OA snapshot persistence.
- If a concrete local implementation gap remains, split and execute the first narrow implementation boundary.
- If no local implementation gap remains, record `production-evidence-deferred` for real PostgreSQL/worker/App Status/high-row/browser evidence only; do not mark the module globally closed.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not change no-OA business rules, relation rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning or frontend behavior unless a verified gap requires it and tests are updated.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Targeted no-OA application/read model/workbench integration tests.
- Relevant platform/read model boundary guards.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified no-OA post-full-state local implementation closure audit or split the first concrete local implementation gap, commit and push to `origin/dev`, then continue to the next selected boundary unless a hard stop gate is hit.
