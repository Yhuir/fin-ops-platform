# OA 集成模块维护入口

- Module key: `oa-integration`
- 类型: 资源模块
- Route: `N/A`
- Page key: `N/A`

## 修改前必读

- `docs/architecture/oa-integration.md`
- `docs/references/external-systems.md`
- `deploy/oa/README.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/product-specs/invoice-lifecycle.md`
- `docs/product-specs/imports-and-etc.md`
- `docs/modules/permissions-and-audit/README.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/imports-etc-invoices/README.md`
- `docs/modules/etc-tickets/README.md`

## 代码入口

- OA session / 权限：`backend/src/fin_ops_platform/app/auth.py`、`backend/src/fin_ops_platform/services/oa_identity_service.py`、`backend/src/fin_ops_platform/services/access_control_service.py`、`web/src/features/session/api.ts`
- OA Mongo 只读 adapter：`backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- OA 投影与同步：`backend/src/fin_ops_platform/services/oa_projection_sync.py`、`backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py`、`backend/src/fin_ops_platform/app/worker.py`
- OA 待付款：`backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`、`backend/src/fin_ops_platform/services/oa_pending_payment_query_service.py`、`backend/src/fin_ops_platform/services/oa_pending_payment_canonical_rows.py`、`backend/src/fin_ops_platform/services/postgres_repositories/oa_pending_payment_query.py`
- OA 手动搜索/导入：`backend/src/fin_ops_platform/services/oa_manual_import_service.py`、`backend/src/fin_ops_platform/app/server.py`
- OA 附件发票识别：`backend/src/fin_ops_platform/services/oa_attachment_invoice_service.py`、`backend/src/fin_ops_platform/services/invoice_attachment_recognition_service.py`
- 目标申请人凭据：`backend/src/fin_ops_platform/services/oa_applicant_credentials.py`、`backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`
- 进项发票 OA 反提：`backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
- ETC OA 草稿/人工确认：`backend/src/fin_ops_platform/services/etc_service.py`、`backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`、`backend/src/fin_ops_platform/app/routes_etc.py`
- 前端入口：`web/src/features/session/api.ts`、`web/src/pages/InputInvoiceUsagePage.tsx`、`web/src/pages/OaPendingPaymentsPage.tsx`、`web/src/pages/EtcTicketManagementPage.tsx`、`web/src/components/settings/SettingsOaApplicantCredentialsSection.tsx`、`web/src/components/settings/OaManualSearchImportTable.tsx`

## 当前边界

- OA 主系统负责登录态、菜单 iframe、用户信息、权限和原始付款申请/报销/项目数据。
- 本系统不修改 OA 原始业务库；对 OA Mongo 只读读取、映射、缓存和投影。
- `Admin-Token` 只作为会话来源；后端必须二次校验 `finops:app:view` 和 app 内访问等级。
- OA 同步通过 worker / durable queue 原子写入本系统 PostgreSQL canonical OA、admission、payment-status 与 watermark facts。它不 fan-out 页面 refresh；各 direct 页面下一次 GET 读取已提交 facts，保留的 Search/共享 relation/no-OA read model 由各自 owner 按明确合同维护。
- OA 附件解析结果不直接等同于正式发票事实。附件发票识别只有三种结果：命中统一发票池则建立/补充关系，判定为正式发票且池内不存在时可受控创建并关联，非正式票据、残缺号码、多义匹配或未知证据直接忽略。受控创建由设置页 `OA附件发票晋级` 控制：默认 `link_existing_only` 只关联已有发票，`disabled` 完全跳过 promotion，只有 `create_missing` 才允许创建缺失的统一发票池记录。
- 目标 OA 申请人凭据只允许 admin 维护，API / settings response 不得回显 password；创建草稿时用目标申请人账号登录 OA 并只使用返回 token。
- ETC 与进项发票 OA 草稿只创建或本地撤销绑定，不自动删除或撤销真实 OA 草稿/流程。
- 真实 OA 登录、RSA 加密、OA 草稿页面、生产 Mongo 字段变体和 OA 菜单角色同步必须通过 staging/生产前 smoke 补证，本地测试只能保护 contract 与失败处理。

## 影响面

| 入口 | 影响范围 | 关键风险 |
| --- | --- | --- |
| `/api/session/me` / session bootstrap | 所有页面、所有 API 权限、page session scope | OA 超时、无权限、token 过期、只读/全操作/admin 分层错误 |
| OA Mongo adapter | Workbench、OA 待付款、进项使用、ETC、税金、成本、搜索 | 外部字段变体、Mongo 断连、缓存 backoff、附件发票 identity、附件 promotion 模式误配置 |
| OA sync worker / canonical snapshot | 关联台 projection、待找发票、OA 待付款、进/销项等 direct 页面 | worker 未入队、canonical snapshot 半写入、retention cutoff、旧 relation row id 迁移 |
| OA 手动搜索/导入 | 设置页、Workbench、Search、历史 OA 补录 | 未完成单据误导入、附件刷新失败、手动 marker 删除后 stale scope |
| OA applicant credentials | 设置页、进项发票 OA 反提 | 非 admin 修改、password 泄漏、pgcrypto key/配置缺失 |
| Target OA applicant login | 进项 OA 草稿、ETC 草稿 | HTTP/网络/无效 JSON/无 token 不能伪装成功，错误不能泄露密码 |
| Input invoice OA reverse | 进项使用、OA 关系、审计、read model invalidation | preview hash stale、version conflict、idempotency、人工 submitted/not_submitted |
| ETC OA draft/manual status | ETC 票据、关联台、税金、成本、search | 本地状态和真实 OA 状态混淆，删除本地批次误删真实 OA |
| OA role sync / deploy | OA 菜单可见性、app 权限模型 | OA 角色与 app allowed/readonly/admin 不一致 |

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
