# 关联台测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

关联台是高 fan-out 页面，任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 自动候选规则 | `WorkbenchMatchingRules`、`WorkbenchFreeMatchingEngine`、special pair rule service | 单笔 OA-bank、OA-bank 多流水合计、OA-发票、OA-bank-invoice、canonical OA 附件发票、免 OA、内部转账、工资等 legacy/special rules |
| 人工确认/撤回/候选拆分 | `/api/workbench/actions/confirm-link`、`cancel-link`、`withdraw-link`、idempotency、UoW | active pair relation、审计、preview lock、版本冲突、重复提交、in-progress replay、撤回恢复上一状态、无 history 撤到无关联、操作后未恢复 row 逐行独立、纯候选 split/suppress |
| 异常处理 | exception classifier/application/projection | open/closed exception、ignore/unignore、金额差异 note、OA 免单、异常取消 |
| Active generation read model | `read_model.workbench_generations`、`workbench_rows/groups/summary/stats` | 原子发布、active pinning、failed generation 不可提升、retention 不删 active |
| Query facade / Redis cache | `WorkbenchQueryFacade`、groups page cache warmer | 只缓存 fresh payload；refreshing/stale/unavailable 不写 Redis；query timeout 有明确 refreshing/unavailable |
| Matching dirty scope | workbench matching dirty queue/worker | lifecycle 只 mark dirty；worker drain matching；失败不回退 legacy dirty scope |
| Relation read model | `workbench_relation` | 批量账务、银行明细 relation tags、下游 invoice lifecycle/cost/tax/search |
| 前端交互 | `ReconciliationWorkbenchPage`、`CandidateGroupGrid`、selection hooks、column/filter tests | loading/refreshing/stale/error、权限禁用、三栏 selection、详情、筛选排序、domain event 刷新、后台刷新期间局部 pending row lock |
| 跨页面 fan-out | bank details、pending invoices、batch accounting、turnover ledger、cost statistics、App Health | relation 确认/撤回后旧页面不能读 stale/empty 伪 fresh |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| OA-bank 单笔精确候选 | P0 | `tests/test_workbench_matching_rules.py`、`tests/test_workbench_free_matching_engine.py` | covered | 基础候选规则，避免误配。 |
| `oa_bank_exact_sum` 多银行流水合计候选 | P0 | `tests/test_workbench_matching_rules.py`、`tests/test_workbench_free_matching_engine.py`、`tests/test_workbench_matching_orchestrator.py`、`tests/test_workbench_v2_api.py` | covered | 覆盖唯一性、证据要求、单笔优先、API grouping。 |
| 三方闭环与 open/paired 分区 | P0 | `tests/test_workbench_candidate_grouping.py`、`tests/test_workbench_reconciliation_engine.py`、`tests/test_workbench_v2_api.py` | covered | active relation 优先于自动候选。 |
| 确认/撤回 idempotency、preview lock、版本冲突和 command 写边界 | P0 | `tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_idempotency_contract.py`、`tests/test_workbench_stale_write_contract.py`、`tests/test_workbench_v2_api.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | 防止重复提交、旧版本写入、不稳定 replay，以及缺 command 时回退到 pair snapshot 直接写。withdraw preview/submit 锁定 `operation_type`、`preview_id`、`submit_expected_versions`。 |
| 纯自动候选 group 统一按钮拆分 | P0 | `tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_candidate_match_service.py`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/WorkbenchSelectionModel.test.ts` | covered | 未配对区点击任一 row 带入完整 group；无 active relation 时后端 preview 判定 `split_candidate`，submit suppress candidate 为 `manual_override`。 |
| 撤回 preview 操作后分组 | P0 | `tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_preview_after_groups_unrestored_bank_invoice_rows_individually`、`tests/test_workbench_pair_relation_service.py`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_withdraw_link_does_not_restore_display_only_existing_case_group`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_withdraw_link_splits_bank_invoice_rows_when_prior_case_id_was_display_only` | covered | active relation 撤回到无关系时，操作后银行流水和发票逐行独立展示；`existing_case` 只能作为显示归属，不能作为撤回可恢复 relation。 |
| 个人暂借款还清 special relation | P0 | `tests/test_workbench_v2_api.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | 创建 settled exception case 与 `personal_advance_repayment_settlement` relation；缺 command 时不得先写 exception case 或 direct pair fallback。 |
| 异常 preview/apply/cancel/ignore | P0 | `tests/test_workbench_exception_*`、`tests/test_workbench_v2_api.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | 覆盖 exception projection、分类、API 行为，以及 closed apply relation command 写边界。 |
| Workbench active generation pinning | P0 | `tests/test_workbench_sql_runtime.py` | covered | groups/summary/detail 必须读取同一个 active generation。 |
| Row detail live/cache/SQL fallback | P0 | `tests/test_workbench_sql_runtime.py`、`tests/test_workbench_query_facade.py` | covered | `GET /api/workbench/rows/{row_id}` 对 opaque OA id 先 live/cache，miss 后按 month hint/all scope 读取 SQL active generation，不从 row id 猜月份失败成 404。 |
| Failed/stale generation 状态 | P0 | `tests/test_workbench_sql_runtime.py`、`tests/test_workbench_query_facade.py` | covered | failed generation 不能被提升为 fresh。 |
| Groups query freshness/cache | P0 | `tests/test_workbench_query_facade.py` | covered | refreshing/stale 不写 Redis；fresh 才缓存。 |
| Refresh handler / dirty scope done | P0 | `tests/test_workbench_sql_runtime.py` | covered | worker refresh 后发布 generation 并完成 dirty scope。 |
| Matching dirty queue | P0 | `tests/test_workbench_dirty_queue_wiring.py`、`tests/test_workbench_matching_dirty_scope_worker.py` | covered | DB dirty queue 是主路径，失败不回退 legacy dirty scopes。 |
| Relation tags 下游投影 | P0 | `tests/test_workbench_v2_api.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_bank_details_service.py` | covered | 银行明细、批量账务和下游页面不能读旧 relation。 |
| OA 附件正式发票统一事实源 | P0 | `tests/test_import_service.py`、`tests/test_workbench_v2_api.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_query_service.py`、`tests/test_workbench_relation_sql_projection.py` | covered | OA 附件正式发票通过 import service promotion 到 `app.invoices`；Workbench SQL 投影只读 canonical invoice；legacy OA query service 不发布 invoice row；relation projection 不回捞 `read_model.workbench_rows` 作为事实源。 |
| Active relation row 去重 | P0 | `tests/test_workbench_pair_relation_service.py`、`tests/test_workbench_pair_relation_integrity_repair.py`、`tests/test_workbench_api.py` | covered | 同一 relation 重复 row id 被 normalize/repair/query grouping 去重，跨 active case 复用 row 被拒绝。 |
| 外部往来 bank-only open 规则 | P0 | `tests/test_workbench_turnover_grouping.py`、`tests/test_turnover_workbench_integration.py`、`web/src/test/WorkbenchSelection.test.tsx` | covered | `turnover_manual_closure` 是共同事实源但不再是 bank-only paired 例外；三栏补齐前留 open。 |
| OA offset / 附件上下文 repair | P0 | `tests/test_workbench_v2_api.py`、`tests/test_workbench_relation_command_service.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | OA 附件发票冲抵自动闭环和缺失附件上下文 repair 必须通过 relation command service 写入。 |
| 前端 action 后 emit `workbenchRelationUpdated` | P1 | `web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/CandidateGroupGrid.test.tsx`、页面事件 listener tests | covered | 保护当前页面/同会话刷新提示。 |
| 前端 loading/stale/error/permission | P1 | `web/src/test/WorkbenchApi.test.ts`、`web/src/test/WorkbenchApiRuntimePath.test.ts`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppHealthStatusContext.test.tsx` | covered for current gates | Workbench stale/loading 不全局禁用无关写；OA dirty/refreshing 仍禁写；提交成功后局部锁刚操作 group；OA 申请人列详情 icon 和第二行时间 chip 受交互测试保护。 |
| 前端三栏列布局与选择状态 | P1 | `web/src/test/WorkbenchColumns.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/WorkbenchSelectionHook.test.tsx` | covered | 银行详情 icon 移到对方户名、发票详情 icon 移到发票号码、发票金额列合并、seller chip 第三行；打开详情不再让“已选 0”的行呈 selected 高亮。 |
| 真实生产 active generation 回放 | P2 | 运维 runbook / SQL dry-run | documented-risk | 需要真实历史数据和 worker/staging 环境。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_workbench_matching_rules.py`、`tests/test_workbench_free_matching_engine.py`、`tests/test_workbench_exception_classifier.py`、`tests/test_workbench_amount_check_service.py` | 规则、金额、方向、证据、候选唯一性、异常分类属于核心业务。 |
| 2. Service-layer tests | 适用 | `tests/test_workbench_matching_orchestrator.py`、`tests/test_workbench_pair_relation_service.py`、`tests/test_workbench_exception_application_service.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_workbench_write_characterization.py`、`tests/test_workbench_uow_contract.py` | 覆盖 service 编排、状态写入、relation command 委托、exception apply/个人暂借款缺 command fail-fast、审计/idempotency、UoW 和 rollback。 |
| 3. API contract tests | 适用 | `tests/test_workbench_api.py`、`tests/test_workbench_v2_api.py`、`tests/test_workbench_query_facade.py` | 覆盖 query/action/preview/cancel/refresh status、payload shape、错误字段和 stale/fresh 状态。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_workbench_sql_runtime.py`、`tests/test_workbench_read_model_service.py`、`tests/test_workbench_dirty_queue_wiring.py`、`tests/test_workbench_matching_dirty_scope_worker.py` | active generation、dirty scope、refresh worker、Redis page cache、retention。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/Workbench*.test.tsx`、`web/src/test/CandidateGroupGrid.test.tsx`、`web/src/test/WorkbenchApi*.test.ts` | 覆盖三栏、selection、列/筛选、API mapper、runtime path、domain event。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_workbench_v2_api.py`、`tests/test_etc_backend.py`、`tests/test_turnover_workbench_integration.py`、`tests/test_no_oa_bank_batch_workbench_integration.py` | 覆盖 ETC/no-OA/turnover/confirm-withdraw 等跨模块链路。 |
| 7. Existing feature regression tests | 适用 | 全部 Workbench regression tests | 关联台是共享事实源；任何改动都要问会影响哪些旧候选、旧分区、旧 action、旧下游页面。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-10 | `oa_bank_exact_sum` 多流水合计候选需要同时覆盖 legacy candidate 和 decision/free engine。 | `tests/test_workbench_matching_rules.py`、`tests/test_workbench_free_matching_engine.py`、`tests/test_workbench_matching_orchestrator.py`、`tests/test_workbench_v2_api.py` | covered |
| 2026-06-09 | 已有 active relation 的 ETC summary 不得继续出现在 open 区。 | `tests/test_workbench_sql_runtime.py`、`tests/test_etc_backend.py` | covered |
| 2026-06-08 | 已提交 ETC 批次需要折叠为 `etc_invoice_summary` open 行，不能散票进入关联台。 | `tests/test_etc_backend.py`、`tests/test_workbench_candidate_grouping.py` | covered |
| 2026-06-11 | paired 详情出现两个一模一样 OA：active relation payload 中重复 row id 被 UI/query 原样展开。 | `tests/test_workbench_pair_relation_service.py`、`tests/test_workbench_pair_relation_integrity_repair.py`、`tests/test_workbench_api.py::WorkbenchApiTests::test_relation_groups_dedupes_duplicate_relation_row_ids` | covered |
| 2026-06-11 | 外部往来 bank-only 手动闭环被 exactly 2 bank rows 例外错误放入 paired。 | `tests/test_workbench_turnover_grouping.py::WorkbenchTurnoverGroupingTests::test_bank_only_turnover_manual_closure_rows_remain_open_even_when_linked`、`tests/test_turnover_workbench_integration.py::TurnoverWorkbenchIntegrationTests::test_manual_zero_difference_closure_creates_open_bank_only_workbench_relation` | covered |
| 2026-06-12 | `confirm-link` / `cancel-link` 缺 relation command service 时回退到 pair snapshot 直接写，形成第二写入口。 | `tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_confirm_and_cancel_link_fail_fast_without_relation_command_service`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback` | covered |
| 2026-06-12 | 关联台 withdraw 预览/提交绕过 command service，且无 history 时沿用合成 OA 附件恢复，容易形成与“恢复上一状态/撤到无关联”冲突的状态。 | `tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_preview_withdraw_relation_returns_locked_previous_state`、`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_withdraw_relation_rejects_stale_preview_identity`、`tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_link_preview_and_submit_delegate_to_relation_command_service`、`tests/test_workbench_v2_api.py -k withdraw_link` | covered |
| 2026-06-12 | withdraw preview 操作后仍按旧 `case_id` 合并未恢复的银行流水和发票，导致三栏展示成同一行。 | `tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_preview_after_groups_unrestored_bank_invoice_rows_individually` | covered |
| 2026-06-12 | App Health 把 workbench read model dirty/stale/rebuilding scopes 映射成 `oaSync=dirty`，导致后台刷新期间关联台全局禁写。 | `web/src/test/AppHealthStatusContext.test.tsx::reports yellow when the backend says the workbench read model is stale`、`web/src/test/WorkbenchSelection.test.tsx::workbench stale refresh does not globally disable selected group actions`、`web/src/test/WorkbenchSelection.test.tsx::OA dirty sync still disables selected group actions` | covered |
| 2026-06-12 | relation submit 成功后后台刷新未结束期间，用户可能对刚操作 group 触发二次写；旧方案也容易把全页面锁住。 | `web/src/test/WorkbenchSelection.test.tsx::confirm link locks only the operated group while the background refresh is pending` | covered |
| 2026-06-12 | 未配对区只有部分 relation snapshot group 会带入整组，普通自动候选需要手动点多栏，无法用统一按钮拆分候选。 | `web/src/test/WorkbenchSelectionModel.test.ts`、`web/src/test/WorkbenchSelection.test.tsx`、`tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_link_splits_pure_candidate_group_without_relation_history` | covered |
| 2026-06-12 | 个人暂借款还清先写 exception case 再 direct pair relation，绕过 relation command freshness/审计边界。 | `tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_personal_advance_repayment_delegates_relation_write_to_command_service`、`tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_personal_advance_repayment_fails_fast_without_relation_command_service`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_personal_advance_repayment_uses_relation_command_boundary` | covered |
| 2026-06-12 | Workbench exception closed apply 直接调用 pair service 创建 `normal_match` / `oa_exempt` relation，绕过统一 freshness/审计边界。 | `tests/test_workbench_exception_application_service.py::WorkbenchExceptionApplicationServiceTests::test_apply_closed_exception_delegates_pair_relation_to_command_service`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_exception_application_uses_relation_command_boundary` | covered |
| 2026-06-12 | `server.py` 在 payload build/repair 中直接创建或取消 OA offset / OA 附件上下文 relation，绕过 command service 审计边界。 | `tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_confirm_relation_allows_oa_invoice_offset_auto_match_mode`、`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_replace_existing_confirm_uses_requested_history_operation_type`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_server_active_relation_repairs_use_relation_command_boundary` | covered |
| 2026-06-12 | 关联台三栏点击 OA 详情时，opaque row id 无法解析月份且 live/cache miss 后未读取 SQL active generation，导致详情抽屉显示“详情加载失败”。 | `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_row_detail_reads_sql_row_without_application_live_sync`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_row_detail_sql_runtime_uses_query_facade_for_opaque_oa_after_live_and_cache_miss`、`web/src/test/WorkbenchSelection.test.tsx::OA applicant column keeps the detail icon on the first line and time chip on the second line` | covered |
| 2026-06-13 | OA 附件发票历史 parser cache 只有费用项 ID + 附件名身份，`app.oa_attachment_invoice_cache_sources` 未持续维护 `attachment_identity_*` bridge，导致 Workbench rebuild 退回全 cache JSON 扫描并把同步拖到十几秒以上。 | `tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_attachment_cache_save_updates_source_lookup_rows`、`tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_oa_attachment_invoice_cache_sources_is_indexed_lookup_table`、`tests/test_workbench_sql_runtime.py` | covered |
| 2026-06-13 | all-scope publish 主要耗时在写 `workbench_rows/groups/group_rows`；盲目把所有批量写入改成 multi-row VALUES 会让 `rows/groups` 变慢。 | `tests/test_postgres_connection.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_workbench_unused_write_indexes_are_dropped`、生产 `scripts/rehydrate-workbench-read-models.py --profile-internal` | covered |
| 2026-06-13 | OA 附件发票和人工导入发票走不同事实源，导致 Workbench、税金/成本下游读取不一致，且人工导入进/销 chip 因 `input/output` 未映射而缺失。 | `tests/test_import_service.py`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_promotes_formal_invoice_to_canonical_source`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata`、`web/src/test/WorkbenchColumns.test.tsx` | covered |
| 2026-06-13 | 取消所有选择后，详情焦点 row 因 `selectedRowId` fallback 被误判为 selected，表现为“已选 0”但蓝色高亮。 | `web/src/test/WorkbenchSelectionHook.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` | covered |
| 2026-06-14 | all-scope 从多个 month shard 聚合时，同一发票或同一银行流水因 supplement、standalone 和 candidate/source group 同时存在，被重复发布成多个 open visible/operable row；点击其中一个会因同 row id 重复暴露而联动高亮另一个。 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_all_scope_suppresses_open_invoice_rows_claimed_by_stronger_open_group`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_all_scope_suppresses_open_bank_rows_claimed_by_stronger_open_group` | covered |
| 2026-06-14 | `oa_bank_exact_sum` 把“光大银行贷款利息”OA、弱 token“科技”的中科视拓服务费流水、OA 项目名“云南溯源科技”token，以及已被 next-month no-OA active relation 或 submitted no-OA batch 占用的流水拼成 paired 自动决策；all-scope 还可能留下 partial automatic decision group。 | `tests/test_workbench_free_matching_engine.py::WorkbenchFreeMatchingEngineTests::test_single_oa_multiple_bank_sum_rejects_generic_technology_token_only`、`tests/test_workbench_free_matching_engine.py::WorkbenchFreeMatchingEngineTests::test_single_oa_multiple_bank_sum_rejects_project_name_only_vendor_token`、`tests/test_workbench_matching_rules.py::WorkbenchMatchingRulesTests::test_oa_bank_exact_sum_rejects_generic_technology_token_only`、`tests/test_workbench_matching_rules.py::WorkbenchMatchingRulesTests::test_oa_bank_exact_sum_rejects_project_name_only_vendor_token`、`tests/test_workbench_reconciliation_engine.py::WorkbenchReconciliationEngineTests::test_active_relation_rows_in_matching_window_are_excluded_before_matching`、`tests/test_workbench_matching_orchestrator.py::WorkbenchMatchingOrchestratorTests::test_legacy_mode_excludes_active_relation_rows_in_matching_window`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_all_scope_drops_partial_automatic_decision_groups_claimed_by_paired_shards`、`tests/test_workbench_reconciliation_decision_cleanup.py`、`tests/test_workbench_reconciliation_decision_store.py::WorkbenchReconciliationDecisionStoreTests::test_repository_cleanup_audit_lists_active_relation_overlaps_in_matching_window` | covered |
| 2026-06-14 | withdraw history 把 `existing_case` 显示归属当成可恢复 relation，导致“操作后”或提交后银行流水+发票仍在同一行，批量账务撤回也会把 OA 附件 case 分组恢复成 active relation。 | `tests/test_workbench_pair_relation_service.py::WorkbenchPairRelationServiceTests::test_replace_with_confirmed_relation_does_not_persist_display_only_existing_case_history`、`tests/test_workbench_pair_relation_service.py::WorkbenchPairRelationServiceTests::test_withdraw_ignores_historical_display_only_existing_case_before_relation`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_withdraw_link_does_not_restore_display_only_existing_case_group`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_withdraw_link_splits_bank_invoice_rows_when_prior_case_id_was_display_only`、`tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_withdraw_does_not_restore_display_only_oa_invoice_snapshot_as_active_relation` | covered |
| 长期 | stale/failed active generation 被读成 fresh 或缓存到 Redis。 | `tests/test_workbench_sql_runtime.py`、`tests/test_workbench_query_facade.py` | covered |
| 长期 | 关系确认/撤回影响银行明细、批量账务、往来款、成本统计等旧页面。 | `tests/test_workbench_v2_api.py`、`tests/test_batch_accounting_api.py`、`tests/test_turnover_workbench_integration.py`、`web/src/test/*` | covered / per-module continuation |

