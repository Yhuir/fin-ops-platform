# 发票导入 L1.5 页面基线卡片

## Scope

- Phase: `16-imports-invoices`
- Page key: `imports-invoices`
- Route: `/imports/invoices`
- Page entry: `web/src/pages/ImportInvoicesPage.tsx`
- Shared workflow entry: `web/src/pages/ImportWorkflowPage.tsx`
- API client: `web/src/features/imports/api.ts`
- Backend entrypoints: `app/server.py` import endpoints, `app/services/import_file_service.py`, `app/services/import_processing_service.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

发票导入是进项、销项和生命周期事实的源头页面。页面渲染共享 `ImportWorkflowPage`，模式为 `invoice`，由同一套文件导入工作流处理文件选择、发票类型、preview、重复审计、confirm、job feedback 和 session 恢复。

当前主链路是：

1. 前端选择发票文件并设置每个文件的 `input_invoice` 或 `output_invoice` 类型。
2. preview 调用共享 `/imports/files/preview`，multipart 中携带文件和 `file_overrides`，包括 `template_code=invoice_export` 和 `batch_type`。
3. 后端创建 `FileImportSession`，记录 `ImportPreviewAuditCounts`，返回预览行、重复/错误统计和 stale 状态。
4. confirm 调用 `/imports/files/confirm`，进入 `file_import` / `invoice_import` / `import.process.requested` 异步处理。
5. import worker 完成标准化和持久化后触发 `invoice_import_confirmed` 生命周期事件，并驱动待找发票、税金抵扣、进项使用、销项收款、OA待付款、关联台、成本和搜索等下游 read model。

## Cross-Page Dependencies

- Upstream: 发票文件、发票类型选择、导入 session、preview audit。
- Direct downstream:
  - `pending-invoices`
  - `input-invoice-usage`
  - `output-invoice-collections`
  - `oa-pending-payments`
  - `tax-offset`
  - `reconciliation-workbench`
- Indirect downstream:
  - `cost-statistics`
  - `turnover-ledger`
  - `app-health-operations`
- Phase 0 dependency group: `Import source facts`，是发票生命周期和税务链路的前置事实入口。

## Read Model / Worker / App Status

- Direct read model: 无独立页面 read model；该页面写入发票源事实并触发生命周期派生。
- Workers/jobs:
  - worker: `import`
  - durable jobs/events: `file_import`、`invoice_import`、`import.process.requested`
- Downstream refresh:
  - `invoice_lifecycle`
  - `pending_invoice`
  - `input_invoice_usage`
  - `output_invoice_collection`
  - `oa_pending_payment`
  - `tax_offset`
  - `workbench` / `workbench_relation`
  - `cost_statistics`
  - `search`
- Freshness rule: confirm 完成不等于所有发票生命周期派生完成；页面必须避免把异步 fan-out 的中间态展示为最终 fresh。

## Current Gaps To Assess Before L2

- 发票类型选择、模板识别、重复发票和错误行提示是否能支持多文件批量导入。
- preview stale 后的恢复、重试和 session 清理是否对用户可理解。
- confirm 后是否有足够的 job 状态和下游刷新提示。
- 进项/销项导入对不同下游页面的影响是否在 UI、文档和测试中被明确。
- 旧 `/imports/preview`、`/imports/confirm` 调用是否仍有兼容价值；新增逻辑不得继续扩大旧入口职责。

## Risks

- 权限: 发票导入、预览、确认、错误导出、历史批次查看可能分属不同权限。
- 审计: 原始文件、导入批次、发票号码、重复判断、confirm 操作和后台 job 必须可追溯。
- stale/fresh: 发票生命周期链路长，多个页面会在 refresh 中间态读取数据。
- 跨页刷新: 待找发票、税金抵扣、进项使用、销项收款、OA待付款、成本统计和关联台都依赖发票事实。
- worker: import worker、生命周期 worker、搜索 worker 的失败和重试不能造成半更新事实。
- 导出: 错误明细、重复明细和导入结果导出字段需要保护。
- 历史数据: 重复发票、红冲/作废、历史批次和旧模板兼容不能被 UI 调整改写语义。

## Test Entry Points

- Backend:
  - `tests/test_import_*`
  - invoice import / import processing / lifecycle refresh 相关测试
  - 下游 read model dirty scope 和 App Status 相关测试
- Frontend:
  - `web/src/test/ImportsApi.test.ts`
  - import workflow 和发票导入页面相关测试
- E2E/integration candidates:
  - 发票导入 -> confirm -> 待找发票/税金抵扣/进项使用页面刷新可见
  - stale preview -> confirm 阻断 -> 重新 preview 后成功 confirm

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖发票类型、重复判断、模板识别、金额/税额边界、stale session。
- Service-layer tests: 适用。覆盖 session、preview audit、confirm、job 入队、生命周期 fan-out。
- API contract tests: 适用。覆盖 preview/confirm response shape、错误字段、权限、stale、重复和 job 字段。
- Read model/cache/background job tests: 适用。覆盖 import worker、invoice lifecycle、下游 dirty scopes 和 freshness。
- Frontend component/interaction tests: 适用。覆盖文件类型选择、preview、错误/空态、confirm、job 状态和重试。
- End-to-end business-flow integration tests: 适用。至少保护导入发票后关键下游页面可见。
- Existing feature regression tests: 适用。保护旧 API、旧模板、旧导出、旧下游列表和权限行为。

## Docs Impact Entry

- Module docs: `docs/modules/imports-invoices/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/imports/`
  - `docs/product-specs/invoices/`
  - `docs/app-architecture/`
  - `docs/dev/`
  - `docs/operations/runtime-worker-governance.md`
- L2 实施前必须明确是否更新发票生命周期、API contract、worker 或下游页面文档。

## Legacy / Transitional Paths

- 旧版 `/imports/preview`、`/imports/confirm` 仍作为兼容入口存在，不能在未审计调用点前删除。
- `ImportWorkflowPage` 是共享入口，不能为发票导入单独复制一套独立流程。
- 新功能应沉淀在 import file service、processing service、生命周期刷新和明确 API contract 中；禁止通过页面本地分支掩盖后端契约缺口。

## L2 Questions

- 页面完善目标是更强的 preview 审计、导入状态可见性、发票类型体验，还是下游刷新闭环？
- 是否需要在 confirm 后展示每个下游 read model 的刷新状态，还是只展示导入 job 状态？
- 多文件混合进项/销项时，失败恢复和重试单位是文件、批次还是行？
- 重复发票策略是否允许用户覆盖、跳过或仅阻断？
- 是否要对旧 import endpoint 做迁移或删除；如需要，哪些调用点和测试先迁移？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先在本 phase 内补齐 `CONTEXT.md` / `RESEARCH.md` / `PLAN.md` 或等价 GSD 文档，并明确：

- 目标用户故事、API contract 和验收标准。
- 受影响的发票生命周期、worker、read model、权限和审计。
- 旧逻辑迁移/删除策略。
- 测试矩阵和文档更新范围。
