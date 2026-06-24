# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `no_oa_bank_batch` is the eleventh non-Go read model implementation pilot.
- `NoOaBankBatchReadModelPersistencePort` owns no-OA public snapshot persistence delegation for the worker refresh path.
- `NoOaBankBatchReadModelRepositoryPort` owns no-OA list/query read model repository access.
- Refresh enqueue goes through `ReadModelRefreshGateway`; scope policy accepts only `all` and month scopes.
- App Status, runtime worker registry and manifest contracts are registered for `no_oa_bank_batch`.
- Frontend submit/withdraw waits on concrete month operation barrier targets; tag selection waits on `all`.
- Remaining local gaps:
  - `Application._derived_lifecycle_no_oa_bank_batch_executor(...)` still owns no-OA derived lifecycle target selection/enqueue result assembly.
  - `NoOaBankBatchApplicationService.persist_mutation(...)` still has broad state-store fallback writes when `save_no_oa_bank_batch_mutation(...)` is absent.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/bank_detail_derived_lifecycle_executor.py`
   - `backend/src/fin_ops_platform/services/invoice_lifecycle_derived_lifecycle_executor.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - relevant lifecycle/no-OA tests.
6. Use CodeGraph for structural lookup and impact before editing.

## Boundary Scope

Target:

- Add `NoOaBankBatchDerivedLifecycleExecutor` or local-pattern equivalent.
- Move no-OA derived lifecycle scope selection, metadata forwarding and enqueue result assembly out of `Application._derived_lifecycle_no_oa_bank_batch_executor(...)`.
- Wire `Application` to create/use the executor with an explicit enqueue callback.
- Preserve target scope semantics:
  - month scope keys become month target scopes.
  - non-month or empty scope plans default to `all`.
  - enqueue reason defaults to `derived_lifecycle_no_oa_bank_batch`.
  - metadata is forwarded through read model refresh metadata.
  - result keeps `deleted_counts`, `invalidated_scopes`, and `enqueued_jobs`.
- Add unit/static guard coverage proving `Application` no longer owns this behavior.
- Do not touch the mutation persistence fallback in this slice except to record it as the next pending boundary.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not change business rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning or frontend behavior.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service tests.test_derived_data_lifecycle_service tests.test_platform_runtime_boundary_guards -v` or narrower targeted platform guards if full guard module has unrelated failures.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified no-OA derived lifecycle executor extraction slice, commit and push to `origin/dev`, then continue to `read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine` unless a hard stop gate is hit.
