# 外部往来款管理 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口、回归范围和未测风险。实现后按实际影响更新矩阵。

## 影响面清单

外部往来款不是孤立页面。修改时必须先确认影响面：

| 影响面 | 当前事实源 | 需要保护的行为 |
| --- | --- | --- |
| 页面和 API client | `web/src/pages/TurnoverLedgerPage.tsx`、`web/src/features/turnoverLedger/api.ts` | grouped table、标签抽屉、补充信息 drawer、人工闭环 drawer、导出 dialog、loading/empty/error/stale、权限禁用 |
| Operation overlay | `GlobalOperationOverlayProvider`、`web/src/features/operationBarrier/api.ts` | tag-selection、extra、confirm、withdraw 成功后等待 `turnover_ledger` barrier fresh，再 reload grouped payload；失败不假装同步，成功后不能残留操作失败/同步失败/read model 失败等可见错误提示 |
| API contract | `backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/app/routes_turnover_ledger.py`、`docs/dev/api-contracts.md` | `GET /api/turnover-ledger`、tag-selection、bank-row-tags batch、extra、confirm、withdraw、export-preview/export |
| Business core | `TurnoverRelationService`、`TurnoverLedgerService`、`TurnoverLedgerExtraService` | 外部往来标签准入、同组一收一支、零差额、同对方、同语义、人工闭环、撤回、extra 校验、内部转账排除 |
| Write UoW | `TurnoverLedgerWriteFacade`、`TurnoverLedgerWriteUnitOfWork`、`turnover_ledger_write_adapters.py` | stale precondition、idempotency、relation/extra/settings/bankdetail 写入、dirty/outbox 同事务、rollback、Workbench relation command service 委托 |
| Read model / worker | `TurnoverLedgerQueryService`、`TurnoverLedgerSqlProjectionBuilder`、`TurnoverLedgerReadModelRefreshService` | fresh/stale/missing/refreshing、source versions、group breakdown、Workbench relation 状态投影、worker complete dirty scope |
| 跨页面影响 | Workbench pair relation、Bank Details、Cost Statistics、Search、App Status | 手动闭环进入 Workbench active pair relation；撤回/分类变化后下游不能读旧 relation；App Status 不能误判 green |
| 前端跨页事件 | `web/src/features/domainEvents.ts` | `turnoverRelationUpdated`、`workbenchRelationUpdated`、`turnoverLedgerExtraUpdated` 只触发刷新提示，不替代后端 dirty/outbox |

## 现有测试入口

后端核心测试：

- `tests/test_turnover_relation_service.py`
- `tests/test_turnover_ledger_service.py`
- `tests/test_turnover_ledger_extra_service.py`
- `tests/test_turnover_ledger_source_versions.py`
- `tests/test_turnover_ledger_export_service.py`

