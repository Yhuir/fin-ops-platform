# Phase 1 API Performance Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize the existing Python backend without a language rewrite by adding PostgreSQL pooling, materialized workbench summary reads, true Redis hot-cache reads for workbench groups, pg_stat_statements support, and split API/DB timing metrics.

**Architecture:** Keep Python as the source-of-truth write service and improve the read path. PostgreSQL remains the durable fact/read-model store, Redis becomes the hot page cache for workbench groups, and `/health.api_performance` reports request, connection-acquire, SQL execute/fetch, and Redis cache behavior separately.

**Tech Stack:** Python `unittest`, `psycopg_pool`, PostgreSQL migrations, Redis helper, existing `PostgresReadModelRepository`, existing workbench read-model worker, `ab`/`curl` for local smoke tests.

---

## Reusable Codex /goal Prompt

```text
/goal 执行 fin-ops-platform 第一阶段 API 性能优化，不做 Go/Fiber 重写：

目标：
1. Python 当前服务保留业务写路径，优化热读接口。
2. 给 PostgresConnection 引入 psycopg_pool，避免每次 fetch/execute 新建连接。
3. 把 API 指标拆成 request_total_ms、connection_acquire_ms、sql_execute_fetch_ms、database_query_count。
4. 增加 read_model.workbench_summary 物化表，让 /api/workbench/summary 从 9 次 SQL 降到 1-2 次。
5. 让 /api/workbench/groups 在 Redis 命中时不再查 PostgreSQL cache version；版本 key 由 read model refresh/save 路径写入。
6. 增加 pg_stat_statements migration/文档/健康观测入口，用于后续确认 top SQL。

执行约束：
- 使用 TDD：先写失败测试并确认 RED，再实现。
- 不覆盖已有未提交改动；只碰相关文件。
- 不扩大到全量后端重构或 Go 服务。
- 每个阶段都运行聚焦测试。

可并行任务：
- Task A：PostgreSQL pooling + timing split。
- Task B：workbench_summary migration/repository/save/read。
- Task C：groups Redis true hot cache。
- Task D：pg_stat_statements migration/docs/monitoring。

串行集成顺序：
1. 先完成 Task A，因为后续任务共享连接和指标。
2. 再完成 Task B，因为 summary API 依赖 read_model repository。
3. 再完成 Task C，因为它依赖现有 groups repository 和 Redis helper。
4. 最后完成 Task D 和验证文档。

验收：
- PYTHONPATH=backend/src python3 -m unittest tests.test_api_performance_metrics tests.test_runtime_redis tests.test_postgres_migrations tests.test_workbench_sql_runtime -v
- PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/api_performance_metrics.py backend/src/fin_ops_platform/services/postgres_connection.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py backend/src/fin_ops_platform/app/server.py
- PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## File Structure

- Modify: `backend/src/fin_ops_platform/services/api_performance_metrics.py`
  - Add connection acquire and SQL execute/fetch timers in addition to current aggregate DB duration.
- Modify: `backend/src/fin_ops_platform/services/postgres_connection.py`
  - Add optional `psycopg_pool.ConnectionPool`.
  - Track connection acquisition separately from SQL execution/fetch.
  - Preserve existing context manager and transaction API.
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
  - Add `get_workbench_summary()` fast path from `read_model.workbench_summary`.
  - Add summary payload write alongside workbench read-model save.
  - Add cache version helper suitable for Redis version key writes.
- Modify: `backend/src/fin_ops_platform/app/server.py`
  - Emit split metrics in `/health.api_performance`.
  - Use Redis version key before DB cache-version lookup for groups cache key.
  - Write groups cache after cold SQL read.
- Modify: `backend/src/fin_ops_platform/services/runtime_redis.py`
  - Add small string get/set helpers for version keys, keeping JSON helpers unchanged.
- Create: `backend/src/fin_ops_platform/postgres/migrations/0018_api_performance_read_model.sql`
  - Create `read_model.workbench_summary`.
  - Enable `pg_stat_statements` if privileges allow.
- Modify: `tests/test_api_performance_metrics.py`
- Modify: `tests/test_runtime_redis.py`
- Modify: `tests/test_postgres_migrations.py`
- Modify: `tests/test_workbench_sql_runtime.py`
- Modify: `docs/operations/monitoring.md`

## Tasks

### Task 1: PostgreSQL Pooling And Split Timing

- [ ] Write failing tests in `tests/test_api_performance_metrics.py` for `connection_acquire_ms` and `sql_execute_fetch_ms`.
- [ ] Write failing tests around `PostgresConnection` using fake pool/connection objects.
- [ ] Implement timing fields in `api_performance_metrics.py`.
- [ ] Implement lazy `psycopg_pool.ConnectionPool` in `postgres_connection.py`.
- [ ] Run focused tests.

### Task 2: Materialized Workbench Summary

- [ ] Add migration test expectations for `0018_api_performance_read_model.sql` and `read_model.workbench_summary`.
- [ ] Add repository tests showing `get_workbench_summary()` reads one materialized row when present.
- [ ] Add repository tests showing `save_workbench_read_models()` upserts summary payload.
- [ ] Implement migration and repository changes.
- [ ] Run migration and workbench SQL tests.

### Task 3: Groups Redis True Hot Cache

- [ ] Add Redis helper tests for string version get/set.
- [ ] Add API test proving Redis hit does not call `workbench_groups_cache_version()`.
- [ ] Implement version-key-first cache lookup and cold path cache population.
- [ ] Ensure no fallback correctness dependency on Redis.
- [ ] Run runtime Redis and workbench SQL tests.

### Task 4: pg_stat_statements And Docs

- [ ] Add migration SQL for `create extension if not exists pg_stat_statements`.
- [ ] Keep migration safe if extension creation is not permitted in a given environment by documenting privilege requirement.
- [ ] Update monitoring docs with new split metric fields and pg_stat_statements usage.
- [ ] Run full focused verification.
