# 切换执行记录 - 20260517

本文对应任务 `p4-16-final-formal-cutover-i-readonly`，用于准备 P4-11 cutover/rollback execution record。由于 readiness gate 当前为 `NO_GO`，且没有用户明确文字授权生产切换，本记录状态为 `blocked_not_executed`。

## 基本信息

| 项 | 值 |
| --- | --- |
| generated_at | `2026-05-17T10:15:29+08:00` |
| operator | Codex |
| status | `blocked_not_executed` |
| go/no-go | `NO_GO` |
| formal go/no-go evidence | `docs/operations/backend-refactor/formal-migration-go-no-go-20260517.json` |
| production cutover requested | no |
| production cutover authorized | no |
| conversation context treated as authorization | no |
| OA source database accessed | no |

## 前置条件复核

| 条件 | 状态 |
| --- | --- |
| readiness gate 为 `GO` | no |
| 维护窗口确认 | no |
| 回滚路径确认 | no |
| latest app Mongo freeze-point backup 确认 | no |
| 用户明确文字授权生产切换 | no |

## P4-11 执行顺序记录

以下是执行顺序模板，不是已执行记录。

| order | phase | status | start/end | expected action when authorized | actual result |
| --- | --- | --- | --- | --- | --- |
| 1 | shadow_read | `blocked_not_executed` | - / - | 启用 Axum shadow read，用户仍看旧 Python API。 | 未执行；readiness gate `NO_GO` 且无授权。 |
| 2 | small_scope_read_switch | `blocked_not_executed` | - / - | 小范围低风险读 route group 切到 Axum，并保留旧 Python 回滚路由。 | 未执行；readiness gate `NO_GO` 且无授权。 |
| 3 | dual_write | `blocked_not_executed` | - / - | 对已评审写路径启用 dual-write，并具备 idempotency、audit、outbox 和对账证据。 | 未执行；readiness gate `NO_GO` 且无授权。 |
| 4 | full_read_switch | `blocked_not_executed` | - / - | shadow 和小范围读证据为 `GO` 后，迁移全部已批准读 route group。 | 未执行；readiness gate `NO_GO` 且无授权。 |
| 5 | stop_old_writes | `blocked_not_executed` | - / - | PostgreSQL 被接受为事实源后，停止或转发旧 Python 写路径。 | 未执行；readiness gate `NO_GO` 且无授权。 |
| 6 | archive_freeze_app_mongo | `blocked_not_executed` | - / - | 创建并确认 app Mongo freeze-point backup 后归档/冻结；不得删除 app Mongo。 | 未执行；readiness gate `NO_GO` 且无授权。 |

## 未执行动作确认

- 未执行 shadow read。
- 未执行 small-scope read switch。
- 未开启 dual-write。
- 未执行 full read switch。
- 未停止 old writes。
- 未 archive/freeze app Mongo。
- 未删除 app Mongo。
- 未执行破坏性命令。
- 未访问 OA 源数据库。
- 未写入 secret、完整 URI、密码、token、S3 credential 或 NATS credential。

## 回滚约束

- 禁止删除 app Mongo。
- PostgreSQL 成为事实源后，禁止旧 Mongo 全量覆盖 PostgreSQL。
- 任何未来执行必须记录 audit evidence、rollback point、operator、approver、business owner、rollback owner、route snapshot 和 feature flag snapshot。
- 任何未来执行不得访问 OA 源数据库，不得把 secret 或完整服务 URI 写入报告。

## blocked_not_executed 原因

readiness gate 当前为 `NO_GO`，有 9 个 blocking checks；没有维护窗口确认、回滚路径确认、latest app Mongo freeze-point backup 确认，也没有用户明确文字授权生产切换。因此本任务停止在证据记录阶段，不请求授权、不执行 P4-11。
