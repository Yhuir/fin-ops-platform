# Domain Events 与 Derived Lifecycle 状态机

> 修改 `Domain Events 与 Derived Lifecycle` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。本模块本身不是业务事实源；它把事实变更传播到后端 dirty/read model 边界和前端刷新提示。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| Backend lifecycle event | declared | `DERIVED_DATA_EVENTS` | 新事件必须先声明，再补 mapping/test/docs。 |
| Backend lifecycle plan | planned dry-run | `DerivedDataLifecycleService.plan_event(..., dry_run=True)` | 用于评估影响面；不得执行落库副作用。 |
| Backend lifecycle plan | executable | `plan_event(..., dry_run=False)` | 只能由 app/service/worker 边界生成，并传给 `execute_plan`。 |
| Domain plan | invalidating / clearing / marking dirty / cleanup | `DERIVED_DATA_DOMAINS` 与 `_DOMAIN_ACTIONS` | executor 根据 domain plan 执行具体 dirty/outbox/cache/job 行为。 |
| Domain plan scope | event-level scope / domain override scope | `Application._execute_derived_data_lifecycle_event(...)`、`_RuntimeWorkerDerivedLifecycle._execute_import_state_changed(...)` | 事件表达影响域，scope override 只用于同一事件下不同 read model 的 concrete scope 差异；不得绕过 lifecycle 直接手写 producer fan-out。 |
| Executor result | executed | `execute_plan(...).deleted_counts/invalidated_scopes/enqueued_jobs` | 成功 executor 合并 summary；缺失 executor 进入 skipped。 |
| Executor result | skipped | `execute_plan(...).skipped` | 未提供 executor 时不猜测副作用，必须显式记录 skipped。 |
| Executor result | errored | `execute_plan(...).errors` | 单个 executor 失败不吞掉；summary 记录 domain/error，调用方决定 HTTP/worker 处理。 |
| Frontend finance event | emitted | `emitFinanceDomainEvent(...)` | dispatch 当前 window，并尝试 BroadcastChannel 通知其他 tab。 |
| Frontend finance event | subscribed | `subscribeFinanceDomainEvent(...)` / `useActiveFinanceDomainEvent(...)` | active 页面立即处理；inactive 页面不作为事实源。 |

禁止流转：

- 禁止前端 domain event 替代后端 dirty scope、outbox、readiness 或 API freshness。
- 禁止新增后端 event 只改枚举，不补影响面、测试和模块文档。
- 禁止新增前端 event 只让页面监听，不确认对应后端 lifecycle/read model/worker 事实链。
- 禁止 lifecycle plan 删除 `PROTECTED_TARGETS`。
- 禁止 `workbench_read_model`、workbench scope invalidation helper 或其它单一 domain executor 隐式刷新不属于自己的 read model domain。
- 禁止 import persistence callback 逐个调用 downstream read model producer；必须通过 `import_state_changed` lifecycle event。

## UI 状态

本模块没有独立页面；UI 状态由使用 domain event 的页面体现。

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 页面收到事件后重新请求 API，或页面重新 mount 后加载 | 只表示页面正在刷新，不证明后端派生数据已完成。 |
| empty | API/read model fresh 且返回空结果 | 不能由 domain event 单独决定。 |
| error | API/worker/read model 返回失败，或页面刷新请求失败 | 前端 event 不吞掉后端错误。 |
| stale / refreshing | API response/read model status 暴露 stale、refreshing、refresh_enqueued | 页面可展示旧数据和刷新提示。 |
| permission disabled/hidden | Auth/API contract | domain event 不改变权限事实。 |

`useActiveFinanceDomainEvent` 的页面激活规则：

- active 页面收到事件时立即调用 handler。
- inactive 页面卸载或不 active 时，不应 replay 离开期间的旧事件。
- 页面重新 mount 后必须通过 API/read boundary 获取当前事实，不从事件缓存恢复业务数据。

## Read Model / Worker 状态

Lifecycle 本身只规划影响域，实际状态由 read model / worker 模块维护：

