# Read Model 状态机

> 修改 legacy read model、worker、runtime queue、App Status 或 direct API 读路径前必须读取本文件。目标架构以 `../../architecture/direct-api-read-architecture.md` 为准：页面读取走 direct API，不再通过 page read model freshness/dirty/readiness 状态机。

## 当前状态

本模块现在是 `legacy-guard-only`。

- Active page read-model manifest：空。
- App Status page read-model registry：空。
- `ReadModelRefreshGateway`：已删除。
- `RuntimeQueueRepository.enqueue_read_model_refresh(...)`、`enqueue_read_model_refresh_in_transaction(...)`、`complete_read_model_refresh(...)` 和 `read_model_refresh_is_*`：已删除。
- `job.read_model_dirty_scopes` 与 `read_model.app_status_readiness`：已由 `0082_drop_legacy_read_model_runtime_state.sql` 删除。
- 页面 API：不得返回 `read_model_status`、`read_model_stale_reasons`、`refresh_enqueued` 或 operation barrier target fields。

## 允许状态

| 状态 | 含义 | 允许行为 |
| --- | --- | --- |
| `direct_api` | 页面 route/service/repository 直接读取 canonical facts、OA SQL projection 或 import facts | 返回 DTO、loading/empty/error/refetch 由页面和业务 API 自己维护 |
| `legacy_guard` | 旧 read model 只作为删除清单、负向 guard 或迁移审计对象存在 | 保留删除证明、负向测试、历史迁移记录 |
| `real_background_task` | 导入、OA 同步、文件迁移、设置重置、Workbench matching 等真实后台任务 | 可使用 `job.outbox_events`、worker heartbeat、background job facts 或 `job.workbench_matching_dirty_scopes` |

## 禁止状态

- 新增 page read model、freshness gate、readiness proof、dirty scope、refresh worker 或 force-refresh 入口。
- 把 Redis、RabbitMQ、frontend domain event、worker wakeup 或 legacy projection 当作页面可读证明。
- 业务 service 直接 SQL 写 page read-model dirty/readiness/outbox 表。
- 生产页面缺 direct SQL/repository/view 时回退到 live scan、memory snapshot 或旧 QueryService 并伪装 fresh。
- 用 `read_model_status=fresh/refreshing/stale/missing/failed/unavailable` 作为页面 response contract。
- 恢复 operation barrier endpoint/service，让页面等待 page refresh scope 后再释放操作。

## 写后闭环

- Mutation API 写 canonical facts/audit 后，返回 status、affected ids/months、version、job 或 committed projection。
- 前端写成功后直接 refetch 目标 direct API，或应用后端返回的 committed projection。
- 真实后台任务的完成证明属于 worker/job/outbox 事实，不替代页面 direct API 可读性。

## 保留例外

- `job.outbox_events` 仍是真实后台任务 transport/fact，不是 page read-model freshness proof。
- `job.workbench_matching_dirty_scopes` 仍是 Workbench matching 当前后台队列，不是 legacy page dirty scope。
- `read_model.workbench_candidate_matches` / `read_model.workbench_reconciliation_decisions` 仍可作为 matching/decision facts；不得因表名包含 `read_model` 直接删除。

## 恢复与清理

- 旧 page read-model 残留只能进入删除 wave 或迁移审计；不得通过 repair/check/apply 工具伪造 fresh。
- 生产真实库不得热改 runtime 表来清除页面 read-model blocker。
- 如发现 current 代码或文档仍要求 page read-model freshness/dirty/readiness，优先删除该要求；确有真实后台任务需求时，归入对应 worker/job 模块。

## 变更记录

| 日期 | 变更 | 验证 |
| --- | --- | --- |
| 2026-06-28 | 状态机改为 guard-only；删除旧 fresh/missing/queued/force-refresh 正向状态合同 | `rg` 当前文档残留扫描、`git diff --check` |
