# Domain Events 与 Derived Lifecycle 状态机

> 修改 `Domain Events 与 Derived Lifecycle` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。本模块本身不是业务事实源；它把事实变更传播到后端 dirty/read model 边界和前端刷新提示。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| Backend lifecycle event | declared | `DERIVED_DATA_EVENTS` | 新事件必须先声明，再补 mapping/test/docs。 |
| Backend lifecycle plan | planned dry-run | `DerivedDataLifecycleService.plan_event(..., dry_run=True)` | 用于评估影响面；不得执行落库副作用。 |
| Backend lifecycle plan | executable | `plan_event(..., dry_run=False)` | 只能由 app/service/worker 边界生成，并传给 `execute_plan`。 |
| Domain plan | invalidating / clearing / marking dirty / cleanup | `DERIVED_DATA_DOMAINS` 与 `_DOMAIN_ACTIONS` | executor 根据 domain plan 执行具体 dirty/outbox/cache/job 行为。 |
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
- 页面动作 emit 前端 `FINANCE_DOMAIN_EVENTS.*` 只提示当前浏览器刷新。
- 运维/backfill/startup stale scan 通过受控 lifecycle event 规划影响域。

失败恢复：

1. 先查后端 lifecycle event 是否覆盖正确 domain 和 scope。
2. 再查 dirty scope/outbox/readiness/worker 状态，确认 refresh 是否实际入队和完成。
3. 前端若没刷新，查 emit/subscribe、active page、BroadcastChannel 和页面 handler。
4. 如果后端 freshness 未完成，修后端 dirty/read model/worker，不通过前端事件伪造成功。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐 domain events / derived lifecycle 状态机 | 明确后端 lifecycle plan、executor summary、前端刷新事件和 read model/worker 状态边界 | 待本轮 domain-events-lifecycle 验证 |
