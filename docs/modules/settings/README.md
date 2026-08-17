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
- `web/src/features/workbench/api.ts`
- `backend/src/fin_ops_platform/app/routes_settings.py` 中 `/api/workbench/settings*`、数据重置和 OA 申请人凭据 routes
- `backend/src/fin_ops_platform/app/server.py` 中 settings route owner 组装和 durable reset enqueue
- `backend/src/fin_ops_platform/services/settings_data_reset_job.py`
- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py` 中 `SettingsDataResetRuntimeFactory`
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
- 访问控制：`/settings` 的“访问账户权限”是唯一人工入口；独立 admin-only `GET/PUT /api/workbench/settings/access-control` 维护其他账号的完整 `full_access` / `read_export_only` 列表，列表缺席派生为 `denied`。唯一 protected administrator `YNSYLP005` 固定且不可由 APP 修改，generic settings 与 Workbench modal 均无 ACL I/O。
- 用户名合同：等值、去重和跨 tier overlap 使用共享 casefold comparison key；输出保留 OA `sys_user.user_name` canonical spelling，碰撞、控制字符、重复和 protected-admin 输入在 OA I/O 前拒绝。
- 写入合同：专用 PUT 使用独立 `access_control_version` / `expected_version`、PostgreSQL CAS 和同事务 durable audit；semantic no-op 零 PostgreSQL/audit/OA I/O。真实变化严格投影三个专用 OA 角色，OA target、PostgreSQL commit 和补偿按明确的 502/503 状态收敛。
- 关联台设置：列布局、银行账户映射、OA 留存时间、OA 导入表单类型/状态过滤、OA 附件发票 promotion 模式、OA 发票抵扣申请人。
- 业务规则：待找发票标签组、免 OA 和往来款标签选择；银行明细自动标签规则只读返回给 settings 页面作为候选事实，`AppSettingsService.update_settings(...)` 不暴露 `bank_transaction_tags` 写参数，写入只能走银行明细 `自动标签规则` 抽屉/API。
- 成本统计无 OA 范围：`cost_statistics_tag_selection` 只保存用户命名的虚拟项目和选中标签 code，schema v3 默认两者为空；候选资格和逐笔无 OA 判定由成本统计 owner 从 canonical 银行/OA 关系计算。自动标签归档不得静默删除已保存选择。
- OA 申请人凭据：独立凭据事实源，只允许 admin 维护，普通 settings payload 不能包含密码、密文或 token。
- 数据重置：银行流水域、发票域、OA 源重置与重建；必须保护禁止删除目标、
  保留必要事实、记录 job progress，并确保 canonical 页面下一次 GET 读取重置后的事实。

设置模块本身多数事实写入 `ApplicationStateStore`。变更会影响多个页面的下一次
canonical query，也可能影响 `workbench` 或 `workbench_relation` owner 的显式 maintenance 合同；
任何改动都必须先做影响面评估，但普通保存不广播 page refresh。

当前 HTTP I/O 边界已关闭：`SettingsApiRoutes` 负责 settings path matching、body/query parsing、权限 gate、错误码和 response shape；`server.py` 不再定义 `_handle_api_workbench_settings*` 旧 handler。`AppSettingsService` 只从持久化 settings store 刷新事实，缺失字段由 normalizer/default contract 处理，不再用旧内存 `_snapshot` 补齐持久化结果。

## 关键影响

| 设置动作 | 后端事实 | 可见性合同 |
| --- | --- | --- |
| 待找发票规则保存 | income/expense rule version 原子递增 | 待找发票下一次 GET 直接应用；不 fan-out retired page scope |
| 银行标签/自动标签保存 | 只允许银行明细规则 API 写入并记录 audit | canonical 页面下次 GET 读取；共享 no-OA/Search 只按各自 owner 合同处理 |
| 项目范围变化 | project settings/version | 成本统计、关联台等 direct 页面下次 GET 直接读取；不发布 page Workbench refresh |
| 访问控制 no-op / 真实变化 | `app.app_settings` ACL family + 独立 version；真实变化同事务写 `audit.events` | no-op 零 I/O；真实变化严格投影 OA 三专用角色后提交，下一次 session/API 使用新 snapshot；失败按补偿状态返回 502/503 |
| OA 导入过滤/留存/promotion | state store，供后续 OA sync/reset 使用 | 页面下次 GET 读取已提交 OA canonical facts |
| OA 申请人凭据维护 | 独立 credential repository | 进项 OA 反提 token provider 使用；普通 settings payload 不含 secret |
| 数据重置 | `settings.data_reset.requested` durable event + `settings-maintenance` worker | API 只校验权限/密码并入队；worker 执行 canonical cleanup、登记派生刷新并请求 Gunicorn graceful reload，job 显示进度/失败 |
| 启动补扫与恢复 | `settings-maintenance` / `workbench-matching` worker | API 构造与启动无业务写副作用；stale scan 仅在 matching worker 显式启用时执行 |

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
