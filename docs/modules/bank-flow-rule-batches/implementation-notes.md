# 流水规则批量处理实施记录

## 2026-07-20 规则保存 O(1) 与 formal relation 合同收口

- 2026-07-14 formal-relations 合同已取代 2026-06-30 的 requirement-based paired/open 模型：active relation 完整成员进入 paired，无 active relation 的事实进入 unpaired singleton。
- 规则保存删除两次 active relation 全量扫描、逐 relation metadata/history 写、turnover mode 升级、broad lifecycle 和重复 refresh；actual change 只写 settings/audit 并 enqueue 一次 `bank_flow_rule_batch/all`。
- semantic no-op 不递增 version、不写 settings/audit、不入队。
- `BankBatchApplicationService` 中 bank-flow 可达的旧 tag writer/sync/helper 已删除；独立 no-OA legacy service 保留自身合同。
- migration `0111_bank_flow_rule_batch_tag_rules_canonical_shape.sql` 把旧 selected seed 合并到 requirements 后删除 selected shape；runtime 不留 fallback。
- 下方 2026-06-30 两个 requirement 同步章节是被本节明确废止的历史记录，不再描述当前运行时合同。

## 2026-07-06 Scope source-version freshness 修复

目标：修复生产 `bank_flow_rule_batches` API 在 `bank_flow_rule_batch:2026-07` worker 刷新已完成且耗时约 100ms 后，仍因 `bank_detail_source_versions_mismatch` 持续返回 stale 并反复 enqueue refresh 的问题。

关键决策：

- API 列表 fresh gate 对月份 scope 不再依赖 bank-detail provider 的 mutable `last_source_versions`；它和 worker 一样通过 `read_model_scope_source_versions(month)` 读取 bank-detail scope summary 与 Workbench relation source-version port。
- Worker 月份 scope rebuild 在 precheck 后若无法 skip，发布 snapshot 时复用同一份 precheck source_versions；后续 `bulk_get_for_rows(...)` 或 relation 明细读取只影响 row payload，不允许改写 scope source-version 形态。
- 不放宽 stale 判定、不把 stale 伪装成 fresh；修复的是同一 scope 内 API 期望版本与 worker 发布版本不一致的问题。
- 旧 no-OA legacy worker/模块仍是独立 legacy 域，本修复只覆盖当前 `/bank-flow-rule-batches` 生产链路和中性 bank-batch refresh core。

测试覆盖：

- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_list_freshness_uses_scope_source_versions`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_refresh_publishes_prechecked_scope_source_versions`
- `tests/test_bank_flow_rule_batch_backend_boundary.py`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_routes.py -q`

## 2026-07-04 Bank Transaction Paired Policy 全局化

目标：把“流水规则标签 / 流水规则标签管理”收敛为全局 Bank Transaction Paired Policy，并删除 bank-flow 页面链路中的旧 no-OA 历史重算和 selected-tag 兼容输出。

关键决策：

- 关联台 `WorkbenchCandidateGroupingService` 的 paired/open 分区改为：任何含银行流水的 group 都先按银行流水 row 上物化的 `requires_oa` / `requires_invoice` 或 legacy `paired_requires_*` 判定；缺失 policy metadata 默认需要 OA 和发票。
- `bank_flow_rule_batch`、工资/内部转账、外部往来、legacy no-OA 等关系类型不再能绕过全局 policy 直接进入 paired；需要无 OA/无发票闭环时，必须由 relation metadata 显式声明 false/false 或对应单项 false。
- `GET /api/bank-flow-rule-batches/tag-rules` 的 public payload 不再返回 `selected_tag_codes` / `inactive_selected_tag_codes`；前端 feature type/API/page 同步删除 `selectedTagCodes` 兼容字段。
- 删除旧 no-OA 历史重算 route、页面入口、前端 API/type/test 和 application service 中无入口的方法；旧 no-OA 历史事实仍由 `no-oa-bank-batches` 模块管理，不再挂回 bank-flow 页面。

测试覆盖：

- `tests/test_workbench_candidate_grouping.py::WorkbenchCandidateGroupingTests::test_bank_transaction_missing_policy_defaults_to_full_three_pane_requirement`
- `tests/test_workbench_candidate_grouping.py`
- `tests/test_bank_flow_rule_batch_routes.py`
- `web/src/test/BankFlowRuleBatchApi.test.ts`

## 2026-07-03 Read model unchanged source-version probe

目标：修复生产 full critical 1s smoke 中 `bank_flow_rule_batch:2026-02` 即使 `source_versions_unchanged` 也可能在 skip 前耗时约 1.4s 的问题。

关键决策：

- `bank_flow_rule_batch.read_model.refresh` 的月份 scope 先通过 bank-detail scope summary 和 Workbench relation source-version port 构造当前 source_versions，再对比 `read_model.bank_flow_rule_batch_rows` 的 source-version summary。
- source_versions 一致时直接 complete dirty scope，不再读取完整银行交易行、分类行、关系行，也不保存 snapshot。
- 无法证明 source_versions 一致时才进入完整 rebuild；`all` scope 不走月级 probe，避免无效 precheck。
- 该改动只调整 worker 内部 I/O 顺序，不改变 bank-flow API、页面 DTO、规则设置、关系状态机、readiness/outbox 事实源或审批/审计边界。

测试覆盖：

- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_scope_source_versions_use_probe_ports_before_row_loading`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_unchanged_read_model_scope_uses_bank_flow_source_version_summary`
- `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_source_versions_for_scope_keys_uses_scope_summary_without_loading_rows`

验证命令：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests tests/test_bank_flow_rule_batch_application_service.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_read_model_manifest.py -q`

## 2026-07-01 最终校验闭环

目标：关闭收口检查发现的 validation drift，确保 bank-flow tag-rule 边界即使被服务层直接调用，也不会接受旧 no-OA selected-tag 语义或重复规则覆盖。

关键决策：

