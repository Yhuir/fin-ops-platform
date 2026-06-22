# Runtime Worker 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

Runtime worker 是全局后台执行面，修改前必须逐项确认影响范围：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| Worker 注册与启动 | `runtime_worker_registry.py`、`app/worker.py`、manifest CLI、deploy env examples | required worker 是否完整、`--registration --worker-instance --check` 是否继续输出 registry 派生配置、systemd env 是否覆盖所有 event type |
| Durable queue | `RuntimeQueueRepository`、`job.outbox_events` | enqueue/dedupe、claim、stale reclaim、complete、retry、dead-letter、publish 状态、operator resolution |
| Read model dirty scope | `job.read_model_dirty_scopes`、`ReadModelRefreshGateway`、scope policy registry | dirty scope source version、source guard、非法 scope 清理、replacement enqueue、不可伪造 fresh |
| Worker loop | `RuntimeWorker.run_once()`、handler registry | heartbeat、statement timeout、task timeout、retry delay、max attempts、无 handler 失败路径 |
| Readiness / App Health | `RuntimeMonitoringRepository`、`ReadModelReadinessReporter` | missing/stale/mismatch/failed/unavailable 聚合、scope 级诊断、worker kind/event type mismatch |
| RabbitMQ transport | `rabbitmq_runtime.py`、dispatcher/consumer/preflight | RabbitMQ 只传 envelope/wakeup，不携带业务 payload；Postgres 仍是事实源；ack 必须在 Postgres claim 成功后 |
| 运维命令 | `runtime_queue_ops`、scope contract check、readiness backfill | inspect/requeue/resolve-dead-letter 必须保留审计和 freshness 前置条件 |
| 跨模块 fan-out | import、ETC、workbench、bank detail、invoice lifecycle、cost/tax read models | 新增事件不能绕过 gateway、registry 或 readiness reporter；旧页面不能读取 stale projection 伪装 fresh |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| Worker 从 Postgres claim event 并 complete | P0 | `tests/test_runtime_worker.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_infrastructure_postgres_integration.py` | covered | 覆盖内存 fake 与真实 Postgres integration。 |
| Handler 失败进入 retry / dead-letter | P0 | `tests/test_runtime_worker.py`、`tests/test_runtime_queue.py` | covered | 覆盖 retry delay、max attempts、processing lock。 |
| Handler 遇到依赖 read model 未 fresh 时短延迟 defer | P0 | `tests/test_runtime_worker.py`、`tests/test_runtime_queue.py` | covered | `*_read_model_not_fresh` / `read_model_not_fresh` 不走普通失败/dead-letter，而是短延迟回 pending。 |
| Same-scope parent shard 未 fresh / inconsistent 时补投 parent scope | P0 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_requeues_same_scope_parent_when_generation_is_inconsistent` | covered | `workbench_read_model_not_fresh: parent_generation_inconsistent parent_scope_keys=...` 不被同 scope skip；会补投 parent month scope，且不被旧 fresh readiness 短路；当前 all/parent event 使用 retry 级退避，避免快速重发抢占 parent month shard。 |
| defer 遇到同 dedupe pending 覆盖事件 | P0 | `tests/test_runtime_queue.py` | covered | 当前 processing 事件标记 done + `runtime_defer_superseded`，避免唯一冲突导致 worker 崩溃并等待 300s lock timeout。 |
| defer 遇到旧 done 事件 source_version 更高 | P0 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_does_not_let_older_done_event_cover_newer_processing_event` | covered | 覆盖事件必须比当前 processing event 更新；旧 done 事件不能把新导入产生的 dirty scope 对应事件错误标记 superseded。 |
| 无 handler / 无 event type 不误 claim | P0 | `tests/test_runtime_worker.py` | covered | 防止 worker 注册错误时吞事件。 |
| Heartbeat 写入与 required worker mismatch | P0 | `tests/test_runtime_worker.py`、`tests/test_runtime_monitoring.py`、`tests/test_runtime_worker_registry.py` | covered | 覆盖 instance、kind、event type mismatch。 |
| 高频 read model 专用 consumer | P0 | `tests/test_runtime_worker_registry.py` | covered | `search`、`search-secondary`、`search-tertiary`、`pending-invoice`、`cost-statistics`、`tax-offset`、`invoice-lifecycle-secondary` 必须保留 required RabbitMQ eligible worker，避免 SLO 退化回 combined worker 串行 drain。 |
| Registry / manifest / deploy env 同步 | P0 | `tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_read_model_slo_smoke.py`、`tests/test_postgres_migrations.py`、`tests/test_runtime_redis.py`、`tests/test_runtime_convergence_closure.py` | covered | 防止新增 worker/read model 只改一处：App Status read model 必须匹配 required worker、RabbitMQ dispatch event、SLO smoke scope、migration storage contract 和 Redis/env 模板。 |
| Read model refresh scope 归一化、校验、去重 | P0 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered | 成本统计旧裸月份/裸 `all` 已有回归覆盖。 |
| Readiness reporter 记录 fresh/failed/mismatch/refreshing | P0 | `tests/test_read_model_readiness_reporter.py`、`tests/test_app_status_readiness_backfill.py` | covered | 覆盖 handler wrapper 和禁止 fan-out 父 scope 伪 fresh。 |
| App Health runtime snapshot | P0 | `tests/test_runtime_monitoring.py` | covered | 覆盖 backlog、failed job、stale dirty scope、worker metrics。 |
| RabbitMQ envelope 不包含业务 payload | P0 | `tests/test_runtime_queue.py`、`tests/test_rabbitmq_runtime.py`、`tests/test_runtime_infrastructure_postgres_integration.py` | covered | RabbitMQ 只可承载 routing identity/version。 |
| RabbitMQ dispatcher publish confirm 后才 mark published | P0 | `tests/test_rabbitmq_runtime.py` | covered | 防止未确认 publish 被标记成功。 |
| RabbitMQ consumer 先 claim Postgres 再 ack | P0 | `tests/test_rabbitmq_runtime.py` | covered | 防止 RabbitMQ 消息成功但 Postgres 事实未锁定。 |
| Runtime queue ops inspect/requeue/resolve dead-letter | P1 | `tests/test_runtime_queue_ops.py` | covered | resolve 要求 fresh readiness 且无 active dirty scope。 |
| RabbitMQ transport 下 stale/superseded processing 处理 | P1 | `tests/test_runtime_queue.py`、`tests/test_runtime_queue_ops.py` | covered | 可重新处理的 stale `processing` 释放回 pending；已被更新同 dedupe event 覆盖的旧 `processing` 走 superseded resolution；两者都写 operator audit，不伪造 fresh。 |
| Runtime state policy / legacy snapshot boundary | P1 | `tests/test_runtime_state_policy.py`、`tests/test_runtime_bootstrap.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | 防止 worker 或生产 bootstrap 回退到 Application/full snapshot。 |
| 真实 RabbitMQ topology publish/consume | P1 | `tests/test_rabbitmq_integration.py`、`tests/test_rabbitmq_staging_preflight.py` | documented-risk | 需要 `RABBITMQ_TEST_URL`；本地/nightly 默认可 skip；staging preflight 缺 `FIN_OPS_TEST_DATABASE_URL` / `RABBITMQ_TEST_URL` 时返回 `configuration_missing`，不当作实现失败。 |
| 真实 Postgres migration + queue integration | P1 | `tests/test_runtime_infrastructure_postgres_integration.py` | documented-risk | 需要 `FIN_OPS_TEST_DATABASE_URL`；无环境时 skip。 |
| 真实 systemd worker drain / 长时间运行 | P2 | `docs/operations/runtime-worker-governance.md` runbook | documented-risk | 需要 staging/生产环境，不作为本地单元测试前置。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_runtime_queue.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_state_policy.py` | Queue 状态流转、scope contract、runtime state cleanup policy 都属于后台业务规则。 |
| 2. Service-layer tests | 适用 | `tests/test_runtime_worker.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_runtime_monitoring.py`、`tests/test_runtime_queue_ops.py`、`tests/test_rabbitmq_staging_preflight.py` | 覆盖 worker orchestration、repository 写入、monitoring、ops 命令前置条件和 staging preflight 环境门禁。 |
| 3. API contract tests | 间接适用 | `tests/test_app_health_*`、`tests/test_runtime_monitoring.py` | 本模块自身不暴露普通业务 API；通过 App Health/runtime snapshot 保护响应事实。若改 `/health` 或 `/api/app-health` shape，必须补 API contract test。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_read_model_readiness_reporter.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_app_status_readiness_backfill.py` | 覆盖 read model refresh handler wrapper、dirty scope、readiness convergence。 |
| 5. Frontend component and interaction tests | 间接适用 | `web/src/test/AppHealth*.test.tsx` | 修改 App Health 展示、loading/stale/error 语义时必须补前端交互测试；纯 worker 内部改动不适用。 |
| 6. End-to-end business-flow integration tests | 按需适用 | `tests/test_runtime_infrastructure_postgres_integration.py`、`tests/test_rabbitmq_integration.py`、`tests/test_rabbitmq_staging_preflight.py`、各业务模块 smoke | 修改跨模块事件或 worker fan-out 时，至少补一个关键业务流 integration/regression test；缺真实 staging env 只能证明 preflight contract，不能证明 broker drain。 |
| 7. Existing feature regression tests | 适用 | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py` | 防止新增 worker/read model/event type 破坏旧 registry、deploy、auth/Application 边界。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-22 | 生产 schema/worker/RabbitMQ/Redis 已有单独测试，但没有跨 registry 门禁；新增 read model 可能只更新 App Status 或 worker registry，漏掉 migration storage contract、critical SLO smoke 或 deploy env，导致本地测试通过、生产运行面缺 worker/schema/transport/cache 配置。 | `tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_app_status_read_model_registry_matches_worker_and_rabbitmq_contracts`、`tests/test_read_model_slo_smoke.py::ReadModelSloSmokeTests::test_critical_only_plans_every_critical_app_status_read_model`、`tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_app_status_read_model_storage_contracts_are_declared`、`tests/test_deploy_runtime_examples.py::DeployRuntimeExampleTests::test_shared_rabbitmq_worker_env_does_not_switch_all_workers_to_rabbitmq`、`tests/test_runtime_redis.py::RuntimeRedisTests::test_production_env_examples_match_runtime_redis_settings_contract` | covered |
| 2026-06-10 | Worker lifecycle 向 `cost_statistics.read_model.refresh` 投递裸月份/裸 `all`，SQL projection 拒绝 scope。 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered |
| 2026-06-10 | 非事务 producer 可能绕过 `ReadModelRefreshGateway` 直接调用 `RuntimeQueueRepository.enqueue_read_model_refresh(...)`。 | `tests/test_platform_runtime_boundary_guards.py::test_read_model_refresh_producers_use_scope_gateway_boundary` | covered |
| 2026-06-11 | 静态 boundary guard 误把 OA 登录 JSON 响应字段 `Admin-Token` 判定为 service 解析 HTTP cookie/header。 | `tests/test_platform_runtime_boundary_guards.py::test_services_do_not_import_http_auth_boundary_or_parse_cookie_token_headers`、`tests/test_target_oa_applicant_token_provider.py` | covered |
| 2026-06-13 | downstream read model 依赖 source read model 尚未 fresh 时，被普通 retry 放大成 60s+ 等待甚至 dead-letter。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_defers_dependency_not_fresh_without_marking_failed`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_delays_dependency_retry_without_failure_or_dead_letter` | covered |
| 2026-06-13 | `defer_event` 把 processing 事件改回 pending 时，如果同 dedupe 已有 pending 新事件，会触发唯一索引冲突并使 worker 崩溃，事件卡到 lock timeout。旧多写 CTE 仍可能执行 pending 分支；当前回归要求覆盖事件存在时只执行 superseded resolve 分支，并且并发 pending 在预查后提交时用 `23505` fallback 二次 resolve。 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_resolves_current_processing_when_pending_same_dedupe_exists`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_resolves_unique_collision_from_concurrent_pending_cover` | covered |
| 2026-06-13 | RabbitMQ worker 只消费 envelope，PostgreSQL 旧 `processing` 行没有对应消息时不会被普通消费自动 reclaim，导致 source read model 长时间 not fresh。 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_release_stale_processing_events_requeues_with_operator_audit`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_resolve_superseded_processing_events_marks_obsolete_processing_done`、`tests/test_runtime_queue_ops.py::RuntimeQueueOpsTests::test_release_stale_processing_dry_run_lists_candidates_without_update` | covered |
| 2026-06-14 | `search-pending`、`cost-tax` 和单 `invoice-lifecycle` worker 串行 drain 多个下游事件，真实 confirm/withdraw 后部分 read model enqueue-to-done 仍超过 5s。 | `tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_hot_read_model_workers_have_dedicated_parallel_consumers` | covered |
| 2026-06-14 | 生产 systemd 模板未显式传 `--dependency-not-fresh-delay-seconds`，只能使用代码默认 2s，关系 fan-out 依赖链固定等待偏长。 | `tests/test_deploy_oa_script.py::DeployOaScriptTests::test_systemd_worker_template_uses_registry_registration_contract` | covered |
| 2026-06-14 | 真实 confirm/withdraw 在 1s dependency defer 与两条 search lane 下，`pending_invoice` dependency retry 和快速 withdraw 的第二个 search scope 仍可能超过 5s。 | `tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_hot_read_model_workers_have_dedicated_parallel_consumers`、`tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_defers_dependency_not_fresh_without_marking_failed`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_delays_dependency_retry_without_failure_or_dead_letter` | covered |
| 2026-06-14 | dependency-not-fresh 补投依赖时，如果依赖 refresh outbox 已经 pending/processing，会 bump 新 source_version 并把等待者继续推迟。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_bump_dependency_refresh_when_scope_already_active`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_read_model_refresh_is_active_checks_pending_or_processing_outbox_event` | covered |
| 2026-06-21 | dependency dirty scope orphan 但 outbox 已 done/缺失时，worker 误判依赖 active，不再补投上游 refresh，导致 downstream read model 长期 refreshing。 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_read_model_refresh_is_active_checks_pending_or_processing_outbox_event`、`tests/test_read_model_scope_contract.py::ReadModelScopeContractServiceTests::test_check_reports_invalid_policy_managed_read_model_scopes_without_writes` | covered |
| 2026-06-14 | projection/facade 的 ensure refresh reason 在依赖 read model 已 active 时仍通过 gateway 入队，覆盖真实写入 reason 并持续 bump source_version，导致 `pending_invoice` 写后收敛 40s+。 | `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_ensure_refresh_reason_does_not_bump_active_scope`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_mutating_refresh_reason_still_bumps_active_scope` | covered |
| 2026-06-16 | `turnover_ledger:all` / `no_oa_bank_batch:all` 因 `bank_detail_read_model_not_fresh` defer 时自动补投 `bank_detail:all`，而 `bank_detail:all` 又 fan-out 月份 shard，导致 dirty scope source_version 持续被 bump，页面长期 refreshing。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_detail_all_shard_reason_does_not_bump_active_scope` | covered |
| 2026-06-16 | downstream projection 读取 fresh `bank_detail` read model 时，部分 transaction id 未投影也被当成 `missing`/not fresh，`downstream_bank_tag_read` 因此每轮都补投月份 shard，刷新后仍缺同一批 id，形成永久循环。 | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_keeps_fresh_status_when_some_rows_are_not_projected`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` | covered |
| 2026-06-16 | downstream projection 读取多个月份时，一个月份 active 会让 facade 重刷所有月份，导致已 fresh 月份被父 worker 的快速重试反复打 pending。 | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` | covered |
| 2026-06-14 | `invoice_lifecycle` 缺少 source_version current guard，快速 confirm/withdraw 时旧版本事件可能继续重建并污染写操作审计；workbench 同步 Redis warmup 进入 refresh ack 前热路径，导致连续写入第二个 workbench event 超过 5s。 | `tests/test_invoice_lifecycle_read_model_refresh.py`、`tests/test_workbench_query_facade.py::WorkbenchGroupsPageCacheWarmerTests::test_sync_cache_warmup_is_disabled_by_default_and_explicitly_enabled` | covered |
| 2026-06-14 | `bank_detail` 缺少 source_version current guard，快速 confirm/withdraw 时旧版本 bank detail 事件会完整 rebuild 并让新版本事件排队，放大 `pending_invoice` 依赖等待。 | `tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests::test_stale_source_version_does_not_rebuild_or_complete`、`tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests::test_source_version_that_becomes_stale_after_rebuild_does_not_complete` | covered |
| 2026-06-15 | Workbench month shard 发布后投递的 `all` aggregate-only 事件使用 shard source_version；如果继续按 all dirty scope source_version 做 stale guard，事件会被跳过，或者 aggregate 未发布仍被标记 done，导致 all generation 长期停留在旧污染版本。 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_runs_all_aggregate_after_shard_publish_even_if_all_scope_source_is_newer`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_does_not_complete_dirty_scope_when_all_aggregate_did_not_publish` | covered |
| 2026-06-20 | 发票导入后新 `processing` refresh event 被同 dedupe 的历史 `done` event 覆盖，`runtime_defer_superseded` 把事件置 done，但当前 dirty scope 仍 pending/refreshing，App Status 长时间不收敛。 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_does_not_let_older_done_event_cover_newer_processing_event` | covered |
| 2026-06-20 | `import.fact.changed` 只 ack 不投递真实 bank detail refresh，或完整 imports snapshot 保存阶段直接生成 import fact dirty/outbox，导致历史月份被重刷或兼容事件 ack 后业务 read model 未更新。 | `tests/test_import_job_queue.py::ImportJobRepositoryTests::test_import_fact_changed_handler_completes_matching_dirty_scope`、`tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot`、`tests/test_import_processing_service.py::test_general_import_confirm_passes_bank_detail_scope_keys_to_persist_state` | covered |
| 2026-06-20 | 发票导入后台 worker 对进项/销项方向页固定双刷，input-only/output-only 文件会刷新无关 read model，放大导入后同步尾延迟。 | `tests/test_import_job_queue.py::ImportJobRepositoryTests::test_invoice_relation_scope_helpers_split_input_and_output_file_months`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models`、`tests/test_write_operation_slo_audit.py::WriteOperationSloAuditTests::test_invoice_import_confirmed_profile_allows_direction_specific_relation_refresh` | covered |
| 2026-06-20 | 后台 import worker 的 `tax_offset` scope helper 未过滤 batch type，银行流水 `trade_time` 会被误算成税金抵扣月份并投递无关刷新。 | `tests/test_import_job_queue.py::ImportJobRepositoryTests::test_tax_offset_scope_helpers_ignore_bank_transaction_files` | covered |
| 2026-06-20 | 银行导入持久化路径只投递 `bank_detail`，未主动投递 `bank_account_balance`，账户余额页面只能依赖 API miss 被动补刷，`bank_import_confirmed` SLO 缺少真实事件来源。 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes`、`tests/test_write_operation_slo_audit.py::WriteOperationSloAuditTests::test_bank_import_confirmed_profile_fails_when_account_balance_scope_is_missing` | covered |
| 2026-06-20 | 历史 `import.fact.changed` 事件已 done，但 `import_facts_changed` dirty scope 仍 pending 且无 active outbox 可 claim，导致 App Status 卡同步中。 | `tests/test_read_model_scope_contract.py::ReadModelScopeContractServiceTests::test_check_reports_orphaned_import_fact_dirty_scopes_without_writes`、`test_apply_deletes_orphaned_import_fact_dirty_scopes_and_records_audit` | covered |
| 2026-06-21 | runtime ETC import link helper 若绕过 `upsert_etc_invoice` 的 link-existing 边界，重新调用 canonical invoice 创建 API，会让 ETC ZIP/OA 附件路径再次污染统一发票池。 | `tests/test_platform_runtime_boundary_guards.py::RuntimeWorkerEtcImportLinkExistingTests::test_runtime_etc_import_link_never_calls_canonical_invoice_create_api` | covered |
| 2026-06-21 | `workbench:all` aggregate-only 报 `parent_generation_inconsistent parent_scope_keys=...` 时，runtime worker 因同 scope type 跳过 dependency refresh，导致 all 事件 failed/dead-letter，parent month scope 不会被重建。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_requeues_same_scope_parent_when_generation_is_inconsistent` | covered |
| 2026-06-21 | Workbench `all` aggregate-only 在 parent month 未 fresh 时按 0.25s 快速 defer/republish，RabbitMQ 队列被 all 聚合事件重发淹没，真正的 parent month scope 长期 pending。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_requeues_same_scope_parent_when_generation_is_inconsistent` | covered |
| 2026-06-21 | 同一 read model scope 已有 active dirty scope 修复时，历史 failed outbox 仍进入 App Status current queue failed，导致“同步中”和“阻断”同时出现。 | `tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_ignores_failed_outbox_row_covered_by_active_dirty_scope` | covered |

