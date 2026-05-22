# Runtime Read Model Final Hardening Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining production hardening gaps for SQL-native runtime read model convergence without reintroducing Application snapshot fallback.

**Architecture:** PostgreSQL facts/projections remain the durable source. Worker builders read repository-native SQL tables, write versioned `read_model.*` rows, and expose reconciliation/EXPLAIN evidence through scripts and docs. Legacy builders may only be used by explicit audit scripts, never production API or worker paths.

**Tech Stack:** Python, PostgreSQL, `read_model.*`, `app.workbench_*`, pytest, `EXPLAIN (FORMAT JSON)`, local PG/Redis/MinIO smoke.

---

## /goal

完成 SQL-native runtime read model 最后一轮 hardening：补齐 workbench old-builder vs SQL projection reconciliation 脚本、override/exception parity、source-version 防旧写、cost/tax reconciliation 入口、hot path EXPLAIN/索引计划记录，并运行目标测试与本地 PG/Redis/MinIO smoke。

## Serial Tasks

### Task 1: Workbench Parity Boundaries

**Files:**
- Modify: `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- Modify: `tests/test_workbench_sql_runtime.py`

- [x] Read `app.workbench_row_overrides` by row id and apply `WorkbenchOverrideService` before grouping.
- [x] Read active `app.workbench_exception_cases` by row id and project exception rows using `WorkbenchOverrideService.apply_exception_projection`.
- [x] Keep candidate generation after active relation and exception/override application so candidates do not override held rows.
- [x] Add tests for override and exception projection parity.

### Task 2: Source-Version Guard

**Files:**
- Modify: `backend/src/fin_ops_platform/services/runtime_queue.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_read_model_refresh.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `tests/test_workbench_sql_runtime.py`
- Modify: `tests/test_runtime_queue.py`

- [x] Increment `job.read_model_dirty_scopes.source_version` on each enqueue and put that version into outbox payload.
- [x] Pass event `source_version` from refresh service to workbench SQL builder.
- [x] Include source_version in `read_model.workbench_snapshots`, `workbench_rows`, and `workbench_candidate_matches`.
- [x] Skip stale writes when incoming source_version is older than existing read model source_version.
- [x] Add tests for dirty scope source_version propagation and stale read model write rejection.

### Task 3: Reconciliation And EXPLAIN Tools

**Files:**
- Create: `scripts/reconcile-runtime-read-models.py`
- Create: `docs/operations/runtime-read-model-hardening.md`
- Modify: `docs/superpowers/plans/2026-05-22-sql-native-worker-projections.md`

- [x] Add a production-safe reconciliation script that reports workbench row/candidate counts, cost/tax read model counts, and optional hot-path EXPLAIN JSON.
- [x] Keep legacy builder comparison opt-in and documented as audit/shadow only.
- [x] Run the script against local PostgreSQL and record sample output summary in operations docs.
- [x] Update the existing SQL-native worker plan with closed and still-open items.

## Parallel Workstreams

- **A: Workbench parity** - override/exception projection and candidate ordering.
- **B: Version guard** - queue source version propagation and stale write protection.
- **C: Reconciliation tooling** - script, docs, EXPLAIN evidence.
- **D: Verification** - pytest, `git diff --check`, local PG/Redis/MinIO smoke.

## Completion Gate

- Production worker refresh modules and SQL projection builders still pass guard tests for no `build_application`, no `StateStore.load()`, no `state:*`.
- Workbench SQL projection applies active overrides, active exception cases, active pair relations, no-OA relation payloads, OA attachment invoice rows, and candidate matches.
- Older source_version writes cannot overwrite newer workbench read model rows/snapshots/candidates.
- A local reconciliation/EXPLAIN command runs successfully against PostgreSQL.
- Targeted pytest passes and `./scripts/check-local-runtime.sh --require-backend` passes.

## Verification Run

2026-05-22 local production-equivalent runtime:

- [x] `PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m pytest tests/test_runtime_state_policy.py tests/test_runtime_queue.py tests/test_cost_statistics_sql_runtime.py tests/test_tax_offset_sql_runtime.py tests/test_workbench_sql_runtime.py tests/test_search_pending_sql_runtime.py tests/test_app_postgres_mode.py tests/test_runtime_bootstrap.py tests/test_oa_projection_sql_runtime.py tests/test_file_object_storage.py -q`
  - Result: `107 passed, 5 warnings, 24 subtests passed`
- [x] Direct PostgreSQL repository smoke for `scope_key='all'`
  - Result: `row_count=61`, `open_groups=22`, `paired_groups=4`, `refresh_status=refreshing`
- [x] `set -a; source .runtime/fin_ops_platform/local-postgres.env; set +a; /opt/miniconda3/bin/python3 scripts/reconcile-runtime-read-models.py --scope-key 2025-12 --explain --json`
  - Result: workbench `2025-12` has `row_count=43`, source kinds `bank=5`, `invoice=2`, `oa=12`, `oa_attachment_invoice=24`, candidate matches `needs_review=2`
- [x] `git diff --check`
  - Result: passed
- [x] `./scripts/check-local-runtime.sh --require-backend`
  - Result: PostgreSQL/Redis/MinIO/backend health ready; Workbench API `month=all` returned `total=61`, `groups=26`

Open audit boundary: old-builder semantic comparison remains opt-in through `scripts/reconcile-runtime-read-models.py --legacy-workbench-json ...`; it requires an explicit legacy/shadow JSON export and is not part of the production API or worker path.