后端 API / UoW / read model / worker：

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_ledger_query_service.py`
- `tests/test_turnover_ledger_read_facade.py`
- `tests/test_turnover_ledger_read_model_refresh.py`
- `tests/test_turnover_workbench_integration.py`
- `tests/test_workbench_turnover_grouping.py`
- `tests/test_app_status_overview_service.py`
- `tests/test_runtime_worker_registry.py`

前端：

- `web/src/test/TurnoverLedgerApi.test.ts`
- `web/src/test/TurnoverLedgerPage.test.tsx`
- `web/src/test/domainEvents.test.ts`
- `web/e2e/turnover-ledger-flow.spec.ts`
- `docs/modules/turnover-ledger/e2e-spec.md`
- `docs/modules/turnover-ledger/e2e-coverage.md`

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 当前结论 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_service.py`、`tests/test_turnover_ledger_extra_service.py` | 已覆盖四类 family、候选/确定候选、人工闭环、重复/跨对方/非零差额/同方向拒绝、撤回、内部转账排除、extra 字段校验、分组金额和利息。 |
| 2. Service-layer tests | 适用 | `tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_ledger_api.py`、`tests/test_turnover_workbench_integration.py`、`tests/test_workbench_pair_relation_service.py` | 已覆盖 UoW transaction、rollback、dirty/outbox、stale precondition、idempotency、settings/extra/bankdetail/relation ports、Workbench relation command service 委托、缺 command fail-fast、既有 OA-bank relation 合并进外部往来闭环、撤回闭环恢复旧 OA-bank relation 和 Workbench pair relation、`cash_closure_case_id` 撤回不回退 legacy pair service。 |
| 3. API contract tests | 适用 | `tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_read_facade.py` | 已覆盖列表/grouped/tag-selection/bank-row-tags/extra/confirm/withdraw/export、权限、错误、版本冲突、idempotency replay/conflict、stale conflict、relation freshness 诊断、导出上限结构化错误、HTML response routing error。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh.py`、`tests/test_turnover_ledger_source_versions.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 已覆盖 stale SQL read model 不伪装 fresh、missing required SQL read model 返回 refreshing、legacy fallback、source versions、projection 保存、Workbench relation fresh 状态写入 grouped payload、Workbench relation non-fresh 不保存半成品、worker handler、registry/App Status 登记。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/src/test/OperationBarrierApi.test.ts`、`web/e2e/turnover-ledger-flow.spec.ts` | 已覆盖 API mapper、首屏 grouped GET 暂时失败后的错误态/刷新恢复/防 false-empty、tag drawer 保存、grouped table、正向 chip（“已关联 OA”“已关联 发票”“收支闭环”）、移除旧负向/泛化 chip、manual closure、仅已关联 OA 的 flow row 不禁用确认闭环、同一 `cash_closure_case_id` flow-row toolbar 撤回、提交前 fresh/rebind 最新 flow row versions、刷新后所选流水消失时不发 POST、跨组/非零差额禁用、extra drawer、detail missing error、stale 阻断 manual closure、operation overlay、导出、domain event；真实 Chromium 覆盖首屏 503 后手动刷新台账恢复、标签准入保存、`turnover_ledger:all` barrier、台账重读、同组两条 flow rows 确认闭环、成本统计 fresh read model fan-out、toolbar 撤回，并在恢复/成功节点检查无可见错误残留。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/e2e/turnover-ledger-flow.spec.ts` | 已覆盖 deterministic 不进入 Workbench、manual zero-difference closure 写 Workbench pair relation、canonical write safety 不通过时不半写入、legacy relation 不污染 Workbench grouping、前端闭环前重刷台账且闭环后刷新关联台可见性；Browser e2e 覆盖 tag-selection -> barrier -> reload、confirm 后等待 operation barrier、进入成本统计断言 fresh explorer 和闭环成本行，再回周转页 withdraw 后重读 grouped payload，且成功后没有操作失败/同步失败/read model 失败等可见错误残留。 |
| 7. Existing feature regression tests | 适用 | 上述全部，加 `tests/test_workbench_turnover_grouping.py`、`web/src/test/domainEvents.test.ts`、`web/e2e/turnover-ledger-flow.spec.ts` | 已保护旧 grouped shape、legacy flat/read model 兼容、标签准入 selected codes、导出字段、Workbench open grouping、Bankdetail tag batch、旧 relation/system relation 拒绝、domain event contract、成本统计下游 fresh read model 展示，以及真实浏览器里 tag selection、closure/recovery 不破坏表格选择、toolbar 状态和“成功但报错提示仍显示”的回归。 |

当前首轮闭环未发现必须立即新增的 P0 测试。已有 turnover 测试覆盖密度高，本轮不为了覆盖率新增低价值测试。

## 场景覆盖清单

