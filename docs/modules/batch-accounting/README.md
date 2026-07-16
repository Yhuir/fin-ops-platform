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
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_job_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前职责

批量账务页面用于把符合批量账务条件的银行流水与日常报销 OA 行做人工关系确认，并支持已确认关系撤回。它不是独立事实源：

- 银行流水、OA 行和已有关联关系来自 Workbench / Workbench relation read model。
- `GET /api/batch-accounting` 必须返回 `summary`、`bank_rows`、`oa_rows`、`relations_by_bank_row_id`、`read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`refresh_enqueued`。显式传入 `page/page_size`、`bank_page/bank_page_size` 或 `oa_page/oa_page_size` 时，后端只裁剪对应列表并返回 `pagination`；不传分页参数时保持旧响应 shape。
- 未提交 bucket 的 read path 必须把 Workbench 输入先收窄为批量账务银行候选和日常报销 OA 候选，再调用 `workbench_relation` facade；`submitted_count` 通过 relation read facade 的年份轻量统计 I/O 取得，不能为未提交首屏加载 12 个月完整 submitted relation DTO。
- 前端未提交 bucket 首屏默认以 200 行页大小分别请求银行流水和可关联 OA 项，并提供独立分页控件；切换 bucket 或流水年份会重置页码、选择和差额说明，避免跨页旧选择误提交。右侧 OA 不按年份过滤，只展示没有关联银行流水的日常报销 OA 主单；仅发票关系或无流水候选关系不应把该 OA 排除。已提交 bucket 只分页银行关系列表，OA 明细来自当前可见 relation bucket。
- `POST /api/batch-accounting/submit` 必须优先通过 Workbench SQL active read model 的窄读口读取本次选中银行流水、OA 主单和对应 OA 附件发票，并通过 `WorkbenchRelationCommandService.confirm_relation(...)` 写入 relation，`special_metadata.source` 必须是 `batch_accounting`，`special_metadata.affected_scope_keys` 必须记录本次关系涉及的具体月份；缺少 command service 时 fail fast，不回退 direct pair relation mutation。
- `POST /api/batch-accounting/{relation_id}/withdraw` 只能撤回当前 active 的批量账务关系，并保留提交/撤回历史备注；撤回必须通过 durable relation command repository 取消当前 batch relation，记录 `withdraw_link` history。它不走旧 snapshot restore，也不得把 OA 附件 case_id / `existing_case` 显示归属恢复成 active relation。
- 旧 `repair_legacy_case_id_collisions(...)` service-level 修复入口已删除；批量账务生产 API/worker 主链路不得再提供 legacy case-id collision repair 写入口。
- 前端提交/撤回成功后发送 `workbenchRelationUpdated`，作为同浏览器会话刷新提示；事实源仍以后端 dirty scope、read model freshness 和 worker readiness 为准。

## 当前边界

- 必须透出 `workbench_relation` read model 状态，不能把非 fresh 空关系显示为真实未提交。
- `read_model_status !== "fresh"` 时，页面可以展示当前可用 payload 和 freshness 诊断，但不能仅因普通 read model non-fresh 全局阻止提交和撤回；写操作必须由权限/session、DB/目标写模型可用性、canonical relation version/idempotency/owner 状态决定。
- `GET /api/batch-accounting` 的 relation 读取必须通过现有 relation read facade/freshness 边界请求 `require_fresh`；缺失或 stale scope 只能经 facade/gateway 入队刷新，不能在页面 GET 路径同步 rebuild 或直接写 durable queue。
- `POST /api/batch-accounting/submit` 和 `POST /api/batch-accounting/{relation_id}/withdraw` 必须走 command service，并基于 canonical relation、idempotency、owner 状态、权限/session、DB 可写性和本次操作 row ids 的 active relation 冲突校验；PostgreSQL runtime 必须注入 durable `PostgresWorkbenchRelationRepository`，不允许在缺少 command service 或 durable repository 时静默写旧 pair service/in-memory snapshot，也不能把整页普通 relation distribution 追赶中作为默认写阻断条件。
- submit/withdraw route 不再调用旧 `_schedule_workbench_pair_relation_persist`、`_schedule_workbench_read_model_persist`、snapshot rollback restore 或 duplicate derived lifecycle；关系事实保存和 dirty/outbox fan-out 只属于 `WorkbenchRelationCommandService` repository。写后刷新 scope 必须来自 relation payload / `affected_scope_keys`，跨月关系只刷新实际月份，不能默认把 scope 扩散为 `all`。
- 前端 submit/withdraw 必须接入 `GlobalOperationOverlayProvider`。写 API 成功是 command 边界完成；随后只短等 `workbench_relation` operation barrier 并尝试重新加载批量账务 payload。barrier blocked/timeout 或 reload 中断不得把已成功的 command 改写成“操作失败”，页面必须提示关系仍在后台同步，并继续以后端 dirty scope、worker 和后续刷新为事实源。
- 批量账务关系变化会影响关联台、银行明细、成本统计、搜索、进项/销项/OA 待付款等依赖关系 read model 或 invoice lifecycle 的页面。
- read model refresh 的事实源是 durable queue / `workbench_relation.read_model.refresh`，不是前端事件。
- 批量账务 GET 必须保持只读；不能在列表读取路径执行 legacy relation repair。
- 批量账务显式分页的 `page_size` 上限为 200，超限必须返回 `invalid_paging`，不能为了首屏性能静默全量返回或把 stale relation distribution 伪装成 fresh。
- 批量账务 SQL 读路径分三类 I/O：未提交列表只用年份候选 loader；submit command 只用 `bank_row_id + oa_row_ids` 窄 loader；已提交 bucket 只用年份级 batch-accounting relation DTO 和银行行窄 payload。三者不能相互复用，也不能回退 Workbench full-page builder；缺少对应 loader/reader 时必须 fail closed 为 unavailable。

## 影响面清单

| 改动点 | 必查影响 |
| --- | --- |
| 页面筛选、bucket、选择、差额说明、提交/撤回 | `BatchAccountingPage.test.tsx` 的 loading/empty/error/stale/筛选/提交/撤回/事件回归 |
| API DTO 或错误码 | `tests/test_batch_accounting_api.py`、`web/src/features/batchAccounting/api.ts` mapper |
| 关系提交/撤回/修复规则 | `BatchAccountingService`、`WorkbenchRelationCommandService`、Workbench relation projection、历史修复回归 |
| `workbench_relation` freshness | `WorkbenchRelationReadFacade`、`workbench_relation` worker、App Status / App Health |
| Dirty/outbox/read model fan-out | `WorkbenchRelationCommandService` repository、runtime worker registry、下游页面 stale/fresh 回归 |
| Bank/OA identity 字段 | 银行明细、关联台、待找发票、进项/销项/OA 待付款和成本统计关系标签 |

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `e2e-spec.md`：维护页面 Spec-first Browser E2E 业务验收合同。
- `e2e-coverage.md`：维护 Spec ID 到 Browser/API/组件/后端/integration 覆盖证据的映射。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
