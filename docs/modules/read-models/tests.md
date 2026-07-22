# Read Model 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口、影响面、P0/P1/P2 缺口和未测风险。全局依赖地图见 `../../dev/testing-closure-dependency-map.md`。

## 修改前影响面清单

- 页面入口：无独立页面；所有列表/统计页面都依赖 read model freshness/status 语义。
- API client：`web/src/features/*/api.ts` 中消费 `read_model_status`、`read_model_stale_reasons`、`refresh_enqueued`、`source_versions` 的 API mapper。
- 操作闭环 API client：`web/src/features/operationBarrier/api.ts` 只轮询后端 freshness barrier，不能在前端自行推断 read model fresh。
- 后端 route：`backend/src/fin_ops_platform/app/server.py` 与 `backend/src/fin_ops_platform/app/routes_*.py` 中所有 read model 查询型 endpoint。
- Service / repository：
  - `backend/src/fin_ops_platform/services/read_model_query_gateway.py`
  - `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
  - `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
  - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
  - `backend/src/fin_ops_platform/services/read_model_scope_contract.py`
  - `backend/src/fin_ops_platform/services/read_model_readiness.py`
  - `backend/src/fin_ops_platform/services/runtime_queue.py`
  - `backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py`
- Read model：当前页面 critical 集合为 `workbench`、`workbench_relation`、`bank_detail`、`bank_account_balance`、`pending_invoice`、`search`、`invoice_lifecycle`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`cost_statistics`、`tax_offset`、`bank_flow_rule_batch`、`turnover_ledger`。`no_oa_bank_batch` 仅作为 legacy API/read-model 回归项保留，不再进入默认 production page SLO 或 `read_model_slo_smoke --critical-only`。
- Worker / dirty scope：`job.read_model_dirty_scopes`、`job.outbox_events`、`RuntimeQueueRepository.enqueue_read_model_refresh(...)`、`runtime_worker_registry.py` 中 read model worker event types。
- Domain event：前端 domain event 只作为刷新提示；read model freshness 和 worker readiness 是事实源。
- 权限 / 审计：本模块不直接做权限判定；风险来自 API route 绕过 read boundary 或 service 直接写 runtime 表。
- 导出 / 文件：导出 API 依赖 fresh gate 后的 rows/summary；导出 shape 由各业务模块测试保护。
- 缓存：Redis 只能缓存 fresh gate 后 payload；`ReadModelQueryGateway` 负责 cache hit/miss 语义。
- 外部依赖：PostgreSQL durable queue 是事实源；Redis/RabbitMQ 不是事实源。
- 可能影响的旧页面：所有依赖 read model 的页面，尤其关联台、银行明细、待找发票、进项/销项/OA 待付款、税金抵扣、成本统计、免 OA、批量账务、往来款和 App Health。
- 可能被哪些上游写入影响：导入确认、关系确认/撤回、规则保存、no-OA 批处理、税金认证导入、设置重置、project scope 变化、read model miss/stale。`startup_stale_scan` 默认关闭；启用时只标记 stale workbench matching dirty scopes，不是用户可见 read model 的直接 refresh 来源。
- 依赖地图引用：`../../dev/testing-closure-dependency-map.md` 的 Read Model / Worker 依赖图、API Contract 风险图和共享风险热点。

## 场景覆盖清单

## 2026-07-16 - cost statistics bounded export read contract

- 变更类型：成本 read-model port 新增 cost-owned export-page read I/O；不改变其他 read model、worker、queue、schema、权限或前端。
- 覆盖证据：preview 最多 8 行；download repository page 最大 1,000；首批完整 summary、后续无重复 summary；non-fresh 零 export rows；文件结束时发布版本变化 fail-closed。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_read_model_manifest.py`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_bulk_export_does_not_reload_full_explorer_payload`。
- 七类测试决策：business、service、API、read model、local integration、regression 适用；frontend 无行为变化。
- 未测风险：真实 PostgreSQL planner、大数据 memory/latency 与生产并发发布留到统一部署后；本轮未部署。

## 2026-07-16 - cost statistics broad state I/O removal

- 变更类型：成本 read-model repository/state-store contract 收窄；不改变其他 read model、HTTP contract、worker event、queue schema、schema migration、权限或前端。
- 覆盖证据：成本 port/manifest 不再暴露全量 load 或无 source-version save；Postgres/local state store 不再携带成本 snapshot key；原 row persistence 测试改走带 dirty source version 的 conditional publish。
- 新增/更新测试：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_does_not_retain_full_snapshot_load_or_unconditional_save_io`、`tests/test_postgres_state_store.py::PostgresStateStoreTests::test_postgres_full_state_snapshot_omits_cost_statistics_read_model`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_postgres_repositories_boundaries.py`、`tests/test_read_model_manifest.py`。
- 七类测试决策：service-layer、read model/cache/background job、projection→publish→query integration、existing regression 适用并覆盖；business core、frontend 不适用，API 仅复跑既有合同回归。
- 未测风险：真实 PostgreSQL planner、worker drain 与生产 p95/p99 留到统一部署后的 evidence gate；本轮未部署。

## 2026-07-13 - committed write SLO miss 恢复收敛门禁

