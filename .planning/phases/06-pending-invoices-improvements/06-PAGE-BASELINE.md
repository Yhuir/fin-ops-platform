# 待找发票 L1.5 页面基线卡片

## Scope

- Phase: `06-pending-invoices-improvements`
- Page key: `pending-invoices`
- Route: `/pending-invoices`
- Page entry: `web/src/pages/PendingInvoicesPage.tsx`
- API client: `web/src/features/pendingInvoices/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/routes_pending_invoices.py`, `backend/src/fin_ops_platform/app/server.py` `/api/pending-invoices*`
- Core services: `pending_invoice_service.py`, `pending_invoice_read_model_service.py`, `pending_invoice_rules_application_service.py`, `pending_invoice_lifecycle_service.py`, `search_pending_sql_projection.py`, `invoice_lifecycle_sql_projection.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

待找发票关注支出/收入流水、进项/销项发票、规则建议、选择已有发票、收入状态批量标记、搜索/read model 状态和 invoice lifecycle 分发。发票获取状态由 `InvoiceLifecyclePolicy` / `invoice_lifecycle` read boundary 与 pending invoice read model 共同表达，页面不私有定义状态。

当前关键边界：

1. 列表父筛选以最终 `invoice_acquisition_status.code` 为事实源。
2. `requires_invoice` 是“需要开票”状态桶，不等同于 `filter_group='requires_invoice'`。
3. OA/流水/发票配对关系不属于待找发票页面私有状态，读写必须走 Workbench relation facade/command service。
4. 选择已有进项发票只从表格上方选中流水工具栏进入；行内三点菜单和“补票”不是当前 UI/HTTP 契约。
5. 收入批量状态写入必须先全量校验再一次性写 command/audit/finalizer，不能逐行循环造成半成功。

## Cross-Page Dependencies

- Upstream:
  - `imports-bank-transactions`
  - `imports-invoices`
  - `reconciliation-workbench`
  - `bank-details`
- Downstream:
  - `input-invoice-usage`
  - `output-invoice-collections`
  - `tax-offset`
  - `cost-statistics`
  - `app-health-operations`
- Phase 0 dependency group: `Invoice lifecycle and tax`。

## Read Model / Worker / App Status

- Read models: `pending_invoice`, `search`, `invoice_lifecycle`
- Workers: `pending-invoice`, `search`, `invoice-lifecycle`, `invoice-lifecycle-secondary`
- Compatibility worker: `search-pending`
- Related relation read model: `workbench_relation`
- Freshness rule: 普通 relation read model 非 fresh 只影响读侧 freshness 和候选展示；写 API 阻断条件来自权限/session、DB/目标写模型、canonical relation version/idempotency/row occupation 冲突。

## Current Gaps To Assess Before L2

- 用户要完善的是规则建议、选择已有发票、收入批量标记、筛选/搜索、详情，还是 read model 状态。
- 页面是否把 `filter_group` 与最终 acquisition status 混用。
- 批量选择已有进项发票 drawer 的 candidates/preview/confirm contract 是否完整。
- 收入批量状态写入是否全量校验并一次性提交。
- 历史 manual invoice command/service 是否仍从 HTTP/UI 暴露；如有必须移除。

## Risks

- 权限: 查看、批量选择发票、收入状态标记、规则配置、导出需要权限分层。
- 审计: 发票选择、收入状态批量写入、规则建议接受/拒绝和撤销需要可追溯。
- stale/fresh: pending invoice、search、invoice lifecycle、workbench relation 状态不同步会影响候选和筛选。
- 跨页刷新: 关联台、进项使用、销项收款、税金抵扣和成本统计都受影响。
- worker: `pending-invoice`、`search`、`invoice-lifecycle` worker 失败会造成状态不可用。
- 导出: 筛选、搜索和状态字段需要保护。
- 历史数据: 旧 manual invoice 兼容事实不能重新成为新写入口。

## Test Entry Points

- Backend:
  - `tests/test_pending_invoice_*`
  - pending invoice read model、rules、lifecycle、relation command 相关测试
- Frontend:
  - `web/src/test/PendingInvoices*.test.tsx`
- Integration candidates:
  - 支出流水 -> 选择已有进项发票 -> Workbench relation fresh -> pending/input usage 更新
  - 收入流水多选 -> income statuses 一次性写入 -> lifecycle/read model fresh

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖 acquisition status、规则命中、批量校验、重复选择和非法状态。
- Service-layer tests: 适用。覆盖 pending service、rules service、lifecycle、relation command/audit。
- API contract tests: 适用。覆盖列表、filter-options、candidates/preview/confirm、income statuses、权限/stale。
- Read model/cache/background job tests: 适用。覆盖 `pending_invoice`、`search`、`invoice_lifecycle` workers。
- Frontend component/interaction tests: 适用。覆盖筛选/搜索、批量选择、drawer、空/错/stale、批量状态写入。
- End-to-end business-flow integration tests: 适用。保护选择已有发票到生命周期状态更新的关键路径。
- Existing feature regression tests: 适用。保护关联台、进项使用、销项收款、税金抵扣和旧状态筛选。

## Docs Impact Entry

- Module docs: `docs/modules/pending-invoices/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/invoice-lifecycle.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/app-architecture/pages.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- 涉及状态口径、批量写入、relation command 或 read model worker 时必须同步长期文档。

## Legacy / Transitional Paths

- 历史 manual invoice command/service 只保留旧数据恢复和迁移兼容事实，不再通过 HTTP API 或 UI 暴露新写入口。
- 页面不得私有定义发票获取状态。
- GET/read 路径不得通过旧事实 live scan 伪装 fresh。

## L2 Questions

- 本轮完善目标是选择已有发票、收入状态批量标记、筛选搜索，还是 stale 状态展示？
- 批量 candidates/preview/confirm 是否需要新增 expected versions 或幂等键？
- 收入状态写入失败时是整批回滚还是部分成功；当前要求应倾向一次性校验和提交。
- relation non-fresh 时 UI 如何提示候选可能不完整？
- 是否要先删除某个旧 manual invoice UI/API 调用点？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确状态口径、relation/read model 边界、权限审计、旧逻辑删除、测试矩阵和文档影响。
