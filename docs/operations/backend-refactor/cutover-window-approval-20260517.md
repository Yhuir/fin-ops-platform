# 切换维护窗口审批证据 - 20260517

本文是 p4-15 的维护窗口配对证据。它只记录候选窗口和审批阻塞项，不授权生产切流、双写、app Mongo 冻结或 app Mongo 删除。

## 结论

| 项 | 值 |
| --- | --- |
| Gate | **NO_GO** |
| go/no-go | `NO_GO` |
| generated_at | `2026-05-17T10:12:00+08:00` |
| approval status | `pending_formal_change_approval` |
| production cutover authorized | no |
| app Mongo freeze authorized | no |
| OA source database accessed | no |

## 候选维护窗口

| 字段 | 值 |
| --- | --- |
| timezone | `Asia/Shanghai` |
| proposed start | `2026-05-24T22:00:00+08:00` |
| proposed end | `2026-05-25T02:00:00+08:00` |
| duration | 240 minutes |
| approver | `pending_named_change_approver` |
| operator | `pending_named_finops_backend_operator` |
| business owner | `pending_named_business_owner` |
| rollback owner | `pending_named_rollback_owner` |
| DBA/ops owner | `pending_named_dba_or_ops_owner` |
| communications owner | `pending_named_communications_owner` |

该窗口是候选时间，不是审批通过的生产变更窗口。缺少命名负责人和正式变更审批，因此审批状态为 `NO_GO`。

## 业务影响范围

- FinOps Web 用户可能在已审批窗口内看到迁移 API 的维护公告。
- 观察和回滚准备范围包括 import confirmation、reconciliation confirmation/withdrawal、search、workbench read models、cost statistics、tax offset、ETC 和 background job status。
- 本证据不授权任何生产副作用请求。写流量、双写和 app Mongo freeze 必须等待单独审批。

## 沟通计划

| 阶段 | 计划 |
| --- | --- |
| before window | 正式审批后公告维护范围、开始/结束时间、operator、rollback owner 和支持渠道。 |
| during window | 在开始、每个 phase 决策点、回滚判断点和窗口结束时发布状态。 |
| after window | 发布 GO/NO_GO 结果、回滚决策、事故链接和证据路径；不得包含 secret 或完整服务 URL。 |
| support channel | `pending_internal_channel_without_secret` |

## 回滚决策点

| phase | latest decision time | rollback action | owner |
| --- | --- | --- | --- |
| shadow_read | `2026-05-24T22:30:00+08:00` | 关闭 shadow read，用户流量继续走旧 Python API。 | `pending_named_rollback_owner` |
| small_scope_read | `2026-05-24T23:15:00+08:00` | 小范围读 route group 回旧 Python API。 | `pending_named_rollback_owner` |
| dual_write | `2026-05-25T00:00:00+08:00` | 关闭双写，保留 PostgreSQL 现场，仅通过审计补偿处理差异。 | `pending_named_rollback_owner` |
| full_read_switch | `2026-05-25T01:00:00+08:00` | 所有迁移读 route group 回旧 Python API。 | `pending_named_rollback_owner` |
| old_write_resume | `2026-05-25T01:30:00+08:00` | 仅在 PostgreSQL 尚未成为唯一事实源前恢复旧写。 | `pending_named_rollback_owner` |

## 备份和 freeze-point 确认

| 字段 | 值 |
| --- | --- |
| latest app Mongo backup evidence | `docs/operations/backend-refactor/app-mongo-backup-restore-report-20260517.json` |
| latest app Mongo backup status | `GO` |
| freeze-point backup required | true |
| freeze-point backup confirmed | false |
| app Mongo freeze authorized | false |
| app Mongo deleted | false |

既有 app Mongo 备份恢复证据通过，但本任务没有执行冻结，也没有创建或确认切换窗口 freeze-point backup。

## 审批阻塞项

- 维护窗口仅为候选时间，尚未获得正式变更审批。
- 缺少命名 approver、operator、business owner、rollback owner、DBA/ops owner 和 communications owner。
- 回滚演练记录为 `NO_GO`，六项演练场景均未执行。
- 切换窗口 app Mongo freeze-point backup 未确认。
- 本证据不授权生产切流、双写或 app Mongo freeze。