- 变更类型：生产 write-operation E2E recovery orchestration；不改变业务关系状态机、HTTP response shape、read model scope、worker event、queue schema、权限或前端行为。
- 覆盖证据：mutation HTTP 已提交但同步写超过 5s 时，runner 保留原 SLO failure，同时使用响应中的精确 outbox receipt 等待 fan-out 完成；只有随后隔离页可读为 fresh，才读取恢复基线并执行正式撤回 checkpoint。首批 receipt 完成后的合法链式 fan-out 允许 consumer gate 对 `202/not fresh/503` 轮询；业务字段或 fresh 响应 latency 失败不可重试。
- 新增/更新测试：`tests/test_write_operation_e2e_smoke.py::WriteOperationE2ESmokeTests::test_committed_write_slo_miss_waits_for_fanout_before_recovery_baseline`、`test_consumer_wait_retries_refreshing_but_not_content_or_latency_failures`；既有 committed/ambiguous recovery、双 checkpoint、System Audit retry 和 impact matrix 回归继续覆盖。
- 七类测试决策：service-layer orchestration、read model/cache/background job、end-to-end business-flow recovery、existing feature regression 适用并覆盖；business core、API contract、frontend interaction 不适用，因为业务规则、外部接口和 UI 均未改变。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest -q tests/test_write_operation_e2e_smoke.py tests/test_write_operation_impact_matrix.py`；`bash scripts/verify.sh lint`。
- 未测风险：本地 fake 不能证明真实 worker drain；发布后必须重新执行同一受控可逆生产场景，并确认 recovery 不再在 `202 refreshing` 上失败。

## 2026-07-06 - Page read model fact-display matrix guard

- 变更类型：spec-first coverage guard / documentation contract；不改变运行时代码、HTTP response shape、权限、业务状态机、worker event、queue schema 或前端行为。
- 覆盖证据：`docs/dev/page-read-model-fact-display-matrix.json` 逐页登记当前 17 个页面 route/pageKey、read model key、生产只读 freshness probe、页面事实源、配对关系事实源和 deterministic Browser/API 证据；`tests/test_page_read_model_fact_display_matrix.py` 强制矩阵与 `web/src/app/pageRegistry.tsx`、App Status read model registry、HTTP SLO probe registry 和证据文件同步。
- 当前页面命名约束：`/bank-flow-rule-batches` 是“流水规则批量处理”，页面矩阵必须使用 `bank_flow_rule_batch`；legacy `no_oa_bank_batch` 只保留后端回归，不进入当前页面 read model/fact-display 覆盖矩阵。
- 七类测试决策：read model/cache/background job、frontend interaction evidence、end-to-end business-flow evidence、existing feature regression 适用并覆盖；business core、service-layer、API contract 不新增运行时断言，因为本轮只固化页面覆盖合同，不改变业务规则、服务编排或 HTTP shape。
- 验证命令：`PYTHONPATH=backend/src:. python3 -m pytest tests/test_page_read_model_fact_display_matrix.py tests/test_spec_first_e2e_docs.py -q`。
- 未测风险：该 guard 证明每个当前页面都有 fresh 入口和事实源显示证据，不证明生产受控写后所有下游页面 1s 内强可见；生产 mutating cross-page freshness 仍由 write-operation SLO / 受控写影响矩阵覆盖。

## 2026-07-06 - Write operation impact matrix guard

- 变更类型：spec-first write-operation coverage guard / documentation contract；不改变运行时代码、HTTP response shape、权限、业务状态机、worker event、queue schema 或前端行为。
- 覆盖证据：`docs/dev/write-operation-impact-matrix.json` 覆盖 `write_operation_slo_audit.DEFAULT_OPERATION_EXPECTATIONS` 当前全部 24 个 operation profile，逐项登记 source page、write endpoint、写入事实源、配对关系事实源、expected outbox scopes、目标 read model/page、生产 gate policy、1s/3s SLO 和 deterministic 证据。
- 新增/更新测试：`tests/test_write_operation_impact_matrix.py` 强制矩阵与 write-operation audit scopes、App Status read model registry、页面 fresh/fact-display 矩阵、standing ticket policy 和证据文件同步；legacy `no_oa_bank_batch` 只允许作为后端 profile/read model，并通过当前“流水规则批量处理”页面的 `bank_flow_rule_batch` 代理 read model 显式记录。
- 七类测试决策：read model/cache/background job、end-to-end business-flow integration evidence、existing feature regression 适用并覆盖；frontend interaction 通过矩阵引用现有 Browser 证据；business core、service-layer、API contract 不新增运行时断言，因为本轮只固化写操作影响覆盖合同，不改变业务规则、服务编排或 HTTP shape。
- 验证命令：`PYTHONPATH=backend/src:. python3 -m pytest tests/test_write_operation_impact_matrix.py tests/test_page_read_model_fact_display_matrix.py -q`。
- 未测风险：该 guard 不执行生产写操作；`standing_apply` 仍需要真实认证、standing ticket 和 `write_operation_e2e_smoke --apply`，导入/设置类写入仍需要 staging 或单次审批。

## 2026-07-06 - no-OA legacy critical SLO 降级

- 变更类型：production SLO target / app status registry alignment；不改变 legacy no-OA API、worker event、read model payload、权限或审计。
- 覆盖证据：当前前端页面入口是 `/bank-flow-rule-batches`，默认 HTTP SLO 采样 `/api/bank-flow-rule-batches` 与 `/api/bank-flow-rule-batches/tag-rules`；`no_oa_bank_batch` 在 App Status read model registry 中标为 non-critical，`read_model_slo_smoke --critical-only` 只覆盖当前页面 critical read model。
- 新增/更新测试：`tests/test_http_slo_probe.py`、`tests/test_read_model_slo_smoke.py`、`tests/test_app_status_overview_service.py`。
- 七类测试决策：read model/cache/background job、API/tool contract、existing regression 适用并覆盖；business core、frontend interaction、E2E 不新增，因为不改变用户操作、页面 UI 或业务状态转换。
- 验证命令：本轮统一运行相关 pytest、lint、docs 和生产 SLO。
- 未测风险：legacy `/api/no-oa-bank-batches/*` 仍由后端回归测试保护；若未来要彻底删除 no-OA 代码，需要单独做 route/service/worker/scenario 全量删除计划。

## 2026-07-03 - Runtime queue available-at SLO boundary

- 变更类型：runtime queue / write-operation SLO timing contract；不改变 HTTP response shape、权限、业务状态机、worker event type、dirty/outbox schema 或 read model payload schema。
- 覆盖证据：事务内 read model refresh 写入显式使用 `clock_timestamp()` 记录 `available_at` / current update time；write-operation SLO 用 `available_at -> processed_at` 衡量 enqueue-to-done，避免长业务事务的 transaction start `now()` 污染 worker drain 指标。
- 新增/更新测试：`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_enqueue_read_model_refresh_in_transaction_preserves_source_version_payload_and_outbox_contract`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_enqueue_read_model_refreshes_in_transaction_batches_dirty_scope_and_outbox_writes`、`tests/test_write_operation_slo_audit.py::WriteOperationSloAuditTests::test_enqueue_duration_uses_available_at_instead_of_transaction_created_at`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；business core 不新增，因为业务规则/金额/状态转换不变；API contract 和 frontend interaction 不新增，因为 response shape 与页面行为不变；E2E 仍由生产固定 write scenario/ticket 复测证明。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_workbench_uow_contract.py tests/test_write_operation_slo_audit.py tests/test_write_operation_e2e_smoke.py tests/test_write_operation_scenario_discovery.py -q`。
- 未测风险：生产发布前无法证明真实 systemd/RabbitMQ/PostgreSQL drain；发布后必须重跑 fixed write-operation apply，并继续单独优化 HTTP write step 本身。

## 2026-07-03 - Workbench relation source-object补读快路径

- 变更类型：read model projection hot-path implementation；不改变 HTTP response shape、权限、业务状态机、worker event type、queue schema 或 read model payload schema。
- 覆盖证据：`workbench_relation` 月份 changed rebuild 复用第一次读取的本月源对象；跨月 relation 缺失成员只按显式 row-id 和 relation 类型补读，不恢复第二次全月 bank/OA/invoice 扫描。
- 新增/更新测试：`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_writes_linked_and_unlinked_relation_rows`、`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_indexes_cross_month_relation_members_in_current_scope`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；business core 不新增，因为不改 relation 状态机或金额判断；API contract 不新增，因为响应合同不变；frontend interaction 不新增，因为页面可见行为不变；E2E 不新增，本轮生产固定 write-operation apply 作为发布后闭环证据。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_sql_projection.py -q`；`python3 -m py_compile backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py`。
- 未测风险：本地 fake 不覆盖真实 PostgreSQL planner、RabbitMQ transport 和 worker 并发；生产必须复跑 fixed write-operation scenario。

## 2026-07-03 - Bank batch source-version probe skip fast path

- 变更类型：read model worker hot-path implementation；不改变 HTTP response shape、权限、业务状态机、worker event type 或 queue schema。
- 覆盖证据：bank-flow/no-OA 月份 scope 的 unchanged skip 在读取完整银行交易行、分类行、关系行之前完成 source_versions 比较；`BankTransactionTagReadFacade.source_versions_for_scope_keys(...)` 是 bank-detail 依赖的 source-version-only I/O；`all` 聚合 scope 不走该月级 precheck，避免额外 snapshot/read 放大。
- 新增/更新测试：`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_source_versions_for_scope_keys_uses_scope_summary_without_loading_rows`、`tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_scope_source_versions_use_probe_ports_before_row_loading`、`tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_unchanged_scope_skips_rebuild_and_snapshot_save`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；business core 不新增，因为不改金额/分类规则/状态转换；API contract 不新增，因为 response shape 不变；frontend interaction 不新增，因为页面行为不变；E2E 不新增到本地测试矩阵，生产 write-operation apply 与 read model SLO 作为发布后证据。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests tests/test_bank_flow_rule_batch_application_service.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_read_model_manifest.py -q`。
- 未测风险：本地 fake repository 不证明真实 PostgreSQL worker 并发下的 p95；生产必须复跑 critical 1s read model smoke 和固定 write-operation scenario。

## 2026-06-28 - PSCIP-L4 production closure accounting

- 变更类型：documentation/accounting only；不改变 runtime、API shape、worker event、queue schema、权限、审计或前端行为。
- 覆盖证据：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-final-closure-report-2026-06-28.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md`、`docs/modules/read-models/boundary-io.md`、`docs/architecture/module-boundaries/read-model-contracts.md`。
- 生产证据：scope contract `ok=true`、`violation_count=0`、current uncovered outbox failure count `0`；`/health/ready` ready；critical read model SLO grouped run 14/15 pass under 5000ms target，唯一 Search miss targeted rerun `499.357ms` pass；dirty/outbox/readiness 收敛；没有已知 stale-as-fresh 路径。
- 七类测试决策：
  - Business core unit tests：不适用，本轮不改金额、分类、状态转换或权限判断。
  - Service-layer tests：不新增；前序 shared gates 已覆盖 manifest、gateway、scope contract、operation barrier 和 runtime worker registry。
  - API contract tests：不新增；本轮只同步文档，生产 admin API smoke 证据已记录在 production evidence。
  - Read model/cache/background job tests：适用但不新增；前序 local gates 和生产 SLO/scope contract 是本轮闭环证据。
  - Frontend component and interaction tests：不新增；本轮不改页面行为，已有页面 tests/Browser specs 保持现状。
  - End-to-end business-flow integration tests：不新增；`READMODEL-E2E-006` 仍按审批 ticket 和安全 scenario 推进真实业务写样本，不阻塞 read model 模块化 PSCIP-L4。
  - Existing feature regression tests：适用但不新增；`tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_scope_contract.py`、manifest/worker/gateway tests 继续作为防漂移入口。
- 验证命令：`bash scripts/verify.sh docs`、`git diff --check`。
- 未测风险：Search 曾有一次 production grouped-run 高延迟样本，targeted rerun 已通过；Workbench groups admin smoke 的 `400` 是 probe shape 问题，不是 stale-as-fresh 证据；浏览器组合覆盖不是 100% 枚举覆盖。

## 2026-06-26 - Dependency source-version skip closure

- 变更类型：narrow implementation slice；不改变 HTTP response shape、权限、业务状态机、worker event type 或 queue schema。
- 覆盖证据：`invoice_lifecycle` skip precheck 纳入 top-level Workbench relation source_versions，并通过 scope summary 做 unchanged proof，避免读取完整 lifecycle rows；`no_oa_bank_batch` worker 从 state_store 注入 SQL read repository，先读取 Bankdetail tag 与 Workbench relation metadata source_versions，再对现有 SQL source_versions summary 做 unchanged skip，不加载完整 relation rows/batch payload rows；`bank_detail` read repository port 暴露 tag facade 必需方法，避免生产 SQL runtime 回退 live provider。
- 新增/更新测试：`tests/test_invoice_lifecycle_sql_projection.py::test_invoice_lifecycle_sql_projection_skips_unchanged_scope_without_rebuild`、`tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_unchanged_scope_skips_rebuild_and_snapshot_save`、`tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests::test_bank_detail_read_model_port_excludes_unrelated_read_model_methods`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖，因为本 slice 修正 dependency source_versions 和 worker skip fast-path；API contract、frontend interaction、E2E 不新增，因为 payload shape、前端状态和用户流程不变；business core 不新增，因为不改金额、分类、生命周期状态或权限判断。
- 验证命令：`python -m pytest tests/test_bank_details_sql_runtime.py tests/test_invoice_lifecycle_sql_projection.py tests/test_no_oa_bank_batch_read_model_refresh.py -q`。
- 未测风险：本地测试不连接真实 PostgreSQL/RabbitMQ/Redis/systemd worker；生产发布后必须用 direct SLO、HTTP SLO 和受控写操作 discovery/确认后的 mutating smoke 验证真实数据 freshness closure。

## 2026-06-26 - Scoped incremental projection fast-paths

- 变更类型：narrow implementation slice；不改变 HTTP response shape、权限、业务状态机、worker event type 或 queue schema。
- 覆盖证据：`cost_statistics` 月度 projection 在 fresh SQL view 的 `source_versions` 与当前 workbench active generation source versions 完全一致时返回 `published=true/skipped_rebuild=true/source_versions_unchanged`；cost-only repository CAS 必须精确匹配当前 dirty event version 与 parent JSONB source versions，只推进 `published_source_version`，不扫描 `read_model.workbench_groups`、不重写 payload/rows。CAS race 返回 unpublished 并保持 refreshing。`invoice_lifecycle` 月度 projection 在 pending invoice、input usage、output collection、OA pending payment scope source versions 与当前 lifecycle source versions 完全一致时跳过 row rebuild；`no_oa_bank_batch` source versions 对 bank_detail 依赖过滤 volatile `source_version`，只保留内容签名和稳定版本字段。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_skips_unchanged_month_scope_without_workbench_scan`、`test_cost_statistics_sql_projection_rejects_unchanged_ack_after_dirty_version_race`、`test_repository_acknowledges_unchanged_cost_scope_without_rewriting_rows_or_payload`、`test_repository_rejects_unchanged_cost_ack_on_dirty_version_or_source_race`、`tests/test_invoice_lifecycle_sql_projection.py::test_invoice_lifecycle_sql_projection_skips_unchanged_scope_without_rebuild`、`tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_source_versions_include_bank_detail_source_versions_from_tag_facade`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖，因为本 slice 只改变 projection skip path 和 source_versions contract；API contract、frontend interaction、E2E 不新增，因为 payload shape、前端状态和用户流程不变；business core 不新增，因为不改金额、分类、生命周期状态或权限判断。
- 验证命令：`python -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_invoice_lifecycle_sql_projection.py tests/test_no_oa_bank_batch_read_model_refresh.py -q`；`python -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_cost_statistics_runtime_service.py tests/test_invoice_lifecycle_sql_projection.py tests/test_invoice_lifecycle_read_facade.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_workbench_integration.py tests/test_read_model_manifest.py -q`。
- 未测风险：本地测试不连接真实 PostgreSQL/RabbitMQ/Redis/systemd worker；生产首次发布后会因为新增/修正 source_versions keys 触发一次重建，第二轮及以后才应进入稳定 skip fast-path，需用 direct SLO 和 HTTP SLO 验证。

## 2026-06-24 - T8 module IO contract reconciliation

- 变更类型：documentation/accounting only；不改变 runtime、API shape、worker event、queue schema、权限、审计或前端行为。
- 覆盖证据：`docs/modules/read-models/README.md` 明确 input/output/event/permission/public/internal/legacy/partitioned-scoped contracts；`docs/modules/read-models/state-machine.md` 明确 force refresh、dedupe、operation barrier 和 projection strategy 状态；`.planning/refactors/modular-io-boundaries/analysis/module-contract-read-models.md` 与 T8 handoff 记录 source limitations 和后续验收点。
- 七类测试决策：
  - Business core unit tests：不适用，本轮不改业务规则、金额、状态转换或分类逻辑。
  - Service-layer tests：不新增；现有 `tests/test_read_model_manifest.py`、gateway/barrier/registry tests 是合同防漂移证据，本轮只同步文档。
  - API contract tests：不适用，本轮不改 HTTP contract 或 response shape。
  - Read model/cache/background job tests：适用但不新增；现有 manifest、refresh gateway、operation barrier、runtime worker registry、scope contract tests 覆盖所记录合同。
  - Frontend component and interaction tests：不适用，本轮不改页面、operation overlay 或 API client 行为。
  - End-to-end business-flow integration tests：不适用，本轮不改跨模块业务流；真实 worker/browser evidence 仍由各模块 smoke 负责。
  - Existing feature regression tests：适用但不新增；`tests/test_read_model_manifest.py`、`tests/test_read_model_architecture_guards.py` 和 module-specific SQL runtime tests 继续保护旧行为。
- 验证命令：`bash scripts/verify.sh docs`、`git diff --check`。
- 未测风险：T8 handoff 文件此前不存在，且 `.planning/.../analysis/module-contract-*.md` 此前为空；本轮从 manifest、module docs 和 existing analysis names reconciliation，不连接真实 PostgreSQL、不验证 worker drain/App Status/high-row/browser evidence。

## 2026-06-24 - Read model manifest contract inventory guard

- 变更类型：manifest/documentation contract guard。
- 覆盖证据：`ReadModelManifestEntry` 新增 `partition_key_contract`、`scoped_incremental_target`、`full_rebuild_fallback`、`freshness_proof_contract`；`docs/modules/read-models/README.md` 新增 14 个 App Status read model 的合同清单；`tests/test_read_model_manifest.py::ReadModelManifestTests.test_manifest_entries_record_partition_rebuild_and_freshness_contracts` 防止新增/修改 read model 时漏登记分区、增量目标、全量重建 fallback 和 freshness proof。
- 七类测试决策：read model/cache/background job、existing feature regression 适用并覆盖；service-layer/API/frontend/E2E/business core 不适用，因为本轮不改变运行时代码、HTTP shape、UI 或业务状态机。
- 验证结果：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v` 通过。
- 未测风险：该 guard 只证明合同已记录并与 registry/worker/scope policy 基础 parity 同测；真实 PostgreSQL worker drain、生产 operation-to-fresh latency 和页面浏览器 smoke 仍由各模块/运行时 smoke 覆盖。

## 2026-06-24 - No-OA bank batch read model repository port extraction

- 变更类型：narrow implementation slice。
- 覆盖证据：`NoOaBankBatchReadModelRepositoryPort`、`NoOaBankBatchApplicationService.list_batches_payload(...)`、`PostgresStateStore.no_oa_bank_batch_sql_read_repository`、`READ_MODEL_MANIFEST["no_oa_bank_batch"].repository_owner`、no-OA application/workbench integration tests、read model manifest test 和 no-OA platform boundary guard。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；API contract 通过 route-level stale/missing regression 覆盖但未新增 response shape 测试；business core/frontend/E2E 不适用，因为本轮不改变生命周期、HTTP shape、frontend operation barrier 或用户流程。
- 验证结果：目标 no-OA application/workbench integration、manifest 和 static guard 通过。
- 下一验证重点：freshness/derived lifecycle audit 应复核 refresh gateway/scope policy、operation barrier、dirty/outbox、worker registry、App Status 和 remaining app-owned helper surfaces。

## 2026-06-24 - No-OA bank batch refresh persistence boundary extraction

- 变更类型：narrow implementation slice。
- 覆盖证据：`NoOaBankBatchReadModelPersistencePort`、`NoOaBankBatchReadModelRefreshService.handle_runtime_event(...)`、runtime worker no-OA refresh wiring、no-OA refresh/application/workbench integration tests 和 no-OA platform boundary guard。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；business core/API contract/frontend/E2E 不适用，因为本轮不改变生命周期、HTTP shape、frontend operation barrier 或用户流程。
- 验证结果：目标 no-OA refresh/application/workbench integration 和 no-OA platform guard 通过；完整 `tests.test_platform_runtime_boundary_guards` 有两个无关 OA invoice / ETC repair guard 失败，后续不应误归因给 no-OA persistence slice。
- 下一验证重点：repository port extraction 应覆盖 no-OA list read port guard、manifest owner/contract、application service list payload status regression 和 docs verify。

## 2026-06-24 - No-OA bank batch repository/state-store boundary audit

- 变更类型：analysis/accounting only。
- 覆盖证据：`NoOaBankBatchReadModelRefreshService`、`NoOaBankBatchApplicationService.list_batches_payload(...)`、`PostgresStateStore.save_no_oa_bank_batches(...)`、`PostgresWorkbenchRepository.save_no_oa_bank_batches(...)`、`PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)`、no-OA manifest/scope/worker registration 和 no-OA refresh/application/workbench integration tests。
- 七类测试决策：本轮不新增测试；下一实现 slice 必须覆盖 service-layer、read model/cache/background job 和 existing feature regression categories。若只抽 worker persistence boundary 且不改 HTTP response shape/frontend barrier，则 API contract/frontend/E2E 作为回归可选；若 response shape 或 barrier target 变化则必须补。
- 下一验证重点：`tests.test_no_oa_bank_batch_read_model_refresh`、`tests.test_no_oa_bank_batch_application_service`、`tests.test_no_oa_bank_batch_workbench_integration`、`tests.test_platform_runtime_boundary_guards`、docs verify 和 app check。

## 2026-06-24 - No-OA bank batch next-pilot selection

- 变更类型：analysis/accounting only。
- 覆盖证据：`read_model_manifest.py`、`runtime_worker_registry.py`、`read_model_scope_policy.py`、`NoOaBankBatchReadModelRefreshService`、`SearchPendingReadModelRefreshService`、`BankAccountBalanceReadModelRefreshService` 和对应测试入口用于候选比较。
- 七类测试决策：本轮主要是 selection/accounting，但目标 no-OA refresh tests 暴露并覆盖了一个旧构造参数断裂；下一 no-OA 边界需要覆盖 service-layer、read model/cache/background job 和 existing feature regression categories。如果触及 HTTP response freshness shape 或前端 operation barrier，则 API contract 和 frontend interaction tests 也适用。
- 下一验证重点：`tests.test_no_oa_bank_batch_read_model_refresh`、`tests.test_no_oa_bank_batch_application_service`、`tests.test_no_oa_bank_batch_workbench_integration`、manifest/worker registry、docs verify 和 app check。

2026-06-28 说明：下表部分长文本保留了 2026-06-24 局部试点时的 `production-evidence-deferred` 记录；这些记录已经被 2026-06-28 PSCIP-L4 production closure 覆盖，不再表示当前 read model 模块化未闭环。后续判断当前状态时，以本文顶部 `2026-06-28 - PSCIP-L4 production closure accounting`、`boundary-io.md` 和 final closure report 为准。

| 场景 | 是否适用 | 现有测试 | 缺口 | 优先级 |
| --- | --- | --- | --- | --- |
| happy path | 适用 | `tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_readiness_reporter.py` | 各业务 read model happy path 由对应模块测试覆盖 | P1 |
| empty state | 适用 | `tests/test_read_model_query_gateway.py::test_missing_sql_view_returns_refreshing_empty_payload_and_enqueues_miss` | 页面空态由业务模块覆盖 | P1 |
| invalid input | 适用 | `tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_scope_contract.py` | 主要月/all read model scope 已由 registry 拒绝 `active:*` 等非法 scope；特殊 scope 继续由 cost statistics / pending invoice policy 覆盖 | P1 |
| missing field | 适用 | `tests/test_read_model_freshness.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_architecture_guards.py` | 共享 gateway 已覆盖 invalid SQL/Redis payload contract；具体 API response 缺字段仍由业务 API contract tests 继续覆盖 | P1 |
| wrong type | 适用 | `tests/test_read_model_query_gateway.py` 覆盖非 dict view/missing、invalid payload validator、旧 Redis cache miss；scope policy 覆盖 normalize | 更细 DTO wrong type 属业务 API 层 | P2 |
| duplicate input | 适用 | `tests/test_read_model_refresh_gateway.py` 覆盖 scope dedupe | durable queue conflict 由 `tests/test_runtime_queue.py` 覆盖 | P1 |
| idempotent repeat | 适用 | `tests/test_runtime_queue.py`、`tests/test_read_model_refresh_gateway.py` | 业务写入 idempotency 属业务模块 | P1 |
| permission denied | 不直接适用 | `tests/test_platform_runtime_boundary_guards.py` 防 service import HTTP auth | 具体 403 shape 由业务 API 测试覆盖 | 不适用 |
| stale version / conflict | 适用 | `tests/test_read_model_freshness.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_architecture_guards.py` | stale write precondition 属业务模块 | P1 |
| `read_model_status=fresh` | 适用 | `tests/test_read_model_query_gateway.py`、`tests/test_read_model_readiness_reporter.py`、`tests/test_read_model_architecture_guards.py` | 业务 API fresh payload shape 由业务模块覆盖；新增直接标记 fresh 的代码位置必须先进入静态 guard 白名单并写明理由 | P1 |
| `read_model_status=refreshing` | 适用 | `tests/test_read_model_query_gateway.py`、`tests/test_read_model_readiness_reporter.py` | 页面 refreshing 行为由业务前端测试覆盖；同 scope 已有 active refresh 时 `refresh_enqueued` 必须为 false，避免把合并刷新误报为新入队 | P1 |
| `read_model_status=stale` | 适用 | `tests/test_read_model_freshness.py` 内部 freshness；public gateway 映射为 refreshing | App Status stale 由 app-health 模块继续审计 | P1 |
| `read_model_status=missing` | 适用 | `tests/test_read_model_query_gateway.py` | App Status missing 由 app-health 模块继续审计 | P1 |
| `read_model_status=failed/unavailable` | 适用 | `tests/test_read_model_readiness_reporter.py`、App Status 测试、`tests/test_read_model_scope_contract.py` 覆盖 outbox failure 是否 current-effective | 各页面 failed/unavailable 展示由业务模块覆盖 | P1 |
| background job queued/running/succeeded/failed | 适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_readiness_reporter.py` | 后台任务 UI 属 app-health/background-jobs 模块 | P1 |
| cache hit/cache miss | 适用 | `tests/test_read_model_query_gateway.py` | Redis 真连接不在本地单测覆盖；本地覆盖缺 schema proof 与 payload contract invalid 的 cache miss | P2 |
| authenticated HTTP SLO fresh gate | 适用 | `tests/test_http_slo_probe.py` | 真实生产登录态 HTTP SLO 需发布后运行；本地覆盖 probe 语义和默认参数 | P1 |
| operation freshness barrier | 适用 | `tests/test_operation_freshness_barrier.py`、`tests/test_app_health_api.py`、`web/src/test/OperationBarrierApi.test.ts` | 真实生产写操作后的 barrier latency 需发布后用登录态 scenario 证明 | P1 |
| external dependency timeout/failure | 不直接适用 | runtime/app-health 模块覆盖依赖状态 | OA/Redis/RabbitMQ/PostgreSQL 真失败需 staging | P2 |
| frontend loading | 间接适用 | 业务页面测试 | 本模块无 UI | 不适用 |
| frontend empty | 间接适用 | 业务页面测试 | 本模块无 UI | 不适用 |
| frontend error | 间接适用 | 业务页面测试 | 本模块无 UI | 不适用 |
| drawer/dialog open/close | 不适用 | N/A | 本模块无 UI | 不适用 |
| filters/sorting/pagination/search | 间接适用 | 业务模块测试 | 本模块只保护 freshness 边界 | P2 |
| export shape | 间接适用 | 业务 export tests | 本模块只保护 fresh gate 语义 | P2 |
| cross-page refresh | 适用 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | 前端事件和业务 page refresh 在 domain-events/business 模块继续审计 | P1 |
| write operation action attribution | 适用 | `tests/test_workbench_uow_contract.py`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_workbench_dirty_queue_wiring.py`、`tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_scenario_discovery.py` | 本地覆盖 profile、action metadata、missing scope、P95 target 和 P99 长尾 target；生产仍需真实登录态和人工批准 scenario 才能执行 mutating gate | P1 |
| old feature regression | 适用 | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_scope_contract.py` | 旧业务 shape 由各模块继续覆盖 | P1 |
| historical bug regression | 适用 | `tests/test_read_model_scope_contract.py`、`tests/test_read_model_refresh_gateway.py` | 生产真实库 dry-run 仍需发布前执行 | P2 |
| production data / migration risk | 适用 | `scripts/check-read-model-scope-contracts.py`、`tests/test_read_model_scope_contract.py`、`tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_app_status_read_model_storage_contracts_are_declared` 覆盖 cost statistics scope contract repair、orphaned import fact dirty scope repair、invalid read model scope repair、repair manifest、audit、rollback、幂等 apply 和 App Status read model storage contract | 当前 runtime apply 必须先 dry-run 并保留 manifest/audit；invalid scope repair 只删除 policy 明确判定 invalid 的 dirty/outbox/readiness 行；新增 read model 必须同步 migration storage contract | P1 documented-risk |
| performance-sensitive query path | 适用 | `tests/test_api_performance_metrics.py`、SQL runtime tests、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_bounds_all_scope_groups_page_query`、`tests/test_postgres_repositories_boundaries.py::test_invoice_lifecycle_rows_are_saved_in_batch_and_scope_is_updated` | Workbench all-scope groups 首屏读取必须保持 page API + `limit/offset` 护栏；invoice lifecycle rows 保存必须保持 batch insert/upsert，避免 critical worker refresh 在真实生产库里被逐行 upsert 放大。 | P2 |
| import fan-out bounded refresh | 适用 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes`、`tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_import_fact_changed_handler_completes_matching_dirty_scope`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_invoice_relation_scope_helpers_split_input_and_output_file_months`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_tax_offset_scope_helpers_ignore_bank_transaction_files` | 发票导入有影响月份时，Workbench 和 pending invoice 必须投递月级 scope；进项/销项方向页按本次文件方向命中刷新；tax offset 只接受进项/销项发票文件；完整 snapshot 保存不能生成 read model refresh 旁路；银行明细必须投递真实 `bank_detail.read_model.refresh`，兼容 `import.fact.changed` 只可作为 legacy bridge；银行导入必须同步投递 `bank_account_balance:all`。 | P1 |
| manifest / registry parity | 适用 | `tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_app_status_read_model_registry_matches_worker_and_rabbitmq_contracts` | 14 个 App Status read model 必须同时存在于 manifest、App Status registry、worker registry、RabbitMQ dispatch 和 scope policy registry；manifest 还必须登记 query contract、projection strategy、`all` scope 语义、force refresh contract、operation barrier contract、repository port contract、owner 和 test owner。 | P1 |
| Workbench active generation special case | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_workbench_manifest_preserves_active_generation_exception`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_query_facade.py` | Workbench 必须保留 active generation 原子发布和等价 freshness contract；不能被误改成普通 gateway/rebuild read model。 | P1 |
| Bank detail / account balance boundary | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_bank_detail_and_balance_manifest_keep_separate_contracts`、`tests/test_bank_details_sql_runtime.py`、`tests/test_bank_auto_tag_rules_api.py`、`tests/test_bank_account_balance_read_model.py` | 银行明细和账户余额保持独立 scope/event/repository owner。普通 category/rule 写入零 barrier 且由当前页面 GET 比较精确 month signature；只有显式 reapply 返回并等待 bounded bank-detail month targets。 | P1 |
| Pending invoice / OA pending payment boundary | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_pending_invoice_and_oa_payment_manifest_preserve_page_scope_contracts`、`tests/test_search_pending_sql_runtime.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | 待找发票必须拒绝裸 `all` 并保留 page-first-screen force refresh；OA 待付款 `all` 仍是 fan-out command；两者 repository port 不得互相污染。 | P1 |
| Invoice lifecycle / input usage / output collection boundary | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_invoice_lifecycle_and_usage_manifest_preserve_scoped_contracts`、`tests/test_invoice_lifecycle_read_model_refresh.py`、`tests/test_invoice_lifecycle_read_facade.py`、`tests/test_invoice_lifecycle_read_facade.py::InvoiceLifecycleReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods`、`tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests::test_invoice_lifecycle_target_uses_exact_month_scope_for_operation_barrier`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_invoice_usage_collection_sql_runtime.py::InputInvoiceUsageReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods`、`tests/test_invoice_usage_collection_sql_runtime.py::OutputInvoiceCollectionReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods`、`tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_input_invoice_usage_app_level_projection_helpers_do_not_return`、`tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_output_invoice_collection_app_level_projection_helpers_do_not_return`、`tests/test_input_invoice_usage_api.py`、`tests/test_input_invoice_usage_api.py::InputInvoiceUsageApiTests::test_relation_details_require_sql_repository_in_production_without_live_rebuild`、`tests/test_output_invoice_collection_api.py::OutputInvoiceCollectionApiTests::test_relation_details_require_sql_repository_in_production_without_live_rebuild`、`tests/test_output_invoice_collection_api.py::OutputInvoiceCollectionApiTests::test_relation_details_use_fresh_sql_read_model_row_without_live_rebuild`、`.planning/refactors/modular-io-boundaries/analysis/read-model-input-invoice-usage-local-implementation-closure-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-repository-port-extraction.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-refresh-freshness-operation-barrier-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-relation-detail-production-repository-fail-closed.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-output-invoice-collection-local-implementation-closure-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-output-invoice-collection.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-repository-port-extraction.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-refresh-freshness-operation-barrier-audit.md`、`tests/test_output_invoice_collection_api.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx` | 发票生命周期、进项使用和销项收款必须保持 scoped incremental、fan-out `all`、独立 query owner/permission owner/repository port；input/output 可共享 `invoice-usage-collection` worker，但不能混用 lifecycle 或彼此的 repository ports。`InvoiceLifecycleReadModelRepositoryPort` 已让 lifecycle facade lookup 和 SQL projection save/mark 走窄 port，且不暴露 input/output/OA/pending/search 方法；`invoice_lifecycle:all` 仍是 fan-out command，facade 没有 queryable all read path，refresh service 扩展 all 为 month shards，并有 exact-month operation barrier regression。当前没有新增 speculative state-store property。`InputInvoiceUsageReadModelRepositoryPort` 额外防止 output/OA/pending read model 方法污染 input usage 端口；`OutputInvoiceCollectionReadModelRepositoryPort` 额外防止 input/OA/pending/workbench relation source-version 方法污染 output 端口，并让 projection save/mark/prune/detail row lookup 走窄 port；input usage 和 output collection app-level rebuild/list/mark projection helper 均已删除且不得回归；output collection mutation responses 返回 concrete freshness targets，前端写后等待具体月份 operation barrier；生产 relation detail 缺 SQL repository 时 input usage 和 output collection 都必须 refreshing/enqueue，不能 live rebuild；input usage 和 output collection local implementation support 均已 accounted，但真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；invoice lifecycle app-owned derived lifecycle executor 已抽取到显式 executor；下一步是 invoice lifecycle local implementation closure audit。 | P1 |
| Cost / tax / turnover summary boundary | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_derived_lifecycle_executor.py`、`tests/test_tax_offset_sql_runtime.py`、`tests/test_tax_offset_worker_rebuild_executor.py`、`tests/test_tax_offset_derived_lifecycle_executor.py`、`tests/test_tax_offset_cache_warmup_executor.py`、`tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_object_identity_policy.py`、`tests/test_tax_offset_service.py`、`tests/test_tax_offset_api.py`、`tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh.py`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-repository-port-extraction.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-refresh-freshness-operation-barrier-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-local-implementation-closure-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-worker-rebuild-executor-port-extraction.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-derived-lifecycle-executor-boundary-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-post-derived-local-implementation-closure-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-cache-warmup-executor-port-extraction.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-final-local-implementation-closure-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-full-state-read-model-snapshot-quarantine.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-post-full-state-local-implementation-closure-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-tax-offset.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-repository-port-extraction.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-refresh-freshness-operation-barrier-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-derived-lifecycle-executor-port-extraction.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-post-derived-local-implementation-closure-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-full-state-read-model-snapshot-quarantine.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-post-full-state-local-implementation-closure-audit.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-cost-statistics.md` | 成本统计必须保持 queryable parent aggregate；税金抵扣和外部往来台账必须保持 fan-out/incremental 语义；三者 repository port、query owner、permission owner 和 primary worker 不得互相污染。`tax_offset` narrow repository port guard 已新增，证明只暴露 manifest-listed load/get/save 方法；freshness/barrier audit 已确认 SQL fresh gate、force refresh、`all` fan-out/month proof、operation barrier 和 retained compat wrapper 分类，且补齐 OA 附件发票 `invoice_type` fallback 回归。worker rebuild executor extraction 已把 `Application.rebuild_tax_offset_read_model_scope(...)` 中的 rebuild/persist/fresh cache publish 行为迁到 `TaxOffsetWorkerRebuildExecutor`；derived lifecycle executor extraction 已把 read model invalidation/month cache clearing 行为迁到 `TaxOffsetDerivedLifecycleExecutor`；cache warmup executor extraction 已把 optional warmup env gate/job scheduling/run-job progress/upsert/persist 行为迁到 `TaxOffsetCacheWarmupExecutor`；full-state snapshot quarantine 已移除 broad `Application._persist_state(...)` 对 `tax_offset_read_models` 的旧写入；post-full-state local closure audit 已确认本地支持 accounted，并把真实 PostgreSQL/worker/App Status/high-row/browser evidence 记录为 deferred，未声明模块全局 closed。after-tax-offset selection 已选择 `cost_statistics` 为下一非 Go read model 试点；cost statistics repository port extraction 已新增 port guard 并让 SQL read/projection save path 使用窄 port；cost statistics freshness/barrier audit 已确认 SQL fresh gate、scope policy、parent aggregate、primary/compat worker 与 App Status registry 的本地证据；cost statistics derived lifecycle executor extraction 已新增 `CostStatisticsDerivedLifecycleExecutor` 并移除 app-owned helper，锁定 invalidation、no-warmup fallback metadata 和 job accounting；full-state snapshot quarantine 已移除 broad `Application._persist_state(...)` 对 `cost_statistics_read_models` 的旧写入，并扩展 guard 防止 cost/tax read model full-state snapshot 回归；post-full-state local closure audit 已确认本地支持 accounted，并把真实 PostgreSQL/worker/App Status/high-row/browser evidence 记录为 deferred，未声明模块全局 closed。after-cost-statistics selection 已选择 `turnover_ledger`；下一边界是 `read-models:turnover-ledger-repository-port-extraction`。 | P1 |
| Search / no-OA bank batch read-side boundary | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_search_and_no_oa_bank_batch_manifest_preserve_read_side_contracts`、`tests/test_search_pending_sql_runtime.py`、`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py` | Search 必须保持 partitioned scoped index 和 search primary worker；no-OA 必须保持 scoped incremental read model 与 `NoOaBankBatchApplicationService` query owner；两者 `all` 均为 fan-out command，repository port、permission owner 和 worker owner 不得互相污染。 | P1 |
| Legacy refresh producer contamination guard | 适用 | `tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_direct_read_model_refresh_enqueue_calls_are_classified` | 非事务 read model refresh 必须通过 `ReadModelRefreshGateway` / scope policy registry；仍存在的 direct `enqueue_read_model_refresh(...)` wrapper 必须有 owner/reason 分类，不能新增未分类旧路径污染 dirty/outbox。 | P1 |

2026-06-24 补充：`invoice_lifecycle` derived lifecycle executor 已抽到 `InvoiceLifecycleDerivedLifecycleExecutor`；`tests/test_invoice_lifecycle_derived_lifecycle_executor.py` 覆盖 scope/reason/metadata/result shape，`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_invoice_lifecycle_derived_lifecycle_uses_explicit_executor_boundary` 防止旧 app-owned helper 回归。

2026-06-24 补充：`read-models:invoice-lifecycle-local-implementation-closure-audit` 已将本地支持记录为 accounted / `production-evidence-deferred`：repository port、facade、refresh service、worker/manifest/App Status、operation barrier 和 derived lifecycle executor 均有本地证据；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍未执行，不能声明 `invoice_lifecycle` 全局 closed。下一步是选择下一个非 Go modular IO/read model 试点。

## 七类测试适用性

| 类别 | 是否适用 | 现有测试入口 | 必须覆盖 | 当前缺口 | 优先级 | 未测风险 |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_read_model_freshness.py`、`tests/test_read_model_refresh_gateway.py` | source version normalize、fresh/stale/missing/schema/source mismatch、expected contract fail-fast、scope normalize/validate/dedupe | 无 P0 缺口 | P1 | 新增 read model 特殊 scope policy 时需补业务规则测试 |
| 2. Service-layer tests | 适用 | `tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_scope_contract.py`、`tests/test_read_model_readiness_reporter.py`、`tests/test_read_model_architecture_guards.py` | gateway 委托 queue、cache hit/miss、missing/stale 入队、scope contract 检查/清理、repair manifest、audit、rollback、readiness 成功/失败记录、query gateway call site 必须声明 freshness contract；direct fresh 与 direct source mismatch 路径必须被静态 guard 分类并证明 expected contract 非空 | 无 P0 缺口 | P1 | 真实 repository/DB 清理需 dry-run |
| 3. API contract tests | 按需适用 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_generic_cost_statistics_enqueue_expands_month_scopes` 和各业务 API tests | API 必须透出 `read_model_status`、`refresh_enqueued`、`stale_reasons` 等关键字段 | 本模块不拥有单一 HTTP contract；需各模块继续补齐 | P1 | 如果业务 route 绕过 gateway，可能只在模块 API tests 暴露 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_read_model_*`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_runtime_queue.py`、`tests/test_operation_freshness_barrier.py` | dirty scope/outbox durable truth、worker lifecycle 使用 gateway、Redis 只缓存 fresh 且满足 payload contract 的 payload、readiness scope 状态、current uncovered outbox failure 不被清理、barrier 只读 runtime facts | 无 P0 缺口 | P1 | Redis/RabbitMQ 真连接属于 runtime/staging 风险 |
| 5. Frontend component and interaction tests | 间接适用 | `web/src/test/*Page.test.tsx`、`web/src/test/domainEvents.test.ts`、页面级 Playwright specs；显式 job另含 `OperationBarrierApi.test.ts` | 页面必须正确消费 fresh/refreshing/stale/empty/error；普通写成功后零 barrier并重跑当前页 normal GET，hidden→visible 与另一可见窗口独立 GET；显式 import/reapply/job 才可等待 exact barrier | 真实浏览器多窗口与逐页面访问需生产/Playwright smoke | P1 | 页面可能把 refreshing 空 rows 当真实空结果或把轻量事件当 fresh 证明 |
| 6. End-to-end business-flow integration tests | 按需适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、各业务 integration tests | 普通写 -> 零 queue -> 页面访问 -> exact dirty scope -> worker/readiness -> 页面 fresh；显式 job 保留声明 target 链 | 全量生产逐页面路径在 Phase 27-07 覆盖 | P2 | 生产 worker drain 和历史数据需 smoke |
| 7. Existing feature regression tests | 适用 | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_scope_contract.py` | runtime 边界不被绕过；service 不 import HTTP/auth；producer 不绕过 gateway；旧非法 scope 可检测/清理 | 无 P0 缺口 | P1 | 新增 producer 时必须同步边界守卫 |

## 2026-06-24 - turnover ledger repository port test note

`read-models:turnover-ledger-repository-port-extraction` 已完成。测试覆盖如下：

- Service-layer tests：turnover repository port guard 证明 `TurnoverLedgerReadModelRepositoryPort` 只暴露 `list_turnover_ledger_view`、`save_turnover_ledger_rows`；旧 direct clear port 已于 2026-07-20 删除。
- Read model/cache/background job tests：已运行 `tests/test_turnover_ledger_query_service.py` 和 `tests/test_turnover_ledger_read_model_refresh.py`，确保 fresh/stale/missing、projection save 和 worker complete dirty scope 行为不变。
- Existing feature regression tests：保持 manifest/architecture guard 不允许 turnover port 暴露 cost/tax/search/no-OA/bank detail 等无关 read model 方法。

Business core、API contract、frontend interaction 和 E2E tests 在 repository-port 首切中未新增，因为本 slice 不改变 grouped payload、manual closure、API shape、operation barrier、权限或前端行为。

下一 slice 是 `read-models:turnover-ledger-refresh-freshness-operation-barrier-audit`，必须审计 fresh gate、force refresh、all fan-out/query proof、Workbench relation source-version proof、operation barrier targets、legacy read contamination 和 app-owned helper 分类。

## 2026-06-24 - no-OA bank batch freshness/derived lifecycle audit note

`read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit` 已完成为 analysis/accounting slice。结论：

- 已有测试/代码证据覆盖 no-OA scope policy、gateway enqueue、manifest owner、runtime worker registration、App Status target、worker stale source-version skip、dirty scope complete、missing/stale/fresh list status 和 frontend operation barrier 目标。
- 本轮未新增测试，因为没有改变运行时代码、HTTP contract、业务状态、worker event、queue schema、Redis/cache、权限、审计或前端行为。
- 下一 slice `read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction` 必须新增 executor service-layer tests 和 platform/static guard，证明 no-OA derived lifecycle target scope selection、reason/metadata forwarding 和 enqueued-job accounting 已移出 `Application`。
- `read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine` 是之后的独立测试边界，必须覆盖 broad state-store fallback 被隔离或删除。

## 2026-06-24 - no-OA bank batch derived lifecycle executor test note

`read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction` 已完成。测试覆盖如下：

- Service-layer tests：新增 no-OA derived lifecycle executor tests，覆盖 month/all target semantics、reason default、metadata forwarding 和 response accounting。
- Read model/cache/background job tests：保持 no-OA refresh job type、scope target 和 enqueue result shape；现有 manifest/refresh gateway/worker tests 继续覆盖 registry、scope policy 和 dirty scope completion。
- Existing feature regression tests：新增 platform boundary guard，防止 no-OA derived lifecycle behavior 回到 `Application`。
- Business core、API contract、frontend interaction 和 E2E tests 未新增，因为本 slice 不改变业务状态机、HTTP contract、UI operation barrier 或用户流程。

## 2026-06-24 - no-OA bank batch mutation persistence fallback quarantine test note

`read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine` 已完成。测试覆盖如下：

- Service-layer tests：新增 no-OA application service fail-fast test，证明 service 层缺少 explicit mutation boundary 时不会调用 broad state-store persistence。
- Read model/cache/background job tests：新增 local state-store boundary test，证明 `ApplicationStateStore.save_no_oa_bank_batch_mutation(...)` 是本地 no-OA mutation snapshot persistence 的统一入口。
- Existing feature regression tests：新增 platform boundary guard，防止 `persist_mutation(...)` 重新出现 broad pair/no-OA/workbench snapshot writes。
- Business core、API contract、frontend interaction 和 E2E tests 未新增，因为本 slice 不改变业务状态机、HTTP contract、UI operation barrier 或用户流程。

## 2026-06-24 - no-OA bank batch full-state snapshot quarantine test note

`read-models:no-oa-bank-batch-full-state-snapshot-quarantine` 已完成。测试覆盖如下：

- Read model/cache/background job tests：新增 `ReadModelArchitectureGuardTests.test_no_oa_bank_batches_are_not_written_by_broad_full_state_persist`，证明 broad `_persist_state(...)` 不再写 `no_oa_bank_batches` 或读取 `_no_oa_bank_batch_service.snapshot()`。
- Existing feature regression tests：同一 guard 证明 `NoOaBankBatchReadModelPersistencePort`、local `save_no_oa_bank_batch_mutation(...)` 和 PostgreSQL `save_no_oa_bank_batch_mutation(...)` 仍存在，防止 explicit persistence boundaries 被误删。
- Business core、API contract、frontend interaction 和 E2E tests 未新增，因为本 slice 不改变业务状态机、HTTP contract、UI operation barrier 或用户流程。

## 2026-06-24 - no-OA bank batch post-full-state local closure audit test note

`read-models:no-oa-bank-batch-post-full-state-local-implementation-closure-audit` 已完成。测试覆盖如下：

- Service-layer tests：复跑 no-OA application service tests，证明 no-OA source-version/stale-reason、list payload、mutation persistence 和 relation command behavior 仍由服务层/ports 管理。
- Read model/cache/background job tests：复跑 no-OA refresh、manifest、refresh gateway 和 full-state architecture guard。
- Existing feature regression tests：新增 platform guard，防止 `_no_oa_bank_batch_source_versions(...)` 和 `_no_oa_bank_batch_stale_reasons(...)` 回到 `Application`。
- Business core、API contract、frontend interaction 和 E2E tests 未新增，因为本 audit 不改变业务状态机、HTTP contract、UI operation barrier 或用户流程。

## 2026-06-24 - turnover ledger freshness/barrier audit note

`read-models:turnover-ledger-refresh-freshness-operation-barrier-audit` 已完成为 analysis-only slice。结论：

- 已有证据：SQL fresh gate、month/all scope policy、manifest/App Status/worker registry、Workbench relation source-version proof 和 operation barrier blocking。
- 2026-07-05 状态：旧 app-owned clear helper、producer `clear_best_effort()`、read repository provider 和 relation mutation legacy invalidation adapter 已删除；`tests/test_turnover_ledger_read_model_refresh_producer.py` 与 `tests/test_platform_runtime_boundary_guards.py` 保护 refresh producer 只通过 gateway enqueue，不暴露 direct clear I/O。

## 2026-06-24 - turnover ledger local implementation closure audit note

`read-models:turnover-ledger-local-implementation-closure-audit` 已完成为 analysis/accounting slice。结论：

- 本地支持 accounted：query service、repository port、SQL projection builder、refresh producer、worker refresh service、transactional write UoW/dirty outbox writer、manifest/App Status/worker registry 和 frontend operation barrier usage 均有现有代码/测试证据。
- compat-only：turnover legacy fallback facades、`TurnoverLedgerLocalDirtyOutboxWriter` 和 `BankDetailsApplicationService` 的内部 turnover enqueue fallback；正常 server factory 注入 `TurnoverLedgerReadModelRefreshProducer.enqueue`。
- 未新增测试：本轮不改运行时代码，复用 producer/query/refresh/API、manifest、runtime worker registry、operation barrier 和 platform boundary guard 作为证据。
- 剩余风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence deferred；该状态不是 module closed。

后续已完成 no-OA 与 Search 试点推进；Search local support 现已 accounted 并转为 `production-evidence-deferred`。下一 slice 是 `read-models:next-pilot-selection-after-search`，需要从当前证据确认 `bank_account_balance` 是否为下一个非 Go read model pilot。

## 历史 bug 回归库

| 日期 | Bug | 根因 | 回归测试 | 验证命令 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-06-22 | App Status 概览中 `Read model 2 刷新中 / Queue 1 pending / 5 processing`，但顶部仍显示 `Workbench read model generation consistency failed.` 和 `阻断`；同时业务页面 API miss 在同 scope 已有 active refresh 时仍返回 `refresh_enqueued=true`，让页面/探针误以为每次加载都新触发刷新。 | App Health 的 Workbench generation health 聚合只要看到旧 `consistency_status=failed` 就写入 unavailable dependency，未优先尊重当前 `read_model_status=refreshing`；`ReadModelQueryGateway._enqueue_refresh()` 使用 `enqueue_many(...)` 的 normalized scope 返回值，不能区分“实际入队”和“被 active refresh 合并”。 | `tests/test_app_health_api.py::AppHealthApiTests::test_app_health_keeps_workbench_consistency_failure_busy_during_active_repair`、`tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_missing_sql_view_does_not_report_new_enqueue_when_scope_is_already_active` | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_health_api tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_app_status_overview_service -v` | 自动化覆盖 active repair 下 App Health 保持 busy/rebuilding、不写 blocked/unavailable dependency，以及 active scope coalescing 时 `refresh_enqueued=false`；真实生产仍需发布后用 App Status 和 HTTP SLO smoke 观察 queue/readiness drain |
| 2026-06-22 | 生产 schema/worker/RabbitMQ/Redis 与本地测试覆盖存在“各测各的”风险：新增 read model 可以只进入某一个 registry，却漏掉 worker、RabbitMQ dispatch、critical SLO smoke、migration storage contract 或 Redis/deploy env 模板。 | App Status read model registry、runtime worker registry、SLO smoke、migration SQL 和 deploy env 模板之间缺少交叉断言；`bank_account_balance`、`invoice_lifecycle` 等生产 read model 表已存在但未进入通用 migration 表基线。 | `tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_app_status_read_model_registry_matches_worker_and_rabbitmq_contracts`、`tests/test_read_model_slo_smoke.py::ReadModelSloSmokeTests::test_critical_only_plans_every_critical_app_status_read_model`、`tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_app_status_read_model_storage_contracts_are_declared`、`tests/test_deploy_runtime_examples.py::DeployRuntimeExampleTests::test_shared_rabbitmq_worker_env_does_not_switch_all_workers_to_rabbitmq`、`tests/test_runtime_redis.py::RuntimeRedisTests::test_production_env_examples_match_runtime_redis_settings_contract` | `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_registry tests.test_read_model_slo_smoke tests.test_postgres_migrations tests.test_deploy_runtime_examples tests.test_runtime_redis -v` | 自动化覆盖 registry/worker/RabbitMQ/SLO/migration/Redis env 的本地 parity；真实 PostgreSQL/RabbitMQ/Redis/systemd drain 仍需 `infra-smoke` 或生产/staging gate |
| 2026-06-22 | Workbench `all` active generation 已发布，但 `/api/workbench?month=all` 主视图和分页/过滤视图仍从 month snapshots 临时拼接 payload/summary，绕过 all-scope 聚合器的唯一 owner、active relation occupancy 和 source_versions proof；分页视图还会返回空 `source_versions` 导致 stale/requeue 循环。 | `PostgresReadModelRepository._load_all_workbench_view(...)` 和 `_load_all_workbench_rows_page_view(...)` 把 `all` query scope 当作页面读取时的临时 aggregate，而不是消费 `workbench:all` active generation；无 active generation 的 legacy fallback 与当前生产事实源没有分层。 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_reads_all_scope_view_from_active_generation_snapshot`、`test_repository_reads_all_scope_filtered_page_from_active_all_summary`、`test_repository_synthesizes_all_workbench_view_from_month_snapshots`、`test_repository_reads_all_scope_filtered_page_without_full_snapshot_payloads` | `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v` | 自动化覆盖 active all snapshot/summary 优先、bounded rows page 读取和 legacy fallback；真实生产旧 generation 仍需发布后 worker drain/authenticated smoke |
| 2026-06-22 | Workbench group detail 在 group page/row detail 已有 freshness gate 的情况下，仍从 SQL active generation 直接返回 `read_model_status=fresh`，导致 source version stale 或 dirty scope refreshing 时前端可展开旧 group 详情。 | `PostgresReadModelRepository.get_workbench_group_detail(...)` 未带出 active generation `source_versions`/`read_model_status`，`WorkbenchQueryFacade.group_detail(...)` 未调用等价 stale gate；direct fresh allowlist 只说明来源是 active generation，没有证明 fresh gate。 | `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_group_detail_stale_source_versions_do_not_return_stale_group`、`test_group_detail_refreshing_status_does_not_return_stale_group`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_group_detail_includes_active_generation_freshness_contract`、`tests/test_read_model_architecture_guards.py` | `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_read_model_architecture_guards -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_group_detail_reads_only_active_generation tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_group_detail_includes_active_generation_freshness_contract tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_group_detail_api_returns_full_group -v` | 自动化覆盖 group detail stale/source mismatch 不返回旧 group、不标 fresh、补投 refresh；真实生产旧 generation 仍需发布后 worker drain/authenticated smoke |
| 2026-06-18 | Workbench `all` aggregate-only refresh 抢在 parent month shard 重建前运行，把 relation 写入后的暂态 parent/member mismatch 写成 failed all generation；旧 failed 被重新入队后仍继续显示为当前失败 | `parent_scope_keys` 只被作为 payload 元数据传递，handler 未检查 parent `workbench` dirty scope 是否仍 pending/processing/failed；refresh-status 和 App Health 对同一 scope failed + processing 未做 current-effective 合并 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_refreshing`、`test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_failed`、`test_workbench_refresh_status_api_treats_requeued_failed_scope_as_refreshing`、`tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_treats_requeued_cost_statistics_deadlock_as_refreshing`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_read_model_refresh_is_fresh_checks_no_active_or_failed_dirty_scope` | `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime tests.test_runtime_worker tests.test_runtime_queue tests.test_app_status_overview_service -v` | 自动化覆盖 parent active/failed 时不调用 aggregate builder、不完成 dirty scope，并走 `workbench_read_model_not_fresh` defer；同 scope requeued failure 展示 refreshing；真实生产 case 需发布后回放或审计 |
| 2026-06-18 | App Health 显示 read model fresh/已同步，但业务页面因 Redis 或 SQL 中的旧 payload 缺少当前 API 必需字段而报加载失败 | freshness gate 只校验 schema/source/readiness，未校验业务 payload shape；旧缓存命中会绕过 SQL view 和刷新入队 | `tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_invalid_fresh_cache_payload_contract_misses_and_uses_sql_view`、`test_invalid_sql_payload_contract_enqueues_refresh_without_populating_cache`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_api_rejects_malformed_fresh_sql_payload_and_requeues` | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_cost_statistics_sql_runtime -v` | 自动化覆盖 invalid Redis cache 不返回 fresh、invalid SQL payload 返回 refreshing 并入队 refresh；真实 Redis/worker drain 需 staging/production smoke |
| 2026-06-17 | 页面 read model 查询漏传 expected source/schema contract，或 legacy direct fresh/direct mismatch 路径未纳入统一边界时，旧 projection 或缺 schema 的 Redis/SQL view 仍可能被当 fresh | `ReadModelQueryGateway` 允许空 expected contract；schema mismatch 只在 expected/actual 都存在时触发；部分自管 read model service 默认空 `source_versions_provider`；legacy route/service 仍有直接写 `read_model_status=fresh` 或直接调用 `source_version_mismatch_reasons` 的等价 freshness gate | `tests/test_read_model_freshness.py::ReadModelFreshnessTests::test_missing_schema_is_not_fresh_when_expected_schema_is_set`、`tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_load_requires_expected_freshness_contract`、`test_cache_missing_expected_schema_misses_and_uses_sql_view`、`test_missing_sql_view_schema_enqueues_refresh_without_populating_cache`、`tests/test_read_model_architecture_guards.py`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_repository_reads_cost_statistics_view_and_dirty_status_from_sql` | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_query_gateway tests.test_read_model_architecture_guards -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_tax_offset_sql_runtime -v` | 自动化覆盖共享 query gate、direct fresh 白名单、direct source mismatch expected-contract guard 和成本统计真实 repository metadata；生产仍需发布后重建旧缺 schema/source 的 projection |
| 2026-06-17 | 下游 read model 在 fresh `workbench_relation` scope 中按 row ids 查询时，如果所有请求 row 都没有 relation row，facade 会把 repository `None` 误判成 `missing` 并反复补投 refresh，生产 drain/requeue 卡在 dependency-not-fresh defer | repository 只能从命中的 rows 推导 scope；rows 全空时没有使用调用方已有的 scope hint 去查 readiness | `tests/test_workbench_relation_read_facade.py::WorkbenchRelationReadFacadeTests::test_repository_treats_empty_rows_in_fresh_hinted_scope_as_fresh_empty_context`、`test_facade_passes_scope_hint_for_empty_relation_context` | `PYTHONPATH=backend/src pytest -q tests/test_workbench_relation_read_facade.py`；生产 `read_model_slo_smoke --apply --target-ms 10000`；生产 queue pending/processing/failed/dead-letter check | 自动化覆盖 fresh hinted scope 的 empty context；生产已验证 15 个 App Status read model scope 重新入队并全部 `done/fresh`，且 fresh scope 下 missing probe 返回 `fresh + rows=[] + refresh_enqueued=false` |
| 2026-06-12 | App Status 不能把已覆盖历史 failure 与当前未覆盖 failure 混为同一类，也不能删除真实 current blocker | 旧 outbox failure 可能已有 later done/fresh readiness 覆盖；另一些失败仍是当前真实阻塞 | `tests/test_read_model_scope_contract.py::test_check_reports_repair_manifest_categories_and_outbox_current_state`、`test_apply_records_audit_with_manifest_cleanup_and_rollback_without_deleting_current_failures`、`test_apply_is_idempotent_after_rows_are_deleted` | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v` | 自动化已覆盖服务层语义；生产真实库 dry-run 仍需执行 |
| 2026-06-13 | HTTP SLO 只看 status/latency，导致快速返回 refreshing 或 refresh_enqueued 被误判为通过 | probe 未把 freshness 纳入 pass/fail；普通业务 `status` 字段还可能被误判为 read model status | `tests/test_http_slo_probe.py::HttpSloProbeTests::test_non_fresh_read_model_or_refresh_enqueue_fails_probe`、`test_plain_status_field_does_not_count_as_read_model_status` | `PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe -v` | 自动化已覆盖 probe 语义；生产真实 HTTP SLO 需发布后验证 |
| 2026-06-10 | legacy/invalid `cost_statistics` dirty/outbox/readiness scope 影响生产 runtime 状态 | 成本统计 scope policy 收敛后旧运行时状态仍保留裸月份/裸 all/非法 scope | `tests/test_read_model_scope_contract.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v` | 自动化已覆盖；生产 `--apply` 为 documented-risk |
| 2026-06-16 | `turnover_relation_changed` 再次生成 legacy `cost_statistics` scope 并造成生产 dead-letter/readiness failed | Postgres 事务型 producer 直接调用 `enqueue_read_model_refresh_in_transaction`，没有复用 scope policy registry | `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction`、`tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear` | `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear -v` | 自动化覆盖 producer；生产 legacy rows 仍需批准后 repair apply |
| 2026-06-16 | downstream all-scope read model 把 `bank_detail_read_model_not_fresh` 推导成 `bank_detail:all`，与 `bank_detail:all` fan-out 月份 shard 互相放大，导致 `turnover_ledger` / `no_oa_bank_batch` 长期 refreshing | 把 fan-out 控制 scope 当作稳定 freshness dependency，且 fan-out shard reason 未参与 active coalescing | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_detail_all_shard_reason_does_not_bump_active_scope` | `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_read_model_refresh_gateway -v` | 自动化覆盖架构边界；生产真实 drain 需发布后验证 |
| 2026-06-16 | fresh `bank_detail` read model 中部分 transaction id 没有投影时，downstream tag facade 误判为 read model missing/not fresh，持续 enqueue `downstream_bank_tag_read` 月份刷新 | missing rows 与 freshness 状态耦合；刷新不能制造不存在的投影行，导致每轮重试都再次 bump source_version | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_keeps_fresh_status_when_some_rows_are_not_projected`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` | `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime.BankTransactionTagReadFacadeTests -v` | 自动化覆盖 facade contract；生产仍需发布后确认 `downstream_bank_tag_read` 不再持续增加 |
| 2026-06-17 | 业务 read model payload 版本字段语义变化后没有 bump schema/source version，导致旧 projection 继续被当 fresh 返回 | 外部往来 grouped flow row 仍保存 `category_version=0`，但 live 写入 precondition 已按 `manual_category_version/version` 判断真实版本 | `tests/test_turnover_ledger_source_versions.py::TurnoverLedgerSourceVersionsTests::test_source_versions_include_all_turnover_and_cross_module_inputs`、`tests/test_turnover_ledger_service.py::TurnoverLedgerServiceTests::test_grouped_ledger_uses_manual_version_when_category_version_is_zero`、`test_grouped_ledger_uses_bank_row_version_when_category_versions_are_zero` | `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_service -v` | 自动化覆盖 turnover schema bump 和投影；生产仍需发布后 worker 重建旧 read model |
| 2026-06-16 | 多个月份依赖中一个 `bank_detail` 月份 pending/processing 时，downstream tag facade 把所有月份都作为 refresh target，导致已 fresh 月份反复回到 pending | non-fresh payload 缺少 blocking scope 粒度，facade 没有优先使用 `dirty_scopes` / signature `dirty_status` | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` | `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime.BankTransactionTagReadFacadeTests -v` | 自动化覆盖 facade contract；生产发布后必须观察月份 shard 不再每秒新增 `downstream_bank_tag_read` |
| 2026-06-16 | Workbench all-scope/full-scope 历史慢查询可能被重新接到首屏 groups API，导致大数据下页面读取突破一秒级目标 | all-scope 真实数据量大；首屏 API 如果绕过 repository page contract，会退化成无界读取 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_bounds_all_scope_groups_page_query` | `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_bounds_all_scope_groups_page_query -v` | 自动化覆盖首屏分页边界；生产投影/发布路径慢 SQL 仍需 staging/生产 profiling |
| 2026-06-20 | 导入确认后 pending invoice 固定投递 `expense:all/income:all/income:cash_income` 全量 aggregate，且进项/销项方向页固定双刷，造成无关页面 read model 刷新；同时 repository 从完整 snapshot 推导 `import.fact.changed`，容易把历史月份重新标脏 | 已知影响月份和文件方向未透传到 read model scope 生成；snapshot 保存层混入 write-operation fan-out 职责 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models`、`tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot`、`tests/test_import_processing_service.py::test_file_import_confirm_job_returns_import_write_targets`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_invoice_relation_scope_helpers_split_input_and_output_file_months` | `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot tests/test_import_processing_service.py tests/test_import_job_queue.py::ImportJobRepositoryTests::test_invoice_relation_scope_helpers_split_input_and_output_file_months -q` | 自动化覆盖月级 fan-out、方向级 fan-out、snapshot 保存不发 refresh、银行明细真实 refresh；真实大文件收益需生产/staging SLO 观察 |
| 2026-06-20 | 历史 `import.fact.changed` outbox 已 done，但 `reason=import_facts_changed` 的 dirty scope 仍 pending，App Status 可长期显示同步中且无 worker 事件可 claim。 | 旧 snapshot fan-out 写入 legacy dirty scope；兼容事件完成后没有统一清理 orphaned dirty scope 的运维入口。 | `tests/test_read_model_scope_contract.py::ReadModelScopeContractServiceTests::test_postgres_repository_lists_only_orphaned_import_fact_dirty_scopes`、`test_check_reports_orphaned_import_fact_dirty_scopes_without_writes`、`test_apply_deletes_orphaned_import_fact_dirty_scopes_and_records_audit`、`test_orphaned_import_fact_repair_is_idempotent` | `PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_scope_contract.py -q`；真实 runtime dry-run `scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json` | dry-run 已证明当前 runtime 有 42 条 orphaned legacy dirty scope；未执行 `--apply`，需生产窗口或批准。 |
| 2026-06-21 | 生产 PostgreSQL runtime 下，部分页面缺 SQL read repository 时仍可能回退旧 query service/live scan，导致页面状态与 read model readiness 分裂，或者旧 `live_query` 污染 refresh 判断。 | 输入/输出发票使用/收款页面历史上保留 legacy/local fallback；缺 repository 与缺 SQL view 是不同失败模式，生产必须 fail-closed。 | `tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_input_api_requires_sql_repository_in_production_without_live_scan`、`test_output_api_requires_sql_repository_in_production_without_live_scan`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_registered_month_or_all_read_models_reject_invalid_scope_keys` | `PYTHONPATH=backend/src python -m pytest tests/test_invoice_usage_collection_sql_runtime.py tests/test_read_model_refresh_gateway.py tests/test_read_model_architecture_guards.py -q` | 自动化覆盖生产 fail-closed 和 scope policy；生产当前只读审计显示 dirty/outbox/non-fresh readiness 均为 0，后续发布仍需 HTTP SLO/infra smoke。 |
| 2026-06-21 | 银行明细、OA 待付款、进项发票使用、销项发票收款等页面长期显示“正在刷新”，但 worker/queue 已无 backlog。 | `all` 同时承担 fan-out 控制 scope 和页面查询 scope；worker 只刷新月份 shard、不发布 parent `all` fresh proof，而页面 API 仍等待或比对 parent/global `all` source versions，导致 fresh child shards 被误判 stale 并反复补投。 | `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests::test_scope_keys_for_unbounded_bank_detail_reads_use_month_shards`、`tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_output_api_all_scope_does_not_loop_on_relation_all_versions`、`tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_production_all_scope_does_not_loop_on_relation_all_versions`、`tests/test_read_model_freshness.py::ReadModelFreshnessTests::test_normalize_source_versions_canonicalizes_nested_values` | `PYTHONPATH=backend/src python -m pytest tests/test_read_model_freshness.py tests/test_bank_details_sql_runtime.py tests/test_invoice_usage_collection_sql_runtime.py tests/test_oa_pending_payment_api.py -q` | 自动化覆盖 fan-out-only `all` 不等于 queryable `all`、无界银行明细改用月份 shard proof、发票/OA all 查询不再被全局 relation all 版本误判 stale；发布后仍需生产 HTTP SLO/worker drain smoke。 |

## 关键 smoke flows

- API miss smoke：业务 API 没有 SQL view 时，`ReadModelQueryGateway` 返回 refreshing 空 payload，并通过 `ReadModelRefreshGateway` 入队规范 scope；只有本次调用实际新增 refresh request 时 `refresh_enqueued=true`，同 scope 已有 active refresh 被合并时必须返回 `refresh_enqueued=false`。
- Production repository miss smoke：`_requires_sql_read_model_runtime()` 为真且页面 SQL read repository 缺失时，API 必须返回 refreshing 空 payload 并入队 `api_sql_repository_unavailable`，不能调用旧 query service 或返回 `live_query`。
- Source version stale smoke：SQL view 存在但 source/schema 不匹配时，API 不能标 fresh；应返回 refreshing/stale reasons 并入队 refresh，且不能写 Redis fresh cache。
- Worker readiness smoke：read model worker 成功后记录 readiness；失败时记录 failed/unavailable 类状态；fan-out-only 结果不能写假 fresh。
- Direct read model SLO smoke：`read_model_slo_smoke --apply` 必须输出每个 event 结果和 `summary.enqueue_to_fresh_ms` p50/p95/p99/max；P2/P3 一秒级解读必须看 p95 `<= 1000ms`，不能只看单条通过。
- Operation barrier smoke：写操作返回 affected scopes 后，前端轮询 `/api/operation-barrier/status`；后端基于 current-effective readiness/dirty/outbox 判定 fresh/refreshing/blocked，blocked 必须返回具体 target，不能关闭 overlay 后让页面显示旧关系。
- Scope contract smoke：生产旧 dirty/outbox/readiness scope 可 dry-run 检测，repair manifest 必须区分已覆盖历史 failure 与 current uncovered blocker；`--apply` 只删除非规范旧状态、补投可归一化 replacement scope、记录 audit/rollback，不清理 current uncovered blocker。
- Write operation attribution smoke：Workbench/no-OA 等高影响写操作必须把 action metadata 透传到 durable refresh request，`write_operation_slo_audit` 只能在 required scopes 都按 operation profile fresh 后通过；P2/P3 一秒级闭环要求 p95 `<= 1000ms` 且 p99 `<= 3000ms`；scenario discovery 生成的 mutating scenario 默认需要人工审批。

## 本模块验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_read_model_readiness_reporter -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier tests.test_read_model_slo_smoke -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_registry tests.test_read_model_slo_smoke tests.test_postgres_migrations tests.test_deploy_runtime_examples tests.test_runtime_redis -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_model_refresh_producer -v
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_lifecycle_derived_lifecycle_executor -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_bounds_all_scope_groups_page_query -v
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_invoice_lifecycle_read_model_refresh.py tests/test_invoice_lifecycle_read_facade.py tests/test_invoice_lifecycle_page_integration.py -q
python3 -m pytest tests/test_operation_freshness_barrier.py tests/test_app_health_api.py -q
cd web && npm test -- --run src/test/OperationBarrierApi.test.ts
bash scripts/verify.sh docs
bash scripts/verify.sh infra-smoke
```

## 2026-06-24 - search next pilot selection test note

- 本轮是 selection/planning slice，不改运行时代码。
- 下一条 `read-models:search-repository-port-extraction` 必须至少覆盖：
  - `tests/test_search_pending_sql_runtime.py`
  - `tests/test_search_api.py`
  - `tests/test_read_model_manifest.py`
  - `tests/test_runtime_worker_registry.py` 如 worker/manifest owner 被触及
- 必跑验证建议：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - search repository port extraction test note

- 新增 service-layer/read-model guard：`tests/test_search_pending_sql_runtime.py::SearchReadModelRepositoryPortTests::test_port_excludes_unrelated_read_model_methods`。
- 回归验证：`tests.test_search_pending_sql_runtime`、`tests.test_search_api`、`tests.test_read_model_manifest`，覆盖 search API shape、SQL read path、projection save path、refresh handler、manifest owner 和 search-pending compatibility。

## 2026-06-24 - search app rebuild helper quarantine test note

- 新增 architecture guard：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_rebuild_helpers_stay_out_of_application`。
- 回归验证：search SQL runtime、search API 和 manifest tests，证明删除 app-owned rebuild helper 不影响 active `/api/search` 或 worker projection path。

## 2026-06-24 - search query freshness service extraction test note

- 新增 service-layer tests：`tests/test_search_pending_sql_runtime.py::SearchQueryFreshnessServiceTests`。
- 新增 architecture guard：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_query_freshness_helpers_stay_out_of_application`。
- 覆盖：search SQL miss/fresh/source-version mismatch payload assembly、refresh enqueue reason、source-version proof ownership，以及 `Application` 不再拥有 query freshness helper。
- 回归验证：search SQL runtime、search API、manifest、runtime worker registry、app check、docs verify 和 diff check。

## 2026-06-24 - search refresh producer and invalidation extraction test note

- 新增 service-layer tests：`tests/test_search_pending_sql_runtime.py::SearchReadModelRefreshProducerTests`。
- 新增 architecture guard：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_refresh_producer_helpers_stay_out_of_application`。
- 覆盖：search refresh enqueue gateway boundary、month/all scope normalization、invalidation fallback 和 `Application` 不再拥有 search refresh producer/invalidation helper。
- 回归验证：search SQL runtime、search API、manifest、runtime worker registry、app check、docs verify 和 diff check。

## 2026-06-24 - search production repository unavailable fail-closed test note

- 新增 API/runtime regression：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_api_requires_sql_repository_in_production_without_live_scan`。
- 覆盖：生产 PostgreSQL runtime 下 `/api/search` 缺少 SQL repository 时返回 unavailable、入队 search refresh，且不调用 legacy/local live scan。
- 回归验证：search SQL runtime、search API、manifest、runtime worker registry、app check、docs verify 和 diff check。

## 2026-06-24 - search upstream producer boundary test notes

- OA projection sync fan-out：`tests/test_oa_projection_sync_service.py::OaProjectionSyncServiceTests::test_oa_sync_search_refresh_uses_search_producer_boundary` 覆盖 `OAProjectionSyncService` 不再直接 `enqueue_many("search", ...)`。
- Runtime import-state fan-out：`tests/test_runtime_worker_read_model_refresh_scopes.py::RuntimeWorkerReadModelRefreshScopeTests::test_import_state_search_refresh_uses_search_producer_boundary` 覆盖 runtime worker handler 不再直接 `_enqueue_scopes("search", ...)`。
- Search worker all-scope fan-out：`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_refresh_handler_expands_search_all_through_search_producer_boundary` 覆盖 `search:all` shard fan-out 通过 `SearchReadModelRefreshProducer.enqueue_scope_keys(...)`。
- Static guard：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_search_refresh_producer_helpers_stay_out_of_application` 防止 app、OA projection sync、runtime worker handlers 和 Search pending refresh service 重新绕过 Search producer。

## 2026-06-24 - search post-all-scope local closure audit test note

- 新增测试：无。本轮是 analysis/accounting slice，不改运行时代码或测试 contract。
- 复用覆盖：Search repository port、query freshness service、refresh producer、production fail-closed、OA fan-out、runtime import-state fan-out、Search worker all-scope fan-out、manifest、registry 和 static guard 测试。
- 结论：未发现剩余本地 implementation gap；Search local support 转为 `production-evidence-deferred`，但真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍未闭环。

## 2026-06-24 - bank account balance next pilot selection test note

- 本轮是 selection/planning slice，不改运行时代码。
- 新增模块维护骨架：`docs/modules/bank-account-balance/`。
- 下一条 `read-models:bank-account-balance-repository-port-extraction` 必须至少覆盖：
  - `tests/test_bank_account_balance_read_model.py`
  - `tests/test_bank_details_sql_runtime.py`
  - `tests/test_bankdetail_backfill_cli.py`
  - `tests/test_read_model_manifest.py`
  - `tests/test_runtime_worker_registry.py`
- 必跑验证建议：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## 2026-06-24 - bank account balance repository port extraction test note

- 新增 service-layer/read-model guard：`tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests::test_port_excludes_unrelated_read_model_methods`。
- 新增 Bank Details service regression：`tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests::test_application_accounts_uses_account_balance_repository_port`。
- 覆盖：账户余额 projection save 和 Bank Details accounts SQL read path 走显式 `BankAccountBalanceReadModelRepositoryPort`，同时保留 API shape 和旧兼容 fallback。
- 下一步：审计 refresh/freshness/operation-barrier、all-only scope contract 和剩余 compat fallback。

## 2026-06-24 - bank account balance refresh/freshness/operation-barrier audit test note

- 新增测试：无。本轮是 analysis/accounting slice。
- 复用覆盖：`tests/test_bank_account_balance_read_model.py`、`tests/test_bank_details_sql_runtime.py`、`tests/test_bankdetail_backfill_cli.py`、`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`。
- 审计结论：`BankAccountBalanceReadModelRefreshProducer` 是下一条实现边界；后续必须补 producer/gateway boundary tests、all-only scope contract guard、dedicated operation barrier regression 和 compat fallback quarantine。

## 2026-06-24 - bank account balance refresh producer extraction test note

- 新增 producer tests：`tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests::test_refresh_producer_enqueues_all_scope_through_gateway`、`test_refresh_producer_returns_false_when_gateway_unavailable`。
- 新增 runtime worker tests：`tests/test_runtime_worker_read_model_refresh_scopes.py::RuntimeWorkerReadModelRefreshScopeTests::test_import_state_bank_account_balance_refresh_uses_producer_boundary`、`test_lifecycle_bank_account_balance_refresh_uses_all_only_producer_boundary`。
- 新增 static guard：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_account_balance_refresh_producer_helpers_stay_out_of_application`。
- 覆盖：account-balance refresh enqueue 不再由 app/runtime/backfill direct helper 持有，且所有路径保持 `bank_account_balance:all`。

## 2026-06-24 - bank account balance derived lifecycle executor extraction test note

- 新增 executor tests：`tests/test_bank_account_balance_derived_lifecycle_executor.py`。
- 新增 static guard：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_account_balance_derived_lifecycle_uses_explicit_executor_boundary`。
- 覆盖：derived lifecycle response assembly 不再由 Application 持有，并保持 all-only payload shape。

## 2026-06-24 - bank account balance all-only scope contract test note

- 新增 gateway/scope-policy test：`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_account_balance_policy_accepts_only_all_scope`。
- 覆盖：gateway 只允许 `bank_account_balance:all` 入 durable queue，拒绝 month/account/active scope。

## 2026-06-24 - bank account balance operation barrier regression test note

- 新增 operation barrier tests：`tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests::test_bank_account_balance_all_dirty_scope_keeps_accounts_target_refreshing`、`test_bank_account_balance_all_outbox_pending_keeps_accounts_target_refreshing`、`test_other_read_model_outbox_pending_does_not_block_bank_account_balance_all_target`。
- 覆盖：账户余额 `all` scope 仍 pending/refreshing 时，accounts freshness target 不能被误判 fresh。

## 2026-06-24 - bank account balance Bank Detail fallback quarantine test note

- 更新 Bank Detail port test，证明 `BankDetailReadModelRepositoryPort` 不再暴露 `list_bank_account_balances(...)`。
- 新增 static guard：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_account_balance_accounts_path_does_not_fallback_to_bank_detail_port`。
- 覆盖：Bank Details accounts SQL read path 不再把 Bank Detail port 当作 account-balance owner。

## 2026-06-24 - bank account balance local implementation closure audit test note

- 新增测试：无。本轮是 analysis/accounting slice。
- 复用覆盖：`tests/test_bank_details_sql_runtime.py`、`tests/test_bank_account_balance_read_model.py`、`tests/test_bank_account_balance_derived_lifecycle_executor.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_operation_freshness_barrier.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_bankdetail_backfill_cli.py`、`tests/test_runtime_bootstrap.py`、`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py` 和 account-balance static guards。
- 结论：未发现剩余本地 implementation gap；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。

## 2026-07-02 - Workbench / Turnover bulk persistence performance tests

- 新增/更新测试：`tests/test_postgres_repositories_boundaries.py::test_read_model_bulk_insert_prefers_multi_values_path_for_allowlisted_tables` 覆盖 `read_model.workbench_rows`、`read_model.workbench_groups`、`read_model.workbench_group_rows`、`read_model.search_index_rows` 和 `read_model.turnover_ledger_rows` 的 multi-values bulk path。
- 回归测试：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_batches_all_scope_generation_rows_when_supported`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_batches_workbench_generation_rows_when_supported`、`tests/test_turnover_ledger_read_model_refresh.py`。
- 覆盖类别：read model/cache/background job tests、service-layer persistence boundary regression、existing feature regression。API contract、frontend interaction、E2E business-flow 本轮不适用，因为没有改变 HTTP response shape、页面行为或业务写入口。
- 生产复测：release `pscip-l4-bulk-persistence-abcca6f78` 发布后运行 `read_model_slo_smoke --critical-only --apply --target-ms 5000` 和 `--target-ms 1000`；5s 为 13/16 pass，1s 为 9/16 pass。`turnover_ledger:all` 1s pass，`workbench:2026-03` 仍 fail。运行 `write_operation_slo_audit --lookback-hours 24 --target-ms 1000 --p99-target-ms 3000 --limit 2000`，结果仍 fail，且缺少部分真实写操作样本。

## 2026-07-02 - Workbench source_version / insert-only generation detail tests

- 更新测试：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_month_rebuild_defers_all_scope_aggregation` 现在断言 worker/event 已传入 `source_version` 时不得再查询 dirty scope source version，并验证 snapshot source version 沿输入 I/O 传播。
- 更新测试：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_persists_workbench_groups_alongside_rows_and_snapshot`、`test_repository_persists_workbench_rows_alongside_snapshot` 断言 generation 明细表不再包含旧 `(generation_id, scope_key, ...) ON CONFLICT DO UPDATE` 分支。
- 覆盖类别：read model/cache/background job tests、service-layer persistence boundary、existing feature regression。API contract、frontend interaction、business core、E2E 真实业务流本轮未新增，因为外部 HTTP/API shape、页面行为和业务 relation 写入口没有变化。
- 本地验证：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py tests/test_runtime_worker.py tests/test_read_model_slo_smoke.py tests/test_postgres_connection.py -q` 为 `210 passed`；边界/API/部署回归命令为 `92 passed`。
- 生产验证：release `pscip-l4-workbench-insert-5f530d1b5` 上 `/health/ready` ready、required worker missing/stale/mismatch `0/0/0`、scope contract default/invalid-scope 均 `ok=true`；最新 critical 5s grouped run 为 14/16 pass，`turnover_ledger:all` 与 `bank_flow_rule_batch:2026-02` 超过 5s，targeted retry 分别 `993.910ms`、`455.961ms` pass。Workbench 1s targeted 仍 fail，真实 confirm/withdraw/no-OA withdraw 当前 release 样本缺失，保留为未测风险。

## 2026-07-02 - Workbench raw payload write amplification tests

- 新增测试：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_writes_workbench_payload_without_duplicate_raw_payload`。
- 更新测试：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_batches_all_scope_generation_rows_when_supported` 现在断言 all-scope snapshot/summary/rows/groups/group_rows 的规范 owner payload 与 `raw_payload={}` 合同：summary 保留 summary payload，rows 保留行详情 payload但裁剪 nested `object_identity`，groups 只保留组级 metadata/count/sort/materialized marker，group_rows 只保留结构化 membership/filter/search/object-identity 列，`payload` / `raw_payload` / `source_versions` 均写 `{}`。
- 覆盖类别：read model/cache/background job tests、service-layer persistence boundary、existing feature regression。API contract、frontend interaction、business core、E2E 真实业务流本轮未新增，因为 HTTP response shape、页面行为和业务写入口未改变。
- 本地验证：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py -q` 为 `178 passed`；`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py tests/test_runtime_worker.py tests/test_read_model_slo_smoke.py tests/test_postgres_connection.py -q` 为 `211 passed`。
- 生产验证：release `pscip-l4-workbench-raw-51cba11e8` 上 `/health/ready` ready，scope contract default/invalid-scope 均 `ok=true`。critical `read_model_slo_smoke --apply --critical-only --target-ms 5000` 为 `16/16` pass，max enqueue-to-fresh `3581.490ms`；targeted `workbench:all --target-ms 1000` pass，enqueue-to-fresh `397.159ms`、handler `352.381ms`。
- 生产 raw payload 证明：active `workbench:all` 的 snapshot/summary/`1701` rows/`960` groups/`1941` group_rows 全部 `raw_payload={}`、`raw_has_normalized=0` 且 payload 非空；active `workbench:2026-02` 同样满足该合同。
- 未测风险：当前 release 之后真实 Workbench relation confirm/withdraw、bank-invoice/bank-turnover confirm/withdraw 和 no-OA withdraw 样本全部缺失，写操作 SLO 仍不能关闭。

## 2026-07-03 - Workbench snapshot/group payload owner tests

- 新增/更新测试：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_materializes_legacy_workbench_view_from_groups_when_snapshot_is_lightweight`、`test_repository_batches_all_scope_generation_rows_when_supported`、`test_repository_writes_workbench_payload_without_duplicate_raw_payload`；`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts`。
- 覆盖合同：`workbench_snapshots.payload` 只保存 metadata/summary shell 和 `workbench_groups_materialized=true` marker；`workbench_groups.payload` 只保存组级 metadata/count/sort/`workbench_group_rows_materialized` marker，不再保存 `oa_rows`、`bank_rows`、`invoice_rows`、`collapsed_rows` 或其它 `*_rows` 成员数组；`workbench_group_rows` 保存成员关系和最小审计 metadata；旧 `/api/workbench` 兼容 view、groups page/detail 和成本统计必须从同一 active generation 的 `workbench_group_rows + workbench_rows` materialize 完整组输出。
- 覆盖类别：service-layer tests、API contract tests、read model/cache/background job tests、existing feature regression。business core 未新增，因为成本归因规则未变；frontend component 未新增，因为页面 response shape 保持 materialized 后兼容；E2E 真实业务流仍等待生产 SLO/write-operation 样本闭环。

## 2026-07-03 - Workbench UoW batch refresh enqueue tests

- 新增测试：`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_enqueue_read_model_refreshes_in_transaction_batches_dirty_scope_and_outbox_writes`。
- 新增测试：`tests/test_workbench_uow_contract.py::WorkbenchUoWContractTests::test_read_model_refresh_writer_uses_batch_repository_interface_when_available`、`test_relation_write_uow_uses_batch_read_model_refresh_writer_when_available`。
- 覆盖合同：事务内多个 read model refresh target 可批量写入 dirty scope/outbox，但必须保持 source_version、dedupe、priority、trace_id、action metadata 和 response source version 映射。
- 覆盖类别：service-layer tests、read model/cache/background job tests、existing feature regression。API contract、frontend interaction 和 E2E 真实业务流未新增，因为外部响应/页面行为不变，生产 latency 仍需固定 write scenario 证明。

## 2026-07-05 - Workbench hot aggregate scheduling tests

- 更新测试：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_uses_coalescing_all_aggregate_enqueue_when_available` 断言 high priority 月分片发布后 `workbench:all` aggregate delay 为 `0s`。
- 更新测试：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_can_enqueue_aggregate_without_legacy_enqueue_method` 断言普通优先级仍保留 `3s` aggregate 合并窗口。
- 覆盖类别：read model/cache/background job tests、service-layer worker scheduling、existing feature regression。API contract 未改；frontend interaction 只调整轮询间隔，复用 `WorkbenchSelection` 行为测试；E2E 真实业务流仍需生产固定 write scenario 验证。

## 2026-07-06 - Invoice lifecycle volatile source_version canonicalization tests

- 新增测试：`tests/test_invoice_lifecycle_sql_projection.py::test_invoice_lifecycle_dependency_versions_ignore_runtime_source_version_only`。
- 覆盖合同：`invoice_lifecycle` 依赖 source_versions 递归移除精确键名 `source_version`，但保留 `*_source_version`、schema/signature/updated_at 等稳定版本字段；上游 read model no-op refresh 的队列计数变化不能触发 lifecycle full rebuild。
- 覆盖类别：read model/cache/background job tests、service-layer projection boundary、existing feature regression。API contract、frontend interaction、business core 和 E2E 真实业务流未新增，因为 HTTP response shape、页面行为和业务写入口不变。

`infra-smoke` 默认跑 read model SLO、runtime sync closure gate、write-operation SLO 和 RabbitMQ staging preflight 工具合同；设置 `FIN_OPS_TEST_DATABASE_URL` 后会追加 critical read model 的 `read_model_slo_smoke --critical-only` dry-run scope discovery，仍不写入 queue。只有同时设置 `FIN_OPS_INFRA_SMOKE_APPLY=1` 时才会追加 `--apply`，真正 enqueue refresh events 并等待 worker drain；设置 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed` 等 profile 后，会追加只读 `write_operation_slo_audit`，审计最近真实业务写入产生的 durable refresh events；设置 `FIN_OPS_TEST_DATABASE_URL` + `RABBITMQ_TEST_URL` 后还会追加 RabbitMQ staging preflight。该入口用于验证 read model / worker 最新状态，不能用 deterministic Browser mock 替代，但必须区分 dry-run、apply 和真实业务写入 audit 证据。

## Nightly CI 覆盖

- `bash scripts/verify.sh all` 会运行全量后端 unittest，因此覆盖上述 read model 模块测试。
- `bash scripts/verify.sh all` 会运行前端 Vitest，因此覆盖页面消费 `read_model_status` 的前端测试。
- `bash scripts/verify.sh docs` 会确认测试闭环文档入口存在。
- Nightly 不连接真实生产 PostgreSQL、Redis、RabbitMQ、OA Mongo；这些风险保留为发布前 dry-run/staging 验证。

## 未测风险

- 未在真实生产 PostgreSQL 上执行 `scripts/check-read-model-scope-contracts.py --json` 或 `--apply`；上线前必须先 dry-run 检查 JSON repair manifest，确认 current uncovered failure 的真实原因，再按 runbook 执行受控清理。
- 生产 critical `read_model_slo_smoke --apply` 已在 release `main-99ea9b35-invoice-lifecycle-batch-20260619145710` 上证明 15/15 个关键 read model scope 达到 `done/fresh` 且 5 秒 SLO 通过：summary p95/max 约 3.52 秒，`invoice_lifecycle` 约 1.29 秒。该证据证明 direct refresh worker drain，不等同于每个真实业务写入口都已完成 write-operation SLO audit。
- 生产 `write_operation_slo_audit` 在 168 小时窗口内发现历史真实写链路样本仍有 1 秒/3 秒 SLO 超时；以 hotfix release 激活时间为 `--since` 后，高影响业务写操作 profile 仍全为 `missing`。因此真实业务写入口闭环必须继续通过已生成的 scenario 候选和真实认证/审批执行来证明。
- 本模块不逐个证明所有业务页面对 `refreshing/stale/missing/failed` 的 UI 行为；后续页面模块闭环必须补齐。
- 本模块默认不验证真实 Redis/RabbitMQ 网络和 worker drain；runtime-workers 与 operations/staging 覆盖。`bash scripts/verify.sh infra-smoke` 只有在 `FIN_OPS_TEST_DATABASE_URL` 和 `FIN_OPS_INFRA_SMOKE_APPLY=1` 同时存在时，才是直接 enqueue worker drain 证据；只有在 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS` 指定 operation 且环境中已有对应真实业务写入样本时，才是该写链路 durable outbox fan-out 证据。
- `server.py` 仍有 legacy route 分发；每个业务模块需要继续确认 route 是否走 `ReadModelQueryGateway` 或等价 freshness boundary。

## 2026-07-20 - workbench_relation relation-only delta

- Worker dispatch：`tests/test_workbench_relation_read_model_refresh.py::WorkbenchRelationReadModelRefreshServiceTests::test_handle_runtime_event_uses_explicit_relation_delta_contract`。
- Projection bounded I/O：`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_relation_delta_uses_narrow_version_and_active_relation_queries`。
- Repository contract：`tests/test_postgres_repositories_boundaries.py::test_workbench_relation_delta_source_versions_preserve_unrelated_sources`。
- 真实 PostgreSQL：`tests/test_turnover_ledger_postgres_integration.py::TurnoverLedgerPostgresIntegrationTests::test_workbench_relation_delta_source_versions_advance_only_relation_proof`。

## 2026-07-22 - Workbench v6 freshness 边界

- `tests/test_workbench_sql_runtime.py::test_workbench_v6_rejects_v5_month_all_and_cache_versions` 覆盖 month/all v6、groups/initial cache 派生版本，以及旧 v5 source version 的 `builder_mismatch`。
- 既有 SQL runtime/query tests 继续覆盖 building/failed 不可读为 fresh、active generation 原子发布和 requirement-aware paired/unpaired 分区；本轮没有新增 worker、registry、manifest、env 或 read model scope。
- 生产验证必须经 exact release checkpoint 先 repair、再由正式 gateway/worker rehydrate；禁止直接写 projection 或伪造 fresh。
