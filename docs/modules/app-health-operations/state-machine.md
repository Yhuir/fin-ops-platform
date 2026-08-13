# 系统状态状态机

> 修改系统状态、App Health、App Status、readiness 或 worker 状态前必须读取本文件。全局状态只能由后端 runtime facts 推导，不能由页面局部 loading 推导。

## 业务状态

### Overall

- `ok/green`：所有关键 domain ready/fresh，无 queued/running/attention job，无 critical dependency/worker/read model 问题。
- `busy/yellow`：存在 loading/refreshing/stale/missing readiness、queued/running job、dirty scope、outbox backlog、非阻断 dependency warning。
- `blocked/red`：session 不可用、critical read model failed/unavailable、required worker missing/mismatch/stale、critical dependency unavailable、runtime snapshot unavailable。
- `write_safety`：独立于 `overall.level` 的写操作安全闸门。`overall.level=blocked` 可以只表示读侧 freshness/domain 失败；只有 session/auth、runtime/DB、关键依赖或目标写模型不可用等写安全 blocker 才设置 `write_safety.blocks_mutations=true` 并派生 `overall.blocks_mutations=true`。

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
- `/api/app-health.app_status.runtime_summary` 是 App Status hover 的整体状态摘要：read models 统计 `fresh/refreshing/stale/missing/failed/unavailable/issue_count/scope_issue_count`，workers 统计 `required/ready/idle/working/stale/missing/mismatched/unavailable/issue_count`，queue 统计 `pending/processing/failed/backlog`。worker `working/running/processing` 表示正在工作，不计入 issue；warning、stale、missing、mismatch、unavailable 才计入 issue。
- readiness backfill 只能从真实 projection 计算；禁止把 missing 批量写成 fresh。

### Dashboard

- `/api/operations/app-health-dashboard` 是 admin-only 只读入口。
- payload 状态：当前 payload（可含局部 unknown warning）、`stale_after_refresh_error`、`unavailable`。
- 局部 inventory/runtime block 失败时返回本轮其它成功区块并只把失败区块标为 unknown，不能用上一份整页缓存冻结独立事实；只有 dashboard 整体构建抛出未处理异常时允许返回上一份 payload 并带 `dashboard_cache_stale_after_error` warning。权限失败和 PostgreSQL runtime 缺失不走缓存兜底。
- 导入历史不再以 `app.import_batches.status` 直接显示。`ImportLifecycleService` 聚合 batch/file/session/job 后输出 `awaiting_confirmation/queued/processing/succeeded/failed/discarded/withdrawn/inconsistent/unknown`；主页最新 5 条与 admin-only 分页抽屉共用该口径。
- `succeeded -> withdrawing -> withdrawn` 只发生在银行批次撤回写请求；按钮进入二次确认，提交期间禁止重复操作和关闭，成功后刷新历史，失败回到可重试并展示明确原因。

### System Audit

- `not_run`：尚未执行，不能显示绿色。
- `running`：一个 outer `REPEATABLE READ READ ONLY` transaction 正在执行 16 个子页面 proof 和 App Health database plane；不触发 refresh/repair。
- `internal_pass_external_unknown`：18 页已登记 App 内部合同在同一 snapshot 内通过，但外部 control evidence 缺失；`overall_status=pass`、`audit_status.external=unknown`、`end_to_end_source_truth=unproven` 同时成立。
- `internal_pass_external_pass`：内部 18 页通过，且银行/OA/发票/ETC 最新、未过期的 complete manifest 与当前 canonical exact set、关键字段和 controls 全部一致；只允许声明 `proven_as_of_external_evidence`，有效时间边界是各 evidence 的 observed/source snapshot 与当前 system snapshot。
- `external_fail`：任一最新 evidence revoked/expired、contract/coverage 非法，或存在 missing/extra/duplicate/field/control mismatch；即使内部 `overall_status=pass` 也必须保持 `end_to_end_source_truth=unproven`，不得回退旧 evidence。
- `issues_found`：任一子页 integrity/freshness/queue、dashboard inventory、manifest/status registry、required worker 或 current outbox 不一致；不得显示系统通过。
- `request_failed`：snapshot/SQL/runtime projection 不可执行，HTTP 返回 fail-closed error；不能用上一次绿色替代。
- Audit result 是不可变历史快照证据。系统页面下一次普通 dashboard refresh 会清除本地 Audit 绿色；后续写入不能沿用旧 `system_audit_id`。

## UI 状态

- loading：首次加载 dashboard 或 App Status provider 请求中；不能显示旧成功态为 fresh。
- empty：无 metrics 样本时显示 `--` 或 unknown，不等于 0。
- error：dashboard/API 请求失败显示错误；如果已有 dashboard payload，保留旧 payload 并提示 stale warning。
- stale/refreshing：来自后端 app_status/domain/readiness，不由当前页面局部 loading 推导。
- permission disabled/hidden：dashboard 仅 admin 可见；非 admin 不请求 dashboard API。App Status popover 的运维入口仅 admin 显示。
- 有界轮询：App Health snapshot 按固定间隔刷新，focus/online 时立即刷新；跨 tab BroadcastChannel 只传播后端 snapshot。旧 SSE/EventSource 路径不得恢复。

