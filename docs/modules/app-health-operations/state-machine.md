# 系统状态状态机

> 修改系统状态、App Health、App Status、readiness 或 worker 状态前必须读取本文件。全局状态只能由后端 runtime facts 推导，不能由页面局部 loading 推导。

## 业务状态

### Overall

- `ok/green`：所有关键 domain ready/fresh，无 queued/running/attention job，无 critical dependency/worker/read model 问题。
- `busy/yellow`：存在 loading/refreshing/stale/missing readiness、queued/running job、dirty scope、outbox backlog、非阻断 dependency warning。
- `blocked/red`：session 不可用、critical read model failed/unavailable、required worker missing/mismatch/stale、critical dependency unavailable、runtime snapshot unavailable。

### Domain

- `ready/fresh`：domain 依赖的 read model 有 readiness 证明，worker/dependency/job 无阻断状态。
- `missing`：registry 要求的 readiness 记录缺失；必须 busy/yellow，不能 green。
- `refreshing/stale/schema_mismatch/source_mismatch`：busy/yellow，等待 worker 收敛或重建。
- `failed/unavailable`：critical read model 或 runtime source 失败；blocked/red。
- cost statistics 特例：月份 shard failed/unavailable 是局部风险；父 scope failed/unavailable 才阻断父 domain。

### Background jobs

- `queued/running`：overall/domain busy，payload 必须包含 job id、type、status、label/message/progress、affected domains/scopes/months。
- `failed/partial_success` 未确认：attention，进入 App Health / App Status 可见。
- `acknowledged/succeeded`：不再作为 active attention job，近期成功窗口之外应移除。

### Runtime infrastructure

- outbox pending/publishing/failed、dirty scopes pending/processing/failed、RabbitMQ publish/queue/DLQ、worker heartbeat lag、worker kind/event mismatch 都是 runtime facts。
- worker `missing` / `stale` / `mismatched` 由 registry 和 heartbeat 推导，不由 systemd active 推导。
- readiness backfill 只能从真实 projection 计算；禁止把 missing 批量写成 fresh。

### Dashboard

- `/api/operations/app-health-dashboard` 是 admin-only 只读入口。
- payload 状态：`fresh`、`stale_after_refresh_error`、`unavailable`。
- 缓存刷新失败允许返回上一份 payload 并带 warning；权限失败和 PostgreSQL runtime 缺失不走缓存兜底。

## UI 状态

- loading：首次加载 dashboard 或 App Status provider 请求中；不能显示旧成功态为 fresh。
- empty：无 metrics 样本时显示 `--` 或 unknown，不等于 0。
- error：dashboard/API 请求失败显示错误；如果已有 dashboard payload，保留旧 payload 并提示 stale warning。
- stale/refreshing：来自后端 app_status/domain/readiness，不由当前页面局部 loading 推导。
- permission disabled/hidden：dashboard 仅 admin 可见；非 admin 不请求 dashboard API。App Status popover 的运维入口仅 admin 显示。
- SSE/轮询：SSE snapshot/heartbeat 失败时可回退轮询；跨 tab BroadcastChannel 同步只传播后端 snapshot。

## Read Model / Worker 状态

- `fresh`：有 `read_model.app_status_readiness` 或 Workbench active generation 等价证明。
- `missing`：registry 要求但没有 readiness 记录；busy/yellow。
- `refreshing`：dirty/outbox/worker 正在处理；busy/yellow。
- `stale`：source/schema/version 不匹配或 dirty 未完成；busy/yellow。
- `failed`：refresh 失败或 readiness failed；critical domain blocked/red。
- `unavailable`：runtime repository/readiness reader 不可用；blocked/red，不能空 green。
- current-effective blocker：`scopes[]`、dirty scope 和 outbox failed/dead-letter 只有在仍代表当前 scope 未收敛时才参与 overall/domain 判定。成本统计 legacy scope `all` / 裸 `YYYY-MM`、以及已被后续同 scope `done` 或 fresh readiness 覆盖的 outbox 失败，只能进入历史诊断或 repair 队列，不能把 canonical fresh 页面拖成 busy/blocked。
- historical diagnostics：`historical_read_model_scopes[]` 暴露历史失败、废弃 scope contract 和可审计修复对象；该字段不作为 fresh 证明，也不参与 `details`、`level` 或 `blocks_mutations` 推导。
- refresh 触发来源：各业务模块 lifecycle event、settings reset、read model miss/stale API enqueue、worker/backfill。`startup_stale_scan` 只标记 workbench matching dirty scopes，不应直接刷新用户可见 read model。
- 失败恢复：通过对应 runbook、runtime queue ops、readiness backfill、worker restart/drain；App Health 只展示和定位，不直接执行 repair。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| - | 初始骨架 | 待补充 | - |
| 2026-06-11 | 补齐 App Health / App Status 测试闭环状态机 | 将 overall/domain/job/runtime/dashboard/readiness 状态纳入统一维护边界 | `tests.test_app_health_api`、`tests.test_app_status_overview_service`、`tests.test_runtime_monitoring`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx` |
| 2026-06-12 | 引入 current-effective blocker 语义 | legacy 成本 scope 与已被后续成功覆盖的 outbox 失败不再污染当前 App Status；历史 scope 通过 `historical_read_model_scopes[]` 暴露 | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v` |
