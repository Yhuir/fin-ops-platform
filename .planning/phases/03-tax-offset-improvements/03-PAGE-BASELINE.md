# 税金抵扣 L1.5 页面基线卡片

## Scope

- Phase: `03-tax-offset-improvements`
- Page key: `tax-offset`
- Route: `/tax-offset`
- Page entry: `web/src/pages/TaxOffsetPage.tsx`
- API client: `web/src/features/tax/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/routes_tax.py`, `backend/src/fin_ops_platform/app/server.py` `/api/tax-offset*`
- Core services: `tax_offset_service.py`, `tax_offset_runtime_service.py`, `tax_offset_read_model_service.py`, `tax_offset_read_model_refresh.py`, `tax_certified_import_*`, `cost_tax_sql_projection.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

税金抵扣关注发票认证、可抵扣试算、已认证导入、计划保存、read model freshness 和认证导入结果。发票生命周期状态由 `InvoiceLifecyclePolicy` / `invoice_lifecycle` read boundary 分发，税金抵扣页面不私有定义认证状态。

当前关键边界：

1. 列表和汇总依赖 `tax_offset` read model 与 `invoice_lifecycle` 状态。
2. 已认证导入和计划保存会写入税务相关 lifecycle/fact，并触发 downstream refresh。
3. 生产刷新由专用 `tax-offset` consumer 承担；旧 `cost-tax` combined worker 只作为兼容消费者。
4. `invoice_lifecycle-secondary` 用于多月份 scope 收敛，不能用页面本地状态替代。

## Cross-Page Dependencies

- Upstream:
  - `imports-invoices`
  - `imports-etc-invoices`
  - `input-invoice-usage`
  - `output-invoice-collections`
  - `reconciliation-workbench`
- Downstream:
  - `cost-statistics`
  - `app-health-operations`
  - 发票生命周期相关页面的状态观察
- Phase 0 dependency group: `Invoice lifecycle and tax`，同时受 `ETC chain` 影响。

## Read Model / Worker / App Status

- Read models: `tax_offset`, `invoice_lifecycle`
- Workers: `tax-offset`, `invoice-lifecycle`, `invoice-lifecycle-secondary`
- Compatibility worker: `cost-tax`
- Related jobs: `tax_offset.read_model.refresh`, `invoice_lifecycle.read_model.refresh`
- Freshness rule: 税金抵扣页面读取必须经过 read model freshness/source-version gate；认证导入或计划写入后不能只更新前端本地状态。

## Current Gaps To Assess Before L2

- 用户要完善的是认证导入、抵扣试算、计划保存、筛选/导出、状态诊断，还是 worker 性能。
- 页面是否完整展示 `tax_offset` 与 `invoice_lifecycle` 的 stale/refreshing/missing 状态。
- 已认证导入 job 结果、错误行、重复认证和幂等语义是否清楚。
- 与 output invoice collection、input usage 和 cost statistics 的状态传播是否有测试保护。
- 旧 `cost-tax` worker 兼容边界是否仍被误认为主刷新 lane。

## Risks

- 权限: 查看税务数据、导入认证结果、保存计划、导出需要权限分层。
- 审计: 认证导入、计划保存、人工调整和导出需要可追溯。
- stale/fresh: `tax_offset` 与 `invoice_lifecycle` 任一 stale 都会影响页面判断。
- 跨页刷新: 发票导入、销项收款、进项使用、成本统计与 ETC 导入均可能影响税金抵扣。
- worker: 专用 `tax-offset` consumer 和 lifecycle secondary 的失败会造成跨月收敛延迟。
- 导出: 税金抵扣导出字段、筛选、认证状态和金额口径必须回归。
- 历史数据: 历史认证结果、红蓝票、ETC 发票同步和旧计划不能被新 UI 状态覆盖。

## Test Entry Points

- Backend:
  - `tests/test_tax_offset_*`
  - tax certified import、tax offset read model、invoice lifecycle 相关测试
- Frontend:
  - `web/src/test/TaxOffsetPage.test.tsx`
- Integration candidates:
  - 发票导入 -> invoice lifecycle fresh -> tax offset refresh -> 抵扣列表可见
  - 已认证导入 -> job 完成 -> tax offset/invoice lifecycle fresh -> 页面状态更新

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖认证状态、可抵扣金额、计划保存、重复认证和红蓝票边界。
- Service-layer tests: 适用。覆盖 tax offset service、certified import job、read model refresh、audit。
- API contract tests: 适用。覆盖列表/汇总/导入/计划/导出 response shape、权限、stale/status。
- Read model/cache/background job tests: 适用。覆盖 `tax_offset`、`invoice_lifecycle`、`tax-offset` worker 和 compatibility worker。
- Frontend component/interaction tests: 适用。覆盖 loading/empty/error/stale、导入、计划保存、筛选、导出。
- End-to-end business-flow integration tests: 适用。保护发票导入或认证导入到税金抵扣可见的关键路径。
- Existing feature regression tests: 适用。保护发票生命周期、销项收款、进项使用、成本统计和旧 worker 行为。

## Docs Impact Entry

- Module docs: `docs/modules/tax-offset/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/cost-tax.md`
  - `docs/product-specs/invoice-lifecycle.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- 涉及税务口径、状态机、worker lane 或 API contract 时必须同步长期文档。

## Legacy / Transitional Paths

- `cost-tax` combined worker 是兼容消费者，不应作为新增能力的唯一性能 lane。
- 页面不得私有定义认证状态或抵扣状态。
- 不得在请求线程同步 live rebuild 并伪装 fresh。

## L2 Questions

- 本轮完善目标是认证导入、计划保存、抵扣列表、导出，还是状态可观测？
- `tax_offset` 与 `invoice_lifecycle` 两类 stale 如何在 UI 上区分？
- 已认证导入是否需要幂等键、批次版本或错误明细下载？
- 旧 `cost-tax` worker 是否需要清理配置或文档去歧义？
- 下游成本统计刷新失败时，税金抵扣页面是否显示诊断或阻断后续计划保存？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确税务状态口径、read model/worker、权限审计、旧兼容路径、测试矩阵和文档影响。
