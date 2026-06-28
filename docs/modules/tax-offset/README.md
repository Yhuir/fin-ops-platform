# 税金抵扣 模块维护入口


- Module key: `tax-offset`
- 类型: 页面模块
- Route: `/tax-offset`
- Page key: `tax-offset`

## 修改前必读

- `docs/product-specs/cost-tax.md`
- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/components/tax/*`
- `web/src/features/tax/api.ts`
- `backend/src/fin_ops_platform/app/routes_tax.py`
- `backend/src/fin_ops_platform/services/tax_offset_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_runtime_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_application_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_job_service.py`

## 当前边界

关注发票认证、可抵扣试算、已认证导入、计划保存、direct API rows/summary 和认证导入结果。发票生命周期状态由 `InvoiceLifecyclePolicy` 和各页面 direct query/service 分发，税金抵扣页面不私有定义认证状态。

当前页面通过 `/api/tax-offset?month=...` 直接读取后端组装 payload；后端 query service 不再读取 SQL/read-model fresh gate，前端不消费 `read_model_status`、scope key、generated-at 或 stale reasons，不展示 read model 刷新面板，不因旧 freshness 字段禁用保存，也不自动轮询等待 fresh。计划保存只使用 direct payload source versions（存在时）和幂等 key 作为并发输入，不再校验 read-model scope。

后端 `tax_offset` read-model refresh worker lane 已删除：不再注册 `tax-offset` / `cost-tax` worker，不再投递 `tax_offset.read_model.refresh`，App Status 不再绑定税金 read-model readiness。旧 cost/tax SQL projection 已删除；历史 SQL 表仅作为迁移清理对象。页面读取仍由 direct API 组装。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或 direct payload 字段变化。
- 业务状态、UI 状态、派生数据状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、affected scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `e2e-spec.md`：维护 Spec-first Browser E2E 验收合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/Vitest/API/integration 的覆盖映射。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
