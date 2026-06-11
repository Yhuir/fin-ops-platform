# 外部往来款管理 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 外部往来款管理首轮测试闭环状态为 `documented-risk`：已有测试覆盖 business core、service/UoW、API contract、read model/worker、前端交互、跨页面集成和旧功能回归。
- 本轮不新增低价值测试。后续只有发现明确 P0/P1 缺口、真实 bug 或业务规则变化时，再按 `tests.md` 中七类矩阵补测试。
- 手动零差额闭环写入 Workbench active pair relation 作为共同事实源；系统 `deterministic` 只表示候选，不是已闭环事实。bank-only 外部往来闭环在关联台保持 open，只有 OA + 银行 + 发票三栏补齐后才进入 paired。
- 手动零差额闭环支持同组多流水；至少一收一支且收支合计差额为 `0.00`。已确认后不能追加流水，漏选时先撤回 bank-only 闭环再重新选择。
- 外部往来页撤回只允许 bank-only open 外部往来闭环；若已在关联台补齐三栏并进入 paired，必须去关联台撤回完整关系。
- `readModelStatus !== "fresh"` 时前端必须禁用确认、撤回、流水选择、extra 保存等写动作。
- 写路径应优先保持 `TurnoverLedgerWriteFacade` / `TurnoverLedgerWriteUnitOfWork` 边界；legacy fallback 只作为兼容风险存在，不能继续扩大。
- 涉及 Workbench relation 的 manual closure/withdraw 即使经过 legacy fallback facade，也必须通过 `WorkbenchRelationCommandService`；缺 command service 时 fail fast，不允许 direct pair relation write fallback。
- 前端 domain event 只作为刷新提示；跨页面一致性仍由后端 dirty/outbox、read model freshness 和 worker readiness 保证。

## 2026-06-11 - 外部往来多流水闭环与 Workbench 三栏规则

- 目标：取消外部往来手动闭环只能选择两笔银行流水的限制，并让外部往来闭环完全复用 Workbench active pair relation 事实源。
- 影响范围：`TurnoverRelationService`、`TurnoverLedgerWriteFacade`、`TurnoverLedgerWorkbenchPairPort`、Workbench candidate grouping、server relation display payload、外部往来页 closure drawer、关联台本地 optimistic update。
- 关键决策：
  - 两笔闭环保留旧 `manual_zero_difference_pair` evidence；三笔及以上使用 `manual_zero_difference_group`。
  - `turnover_manual_closure` bank-only active relation 只能留在关联台 open，不再享受 exactly 2 bank rows paired 例外。
  - 外部往来页撤回前检查 `turnover:{relation_id}` 是否仍是 bank-only turnover relation；若已升级为三栏关系，返回 `turnover_closure_withdraw_requires_workbench`。
  - confirm 和 withdraw 都通过 UoW dirty/outbox 刷新 `turnover_ledger`、`workbench`、`workbench_relation`、`cost_statistics`、`search`。
- 文档影响：同步更新产品规格、API contract、app architecture、本模块 README/state-machine/tests/implementation-notes，以及关联台模块状态和测试矩阵。
- 测试覆盖：新增/更新 `tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`。
- 验证命令：见本轮最终执行记录；目标后端和前端测试均已覆盖多流水、bank-only open、withdraw cancel/reject 和 optimistic update。
- 未测风险：未运行真实生产库 Workbench active generation 全量回放；真实大数据滚动和视觉检查仍需浏览器/staging smoke。

## 2026-06-11 - 首轮测试闭环审计

- 目标：把 `turnover-ledger` 从测试闭环 `pending` 推进到可维护的 `documented-risk` 状态。
- 影响范围：外部往来页面、tag-selection、bank-row-tags batch、relation extra、manual closure、withdraw、export、turnover read model、turnover-ledger worker、Workbench pair relation、App Status、前端 domain events。
- CodeGraph 审计：
  - `TurnoverLedgerPage` 调用 `fetchTurnoverLedgerGrouped`、`fetchTurnoverLedgerTagSelection`、`confirmTurnoverClosure`、`saveTurnoverRelationExtra`、`withdrawTurnoverRelation`，并在 stale read model 时通过 `ledgerActionsDisabled` 禁用写动作。
  - `TurnoverLedgerApiRoutes` 仍承接 read/write route 形状；read path 已通过 `TurnoverLedgerReadFacade` 包住。
  - `TurnoverLedgerQueryService` 通过 `ReadModelQueryGateway` 处理 `turnover_ledger` scope `all` 的 fresh/stale/missing/refreshing。
  - `TurnoverLedgerWriteFacade` 和 `TurnoverLedgerWriteUnitOfWork` 覆盖 extra、bank-row-tags、confirm、zero-difference closure、withdraw、tag-selection 的 stale precondition、idempotency、dirty/outbox。
  - `TurnoverLedgerReadModelRefreshService`、`TurnoverLedgerSqlProjectionBuilder`、`runtime_worker_registry.py` 和 App Status registry 已登记 `turnover-ledger` worker、`turnover_ledger` read model 和 `turnover_ledger.read_model.refresh` event。
