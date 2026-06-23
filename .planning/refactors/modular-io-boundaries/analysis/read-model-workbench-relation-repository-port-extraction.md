# Workbench Relation Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:workbench-relation-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Decision

Add a narrow `WorkbenchRelationReadModelRepositoryPort` and wire `workbench_relation` read-model consumers through it before migrating broader relation lifecycle code.

This mirrors the successful `bank_detail` repository-port pattern: the broad `PostgresReadModelRepository` remains the SQL implementation owner, but app/worker read-model wiring no longer needs the full repository surface for `workbench_relation`.

## Runtime Changes

- Added `backend/src/fin_ops_platform/services/workbench_relation_read_model_repository.py`.
- `PostgresStateStore` now exposes `workbench_relation_sql_read_repository`.
- `Application._workbench_relation_read_facade(...)` now uses `_workbench_relation_sql_read_repository` instead of `_state_store.read_model_repository`.
- `worker.py` now injects `WorkbenchRelationReadModelRepositoryPort` into `WorkbenchRelationSqlProjectionBuilder`.
- `WorkbenchRelationSqlProjectionBuilder` wraps the default `PostgresReadModelRepository` in the port when no repository is passed.
- `READ_MODEL_MANIFEST["workbench_relation"].repository_owner` is now `WorkbenchRelationReadModelRepositoryPort`.

## Port Contract

Allowed methods:

- `get_workbench_relation_rows_by_ids`
- `list_workbench_relation_rows`
- `get_workbench_relation_groups_by_ids`
- `workbench_relation_source_versions`
- `save_workbench_relation_distribution`
- `mark_workbench_relation_scope_empty`

Forbidden through this port:

- unrelated read model query methods such as pending invoice, OA pending, bank detail or cost/tax methods;
- canonical relation write lifecycle methods;
- direct writes to `app.workbench_pair_relations`;
- direct queue/readiness manipulation outside existing refresh gateway and worker services.

## Preserved Behavior

- `WorkbenchRelationReadFacade` still owns downstream freshness-gated read behavior.
- Missing/stale relation context still enqueues refresh through `ReadModelRefreshGateway`.
- `linked` / `candidate` / `unlinked` semantics are unchanged.
- Source-version payloads are unchanged.
- Projection builder still writes the same relation distribution rows/groups.
- Canonical relation write lifecycle is untouched.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/state-machine.md`

No new global or module state definition is required. The existing state labels are sufficient:

- this slice: `implementation-closed`;
- `workbench_relation` module closure: `implementation-gap-open`;
- next slice: `implementation-pending`;
- Go candidates: `blocked-by-prerequisite`.

The next implementation boundary should be:

`read-models:workbench-relation-derived-lifecycle-executor-port-extraction`

That next slice should extract the remaining `Application._derived_lifecycle_workbench_relation_read_model_executor(...)` app-level lifecycle enqueue helper into an explicit service/port, without touching relation writes.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. This slice does not change relation business rules, mode/state transitions, amount logic, row occupation or idempotency. |
| Service-layer tests | Applicable. `tests/test_workbench_relation_read_facade.py::WorkbenchRelationReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods` proves the new port exposes only relation read-model methods and forwards allowed calls. |
| API contract tests | Not directly applicable. No HTTP response shape or route behavior changed. App startup check was run to catch wiring errors. |
| Read model/cache/background job tests | Applicable. `tests/test_workbench_relation_read_facade.py` and `tests/test_workbench_relation_sql_projection.py` prove freshness statuses, enqueue behavior, candidate/linked/unlinked semantics and projection writes remain intact. |
| Frontend component and interaction tests | Not applicable. No frontend behavior or API payload changed. |
| End-to-end business-flow integration tests | Not applicable for this port extraction. Existing relation E2E remains regression evidence; no browser behavior changed. |
| Existing feature regression tests | Applicable. The facade/projection tests and app check protect existing relation read/projection behavior and app wiring. |

## Verification

Executed:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_read_facade -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_sql_projection -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`

Pending before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Completion Claim

This slice closes only the repository port extraction boundary. It does not close `workbench_relation`, does not migrate relation write lifecycle, does not validate production PostgreSQL/worker behavior, and does not unblock Go admission.
