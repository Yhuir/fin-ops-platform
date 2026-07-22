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
- 台账读取：只走 `turnover_ledger` SQL read model；`TurnoverLedgerApiRoutes` 是 HTTP route owner，读请求进入 `TurnoverLedgerQueryService`，repository miss 必须经 `ReadModelQueryGateway` fail-closed/enqueue，不再经过 app read forwarding facade、live page builder 或配置分叉。repository 用固定查询数在 SQL 内完成方向/家庭/状态过滤、总计与 family 汇总，并只读取当前页规范化 payload；`all` query 聚合全部月份 dirty scope，不能在任一月份刷新或失败时伪装 fresh。`TurnoverLedgerSqlProjectionBuilder` 在 projection 阶段通过 `WorkbenchRelationReadModelRepositoryPort.workbench_relation_source_bundle_from_source(...)` 从 canonical `app.workbench_pair_relations` 的同一快照读取 active relation rows 与 source summary，不串行等待 `workbench_relation` read model；随后把 `workbench_relation_status/case_ids/mode/source/row_ids`、`linked_oa`、`linked_invoice`、`cash_closure_linked`、`cash_closure_case_id/source/relation_id` 投影到 grouped payload。relation-only outbox 明确携带 `relation_deltas + row_ids` 时，month worker 只读 `bank_row_ids` 重叠的 grouped rows、重套 relation context 并窄 upsert；旧的整月读出、删除、重写路径不再进入该 hot path。canonical source 不可用时必须 fail fast，不保存半成品 turnover read model。
- 写入入口：tag-selection、bank-row-tags batch、relation extra、confirm、withdraw 通过 request-boundary facade 进入 `TurnoverLedgerWriteFacade` / UoW；涉及 Workbench relation 的 manual closure/withdraw 必须统一委托 `WorkbenchRelationCommandService`，缺 command service 时 fail fast，不回退 direct pair relation mutation。
- 手动闭环：用户在页面选择同一往来组多条真实银行流水，至少一收一支且收支合计差额为 `0.00`。Turnover domain 只做无副作用业务校验；写事务仅通过 `WorkbenchRelationCommandService` 写 canonical Workbench active pair relation，不再重复写 Turnover relation/event。同一 request-scoped bank-row selection port 同时服务版本校验、closure preview 与 requirement 冻结；按所选顺序读取 `effective_category_code`（仅在缺失时回退 `category_code`），且每次确认只读取一次 canonical 流水规则 payload。新 relation 复用统一 requirement helper 写入 tag code、`requires_oa`、`requires_invoice`、规则来源和版本。active relation 只表示同组 ownership；Workbench 只按冻结 metadata 判断 required row type，bank-only 且要求 OA 的闭环仍以同一个 case 留在未配对区，全部要求满足后才进入已配对。缺失、空或未知规则 fail closed，规则保存不再追溯回写既有 relation；存量缺快照关系只能走受控 repair。若所选银行流水已处在仅含 `oa` + `bank` 的 active relation 中，闭环确认可合并这些既有关联，但合并后的全部银行成员必须属于本次 selected ids，否则在 command 前冲突；既有 relation 包含发票或其他 row type 时必须转关联台处理完整关系。
- 撤回：现代外部往来闭环统一用 `/api/turnover-ledger/closures/withdraw`，按 `cash_closure_case_id` 通过 command service `withdraw_relation` 撤回对应 active case，并恢复确认前可恢复的 OA-bank 关系；事务内只允许 `{oa, bank}` 且至少两条 bank rows。显式携带 `special_metadata.turnover_relation_id` 的历史闭环才可走 `/api/turnover-ledger/relations/{relation_id}/withdraw`；页面和 projection 不得从 case id 猜旧 relation id。已包含发票或其他 row type 的 relation 必须转关联台撤回。
- 前端闭环入口：表格 checkbox 选中未闭环 flow rows 时，toolbar 主按钮为“确认闭环”。所选 flow rows 全部带同一个 `cash_closure_case_id` 且 `cash_closure_linked=true` 时，主按钮切换为“撤回闭环”。同一次选择不得混合已闭环与未闭环流水，也不得跨多个闭环 case 撤回。
- 下游影响：外部往来关系变更影响 `turnover_ledger`、`workbench`、`workbench_relation`、成本统计、搜索和前端跨页刷新提示。
- 操作闭环：前端 tag-selection、extra 保存、manual closure confirm/withdraw 必须接入 `GlobalOperationOverlayProvider`。manual closure 发起和提交不能依赖 stale grouped payload；提交前必须先等待所选 rows 对应的 affected-month `turnover_ledger` scopes fresh、重新加载 grouped payload，并按原始 bank row ids 在同一 group 内重绑定最新 flow rows，用最新 `categoryVersion` 生成 `expected_versions`；无法从所选 rows 解析月份时才退回 `all`。manual closure confirm/withdraw 的写 API 只返回本操作可见性所需的硬等待目标：affected-month `turnover_ledger` 和受影响月份的 `workbench_relation`；`workbench` 月份聚合、成本统计、搜索等下游 read model 继续通过 dirty/outbox 和 App Status/SLO 监控收敛，不得作为外部往来写操作的 overlay 释放条件。POST 成功后若 operation barrier 或页面 reload 仍未收敛，前端只能提示“操作已提交，后台同步尚未完成”，不能显示“操作失败”；提交前 fresh gate 和后端写入本身失败仍必须阻断。
- App Status：`turnover_ledger` domain 绑定单一 `turnover-ledger` worker、`turnover_ledger` read model、`turnover_ledger.read_model.refresh` job type。现代闭环确认/撤回只改变 canonical Workbench relation context，不再用第二 worker 并发全量重建。

不属于本模块事实源：

- 银行明细分类规则的长期业务口径归 `bank-details` 和产品规格维护。
- Workbench 已配对区事实由 Workbench pair relation/read model 维护，不能由 Turnover query 层临时拼接或直接读取 pair service snapshot；Turnover 页面只能消费 projection 已写入的 Workbench relation 状态字段。外部往来页只展示正向 chip：`linked_oa=true` 显示“已关联 OA”，`linked_invoice=true` 显示“已关联 发票”，`cash_closure_linked=true` 显示醒目的“收支闭环”。不得再显示“已关联业务单据”“未闭环”“部分已闭环”“候选关联”等旧 chip。
- 前端 domain event 只作为同浏览器刷新提示，不是跨页面一致性的事实源。

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
