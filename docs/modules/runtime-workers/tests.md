# Runtime Worker 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

Runtime worker 是全局后台执行面，修改前必须逐项确认影响范围：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| Worker 注册与启动 | `runtime_worker_registry.py`、`app/worker.py`、manifest CLI、deploy env examples | required worker 是否完整、`--registration --worker-instance --check` 是否继续输出 registry 派生配置、systemd env 是否覆盖所有 event type |
| Durable queue | `RuntimeQueueRepository`、`job.outbox_events` | enqueue/dedupe、claim、stale reclaim、complete、retry、dead-letter、publish 状态、operator resolution |
| Legacy read model dirty scope | 历史迁移记录 | `job.read_model_dirty_scopes` 与 `read_model.app_status_readiness` 已由 `0082_drop_legacy_read_model_runtime_state.sql` 删除；app/server、runtime handler、`RuntimeWorker` dependency-not-fresh fan-out、runtime queue read-model refresh methods 和 registry event parser 已删除 |
| Worker loop | `RuntimeWorker.run_once()`、handler registry | heartbeat、statement timeout、task timeout、retry delay、max attempts、无 handler 失败路径 |
| Readiness / App Health | `RuntimeMonitoringRepository` | legacy readiness 只读聚合、scope 级诊断、worker kind/event type mismatch；`ReadModelReadinessReporter` 写入链已删除 |
| RabbitMQ transport | `rabbitmq_runtime.py`、dispatcher/consumer/preflight | RabbitMQ 只传 envelope/wakeup，不携带业务 payload；Postgres 仍是事实源；ack 必须在 Postgres claim 成功后 |
| 运维命令 | `runtime_queue_ops` | inspect/requeue/replay/release-stale-processing/resolve-superseded-processing 必须保留审计和真实 runtime 前置条件；readiness backfill、scope-contract repair、readiness/dirty-scope dead-letter resolve 已删除 |
| 跨模块 fan-out | import、ETC、workbench matching、真实后台任务 | 新增真实后台事件不能绕过 registry；`ReadModelRefreshGateway`、runtime queue read-model refresh methods 和 page `.read_model.refresh` parser 已删除，旧页面不能读取 stale projection 伪装 fresh |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| Worker 从 Postgres claim event 并 complete | P0 | `tests/test_runtime_worker.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_infrastructure_postgres_integration.py` | covered | 覆盖内存 fake 与真实 Postgres integration。 |
| Handler 失败进入 retry / dead-letter | P0 | `tests/test_runtime_worker.py`、`tests/test_runtime_queue.py` | covered | 覆盖 retry delay、max attempts、processing lock。 |
| Handler 遇到依赖 read model 未 fresh 时短延迟 defer | P0 | `tests/test_runtime_worker.py`、`tests/test_runtime_queue.py` | covered | `*_read_model_not_fresh` / `read_model_not_fresh` 不走普通失败/dead-letter，也不再补投 dependency refresh；只短延迟回 pending，等待 direct/legacy 残留路径自行收敛或后续删除。 |
| Same-scope parent shard 未 fresh / inconsistent 时只 defer | P0 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_defers_same_scope_parent_inconsistent_without_dependency_refresh` | covered | `workbench_read_model_not_fresh: parent_generation_inconsistent parent_scope_keys=...` 不再解析 parent scope 或补投 parent month scope；当前行为只按 dependency-not-fresh delay defer 当前事件，并且 heartbeat 不携带 `dependency_refreshes`。 |
| defer 遇到同 dedupe pending 覆盖事件 | P0 | `tests/test_runtime_queue.py` | covered | 当前 processing 事件标记 done + `runtime_defer_superseded`，避免唯一冲突导致 worker 崩溃并等待 300s lock timeout。 |
| defer 遇到旧 done 事件 source_version 更高 | P0 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_does_not_let_older_done_event_cover_newer_processing_event` | covered | 覆盖事件必须比当前 processing event 更新；旧 done 事件不能把新导入产生的 dirty scope 对应事件错误标记 superseded。 |
| 无 handler / 无 event type 不误 claim | P0 | `tests/test_runtime_worker.py` | covered | 防止 worker 注册错误时吞事件。 |
| Heartbeat 写入与 required worker mismatch | P0 | `tests/test_runtime_worker.py`、`tests/test_runtime_monitoring.py`、`tests/test_runtime_worker_registry.py` | covered | 覆盖 instance、kind、event type mismatch。 |
| 高频 read model 专用 consumer | P0 | `tests/test_runtime_worker_registry.py` | covered | `pending-invoice`、`cost-statistics`、`tax-offset`、`invoice-lifecycle` / `invoice-lifecycle-secondary` read-model consumers 已删除；剩余 worker 必须由 registry/env/App Status/RabbitMQ dispatch 同源推导，避免旧 read model lane 回流。 |
| Registry / manifest / deploy env 同步 | P0 | `tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_postgres_migrations.py`、`tests/test_runtime_redis.py`、`tests/test_runtime_convergence_closure.py` | covered | 防止真实 worker 或 legacy read model 变更只改一处：未下线的 App Status read model 必须匹配 required worker、RabbitMQ dispatch event、migration storage contract 和 Redis/env 模板；worker read-model registration 也必须反向出现在 App Status/manifest/policy。 |
| Read model refresh scope 归一化、校验、去重 | P0 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_read_model_refresh_gateway_is_removed` | covered | 当前 active page read-model registry 为空；`ReadModelRefreshGateway`、runtime queue read-model refresh methods、registry `read_model_event_types()` 和 scope-contract repair 服务已删除。 |
| Readiness reporter 写入链已删除 | P0 | `tests/test_app_status_overview_service.py` | covered | worker 不再通过 reporter 写 `read_model.app_status_readiness`；测试保护 runtime repository 不再提供 readiness 写入口。 |
| App Health runtime snapshot | P0 | `tests/test_runtime_monitoring.py`、`tests/test_app_health_api.py`、`tests/test_app_status_overview_service.py` | covered | 覆盖 backlog、failed job、worker metrics，并断言 health/App Status 不再读取 dirty scope/readiness。 |
| RabbitMQ envelope 不包含业务 payload | P0 | `tests/test_runtime_queue.py`、`tests/test_rabbitmq_runtime.py`、`tests/test_runtime_infrastructure_postgres_integration.py` | covered | RabbitMQ 只可承载 routing identity/version。 |
| RabbitMQ dispatcher publish confirm 后才 mark published | P0 | `tests/test_rabbitmq_runtime.py` | covered | 防止未确认 publish 被标记成功。 |
| RabbitMQ consumer 先 claim Postgres 再 ack | P0 | `tests/test_rabbitmq_runtime.py` | covered | 防止 RabbitMQ 消息成功但 Postgres 事实未锁定。 |
| Transactional dirty/outbox writer scope contract | P1 | `tests/test_runtime_queue.py`、`tests/test_postgres_repositories_boundaries.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_workbench_uow_contract.py` | covered | 事务内 writer 必须在同一 transaction 写 dirty/outbox，保持 source_version/dedupe/payload contract，并且 custom transactional writer 产出的 scope 必须通过共享 scope policy registry。 |
| Runtime queue ops inspect/requeue/replay/release/superseded | P1 | `tests/test_runtime_queue_ops.py` | covered | 保留真实 outbox/RabbitMQ 运维入口；`resolve-dead-letter` / `resolve-covered-dead-letters` 已删除并有负向测试。 |
| RabbitMQ transport 下 stale/superseded processing 处理 | P1 | `tests/test_runtime_queue.py`、`tests/test_runtime_queue_ops.py` | covered | 可重新处理的 stale `processing` 释放回 pending；已被更新同 dedupe event 覆盖的旧 `processing` 走 superseded resolution；两者都写 operator audit，不伪造 fresh。 |
| Runtime state policy / legacy snapshot boundary | P1 | `tests/test_runtime_state_policy.py`、`tests/test_runtime_bootstrap.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | 防止 worker 或生产 bootstrap 回退到 Application/full snapshot。 |
| 真实 RabbitMQ topology publish/consume | P1 | `tests/test_rabbitmq_integration.py`、`tests/test_rabbitmq_staging_preflight.py` | documented-risk | 需要 `RABBITMQ_TEST_URL`；本地/nightly 默认可 skip；staging preflight 缺 `FIN_OPS_TEST_DATABASE_URL` / `RABBITMQ_TEST_URL` 时返回 `configuration_missing`，不当作实现失败。 |
| 真实 Postgres migration + queue integration | P1 | `tests/test_runtime_infrastructure_postgres_integration.py` | documented-risk | 需要 `FIN_OPS_TEST_DATABASE_URL`；无环境时 skip。 |
| 真实 systemd worker drain / 长时间运行 | P2 | `docs/operations/runtime-worker-governance.md` runbook | documented-risk | 需要 staging/生产环境，不作为本地单元测试前置。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_runtime_queue.py`、`tests/test_runtime_state_policy.py`、scope/manifest architecture guards | Queue 状态流转、scope contract、runtime state cleanup policy 都属于后台业务规则；deleted gateway 不再有正向单测。 |
| 2. Service-layer tests | 适用 | `tests/test_runtime_worker.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_runtime_monitoring.py`、`tests/test_runtime_queue_ops.py`、`tests/test_rabbitmq_staging_preflight.py` | 覆盖 worker orchestration、repository 写入、monitoring、ops 命令前置条件和 staging preflight 环境门禁。 |
| 3. API contract tests | 间接适用 | `tests/test_app_health_*`、`tests/test_runtime_monitoring.py` | 本模块自身不暴露普通业务 API；通过 App Health/runtime snapshot 保护响应事实。若改 `/health` 或 `/api/app-health` shape，必须补 API contract test。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_app_status_overview_service.py` | 覆盖 dirty scope 兼容面和 readiness 写入口删除；readiness backfill、reporter 与 health/App Status read side 已删除。 |
| 5. Frontend component and interaction tests | 间接适用 | `web/src/test/AppHealth*.test.tsx` | 修改 App Health 展示、loading/stale/error 语义时必须补前端交互测试；纯 worker 内部改动不适用。 |
| 6. End-to-end business-flow integration tests | 按需适用 | `tests/test_runtime_infrastructure_postgres_integration.py`、`tests/test_rabbitmq_integration.py`、`tests/test_rabbitmq_staging_preflight.py`、各业务模块 smoke | 修改跨模块事件或 worker fan-out 时，至少补一个关键业务流 integration/regression test；缺真实 staging env 只能证明 preflight contract，不能证明 broker drain。 |
| 7. Existing feature regression tests | 适用 | `tests/test_platform_runtime_boundary_guards.py`、`tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py` | 防止新增真实 worker/event type 或 legacy read model 下线/变更破坏旧 registry、deploy、auth/Application 边界。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-25 | `WorkbenchMatchingWorkerFactory` 仍按旧合同向 `WorkbenchMatchingOrchestrator` 传 `pair_relation_service=`，而 orchestrator 已迁移到 `relation_read_port`，导致生产 `fin-ops-worker@workbench-matching.service` 启动即 `TypeError` 并进入 systemd restart loop。 | `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_workbench_matching_uses_relation_read_port_not_pair_service` | covered |
| 2026-06-22 | Workbench active repair 已在运行，但 App Health 聚合旧 generation consistency failure 时仍写入 `workbench_read_model` unavailable dependency，导致运行摘要 yellow/refreshing 和顶部 red/blocked 同时出现。 | `tests/test_app_health_api.py::AppHealthApiTests::test_app_health_keeps_workbench_consistency_failure_busy_during_active_repair`、`tests/test_app_status_overview_service.py` | covered |
| 2026-06-22 | 生产 schema/worker/RabbitMQ/Redis 已有单独测试，但没有跨 registry 门禁；新增 read model 可能只更新 App Status 或 worker registry，漏掉 migration storage contract 或 deploy env，导致本地测试通过、生产运行面缺 worker/schema/transport/cache 配置。 | `tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_app_status_read_model_registry_matches_worker_and_rabbitmq_contracts`、`tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_app_status_read_model_storage_contracts_are_declared`、`tests/test_deploy_runtime_examples.py::DeployRuntimeExampleTests::test_shared_rabbitmq_worker_env_does_not_switch_all_workers_to_rabbitmq`、`tests/test_runtime_redis.py::RuntimeRedisTests::test_production_env_examples_match_runtime_redis_settings_contract` | covered |
| 2026-06-10 | Worker lifecycle 曾向 `cost_statistics.read_model.refresh` 投递裸月份/裸 `all`，SQL projection 拒绝 scope。 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_manifest.py`、`tests/test_read_model_architecture_guards.py` | covered；`ReadModelRefreshGateway` 和 scope-contract repair 服务已删除 |
| 2026-06-10 | 非事务 producer 可能绕过 shared scope boundary 直接调用 `RuntimeQueueRepository.enqueue_read_model_refresh(...)`。 | `tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_runtime_queue_read_model_refresh_methods_are_removed`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_read_model_refresh_gateway_is_removed` | covered；app/server、runtime handler、RuntimeWorker generic gateway 和 runtime queue read-model refresh methods 已删除 |
| 2026-06-11 | 静态 boundary guard 误把 OA 登录 JSON 响应字段 `Admin-Token` 判定为 service 解析 HTTP cookie/header。 | `tests/test_platform_runtime_boundary_guards.py::test_services_do_not_import_http_auth_boundary_or_parse_cookie_token_headers`、`tests/test_target_oa_applicant_token_provider.py` | covered |
| 2026-06-13 | downstream read model 依赖 source read model 尚未 fresh 时，被普通 retry 放大成 60s+ 等待甚至 dead-letter。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_defers_dependency_not_fresh_without_marking_failed`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_delays_dependency_retry_without_failure_or_dead_letter` | covered |
| 2026-06-13 | `defer_event` 把 processing 事件改回 pending 时，如果同 dedupe 已有 pending 新事件，会触发唯一索引冲突并使 worker 崩溃，事件卡到 lock timeout。旧多写 CTE 仍可能执行 pending 分支；当前回归要求覆盖事件存在时只执行 superseded resolve 分支，并且并发 pending 在预查后提交时用 `23505` fallback 二次 resolve。 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_resolves_current_processing_when_pending_same_dedupe_exists`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_resolves_unique_collision_from_concurrent_pending_cover` | covered |
| 2026-06-13 | RabbitMQ worker 只消费 envelope，PostgreSQL 旧 `processing` 行没有对应消息时不会被普通消费自动 reclaim，导致 source read model 长时间 not fresh。 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_release_stale_processing_events_requeues_with_operator_audit`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_resolve_superseded_processing_events_marks_obsolete_processing_done`、`tests/test_runtime_queue_ops.py::RuntimeQueueOpsTests::test_release_stale_processing_dry_run_lists_candidates_without_update` | covered |
| 2026-06-28 | `cost-tax`、`cost-statistics`、`tax-offset`、`invoice-lifecycle` 和 `invoice-lifecycle-secondary` read-model worker lane 已删除；真实 confirm/withdraw 后不再以 read model enqueue-to-done 作为页面验收。 | `tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_cost_tax_read_model_workers_are_removed`、`tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_invoice_lifecycle_read_model_workers_are_removed` | covered |
| 2026-06-14 | 生产 systemd 模板未显式传 `--dependency-not-fresh-delay-seconds`，只能使用代码默认 2s，关系 fan-out 依赖链固定等待偏长。 | `tests/test_deploy_oa_script.py::DeployOaScriptTests::test_systemd_worker_template_uses_registry_registration_contract` | covered |
| 2026-06-14 | 真实 confirm/withdraw 在 1s dependency defer 与两条 search lane 下，`pending_invoice` dependency retry 和快速 withdraw 的第二个 search scope 仍可能超过 5s。 | `tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_hot_read_model_workers_have_dedicated_parallel_consumers`、`tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_defers_dependency_not_fresh_without_marking_failed`、`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_delays_dependency_retry_without_failure_or_dead_letter` | covered |
| 2026-06-14 | 历史：dependency-not-fresh 补投依赖时，如果依赖 refresh outbox 已经 pending/processing，会 bump 新 source_version 并把等待者继续推迟。当前 `RuntimeWorker` 已删除 dependency refresh enqueue/active/fresh 探测，只 defer 当前事件。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_probe_dependency_refresh_active_state`、`tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_probe_dependency_refresh_fresh_state`、`tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_runtime_worker_dependency_refresh_gateway_does_not_return` | covered |
| 2026-06-21 | dependency dirty scope orphan 但 outbox 已 done/缺失时，worker 误判依赖 active，不再补投上游 refresh，导致 downstream read model 长期 refreshing。 | `tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_runtime_queue_read_model_refresh_methods_are_removed`、runtime worker defer tests | covered；orphan repair helper 和 runtime queue read-model active/fresh probes 已删除 |
| 2026-06-14 | 历史 projection/facade 的 ensure refresh reason 在依赖 read model 已 active 时仍通过 gateway 入队，覆盖真实写入 reason 并持续 bump source_version，导致 `pending_invoice` 写后收敛 40s+。 | historical deleted gateway tests；当前回归由 gateway deletion guards、runtime worker defer tests 和 direct API guards 覆盖 | history-only；当前 app/server、runtime handler 和 RuntimeWorker generic page refresh producer 已删除 |
| 2026-06-28 | `bank_detail` read-model runtime 删除后，registry/manifest/AppStatus/deploy/producer/repository 不得回流；下游标签读取必须走 direct effective category provider。 | `tests/test_bank_details_sql_runtime.py`、`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py`、`tests/test_platform_runtime_boundary_guards.py` | covered |
| 2026-06-14 | 历史：`invoice_lifecycle` refresh worker 缺少 source_version current guard 时，快速 confirm/withdraw 可能让旧版本事件继续重建；该 worker lane 现已删除。Workbench 同步 Redis warmup 曾进入 refresh ack 前热路径，导致连续写入第二个 workbench event 超过 5s。 | `tests/test_invoice_lifecycle_derived_lifecycle_executor.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_platform_runtime_boundary_guards.py` | history-only for invoice lifecycle；当前回归由 direct API/negative registry guards、SQL runtime 与平台边界 guard 覆盖 |
| 2026-06-14 | 历史：`bank_detail` source_version guard 缺失会放大等待。 | 旧 worker 已删除；当前以 direct provider 和 negative registry guards 防止该 runtime 回流。 | history-only |
| 2026-06-15 | Workbench month shard 发布后投递的 `all` aggregate-only 事件使用 shard source_version；如果继续按 all dirty scope source_version 做 stale guard，事件会被跳过，或者 aggregate 未发布仍被标记 done，导致 all generation 长期停留在旧污染版本。 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_runs_all_aggregate_after_shard_publish_even_if_all_scope_source_is_newer`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_does_not_complete_dirty_scope_when_all_aggregate_did_not_publish` | covered |
| 2026-06-20 | 发票导入后新 `processing` refresh event 被同 dedupe 的历史 `done` event 覆盖，`runtime_defer_superseded` 把事件置 done，但当前 dirty scope 仍 pending/refreshing，App Status 长时间不收敛。 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_does_not_let_older_done_event_cover_newer_processing_event` | covered |
| 2026-06-20 | 历史：`import.fact.changed` 与 bank_detail refresh 的兼容链路可能重刷历史月份。 | `tests/test_import_job_queue.py::ImportJobRepositoryTests::test_import_fact_changed_handler_completes_matching_dirty_scope`、`tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot`、`tests/test_import_processing_service.py::test_general_import_confirm_uses_direct_bank_detail_without_refresh_scope` | covered；bank_detail refresh 已下线 |
| 2026-06-20 | 发票导入后台 worker 对进项/销项方向页固定双刷，input-only/output-only 文件会刷新无关 read model，放大导入后同步尾延迟。 | `tests/test_import_job_queue.py::ImportJobRepositoryTests::test_invoice_relation_scope_helpers_split_input_and_output_file_months`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models`、`tests/test_write_operation_slo_audit.py::WriteOperationSloAuditTests::test_invoice_import_confirmed_profile_allows_direction_specific_relation_refresh` | covered |
| 2026-06-20 | 后台 import worker 的 `tax_offset` scope helper 未过滤 batch type，银行流水 `trade_time` 会被误算成税金抵扣月份并投递无关刷新。 | `tests/test_import_job_queue.py::ImportJobRepositoryTests::test_tax_offset_scope_helpers_ignore_bank_transaction_files` | covered |
| 2026-06-20 | 历史：银行导入持久化路径只投递 `bank_detail`/未投递账户余额。 | `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_does_not_enqueue_bank_detail_for_transaction_month_scopes`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | covered；银行明细/账户余额 direct API 不再需要 read-model refresh |
| 2026-06-20 | 历史 `import.fact.changed` 事件已 done，但 `import_facts_changed` dirty scope 仍 pending 且无 active outbox 可 claim，导致 App Status 卡同步中。 | scope-contract repair tests 已删除；当前以 direct API 不依赖页面 read-model dirty scope、runtime queue active check 和后续 cleanup wave 处理 | legacy-residue |
| 2026-06-21 | runtime ETC import link helper 若绕过 `upsert_etc_invoice` 的 link-existing 边界，重新调用 canonical invoice 创建 API，会让 ETC ZIP/OA 附件路径再次污染统一发票池。 | `tests/test_platform_runtime_boundary_guards.py::RuntimeWorkerEtcImportLinkExistingTests::test_runtime_etc_import_link_never_calls_canonical_invoice_create_api` | covered |
| 2026-06-21 | 历史：`workbench:all` aggregate-only 报 `parent_generation_inconsistent parent_scope_keys=...` 时，runtime worker 曾尝试补投 parent month scope。当前 Workbench page read-model lane 已删除，`RuntimeWorker` 不再解析 parent scopes 或补投 page refresh。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_defers_same_scope_parent_inconsistent_without_dependency_refresh`、`tests/test_read_model_architecture_guards.py::ReadModelArchitectureGuardTests::test_runtime_worker_dependency_refresh_gateway_does_not_return` | covered |
| 2026-06-21 | 历史：Workbench `all` aggregate-only 在 parent month 未 fresh 时按 0.25s 快速 defer/republish，RabbitMQ 队列被 all 聚合事件重发淹没。当前测试只保护 dependency-not-fresh short defer 和无 dependency enqueue payload。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_defers_same_scope_parent_inconsistent_without_dependency_refresh` | covered |
| 2026-06-21 | 同一 read model scope 已有 active dirty scope 修复时，历史 failed outbox 仍进入 App Status current queue failed，导致“同步中”和“阻断”同时出现。 | 2026-06-28 health/App Status 已删除 active dirty scope/readiness 覆盖输入；当前只保留 outbox current-effective 过滤。 | covered |

## 关键 smoke flows

保留少量高价值 smoke，不做全量巨型 E2E：

1. `legacy runtime queue compatibility -> page .read_model.refresh producer/parser 不得回流 -> direct API reload 或真实后台 outbox event`
2. `RabbitMQ dispatcher -> persistent envelope publish -> consumer receives wakeup -> Postgres claim -> handler complete -> RabbitMQ ack`
3. `dead-letter event -> runtime_queue_ops inspect -> repair/requeue or记录 legacy residue -> direct API 验证`
4. `新增 worker registration -> manifest CLI -> deploy env examples -> runtime monitoring required worker metrics`
5. `导入/ETC/关系变更 -> derived lifecycle -> affected scopes/backend diagnostics -> 页面 direct reload/unavailable 状态`

## 本模块验证命令

本模块最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_worker_registry tests.test_runtime_queue tests.test_runtime_monitoring -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_architecture_guards tests.test_app_status_overview_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_runtime tests.test_runtime_queue_ops tests.test_runtime_state_policy tests.test_deploy_runtime_examples tests.test_runtime_redis -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_app_status_overview_service -v
bash scripts/verify.sh docs
```

