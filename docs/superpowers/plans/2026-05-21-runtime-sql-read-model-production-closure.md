# Runtime SQL Read Model Production Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 runtime SQL/read-model 收敛的最终生产闭环验证与剩余 legacy 边界收口，确认真实 PostgreSQL/Redis/MinIO/OA/worker/performance/snapshot fallback 全部达到 cutover 标准。

**Architecture:** 生产 API/worker 只能依赖 PostgreSQL facts/read model、PostgreSQL durable queue、Redis 短 TTL cache/wakeup、S3-compatible object storage 和显式轻量配置。旧 snapshot、Mongo、GridFS 和旧 builder 只允许在 migration/shadow/audit/rollback/local-test 边界出现，并由 static guard 与真实 smoke 双重验证。

**Tech Stack:** Python stdlib CLI、PostgreSQL migrations/repositories、Redis CLI/helper、S3-compatible object storage via boto3, runtime worker, unittest, repository scripts.

---

## /goal Prompt

```text
/goal 完成运行时 SQL Read Model 收敛最终生产闭环，覆盖真实基础设施、worker、对象存储迁移、性能检查、剩余 snapshot fallback 分类清理和旧 builder 生产边界验证。

上下文：
- 仓库：/Users/yu/Desktop/fin-ops-platform
- 设计规格：docs/superpowers/specs/2026-05-21-runtime-sql-read-model-convergence-design.md
- 当前本地代码级 guard 已通过，但仍需完成：
  1. 真实 PostgreSQL/Redis/MinIO/OA 环境 integration smoke。
  2. 真实 worker claim/complete/retry/backfill 流程验证。
  3. MinIO/S3 对象迁移 checksum、orphan cleanup、GridFS backfill 生产级实跑验证。
  4. 大样本启动时间、内存、workbench/cost/tax 查询性能验证。
  5. PostgresStateStore 剩余 _load_snapshot(...) 兼容读取点逐域分类、清理或登记 legacy-only。
  6. 旧 builder 代码仍存在时，必须证明 production PostgreSQL API/worker 不可达，且只用于 legacy/local/test/对账工具。

目标：
1. 增加一个最终 closure harness，能一键检查 PostgreSQL migration、Redis ping、MinIO/S3 put/get/delete、worker --check、worker claim/complete/retry、file object backfill/verify/cleanup、read model API miss/stale 行为和性能查询。
2. 在缺少真实基础设施时，harness 必须 fail/skip 得清楚，不能误报完成；在 `--require-real-infra` 下任何真实 infra 缺失都返回非零。
3. 补充 static guard：生产路径禁止 `state:full_state`、已迁移 read model snapshot fallback、GridFS fallback、direct OA Mongo fallback 和旧 workbench/cost/tax 同步 builder。
4. 给 `PostgresStateStore._load_snapshot(...)` 剩余域建立分类表：formalized、legacy-runtime-temporary、migration-shadow-test-only、cleanup-candidate；除 migration/shadow/test-only 外，生产可达项必须有退出条件。
5. 跑真实或本机可用的验证：如果没有真实 PostgreSQL/Redis/MinIO/OA，则执行 harness 并记录阻塞项；如果有环境变量，则必须实际跑到 PASS。
6. 更新 docs/dev、docs/operations 和最终报告，说明如何复现最终验证。

串行任务：
1. 读取 README、backend/README、docs/dev/runtime-bootstrap.md、docs/architecture/persistence-and-read-models.md、docs/operations/object-storage-minio.md、现有 runtime tests 和 PostgresStateStore。
2. 先写 closure harness tests：无 infra 时报告 skipped/blocking；require-real-infra 时缺失 infra 返回失败；static guard 能识别禁止模式。
3. 实现 `fin_ops_platform.tools.run_runtime_convergence_closure`：
   - PostgreSQL：检查 DB URL、migration status、runtime integration test、queue claim/complete/retry smoke。
   - Redis：ping 和短 TTL set/get/delete。
   - MinIO/S3：bucket put/get/delete checksum smoke；强制模式要求 `FIN_OPS_APP_MONGO_*` 可达，并执行 legacy GridFS backfill/verify/orphan cleanup worker smoke。
   - Worker：`python -m fin_ops_platform.app.worker --check` 和可选 `--max-iterations 1` claim smoke。
   - Performance：记录 API bootstrap time、read model query `EXPLAIN` 或 repository query timing。
   - Static：扫描生产代码旧 fallback 与 builder 边界。
4. 分类并文档化 `PostgresStateStore._load_snapshot(...)` 剩余域；能清理的直接清理，不能清理的登记退出条件。
5. 运行 targeted tests、完整 unittest、closure harness。
6. 输出最终完成报告：PASS、SKIPPED、BLOCKED 必须区分；只有 require-real-infra 全 PASS 时才能宣布整体生产闭环完成。

可并行任务：
- A: closure harness 和测试。
- B: snapshot fallback 分类/guard。
- C: real infra smoke 文档和脚本。
- D: 性能/worker/object storage 验证。

完成门槛：
- `python3 -m fin_ops_platform.tools.run_runtime_convergence_closure --require-real-infra --json` 在真实 PostgreSQL/Redis/MinIO/OA 环境下返回 0。
- worker 至少完成一次真实 PostgreSQL claim/complete/retry/backfill 验证。
- MinIO/S3 完成 put/get/delete checksum、GridFS backfill/verify/cleanup 验证。
- workbench/cost/tax 查询有大样本或代表性 `EXPLAIN`/timing 记录。
- `PostgresStateStore._load_snapshot(...)` 剩余项均有分类、退出条件和 guard。
- 旧 builder 仅在 legacy/local/test/reconciliation 可达，production PostgreSQL API/worker 不可达。
- 完整 unittest 通过，真实 infra 缺失时不得宣称全部完成。
```

## Execution Notes

- 本计划要求真实外部依赖。没有 `FIN_OPS_TEST_DATABASE_URL` / Redis / MinIO / App Mongo/GridFS source / OA source 时，最多完成代码级 harness 与本地 guard，不能宣布生产闭环完成。
- Docker 可作为本地真实 infra 的候选，但 Docker daemon 必须已运行；当前机器若 Docker daemon 未启动，需要先由操作者启动 Docker Desktop 或提供现有服务 URL。