## Read Model / Worker 状态

- `fresh`：`workbench` 与 `workbench_relation` 具有
  `read_model.app_status_readiness` 和 current-effective queue 证明；其它 canonical 页面只依赖 PostgreSQL/runtime 健康证明。
- `missing`：registry 要求但没有 readiness 记录；busy/yellow。
- `refreshing`：dirty/outbox/worker 正在处理；busy/yellow。
- `stale`：source/schema/version 不匹配或 dirty 未完成；busy/yellow。
- `failed`：refresh 失败或 readiness failed；critical domain blocked/red。
- `unavailable`：runtime repository/readiness reader 不可用；blocked/red，不能空 green。
- current-effective blocker：`scopes[]`、dirty scope 和 outbox failed/dead-letter 只有在仍代表当前 scope 未收敛时才参与 overall/domain 判定。成本统计 legacy scope `all` / 裸 `YYYY-MM`、以及已被后续同 scope `done`、fresh readiness 或同 scope active dirty scope 覆盖的 outbox 失败，只能进入历史诊断或 repair 队列，不能把 canonical fresh/refreshing 页面拖成 blocked。同一 current-effective scope 如果旧 `failed` 已被新的 `pending`/`processing` 覆盖，当前状态是 `refreshing`，旧 `last_error` 不再作为当前阻断。
- historical diagnostics：`historical_read_model_scopes[]` 暴露历史失败、废弃 scope contract 和可审计修复对象；该字段不作为 fresh 证明，也不参与 `details`、`level` 或 `blocks_mutations` 推导。
- refresh 触发来源：各业务模块 lifecycle event、settings reset、read model miss/stale API enqueue、worker/backfill。stale scan 只能由显式启用的 `workbench-matching` worker 启动，不得在 API Application 初始化时运行。
- 失败恢复：通过对应 runbook、runtime queue ops、readiness backfill、worker restart/drain；App Health 只展示和定位，不直接执行 repair。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-08-01 | Readiness 与 worker topology 收敛为 `workbench`、`workbench_relation` 两个 read model 和 6 个 required worker；Search/no-OA projection 历史行退出 current-effective 状态 | App Status registry、runtime summary、部署门禁 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py`、`tests/test_runtime_worker_registry.py` |
| 2026-07-11 | App Health 成为 17 页 system Audit owner | 一个 outer snapshot 执行其余 16 页 proof；database/runtime/external 三个 evidence plane 分离，旧进项专项面板删除 | `tests/test_audit_app_health_system.py`、`tests/test_app_health_api.py`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/e2e/app-shell.spec.ts` |
| 2026-07-11 | 外部 evidence exact proof owner | 四域 immutable manifest 与 canonical facts 做 exact set/field/control equality；显式 page coverage，删除 free-text classifier | `tests/test_external_control_evidence_*.py`、`tests/test_audit_external_control_evidence.py`、`tests/test_audit_app_health_system.py` |
| - | 初始骨架 | 待补充 | - |
| 2026-07-27 | 恢复关联台 Workbench generation App Status 合同；read-model readiness 精确登记为 `workbench` 与三个共享模型，其它 canonical 页面按 PostgreSQL/runtime 健康判断 | App Status registry、runtime summary、前端状态类型 | `tests/test_app_health_service.py`、`tests/test_runtime_state_policy.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-20 | App Status 增加 runtime summary，并在 hover 与系统状态页展示 read model / worker / queue 整体状态 | 用户不用进入具体表格即可判断 read model 是否 fresh、worker 是否 active/working、queue 是否有 backlog | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service -v`；`cd web && npm test -- --run src/test/AppStatusApi.test.ts src/test/AppStatusIndicator.test.tsx src/test/AppHealthOperationsPage.test.tsx` |
| 2026-06-18 | 同一 read model scope 旧 failed 被新 pending/processing 覆盖时展示 refreshing，旧 last_error 只做历史诊断 | `RuntimeMonitoringRepository.app_status_runtime_snapshot()`、App Health / App Status current-effective read model 状态 | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service -v` |
| 2026-06-11 | 补齐 App Health / App Status 测试闭环状态机 | 将 overall/domain/job/runtime/dashboard/readiness 状态纳入统一维护边界 | `tests.test_app_health_api`、`tests.test_app_status_overview_service`、`tests.test_runtime_monitoring`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx` |
| 2026-06-12 | 引入 current-effective blocker 语义 | legacy 成本 scope 与已被后续成功覆盖的 outbox 失败不再污染当前 App Status；历史 scope 通过 `historical_read_model_scopes[]` 暴露 | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v` |
| 2026-06-13 | 拆分 read freshness 与 write safety | critical read model failed/unavailable 仍让 domain/overall blocked/red，但不再自动全局禁写；mutation gate 使用 `overall.write_safety.blocks_mutations`，runtime/dependency/session blocker 仍禁写 | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service -v`；`cd web && npm test -- --run src/test/AppStatusApi.test.ts src/test/AppHealthStatusContext.test.tsx` |
