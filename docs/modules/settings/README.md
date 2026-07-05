# 设置模块维护入口

- Module key: `settings`
- 类型：页面模块 / 高风险配置域
- Route: `/settings`
- Page key: `settings`

## 修改前必读

- `docs/product-specs/platform-settings-health.md`
- `docs/operations/data-safety.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/dev/testing-closure-dependency-map.md`
- `docs/modules/read-models/README.md`
- `docs/modules/runtime-workers/README.md`
- `docs/modules/domain-events-lifecycle/README.md`
- 受影响下游模块：`reconciliation-workbench`、`bank-details`、`pending-invoices`、`tax-offset`、`cost-statistics`、`input-invoice-usage`、`output-invoice-collections`、`oa-pending-payments`、`imports-*`、`etc-tickets`

## 代码入口

- `web/src/pages/SettingsPage.tsx`
- `web/src/components/settings/*`
- `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- `web/src/features/workbench/api.ts`
- `backend/src/fin_ops_platform/app/routes_settings.py` 中 `/api/workbench/settings*`、数据重置和 OA 申请人凭据 routes
- `backend/src/fin_ops_platform/app/server.py` 中 settings route owner 组装、runtime reset executor 和 read model/lifecycle side-effect ports
- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/services/settings_data_reset_service.py`
- `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`
- `backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/oa_applicant_credentials.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`

## 当前边界

设置模块维护平台级配置事实，不只是设置页 UI。当前边界包括：

- 项目范围：OA 项目同步、手工项目、已完成项目、本地删除 override。
- 访问控制：允许访问、只读导出、admin、full access 派生名单和 OA role sync。
- 关联台设置：列布局、银行账户映射、OA 留存时间、OA 导入表单类型/状态过滤、OA 附件发票 promotion 模式、OA 发票抵扣申请人。
- 业务规则：待找发票标签组、免 OA 和往来款标签选择；银行明细自动标签规则只读返回给 settings 页面作为候选事实，`AppSettingsService.update_settings(...)` 不暴露 `bank_transaction_tags` 写参数，写入只能走银行明细 `自动标签规则` 抽屉/API。
- OA 申请人凭据：独立凭据事实源，只允许 admin 维护，普通 settings payload 不能包含密码、密文或 token。
- 数据重置：银行流水域、发票域、OA 源重置与重建；必须保护禁止删除目标、保留必要事实、记录 job progress，并避免旧 read model/cache 被误判为 fresh。

设置模块本身多数事实写入 `ApplicationStateStore`，但它的变更会扇出到 read model、dirty scope、worker、App Status 和多个页面。任何改动都必须先做影响面评估。

当前 HTTP I/O 边界已关闭：`SettingsApiRoutes` 负责 settings path matching、body/query parsing、权限 gate、错误码和 response shape；`server.py` 不再定义 `_handle_api_workbench_settings*` 旧 handler。`AppSettingsService` 只从持久化 settings store 刷新事实，缺失字段由 normalizer/default contract 处理，不再用旧内存 `_snapshot` 补齐持久化结果。

## 关键 fan-out

| 设置动作 | 后端事实 / event | 受影响模块 |
| --- | --- | --- |
| 待找发票规则保存 | `pending_invoice_rules_changed`，规则 version 递增 | 待找发票、关联台、发票 lifecycle、进项/销项/OA 待付款、税金、成本、搜索 |
| 银行标签/自动标签保存 | 仅由银行明细 `自动标签规则` API 触发 `bank_auto_tag_rules_changed` / bank auto tag rules audit；`/api/workbench/settings` 携带 `bank_transaction_tags` 必须拒绝；settings service 不提供该写参数 | 银行明细、免 OA、关联台候选、往来款、成本、搜索 |
| 项目范围变化 | `project_scope_changed` 或等价 dirty scope | 成本统计、搜索、关联台项目展示 |
| 访问控制变化 | state store + OA role sync | 页面可见性、写入权限、导出权限、数据重置权限 |
| OA 导入过滤/留存/promotion 设置变化 | state store，后续 OA reset/rebuild 或 sync 使用；OA 附件发票 promotion 默认 `link_existing_only`，`disabled` 完全跳过，只有 `create_missing` 才允许创建缺失正式发票 | OA 待付款、进项/销项、税金、成本、关联台、统一发票池 |
| OA 申请人凭据维护 | 独立 credential repository；不进入普通 settings payload | 进项发票使用 OA 反提草稿、真实 OA 登录/token provider |
| 数据重置 | `settings_reset_completed`、read model/dirty scope/cache cleanup | 所有列表页、导入、关联台、App Status/App Health |
| 启动补扫 | `startup_stale_scan` 默认关闭；启用时只标记 stale workbench matching dirty scopes | 关联台 matching 候选补扫；不直接刷新用户可见 read model |

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
- `e2e-spec.md`：维护设置页 Spec-first Browser 业务验收合同。
- `e2e-coverage.md`：维护设置页 Spec-first 合同到自动化覆盖的映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
