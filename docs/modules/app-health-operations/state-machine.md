# 系统状态状态机

> 修改系统状态、App Health、App Status 或 worker 状态前必须读取本文件。全局状态只能由后端 runtime facts 推导，不能由页面局部 loading 推导。

## 业务状态

### Overall

- `ok/green`：所有关键 domain ready，无 queued/running/attention job，无 critical dependency/worker/outbox 问题。
- `busy/yellow`：存在 queued/running job、outbox backlog、worker stale 或非阻断 dependency warning。
- `blocked/red`：session 不可用、required worker missing/mismatch/unavailable、critical dependency unavailable 或 runtime snapshot unavailable。
- `write_safety`：独立于 `overall.level` 的写操作安全闸门。只有 session/auth、runtime/DB、关键依赖或目标 command precondition 不可用时，才设置 `write_safety.blocks_mutations=true` 并派生 `overall.blocks_mutations=true`。

### Domain

- `ready`：domain 的 required worker、dependency、job 和 outbox 无阻断状态。
- `busy`：domain 有 queued/running task、worker stale 或 outbox backlog。
- `blocked`：critical domain 的 required worker、dependency 或 runtime source 不可用。

### Background jobs

- `queued/running`：overall/domain busy，payload 必须包含 job id、type、status、label/message/progress、affected domains/scopes/months。
- `failed/partial_success` 未确认：attention，进入 App Health / App Status 可见。
- `acknowledged/succeeded`：不再作为 active attention job，近期成功窗口之外应移除。

### Runtime infrastructure

- outbox pending/processing/failed/dead-lettered、领域队列状态、worker heartbeat lag、worker kind/event mismatch 都是 runtime facts。
- worker `missing` / `stale` / `mismatched` 由 registry 和 heartbeat 推导，不由 systemd active 推导。
- `/api/app-health.app_status.runtime_summary` 是 App Status hover 的整体状态摘要：workers 统计 `required/ready/idle/working/stale/missing/mismatched/unavailable/issue_count`，queue 统计 `pending/processing/failed/backlog`。worker `working/running/processing` 表示正在工作，不计入 issue；warning、stale、missing、mismatch、unavailable 才计入 issue。

### Dashboard

- `/api/operations/app-health-dashboard` 是 admin-only 只读入口。
- payload 状态：当前 payload（可含局部 unknown warning）、`stale_after_refresh_error`、`unavailable`。
- 局部 inventory/runtime block 失败时返回本轮其它成功区块并只把失败区块标为 unknown，不能用上一份整页缓存冻结独立事实；只有 dashboard 整体构建抛出未处理异常时允许返回上一份 payload 并带 `dashboard_cache_stale_after_error` warning。权限失败和 PostgreSQL runtime 缺失不走缓存兜底。
- 导入历史不再以 `app.import_batches.status` 直接显示。`ImportLifecycleService` 聚合 batch/file/session/job 后输出 `awaiting_confirmation/queued/processing/succeeded/failed/discarded/withdrawn/inconsistent/unknown`；主页最新 5 条与 admin-only 分页抽屉共用该口径。
- `succeeded -> withdrawing -> withdrawn` 只发生在银行批次撤回写请求；按钮进入二次确认，提交期间禁止重复操作和关闭，成功后刷新历史，失败回到可重试并展示明确原因。

### System Audit

- `not_run`：尚未执行，不能显示绿色。
- `running`：一个 outer `REPEATABLE READ READ ONLY` transaction 正在执行 17 个子页面 proof 和 App Health database plane；不触发 refresh/repair。
- `internal_pass_external_unknown`：18 页已登记 App 内部合同在同一 snapshot 内通过，但外部 control evidence 缺失；`overall_status=pass`、`audit_status.external=unknown`、`end_to_end_source_truth=unproven` 同时成立。
- `internal_pass_external_pass`：内部 18 页通过，且银行/OA/发票/ETC 最新、未过期的 complete manifest 与当前 canonical exact set、关键字段和 controls 全部一致；只允许声明 `proven_as_of_external_evidence`，有效时间边界是各 evidence 的 observed/source snapshot 与当前 system snapshot。
- `external_fail`：任一最新 evidence revoked/expired、contract/coverage 非法，或存在 missing/extra/duplicate/field/control mismatch；即使内部 `overall_status=pass` 也必须保持 `end_to_end_source_truth=unproven`，不得回退旧 evidence。
- `issues_found`：任一子页 integrity/queue、dashboard inventory、manifest/status registry、required worker 或 current outbox 不一致；不得显示系统通过。
- `request_failed`：snapshot/SQL/runtime observation 不可执行，HTTP 返回 fail-closed error；不能用上一次绿色替代。
- Audit result 是带 snapshot/generated-at 的不可变历史快照证据。普通 dashboard refresh 不清除用户正在查看的结果；只有用户再次运行 Audit 才替换本地证据，后续写入仍不能沿用旧 `system_audit_id`。

## UI 状态

- loading：首次加载 dashboard 或 App Status provider 请求中；不能显示旧成功态为 fresh。
- empty：无 metrics 样本时显示 `--` 或 unknown，不等于 0。
- error：dashboard/API 请求失败显示错误；如果已有 dashboard payload，保留旧 payload 并提示 stale warning。
- stale/refreshing：来自后端 dashboard fallback、job、worker 或 outbox 状态，不由当前页面局部 loading 推导。
- permission disabled/hidden：dashboard 仅 admin 可见；非 admin 不请求 dashboard API。App Status popover 的运维入口仅 admin 显示。
- 有界轮询：App Health snapshot 按固定间隔刷新，focus/online 时立即刷新；跨 tab BroadcastChannel 只传播后端 snapshot。旧 SSE/EventSource 路径不得恢复。

## Worker / Queue 状态

- worker `ready/idle/working`：required instance 已登记且 heartbeat、kind、event type 合同一致；`working` 不计为问题。
- worker `stale`：busy/yellow；`missing/mismatch/unavailable` 在 critical domain 中 blocked/red。
- queue `pending/processing`：busy/yellow；`failed/dead_lettered` 进入 attention 或 release-readiness blocker，具体阻断级别由事件/域合同决定。
- 失败恢复通过对应 runbook、runtime queue ops 或 worker restart/drain；App Health 只展示和定位，不直接执行 repair。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-08-23 | 移除业务页分散 Audit 控件，前端只保留 App Health System Audit；App Status 清除已退役 read-model/readiness 状态 | 页面 UI、固定 System Audit API、worker/queue 状态口径 | `tests/test_page_audit_registry.py`、`tests/test_read_model_runtime_removal.py`、`web/src/test/AppHealthOperationsPage.test.tsx`、全量前端测试与生产 System Audit/SLO |
| 2026-07-11 | App Health 成为 17 页 system Audit owner | 一个 outer snapshot 执行其余 16 页 proof；database/runtime/external 三个 evidence plane 分离，旧进项专项面板删除 | `tests/test_audit_app_health_system.py`、`tests/test_app_health_api.py`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/e2e/app-shell.spec.ts` |
| 2026-07-11 | 外部 evidence exact proof owner | 四域 immutable manifest 与 canonical facts 做 exact set/field/control equality；显式 page coverage，删除 free-text classifier | `tests/test_external_control_evidence_*.py`、`tests/test_audit_external_control_evidence.py`、`tests/test_audit_app_health_system.py` |
