# 外部往来款管理 L1.5 页面基线卡片

## Scope

- Phase: `01-turnover-ledger-improvements`
- Page key: `turnover-ledger`
- Route: `/turnover-ledger`
- Page entry: `web/src/pages/TurnoverLedgerPage.tsx`
- API client: `web/src/features/turnoverLedger/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`, `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
- Core services: `turnover_ledger_service.py`, `turnover_ledger_query_service.py`, `turnover_ledger_write_facade.py`, `turnover_ledger_write_uow.py`, `turnover_ledger_read_model_refresh.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

外部往来款管理把银行明细中已确认三层外部往来分类的流水汇总成台账，并提供标签准入、补充信息、导出和人工零差额闭环。页面读取 `turnover_ledger` SQL read model，写入操作通过 `TurnoverLedgerWriteFacade` / UoW 处理；涉及 Workbench relation 的手动闭环和撤回必须委托 `WorkbenchRelationCommandService`。

当前关键边界：

1. 候选来源是银行明细有效分类和外部往来标签规则；`deterministic` 只表示零差额候选，不代表已闭环。
2. 查询通过 `ReadModelQueryGateway` 处理 fresh/stale/missing/refreshing，不能用旧 snapshot 伪装 fresh。
3. 手动闭环要求用户选择同一往来组多条真实银行流水，至少一收一支，收支合计差额为 `0.00`。
4. bank-only 外部往来闭环在关联台仍保持 open；只有补齐 OA + 银行 + 发票三栏后才进入 paired。
5. manual closure 的操作闭环必须等待 `turnover_ledger:all`、受影响月份 `workbench_relation`、受影响月份 `workbench` 和 `workbench:all` fresh 后再释放 overlay。

## Cross-Page Dependencies

- Upstream:
  - `bank-details`: 银行流水、有效分类、外部往来标签规则。
  - `imports-bank-transactions`: 银行流水源事实。
  - `reconciliation-workbench`: Workbench active relation / relation read facade。
- Downstream:
  - `reconciliation-workbench`: 手动闭环会写 Workbench active relation。
  - `cost-statistics`: 外部往来关系和分类可能影响成本聚合。
  - `app-health-operations`: worker/read model 状态可观测。
- Related pages:
  - `batch-accounting`
  - `no-oa-bank-batches`
  - `settings`
- Phase 0 dependency group: `Workbench relation core`。

## Read Model / Worker / App Status

- Read model: `turnover_ledger`
- Worker: `turnover-ledger`
- Job type: `turnover_ledger.read_model.refresh`
- Related read models: `workbench`, `workbench_relation`, `cost_statistics`, `search`
- App Status domain: `turnover_ledger`
- Freshness rule: 页面读取、手动闭环提交和撤回都必须显式处理 `fresh/stale/missing/refreshing`；前端事件只做同浏览器刷新提示，不是跨页面一致性事实源。

## Current Gaps To Assess Before L2

- 用户要完善的是标签准入、台账分组、补充信息、导出、人工闭环、撤回，还是跨页刷新闭环。
- 当前 grouped payload、`categoryVersion`、`expected_versions` 和 affected months 是否在 UI/API 中足够可见。
- manual closure 发起前是否能可靠等待最新 `turnover_ledger:all` 并重新绑定原始 bank row ids。
- tag-selection、bank-row-tags batch、extra 保存、confirm/withdraw 是否全部接入 operation overlay。
- legacy fallback 边界是否仍必要；如果存在绕过 command service 的旧路径，L2 必须提出移除计划。

## Risks

- 权限: 标签准入、补充信息保存、闭环确认、撤回和导出应分别确认权限。
- 审计: 标签变更、extra 保存、manual closure、withdraw、导出都需要可追溯。
- stale/fresh: stale grouped payload 不能用于提交闭环；提交后必须等待指定 freshness targets。
- 跨页刷新: 外部往来关系会影响关联台、银行明细、成本统计和搜索。
- worker: `turnover-ledger` worker 失败或 refresh 阻塞会导致页面不能安全提交或展示。
- 导出: 台账导出字段、筛选条件和分组口径需要回归保护。
- 历史数据: system/generated relation 不能被人工撤回；历史分类变化不能污染当前闭环。

## Test Entry Points

- Backend:
  - `tests/test_turnover_*`
  - turnover read facade/query/write/UoW/export/read model refresh 相关测试
  - Workbench relation command service 相关回归
- Frontend:
  - `web/src/test/TurnoverLedger*.test.tsx`
- Integration candidates:
  - 银行明细分类 -> turnover read model fresh -> manual closure -> Workbench relation fresh -> 页面重载
  - manual closure stale grouped payload -> submit 阻断 -> refresh 后成功

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖外部往来标签准入、零差额闭环、撤回合法性、分类版本冲突。
- Service-layer tests: 适用。覆盖 write facade/UoW、relation command 委托、read model refresh、导出服务。
- API contract tests: 适用。覆盖列表、tag-selection、extra、confirm、withdraw、export 的 response shape、权限和错误。
- Read model/cache/background job tests: 适用。覆盖 `turnover_ledger` dirty/fresh、worker、operation barrier。
- Frontend component/interaction tests: 适用。覆盖 stale/loading/empty/error、分组选择、保存、闭环、撤回、导出。
- End-to-end business-flow integration tests: 适用。保护银行分类到外部往来闭环再到关联台状态的关键路径。
- Existing feature regression tests: 适用。保护银行明细、关联台、成本统计、旧关系和导出行为。

## Docs Impact Entry

- Module docs: `docs/modules/turnover-ledger/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/bank-turnover-and-no-oa.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/app-architecture/pages.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- L2 前必须评估是否更新 `docs/architecture/backend-refactor/turnover-ledger-discovery.md` 和 write UoW 计划。

## Legacy / Transitional Paths

- `TurnoverLedgerWriteFacade` / UoW 中如仍有 legacy fallback，必须在 L2 中逐项确认是否保留、迁移或删除。
- 涉及 Workbench relation 的写入不得回退到 direct pair relation mutation。
- Turnover query 层不能临时拼接 Workbench 已配对事实，也不能直接读取 pair service snapshot 作为事实源。

## L2 Questions

- 本轮完善的主目标是哪一条用户路径：标签准入、台账查看、补充信息、导出、手动闭环、撤回，还是状态可见性？
- 是否需要先移除某条旧写入路径，防止旧逻辑污染 command/UoW 链路？
- manual closure 是否要新增前端操作前 freshness gate，还是后端强制拒绝 stale expected versions 即可？
- 导出是否必须包含 read model 状态或筛选条件快照？
- 下游 Workbench/成本统计刷新失败时，页面应该阻断后续操作还是展示诊断并允许只读？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确 API contract、worker/read model、权限、审计、旧逻辑删除和测试矩阵。