## 关键 smoke flows

保留少量高价值 smoke，不做全量巨型 E2E：

1. `producer -> ReadModelRefreshGateway -> job.read_model_dirty_scopes/job.outbox_events -> RuntimeWorker -> ReadModelReadinessReporter -> App Health`
2. `RabbitMQ dispatcher -> persistent envelope publish -> consumer receives wakeup -> Postgres claim -> handler complete -> RabbitMQ ack`
3. `dead-letter event -> runtime_queue_ops inspect -> repair/requeue or guarded resolve -> readiness/App Health 收敛`
4. `新增 worker registration -> manifest CLI -> deploy env examples -> runtime monitoring required worker metrics`
5. `导入/ETC/关系变更 -> derived lifecycle -> affected read model scopes -> 页面 read model refreshing/fresh 状态`

## 本模块验证命令

本模块最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_worker_registry tests.test_runtime_queue tests.test_runtime_monitoring -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract tests.test_read_model_readiness_reporter -v
PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_runtime tests.test_runtime_queue_ops tests.test_runtime_state_policy tests.test_deploy_runtime_examples tests.test_runtime_redis -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_app_status_readiness_backfill -v
bash scripts/verify.sh docs
```

统一真实基础设施 gate：

```bash
bash scripts/verify.sh infra-smoke
```

本地没有 `FIN_OPS_TEST_DATABASE_URL` / `RABBITMQ_TEST_URL` 时，该命令验证 read model SLO、runtime sync closure gate、write-operation SLO、RabbitMQ staging preflight 工具合同，并跳过真实连接；配置真实 staging PostgreSQL 后会追加 `read_model_slo_smoke --critical-only` dry-run scope discovery。只有同时设置 `FIN_OPS_INFRA_SMOKE_APPLY=1` 时，才会追加 `--apply` 并真正 enqueue refresh events、等待 worker drain；配置 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed` 等 profile 后，会运行只读 `write_operation_slo_audit` 审计最近真实业务写入产生的 durable refresh events；配置真实 staging PostgreSQL/RabbitMQ 后还会运行 RabbitMQ staging preflight。

