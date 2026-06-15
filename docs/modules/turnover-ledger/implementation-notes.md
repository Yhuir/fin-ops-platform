# 外部往来款管理 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 外部往来款管理首轮测试闭环状态为 `documented-risk`：已有测试覆盖 business core、service/UoW、API contract、read model/worker、前端交互、跨页面集成和旧功能回归。
- 本轮不新增低价值测试。后续只有发现明确 P0/P1 缺口、真实 bug 或业务规则变化时，再按 `tests.md` 中七类矩阵补测试。
- 手动零差额闭环写入 Workbench active pair relation 作为共同事实源；系统 `deterministic` 只表示候选，不是已闭环事实。bank-only 外部往来闭环在关联台保持 open，只有 OA + 银行 + 发票三栏补齐后才进入 paired。
- PostgreSQL SQL runtime 下外部往来闭环的银行流水事实源必须是 `bank_detail` SQL read model，并保留 Workbench 使用的 legacy/source row id；不能再从 legacy import snapshot 推导可闭环流水。
- 手动零差额闭环支持同组多流水；至少一收一支且收支合计差额为 `0.00`。已确认后不能追加流水，漏选时先撤回 bank-only 闭环再重新选择。
- 外部往来页撤回只允许 bank-only open 外部往来闭环；若已在关联台补齐三栏并进入 paired，必须去关联台撤回完整关系。
- `readModelStatus !== "fresh"` 时前端必须显示诊断并避免把旧 grouped payload 当作最终业务结论；manual closure 这类依赖页面所选 flow row versions 的写操作必须先阻断或等待 fresh 后重新加载并重绑定，后端 stale precondition、canonical write safety、权限/session、DB 和 idempotency/version 继续作为最终兜底。写 API 成功后必须用全屏 operation overlay 等待 `turnover_ledger` barrier fresh 并重新加载。
- 写路径应优先保持 `TurnoverLedgerWriteFacade` / `TurnoverLedgerWriteUnitOfWork` 边界；legacy fallback 只作为兼容风险存在，不能继续扩大。
- 涉及 Workbench relation 的 manual closure/withdraw 即使经过 legacy fallback facade，也必须通过 `WorkbenchRelationCommandService`；缺 command service 时 fail fast，不允许 direct pair relation write fallback。
- 前端 domain event 只作为刷新提示；跨页面一致性仍由后端 dirty/outbox、read model freshness 和 worker readiness 保证。

## 2026-06-16 - Bank detail dependency loop caused empty turnover ledger

