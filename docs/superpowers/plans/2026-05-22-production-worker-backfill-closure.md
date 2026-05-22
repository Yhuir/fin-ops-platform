# Production Worker Backfill Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 OA projection、SQL-native workbench builder、runtime worker、全量 backfill 与 reconciliation 的生产级收口，让 PostgreSQL facts 月份覆盖和 read model 月份覆盖一致。

**Architecture:** PostgreSQL facts 是唯一生产事实源；OA sync worker 将 OA 主记录、付款明细、附件和发票识别结果拆入结构化表；read model worker 按 month/scope shard 从结构化 repository 读取并写 `read_model.*`。worker 通过 PostgreSQL durable queue claim，带任务超时、statement timeout、进度 heartbeat 和可重复 backfill/reconciliation 入口；Redis 只做 wakeup/cache，不影响正确性。

**Tech Stack:** Python, PostgreSQL, psycopg, `job.outbox_events`, `job.read_model_dirty_scopes`, `app.oa_*`, `read_model.*`, pytest, local PG/Redis/MinIO smoke.

---

## /goal

正式收口 runtime SQL read model worker/backfill：补 OA projection repository，把 `expense_items`、attachments、invoice artifacts 写入结构化 PG 表；把 workbench builder 改成 SQL-native 结构化读取优先；给 worker 增加任务 timeout、statement timeout、进度日志和卡死释放；为本地/服务器提供长期 worker 服务配置；跑全量 backfill 并用 reconciliation 证明 facts 月份覆盖与 read model 月份覆盖一致。

## Serial Tasks

### Task 1: Evidence And Guard Tests

**Files:**
- Modify: `tests/test_oa_projection_sql_runtime.py`
- Modify: `tests/test_runtime_queue.py`
- Modify: `tests/test_workbench_sql_runtime.py`

- [x] Add failing tests proving `PostgresOAProjectionRepository.upsert_application_records()` writes rows to `app.oa_application_items` and `app.oa_attachments`.
- [x] Add failing tests proving workbench SQL projection can build OA attachment invoice rows from structured `app.oa_application_items` / `app.oa_attachments` / `app.oa_attachment_invoice_cache` without relying only on `oa_applications.normalized_payload.expense_items`.
- [x] Add failing tests proving worker sets a bounded PostgreSQL statement timeout per claimed event and clears it after completion/failure.

### Task 2: Structured OA Projection

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py`
- Modify: `backend/src/fin_ops_platform/postgres/migrations/0012_workbench_rows_scope_unique.sql`

- [x] Upsert OA application and return its `id`.
- [x] Delete and reinsert child `app.oa_application_items` for the application in the same transaction.
- [x] Delete and reinsert child `app.oa_attachments` for the application in the same transaction.
- [x] Derive attachment rows from `attachment_invoices`, `attachment_evidences`, and `attachment_artifacts`; keep source attachment key stable.
- [x] Add indexes needed by structured reads: item application/row, attachment application/source key, attachment file name, and optional scope lookup through parent.

### Task 3: SQL-Native Workbench Builder

**Files:**
- Modify: `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- Modify: `tests/test_workbench_sql_runtime.py`

- [x] Read attachment invoice evidence from structured OA item/attachment/cache joins first.
- [x] Fall back to existing payload-derived evidence only for rows not yet structure-backfilled.
- [x] Keep row id generation stable with old attachment row ids.
- [x] Ensure month shards `2026-01` to `2026-04` build without loading all application state or calling `Application`.

### Task 4: Worker Runtime Hardening

**Files:**
- Modify: `backend/src/fin_ops_platform/services/runtime_worker.py`
- Modify: `backend/src/fin_ops_platform/services/runtime_queue.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Modify: `tests/test_runtime_queue.py`

- [x] Add `RuntimeWorkerConfig.statement_timeout_seconds`.
- [x] Set PostgreSQL `statement_timeout` before handling each event when repository supports it.
- [x] Add heartbeat status `processing` with event id/scope before handler execution.
- [x] On timeout or exception, fail event as retryable and include concise error text.
- [x] Keep stale processing event reclaim through `lock_timeout_seconds`.

### Task 5: Backfill And Worker Service Entrypoints

**Files:**
- Create: `scripts/backfill-runtime-read-models.py`
- Modify: `docs/operations/deployment.md`
- Modify: `docs/operations/runtime-read-model-hardening.md`
- Modify: `backend/README.md`

- [x] Add idempotent CLI to enqueue all missing workbench/search/cost/tax/pending scopes from facts.
- [x] Add `--run-worker` mode to drain bounded iterations with configured handlers.
- [x] Document local and server worker commands for `worker-workbench`, `worker-search`, `worker-pending-invoice`, `worker-cost-tax`, and `worker-oa-sync`.
- [x] Document that API alone is not enough; production requires persistent worker services.

### Task 6: Verification

**Commands:**
- `PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m pytest tests/test_oa_projection_sql_runtime.py tests/test_workbench_sql_runtime.py tests/test_runtime_queue.py tests/test_runtime_state_policy.py -q`
- `set -a; source .runtime/fin_ops_platform/local-postgres.env; set +a; /opt/miniconda3/bin/python3 scripts/backfill-runtime-read-models.py --enqueue-missing`
- `set -a; source .runtime/fin_ops_platform/local-postgres.env; set +a; /opt/miniconda3/bin/python3 scripts/backfill-runtime-read-models.py --run-worker --max-iterations 200`
- `set -a; source .runtime/fin_ops_platform/local-postgres.env; set +a; /opt/miniconda3/bin/python3 scripts/reconcile-runtime-read-models.py --scope-key all --explain --json`
- `./scripts/check-local-runtime.sh --require-backend`
- `git diff --check`

## Parallel Workstreams

- **A: OA facts structure** - repository child-table writes and backfill query surfaces.
- **B: Workbench SQL-native builder** - structured attachment evidence and month shard parity.
- **C: Worker hardening** - timeout, heartbeat, reclaim behavior.
- **D: Operations/backfill** - enqueue/drain CLI, docs, local/server worker commands.

## Completion Gate

- `app.oa_application_items` and `app.oa_attachments` are populated for synced OA records with expense items/attachments.
- `read_model.workbench_rows` covers every month present in `app.invoices`, `app.bank_transactions`, or `app.oa_applications` unless explicitly filtered by status/deleted rows.
- `job.outbox_events` and `job.read_model_dirty_scopes` do not remain pending for normal backfill scopes after worker drain.
- Workbench API `month=all` and month shards return SQL read model data without calling `_build_raw_workbench_payload`.
- Worker has bounded task timeout and progress heartbeat.
- Redis/MinIO absence does not break PostgreSQL polling correctness; when configured locally, health reports them as ready.
