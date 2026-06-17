# 外部往来款管理 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 外部往来款管理首轮测试闭环状态为 `documented-risk`：已有测试覆盖 business core、service/UoW、API contract、read model/worker、前端交互、跨页面集成和旧功能回归。
- 本轮不新增低价值测试。后续只有发现明确 P0/P1 缺口、真实 bug 或业务规则变化时，再按 `tests.md` 中七类矩阵补测试。
- 手动零差额闭环写入 Workbench active pair relation 作为共同事实源；系统 `deterministic` 只表示候选，不是已闭环事实。外部往来闭环 relation 在关联台保持 open，直到发票等完整业务关系在关联台补齐；若闭环确认前已有 OA-bank relation，可合并为同一个包含 `oa` + `bank` rows 的 active case。
- PostgreSQL SQL runtime 下外部往来闭环的银行流水事实源必须是 `bank_detail` SQL read model，并保留 Workbench 使用的 legacy/source row id；不能再从 legacy import snapshot 推导可闭环流水。
- 手动零差额闭环支持同组多流水；至少一收一支且收支合计差额为 `0.00`。已确认后不能追加流水，漏选时先撤回原闭环关系再重新选择。
- 外部往来页撤回只允许 row types 子集为 `{oa, bank}` 的 `turnover_manual_closure`；若已在关联台补齐发票或其他业务 row type，必须去关联台撤回完整关系。
- `readModelStatus !== "fresh"` 时前端必须显示诊断并避免把旧 grouped payload 当作最终业务结论；manual closure 这类依赖页面所选 flow row versions 的写操作必须先阻断或等待 fresh 后重新加载并重绑定，后端 stale precondition、canonical write safety、权限/session、DB 和 idempotency/version 继续作为最终兜底。写 API 成功后必须用全屏 operation overlay 等待 `turnover_ledger` barrier fresh 并重新加载。
- 写路径应优先保持 `TurnoverLedgerWriteFacade` / `TurnoverLedgerWriteUnitOfWork` 边界；legacy fallback 只作为兼容风险存在，不能继续扩大。
- 涉及 Workbench relation 的 manual closure/withdraw 即使经过 legacy fallback facade，也必须通过 `WorkbenchRelationCommandService`；缺 command service 时 fail fast，不允许 direct pair relation write fallback。
- 外部往来闭环和 OA/业务单据关联是两个不同事实：OA/业务单据关联 chip 只展示，不参与“确认闭环/撤回闭环”的决定链路；每条 flow row 单独展示“已闭环/未闭环”chip。确认闭环可合并所选银行流水已有的 OA-bank active relation；撤回闭环只撤回 `turnover_manual_closure`，并恢复确认前的 OA-bank relation。
- 前端 domain event 只作为刷新提示；跨页面一致性仍由后端 dirty/outbox、read model freshness 和 worker readiness 保证。
- export-preview/export 是同步生成路径；group 总数或展开后的 formal rows 超过 20,000 时必须返回 `turnover_ledger_export_row_limit_exceeded`，不能继续生成大预览或 XLSX。

## 2026-06-17 - SQL bank row 0 占位版本导致闭环 stale 误报

