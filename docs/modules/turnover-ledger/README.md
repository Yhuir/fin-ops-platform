# 外部往来款管理 模块维护入口

- Module key: `turnover-ledger`
- 类型: 页面模块
- Route: `/turnover-ledger`
- Page key: `turnover-ledger`

## 修改前必读

- `docs/product-specs/bank-turnover-and-no-oa.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/architecture/backend-refactor/turnover-ledger-discovery.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- `web/src/pages/TurnoverLedgerPage.tsx`
- `web/src/components/turnoverLedger/*`
- `web/src/features/turnoverLedger/api.ts`
- `web/src/features/turnoverLedger/types.ts`
- `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
- `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_service.py`
- `backend/src/fin_ops_platform/services/turnover_relation_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_extra_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_export_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_source_versions.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`

## 当前边界

外部往来款管理负责把银行明细中已确认三层外部往来分类的流水汇总成外部往来台账，并提供标签准入、补充信息、导出和人工零差额闭环。

当前有效边界：

- 候选来源：银行明细有效分类和外部往来标签规则；`deterministic` 只表示零差额候选，不表示已闭环。
- 台账读取：优先走 `turnover_ledger` SQL read model；`TurnoverLedgerQueryService` 通过 `ReadModelQueryGateway` 处理 fresh/stale/missing/refreshing。
- 写入入口：tag-selection、bank-row-tags batch、relation extra、confirm、withdraw 通过 `TurnoverLedgerWriteFacade` / UoW 或 legacy fallback 边界；涉及 Workbench relation 的 manual closure/withdraw 必须统一委托 `WorkbenchRelationCommandService`，缺 command service 时 fail fast，不回退 direct pair relation mutation。
- 手动闭环：用户在页面选择同一往来组多条真实银行流水，至少一收一支且收支合计差额为 `0.00`，后端写 Turnover manual relation，并通过 `WorkbenchRelationCommandService` 写 Workbench active pair relation；bank-only 外部往来闭环在关联台保持 open，只有补齐 OA + 银行 + 发票三栏后才进入 paired。
- 撤回：只允许撤回 manual/source 合法的外部往来关系；system/generated relation 必须拒绝。Workbench relation 撤回通过 command service cancel，撤回前用 `WorkbenchRelationReadFacade` 检查仍是 bank-only `turnover_manual_closure`。
- 下游影响：外部往来关系变更影响 `turnover_ledger`、`workbench`、`workbench_relation`、成本统计、搜索和前端跨页刷新提示。
- App Status：`turnover_ledger` domain 绑定 `turnover-ledger` worker、`turnover_ledger` read model、`turnover_ledger.read_model.refresh` job type。

不属于本模块事实源：

- 银行明细分类规则的长期业务口径归 `bank-details` 和产品规格维护。
- Workbench 已配对区事实由 Workbench pair relation/read model 维护，不能由 Turnover query 层临时拼接或直接读取 pair service snapshot。
- 前端 domain event 只作为同浏览器刷新提示，不是跨页面一致性的事实源。

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
