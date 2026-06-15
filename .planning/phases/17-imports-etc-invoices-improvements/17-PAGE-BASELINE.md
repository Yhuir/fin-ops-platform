# ETC 发票导入 L1.5 页面基线卡片

## Scope

- Phase: `17-imports-etc-invoices`
- Page key: `imports-etc-invoices`
- Route: `/imports/etc-invoices`
- Page entry: `web/src/pages/ImportEtcInvoicesPage.tsx`
- Shared workflow entry: `web/src/pages/ImportWorkflowPage.tsx`
- API clients: `web/src/features/etc/api.ts`, `web/src/features/imports/api.ts`
- Backend entrypoints: `app/routes_etc.py`, `app/server.py` `/api/etc/import*`, `app/services/etc_service.py`, `app/services/import_processing_service.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

ETC 发票导入是 ETC 票据链路的源事实入口。页面使用共享 `ImportWorkflowPage`，模式为 `etc_invoice`，但后端主链路不同于通用 `/imports/files/*`：它通过 ETC 专用 API 处理 zip 预览、任务版本校验、确认项集合校验和 ETC 业务批次绑定。

当前主链路是：

1. 页面读取可导入的 ETC reconciliation ready task。
2. 用户上传 zip，前端调用 `/api/etc/import/preview`。
3. 后端根据 confirmed item set 过滤 zip，返回可确认项、错误项和 `confirmed_item_set_hash`。
4. confirm 调用 `/api/etc/import/confirm`，校验 task version、confirmed item set hash 和 import session freshness。
5. 后端创建 `etc_invoice_import` job，worker 创建或复用 task-scoped ETC business batch，写入 ETC import batch / invoice facts，同步 canonical invoice，并触发 `etc_import_confirmed` 生命周期刷新。

## Cross-Page Dependencies

- Upstream:
  - ETC reconciliation ready task
  - ETC confirmed item set
  - zip 文件内容和解析结果
- Direct downstream:
  - `etc-tickets`: ETC 票据管理、业务批次、OA 草稿/手工状态和删除链路。
  - `reconciliation-workbench`: ETC 发票/票据事实进入关联和匹配视图。
  - `tax-offset`: ETC 发票同步为 canonical invoice 后参与抵扣链路。
  - `cost-statistics`: ETC 成本事实影响成本统计。
- Indirect downstream:
  - `input-invoice-usage`
  - `pending-invoices`
  - `app-health-operations`
- Phase 0 dependency group: `Import source facts` 与 `ETC chain`，是 ETC 票据和税务链路的前置事实入口。

## Read Model / Worker / App Status

- Direct read model: 无独立 App Status read model；页面写入 ETC 导入事实。
- Workers/jobs:
  - worker: `import`
  - job/event: `etc_invoice_import`
  - lifecycle event: `etc_import_confirmed`
- Downstream refresh:
  - ETC business batch / ticket facts
  - canonical invoice sync
  - invoice lifecycle
  - workbench / tax offset / cost statistics
- Freshness rule: ETC import confirm 只代表 ETC 导入 job 被接受；ETC 票据、发票生命周期、税金抵扣和成本统计仍需要各自 refresh/fresh gate。

## Current Gaps To Assess Before L2

- ready task 选择、任务版本变化和 confirmed item set hash 失效时的用户反馈是否足够明确。
- zip preview 的错误、缺失、重复和已确认项过滤是否可解释。
- confirm 后 ETC business batch、canonical invoice 和下游 read model 的状态是否可追踪。
- ETC 专用导入 API 与通用导入工作流的边界是否清晰，避免误用 `/imports/files/*`。
- 与 `etc-tickets` 的 OA 草稿/手工状态/删除链路是否在实施前被共同审计。

## Risks

- 权限: ETC ready task 查看、zip preview、confirm、业务批次查看和删除可能需要不同权限。
- 审计: task version、confirmed item set hash、zip 内容、导入批次、业务批次和 canonical invoice 同步必须可追溯。
- stale/fresh: task 版本、confirmed set、import session 和下游 read model 都可能 stale。
- 跨页刷新: ETC 票据、关联台、税金抵扣、成本统计和进项使用链路都会受到影响。
- worker: `etc_invoice_import` 失败、重复提交、部分解析失败和 canonical invoice 同步失败需要明确恢复语义。
- 导出: ETC 错误明细、导入结果和票据导出字段不能被破坏。
- 历史数据: 已确认任务和历史业务批次不能被重复导入或 UI 重试污染。

## Test Entry Points

- Backend:
  - `tests/test_etc_backend.py`
  - `tests/test_import_*`
  - ETC service、zip filter、document parser、import processing、lifecycle refresh 相关测试
- Frontend:
  - `web/src/test/EtcApi.test.ts`
  - ETC 导入和共享 import workflow 相关测试
- E2E/integration candidates:
  - ETC ready task -> zip preview -> confirm -> ETC tickets 可见 -> tax/cost 下游刷新
  - task version/hash stale -> confirm 阻断 -> 重新 preview 后成功

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖 task version、hash 校验、zip filter、重复项、canonical invoice 同步语义。
- Service-layer tests: 适用。覆盖 ETC service、业务批次、import job、lifecycle fan-out 和幂等。
- API contract tests: 适用。覆盖 `/api/etc/import/preview`、`/api/etc/import/confirm` 的成功、stale、错误、权限和 job response。
- Read model/cache/background job tests: 适用。覆盖 `etc_invoice_import` worker、ETC downstream refresh 和 freshness。
- Frontend component/interaction tests: 适用。覆盖 ready task、zip 上传、preview 错误、confirm、stale feedback 和 job 状态。
- End-to-end business-flow integration tests: 适用。至少保护 ETC 导入到 ETC 票据、税金抵扣或成本统计可见的关键路径。
- Existing feature regression tests: 适用。保护 ETC 票据管理、旧 ETC API、历史批次、删除/状态流转和下游页面。

## Docs Impact Entry

- Module docs: `docs/modules/imports-etc-invoices/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/imports/`
  - `docs/product-specs/etc/`
  - `docs/app-architecture/`
  - `docs/dev/`
  - `docs/operations/runtime-worker-governance.md`
- L2 实施前必须明确 ETC 专用 API、业务批次、worker 和下游页面文档是否需要同步。

## Legacy / Transitional Paths

- ETC 发票导入不能误走通用 `/imports/files/preview` / `/imports/files/confirm` 主链路。
- ETC 专用导入与共享 `ImportWorkflowPage` 的 UI 复用要保持边界清晰：UI 复用不等于后端 contract 复用。
- 如要删除或迁移 ETC 旧入口，必须先审计 `etc-tickets`、ETC service、测试和文档中的调用点。

## L2 Questions

- 页面完善目标是 ready task 选择、zip preview 可解释性、stale 阻断，还是下游刷新闭环？
- confirm 后是否需要展示 ETC business batch ID、canonical invoice sync 结果和下游刷新状态？
- 部分 zip 项失败时，是否允许确认可用项，还是要求整包成功？
- hash/version stale 后是否自动重新拉取 task，还是要求用户手动重新 preview？
- 与 ETC 票据管理的状态流转和删除链路是否需要合并到同一实施切片？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先在本 phase 内补齐 `CONTEXT.md` / `RESEARCH.md` / `PLAN.md` 或等价 GSD 文档，并明确：

- ETC 专用导入 contract、任务版本和 hash 校验语义。
- 受影响的 ETC business batch、canonical invoice、worker、read model 和权限。
- 旧路径迁移/删除策略。
- 测试矩阵、下游验证和文档更新范围。
