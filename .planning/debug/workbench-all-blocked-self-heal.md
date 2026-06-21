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

- hypothesis: The previous bad ordinary `workbench:all` event left a durable failed all-scope generation/queue item and a pending aggregate/backlog item; the current architecture reports it as blocked but does not automatically repair by rebuilding affected month shards and republishing aggregate-only all.
- next_action: resolved; deploy and let runtime worker consume the current backlog so parent month scopes rebuild and aggregate-only all publishes a fresh active generation.

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
