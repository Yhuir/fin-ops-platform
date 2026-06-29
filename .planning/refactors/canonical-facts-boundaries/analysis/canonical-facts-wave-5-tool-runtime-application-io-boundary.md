# Canonical Facts Wave 5 - Tool Runtime Application I/O Boundary

Date: 2026-06-29

## Scope

Bounded slice for ETC historical migration/link/cleanup tools that still reached `Application._state_store` directly:

- `backend/src/fin_ops_platform/tools/link_existing_etc_batches.py`
- `backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py`
- `backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py`

These tools are current named operational entrypoints, not dead legacy files:

- `docs/operations/etc-business-batches.md` documents `migrate_historical_etc_business_batches.py` for historical submitted ETC migration.
- `docs/modules/etc-tickets/boundary-io.md` lists cleanup/migration/link tools as ETC module tools.
- `docs/modules/workbench-relations/boundary-io.md` lists migration/link tools as Workbench relation tools.
- Existing unit tests cover link and migration dry-run behavior.

## Decision

Do not delete these tools in this slice. Instead, isolate their remaining application snapshot/state persistence I/O in one explicit tool-only boundary:

- `backend/src/fin_ops_platform/tools/runtime_application.py`

The business tool files now depend on this module and no longer directly access `Application._state_store` or `_initialize_runtime_services`.

## I/O Boundary

Input:

- Optional `--data-dir` for non-PostgreSQL/local operational runs.
- Tool spec JSON files and task ids owned by the calling tool.

Boundary module:

- Builds a lightweight `Application` through `build_application(...)`.
- Loads only the partial snapshots needed by these legacy operational tools: imports, file imports, Workbench pair relations and ETC reconciliation state.
- Exposes explicit callbacks for ETC state persistence and invoice ETC metadata persistence.

Output:

- The calling tool receives initialized application services and explicit persistence callbacks.
- Business tool files do not know how application state is loaded or persisted.

Deletion criteria:

- Delete `runtime_application.py` after the remaining tools either move to owner module service/repository ports without application private state, or are retired.

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/runtime_application.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py tests/test_migrate_historical_etc_business_batches_tool.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_link_existing_etc_batches_tool tests.test_migrate_historical_etc_business_batches_tool
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_production_runtime_paths_do_not_import_local_state_store
```