- 关键测试覆盖：
  - Business core：`tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_service.py`、`tests/test_turnover_ledger_extra_service.py`。
  - Service/UoW：`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_ledger_api.py`。
  - API contract：`tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_read_facade.py`。
  - Read model/worker：`tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh.py`、`tests/test_turnover_ledger_source_versions.py`。
  - Frontend：`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/domainEvents.test.ts`。
  - Integration/regression：`tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py`。
- 文档影响：
  - 补齐 `README.md` 模块边界和代码入口。
  - 将 `tests.md` 迁入测试闭环标准结构。
  - 补齐 `state-machine.md`。
- 未测风险：
  - 真实 PostgreSQL 历史数据、半迁移/脏数据、大数据 EXPLAIN 和锁等待。
  - 真实 RabbitMQ/Redis/systemd worker drain 和网络抖动恢复。
  - 浏览器真实下载 XLSX、视觉遮挡和大数据滚动性能。
  - legacy fallback 删除前仍需要专门回归。
- 后续事项：
  - 若修改写路径，优先补 `tests/test_turnover_ledger_uow_contract.py` 或 API characterization，再改实现。
  - 若修改 grouped row shape，必须同时更新后端 API contract、前端 mapper/page tests 和 export tests。
  - 若修改 Workbench pair relation 语义，必须同步运行 Workbench turnover grouping 和 manual closure integration tests。

## 2026-06-12 - Workbench relation 写入口收敛

- 目标：让外部往来 manual zero-difference closure/withdraw 的 Workbench relation 写入走统一 `WorkbenchRelationCommandService`，避免 turnover 页面直接持有独立 relation 写事实源。
- 关键决策：
  - Turnover manual relation 仍归 turnover 模块；跨页面 OA/银行/发票配对关系归 `workbench_relations` 模块。
  - closure 写 Workbench relation 使用 `confirm_relation(case_id="turnover:{relation_id}", relation_mode="turnover_manual_closure")`。
  - withdraw 撤回 Workbench relation 使用 `cancel_relation(case_id="turnover:{relation_id}")`，history operation 为 `turnover_manual_closure_withdraw`。
  - 写入前必须通过 relation read model freshness precondition；non-fresh 时返回 409，并且不能先改 turnover snapshot。
  - 已补齐成三栏 relation 的 bank row 不能从 turnover 页面撤回，仍要求到关联台撤回完整关系。
- 影响范围：`TurnoverLedgerWorkbenchPairPort`、`TurnoverLedgerWriteFacade`、Application turnover facade wiring、turnover API error payload、workbench-relations 模块文档。
- 测试覆盖：
  - `test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service`
  - `test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service`
  - `test_manual_closure_fails_fast_when_workbench_relation_read_model_is_stale`
  - `test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service`
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_uow_contract.py tests/test_turnover_workbench_integration.py tests/test_turnover_ledger_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
python3 -m compileall -q backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/app/server.py
bash scripts/verify.sh docs
git diff --check
```

- 已观察结果：turnover UoW/workbench/API 208 passed、31 subtests passed；relation command/read/projection 12 passed；repository boundary/runtime guard 43 passed；compileall、docs verify、diff check 均通过。存在既有 SWIG deprecation warnings。
- 未测风险：
  - 真实 PostgreSQL 历史数据、worker drain、前端跨页面即时反馈仍需 staging 或后续 Phase 验证。

## 2026-06-12 - Workbench relation legacy fallback direct write 删除

- 目标：删除 `TurnoverLedgerWorkbenchPairPort` 在缺少 relation command service 时的 direct pair relation write fallback，避免 legacy fallback facade 绕过统一 relation 事实源。
- 影响范围：`turnover_ledger_write_adapters.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_platform_runtime_boundary_guards.py` 和本模块文档。
- 关键决策：manual closure confirm/withdraw 需要 Workbench relation command service。缺少 command service 时抛 `workbench_relation_command_unavailable`，不读写 `WorkbenchPairRelationService` fallback，也不调用本地 pair snapshot persist。withdrawability 仍可用 `WorkbenchRelationReadFacade` 校验 bank-only relation。
- 文档影响：更新 `README.md`、`tests.md`、`implementation-notes.md`，并同步 `workbench-relations` 模块。
- 测试覆盖：新增 port 级 fail-fast 测试覆盖 confirm/withdraw 缺 command；新增 runtime boundary guard 防止 `TurnoverLedgerWorkbenchPairPort` 重新出现 `replace_with_confirmed_relation`、direct `cancel_relation(case_id)` 或 `_persist_pair_relations(...)`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_uow_contract.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_api.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback -q`。
- 未测风险：真实 PostgreSQL 历史数据和 worker drain 仍需 staging 或发布前 smoke；本阶段未改前端。
- 后续事项：继续收口 no-OA legacy migration/repair/consolidation，它仍在 `build_batches(...)` 中执行 direct pair relation mutation，需要单独设计 repair port 或离线工具。
