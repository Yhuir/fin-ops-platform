# 操作历史边界与 I/O

## 职责

- 负责：管理员审计查询、按业务请求聚合生命周期、筛选、游标翻页、操作人选项、详情与前后状态展示。
- 不负责：业务事实修改、修复、read model 刷新、历史补录和权限配置。

## I/O

| 边界 | 输入 | 输出/约束 |
| --- | --- | --- |
| 写操作审计 | 服务端解析出的 actor id/name/account、HTTP route/request id、结果；领域服务前后值 | 追加写 `audit.events`；requested 写失败时业务 mutation fail closed；敏感键被移除；客户端不能覆盖 actor |
| 财务事实修正 | 数据库 transaction-local actor/reason | `app.financial_fact_corrections` + `audit.events` 同事务追加；无 reason 拒绝关键字段更新/删除 |
| 列表 API `GET /api/operations/history` | 005 session、日期/人员/页面/搜索/cursor | 在数据库内先按 `request_id` 合并 requested/completed，再筛选和翻页；最多 200 条，稳定时间+operation key 游标；只返回覆盖点之后的数据 |
| 操作人 API `GET /api/operations/history/actors` | 005 session | 返回审计事实中完整、去重的操作人 id/name/account 选项 |
| 详情 API `GET /api/operations/history/{operation_key}` | 005 session、request/event operation key | 返回一个逻辑操作及用户可读的对象、选择项和前后状态；不返回内部 ID、raw payload 或 secret；不存在返回 404 |

Own read model：无。Redis/RabbitMQ/后台 worker：无。事实源为 PostgreSQL `audit.events`。

旧链路删除条件：生产不得使用 `AuditTrailService._entries`；它只保留给无 repository 的隔离单元测试。前端不得按 raw event 逐行显示 requested/completed，也不得恢复 audit 表 UPDATE/DELETE 权限或页面端自行拼接 actor。
