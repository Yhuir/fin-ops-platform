# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `no_oa_bank_batch` is the eleventh non-Go read model implementation pilot.
- `NoOaBankBatchReadModelPersistencePort` owns no-OA public snapshot persistence delegation for the worker refresh path.
- `NoOaBankBatchReadModelRepositoryPort` owns no-OA list/query read model repository access.
- `NoOaBankBatchDerivedLifecycleExecutor` owns derived lifecycle target scope selection, refresh metadata forwarding and enqueued-job accounting.
- Refresh enqueue goes through `ReadModelRefreshGateway`; scope policy accepts only `all` and month scopes.
- App Status, runtime worker registry and manifest contracts are registered for `no_oa_bank_batch`.
- Frontend submit/withdraw waits on concrete month operation barrier targets; tag selection waits on `all`.
- Remaining local gap:
  - `NoOaBankBatchApplicationService.persist_mutation(...)` still has broad state-store fallback writes when `save_no_oa_bank_batch_mutation(...)` is absent.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-derived-lifecycle-executor-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `backend/src/fin_ops_platform/services/state_store.py`
   - relevant no-OA mutation/persistence tests.
6. Use CodeGraph for structural lookup and impact before editing.

## Boundary Scope

Target:

- Remove or quarantine the fallback in `NoOaBankBatchApplicationService.persist_mutation(...)` that directly calls broad state-store methods:
  - `save_workbench_pair_relations(...)`
  - `save_no_oa_bank_batches(...)`
  - `save_workbench_read_models(...)`
- Preserve the primary atomic boundary `save_no_oa_bank_batch_mutation(...)`.
- Decide from current code whether local/non-PostgreSQL stores need an explicit narrow mutation port or should fail fast when the atomic boundary is absent.
- Keep no-OA submit/withdraw/internal-transfer mutation semantics unchanged.
- Add tests/guards proving mutation persistence no longer falls back to broad state-store writes.
- Record any production/local compatibility limitation explicitly.

Forbidden:

- Do not change no-OA business rules, relation rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning or frontend behavior.
- Do not change the already extracted derived lifecycle executor except to fix a regression caused by this slice.
- Do not implement Go/Fiber/Go Worker.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py backend/src/fin_ops_platform/services/postgres_state_store.py`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Targeted no-OA mutation/persistence tests, no-OA application/read model/workbench integration tests, and relevant platform guards.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified no-OA mutation persistence fallback quarantine slice, commit and push to `origin/dev`, then run a no-OA local closure audit unless a hard stop gate is hit.