- 目标：修复外部往来款管理页选择 `txn_imported_*` SQL bank detail 流水确认手动零差额闭环时，后端误报“银行流水状态已变化，请刷新后重试。”的问题。
- 影响范围：SQL bank detail row -> turnover flow row 映射、`TurnoverLedgerBankRowStalePreconditionPort` 写入前置版本校验、前端 grouped row mapper、manual closure API/e2e 回归。
- 根因：上一轮修复覆盖了前端 fresh reload 和缺失版本字段，但真实 SQL 读模型里 `category_version=0` 是占位值；前端已按 `manual_category_version` / `version` 提交真实 `expected_versions`，后端 stale precondition 却仍把 `category_version=0` 当当前版本，导致误判 stale。
- 关键决策：统一使用 `turnover_bank_row_version` 选择银行流水版本，按 `category_version`、`manual_category_version`、`version` 顺序取第一个非零数值；只有所有候选都为空或为 0 时才保留 0。前端 mapper 使用同一语义，避免页面提交体和后端校验再次分叉。
- 文档影响：更新本模块 `tests.md` 与本实施记录；业务口径、API 字段 shape 和状态机不变。
- 测试覆盖：新增/更新 `test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_is_zero`、`test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_version_is_zero`、`test_bank_row_stale_precondition_uses_manual_version_when_category_version_is_zero`、`test_bank_row_stale_precondition_uses_base_version_when_category_versions_are_zero`、`test_manual_closure_api_accepts_sql_rows_with_zero_category_version`、`web/src/test/TurnoverLedgerApi.test.ts`，并继续保留 Playwright 对 confirm payload 的校验。
- 未测风险：本地未连接真实生产 PostgreSQL 数据重放截图中的原始三笔记录；已用相同 row id 和版本字段形态构造 API 集成复现。

## 2026-06-17 - OA 关联展示与外部往来闭环关系拆分

- 目标：修复外部往来款管理页把某条流水已关联 OA 的状态显示成“关联台已关联”，并把它误用于确认/撤回闭环判断的问题；同时支持流水 1/OA1、流水 2/OA2、流水 3 共同确认成一个外部往来闭环 active case。
- 影响范围：`TurnoverLedgerWorkbenchPairPort`、`WorkbenchRelationCommandService`、`WorkbenchPairRelationService` withdraw restore history、`TurnoverLedgerGroupedTable`、`TurnoverLedgerPage`、turnover/workbench integration tests、本模块文档和关联台关系状态机。
- 关键决策：
  - `turnover_manual_closure` 可以包含 `oa` + `bank` rows，但外部往来页只能合并 row types 子集为 `{oa, bank}` 且实际包含 OA 的既有 relation；包含 `invoice`、纯 bank-only 既有 relation、已有 `turnover_manual_closure` 或其他 row type 时拒绝并要求按对应 owner 先处理。
  - 确认闭环使用 `confirm_relation(..., replace_existing=True, before_relations=...)` 替换既有 OA-bank relation，并在 metadata 中保留本次选择的 `turnover_closure_bank_row_ids`。
  - 撤回闭环使用 `withdraw_relation`，底层 `WorkbenchPairRelationService` 识别 `turnover_manual_closure_confirm` 历史并恢复被标记为 `restorable_on_withdraw` 的 OA-bank relation；不再使用普通 `cancel_relation` 作为外部往来撤回语义。
  - 前端 group chip 只统计闭环关系；行内 chip 拆成“已关联 OA/已关联业务单据”和“已闭环/未闭环”。OA/业务单据 chip 仅展示，不禁用确认闭环，也不显示撤回闭环。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`、本实施记录和 `docs/modules/workbench-relations/state-machine.md`；长期产品口径不新增独立文档。
- 测试覆盖：新增/更新 `test_turnover_manual_closure_merges_existing_oa_bank_relations`、`test_turnover_manual_closure_rejects_rows_already_in_turnover_closure`、`test_turnover_workbench_pair_port_withdraw_restores_merged_oa_bank_relations`、`test_withdraw_restores_previous_relations_from_turnover_manual_closure_history`、`test_manual_closure_merges_existing_oa_bank_relations_and_withdraw_restores_them`、`allows manual closure confirmation when selected rows are only linked to OA`、`shows Workbench relation feedback from the grouped ledger payload`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service tests.test_workbench_relation_command_service tests.test_turnover_ledger_uow_contract tests.test_turnover_workbench_integration -v`；`cd web && npm test -- --run src/test/TurnoverLedgerPage.test.tsx`。
- 未测风险：本地测试没有用真实生产 PostgreSQL 数据和真实浏览器截图证明所有历史 OA id 命名都可被前端识别为 OA；后端关系恢复以 row type 为准，UI 的“已关联 OA”chip 仍依赖 projected row ids/mode 中可识别 OA 线索。