- `AppSettingsService.update_bank_flow_rule_batch_tag_rules(...)` 在服务边界拒绝 `selected_tag_codes` / `selectedTagCodes`，错误码为 `bank_flow_rule_batch_selected_tag_codes_forbidden`。
- `rules[]` 中重复 `tag_code` 在归一化前 fail fast，错误码为 `duplicate_bank_flow_rule_batch_tag_rule`，不再允许后写覆盖前写。
- 不改变 no-OA legacy `selected_tag_codes` 合同；该旧写路径只属于 `no-oa-bank-batches`。
- 长期文档状态更新为 modular closure：页面级 state/effect 编排保留在 page，纯 I/O、DTO、策略、view model、operation barrier helper 和通用组件位于 feature 边界。

测试覆盖：

- `tests/test_app_settings_service.py::AppSettingsServiceTests::test_bank_flow_rule_batch_tag_rules_reject_legacy_selection_and_duplicate_rules`
- `tests/test_bank_flow_rule_batch_routes.py::BankFlowRuleBatchRoutesTests::test_tag_rules_reject_legacy_selection_and_duplicate_rules`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_app_settings_service.py tests/test_bank_flow_rule_batch_routes.py -q`
- 其余回归命令见本次最终答复。

## 2026-07-01 Read model / 操作 API 性能收敛

目标：降低流水规则批量处理页面常用操作耗时，移除 detail/withdraw/reset 中可避免的 `all` scope 同步刷新，并让 bank-flow worker 使用专属 source-version summary 跳过 unchanged scope。

关键决策：

- `detail_payload(batch_id)` 和 `withdraw_batch(batch_id)` 先读取当前 bank-flow batch storage；只有 batch 缺失时才 fallback `scope_key=all` runtime snapshot refresh。
- `reset_submitted_bank_flow_rule_batches()` 不再做前置 `all` refresh；撤回后只同步刷新受影响月份 scope，没有月份时才 fallback `all`。
- `unchanged_read_model_scope_result(...)` 按 relation mode 选择 `bank_flow_rule_batch_source_versions_summary(...)` 或 no-OA summary；worker 对 bank-flow 也启用 unchanged skip。
- `tag-rules` 保存仍保留 `all` refresh enqueue，因为规则变更可能影响所有 active bank-flow relation requirement metadata；要进一步优化需要先引入 tag/relation 到 affected scope 的可靠索引。

测试覆盖：

- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_detail_uses_current_bank_flow_batch_without_all_scope_refresh`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_detail_falls_back_to_all_scope_refresh_when_batch_is_missing`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_withdraw_uses_current_bank_flow_batch_without_all_scope_refresh`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_withdraw_falls_back_to_all_scope_refresh_when_batch_is_missing`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_reset_submitted_refreshes_affected_months_without_preflight_all_refresh`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_unchanged_read_model_scope_uses_bank_flow_source_version_summary`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_postgres_repositories_boundaries.py -q`

## 2026-07-01 Tag-rule settings family 独立切换

目标：关闭 `bank_flow_rule_batch` 运行时规则仍读取/写入 `no_oa_bank_batch_tag_selection` 的问题，避免银行流水规则批处理页面继续被 no-OA settings family 污染。

关键决策：

- 新增迁移 `0083_bank_flow_rule_batch_tag_rules.sql`，在 `app.app_settings.settings_payload` 缺失 `bank_flow_rule_batch_tag_rules` 时，从历史 `no_oa_bank_batch_tag_selection` 一次性复制规则值；运行时不做隐式 fallback。
- `AppSettingsService` 新增 `get_bank_flow_rule_batch_tag_rules_payload()` / `update_bank_flow_rule_batch_tag_rules(...)`，保留原 public payload shape、乐观锁、active tag 校验、审计和自动标签归档时的失效规则清理。
- `BankFlowRuleBatchApplicationService` 的规则读写切到 bank-flow settings key；`BankBatchApplicationService` 按 relation mode 选择 tag rules payload 和 source versions，`bank_flow_rule_batch` read model freshness 使用 `bank_flow_rule_batch_tag_rules_version`。
- 2026-07-04 后旧 no-OA 历史重算不再属于 bank-flow 页面或公开 API；历史 no-OA 事实只由 no-OA legacy 域管理。

测试覆盖：

- `tests/test_app_settings_service.py::AppSettingsServiceTests::test_bank_flow_rule_batch_tag_rules_are_independent_from_no_oa_selection`
- `tests/test_app_settings_service.py::AppSettingsServiceTests::test_update_settings_preserves_bank_flow_rule_batch_tag_rules`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_update_tag_selection_uses_bank_flow_rule_settings_boundary`
- `tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_source_versions_use_bank_flow_rule_version_boundary`
- `tests/test_bank_flow_rule_batch_routes.py::BankFlowRuleBatchRoutesTests::test_tag_rules_return_policy_rules_and_map_conflict`
- `tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_bank_flow_rule_batch_tag_rules_settings_are_split_from_no_oa_settings`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_app_settings_service.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_state_store.py -q`

## 2026-07-01 PostgreSQL 独立物理存储切换

目标：关闭 `bank_flow_rule_batch` 逻辑边界已独立但生产批次存储/read model 仍复用 no-OA 物理表的问题。

关键决策：

- 新增迁移 `0082_bank_flow_rule_batch_storage.sql`，创建 `app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`、`read_model.bank_flow_rule_batch_rows`，并从历史 no-OA 表中按 `relation_mode=bank_flow_rule_batch` 回填旧数据。
- `PostgresStateStore.load/save_bank_flow_rule_batches*` 改为调用 `PostgresWorkbenchRepository` 的 bank-flow 专属 I/O；`PostgresReadModelRepository.list_bank_flow_rule_batch_rows` 和 `bank_flow_rule_batch_source_versions_summary` 改为查询 `read_model.bank_flow_rule_batch_rows`。
- legacy no-OA 继续使用 `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events`、`read_model.no_oa_bank_batch_rows`；`relation_mode` 仍保留在 bank-flow payload/metadata 中供 API 和 Workbench relation 兼容，但不再作为 bank-flow 运行时读写 no-OA 表的条件。
- 本次不迁移标签规则 family，也不拆分前端页面状态；标签规则 family 风险已在上方 2026-07-01 `bank_flow_rule_batch_tag_rules` 切换中关闭，前端状态拆分仍保留为后续任务。