- 目标：修复外部往来款管理页无数据、App Status 长时间显示银行明细同步中的问题。
- 真实原因：`bank_detail` 月份 read model 本身已经有外部往来流水和自动标签结果；页面无数据是因为 `turnover_ledger:all` worker 被银行明细 freshness 依赖循环阻塞。第一层问题是 downstream all-scope `bank_detail_read_model_not_fresh` 被旧 runtime worker 自动补投成 `bank_detail:all`，把 fan-out command 当成稳定 dependency。第二层问题是 `BankTransactionTagReadFacade` 把 fresh `bank_detail` read model 中缺失的 transaction id 误判成 read model `missing`，导致 `downstream_bank_tag_read` 每轮都补投月份 refresh；刷新不能制造不存在的投影行，因此 source_version 持续被 bump。
- 影响范围：runtime worker dependency scope 推导、read model refresh gateway active coalescing、bank tag read facade missing-row contract；不改变外部往来 grouped ledger 业务计算、手动闭环写入、Workbench relation 写入口或前端 empty state。
- 关键决策：从架构上禁止 downstream all-scope dependency defer 推导 `bank_detail:all`；只允许从 source scope 推导具体月份。`bank_detail_all_shard` 作为 ensure/wakeup reason 参与 active coalescing，避免重复 bump 正在处理的月份 shard。fresh read model 的 missing transaction id 只作为诊断信息，downstream 外部往来计算按无标签行处理，不再补投 refresh 或抛 not fresh。
- 测试覆盖：`RuntimeWorkerTests.test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`ReadModelRefreshGatewayTests.test_bank_detail_all_shard_reason_does_not_bump_active_scope`、`BankTransactionTagReadFacadeTests.test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows`，并运行外部往来和免 OA read model dependency 回归。
- 生产验证要求：发布后观察 `job.read_model_dirty_scopes` / `job.outbox_events` 中 `bank_detail` 月份 shard、`turnover_ledger:all` 和 `no_oa_bank_batch:all` 收敛；页面必须由 fresh read model 显示数据，不能用手工改 readiness 或直接 SQL 填 rows。

## 2026-06-15 - SQL runtime closure source alignment

- 目标：修复生产环境外部往来页选中三笔银行流水确认闭环失败，且关联台 open 区没有生成同一个关系组的问题。
- 真实原因：不是关联台渲染丢关系，也不是 deterministic 候选应自动显示为已配对。生产 SQL runtime 的 `bank_detail` read model 已有这三笔流水及当前自动标签版本，但闭环写路径仍从 legacy import snapshot 读取可闭环银行流水；该快照在当前 SQL 部署下为空或不含目标行，所以后端在 stale/unknown bank row precondition 阶段拒绝写入，`TurnoverRelationService.confirm_zero_difference_closure` 和 `WorkbenchRelationCommandService.confirm_relation` 都没有执行。
- 第二个必须修复的边界：`bank_detail` SQL read model 的 durable `transaction_id` 可能是 UUID，而关联台 row id 使用 legacy/source id，例如 `txn_imported_*`。闭环写入必须把 legacy/source id 保留为 `id` 与 `source_bank_row_id`，否则即使 relation 写成功也可能无法和关联台行聚合。
- 关键决策：`Application._turnover_bank_transaction_rows()` 在 SQL runtime 下改为读取 `bank_detail_sql_read_repository.list_bank_detail_tagged_rows_by_month(...)`；使用 app settings 中的外部往来选中标签集过滤；`read_model_status` 允许 `fresh` 和 `refreshing`，但 `refreshing` payload 中只接受当前 `bank-auto-tag-rules:{version}` 的行，避免把旧规则版本行拿去闭环；应用启动早期 settings service 尚未绑定时返回空集合，不让 startup wiring 崩溃。
- 文档影响：更新本模块实施记录和测试矩阵；银行标签恢复和设置入口收口记录在 `bank-details`、`settings` 模块。
- 测试覆盖：新增 `test_sql_bank_detail_turnover_rows_keep_legacy_source_ids_for_manual_closure` 覆盖 SQL read model row -> turnover closure -> Workbench active relation，新增 `test_sql_turnover_rows_tolerate_early_startup_before_app_settings_service_is_bound` 覆盖启动早期安全返回。
- 生产验证：已用现有 application facade 对目标三笔 legacy bank row ids 写入 manual zero-difference closure，并验证 `workbench_relation` read facade 返回 `fresh`，三笔行都 linked 到同一个 `turnover:{relation_id}` open group。
- 未测风险：未在本轮执行标准发布脚本全量重发 release；生产采取当前 release 单文件 hotfix 并重启服务，后续正式发布应带上本地变更和完整验证。

## 2026-06-15 - Manual closure selected-row fresh gate

- 目标：解决外部往来页选择多条银行流水打开闭环抽屉后，点击确定时使用旧 `categoryVersion` 生成 `expected_versions`，后端返回“银行流水状态已变化，请刷新后重试。”，导致 turnover relation 和 Workbench relation 都未写入、关联台 open 区没有关系组的问题。
- 影响范围：`TurnoverLedgerPage` manual closure 提交流、stale grouped read model 行为、`web/src/test/TurnoverLedgerPage.test.tsx`。
- 真实原因：不是关联台渲染丢失配对关系；闭环 POST 在 `TurnoverLedgerBankRowStalePreconditionPort` 前置版本检查被拒绝，后续 `confirm_zero_difference_closure`、`WorkbenchRelationCommandService.confirm_relation`、`freshness_targets` 等链路都没有执行。
- 关键决策：不新增后端旁路、不放宽 expected_versions。前端在 manual closure 点击确定前先等待 `turnover_ledger:all` fresh，再重新拉取 grouped payload，按原始 bank row ids 在原 group 的 latest `flow_rows` 中重绑，重新计算零差额并用最新 `categoryVersion` 提交。刷新后任一流水缺失、离开原 group 或不再零差额，则关闭抽屉并提示重新选择，不发 POST。当前 grouped read model 非 fresh 时，页面“确认闭环”入口禁用。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 与本实施记录。
- 测试覆盖：新增/更新 `web/src/test/TurnoverLedgerPage.test.tsx` 中 `refreshes the grouped ledger before manual closure and submits latest bank row versions`、`blocks manual closure when a selected flow disappears after the fresh ledger reload`、`shows grouped read model stale warning and blocks manual closure`。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产库上的 worker drain 和跨页面视觉刷新仍需 staging/生产前 smoke；本次本地测试已覆盖请求体版本、阻断旧选择、后端 UoW/API/workbench relation contract。

## 2026-06-15 - Manual closure Workbench visibility barrier

- 目标：外部往来页面确认多笔 manual zero-difference closure 后，关联台 `open` 区必须能在同一次跨页刷新中看到同一个 `case:turnover:{relation_id}` open group，避免先刷新到旧 Workbench generation。
- 影响范围：`TurnoverLedgerConfirmRequestBoundaryFacade` 响应契约、`TurnoverLedgerPage` operation barrier 等待、turnover closure API mapper、关联台跨页刷新事件时序。
- 关键决策：relation 写入和 Workbench 分组架构保持不变；真实缺口是闭环 API 只让前端等待 turnover ledger，未暴露/等待 Workbench 可见性目标。manual closure confirm 响应新增 `freshness_targets`，包含 `turnover_ledger:all`、受影响月份 `workbench_relation`、受影响月份 `workbench` 和 `workbench:all`；前端等这些 targets fresh 后再 reload 和 emit `workbenchRelationUpdated`。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 与本实施记录；关联台模块测试矩阵同步补充跨页刷新等待保护。
- 测试覆盖：新增/更新 `tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_workbench_integration.py`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`。
- 验证命令：见本轮最终执行记录。
- 未测风险：未运行真实生产库全量 Workbench active generation 回放；该风险与数据回放相关，不影响本次响应/等待契约。

