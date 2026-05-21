# Runtime SQL Read Model Final Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收口 runtime SQL/read-model cutover，清理生产可达的旧 workbench 同步构建、`state:*` JSON full snapshot 和 PostgreSQL snapshot fallback 残留。

**Architecture:** 生产 API/worker 主路径只读 PostgreSQL facts/read model，并通过 durable queue 标记 miss/stale refresh；旧 snapshot、Mongo、GridFS 只保留在 legacy bootstrap、migration、shadow、audit 和 rollback 工具边界。先用 guard test 锁定禁止路径，再逐项把剩余兼容分支改成 SQL/read-model 或明确 legacy-only。

**Tech Stack:** Python stdlib HTTP app、PostgreSQL repositories、runtime worker/queue、Redis helper、MinIO/S3 object storage abstraction、unittest/pytest、repository static guard tests.

---

## /goal Prompt

```text
/goal 收口 runtime SQL/read-model 收敛 hardening，清理生产路径中剩余旧 snapshot/Mongo/GridFS fallback，并完成真实基础设施验证边界。

上下文：
- 仓库：/Users/yu/Desktop/fin-ops-platform
- 设计规格：docs/superpowers/specs/2026-05-21-runtime-sql-read-model-convergence-design.md
- 当前已完成大部分 Module 1-11 框架，但代码搜索仍发现：
  - app/server.py 中仍有 _build_raw_workbench_payload、_get_or_build_workbench_read_model、_build_api_workbench_payload 生产可达 fallback。
  - app/server.py 中仍有 _persist_state() 汇总保存路径。
  - postgres_state_store.py 中仍有部分 _load_snapshot(...) runtime fallback。
  - 真实 PostgreSQL/Redis/MinIO/OA integration smoke 和性能检查尚未完整执行。

目标：
1. /api/workbench、/api/cost-statistics、/api/tax-offset 等已迁移生产 API 在 SQL/read model miss/stale 时只 enqueue refresh 并返回明确状态，不同步 rebuild 大 payload。
2. 生产 bootstrap / request / worker 主路径不写入或读取 state:full_state、state:workbench_*、cost/tax read model snapshot fallback。
3. PostgresStateStore 中剩余 _load_snapshot fallback 按 domain 分类：已迁移 read model 直接删除 fallback；尚未结构化迁移的 migration/shadow/test 场景必须显式标注，不可被 production API 当作事实源。
4. _persist_state() 不再让 PostgreSQL production 写 state:full_state；生产写路径用 domain repository/save_*、dirty scope/outbox、audit。
5. 增强 guard test/static check，阻止生产代码重新引入 StateStore.load、state:full_state、state:workbench_*、GridFS fallback、direct OA Mongo fallback。
6. 用可用环境运行 unit/pytest/API/worker smoke；若缺少真实 PostgreSQL/Redis/MinIO/OA，明确记录未运行项和替代验证。

串行任务：
1. 搜索并分类 server.py、postgres_state_store.py、worker.py、tools/、tests/、docs 中的旧 fallback 调用点。
2. 先写失败的 guard test，覆盖 production API miss 不调用旧 builders、Postgres read model loader 不读 runtime snapshot、Postgres save 不写 state:full_state。
3. 修改 app/server.py：production PostgreSQL runtime 缺少 SQL repository 或 SQL miss 时不得落回旧同步 builder；legacy/local test path 保持兼容。
4. 修改 postgres_state_store.py：已迁移 workbench/cost/tax read model loader 不读取 runtime snapshot fallback；save(payload) 不再写 state:full_state，除非显式 legacy/shadow 工具路径另行实现。
5. 修复 turnover_ledger_extras fallback persist 的 legacy reason 或改成正式 save_* 路径，避免生产 reason guard 隐患。
6. 更新 docs/dev/runtime-bootstrap.md、docs/architecture/persistence-and-read-models.md、docs/operations/monitoring.md，写清楚最终收口边界和剩余未迁移 domain。
7. 运行 tests/test_runtime_bootstrap.py、tests/test_workbench_sql_runtime.py、tests/test_cost_statistics_sql_runtime.py、tests/test_tax_offset_sql_runtime.py、tests/test_postgres_state_store.py、worker/API smoke；尽量运行完整 unittest。

可并行任务：
- A: server.py API/read model fallback 清理和相关 API tests。
- B: postgres_state_store.py snapshot fallback 分类清理和 repository tests。
- C: guard/static check 增强。
- D: docs/operations cutover、rollback、verification 更新。

完成门槛：
- 生产 PostgreSQL bootstrap 不加载 full_state。
- 已迁移 read model 的 production API miss 不同步 rebuild，不读取 state:* fallback。
- PostgresStateStore.save() 不再写 state:full_state 作为生产事实源。
- GridFS/Mongo/OA direct fallback 只存在 migration、shadow、audit、rollback 或显式 worker sync 边界。
- Guard test 能阻止新增生产旧 fallback。
- 可用测试通过；缺失真实基础设施时列出未运行的 integration/performance 验证。
```

## Task 1: Static Classification and Guards

**Files:**
- Modify: `tests/test_runtime_bootstrap.py`
- Modify: `tests/test_postgres_state_store.py`

- [ ] Add guard tests for production API fallback patterns.
- [ ] Add repository tests proving migrated read model loaders ignore `state:*` fallback.
- [ ] Add repository test proving `PostgresStateStore.save()` does not write `state:full_state`.
- [ ] Run targeted tests and confirm failures before implementation.

## Task 2: Application Production Fallback Boundary

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`

- [ ] Add a small helper that identifies production PostgreSQL runtime.
- [ ] Make `/api/workbench` return refresh/unavailable status instead of `_build_api_workbench_payload()` when SQL repository is missing in production PostgreSQL runtime.
- [ ] Keep local pickle and explicit legacy bootstrap behavior unchanged for existing tests/tools.
- [ ] Fix `turnover_ledger_extras` legacy fallback reason or remove fallback by requiring `save_turnover_ledger_extras`.

## Task 3: PostgreSQL Store Snapshot Fallback Hardening

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`

- [ ] Remove runtime snapshot fallback from migrated read model loaders: workbench, candidate matches, cost statistics, tax offset.
- [ ] Keep targeted formal-table save/load compatibility for domains not yet fully moved, but avoid `state:full_state`.
- [ ] Stop writing `state:full_state` from generic `save(payload)`.

## Task 4: Documentation

**Files:**
- Modify: `docs/dev/runtime-bootstrap.md`
- Modify: `docs/architecture/persistence-and-read-models.md`
- Modify: `docs/operations/monitoring.md`

- [ ] Document final hardening boundary.
- [ ] Document accepted legacy-only surfaces.
- [ ] Document required real infrastructure validation commands and known environment prerequisites.

## Task 5: Verification

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap tests.test_postgres_state_store tests.test_workbench_sql_runtime tests.test_cost_statistics_sql_runtime tests.test_tax_offset_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --once --database-url postgresql://invalid/fin_ops --no-redis
```

Expected:
- Targeted unit tests pass.
- Full unittest passes or any failures are unrelated and documented.
- Worker smoke either exits cleanly when configured with a fake/dummy path or reports expected database connectivity failure without importing API in-process thread.
