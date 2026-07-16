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
- `backend/src/fin_ops_platform/services/tax_offset_read_model_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_application_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_job_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_sql_projection.py`

## 当前边界

关注发票认证、可抵扣试算、已认证导入、计划保存、read model freshness 和认证导入结果。发票生命周期状态由 `InvoiceLifecyclePolicy` / `invoice_lifecycle` read boundary 分发，税金抵扣页面不私有定义认证状态。

生产刷新由专用 `tax-offset` RabbitMQ consumer 承担独立性能 lane；旧 `cost-tax` combined worker 保留为兼容消费者，不再是唯一性能 lane。当前 P2/P3 closure 按首屏 API 或 direct refresh p95 <= 1000ms 验收，写操作链路还要求 operation-to-fresh p99 <= 3000ms。`invoice_lifecycle` 另有 `invoice-lifecycle-secondary` 并发消费者用于多月份 scope 收敛；所有 read model freshness 仍以 durable queue/readiness 为事实源。

2026-07-16 起税金 SQL projection 的唯一 owner 是 `tax_offset_sql_projection.py`。旧混合 `cost_tax_sql_projection.py` 已删除；成本 builder 位于独立的成本模块，生产 worker 只做两个明确 import。该所有权拆分不改变税金 SQL、payload、Redis、read model、queue、worker event 或页面/API。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `e2e-spec.md`：维护 Spec-first Browser E2E 验收合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/Vitest/API/integration 的覆盖映射。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