## 2026-06-14 - 写操作后 freshness barrier

- 目标：外部往来 tag-selection、extra、manual closure confirm/withdraw 后隐藏 read model 收敛窗口，避免页面提前显示旧分组或允许重复操作。
- 影响范围：`TurnoverLedgerPage` 写操作、`GlobalOperationOverlayProvider`、`operationBarrier` API client。
- 关键决策：写 API 成功后等待 `turnover_ledger` barrier fresh，再 reload grouped payload 并关闭 overlay。前端事件只做刷新提示，不能替代 barrier/read boundary。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`。
- 测试覆盖：更新 `web/src/test/TurnoverLedgerPage.test.tsx`，并由 `GlobalOperationOverlayContext.test.tsx`、`OperationBarrierApi.test.ts` 覆盖共享 overlay/barrier 行为。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产登录态 operation-to-fresh latency 需要发布后度量。

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
  - `TurnoverLedgerPage` 调用 `fetchTurnoverLedgerGrouped`、`fetchTurnoverLedgerTagSelection`、`confirmTurnoverClosure`、`saveTurnoverRelationExtra`、`withdrawTurnoverRelation`；stale read model 只显示诊断，写操作由后端 stale precondition/canonical write safety 决定，成功后通过 operation barrier 等待 fresh。
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
  - 手动闭环写入使用 canonical relation command/write safety；`workbench_relation` distribution/read model non-fresh 不阻断写入，写后继续刷新 Workbench 和 downstream read model。
  - 已补齐成三栏 relation 的 bank row 不能从 turnover 页面撤回，仍要求到关联台撤回完整关系。
- 影响范围：`TurnoverLedgerWorkbenchPairPort`、`TurnoverLedgerWriteFacade`、Application turnover facade wiring、turnover API error payload、workbench-relations 模块文档。
- 测试覆盖：
  - `test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service`
  - `test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service`
  - `test_manual_closure_uses_canonical_relation_when_workbench_relation_read_model_is_stale`
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
