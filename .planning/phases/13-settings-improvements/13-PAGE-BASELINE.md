# 设置 L1.5 页面基线卡片

## Scope

- Phase: `13-settings-improvements`
- Page key: `settings`
- Route: `/settings`
- Page entry: `web/src/pages/SettingsPage.tsx`
- Related UI: `web/src/components/settings/*`, `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- API client: `web/src/features/workbench/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/server.py` `/api/workbench/settings*`, data reset routes, OA applicant credential routes
- Core services: `app_settings_service.py`, `settings_data_reset_service.py`, `oa_applicant_credentials.py`, `target_oa_applicant_token_provider.py`, `derived_data_lifecycle_service.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

设置模块维护平台级配置事实，不只是设置页 UI。多数事实写入 `ApplicationStateStore`，但设置变更会 fan-out 到 read model、dirty scope、worker、App Status 和多个页面。

当前边界包括：

1. 项目范围、访问控制、关联台设置、业务规则、OA 申请人凭据和数据重置。
2. 银行明细自动标签规则只读返回给 settings 页面作为候选事实；写入只能走银行明细自动标签规则抽屉/API。
3. `AppSettingsService.update_settings(...)` 不暴露 `bank_transaction_tags` 写参数，`/api/workbench/settings` 携带该字段必须拒绝。
4. OA 申请人凭据是独立凭据事实源，只允许 admin 维护，普通 settings payload 不能包含密码、密文或 token。
5. 数据重置必须保护禁止删除目标、保留必要事实、记录 job progress，并避免旧 read model/cache 被误判为 fresh。

## Cross-Page Dependencies

- Downstream fan-out:
  - `reconciliation-workbench`
  - `bank-details`
  - `pending-invoices`
  - `tax-offset`
  - `cost-statistics`
  - `input-invoice-usage`
  - `output-invoice-collections`
  - `oa-pending-payments`
  - `imports-bank-transactions`
  - `imports-invoices`
  - `imports-etc-invoices`
  - `etc-tickets`
  - `app-health-operations`
- Phase 0 dependency group: `Analytics and status` / global configuration fan-out。

## Read Model / Worker / App Status

- Direct read model: settings 本身主要是 state store/config facts。
- Workers/jobs:
  - `oa-sync`
  - `settings_refresh`
  - data reset/background jobs
- Dependencies: `oa_identity`, `state_store`, OA applicant credential repository
- Downstream events:
  - `pending_invoice_rules_changed`
  - `bank_auto_tag_rules_changed` only via bank details API
  - `project_scope_changed`
  - `settings_reset_completed`
  - startup stale scan only marks stale matching dirty scopes when enabled
- Freshness rule: 设置变更完成不等于所有下游 read model fresh；必须由 dirty scope/outbox/readiness/App Status 观察收敛。

## Current Gaps To Assess Before L2

- 用户要完善的是设置 UI、访问控制、项目范围、业务规则、OA 凭据、数据重置，还是 fan-out 状态反馈。
- settings payload 是否拒绝 `bank_transaction_tags` 写入。
- OA applicant credentials 是否完全独立于普通 settings payload，且无 secret 泄露。
- 数据重置是否记录 job progress、清理 read model/cache readiness，并避免旧数据 fresh。
- 每个设置动作的 downstream dirty scopes 和文档影响是否明确。

## Risks

- 权限: admin、full access、readonly export、数据重置和 OA 凭据维护风险极高。
- 审计: 设置变更、访问控制、凭据维护、数据重置和规则保存必须审计。
- stale/fresh: 设置变更 fan-out 到多个 read model，旧 cache/readiness 不能误报 fresh。
- 跨页刷新: 几乎所有业务页面可能受设置影响。
- worker: OA sync、data reset、read model refresh 失败会导致配置和数据状态不一致。
- 导出: 访问控制变化会影响只读导出权限。
- 历史数据: 数据重置必须保留必要事实并保护禁止删除目标。

## Test Entry Points

- Backend:
  - `tests/test_app_settings_service.py`
  - `tests/test_settings_data_reset_service.py`
  - OA credential、access control、derived lifecycle 相关测试
- Frontend:
  - `web/src/test/SettingsPage.test.tsx`
- Integration candidates:
  - pending invoice rules 保存 -> dirty scopes -> pending/search/lifecycle refresh
  - data reset -> job progress -> read model/cache cleanup -> App Status reflects refreshing/stale

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖访问控制、项目范围、规则保存、数据重置保护和拒绝非法字段。
- Service-layer tests: 适用。覆盖 settings service、data reset service、credential repository、dirty fan-out/audit。
- API contract tests: 适用。覆盖 settings get/update、credential routes、reset routes、权限、错误字段。
- Read model/cache/background job tests: 适用。覆盖 settings fan-out、data reset jobs、readiness/cache cleanup、OA sync。
- Frontend component/interaction tests: 适用。覆盖设置表单、权限显示、凭据维护、数据重置、loading/error/progress。
- End-to-end business-flow integration tests: 适用。设置变更跨多个模块，至少保护一条规则保存或数据重置全链路。
- Existing feature regression tests: 适用。保护所有受设置影响的页面、权限和导出。

## Docs Impact Entry

- Module docs: `docs/modules/settings/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/platform-settings-health.md`
  - `docs/operations/data-safety.md`
  - `docs/operations/runtime-worker-governance.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/dev/api-contracts.md`
- 设置变更高概率需要同步长期文档，尤其是权限、数据重置、凭据和 fan-out。

## Legacy / Transitional Paths

- `/api/workbench/settings` 不得写 `bank_transaction_tags`；该写入只能走银行明细自动标签规则 API。
- 普通 settings payload 不得包含密码、密文或 token。
- startup stale scan 默认关闭；启用时只标记 stale workbench matching dirty scopes，不直接刷新用户可见 read model。
- 数据重置不得留下旧 read model/cache 被误判 fresh 的路径。

## L2 Questions

- 本轮完善目标是 UI、权限、规则、凭据、数据重置，还是 fan-out 状态？
- 是否有旧 settings payload 字段必须拒绝或迁移？
- 数据重置是否需要新的 dry-run、二次确认或 job progress contract？
- 设置保存后是否需要展示 downstream refresh 状态？
- OA 凭据维护是否需要更严格的审计和 secret redaction 测试？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确配置事实源、权限审计、fan-out、旧字段删除、测试矩阵和文档影响。
