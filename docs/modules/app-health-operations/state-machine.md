# 系统状态状态机

> 修改系统状态、App Health、App Status、runtime readiness 或 worker 状态前必须读取本文件。全局状态只能由后端 runtime facts 推导，不能由页面局部 loading 推导。

## 业务状态

### Overall

- `ok/green`：所有关键 domain runtime-ready，无 queued/running/attention job，无 critical dependency/worker/runtime 问题。
- `busy/yellow`：存在 queued/running job、outbox backlog、非阻断 dependency warning 或 required worker stale。
- `blocked/red`：session 不可用、required worker missing/mismatch、critical dependency unavailable、runtime snapshot unavailable。
- `write_safety`：独立于 `overall.level` 的写操作安全闸门。只有 session/auth、runtime/DB、关键依赖或目标写模型不可用等写安全 blocker 才设置 `write_safety.blocks_mutations=true` 并派生 `overall.blocks_mutations=true`。旧页面同步诊断不是全局写闸门。

### Domain

- `ready`：domain 依赖的 worker/dependency/job 无阻断状态。
- `busy`：真实 background job、outbox backlog 或非阻断 runtime dependency warning 仍在处理中。
- `blocked`：session、runtime repository、required worker、critical dependency 或目标写安全前置条件不可用。
- Legacy projection missing/stale/schema mismatch/source mismatch/failed/unavailable 只作为删除期诊断清单，不能给 App Status domain 染色，也不能证明当前页面状态。
- 页面 legacy projection、cost statistics shard 或 historical scope 问题不再通过 App Status domain 染色；具体页面通过自身 direct API loading/error/empty 状态处理。

### Background jobs

- `queued/running`：overall/domain busy，payload 必须包含 job id、type、status、label/message/progress、affected domains/scopes/months。
- `failed/partial_success` 未确认：attention，进入 App Health / App Status 可见。
- `acknowledged/succeeded`：不再作为 active attention job，近期成功窗口之外应移除。

### Runtime infrastructure

- outbox pending/publishing/failed、RabbitMQ publish/queue/DLQ、worker heartbeat lag、worker kind/event mismatch 都是 runtime facts；legacy page read-model dirty scope/readiness 不再进入健康状态机。
- worker `missing` / `stale` / `mismatched` 由 registry 和 heartbeat 推导，不由 systemd active 推导。
- `/api/app-health.app_status.runtime_summary` 是 App Status hover 的整体状态摘要：workers 统计 `required/ready/idle/working/stale/missing/mismatched/unavailable/issue_count`，queue 统计 `pending/processing/failed/backlog`。该摘要不再包含 `read_models`。worker `working/running/processing` 表示正在工作，不计入 issue；warning、stale、missing、mismatch、unavailable 才计入 issue。
- readiness backfill 已删除；禁止把 missing 批量写成 fresh。

### Dashboard

- `/api/operations/app-health-dashboard` 是 admin-only 只读入口。
- payload 状态：`current`、`stale_after_refetch_error`、`unavailable`。
- 缓存重新读取失败允许返回上一份 payload 并带 warning；权限失败和 PostgreSQL runtime 缺失不走缓存兜底。

## UI 状态

- loading：首次加载 dashboard 或 App Status provider 请求中；不能把旧成功态显示为 current/healthy。
- empty：无 metrics 样本时显示 `--` 或 unknown，不等于 0。
- error：dashboard/API 请求失败显示错误；如果已有 dashboard payload，保留旧 payload 并提示 stale warning。
- backend processing：来自后端 app_status/domain/runtime facts，不由当前页面局部 loading 推导。
- permission disabled/hidden：dashboard 仅 admin 可见；非 admin 不请求 dashboard API。App Status popover 的运维入口仅 admin 显示。
- SSE/轮询：SSE snapshot/heartbeat 失败时可回退轮询；跨 tab BroadcastChannel 同步只传播后端 snapshot。

## Legacy Diagnostics / Runtime Worker 状态

