---
status: resolved
trigger: "After deploying the turnover closure scope fix, App Health still shows blocked with workbench_all_scope_parent_inconsistent, one failed job, one backlog, one refreshing read model, and two syncing domains."
created: "2026-06-21"
updated: "2026-06-21"
---

# Debug Session: workbench-all-blocked-self-heal

## Symptoms

- App Health remains blocked after deploying the code fix.
- Runtime summary still shows one failed queue item, one backlog item, one refreshing read model, and two syncing domains.
- Top error remains `workbench_all_scope_parent_inconsistent: generation_metadata_actual_mis...`.

## Current Focus

- hypothesis: The self-heal path now requeues parent month scopes, but the status plane still prioritizes historical generation consistency failures and failed outbox rows over same-scope active repairs. This makes App Status show syncing scopes and blocked/failed at the same time.
- next_action: resolved in code; deploy and let runtime worker consume the current backlog so parent month scopes rebuild and aggregate-only all publishes a fresh active generation.

## Evidence

- The prior turnover fix stopped new ordinary `workbench:all` fan-out from external turnover closure, but it did not repair historical failed all-scope generation/outbox rows.
- `PostgresReadModelRepository._refresh_workbench_all_scope_from_month_shards(...)` wrote a new failed `workbench:all` generation when any parent month active generation was internally inconsistent.
- `WorkbenchSqlProjectionBuilder.refresh_workbench_all_scope_from_active_shards(...)` treated that failed all generation as a normal RuntimeError, so runtime worker marked the all event failed instead of dependency-not-fresh/deferred.
- Runtime worker dependency refresh parsing skipped same-scope dependencies, so `workbench_read_model_not_fresh: parent_scope_keys=...` could not enqueue the parent `workbench` month scope.

## Eliminated

- App Health current-effective outbox coverage already ignores old failed events after later pending/done/fresh rows for the same event/scope.
- Workbench aggregate-only all already defers when parent dirty scopes are active/failed/stale; the missing path was parent active generation consistency failure after readiness still appeared fresh.

## Resolution

- root_cause: Workbench all-scope aggregation modeled parent generation inconsistency as a failed all generation. That protected all-scope publication but created a durable failed queue/read model state with no automatic parent shard rebuild path.
- fix: Parent generation inconsistency is now modeled as dependency-not-fresh for aggregate-only all. Month publish paths skip all aggregation without writing failed all or rolling back the month shard. Aggregate-only all raises `workbench_read_model_not_fresh: parent_generation_inconsistent parent_scope_keys=...`; runtime worker defers the all event and enqueues the listed parent `workbench` month scopes even if readiness previously looked fresh.
- verification: Added/updated regression tests for repository all aggregation, aggregate-only all defer, runtime worker parent dependency refresh, plus existing App Health current-effective coverage.
- files_changed: `.planning/debug/workbench-all-blocked-self-heal.md`, `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`, `backend/src/fin_ops_platform/services/runtime_worker.py`, `backend/src/fin_ops_platform/services/workbench_sql_projection.py`, `tests/test_runtime_worker.py`, `tests/test_workbench_sql_runtime.py`, `docs/modules/reconciliation-workbench/implementation-notes.md`, `docs/modules/reconciliation-workbench/state-machine.md`.

## Second Pass Resolution

- root_cause: The repair queue was active, but `PostgresReadModelRepository.get_workbench_refresh_status(...)` checked generation consistency failures before dirty scope `pending` / `processing`, so the same scope was reported as `failed` while the worker was already rebuilding it. `RuntimeMonitoringRepository` also treated a historical failed outbox row as current unless it was covered by a later outbox/readiness row; it did not treat same-scope active dirty scope repair as coverage.
- fix: Workbench refresh status now reports `refreshing` while same-scope repair is active, suppressing old `last_error` from the current failure banner while retaining `consistency_status=failed` and stale reasons for diagnostics. Runtime monitoring current-effective outbox SQL now ignores failed/dead-letter/publish-failed read model refresh rows covered by a newer/equal same-scope active dirty scope.
- verification: Added `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_reports_inconsistent_workbench_generation_as_refreshing_during_active_repair` and `tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_ignores_failed_outbox_row_covered_by_active_dirty_scope`.
- files_changed: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`, `backend/src/fin_ops_platform/services/runtime_monitoring.py`, `tests/test_workbench_sql_runtime.py`, `tests/test_app_status_overview_service.py`, `docs/modules/app-health-operations/implementation-notes.md`, `docs/modules/app-health-operations/state-machine.md`, `docs/modules/app-health-operations/tests.md`, `docs/modules/reconciliation-workbench/implementation-notes.md`, `docs/modules/reconciliation-workbench/state-machine.md`, `docs/modules/runtime-workers/tests.md`.
