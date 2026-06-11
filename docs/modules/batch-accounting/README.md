# 批量账务 模块维护入口

- Module key: `batch-accounting`
- 类型: 页面模块
- Route: `/batch-accounting`
- Page key: `batch-accounting`

## 修改前必读

- `docs/product-specs/reconciliation-and-workbench.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/refactor-ui/modules/phase_6_batch_accounting.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/bank-details/README.md`
- `docs/modules/cost-statistics/README.md`

## 代码入口

- `web/src/pages/BatchAccountingPage.tsx`
- `web/src/features/batchAccounting/api.ts`
- `web/src/features/batchAccounting/types.ts`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/batch_accounting_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py`
- `backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py`
- `backend/src/fin_ops_platform/services/workbench_relation_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/workbench_relation_distribution_mapper.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_job_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前职责

批量账务页面用于把符合批量账务条件的银行流水与日常报销 OA 行做人工关系确认，并支持已确认关系撤回。它不是独立事实源：

- 银行流水、OA 行和已有关联关系来自 Workbench / Workbench relation read model。
- `GET /api/batch-accounting` 必须返回 `summary`、`bank_rows`、`oa_rows`、`relations_by_bank_row_id`、`read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`refresh_enqueued`。
- `POST /api/batch-accounting/submit` 写入 Workbench pair relation，`special_metadata.source` 必须是 `batch_accounting`。
- `POST /api/batch-accounting/{relation_id}/withdraw` 只能撤回当前 active 的批量账务关系，并保留提交/撤回历史备注。
- 前端提交/撤回成功后发送 `workbenchRelationUpdated`，作为同浏览器会话刷新提示；事实源仍以后端 dirty scope、read model freshness 和 worker readiness 为准。

## 当前边界

- 必须透出 `workbench_relation` read model 状态，不能把非 fresh 空关系显示为真实未提交。
- `read_model_status !== "fresh"` 时，页面可以展示当前可用 payload，但必须阻止提交和撤回。
- 批量账务关系变化会影响关联台、银行明细、成本统计、搜索、进项/销项/OA 待付款等依赖关系 read model 或 invoice lifecycle 的页面。
- read model refresh 的事实源是 durable queue / `workbench_relation.read_model.refresh`，不是前端事件。
- 批量账务 GET 必须保持只读；不能在列表读取路径执行 legacy relation repair。

## 影响面清单

| 改动点 | 必查影响 |
| --- | --- |
| 页面筛选、bucket、选择、差额说明、提交/撤回 | `BatchAccountingPage.test.tsx` 的 loading/empty/error/stale/筛选/提交/撤回/事件回归 |
| API DTO 或错误码 | `tests/test_batch_accounting_api.py`、`web/src/features/batchAccounting/api.ts` mapper |
| 关系提交/撤回规则 | `BatchAccountingService`、`WorkbenchPairRelationService`、Workbench relation projection、历史修复回归 |
| `workbench_relation` freshness | `WorkbenchRelationReadFacade`、`workbench_relation` worker、App Status / App Health |
| Dirty/outbox/lifecycle event | `DerivedDataLifecycleService`、runtime worker registry、下游页面 stale/fresh 回归 |
| Bank/OA identity 字段 | 银行明细、关联台、待找发票、进项/销项/OA 待付款和成本统计关系标签 |

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
