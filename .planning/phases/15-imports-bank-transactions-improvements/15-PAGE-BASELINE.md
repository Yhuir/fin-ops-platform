# 银行流水导入 L1.5 页面基线卡片

## Scope

- Phase: `15-imports-bank-transactions`
- Page key: `imports-bank-transactions`
- Route: `/imports/bank-transactions`
- Page entry: `web/src/pages/ImportBankTransactionsPage.tsx`
- Shared workflow entry: `web/src/pages/ImportWorkflowPage.tsx`
- API client: `web/src/features/imports/api.ts`
- Backend entrypoints: `app/server.py` import endpoints, `app/services/import_file_service.py`, `app/services/import_processing_service.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

银行流水导入是导入源事实页面之一，负责把银行流水文件从前端导入工作流推进到后端 preview、confirm 和异步处理链路。页面本身渲染共享的 `ImportWorkflowPage`，模式为 `bank_transaction`，并在每个文件维度绑定银行账户映射后再进入 preview。

当前主链路是：

1. 前端选择文件并配置银行账户映射。
2. 调用共享导入 preview API，提交 multipart 文件和 `file_overrides`，其中 `batch_type=bank_transaction`。
3. 后端创建或恢复 `FileImportSession`，写入 preview audit 信息，返回行级预览、重复/错误统计和 stale 判定信息。
4. confirm 进入 `/imports/files/confirm`，后端返回 `202` 和后台 job 信息。
5. import worker 处理 `bank_transaction_import` / `file_import` / `import.process.requested` 后，触发银行明细、工作台匹配、关联关系、发票生命周期、成本和搜索等下游刷新。

## Cross-Page Dependencies

- Upstream: 原始银行流水文件、银行账户映射、导入 session、preview audit。
- Direct downstream:
  - `bank-details`: 银行流水事实、银行账户余额和银行明细 read model。
  - `reconciliation-workbench`: 银行流水参与匹配和工作台聚合。
  - `batch-accounting`: 依赖工作台关联关系的批量账务链路。
  - `turnover-ledger`: 外部往来款 ledger 可能依赖已入库流水和关联状态。
- Indirect downstream:
  - `pending-invoices`、`tax-offset`、`cost-statistics`、`app-health-operations`。
- Phase 0 dependency group: `Import source facts`，必须先于依赖这些源事实的页面深度实现。

## Read Model / Worker / App Status

- Direct read model: 无独立页面 read model；该页面是导入写入入口。
- Workers/jobs:
  - worker: `import`
  - durable jobs/events: `file_import`、`bank_transaction_import`、`import.process.requested`
- Downstream refresh:
  - bank detail/account balance
  - workbench/workbench relation/matching
  - invoice lifecycle/search/cost 相关派生链路
- App Status: 页面实现前必须确认导入 job、downstream dirty scope、refreshing/stale/fresh 状态在系统状态页可观测。
- Freshness rule: confirm 成功只代表导入 job 已入队或已完成提交，不代表所有下游 read model 已 fresh；页面完成态不能误导用户认为所有依赖页面已刷新完成。

## Current Gaps To Assess Before L2

- 用户可见的 preview stale、重复文件、重复流水、错误行和账户映射缺失提示是否足够明确。
- 多文件导入时，每个文件的账户映射、preview 结果和 confirm 状态是否可追踪。
- confirm 后的 job 反馈是否能区分导入处理完成、下游刷新中、下游刷新失败。
- 下游页面刷新策略是否有明确入口，避免用户跳转到银行明细或关联台时看到旧数据却被标记为 fresh。
- 旧版 `/imports/preview`、`/imports/confirm` 是否仍被必要测试或兼容调用使用；如要移除必须先确认替代链路和回归覆盖。

## Risks

- 权限: 导入、预览、确认、下载错误明细和查看历史导入记录可能需要不同权限。
- 审计: preview audit、confirm audit、导入批次、原始文件引用和错误行必须可追溯。
- stale/fresh: confirm 与下游 read model fresh 之间存在异步窗口。
- 跨页刷新: 银行明细、关联台、批量账务、外部往来款和成本统计都可能读取导入结果。
- worker: import job 失败、重复入队、部分文件成功、部分文件失败需要明确恢复策略。
- 导出: 错误行、导入结果、重复流水导出字段不能破坏现有格式。
- 历史数据: 重复检测和幂等处理不能因为新增字段或 UI 改动而改变历史批次语义。

## Test Entry Points

- Backend:
  - `tests/test_import_*`
  - import file/preview/confirm/service/worker 相关测试
  - 下游 dirty scope/read model refresh 相关测试
- Frontend:
  - `web/src/test/ImportsApi.test.ts`
  - `web/src/test/ImportCenterPage.test.tsx`
  - import workflow 相关组件测试
- E2E/integration candidates:
  - 银行流水导入 -> confirm job -> 银行明细刷新 -> 关联台可见
  - 重复文件/重复流水 -> preview warning -> confirm 阻断或幂等处理

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖重复检测、账户映射、行级校验、stale session 和幂等语义。
- Service-layer tests: 适用。覆盖导入 session、preview audit、confirm、job 入队、dirty scope fan-out。
- API contract tests: 适用。覆盖 preview/confirm 成功、错误、stale、重复、权限和 job response shape。
- Read model/cache/background job tests: 适用。覆盖 import worker、downstream dirty scopes、freshness/status。
- Frontend component/interaction tests: 适用。覆盖文件选择、账户映射、preview、confirm、错误反馈、job 状态。
- End-to-end business-flow integration tests: 适用。至少保护导入到银行明细/关联台可见的关键路径。
- Existing feature regression tests: 适用。旧导入 API、历史批次、导出、下游列表不变空都要保护。

## Docs Impact Entry

- Module docs: `docs/modules/imports-bank-transactions/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/imports/`
  - `docs/app-architecture/`
  - `docs/dev/`
  - `docs/operations/runtime-worker-governance.md`
- L2 实施前必须做 docs impact assessment；若只调整内部实现且不改变接口/状态/事实源，最终可说明 docs 不适用。

## Legacy / Transitional Paths

- 旧版 `/imports/preview`、`/imports/confirm` 仍作为程序化或回归入口存在，不能在 L2 中直接删除。
- 如要移除旧链路，必须先证明共享 `/imports/files/preview` 与 `/imports/files/confirm` 已覆盖全部调用点、测试和文档，并同步删除旧测试依赖。
- 禁止在旧 API 上继续堆新业务逻辑；新逻辑应沉淀到共享 import service/worker 边界。

## L2 Questions

- 页面完善的首要目标是 UX 可见性、导入准确性、异步状态反馈，还是下游刷新闭环？
- confirm 后是否需要页面内等待下游 read model fresh，还是只提供 job 状态和跳转提示？
- 账户映射缺失或历史账户配置变化时，是否允许保存草稿 session？
- 多文件部分失败时，用户期望是整批回滚、成功项保留，还是逐文件重试？
- 是否要同步清理旧 import endpoint；如果需要，替代 API、测试和文档的迁移顺序是什么？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先在本 phase 内补齐 `CONTEXT.md` / `RESEARCH.md` / `PLAN.md` 或等价 GSD 文档，并明确：

- 用户要完善的具体功能和验收标准。
- 受影响 API contract、worker、read model、权限和审计。
- 旧逻辑是否迁移或删除，删除顺序和测试保护。
- 最小可验证切片，以及实现后需要回写的长期文档。