统一真实基础设施 gate：

```bash
bash scripts/verify.sh infra-smoke
```

本地没有 `FIN_OPS_TEST_DATABASE_URL` / `RABBITMQ_TEST_URL` 时，该命令验证 runtime sync closure gate、write-operation SLO、RabbitMQ staging preflight 工具合同，并跳过真实连接；配置 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed` 等 profile 后，会运行只读 `write_operation_slo_audit` 审计最近真实业务写入产生的 durable outbox events；配置真实 staging PostgreSQL/RabbitMQ 后还会运行 RabbitMQ staging preflight。

有真实基础设施时追加：

```bash
FIN_OPS_TEST_DATABASE_URL=postgresql://... PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_postgres_integration -v
RABBITMQ_TEST_URL=amqp://... PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_integration -v
FIN_OPS_TEST_DATABASE_URL=postgresql://... RABBITMQ_TEST_URL=amqp://... PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_staging_preflight -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight --json --skip-real-tests
FIN_OPS_TEST_DATABASE_URL=postgresql://... FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会跑 backend unittest discover、frontend vitest/build 和 docs guard。默认夜间 CI 不依赖真实 Postgres/RabbitMQ URL；因此真实基础设施 smoke 属于 staging/手动 gate。

## 未测风险

- 当前默认 CI 不证明真实 RabbitMQ broker、真实 Postgres migration、systemd unit 和 worker 长时间运行；未设置 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS` 时也不证明真实业务写入后的 durable outbox events。
- RabbitMQ 作为可选 transport 的端到端 broker 测试需要 `RABBITMQ_TEST_URL`，没有该环境变量时只能依赖 fake channel/consumer 测试。
- `requeue`、`release-stale-processing`、`resolve-superseded-processing` 等运维命令的真实生产执行仍需 operator review；测试只保护命令前置条件和 SQL 行为。
- 业务页面层面的 loading/stale/error 展示不在本模块完全覆盖，必须由具体页面模块补前端交互和关键业务流回归。