| 状态 | 判定 | 本模块责任 |
| --- | --- | --- |
| `fresh` | 对应 read model readiness 或 active generation 证明可读 | lifecycle 不直接声明 fresh。 |
| `missing` | registry/readiness 缺少证明 | lifecycle 可触发 refresh，但不能把 missing 包装为空结果。 |
| `refreshing` | dirty scope pending/processing 或 parent scope 等 shard | lifecycle 应产生正确 affected scope 和 enqueued job。 |
| `stale` | source/schema mismatch 或 dirty source version 未完成 | lifecycle 应覆盖受影响 read model，不漏发下游域。 |
| `failed` | executor/worker/read model refresh 失败 | summary/errors、App Health、worker readiness 暴露失败。 |
| `unavailable` | DB/worker/read model/runtime 不可用 | 页面/API 根据后端事实展示，不由前端 event 修正。 |

Refresh 触发来源：

- 后端业务写入调用 `Application._execute_derived_data_lifecycle_event(...)`。
- runtime worker handler 调用 `_RuntimeWorkerDerivedLifecycle.execute_event(...)`。
- 导入 facts 保存后调用 `import_state_changed`，并通过 per-domain scope override 表达 workbench month scope、pending invoice scope、invoice usage collection scope、bank detail scope 和 cost/search scope 的差异；bank detail refresh reason 必须保持 `import_facts_changed`。
- 页面动作 emit 前端 `FINANCE_DOMAIN_EVENTS.*` 只提示当前浏览器刷新。
- 运维/backfill/startup stale scan 通过受控 lifecycle event 规划影响域。
- `startup_stale_scan` 是 opt-in 启动补扫，只有 `FIN_OPS_STARTUP_WORKBENCH_MATCHING_STALE_SCAN_ENABLED=1` 时才在 API 启动时执行；执行时只允许标记不 fresh 的 `workbench_matching_dirty_scopes`，不得直接 invalidating 或 enqueue 用户可见 read model，避免服务重启把页面拖入长时间 refreshing/failed。

失败恢复：

1. 先查后端 lifecycle event 是否覆盖正确 domain 和 scope。
2. 再查 dirty scope/outbox/readiness/worker 状态，确认 refresh 是否实际入队和完成。
3. 前端若没刷新，查 emit/subscribe、active page、BroadcastChannel 和页面 handler。
4. 如果后端 freshness 未完成，修后端 dirty/read model/worker，不通过前端事件伪造成功。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-23 | 补 invoice lifecycle/read model manifest 合同守卫记录 | 不改变 lifecycle event、plan、executor 或前端 finance event 状态；只登记 `invoice_lifecycle` 继续作为跨页面生命周期 read boundary，input/output 页面 read model 通过独立合同消费生命周期结果 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_invoice_lifecycle_and_usage_manifest_preserve_scoped_contracts` |
| 2026-07-05 | 收口 `import_state_changed` 并移除隐藏 I/O | 导入持久化后的派生刷新由 lifecycle event + domain scope override 统一规划；invoice usage collection / OA pending payment 成为显式 domain；`workbench_read_model` executor 和 workbench scope invalidation helper 不再隐藏刷新其它 read model；Application/runtime worker 保留 bank detail `import_facts_changed` reason；runtime worker 补齐 `bank_flow_rule_batch_read_model` executor | `tests.test_derived_data_lifecycle_service`、`tests.test_runtime_worker_read_model_refresh_scopes`、`tests.test_workbench_dirty_queue_wiring.WorkbenchDirtyQueueWiringTests.test_import_state_persistence_uses_lifecycle_domain_scope_overrides`、`tests.test_workbench_dirty_queue_wiring.WorkbenchDirtyQueueWiringTests.test_pair_relation_lifecycle_metadata_limits_downstream_refreshes`、`tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_scope_invalidation_does_not_refresh_invoice_usage_domains`、`tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate` |
| 2026-06-11 | 补齐 domain events / derived lifecycle 状态机 | 明确后端 lifecycle plan、executor summary、前端刷新事件和 read model/worker 状态边界 | 待本轮 domain-events-lifecycle 验证 |
| 2026-06-13 | 收窄 startup stale scan 影响域并改为 opt-in | 默认启动不再执行补扫；启用时只标记 stale workbench matching dirty scopes，不再刷新 workbench、relation、invoice lifecycle、cost、tax 等页面 read model | `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_workbench_dirty_queue_wiring -v` |