## 2026-06-16 - P2/P3 外部往来同步导出上限

- 目标：收敛外部往来 export-preview/export 大数据同步生成风险，避免超过 20,000 个 group 或展开后超过 20,000 行时继续构造预览/XLSX。
- 影响范围：`TurnoverLedgerExportService`、turnover export API error mapping、外部往来导出 service/API 测试、模块测试矩阵和 P2/P3 闭环台账。
- 关键决策：导出上限为 20,000 行；先根据 grouped payload `pagination.total` 拒绝明显超大 group，再根据 formal rows 数拒绝单 group 大量 flow rows。普通参数错误仍保持 `invalid_turnover_ledger_export_request`。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；产品/API 长期文档未扩展，因为这是性能保护边界。
- 测试覆盖：新增 `tests/test_turnover_ledger_export_service.py::TurnoverLedgerExportServiceTests::test_export_rejects_group_count_above_sync_row_limit`、`test_export_rejects_flattened_flow_rows_above_sync_row_limit` 和 `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_export_limit_returns_structured_error`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_export_service.TurnoverLedgerExportServiceTests.test_export_rejects_group_count_above_sync_row_limit tests.test_turnover_ledger_export_service.TurnoverLedgerExportServiceTests.test_export_rejects_flattened_flow_rows_above_sync_row_limit tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_export_limit_returns_structured_error -v`。
- 未测风险：真实 PostgreSQL grouped query、浏览器下载/打开文件和长表格视觉性能仍需 staging/manual smoke；本地只证明超大同步导出不会继续生成文件。

## 2026-06-16 - P2/P3 严格临时目录清理证据

- 目标：把外部往来 API 测试从 `TemporaryDirectory(ignore_cleanup_errors=True)` 放宽清理切回严格清理，避免后台 job executor 异步写入残留被测试吞掉。
- 影响范围：`tests/test_turnover_ledger_api.py`；业务实现、API contract、read model scope 和前端行为不变。
- 关键决策：保留严格 `TemporaryDirectory()`；对会启动后台 job 的用例在临时目录退出前调用 `app.shutdown_background_jobs()`，必要时使用 `try/finally`，不通过放宽 cleanup 隐藏资源边界问题。
- 文档影响：更新本实施记录、`tests.md` 和 P2/P3 closure ledger；长期业务口径不变。
- 测试覆盖：`tests.test_turnover_ledger_api` 覆盖外部往来 API、UoW、idempotency、stale precondition、read model refresh 和 Workbench relation 回归；同时运行 `tests.test_historical_etc_business_batch_migration_service` 验证相关历史 ETC migration 严格清理。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api tests.test_historical_etc_business_batch_migration_service -v`，结果 136 tests passed。
- 未测风险：这只证明本地测试资源释放和后台 job 边界；真实 worker/systemd/RabbitMQ drain 与一秒级生产 SLO 仍需 staging/production gate。

## 2026-06-16 - 已关联手工闭环 flow-row toolbar 撤回