## 关键 smoke flows

1. `导入/OA/ETC/关系变更 -> workbench dirty scope -> worker refresh -> active generation publish -> /api/workbench fresh -> 页面三栏展示`
2. `open candidate -> group selection -> confirm preview -> confirm submit -> active pair relation -> domain event -> downstream relation read models refresh`
3. `paired relation -> withdraw preview locked by preview_id/expected_versions -> previous state restored or no-history unlinked -> dirty scopes/readiness/App Health 收敛`
4. `open automatic candidate -> group selection -> split_candidate preview -> submit suppresses candidate -> workbench refresh no longer groups the same candidate`
5. `ETC business batch submitted -> etc_invoice_summary open row -> OA/bank/invoice 三项确认 -> paired 区展开明细`
6. `Workbench query refreshing/stale -> 页面展示刷新/陈旧状态 -> Redis 不缓存 stale payload -> 无关 group 可继续操作 -> 后续 fresh 后更新`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_rules tests.test_workbench_free_matching_engine tests.test_workbench_matching_orchestrator -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_workbench_dirty_queue_wiring tests.test_workbench_matching_dirty_scope_worker -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_groups_page_pins_versions_counts_and_rows_to_single_active_generation tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_refresh_status_api_exposes_dirty_scopes_and_worker_lag -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_keeps_oa_bank_exact_sum_candidate_in_one_open_group tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_and_cancel_link_defer_read_model_persistence_to_background -v
cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchApiRuntimePath.test.ts src/test/WorkbenchSelection.test.tsx src/test/CandidateGroupGrid.test.tsx
bash scripts/verify.sh docs
```

扩展回归按改动选择：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend tests.test_turnover_workbench_integration tests.test_no_oa_bank_batch_workbench_integration -v
cd web && npm test -- --run src/test/WorkbenchExceptionModal.test.tsx src/test/WorkbenchZone.test.tsx src/test/WorkbenchColumnLayout.test.tsx src/test/WorkbenchColumns.test.tsx
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend vitest 和 build，覆盖完整 Workbench 测试集。单轮模块验证只跑最小闭环，避免把所有历史 Workbench case 作为每次人工推进的阻塞项。

## 未测风险

- 本轮不运行真实生产库 active generation 全量回放；需要 staging/生产只读验证。
- 前端视觉布局和大数据性能需要浏览器/真实数据 smoke，Vitest 主要保护交互和 API mapper。
- 关联台仍有 legacy `server.py` handler 和多条生产相关链路；后续改动应按具体影响选择扩展回归，而不是只跑最小闭环。
