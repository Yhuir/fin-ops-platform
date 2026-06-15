# 进项发票使用情况 L1.5 页面基线卡片

## Scope

- Phase: `07-input-invoice-usage-improvements`
- Page key: `input-invoice-usage`
- Route: `/input-invoice-usage`
- Page entry: `web/src/pages/InputInvoiceUsagePage.tsx`
- API client: `web/src/features/inputInvoiceUsage/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/server.py` `/api/input-invoice-usage*`
- Core services: `input_invoice_usage_service.py`, `input_invoice_usage_oa_reverse_service.py`, `workbench_relation_read_facade.py`, `oa_applicant_credentials.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

进项发票使用情况关注进项发票使用状态、筛选、导出、OA 反查、以发票反提 OA 和 invoice usage read model。关系证据来自 `WorkbenchRelationReadFacade` / `DistributedInvoiceRelationContext`，页面读路径不直接调用 `WorkbenchRelationCommandService`。

当前关键边界：

1. `以发票反提 OA` 由 FinOps 使用目标 OA 申请人的已配置凭据创建 OA 暂存草稿，OA 提交由用户在 OA 系统中手动完成。
2. OA reverse batch 只记录本地流程状态；OA/发票 relation 事实必须通过 `WorkbenchRelationCommandService` 写入 `input_invoice_oa_reverse`。
3. linked 或 candidate relation 中多条 OA、银行流水或进项发票必须聚合为一条使用情况行，用 `+N` 和 relation details 展开。
4. `relationStatus='candidate'` 只能作为候选证据展示；支付/已确认判断只能使用 `linked` 关系。
5. row relation details 在 SQL read model 可用时按 row id 展开，不得触发全量 live rebuild。

## Cross-Page Dependencies

- Upstream:
  - `imports-invoices`
  - `pending-invoices`
  - `reconciliation-workbench`
  - `oa-pending-payments`
  - OA 凭据/申请人配置
- Downstream:
  - `tax-offset`
  - `cost-statistics`
  - `app-health-operations`
  - 关联台和 invoice lifecycle 观察页面
- Phase 0 dependency group: `Invoice lifecycle and tax`。

## Read Model / Worker / App Status

- Read models: `input_invoice_usage`, `invoice_lifecycle`
- Worker: `invoice-usage-collection`
- Related read model: `workbench_relation`
- Related dependencies: OA applicant credentials, `DistributedInvoiceRelationContext`
- Freshness rule: read model missing/stale/source mismatch 时，详情 API 应返回 refreshing/unavailable 并入队刷新；不能 live rebuild 后伪装 fresh。

## Current Gaps To Assess Before L2

- 用户要完善的是列表筛选、导出、关系详情、OA 反查，还是以发票反提 OA。
- relation 聚合、`relationCount`、`detailMode=list`、`summaries` 和 `invoiceRelations` 是否覆盖多关系展示。
- OA reverse 凭据、权限、安全边界和本地确认历史是否完整。
- candidate 与 linked 状态是否在 UI/API 中被正确区分。
- 是否存在页面直接读取候选表或自行拼候选的旧逻辑；L2 必须移除。

## Risks

- 权限: 查看发票使用、导出、OA 反查、创建 OA 草稿、查看关系详情需要权限和凭据边界。
- 审计: OA reverse、关系写入、本地确认、导出和凭据使用需要审计。
- stale/fresh: input usage、invoice lifecycle、workbench relation 任何 stale 都会影响使用状态。
- 跨页刷新: pending invoices、OA pending payments、tax offset、cost statistics 和关联台受影响。
- worker: `invoice-usage-collection` refresh 失败会导致列表/详情不可用。
- 导出: 多关系聚合、金额合计和候选/已确认状态需要保护。
- 历史数据: candidate 关系不能被当作已支付或已确认事实。

## Test Entry Points

- Backend:
  - `tests/test_input_invoice_usage_*`
  - `tests/test_invoice_usage_collection_*`
  - OA reverse、relation details、read model refresh 相关测试
- Frontend:
  - `web/src/test/InputInvoiceUsage*.test.tsx`
- Integration candidates:
  - pending invoice attach -> Workbench relation fresh -> input usage 聚合行更新
  - invoice reverse OA -> OA draft 创建 -> 本地历史 -> relation facts 分发

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖 relation 聚合、candidate/linked 判定、OA reverse 状态和凭据边界。
- Service-layer tests: 适用。覆盖 input usage service、OA reverse service、relation facade、read model refresh。
- API contract tests: 适用。覆盖列表、relation details、OA reverse、导出、权限/stale/unavailable。
- Read model/cache/background job tests: 适用。覆盖 `input_invoice_usage`、`invoice_lifecycle`、`invoice-usage-collection`。
- Frontend component/interaction tests: 适用。覆盖筛选、导出、`+N` 详情、OA reverse、loading/error/stale。
- End-to-end business-flow integration tests: 适用。保护发票关系到进项使用展示的关键路径。
- Existing feature regression tests: 适用。保护待找发票、OA待付款、税金抵扣、关联台和旧导出。

## Docs Impact Entry

- Module docs: `docs/modules/input-invoice-usage/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/invoice-lifecycle.md`
  - `docs/app-architecture/pages.md`
  - `docs/dev/api-contracts.md`
  - OA reverse 相关设计文档
- 涉及 OA reverse 时还必须维护 `oa-reverse-design.md` 和 `oa-reverse-implementation-plan.md`。

## Legacy / Transitional Paths

- 页面不得直接读取关联台候选表或自行拼候选。
- 读路径不直接调用 command service；写 relation 必须通过明确 OA reverse/command service 边界。
- row detail 不得触发全量 live rebuild。

## L2 Questions

- 本轮完善目标是关系详情、导出、OA reverse，还是 read model 状态可见性？
- OA reverse 是否需要新的凭据校验、幂等键或本地历史状态机？
- 多关系聚合的 `+N` 展示是否需要统一组件或 API shape 调整？
- candidate 关系在筛选和导出中如何呈现？
- 是否存在旧候选读取或 direct relation 拼接代码必须删除？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确 invoice usage/read model、OA reverse、权限审计、旧逻辑删除、测试矩阵和文档影响。
