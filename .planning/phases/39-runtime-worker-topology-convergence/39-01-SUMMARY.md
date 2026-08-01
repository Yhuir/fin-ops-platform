---
phase: 39-runtime-worker-topology-convergence
plan: "01"
status: complete
completed_at: 2026-08-01
release: main-a2d03430-20260801133923
git_commit: a2d034307da16a3c17d7ed0fb7b5620a90422f49
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

## 生产发布与验证

- `a2d034307da16a3c17d7ed0fb7b5620a90422f49` 已推送 `origin/main`，并通过 `scripts/with-production-admin-token.sh ./scripts/deploy-oa.sh` 发布为 `main-a2d03430-20260801133923`；上一版 `main-d18edd00-20260801072547` 保留为回滚锚点。
- pre/T+0/T+60/T+300 release gate 全部 PASS；6 个 required worker 全部 active/available，`required_worker_not_ready=0`、`unknown_worker_count=0`，两个保留 read model ready。
- PostgreSQL durable outbox/dirty scope、RabbitMQ pending/publishing/failed/dead-letter 均为 0；队列 T+300 稳定，page canonical audit 与 domain contract audit 通过，未触发回滚。
- `no-oa-bank-batch`、`search`、`search-secondary`、`search-tertiary`、`workbench-secondary` systemd unit 全部 `inactive/disabled`。
- 生产机内环认证 HTTP SLO：32 个核心 API × 20 次，640/640 成功，最慢 p95 `751.858ms`；当前月 no-OA canonical list p50/p95/p99 为 `893.811/983.787/1015.582ms`，p95 满足 `<1s` 首屏合同。
- 当前产品 bank-flow 未提交/已提交列表 p95 为 `64.097/32.779ms`；内部转账详情 p95 `52.295ms`，20/20 均为 HTTP 200。
- Workbench 读模型为 `fresh`；170 个 paired group 中 62 个来自 `bank_flow_rule_batch`，其中 35 个为内部转账，零空成员/非 paired 异常。抽样正式批次为 `submitted`、2 条流水且分类全部为 `internal_transfer`。
- 运行时健康：HTTP active/peak 为 `1/4`，拒绝、body rejection 和 DB backpressure 均为 0；PostgreSQL pool size/max/available/waiting 为 `4/10/3/0`。
- legacy `month=all` no-OA 跨全历史管理查询 p95 约 `2.59s`；它无当前前端消费者，不是首屏合同。本 Phase 不为已退役页面重建 cache/worker，并保留该显式上限记录。
