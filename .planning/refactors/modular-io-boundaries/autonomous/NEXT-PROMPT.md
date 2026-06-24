# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:invoice-lifecycle-refresh-freshness-operation-barrier-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:invoice-lifecycle-refresh-freshness-operation-barrier-audit`
- Last status: `regression-guard-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `invoice_lifecycle` is the seventh non-Go read model implementation pilot.
- Repository port extraction is implemented: `InvoiceLifecycleReadModelRepositoryPort` wraps lifecycle read model methods, the facade uses it for lookups, and the SQL projection builder uses it for save/mark paths.
- Freshness/barrier audit is closed as a regression guard: facade reads do not expose a queryable `all`, refresh service expands `all` into month shards, source-version currentness is checked before and after rebuild, scope policy accepts month/all only, and App Status/worker/manifest contracts are registered.
- `tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests::test_invoice_lifecycle_target_uses_exact_month_scope_for_operation_barrier` now proves a concrete lifecycle month target is not blocked by another month pending outbox.
- `Application._derived_lifecycle_invoice_lifecycle_executor(...)` remains app-owned but gateway-backed. It is the next local implementation gap.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target planning evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-repository-port-extraction.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/domain-events-lifecycle/README.md`
   - `docs/modules/domain-events-lifecycle/tests.md`
6. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Add an explicit `InvoiceLifecycleDerivedLifecycleExecutor` service/port.
- Move `Application._derived_lifecycle_invoice_lifecycle_executor(...)` behavior into that executor.
- Preserve scope selection, `deleted_counts`, `invalidated_scopes`, `enqueued_jobs`, reason default, and metadata filtering semantics.
- Keep refresh enqueue behind `ReadModelRefreshGateway` through the existing application refresh producer callback; do not directly SQL-write `job.outbox_events` or `job.read_model_dirty_scopes`.
- Wire `Application` to call the new executor from the derived lifecycle domain map.
- Add unit/static guard coverage preventing `_derived_lifecycle_invoice_lifecycle_executor` from returning as app-owned implementation logic.
- Update modular IO analysis/state docs and read-models/domain-events module docs/tests as applicable.

Forbidden:

- Do not change invoice lifecycle business rules, payload shape, source-version semantics, worker event semantics, queue schema, API behavior, frontend behavior, Go/Fiber/Go Worker or production state.
- Do not claim `invoice_lifecycle` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted new executor test and relevant static guard.
- Existing derived lifecycle / operation barrier / invoice lifecycle targeted tests as applicable.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified invoice lifecycle derived lifecycle executor extraction slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
