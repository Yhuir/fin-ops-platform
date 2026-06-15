# ETC 票据管理 L1.5 页面基线卡片

## Scope

- Phase: `12-etc-tickets-improvements`
- Page key: `etc-tickets`
- Route: `/etc-tickets`
- Page entry: `web/src/pages/EtcTicketManagementPage.tsx`
- API client: `web/src/features/etc/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/server.py` `/api/etc*`
- Core services: `etc_service.py`, `etc_business_batch_application_service.py`, `etc_reconciliation_service.py`, `workbench_relation_command_service.py`, `historical_etc_repair_service.py`, `existing_etc_batch_link_service.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

ETC 票据管理关注 ETC 票据、人工业务批次、导入草稿、OA 提交人工确认、source files、reconciliation task workflow、业务批次删除/reset，以及提交后在关联台的 `etc_invoice_summary` 投影。

当前关键边界：

1. 用户可见事实源是 `/api/etc/business-batches*` 与 `etc_business_batches`；`etc_reconciliation_tasks` 保留为导入、核对、source file 和 workflow 状态。
2. 新建批次走 `POST /api/etc/business-batches`，后端 application service 编排 task + active business batch 并返回统一 payload。
3. 没有 active business batch 绑定的 task-only 记录不得进入左侧批次列表或 tab 计数。
4. 旧 `/api/etc/batches*` 只作为过渡兼容入口，不应新增能力。
5. 已提交批次删除/reset 必须先通过 Workbench relation command boundary 的 canonical write safety。

## Cross-Page Dependencies

- Upstream:
  - `imports-etc-invoices`
  - source file/object storage
  - ETC reconciliation tasks
- Direct downstream:
  - `reconciliation-workbench`: `etc_invoice_summary` open projection 和 active relation 取消。
  - `tax-offset`: ETC 发票同步后参与抵扣。
  - `cost-statistics`: ETC 成本归集。
  - `app-health-operations`: import/Workbench/ETC worker 状态。
- Related:
  - `input-invoice-usage`
  - `pending-invoices`
- Phase 0 dependency group: `ETC chain`。

## Read Model / Worker / App Status

- Direct App Status read model: 无独立 ETC 票据 read model；依赖 ETC service/business batch facts 和下游 read models。
- Worker/jobs:
  - import worker / `etc_invoice_import`
  - Workbench relation worker
  - downstream tax/cost lifecycle workers
- Related facts: `etc_business_batches`, `etc_reconciliation_tasks`, source files, Workbench relation
- Freshness rule: `submitted` 只表示 ETC 批次已人工确认提交，不等于关联台三项已配对；domain event 只作页面刷新提示，不是 relation 事实源。

## Current Gaps To Assess Before L2

- 用户要完善的是业务批次列表、新建批次、source files、OA 人工确认、删除/reset、历史迁移，还是关联台投影。
- task-only 记录是否仍出现在用户可见列表或计数中。
- 删除/reset 是否在本地修改前完成 Workbench relation canonical write safety。
- source file 上传是否做到对象存储成功后才追加元数据。
- 旧 `/api/etc/batches*` 是否仍被 UI 或测试调用；L2 必须确认迁移策略。

## Risks

- 权限: 查看/新建批次、上传 source file、人工 OA 状态、删除/reset、历史迁移需要权限分层。
- 审计: 批次创建、OA 状态、source file、删除/reset、历史迁移和 relation 写入都需审计。
- stale/fresh: ETC 批次状态、Workbench relation、tax/cost 下游可能不同步。
- 跨页刷新: ETC 导入、业务批次提交/删除、历史迁移影响关联台、税金抵扣、成本统计和搜索。
- worker: import、Workbench relation、tax/cost worker 失败会导致用户看到半闭环状态。
- 导出: 如有票据/批次导出，字段和状态口径需保护。
- 历史数据: 历史 repair/migration 必须通过 command service，不能 direct pair mutation。

## Test Entry Points

- Backend:
  - `tests/test_etc_*`
  - `tests/test_etc_backend.py`
  - ETC business batch、source file、delete/reset、historical migration、relation command 相关测试
- Frontend:
  - `web/src/test/Etc*.test.tsx`
  - `web/src/test/EtcApi.test.ts`
- Integration candidates:
  - ETC import -> business batch visible -> manual submitted -> Workbench summary visible
  - submitted batch delete/reset -> relation safety -> Workbench active relation canceled

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖 business batch 状态、task-only 隐藏、manual OA status、delete/reset 规则。
- Service-layer tests: 适用。覆盖 application service、source file persistence、historical repair/migration、command service 委托。
- API contract tests: 适用。覆盖 business-batches、manual-oa-status、source files、delete/reset、权限和错误。
- Read model/cache/background job tests: 适用。覆盖 import job、Workbench relation refresh、tax/cost downstream。
- Frontend component/interaction tests: 适用。覆盖批次列表、tab 计数、source file、OA 状态、删除/reset、错误/stale。
- End-to-end business-flow integration tests: 适用。保护 ETC 导入到票据管理再到关联台/税金/成本的关键路径。
- Existing feature regression tests: 适用。保护旧 ETC API 兼容、导入、关联台、税金抵扣、成本统计和历史迁移。

## Docs Impact Entry

- Module docs: `docs/modules/etc-tickets/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/imports-and-etc.md`
  - `docs/operations/etc-business-batches.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/dev/api-contracts.md`
- 涉及业务批次、source file、OA 状态、删除/reset 或 relation 投影时必须同步长期文档。

## Legacy / Transitional Paths

- 旧 `/api/etc/batches*` 只保留过渡兼容，不新增能力。
- ETC 专用 OA 自动检测链路已移除；创建 OA 草稿后只允许人工确认 submitted/not_submitted。
- historical repair/migration/existing batch link 必须通过 `WorkbenchRelationCommandService`；缺 command service fail fast。
- task-only 记录不得作为用户可见批次事实。

## L2 Questions

- 本轮完善目标是业务批次 UX、source file、OA 人工确认、删除/reset，还是旧 API 迁移？
- 是否必须先清理旧 `/api/etc/batches*` 调用点？
- 删除/reset 是否需要 operation overlay 和哪些 freshness targets？
- source file 对象存储失败如何向用户反馈并保证无半写？
- submitted 与三项 paired 的差异是否需要在 UI 中更明确？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确 ETC business batch、relation command、source file、权限审计、旧逻辑删除、测试矩阵和文档影响。