| 场景 | 代表测试 |
| --- | --- |
| grouped GET 暂时失败恢复 | `web/src/test/TurnoverLedgerPage.test.tsx::recovers grouped ledger after a transient load failure when refreshed`、`web/e2e/turnover-ledger-flow.spec.ts::recovers grouped ledger after a transient load failure when refreshed` |
| 外部往来标签准入默认选择和版本冲突 | `test_turnover_ledger_tag_selection_get_put_and_version_conflict` |
| tag-selection queue failure rollback | `test_turnover_ledger_tag_selection_queue_failure_rolls_back_settings_save`、`test_tag_selection_outbox_failure_rolls_back_settings_save_and_audit` |
| grouped read model stale/missing | `test_stale_sql_read_model_is_not_returned_as_fresh_and_enqueues_refresh`、`test_missing_required_sql_read_model_returns_empty_refreshing_payload_and_enqueues_miss` |
| grouped table 金额和真实 flow rows | `test_grouped_ledger_places_flow_amounts_by_turnover_action_type_and_exposes_breakdowns`、`test_expands_Jia_Xiaohua_with_real_flow_rows_instead_of_allocation_lot_rows` |
| 人工零差额闭环 | `test_manual_zero_difference_closure_creates_open_bank_only_workbench_relation`、`test_closure_request_boundary_returns_workbench_visibility_freshness_targets`、`test_manual_closure_accepts_three_bank_rows_and_keeps_workbench_open`、`test_manual_closure_merges_existing_oa_bank_relations_and_withdraw_restores_them`、`test_confirms_a_manual_zero-difference_turnover_closure_from_three_same-group_flow_rows`、`test_turnover_manual_closure_merges_existing_oa_bank_relations`、`test_turnover_manual_closure_rejects_rows_already_in_turnover_closure`、`test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service`、`test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure` |
| SQL runtime 银行流水闭环事实源 | `test_sql_bank_detail_turnover_rows_keep_legacy_source_ids_for_manual_closure`、`test_sql_turnover_rows_tolerate_early_startup_before_app_settings_service_is_bound` |
| 前端闭环提交前最新版本保护 | `refreshes the grouped ledger before manual closure and submits latest bank row versions`、`blocks manual closure when a selected flow disappears after the fresh ledger reload`、`shows grouped read model stale warning and blocks manual closure` |
| 非法闭环拒绝 | `test_confirm_zero_difference_closure_rejects_duplicate_row_ids`、`test_confirm_zero_difference_closure_rejects_cross_counterparty_rows`、`test_confirm_zero_difference_closure_rejects_non_zero_difference`、`test_confirm_zero_difference_closure_rejects_same_direction_pair` |
| stale/idempotency | `test_target_confirm_request_expected_versions_reach_write_command`、`test_target_confirm_idempotency_key_replays_without_duplicate_confirm_or_refresh`、`test_withdraw_stale_precondition_rejects_changed_relation_before_mutation_or_refresh`、`test_manual_closure_uses_canonical_relation_when_workbench_relation_read_model_is_stale` |
| relation extra | `test_relation_extra_get_returns_default_structure_and_put_persists`、`test_target_relation_extra_stale_expected_version_rejects_without_save_or_refresh`、`test_relation_extra_outbox_failure_does_not_return_best_effort_success` |
| Bankdetail tag batch fan-out | `test_turnover_bank_row_tag_batch_refreshes_all_required_scopes`、`test_target_turnover_bank_row_tag_batch_queue_failure_rolls_back_category_save` |
| Workbench 回归 | `test_deterministic_turnover_relation_does_not_group_bank_rows_in_workbench`、`test_bank_only_turnover_manual_closure_rows_remain_open_even_when_linked`、`test_manual_pair_relation_occupied_bank_row_is_not_overridden_by_turnover_relation`、`test_withdraw_restores_previous_relations_from_turnover_manual_closure_history`、`test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service`、`test_turnover_workbench_pair_port_withdraw_restores_merged_oa_bank_relations`、`test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure_withdraw`、`test_turnover_workbench_pair_port_delegates_cash_closure_withdraw_to_relation_command_service`、`test_turnover_workbench_pair_port_requires_relation_command_service_for_cash_closure_withdraw`、`test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service` |
| 前端闭环 chip 和 toolbar | `shows Workbench relation feedback from the grouped ledger payload`、`allows manual closure confirmation when selected rows are only linked to OA`、`withdraws a selected linked manual closure from the table toolbar`、`web/e2e/turnover-ledger-flow.spec.ts` |
| Worker / App Status | `test_worker_handler_rebuilds_scope_and_completes_dirty_scope`、`test_domain_registry_covers_frontend_routes`、`test_required_worker_missing_marks_critical_domain_blocked` |
| Workbench relation 状态投影 | `test_projection_enriches_rows_with_fresh_workbench_relation_context`、`test_projection_does_not_save_when_workbench_relation_context_is_not_fresh`、`maps ledger, detail, confirm, and withdraw responses from snake_case`、`shows Workbench relation feedback from the grouped ledger payload` |
| `bank_detail` dependency fan-out 不阻塞 all-scope 台账 | `RuntimeWorkerTests.test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`ReadModelRefreshGatewayTests.test_bank_detail_all_shard_reason_does_not_bump_active_scope` |
| fresh missing bank tag rows 不阻塞 all-scope 台账 | `BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_keeps_fresh_status_when_some_rows_are_not_projected`、`BankTransactionTagReadFacadeTests.test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` |
| blocking dirty scope 粒度不阻塞 all-scope 台账 | `BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` |
| bank detail tag facade 下游版本合同 | `BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_returns_standardized_fresh_tagged_rows`、`BankTransactionTagReadFacadeTests.test_bulk_get_for_rows_preserves_versions_for_downstream_preconditions` |
| 前端 stale 写禁用 | `shows grouped read model stale warning and blocks manual closure`、`web/e2e/turnover-ledger-flow.spec.ts::shows stale grouped ledger data without allowing manual closure` |
| 前端 operation-to-fresh closure | tag-selection、extra、manual closure confirm/withdraw 后保持全屏 overlay；manual closure confirm 提交前等待 `turnover_ledger:all` fresh 并 reload/rebind 最新 flow rows，提交后只把后端 `freshness_targets` 中的 `turnover_ledger`、`workbench_relation` 作为硬等待目标，`workbench` 月份/all 聚合继续后台收敛；若 POST 成功后的 operation barrier/reload 被 blocked 或超时，页面显示“操作已提交，后台同步尚未完成” warning，不弹“操作失败”；`web/e2e/turnover-ledger-flow.spec.ts` 在真实 Chromium 中覆盖标签准入保存 -> barrier -> ledger reload，以及同组 flow rows confirm -> 成本统计 fresh read model fan-out -> withdraw recovery，并检查成功后无可见错误残留 |
| 手动闭环后同对方剩余流水保留 | `test_manual_closure_keeps_remaining_same_counterparty_rows_in_auto_relation`、`test_grouped_ledger_keeps_unselected_same_counterparty_flows_after_manual_closure` |

## 历史 bug 回归库

| 风险/历史问题 | 当前保护 |
| --- | --- |
| deterministic 被误当作已闭环并进入 Workbench | `tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py` |
| grouped 视图把 allocation lot 当真实流水导出或展示 | `tests/test_turnover_ledger_export_service.py`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 外部往来 export-preview/export 对超大 group 或展开后超大 flow rows 同步生成预览/XLSX，拖慢 API 线程和内存；或前端下载路径/页面弹窗吞掉后端超限消息 | `tests/test_turnover_ledger_export_service.py::TurnoverLedgerExportServiceTests::test_export_rejects_group_count_above_sync_row_limit`、`tests/test_turnover_ledger_export_service.py::TurnoverLedgerExportServiceTests::test_export_rejects_flattened_flow_rows_above_sync_row_limit`、`tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_export_limit_returns_structured_error`、`web/src/test/TurnoverLedgerApi.test.ts::surfaces backend row-limit messages from failed export downloads`、`web/src/test/TurnoverLedgerPage.test.tsx::shows backend export row-limit messages inside the export dialog` |
| stale read model 下仍允许确认/撤回/extra 写入 | `web/src/test/TurnoverLedgerPage.test.tsx` stale 写禁用测试，后端 stale precondition 测试 |
| manual closure 抽屉缓存旧 row version，POST 使用旧 `expected_versions` 被后端拒绝，导致关联台没有生成配对/open 组 | `refreshes the grouped ledger before manual closure and submits latest bank row versions`、`blocks manual closure when a selected flow disappears after the fresh ledger reload` |
| 已被 `turnover_manual_closure` 关联台关系占用的 flow row 在表格中被选中后，toolbar 仍只提供“确认闭环”，用户无法从当前选择直接撤回手工闭环，且可能误点普通闭环路径 | `withdraws a selected linked manual closure from the table toolbar` |
| 已关联 OA 的银行流水被 `workbench_relation_status=linked` 误当成外部往来闭环，导致“确认闭环”被禁用，并显示模糊的“关联台已关联/已关联业务单据/未闭环”等旧 chip | `allows manual closure confirmation when selected rows are only linked to OA`、`shows Workbench relation feedback from the grouped ledger payload` |
| 流水 1 已配对 OA1、流水 2 已配对 OA2、流水 3 未配对时，外部往来确认闭环未把 5 项放入同一个 active case，或撤回闭环时误删/不恢复原 OA-bank relation | `test_turnover_manual_closure_merges_existing_oa_bank_relations`、`test_withdraw_restores_previous_relations_from_turnover_manual_closure_history`、`test_manual_closure_merges_existing_oa_bank_relations_and_withdraw_restores_them`、`test_turnover_workbench_pair_port_withdraw_restores_merged_oa_bank_relations` |
| 已经存在 `turnover_manual_closure` 的流水被再次确认闭环，替换掉原闭环关系而不是提示先撤回 | `test_turnover_manual_closure_rejects_rows_already_in_turnover_closure` |
| 同一对方多笔外部往来中只选择两笔确认闭环后，`rebuild_from_bank_rows()` 删除了包含已闭环 row 的整个自动 relation，导致未选流水从外部往来页消失 | `test_manual_closure_keeps_remaining_same_counterparty_rows_in_auto_relation`、`test_grouped_ledger_keeps_unselected_same_counterparty_flows_after_manual_closure` |
| SQL bank detail row 或 grouped read model flow row 缺 `category_version` / `category_version=0` 占位时，转换出的 turnover flow row、保存的 grouped projection 或写入前置校验没有回退到 `manual_category_version` 或基础 `version`，导致后端 stale precondition 误报“银行流水状态已变化”；或者版本语义改变后未 bump `turnover_ledger_schema_version`，旧 projection 被继续当 fresh 返回 | `test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_missing`、`test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_versions_missing`、`test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_is_zero`、`test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_version_is_zero`、`test_grouped_ledger_uses_manual_version_when_category_version_is_zero`、`test_grouped_ledger_uses_bank_row_version_when_category_versions_are_zero`、`test_source_versions_include_all_turnover_and_cross_module_inputs`、`test_bank_row_stale_precondition_uses_manual_version_when_category_version_is_zero`、`test_bank_row_stale_precondition_uses_base_version_when_category_versions_are_zero`、`test_manual_closure_api_accepts_sql_rows_with_zero_category_version`、`test_sql_bank_detail_turnover_row_prefers_category_version_over_manual_version` |
| `BankTransactionTagReadFacade` 从 fresh `bank_detail` read model 给 turnover worker 提供标签事实时丢弃 `category_version`、`manual_category_version`、`version`，导致 fresh `turnover_ledger` grouped payload 仍提交 `expected_versions=0`，后端当前 bank row 版本为 `1/2` 时正确拒绝为 stale | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_returns_standardized_fresh_tagged_rows`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_bulk_get_for_rows_preserves_versions_for_downstream_preconditions` |
| 关联台撤回或补链后，流水台 grouped payload 仍只显示 turnover 本地状态，无法反馈 Workbench active relation 当前事实；或 Workbench relation read model stale 时发布新的 turnover read model，导致 stale relation 伪装 fresh | `test_projection_enriches_rows_with_fresh_workbench_relation_context`、`test_projection_marks_workbench_bank_pair_as_cash_closure_when_group_zeroes_out`、`test_projection_does_not_save_when_workbench_relation_context_is_not_fresh`、`shows Workbench relation feedback from the grouped ledger payload` |
| SQL runtime 下闭环写路径读取 legacy import snapshot，而不是 `bank_detail` SQL read model，导致生产已有流水仍报 `unknown_transaction_id` 或 stale，且 Workbench relation 没有写入 | `test_sql_bank_detail_turnover_rows_keep_legacy_source_ids_for_manual_closure` |
| Postgres 事务写路径绕过 read model scope policy，确认/撤回外部往来时向成本统计投递裸月份或裸 `all`，导致 `cost_statistics` dead-letter 和 App Status failed | `test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction`、`test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear` |
| 写操作成功后 `turnover_ledger` 仍 refreshing 时页面提前可操作或展示旧分组 | `web/src/test/TurnoverLedgerPage.test.tsx` operation overlay 回归、`web/src/test/OperationBarrierApi.test.ts` |
| queue/outbox 失败后 API 返回成功导致 read model 永久旧 | `tests/test_turnover_ledger_uow_contract.py` rollback tests |
| relation extra legacy full snapshot fallback 误吞持久化问题 | `tests/test_turnover_ledger_api.py` dedicated store / no full snapshot fallback tests |
| 外部往来 API 写 Bankdetail facts 后漏刷 Workbench/Turnover | `test_turnover_bank_row_tag_batch_refreshes_all_required_scopes` |
| 银行标签配置损坏为只有 label 的历史定义，旧确认记录缺外部往来 action，导致台账/关联台无法重建关系 | `tests/test_bank_transaction_category_service.py::BankTransactionCategoryServiceTests.test_legacy_category_record_uses_current_external_definition_semantics`、`tests/test_bank_details_sql_runtime.py::BankDetailSqlProjectionBuilderTests.test_rebuild_enriches_legacy_confirmation_from_current_external_tag_definition` |
| `turnover_ledger:all` 遇到 `bank_detail_read_model_not_fresh` 后自动补投 `bank_detail:all`，与 bank detail 月份 fan-out 互相 bump，页面长期 refreshing 且无数据 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_detail_all_shard_reason_does_not_bump_active_scope` |
| fresh `bank_detail` read model 里缺少部分 transaction id 时被误判为 non-fresh，`downstream_bank_tag_read` 持续刷新月份 shard，台账 all scope 永久 pending | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` |
| 多个月份中一个 `bank_detail` 月份 pending 时，facade 重刷所有月份，导致已 fresh 月份被快速父重试反复打 pending，台账 all scope 等不到同时 fresh | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` |
| 测试使用 `TemporaryDirectory(ignore_cleanup_errors=True)` 掩盖后台 job executor 未关闭，导致外部往来写入链路可能在临时目录释放时仍有异步写入残留 | `tests/test_turnover_ledger_api.py` 已切换为严格 `TemporaryDirectory()`；受影响用例在退出临时目录前调用 `app.shutdown_background_jobs()`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api tests.test_historical_etc_business_batch_migration_service -v` 覆盖 136 个严格清理回归 |

新增线上或手工发现 bug 时，必须先在本节补复现测试名称，再修实现。

## 关键 Smoke Flow

本地自动化重点保护：

1. 银行明细已确认外部往来分类 -> tag-selection 生效 -> 等待 `turnover_ledger:all` operation barrier -> grouped ledger 重新加载。`web/e2e/turnover-ledger-flow.spec.ts` 已在真实 Chromium 中覆盖标签准入保存请求体、barrier、reload 和成功后无可见错误残留。
2. grouped table 选择同组多条真实 flow rows -> 提交前等待台账 fresh 并重绑最新 row versions -> 人工零差额闭环 -> Turnover manual relation + Workbench pair relation -> 成本统计 fresh read model 展示闭环成本行；若所选流水已有 OA-bank relation，则合并进同一个 active case -> 前端刷新。`web/e2e/turnover-ledger-flow.spec.ts` 已在真实 Chromium 中覆盖两条同组 flow rows 的 confirm 主链路，并断言闭环后只显示“收支闭环”、成本统计展示 `外部往来闭环成本项目`，且成功后无可见错误残留。
3. 手动闭环 relation 撤回 -> 只撤回同一 `cash_closure_case_id` 的多流水闭环，并恢复确认前的 OA-bank relation；关联台已经配对的同组银行收支闭环从外部往来页撤回时走 `/api/turnover-ledger/closures/withdraw`，与关联台撤回同一条 Workbench command service 链路；已升级为包含发票或其他业务 row type 时必须从关联台撤回；Workbench relation read model 不 fresh 时必须 fail fast 且不产生 Turnover 半写入。`web/e2e/turnover-ledger-flow.spec.ts` 已覆盖已闭环 flow row toolbar 撤回和 grouped payload 移除“收支闭环”。
4. extra 保存 -> relation row 更新 -> `turnoverLedgerExtraUpdated` 只作为局部刷新提示。
5. grouped ledger `read_model_status=stale` -> 页面显示非最新 warning、保留当前 flow rows；即使选中两条真实流水，确认闭环仍禁用，Browser smoke 断言零 confirm mutation。
6. tag-selection / bank-row-tags / confirm / withdraw / extra 的 outbox 失败必须 rollback 或显式暴露失败。
7. tag-selection / extra / confirm / withdraw -> 全屏 overlay；manual closure 提交前额外执行 `turnover_ledger:all` fresh gate 和 grouped reload/rebind -> 写成功后等待 operation barrier fresh -> reload grouped ledger -> overlay 释放；若写成功后的 barrier/reload 被 blocked 或超时，仅显示后台同步 warning，不得把已提交操作渲染成“操作失败”。Browser smoke 已断言 confirm/withdraw 都触发 `POST /api/operation-barrier/status`。

真实环境 smoke 仍需在发布前执行：

- 真实 PostgreSQL 历史数据上刷新 `turnover_ledger` read model。
- 真实 RabbitMQ/Redis/systemd worker drain。
- 浏览器导出 XLSX 文件打开检查；本地已覆盖超过 20,000 行同步导出 fail-closed，但不覆盖真实下载/打开耗时。
- 大数据 grouped table 性能和滚动检查。

## 模块验证命令

后端目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_read_facade tests.test_turnover_ledger_read_model_refresh tests.test_turnover_ledger_uow_contract tests.test_turnover_workbench_integration -v
```