测试覆盖：

- `tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_bank_flow_rule_batch_independent_storage_schema_and_backfill_are_declared`
- `tests/test_postgres_repositories_boundaries.py::test_bank_flow_rule_batch_save_uses_dedicated_physical_tables`
- `tests/test_postgres_repositories_boundaries.py::test_no_oa_bank_batch_save_does_not_touch_bank_flow_physical_tables`
- `tests/test_postgres_repositories_boundaries.py::test_bank_flow_rule_batch_read_model_queries_dedicated_table_without_relation_mode_predicate`
- `tests/test_bank_flow_rule_batch_backend_boundary.py::BankFlowRuleBatchBackendBoundaryTests::test_postgres_state_store_bank_flow_storage_uses_dedicated_repository_io`
- `tests/test_state_store.py::StateStoreTests::test_bank_flow_rule_batches_use_independent_local_snapshot_file`

验证命令：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_postgres_migrations.py tests/test_postgres_repositories_boundaries.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_application_service.py -q`
- `git diff --check -- backend/src/fin_ops_platform/postgres/migrations backend/src/fin_ops_platform/services tests docs .planning/quick/20260701-bank-flow-rule-batches-full-closure-goal`

## 2026-06-30 App Status storage contract 补齐

目标：修复 `bank_flow_rule_batch` 已登记到 App Status read model registry，但 migration storage contract 未登记，导致完整 `tests/test_postgres_migrations.py` 失败的问题。

关键决策：

- 保留 `bank_flow_rule_batch` 作为独立 read model key、scope、worker event、operation barrier target 和 App Status readiness 目标；不回退到 `no_oa_bank_batch` registry。
- 当时不新增 `read_model.bank_flow_rule_batch_rows` 物理表，过渡期继续使用 `read_model.no_oa_bank_batch_rows`，并由 `payload.relation_mode=bank_flow_rule_batch` 及 relation-mode filter/index 隔离。该过渡判断已在 2026-07-01 被 `0082_bank_flow_rule_batch_storage.sql` 取代。
- 当时 `READ_MODEL_STORAGE_CONTRACTS["bank_flow_rule_batch"]` 显式指向 `read_model.no_oa_bank_batch_rows`，把共享物理存储从隐式 WIP 变成可验证合同；当前合同已更新为 `read_model.bank_flow_rule_batch_rows`。

测试覆盖：

- `tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_app_status_read_model_storage_contracts_are_declared`
- `tests/test_read_model_manifest.py`

## 2026-06-30 后端闭环与旧链路隔离

目标：把 `bank_flow_rule_batch` 从 no-OA route/readiness/producer/worker alias 中拆出，形成独立逻辑 API、read model、worker 和 operation barrier target。

关键决策：

- 保留 no-OA legacy 业务域本身，不删除仍被 `/api/no-oa-bank-batches/*` 使用的历史代码；删除的是 bank-flow 新链路对 no-OA route/event/scope/producer 的依赖。
- 新增 `routes_bank_flow_rule_batches.py`、`BankFlowRuleBatchApplicationService`、`BankFlowRuleBatchReadModelRefreshProducer`、`BankFlowRuleBatchReadModelRefreshService`、`BankFlowRuleBatchReadModelRepositoryPort`；`routes_no_oa_bank_batches.py` 不再处理 `/api/bank-flow-rule-batches/*`。
- `READ_MODEL_MANIFEST`、App Status read model registry、scope policy、runtime worker registry、RabbitMQ dispatch event 和 deploy env 示例均登记 `bank_flow_rule_batch` / `bank-flow-rule-batch` / `bank_flow_rule_batch.read_model.refresh`。
- Operation barrier 删除 `bank_flow_rule_batch -> no_oa_bank_batch` alias，bank-flow readiness/outbox/worker 缺失会真实返回 refreshing/blocked，不再被 no-OA fresh 状态掩盖。
- 当时批次物理存储仍使用 `app.no_oa_bank_batches` 与 `read_model.no_oa_bank_batch_rows`，必须继续用 `relation_mode=bank_flow_rule_batch` 隔离；该风险已在 2026-07-01 通过 `0082_bank_flow_rule_batch_storage.sql` 关闭。

测试覆盖：

- `tests/test_bank_flow_rule_batch_backend_boundary.py`
- `tests/test_bank_flow_rule_batch_routes.py`
- `tests/test_bank_flow_rule_batch_read_model_refresh_producer.py`
- `tests/test_operation_freshness_barrier.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_no_oa_bank_batch_routes.py`

## 2026-06-30 外部往来旧关系 requirement 同步修复

目标：

- 修复外部往来款借入/归还借款保存为不需要发票后，旧 `turnover:* manual_confirmed` active relation 仍停留在关联台未配对区的问题。

关键决策：

- 规则 UI 是 requirement owner，但 Workbench 分区事实源仍必须是 relation metadata。不能让 Workbench 在查询时读取当前 settings，因为已存在 relation 的 paired/open 判定必须可审计、可回放、可跨进程一致。
- 保存规则后，`NoOaBankBatchApplicationService.update_tag_selection(...)` 除同步 `bank_flow_rule_batch` relation 外，还会扫描 active `turnover:*` relation。若银行流水分类 code 直接命中规则，或属于外部往来/借入/借出/业务往来分类族且存在 `external_turnover` requirement，则通过 `WorkbenchRelationCommandService.update_relation_metadata_for_case_id(..., relation_mode=turnover_manual_closure)` 升级旧 relation 并写入 `requires_oa` / `requires_invoice`。
- 旧逻辑删除/隔离：普通 `manual_confirmed` 两栏 relation 不放宽；无匹配外部往来规则的 relation 不改；同步不直接写 relation 表，不依赖进程内 snapshot。

测试覆盖：

- `tests/test_no_oa_bank_batch_tag_selection_api.py::NoOaBankBatchTagSelectionApiTests::test_tag_rule_update_upgrades_legacy_turnover_relation_from_persistent_repository`
- `tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_update_relation_metadata_for_case_id_can_upgrade_relation_mode`
- `tests/test_workbench_turnover_grouping.py::WorkbenchTurnoverGroupingTests::test_two_pane_turnover_manual_closure_with_no_invoice_requirement_is_paired`

验证命令：

- `PYTHONPATH=backend/src:. pytest tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_candidate_grouping.py tests/test_workbench_turnover_grouping.py tests/test_no_oa_bank_batch_application_service.py tests/test_workbench_relation_command_service.py tests/test_workbench_relation_command_repository_adapter.py tests/test_turnover_workbench_integration.py tests/test_turnover_ledger_uow_contract.py -q`

未测风险：

- 生产需发布后执行一次同步，确认现存 `turnover:*` 旧关系被升级并触发 `workbench_relation` / `workbench` 刷新。

## 2026-06-30 规则保存同步已提交 relation requirement 修复

目标：

- 修复保存“外部往来款”等流水标签的 `OA` / `发票` requirement 后，已提交 `bank_flow_rule_batch` relation 仍按旧 requirement 留在关联台未配对区的问题。

关键决策：

- 根因不是 Workbench 分组缺展示逻辑，而是规则保存只更新 settings family 和 read model refresh，没有同步已存在 active relation 的 `special_metadata.requires_oa` / `requires_invoice` / `flow_rule_version`。Workbench 按架构只能读取 relation fact，不应在分组阶段回读当前设置，否则 settings 与关系事实会变成双事实源。
- 修复边界放在 `NoOaBankBatchApplicationService.update_tag_selection(...)`：保存规则后由流水规则模块 owner 遍历 active `relation_mode=bank_flow_rule_batch` relation，并通过 `WorkbenchRelationCommandService.update_relation_metadata_for_case_id(...)` 回写 requirement metadata。
- 生产验证发现新进程构造的内存 `WorkbenchPairRelationService` 不一定包含历史 relation；因此 no-OA/bank-flow application service 注入的 relation command 必须通过 state store / PostgreSQL durable repository load active relations，再回写同一 repository。`WorkbenchRelationCommandRepositoryAdapter` 在传入 repository 时以 repository 为 load 事实源，内存只作为未注入 repository 的兼容路径。
- 删除旧污染路径：不再在存在 `NoOaBankBatchTagSelectionApplicationService` 时提前 return；委托保存后必须继续执行 bank-flow relation requirement sync。旧 no-OA relation 不参与同步，避免 legacy 链路被新规则污染。
- 同步只更新已有 relation metadata 和版本，不让 Workbench 直接读取 settings；变更后触发 no-OA 过渡底座的 mutation persistence、derived lifecycle 和 `bank_flow_rule_batch_tag_rules_changed` refresh。

测试覆盖：

- `tests/test_no_oa_bank_batch_tag_selection_api.py::NoOaBankBatchTagSelectionApiTests::test_bank_flow_rule_tag_rule_update_resyncs_submitted_relation_requirements` 覆盖 PUT 规则后已提交 relation metadata 从 `requires_invoice=true` 同步为 `false`，并更新 `flow_rule_version`。
- `tests/test_no_oa_bank_batch_tag_selection_api.py::NoOaBankBatchTagSelectionApiTests::test_bank_flow_rule_tag_rule_update_resyncs_relation_from_persistent_repository` 覆盖进程内 relation snapshot 为空时，规则保存仍从持久化 relation repository 同步已提交 relation。
- `tests/test_workbench_relation_command_repository_adapter.py::WorkbenchRelationCommandRepositoryAdapterTests::test_load_prefers_repository_when_repository_is_configured` 锁定 adapter load 事实源。
- `tests/test_workbench_candidate_grouping.py::WorkbenchCandidateGroupingTests::test_bank_flow_rule_batch_requires_only_oa_before_paired` 覆盖只要求 OA、不要求发票时，缺 OA 留 open，补齐 OA 后进入 paired。

验证命令：

- `pytest tests/test_workbench_candidate_grouping.py::WorkbenchCandidateGroupingTests::test_bank_flow_rule_batch_requires_only_oa_before_paired tests/test_no_oa_bank_batch_tag_selection_api.py::NoOaBankBatchTagSelectionApiTests::test_bank_flow_rule_tag_rule_update_resyncs_submitted_relation_requirements -q`

未测风险：

- 本地测试使用稳定 `fee` 标签构造同步场景；生产同一同步逻辑按 `flow_rule_tag_code` 泛化到 `external_turnover` 等标签。发布后需要对生产当前 settings 执行一次同步或重新保存规则，使此前已保存但未同步的 relation metadata 收敛。

## 2026-06-30 submitted 列表 read model mode 修复

目标：

- 修复流水规则批量处理提交后，关联台已有 `bank_flow_rule_batch` relation，但页面“已提交”列表不显示该批次的问题。

关键决策：

- 根因是过渡期复用 `no_oa_bank_batch` 底座时，写侧已经使用 `relation_mode=bank_flow_rule_batch`，但构建/read model 回灌仍依赖旧 no-OA 判定。具体旧污染点包括：列表查询没有显式 relation mode I/O；active relation 回灌只识别 no-OA；服务内由 submitted batch 反推 relation fact 时把所有已提交批次硬编码为 `no_oa_bank_batch`。
- 修复边界放在服务和 read repository：`NoOaBankBatchService.build_batches`、`submit_selected_rows` 接受目标 `relation_mode`；批次 payload/read model row 携带 `relation_mode`；列表 API 将 `relation_mode` 传给 read repository；SQL read repository 用 payload relation mode 分区，旧缺字段行默认只归 `no_oa_bank_batch`。
- 服务内部旧逻辑删除/隔离：submitted/withdrawn/stale/superseded 批次保留只保留当前 refresh mode；submitted batch relation fact 只为当前 refresh mode 生成并继承 batch mode；no-OA legacy repair/migration 只能在 no-OA refresh 链路内工作，不能改写 `bank_flow_rule_batch` relation。
- 新增 `read_model.no_oa_bank_batch_rows` relation-mode 过滤表达式索引，保障过渡 read model 的 submitted/unsubmitted 查询性能。

测试覆盖：

- `tests/test_no_oa_bank_batch_service.py` 覆盖 `bank_flow_rule_batch` active relation 能投影成 submitted 批次，并且不会污染 legacy no-OA submitted 列表。
- `tests/test_no_oa_bank_batch_application_service.py` 覆盖应用层列表把 `relation_mode` 传入 read repository。
- `tests/test_no_oa_bank_batch_routes.py` 覆盖 `/api/bank-flow-rule-batches` 列表路由传入 `bank_flow_rule_batch`。
- `tests/test_no_oa_bank_batch_api.py` 覆盖 `/api/bank-flow-rule-batches/submit-selection` 提交后能在 bank-flow submitted 列表读到，并且不会进入 legacy no-OA submitted 列表。
- `tests/test_no_oa_bank_batch_read_model_refresh.py` 和 `tests/test_postgres_migrations.py` 回归 worker 与迁移清单。

验证命令：

- `pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_routes.py tests/test_postgres_migrations.py`

未测风险：

- 未新增浏览器截图回归；发布后已触发 `no_oa_bank_batch/all` refresh，metadata 使用 `bank_flow_rule_batch_read_model_refresh`，生产 read model 已存在 `bank_flow_rule_batch/submitted` 行。

## 2026-06-29 文档/边界 slice

目标：

- 将需求从“免 OA 流水批量处理”重新定位为“流水规则批量处理”。
- 先沉淀模块边界、I/O、状态机、API 合同和 E2E 规格，不做实现代码。

确认决策：

- 页面不再只处理免 OA 流水，应覆盖所有需要按银行流水标签批量处理的流水。
- 标签规则抽屉左侧事实来自银行明细 active 标签，且左侧只读。
- 右侧只保留 `OA`、`发票` checkbox。
- 勾选表示进入关联台已配对区前必须具备对应 row type；空表示不需要该项。
- 新增/未配置标签默认 `OA` 和 `发票` 都勾选。
- 旧 `selected_tag_codes` 不作为新规则迁移来源；所有数据重新按新规则处理。
- 从本页面提交的批量银行流水进入关联台；超过 3 条银行流水默认折叠。
- 是否进入已配对区仍由 OA/发票 requirement 和实际 row type 是否满足决定。

本 slice 更新：

- 新增 `docs/modules/bank-flow-rule-batches/` 模块文档骨架。
- 计划同步模块索引、canonical facts、read model 合同、Workbench relation/reconciliation/bank details 边界和 API 契约。
- GSD 记录位于 `.planning/quick/260629-bank-flow-rule-batches-boundary/`。

风险：

- 当前代码和部分文档已经包含旧 no-OA 中间实现；implementation slice 必须先清理命名和边界，避免新旧规则同时生产写入。
- 若实现阶段允许跨账户、跨月或跨标签批量提交，需要重新扩展状态机和 relation metadata；当前文档保守约束为同月、同账户、同标签。

后续事项：

- 规则持久化当前使用独立 settings key `app_settings.bank_flow_rule_batch_tag_rules`；如未来升级到独立表，必须保留版本、审计、主动迁移和删除条件。
- 实现新 route/service/read model 后，再迁移导航和旧 no-OA route。
- 编写 Playwright E2E 前先把 `e2e-spec.md` 中的 Spec ID 映射到测试名。

## 2026-06-29 实现 slice

目标：

- 将用户入口改为“流水规则批量处理”，生产调用走 `/api/bank-flow-rule-batches`。
- 重做标签规则抽屉为紧凑 grid：左侧银行标签只读，右侧仅 `OA` / `发票` requirement checkbox。
- 新路径不接收 `selected_tag_codes`；保存只提交 `rules`。
- 提交选中流水写入 `relation_mode=bank_flow_rule_batch`，metadata 保留规则版本、tag code、OA/发票 requirement 和折叠提示。
- Workbench 根据 `requires_oa` / `requires_invoice` 判定 paired/open，大于 3 条银行流水折叠，并显示“流水规则批次明细”。

当前实现说明：

- 后端 route、application service、read model key、refresh producer、worker event、operation barrier、repository port、mutation persistence port 和 refresh persistence port 已作为 `bank_flow_rule_batch` 独立边界接入。
- 旧 no-OA route 仍保留兼容；新页面和 E2E 使用 bank-flow-rule-batches route，且 bank-flow route/service/refresh 不再 import 或继承 no-OA route/application/refresh 模块。
- 共享批次计算逻辑已放入中性 `bank_batch_application_service.py` / `bank_batch_service.py`；no-OA legacy 和 bank-flow 分别从自己的模块边界调用。
- bank-flow 页面不提供历史 no-OA 管理入口；普通查询、提交、撤回和刷新不读写 no-OA batch service。
- 新功能 mutation 和前端等待使用 `read_model_key=bank_flow_rule_batch`；operation barrier 直接读取 `bank_flow_rule_batch` readiness/outbox/worker，不再映射到 no-OA。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_candidate_grouping.py tests/test_workbench_relation_command_service.py -q`
- `npm --prefix web test -- --run CandidateGroupGrid.test.tsx BankFlowRuleBatchPage.test.tsx BankFlowRuleBatchApi.test.ts App.test.tsx`
- `npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium`
- `npm --prefix web run e2e -- e2e/permissions-role-matrix.spec.ts --project=chromium`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_operation_freshness_barrier.py tests/test_read_model_manifest.py tests/test_runtime_worker_registry.py -q`
- `bash scripts/verify.sh docs`
- `npm --prefix web run build`
- `git diff --check`

剩余风险：

- 独立 `bank_flow_rule_batch` 物理表已在 2026-07-01 `0082_bank_flow_rule_batch_storage.sql` 中拆出。
- “补齐 OA/发票后从 open 进入 paired”的完整跨页浏览器动作仍需后续接入真实补票/补 OA 流程测试。

## 2026-06-30 标签规则抽屉分组 UI slice

目标：

- 将“流水规则标签管理”右侧抽屉继续保持紧凑 xlsx/grid 形态。
- `收支类型` 按连续方向合并单元格，同一方向只显示一次。
- `流水主标签` 按主标签合并单元格，同一主标签只显示一次。
- 同一 `流水主标签` 下的不同子标签共享同一行组背景色；不同主标签使用不同背景色。
- `收支类型` 第一列压缩为固定窄列，并用方向底色/左侧色带强化 `支出`、`收入`、`全部` 分隔。

边界说明：

- 主要调整前端展示层 view model、table `rowSpan` 和样式。
- 标签 direction 读取兼容 `expense/outflow/debit/支出/支` 与 `income/inflow/credit/收入/收`；后端组装 active tag 时同 code 优先采用最新银行标签定义中的 direction。
- 不改变 `active_tags` 事实来源、`requirements_by_tag_code` 持久化、保存 payload、权限、read model、operation barrier 或 Workbench paired/open 判定。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_tag_selection_api.py -q`
- `npm --prefix web test -- --run src/test/BankFlowRuleBatchPage.test.tsx`
- `npm --prefix web run build`
- `npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium`
- `git diff --check`

## 2026-06-29 已提交批次重置 slice

目标：

- 将流水规则批量处理页当前所有 `submitted` 批次恢复为可重新按规则处理的未提交候选。
- 整理迁移期数据库状态，但不手工 SQL 修改批次表或 relation 表。

关键决策：

- 新增 `POST /api/bank-flow-rule-batches/reset-submitted`，由页面“重置全部已提交”触发。
- 后端复用既有 `withdraw_batch`、`WorkbenchRelationCommandService.cancel_relation(...)`、`persist_mutation(...)` 和 operation barrier；旧批次进入 withdrawn/audit history。
- read model 后续 rebuild 后，释放的银行 rows 按当前银行标签和 OA/发票规则重新进入未提交候选；不会自动重新提交。

验证：

- `tests/test_no_oa_bank_batch_tag_selection_api.py` 覆盖提交后 reset、relation 取消、row 回到未提交候选。
- `web/src/test/BankFlowRuleBatchPage.test.tsx` 覆盖页面按钮、API payload、operation event。
- `web/e2e/bank-flow-rule-batches-flow.spec.ts` 覆盖浏览器提交后 reset 并回到未提交。

## 2026-06-30 已提交批次运行时同步修复

目标：

- 修复生产中列表显示 `bank_flow_rule_batch` submitted 批次，但详情/撤回返回“流水规则批次不存在”的问题。

关键决策：

- 列表以 SQL read model 为入口，详情/撤回仍必须操作 canonical batch service。对于由 worker 从 active relation 回灌出来的 submitted 批次，API 进程启动期快照可能晚于 worker 写入；因此 bank-flow 详情、撤回和 reset 入口先刷新 `relation_mode=bank_flow_rule_batch` runtime snapshot，再读取/修改批次。
- reset submitted 候选显式限定 `relation_mode=bank_flow_rule_batch`，禁止 legacy no-OA submitted 批次混入新页面重置链路。

验证：

- `tests/test_bank_flow_rule_batch_application_service.py` 覆盖 detail/withdraw 前刷新 runtime snapshot，以及 submitted 候选 relation mode 边界。

## 2026-07-02 批量持久化 I/O 优化

目标：

- 降低 `bank_flow_rule_batch.read_model.refresh` 在多 batch scope 下的 projection 写入 round-trip，避免逐 batch 两条 upsert 放大 worker handler 时间。
- 保持 bank-flow 与 legacy no-OA 的物理表、event 表、read model rows 完全隔离。

关键决策：

- `PostgresWorkbenchRepository.save_bank_flow_rule_batches*` 继续作为 bank-flow persistence owner，删除范围和 event 替换顺序不变。
- `app.bank_flow_rule_batches` 和 `read_model.bank_flow_rule_batch_rows` 改为批量 values upsert；payload 仍强制写入 `relation_mode=bank_flow_rule_batch`。
- 同步复用该批量 helper 优化 no-OA legacy persistence，但两者仍写各自表，禁止跨表 fallback。

验证：

- `tests/test_postgres_repositories_boundaries.py` 覆盖 bank-flow 专属物理表写入、禁止 no-OA 表污染、no-OA/bank-flow projection insert 不走逐行 `execute`。
- `PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_workbench_integration.py tests/test_bank_flow_rule_batch_application_service.py -q`

剩余风险：

- 本地优化尚未部署到生产；2026-07-02 生产 1s 高性能 baseline 中 `bank_flow_rule_batch` enqueue-to-fresh `5322.643ms`、handler `4543.139ms`，仍需部署后复测，并继续分析非写入阶段长尾。

## 2026-07-05 模块化 close 审计

目标：

- 使用 Grill me / Ponytail 对流水规则批量处理页面和上下游 I/O 做全量收口，移除 bank-flow 新链路里继续泄露的旧 no-OA 命名、source kind、错误码和文案。
- 不扩大到 no-OA legacy 模块自身退休；`/api/no-oa-bank-batches/*`、`no_oa_bank_batch` read model 和 legacy tests 仍归 `no-oa-bank-batches` 边界。

关键决策：

- `routes_bank_flow_rule_batches.py` 在 HTTP 输出边界翻译共享 bank-batch core 仍可能抛出的 legacy `no_oa_bank_batch_*` selection/relation/version/persistence 错误，公开 API 只返回 `bank_flow_rule_batch_*`。
- `workbench_candidate_grouping.py` 不再让 bank-flow 折叠摘要复用 no-OA 输出：bank-flow summary 使用 `source_kind=bank_flow_rule_batch_summary`、id prefix `bank_flow_rule_summary:`、`invoice_relation.code=bank_flow_rule_batch` 和 `流水规则` display tag，并过滤旧 `免OA` tag。
- `workbench_candidate_grouping.py` 的 Bank Transaction Paired Policy 保留 legacy `no_oa_bank_batch` 在缺失 explicit requirement metadata 时的无需 OA/发票合同；若 legacy no-OA 已写 `requires_oa` / `requires_invoice` 则仍按显式 requirement 判定。该保留只服务 no-OA legacy，bank-flow 缺失 requirement metadata 仍 fail closed 为需要 OA+发票。
- `postgres_repositories/read_models.py` 把 `bank_flow_rule_batch_summary` 纳入 Workbench summary display-only source kind，避免摘要行污染真实银行明细计数、筛选和 read model I/O。
- `web/src/features/workbench/api.ts` 与 `ReconciliationWorkbenchPage.tsx` 按 bank-flow source kind / relation metadata 识别撤回链路，用户可见文案和撤回 reason 改为“流水规则批次”。
- `web/e2e/bank-flow-rule-batches-flow.spec.ts` 与 deterministic `apiMocks.ts` 移除 bank-flow 浏览器链路里的旧 no-OA fixture I/O：transaction id 改为 `bank-flow-rule-e2e-*`，batch id 改为 `bank-flow-rule-batch-e2e-*`，relation case id 改为 `bank-flow-rule-relation-e2e-*`，成本统计 fan-out 项目名改为 `流水规则手续费成本项目`，read model stale reason 改为 `bank_flow_rule_batch_*`。
- `docs/dev/testing-closure-dependency-map.md` 从旧 no-OA 页面入口改为 bank-flow 页面入口；no-OA 只登记 legacy API/read-model。

验证：

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_routes.py tests/test_workbench_candidate_grouping.py::WorkbenchCandidateGroupingTests::test_bank_flow_rule_batch_collapses_only_when_more_than_three_bank_rows tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_treats_bank_flow_rule_batch_summary_source_kind_as_display_only -q`
- `python3 -m ruff check backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py backend/src/fin_ops_platform/services/workbench_candidate_grouping.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_bank_flow_rule_batch_routes.py tests/test_workbench_candidate_grouping.py tests/test_workbench_sql_runtime.py`
- `cd web && npm test -- --run BankFlowRuleBatchApi.test.ts CandidateGroupGrid.test.tsx`
- `cd web && npm exec tsc -- --noEmit`

## 2026-07-20 流水规则配置保存 O(1) 收敛

目标：

- 将 tag-rules 保存从两次 active relation 全量扫描与逐 relation 写回，收敛为固定成本的 settings/audit 单写和一次 bank-flow read-model refresh。
- 保持批次列表、详情、提交、撤回、重置、no-OA、关联台和流水台账合同不变。

关键决策：

- formal relation 本身决定既有关系的 paired/unpaired；relation 中的 requirement metadata 是创建时审计快照，规则保存不再追溯改写。
- bank-flow 规则 canonical payload 只保留 `version` 与 `requirements_by_tag_code`；migration 0111 移除旧 selected shape，且不修改 no-OA payload。
- 同值保存是真正 no-op；实际变化只产生一次 audit 与一次 `bank_flow_rule_batch/all` durable refresh。
- 删除旧 `_sync_bank_flow_rule_relation_requirements`、`_sync_turnover_rule_relation_requirements` 及其专用 relation 扫描/逐条写回 helper，不保留 fallback。

验证：

- 目标后端 160 passed + 15 subtests；关联回归 204 passed + 287 subtests；前端既有 3 files / 53 tests passed。
- 真实 PostgreSQL 空库应用 0001–0111，migration canonical/no-OA 隔离/幂等通过。
- 真实 PostgreSQL 20 次采样：no-op p95 `34.002ms`，actual change p95 `83.475ms`；actual change 只有 1 个 bank-flow all dirty scope、0 relation history。
- 全量后端修正后为 4200 passed、64 skipped、716 subtests；剩余 historical ETC、Workbench repository/direct cost fan-out、cost fan-out matrix 与 cost-statistics fixture 问题可在未改动基线 SHA `3c80361db` 复现，不属于本项链路。
- SHA `182c29be4d6b1f9fd91001d88600fddd411bf2ef` 已部署为 `main-182c29be-20260720015418`；migration 0111 用时 42ms，API/dispatcher/22 workers active 且 worker workdir mismatch 为 0。
- 生产 20 次读取：页面壳 p95 `139.570ms`、GET p95 `258.567ms`、Page Audit p95 `370.022ms`；60/60 通过。
- 生产同值 PUT 20 次测量 p95 `275.186ms`、max `431.232ms`，version `11 → 11`。
- bank-flow、关联台、银行明细、turnover Page Audit 全部 `pass / fresh / drained`、0 issue；本子链路生产闭环完成。

## 2026-07-20 流水规则批量处理读写性能收敛

目标：

- 把 all/month 列表从双全量 row 读取、Python 分页和摘要收敛为固定查询数的 SQL 分页/聚合。
- 把批次详情的逐成员银行流水读取改为现有 canonical repository bulk I/O。
- 把 reset 的逐 relation cancel 与请求内逐月 rebuild 改为一次 scoped bulk cancel、一次原子 delta 保存和后台 scoped reconcile。
- 删除 bank-flow 运行链中的 no-OA schema/ID/display/error/idempotency/worker/route compatibility 路径，同时保持独立 no-OA legacy 模块功能不变。

实现决策：

- `BankFlowRuleBatchReadModelRepositoryPort.read_page(...)` 是页面列表唯一 read I/O：当前页 rows 使用 `LIMIT/OFFSET`，total 使用完整列表筛选，summary 使用 month/account summary filter 聚合，source-version/readiness proof 独立返回；前端默认 page size 从 200 收窄为 50。
- `ImportNormalizationService.list_transactions_by_ids(...)` 复用 `PostgresCoreRepository.list_bank_transactions_by_ids(...)`，按输入 ID 去重并恢复稳定顺序；bank-flow detail/selection 不再调用逐 row getter。
- reset 领域状态仍逐批校验 version，但 relation command 只调用一次 `cancel_relations_by_case_ids(...)`；persistence 显式接收 `changed_batch_ids`，即使历史 active relation 已缺失也不会漏写 withdrawn batch。HTTP 请求不调用 `refresh_batches(...)`。
- submit/withdraw/reset command 成功后前端先更新本页 committed state并解除前台阻塞；`bank_flow_rule_batch` freshness wait 与 reload 作为后台 reconcile，完整跨页 targets 继续通过既有 domain event 发布。
- bank-flow service 使用独立 schema version、新 batch ID prefix、正式 display tag、错误码和 idempotency namespace；route legacy error translation map 已删除。共享 core 的中性 bank rows/source versions/stale reasons 是正式入口，no-OA 名称只保留为 legacy 模块 wrapper。

验证证据：

- 目标及隔离回归 459 tests 通过；前端 BankFlowRuleBatch page/API 43 tests 通过。
- Chromium `bank-flow-rule-batches-flow.spec.ts` 最终 9/9 通过；reset 写后不自动触发下一批 detail GET，后台重读稳定使用 unsubmitted/page 1。
- 真实本地 PostgreSQL 空库应用全部 migrations 后，paged query + aggregate summary integration test 通过；验证 draft presentation、pagination total 和完整 summary 金额/计数。
- architecture guard 固定 bank-flow route/application/refresh wrapper 不得出现 `no_oa`、`NO_OA`、`免OA` 或 legacy error map。
- 最终唯一 SHA、部署 release、生产读/写性能、Page Audit 和 worker drain 证据在本次统一发布验证完成后补录。

生产首轮验证与补充收敛：

- release `main-a3a331b5-20260720030257` 首轮 20 次读测量中，页面壳 p95 `108.923ms`、Audit p95 `265.977ms` 已通过；all 列表从基线 `965.789ms` 降到 `539.327ms`，但仍未达到 `500ms` 门槛；2026-07 月列表 p95 `720.336ms`，且首次请求真实经历一次 stale/enqueue。因此本阶段没有提前关闭。
- runtime 指标显示列表数据库 p95 约 `80.504ms`，而 server p95 约 `606.884ms`，剩余瓶颈主要在请求内 Python source-version/presentation，而不是 SQL 分页本身。
- 删除列表热路径中重复的 relation source-version 预加载；月份 expected-source read 本身已经通过同一 facade 读取该 scope，旧调用造成一次重复 I/O。
- shared source-version port 现在按显式 relation mode 传递 `bank_flow_rule_batch_source_version_precheck`；bank-flow API/worker 不再把旧 `no_oa_bank_batch_source_version_precheck` reason 污染到 dependency I/O，no-OA legacy 默认值只保留在自身调用链。
- 当前页 50 个 batch 与约 40 个 summary category 过去会分别调用 `tag_dictionary_payload()`，每次 deep-copy 整份分类字典；现在每个请求只建立一次 definition index 并复用，不新增跨请求 payload cache。
- `BankTransactionCategoryService.snapshot_version()` 缓存与完整 snapshot 序列化完全相同的 SHA-256，只在分类或 tag dictionary 实际变更时失效。20,000 条合成记录中，旧 copy+hash 约 `212.869ms`，首次无 copy hash 约 `190.723ms`，后续读取约 `0.005ms`；该优化保持 hash 合同不变，不改变其它页面数据。
- 目标与 no-OA 隔离回归 `103 passed`，lint 通过；必须部署新 SHA 后重新执行相同 20 次生产读测量，未达门槛不得关闭。

生产第二轮与 durable freshness 收敛：

- SHA `1be049026` 部署为 `main-1be04902-20260720032126` 后，all 列表 p95 降至 `244.072ms` 并通过；month 列表 p95 为 `541.278ms`，20/20 fresh、零 enqueue，但仍高于 `500ms`，阶段继续保持 open。
- runtime 证明 month 与 all 的主要差异是每次 month GET 额外跨读 bank-detail/workbench-relation live source versions，查询数 p95 `15`；这绕过了页面 repository 的 durable freshness 边界，并在每次只读请求重复 worker 才需要的 dependency precheck。
- 列表删除 live dependency source-version读取，改为只消费 `read_page(...)` 返回的本模块 durable dirty/readiness/source-consistency proof。canonical writer仍必须事务内写 dirty/outbox，worker仍执行完整 source-version precheck；不存在“事实变了但页面继续伪装 fresh”的 fallback。
- repository 对 fresh 月份 scope 的多个 distinct source versions返回 `schema_mismatch`，API返回明确 stale reason并入队 scoped refresh；all scope允许不同月份具有不同 source versions。
- 同时删除 month readiness 对同一 dirty scope 的重复查询。真实 disposable PostgreSQL应用 0001–0111 后，SQL分页/聚合/混合 source-version fail-closed integration test通过；目标测试中的既有 cost-statistics fan-out fixture failure不属于本改动且未放宽。

最终生产读验证与写门禁：

- SHA `a5e5b795a` / release `main-a5e5b795-20260720032959` 的最终 20 次生产采样全部达标：页面壳 p95 `130.237ms`、all list p95 `272.284ms`、2026-07 month list p95 `260.943ms`、Page Audit p95 `322.560ms`；80/80 成功，list 40/40 fresh 且零 enqueue。
- 1-row 与 33-row 详情各 20 次测量，p95 分别为 `175.940ms` 与 `337.446ms`；`bank-flow-rule-batches`、关联台、银行明细、流水台账、成本统计五个 Page Audit 均 `pass / fresh / drained / ready`、0 issue。
- 生产 submit/withdraw 可逆样本没有被擅自执行：首次 mutation 的强制 `app-health-operations` 预检发现 `tax-offset`、`input-invoice-usage`、`output-invoice-collections`、`settings` 四个范围外页面已有 integrity issue，并在写前 fail closed。为保持模块隔离和九页面串行，当前模块不跨界修复、也不绕过门禁；该写证据在主控流程最终系统门、全局预检恢复 pass 后补做。