有真实基础设施时追加：

```bash
FIN_OPS_TEST_DATABASE_URL=postgresql://... PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_postgres_integration -v
RABBITMQ_TEST_URL=amqp://... PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_integration -v
FIN_OPS_TEST_DATABASE_URL=postgresql://... RABBITMQ_TEST_URL=amqp://... PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_staging_preflight -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight --json --skip-real-tests
FIN_OPS_TEST_DATABASE_URL=postgresql://... FIN_OPS_INFRA_SMOKE_APPLY=1 bash scripts/verify.sh infra-smoke
FIN_OPS_TEST_DATABASE_URL=postgresql://... FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会跑 backend unittest discover、frontend vitest/build 和 docs guard。默认夜间 CI 不依赖真实 Postgres/RabbitMQ URL；因此真实基础设施 smoke 属于 staging/手动 gate。

## 未测风险

- 当前默认 CI 不证明真实 RabbitMQ broker、真实 Postgres migration、systemd unit 和 worker 长时间 drain；`infra-smoke` 未设置 `FIN_OPS_INFRA_SMOKE_APPLY=1` 时也不证明直接 enqueue worker drain，未设置 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS` 时也不证明真实业务写入后的 durable refresh events。
- RabbitMQ 作为可选 transport 的端到端 broker 测试需要 `RABBITMQ_TEST_URL`，没有该环境变量时只能依赖 fake channel/consumer 测试。
- `resolve-dead-letter` 等运维命令的真实生产执行仍需 operator review 和 readiness 事实核对；测试只保护命令前置条件和 SQL 行为。
- 业务页面层面的 loading/stale/error 展示不在本模块完全覆盖，必须由具体页面模块补前端交互和关键业务流回归。