- 目标：补齐外部往来表格选择已关联 `turnover_manual_closure` flow row 后的操作闭环，避免 toolbar 仍只暴露普通“确认闭环”入口。
- 影响范围：`TurnoverLedgerPage` selection toolbar、`TurnoverLedgerPage.test.tsx`、P2/P3 closure ledger；后端 withdraw API contract 不变。
- 关键决策：表格 checkbox 仍是 flow-row 选择入口；若当前选择包含已关联 Workbench row，普通“确认闭环”禁用。只有所选 flow rows 全部属于同一个 `turnover_manual_closure` relation 时，toolbar 启用“撤回闭环”，复用现有 `/api/turnover-ledger/relations/{id}/withdraw`，优先等待后端返回的 `freshness_targets`，然后 reload grouped ledger 并发送 turnover/workbench domain events。
- 文档影响：更新本模块 `tests.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：新增 `web/src/test/TurnoverLedgerPage.test.tsx::withdraws a selected linked manual closure from the table toolbar`；完整 `TurnoverLedgerPage.test.tsx` 继续覆盖抽屉撤回、manual closure、stale 阻断和 operation overlay。
- 验证命令：`npm --prefix web test -- --run src/test/TurnoverLedgerPage.test.tsx`。
- 未测风险：未用真实浏览器大数据表格截图验证 toolbar 换行动效；生产真实 withdraw SLO 仍需登录态 mutating scenario 证明。

## 2026-06-16 - Postgres 事务入队补齐成本统计 scope policy

- 目标：阻止外部往来确认/撤回在 PostgreSQL 事务写路径中绕过 `ReadModelRefreshGateway`，继续向 `cost_statistics.read_model.refresh` 投递裸月份或裸 `all`。
- 影响范围：`TurnoverLedgerDirtyOutboxWriter`、`TurnoverLedgerWriteUnitOfWork`、Postgres facade refresh request、成本统计下游 read model 和 App Status readiness。
- 关键决策：事务内写入仍使用 `enqueue_read_model_refresh_in_transaction` 保持同一业务事务；在调用前复用 `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY` 做 normalize/validate。`source_versions` 优先按实际入队 event 的 canonical `scope_key` 记录。
- 文档影响：更新 turnover-ledger、read-models、cost-statistics 模块记录，并在 P2/P3 closure ledger 登记生产 dry-run 证据。
- 测试覆盖：新增 `test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction`；更新 `test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear` 断言 Postgres path 入队 `active/all` canonical cost scopes。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`。
- 未测风险：生产已有 9 条 legacy cost statistics runtime 状态仍需受控 `scripts/check-read-model-scope-contracts.py --apply` 清理；本次未执行生产写入、重启或部署。
- 后续事项：发布后先 dry-run，再执行批准后的 scope contract repair apply，并复查 `/health/ready`、dirty/outbox/readiness。

## 2026-06-16 - SQL bank detail category version fallback