- Legacy read model freshness 已从 App Health / App Status 状态机移除；下列状态只作为运维专项诊断或历史口径，不再作为 App Status domain/runtime payload 合同字段。
- `missing`：legacy registry 记录缺失；仅诊断。
- `refreshing`：legacy read-model 状态仅诊断；真实处理中状态来自 outbox/worker runtime facts。
- `stale`：source/schema/version 不匹配；legacy read-model 状态仅诊断。
- `failed`：legacy refresh 失败；legacy read-model 状态仅诊断。
- `unavailable`：legacy diagnostics reader 不可用时不再染色 App Status；runtime repository 不可用仍 blocked/red，不能空 green。
- current-effective blocker：outbox failed/dead-letter 只有在仍代表当前 scope 未收敛时才参与 overall/domain 判定。成本统计 legacy scope `all` / 裸 `YYYY-MM`、以及已被后续同 scope `done` 覆盖的 outbox 失败，只能进入历史诊断或 audit 队列，不能把 canonical direct 页面拖成 blocked。同一 current-effective scope 如果旧 `failed` 已被新的 `pending`/`processing` 覆盖，当前状态是 runtime processing，旧 `last_error` 不再作为当前阻断。
- historical diagnostics：`historical_read_model_scopes[]` 不再由 App Status domain payload 暴露。历史失败、废弃 scope contract 和可审计修复对象应通过运维专项工具或 legacy 页面诊断处理。
- runtime 触发来源：各业务模块 lifecycle event、settings reset、真实 worker/outbox。`startup_stale_scan` 默认关闭；启用时只标记 workbench matching rescan diagnostics，不应重建用户可见页面 payload。
- 失败恢复：通过对应 runbook、runtime queue ops、worker restart/queue drain；App Health 只展示和定位，不直接执行修复。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-28 | Runtime health/App Status 删除 read-model readiness 与 dirty-scope 输入 | `/health`、`/health/ready`、Prometheus 和 App Status runtime snapshot 不再输出或读取 `dirty_scopes*`、`stale_dirty_scope_count`、`job.read_model_dirty_scopes` 或 `read_model.app_status_readiness`；current blocker 只由 outbox、worker、RabbitMQ、failed jobs/API metrics 推导 | `PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_monitoring.py tests/test_app_status_overview_service.py tests/test_prometheus_metrics.py tests/test_health_ready_payload_probe.py tests/test_runtime_sync_closure_gate.py tests/test_app_health_api.py tests/test_app.py tests/test_app_postgres_mode.py -q --tb=short` |
| 2026-06-27 | App Health alert service 删除 `workbench_read_model` 输入依赖 | `AppHealthAlertService` 只按 OA runtime diagnostics、dependency、session 和真实 background job 生成 alert；不再从已删除的 page read-model payload 生成 Workbench rebuild alert | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_health_alert_service tests.test_app_health_api tests.test_app_status_overview_service -v` |
| 2026-06-27 | App Health / App Status 移除页面 read-model readiness/status 面 | `AppHealthService` 不再返回 `workbench_read_model` / `workbench_relation_read_model`；`AppStatusOverviewService` 不再接收 `read_model_statuses`，domain payload/runtime summary 不再包含 read-model fields | `PYTHONPATH=backend/src python3 -m pytest tests/test_app_status_overview_service.py tests/test_app_health_api.py -q` |
| - | 初始骨架 | 待补充 | - |
| 2026-06-21 | current-effective outbox 过滤后续同 scope 成功/重试，Workbench generation consistency failure 在 active diagnostic 期间展示 runtime processing 而不是 blocked | `RuntimeMonitoringRepository.app_status_runtime_snapshot()`、health summary/outbox attention SQL、Workbench historical diagnostic 到 App Status 的旧状态口径 | 历史测试已由 2026-06-28 outbox-only runtime health contract 覆盖 |
| 2026-06-20 | App Status 增加 runtime summary，并在 hover 与系统状态页展示 worker / queue 整体状态 | 用户不用进入具体表格即可判断 worker 是否 active/working、queue 是否有 backlog | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service -v`；`cd web && npm test -- --run src/test/AppStatusApi.test.ts src/test/AppStatusIndicator.test.tsx src/test/AppHealthOperationsPage.test.tsx` |
| 2026-06-18 | 同一 read model scope 旧 failed 被新 pending/processing 覆盖时展示 runtime processing，旧 last_error 只做历史诊断 | `RuntimeMonitoringRepository.app_status_runtime_snapshot()`、App Health / App Status current-effective historical diagnostic 状态 | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service -v` |
| 2026-06-11 | 补齐 App Health / App Status 测试闭环状态机 | 将 overall/domain/job/runtime/dashboard/readiness 状态纳入统一维护边界 | `tests.test_app_health_api`、`tests.test_app_status_overview_service`、`tests.test_runtime_monitoring`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx` |
| 2026-06-12 | 引入 current-effective blocker 语义 | legacy 成本 scope 与已被后续成功覆盖的 outbox 失败不再污染当前 App Status；历史 scope 通过 `historical_read_model_scopes[]` 暴露 | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v` |
| 2026-06-13 | 拆分 read-path diagnostics 与 write safety | 历史 read-model failed/unavailable 已不再让 domain/overall blocked/red；mutation gate 使用 `overall.write_safety.blocks_mutations`，runtime/dependency/session blocker 仍禁写 | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service -v`；`cd web && npm test -- --run src/test/AppStatusApi.test.ts src/test/AppHealthStatusContext.test.tsx` |
