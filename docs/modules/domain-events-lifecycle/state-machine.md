# Domain Events 与 Derived Lifecycle 状态机

日期：2026-07-25

本模块不是普通写入分发器。后端 lifecycle 只允许两个显式维护事件：

| Event | 唯一生产入口 | Scope 合同 | 允许结果 |
| --- | --- | --- | --- |
| `etc_business_batch_changed` | 历史 ETC repair link | 精确月份，`include_all=false` | 已登记维护 executor 的 invalidation/job summary |
| `settings_reset_completed` | admin data reset 完成并 reload runtime 后 | 显式 `include_all=true` | 全域维护 executor 的 invalidation/job summary |

## Plan 状态

- `planned dry-run`：`plan_event(..., dry_run=True)` 只评估，无副作用。
- `executable`：`Application._execute_explicit_maintenance_lifecycle(...)` 生成 `dry_run=False` plan，并注入 reason/metadata。
- `executed`：executor 结果合并到 `deleted_counts`、`invalidated_scopes`、`enqueued_jobs`。
- `skipped`：缺少 executor 必须明确记录，不猜测副作用。
- `errored`：单 executor 失败进入 `errors`，管理员 reset/repair owner 决定失败/部分成功语义。

禁止流转：

- import confirm、OA sync、关系确认/撤回、分类、规则、Drawer 保存不得进入本状态机。
- 不得恢复 `import_state_changed`、`import.fact.changed`、`_RuntimeWorkerDerivedLifecycle` 或 `Application._execute_derived_data_lifecycle_event`。
- 不得由单个 executor 隐式刷新未声明页面；不得用前端 domain event 伪造 dirty/readiness/fresh。
- `PROTECTED_TARGETS` 永远不能被 lifecycle plan 删除。

## 前端边界

前端没有 finance domain event 或业务 tag BroadcastChannel。另一个页面/标签页的写入、focus、hidden→visible 与 BFCache 恢复不触发业务 GET；route 进入/重进、查询变化、浏览器手动刷新或明确重试时，页面从 API/read freshness boundary 取得事实。

## 失败恢复

1. 核对调用是否属于两个允许的维护入口。
2. 核对 plan event、scope、reason、permission/audit。
3. 检查 exact dirty/outbox/readiness/worker，而不是扩大为普通写 fan-out。
4. worker 修复后重跑显式维护命令；前端页面手动刷新不能替代后端维护恢复。
