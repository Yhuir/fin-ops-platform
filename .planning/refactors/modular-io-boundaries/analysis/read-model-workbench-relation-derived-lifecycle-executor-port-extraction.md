# Workbench Relation Derived Lifecycle Executor Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:workbench-relation-derived-lifecycle-executor-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Decision

Extract the app-level `Application._derived_lifecycle_workbench_relation_read_model_executor(...)` helper into an explicit service boundary: `WorkbenchRelationDerivedLifecycleExecutor`.

This closes only the derived lifecycle enqueue helper boundary. It does not migrate canonical relation writes, relation command service ownership, read facade semantics, projection builder semantics or downstream page read models.

## Previous State

- `workbench_relation` repository port extraction was already closed.
- `server.py` still owned the derived lifecycle refresh enqueue helper for `workbench_relation`.
- The helper selected explicit domain plan scope keys when present, otherwise fell back to `["all"]`.
- The helper enqueued through `_enqueue_generic_read_model_refreshes("workbench_relation", ...)`, which delegates to `ReadModelRefreshGateway`.

## Runtime Changes

- Added `backend/src/fin_ops_platform/services/workbench_relation_derived_lifecycle_executor.py`.
- Removed `Application._derived_lifecycle_workbench_relation_read_model_executor(...)`.
- Updated the derived lifecycle executor registry to use `self._workbench_relation_derived_lifecycle_executor().execute`.
- Added `Application._workbench_relation_derived_lifecycle_executor(...)` as dependency assembly only.
- Preserved reason default, metadata filtering, `deleted_counts`, `invalidated_scopes` and `enqueued_jobs` payload shape.
- Added a static guard preventing the old app-level helper from returning.

## Preserved Contract

- Explicit `domain_plan["scope_keys"]` still wins.
- Empty scope plans still fall back to `["all"]`.
- Enqueue still goes through the same gateway-backed app enqueue wrapper.
- Metadata forwarding remains limited to:
  - `source`
  - `case_id`
  - `action_name`
  - `downstream_scope_types`
  - `invoice_usage_scope_types`
  - `pending_invoice_scope_keys`
- `workbench_relation.read_model.refresh` remains the reported job name when enqueue succeeds.

## Legacy Path Classification

- Removed: `Application._derived_lifecycle_workbench_relation_read_model_executor(...)`.
- Retained as dependency assembly: `Application._workbench_relation_derived_lifecycle_executor(...)`.
- Compat-only: none introduced.
- Blocked-by-human-gate: none.

Old paths in this slice do not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status or new authoritative outputs outside the existing gateway-backed enqueue boundary.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/state-machine.md`

No global or module state definition changed. Existing labels remain sufficient:

- this slice: `implementation-closed`;
- `workbench_relation` module closure: `implementation-gap-open`;
- next slice: `analysis-pending`;
- Go candidates: `blocked-by-prerequisite`.

The next boundary should be:

`read-models:workbench-relation-local-implementation-closure-audit`

That audit must decide whether the remaining local gaps are relation write lifecycle extraction, repository SQL owner split, read facade force-refresh/freshness proof hardening, service factory collaborator audit, or a production-evidence defer slice.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. This slice does not change relation modes, statuses, row occupation, amount rules or idempotency. |
| Service-layer tests | Applicable. `tests/test_workbench_relation_derived_lifecycle_executor.py` covers explicit scope selection, all fallback, reason/metadata forwarding and payload shape. |
| API contract tests | Not directly applicable. No HTTP route or response shape changed. App startup check was run. |
| Read model/cache/background job tests | Applicable. The new executor tests prove the same read model refresh job payload behavior; derived lifecycle service regression tests still pass. |
| Frontend component and interaction tests | Not applicable. No frontend API or UI behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this narrow app helper extraction. Existing relation E2E remains broader regression evidence. |
| Existing feature regression tests | Applicable. `tests/test_derived_data_lifecycle_service.py`, app check and the static runtime boundary guard protect existing lifecycle registry behavior. |

## Verification

Executed:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_derived_lifecycle_executor tests.test_bank_detail_derived_lifecycle_executor -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_relation_derived_lifecycle_uses_explicit_executor_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`

Pending before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Completion Claim

This slice closes only the `workbench_relation` derived lifecycle executor extraction boundary. The module remains `implementation-gap-open`; production PostgreSQL/worker/App Status/high-row/browser evidence is not claimed, and Go/Fiber/Go Worker admission remains blocked.
