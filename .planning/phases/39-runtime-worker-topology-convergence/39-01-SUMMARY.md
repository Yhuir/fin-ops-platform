---
phase: 39-runtime-worker-topology-convergence
plan: "01"
status: local-complete-production-pending
completed_at: 2026-08-01
---

# Phase 39 实施摘要

## 结果

- required worker 从 11 个收敛为 6 个：`oa-sync`、`workbench-matching`、`workbench`、`workbench-relation`、`import`、`settings-maintenance`。
- read-model registry/manifest 从 4 项收敛为 2 项：`workbench`、`workbench_relation`。
- 删除 Search API、service、projection、repository、freshness、refresh producer/worker、三个 runtime instance、前端 mock、测试与模块文档。
- 删除 no-OA projection、repository、freshness、refresh producer/worker、repair/lifecycle 工具；保留 canonical batch facts、submit/withdraw、审计、幂等、事务和 Workbench internal-transfer relation owner。
- `GET /api/no-oa-bank-batches` 复用现有 canonical refresh/list service，在请求内按 month/all scope 更新并分页返回，不再输出 read-model/queue/freshness 元数据。
- 删除 `workbench-secondary`；部署控制继续复用 registry 驱动的 unknown unit stop/disable/reset-failed 边界。
- 未增加依赖、框架、worker 类型、cache、兼容 route、fallback 或新持久化层。

## 本地验证

- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `bash scripts/verify.sh backend`：3774 tests 通过，49 个真实外部基础设施/本机样本用例按条件跳过。
- `bash scripts/verify.sh frontend`：73 files / 901 tests 通过；TypeScript 与 Vite production build 通过。
- `bash scripts/verify.sh e2e`：Chromium 164/164 通过。
- `bash scripts/verify.sh infra-smoke`：71 tests 通过，25 个真实 PostgreSQL/RabbitMQ/auth gate 按条件跳过；这些由生产部署后验证补齐。
- whole-repo active runtime scan：生产源码、前端 mock 中 Search/no-OA retired API/class/event 为零；测试中只保留明确负向退休守卫。
- `git diff --check`：通过。

## 待发布验证

- 推送 `origin/main` 并通过 `./scripts/deploy-oa.sh` 发布。
- 验证 active release、精确 6 worker、旧 unit disabled/inactive、RabbitMQ/PostgreSQL durable queue drain、两个 read model ready。
- 验证 no-OA canonical list/detail 与 Workbench internal-transfer 只读链；采集暖读 p50/p95/p99/max、HTTP error 和 runtime health。
- 完成 T+0/T+60/T+300 release gate 后将结果写入 `39-VERIFICATION.md`。
