# 操作历史边界与 I/O

## 职责

- 负责：管理员审计查询、筛选、游标翻页、单条详情与前后值展示。
- 不负责：业务事实修改、修复、read model 刷新、历史补录和权限配置。

## I/O

| 边界 | 输入 | 输出/约束 |
| --- | --- | --- |
| 写操作审计 | 服务端解析出的 actor、HTTP route/request id、结果；领域服务前后值 | 追加写 `audit.events`；requested 写失败时业务 mutation fail closed；敏感键被移除 |
| 财务事实修正 | 数据库 transaction-local actor/reason | `app.financial_fact_corrections` + `audit.events` 同事务追加；无 reason 拒绝关键字段更新/删除 |
| 列表 API | 005 session、日期/人员/页面/搜索/cursor | 最多 200 条，稳定时间+UUID 游标；只返回覆盖点之后的数据 |
| 详情 API | 005 session、event UUID | 单条审计事实；不存在返回 404 |

Own read model：无。Redis/RabbitMQ/后台 worker：无。事实源为 PostgreSQL `audit.events`。

旧链路删除条件：生产不得使用 `AuditTrailService._entries`；它只保留给无 repository 的隔离单元测试。不得恢复 audit 表 UPDATE/DELETE 权限或页面端自行拼接 actor。
