# 操作历史边界与 I/O

## 职责

- 现金例外：精确 `/api/cash` 与 `/api/cash/*` 在 HTTP requested/completed 两个钩子均排除，成功/失败/配置/任务操作都不写全局历史；现金仍是需要认证授权的真实 mutation。平台页面 ACL 更改的既有安全审计不排除。详见 [cash I/O](../cash/boundary-io.md)。

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

## 2026-09-22 管理员导入任务处理

import_job.dispose 为结束导入任务处理，HTTP completion 固化处理原因、补充说明、原执行结果和处理状态证据；领域成功事件与 job disposition 同事务。不删除失败历史，不把关闭提醒解释为导入成功。

实施、验证与旧链路清理见[处理闭环](../../dev/import-task-disposition-plan.md)。

## 2026-09-23 共享导入任务

银行、发票和 ETC 的已登记 durable import task 向所有已获平台访问权的登录用户开放查看、复核、重新预览、重试、确认和结束处理；不按创建人或管理员分层。未登记的私人草稿继续校验创建人；OA、税务和其他任务保留原权限。原页面权限、App Health 管理权限、设置和现金边界不扩大。

- 输入：`GET /api/imports/jobs?page&page_size&domain`、按任务 UUID 读取详情/银行映射、既有 session/review/confirm/retry/discard API。session 访问必须由同一 durable task 的类型、session ID 和原创建人事实证明；没有 task 时仅允许原草稿本人。`domain` 在分页与计数之前筛选，详情按需读取。
- 输出：共享任务摘要与分页详情、既有预览/任务 DTO、状态变化与真实操作人审计。创建人与文件 provenance 不修改；确认/重试的 actor 快照随任务持久化，worker 按实际操作人的当前平台授权执行，成功结果和领域审计与事实同事务。
- 前端：全局状态、银行/发票/ETC 页和 App Health 复用 `ImportJobDiagnostics`；共享抽屉复用 `ImportWorkflowPage` 的任务模式，不要求进入受页面 ACL 限制的原页。正常上传页仍为空白草稿；打开共享任务使用独立组件实例，不覆盖当前未保存内容。
- 刷新：沿用现有全局轮询，写后回读当前任务/列表；共享任务跨状态保持可见。不新增定时器、缓存、read model、队列、依赖、迁移或备份。
- 旧链清理：删除导入任务 admin-only、共享任务 creator-only、跨用户无法继续预览文案与对应旧测试假设；非共享任务的 owner 校验保留。失败不能用普通已读绕过明确结束处理；原错误历史保留。
- 验证：共享权限、私人草稿隔离、跨用户确认/异步审计、分页筛选、并发与回滚、丢失响应核实、旧页面导入回归；见[共享实施与验收](../../dev/import-task-disposition-plan.md#共享处理修订2026-09-23)。
