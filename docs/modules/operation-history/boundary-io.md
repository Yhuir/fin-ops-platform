# 操作历史边界与 I/O

## 职责

- 负责：管理员审计查询、按业务请求聚合生命周期、筛选、游标翻页、操作人选项、详情与前后状态展示。
- 不负责：业务事实修改、修复、read model 刷新、历史补录和权限配置。

## I/O

| 边界 | 输入 | 输出/约束 |
| --- | --- | --- |
| 写操作审计 | 服务端解析出的 actor id/name/account、HTTP route/request id、结果；领域服务前后值；操作发生时的有界证据快照 | 由后端语义注册表把 route 归一为稳定 `action_code/action_label/object_label/description` 后追加写 `audit.events`；同一 HTTP mutation 内的领域审计继承 request id 并聚合为一条逻辑操作；requested 写失败时业务 mutation fail closed；敏感键被递归移除；客户端不能覆盖 actor |
| 关系收据审计 | 收据 service 的服务端 actor、relation case、receipt id、内容指纹、付款方/日期/金额/发票号快照 | 首次持久化新指纹时追加 `receipt_generated`；每次服务端成功返回 PDF 时追加 `receipt_print_requested`。相同指纹重放不得重复文件或 generated 事件；系统永不声称浏览器已经完成打印，不记录伪 `receipt_printed`。 |
| 财务事实修正 | 数据库 transaction-local actor/reason | `app.financial_fact_corrections` + `audit.events` 同事务追加；无 reason 拒绝关键字段更新/删除 |
| 列表 API `GET /api/operations/history` | 005 session、日期/人员/页面/搜索/cursor | 在数据库内先按 `request_id` 合并 requested/completed，再筛选和翻页；最多 200 条，稳定时间+operation key 游标；只返回覆盖点之后的数据 |
| 操作人 API `GET /api/operations/history/actors` | 005 session | 返回审计事实中完整、去重的操作人 id/name/account 选项 |
| 详情 API `GET /api/operations/history/{operation_key}` | 005 session、request/event operation key | 返回一个逻辑操作及固定 `detail` 投影：`target`、`artifacts[]`、`records[]`、`changes[]`、`failure`、`legacy_evidence_missing`。OA 补充凭证成功时返回受保护预览 URL，失败/删除只保留文件元数据；手工发票返回发票号、销购方、日期和金额快照。存在固化证据时不再查询可变业务表；旧记录仅用同 request 的关系历史做去标识化兼容投影，不模糊反查。不存在返回 404；不返回 raw payload、secret 或审计内部标识。前端列表与详情请求分别采用 latest-request/abort 约束，旧响应不得覆盖新筛选或新选择。 |

Own read model：无。Redis/RabbitMQ/后台 worker：无。事实源为 PostgreSQL `audit.events`。

旧链路删除条件：生产不得使用 `AuditTrailService._entries`；它只保留给无 repository 的隔离单元测试。前端不得按 raw event 逐行显示 requested/completed，不得使用旧 `items` DTO/操作明细表格、维护 route/object type 文案映射或展示内部审计标识，也不得恢复 audit 表 UPDATE/DELETE 权限或页面端自行拼接 actor。