- 目标：修复外部往来页确认闭环时，SQL bank detail row 缺 `category_version` 但有 `manual_category_version` 或基础 `version` 时，后端 stale precondition 误报“银行流水状态已变化”的问题。
- 真实原因：`TurnoverLedgerBankRowStalePreconditionPort` 已按 `category_version -> manual_category_version -> version` 判断当前版本，但 `Application._turnover_bank_transaction_row_from_bank_detail(...)` 从 `bank_detail` SQL read model 转换 turnover flow row 时没有把 fallback 后的版本统一输出为 `category_version`。前端刷新后提交的是最新 `categoryVersion`，后端当前 row 却缺该字段，导致 expected/current 比较失败。
- 影响范围：`bank_detail` SQL read model -> turnover flow row 转换边界；不改变手动闭环业务规则、Workbench relation 写入口、dirty/outbox、operation barrier 或前端提交流。
- 关键决策：在转换边界统一写出 `category_version`，优先级保持 `category_version -> manual_category_version -> version`，无效值归零；不放宽 stale precondition，不新增 fallback 写路径。
- 文档影响：更新本实施记录和测试矩阵；长期业务口径不变。
- 测试覆盖：新增 `test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_missing`、`test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_versions_missing`、`test_sql_bank_detail_turnover_row_prefers_category_version_over_manual_version`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`；`cd web && npm test -- --run src/test/TurnoverLedgerPage.test.tsx src/test/TurnoverLedgerApi.test.ts`。
- 未测风险：本地自动化覆盖转换和前端 fresh/rebind 回归；真实生产历史数据仍需在发布后通过正常 `bank_detail` / `turnover_ledger` read model refresh 和手工 smoke 验证。

## 2026-06-16 - Workbench relation feedback projection

- 目标：补齐关联台反向影响外部往来款管理页的可见反馈。此前手工闭环会写 Workbench active pair relation 并触发刷新事件，但 turnover grouped payload 没有承载 canonical Workbench relation 状态；关联台侧撤回或补链后，流水台刷新也只能看到 turnover 本地状态。
- 影响范围：`TurnoverLedgerSqlProjectionBuilder`、standalone worker 依赖注入、`web/src/features/turnoverLedger/api.ts`、`TurnoverLedgerGroupedTable`。
- 关键决策：
  - projection 阶段通过 `WorkbenchRelationReadFacade.get_by_row_ids(require_fresh=True)` 读取 fresh 的 relation distribution，把 `workbench_relation_status`、`workbench_relation_case_ids`、`workbench_relation_mode`、`workbench_relation_source`、`workbench_relation_row_ids` 写入 grouped payload。
  - Workbench relation context 不 fresh 时抛 `workbench_relation_read_model_not_fresh`，不保存半成品 turnover read model，避免 stale relation 被包装成 fresh turnover 数据。
  - 前端只做 snake_case/camelCase 映射和状态 chip 展示，不把 domain event 或本地 React state 当事实源。
- 文档影响：更新本模块 README、state-machine、tests 和 implementation notes；长期业务口径不变。
- 测试覆盖：新增 `test_projection_enriches_rows_with_fresh_workbench_relation_context`、`test_projection_does_not_save_when_workbench_relation_context_is_not_fresh`；更新 `web/src/test/TurnoverLedgerApi.test.ts` 和 `web/src/test/TurnoverLedgerPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_model_refresh -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`；`cd web && npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx`。
- 未测风险：真实/staging 环境仍需验证 worker 顺序和页面可见性：先刷新 `workbench_relation` scope，再刷新 `turnover_ledger`，浏览器在 operation barrier fresh 后应看到 relation chip。

## 2026-06-16 - Bank detail dependency loop caused empty turnover ledger

- 目标：修复外部往来款管理页无数据、App Status 长时间显示银行明细同步中的问题。
- 真实原因：`bank_detail` 月份 read model 本身已经有外部往来流水和自动标签结果；页面无数据是因为 `turnover_ledger:all` worker 被银行明细 freshness 依赖循环阻塞。第一层问题是 downstream all-scope `bank_detail_read_model_not_fresh` 被旧 runtime worker 自动补投成 `bank_detail:all`，把 fan-out command 当成稳定 dependency。第二层问题是 `BankTransactionTagReadFacade` 曾把 fresh `bank_detail` read model 中缺失的 transaction id 误判成 read model `missing`。第三层问题是多个月份里只要一个月份 pending，facade 曾把所有月份都作为 `downstream_bank_tag_read` refresh target，刚刷完的月份被下一轮重打 pending，导致 all scope 永久等不到所有月份同时 fresh。
- 影响范围：runtime worker dependency scope 推导、read model refresh gateway active coalescing、bank tag read facade missing-row 与 blocking-scope contract；不改变外部往来 grouped ledger 业务计算、手动闭环写入、Workbench relation 写入口或前端 empty state。
- 关键决策：从架构上禁止 downstream all-scope dependency defer 推导 `bank_detail:all`；只允许从 source scope 推导具体月份。`bank_detail_all_shard` 作为 ensure/wakeup reason 参与 active coalescing，避免重复 bump 正在处理的月份 shard。fresh read model 的 missing transaction id 只作为诊断信息，downstream 外部往来计算按无标签行处理，不再补投 refresh 或抛 not fresh。非 fresh 依赖读取只补投 dirty/blocking scope，不重刷已经 fresh 的月份。
- 测试覆盖：`RuntimeWorkerTests.test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`ReadModelRefreshGatewayTests.test_bank_detail_all_shard_reason_does_not_bump_active_scope`、`BankTransactionTagReadFacadeTests.test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows`、`BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes`，并运行外部往来和免 OA read model dependency 回归。
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