前端目标验证：

```bash
cd web && npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/GlobalOperationOverlayContext.test.tsx src/test/OperationBarrierApi.test.ts src/test/domainEvents.test.ts
cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts
```

文档验证：

```bash
bash scripts/verify.sh docs
```

严格临时目录清理验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api tests.test_historical_etc_business_batch_migration_service -v
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 通过 backend unittest discovery、frontend Vitest、frontend build 和 deterministic Playwright smoke 覆盖本模块。Browser smoke 当前包含 `web/e2e/turnover-ledger-flow.spec.ts`，用于保护真实 Chromium 中 grouped GET 暂时 503 后手动刷新恢复、tag-selection save、operation barrier、ledger reload、manual closure confirm、成本统计 fresh read model fan-out、withdraw、grouped payload recovery 和成功后无可见错误残留。由于 turnover 后端测试数量多，nightly 可以发现大部分 API/UoW/read model/worker 回归；本地开发时仍应优先运行上方目标验证命令，减少反馈时间。

## 未测风险

- 真实生产 PostgreSQL 历史数据中的重复、缺字段、半迁移状态，不能由本地 fixture 完全证明。
- 真实 RabbitMQ/Redis/systemd worker drain、网络抖动和 worker 重启恢复需要 staging 或生产前 smoke。
- 大数据量 grouped table、导出 XLSX 文件、浏览器视觉遮挡、mutation 级网络失败和真实下载打开耗时需要真实浏览器/样本验证；本地 Playwright smoke 只覆盖小样本 grouped GET 失败恢复和 confirm/withdraw 主链路。
- 外部往来写路径仍保留 legacy fallback 分支；常规 manual closure/withdraw 已通过 command service 收敛，未来删除 fallback 前需要单独回归。
- 自动标签规则恢复只证明银行明细 read model 可从当前定义补齐历史确认语义；真实生产仍需刷新对应 `bank_detail`、`turnover_ledger`、`workbench_relation`、`workbench` scopes 后验证 open 区可见。
