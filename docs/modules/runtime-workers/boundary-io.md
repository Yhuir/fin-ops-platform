# Runtime Worker 模块边界与 I/O

日期：2026-07-06

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：所有后台 worker 由 registry、durable queue、handler 和部署 manifest 显式声明。
- 当前闭环：worker 入口使用 registration contract；worker instance、event type、claim scope lane、env example、manifest/check command 和 App Health readiness 均由 `runtime_worker_registry.py` 派生。`workbench.read_model.refresh` 已按 `scope_key` 拆成月份 shard lane 与显式 `all` aggregate 维护 lane；普通写后可见性走月份 shard + query-composed all，避免慢聚合阻塞首屏月份刷新。部署文档不再维护手写 worker 矩阵或 `sudo systemctl enable --now fin-ops-worker@...` 清单。
- 性能证据风险：高性能全域闭环仍需要生产 SLO 复测证明所有页面/读写操作 p95 收敛；该风险属于运行证据，不再代表 Runtime Worker 边界或 I/O open。
- 旧代码删除状态：旧 `worker_legacy_application` / `RuntimeWorkerApplicationBridge` / GridFS migration worker / 手写生产 worker 矩阵已移除；本轮删除无调用 `_handle_import_fact_changed_event` wrapper 与 `required_worker_dependency(...)` 死 helper。

## 职责边界

### 负责

- Runtime queue、worker registry、worker handler、worker health/readiness。
- 把 durable queue 中的 outbox/read model event 分发给对应 worker。
- 为部署和 app health 暴露 worker 实例合同。

### 不负责

- 不拥有业务源事实。
- 不直接知道 HTTP cookie/header 或 Flask response。
- 不绕过 service/repository 边界写业务表。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Outbox/job event | PostgreSQL durable queue | event type 必须在 registry 中登记。read model refresh metadata 只允许白名单字段进入 outbox；操作级 `row_ids` / `case_ids` 只能作为 worker 局部投影提示，不能替代 dirty scope/source_version 事实源；`force_refresh=true` 仅用于显式运维重建并强制 full projection；同 scope pending event 合并时必须删除 row 级 metadata 并让 handler full rebuild |
| Refresh availability timestamp | `job.outbox_events.available_at` | write-operation / read-model refresh SLO 以 `available_at -> processed_at` 衡量 enqueue-to-done；事务内 writer 必须用 `clock_timestamp()` 写实际入队可处理时间，不能让 transaction-level `now()` 把业务写事务耗时计入 worker drain；同 scope pending refresh 被新 source_version 合并时，active outbox event 的 `created_at`/`updated_at` 也必须重置为当前 enqueue 时间，避免兼容报表继续读到旧 pending 年龄 |
| Worker instance env | deploy/systemd | 生产 systemd 必须传 `--registration <instance>` 与 `--worker-instance <instance>`；instance name、event types、claim scope filters 与 handler flags 由 registry 派生。PostgreSQL durable queue worker 的默认 idle poll 为 `0.05s`，`workbench` 月分片热 lane 使用 `0.01s`，`workbench-aggregate` 使用 `0.05s` idle poll 与 `FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=4` 小批量 drain；历史 `--poll-interval-seconds 2`、`0.25`、`0.1`、`0.05` 只允许由 deploy helper 精确迁移到当前 release env 示例声明值，不能重新作为 read model worker 默认值 |
| Claim scope filter | worker registry / worker env | 只用于同一 event type 下拆分 worker lane；`workbench` worker 必须 `--exclude-claim-scope-key all`，`workbench-aggregate` worker 必须 `--claim-scope-key all`。scope contract 仍由 read model scope policy 负责，不能把业务 scope 规则塞进 queue 层 |
| Workbench all aggregate scheduling | `WorkbenchReadModelRefreshService` | 普通月分片 refresh 完成后不再自动投递 `workbench:all` aggregate；relation 写入产生的 `workbench_relation_changed` 也只要求受影响 month shard 和下游 read model 收敛。只有 event payload 显式声明 `publish_all_aggregate=true` 的 rebuild/repair/backfill 才可投递 `all` aggregate 到 `workbench-aggregate` lane；该 lane 不得进入写事务，也不得成为普通写后可见性、freshness gate 或 operation barrier 的必要条件 |
| Workbench dependent publish | `WorkbenchReadModelRefreshService` | `cost_statistics` 直接消费 Workbench 月度 active generation。月分片 projection commit 后，handler 必须在完成 Workbench dirty scope 前通过 `ReadModelRefreshGateway` 入队该月份的 active/all 成本 scope；入队失败使当前 handler 失败并重试，禁止出现 Workbench 已标 fresh、成本仍停留在旧 generation 且 queue drained。materialized `workbench:all` 不属于成本输入，不触发该 fan-out |
| Relation-dependent invoice publish | `InvoiceUsageCollectionSqlProjectionBuilder` / runtime worker | input/output invoice projection 读取共享 relation scope 前必须通过 `workbench_relation` freshness gate；关系 scope pending/processing/stale 时抛出 `workbench_relation_read_model_not_fresh` 并由 worker 短延迟 defer，禁止把并行 claim 的旧 relation source versions 写成 fresh。 |
| Claim hot path index | PostgreSQL migration | `job.outbox_events` active queue claim 必须保留 event-type-first 索引 `outbox_events_claim_event_type_priority_idx`，覆盖 `event_type/status/priority rank/available_at/created_at/id`；该索引只优化 worker lane claim I/O，不改变 durable queue 状态机、priority 语义或 freshness/readiness 事实源 |
| Handler call | runtime worker | handler 只处理登记 event type |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Job result/status | runtime queue/app health | 成功、失败、重试和 readiness 可观察；影响 read model 的 job completion result summary 必须携带 target envelope 或明确不适用 |
| Fan-out parent result | readiness / app health | manifest 为 `fan_out_command` 的 command-only `all` parent 只负责入队 child scopes，不写 current readiness；parent event/dirty scope 的当前失败仍可观察，历史 readiness 只作为 diagnostics。真实 queryable all scope（当前 `bank_account_balance:all`）和 queryable parent 不适用该忽略规则。 |
| Worker heartbeat | `job.runtime_worker_heartbeats` | 空轮询 `idle` heartbeat 必须节流，禁止每个 0.05s poll 同步写库；`processing`、`deferred`、`failed`、`stopping`、`stopped` 等事件状态必须即时写入 |
| Read model projection | 对应 repository | 只写 worker 对应投影 |
| Wakeup/transport | RabbitMQ 可选 | 不能作为状态事实源 |
| Queue history retention result | runtime queue ops / deploy timer | 只删除 `done` 历史；输出按 outbox event type 与 dirty scope type 聚合的 candidate/deleted count |

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Runtime queue | `backend/src/fin_ops_platform/services/runtime_queue.py` |
| Runtime queue migrations | `backend/src/fin_ops_platform/postgres/migrations/*runtime_queue*.sql` |
| Worker registry | `backend/src/fin_ops_platform/services/runtime_worker_registry.py` |
| Worker runtime | `backend/src/fin_ops_platform/services/runtime_worker.py`、`runtime_worker_handlers.py` |
| App worker entry | `backend/src/fin_ops_platform/app/worker.py` |
| Queue ops | `backend/src/fin_ops_platform/tools/runtime_queue_ops.py` |
| RabbitMQ | `backend/src/fin_ops_platform/app/rabbitmq_dispatcher.py`、`rabbitmq_topology.py`、`services/rabbitmq_runtime.py` |
| Deploy | `deploy/oa/systemd/*.service.example`、`deploy/oa/env/*.env.example`、`deploy/oa/bin/finops-ensure-runtime-workers.sh`、`deploy/oa/bin/finops-prune-runtime-queue-history.sh` |
| Tests | `tests/test_runtime_worker*.py`、`tests/test_runtime_queue*.py`、`tests/test_rabbitmq_*.py` |

## 依赖方向

- 允许依赖：runtime queue repository、registered handlers、read model projection services。
- 必须通过：runtime worker registry。
- 禁止绕过：worker import `Application`、`app.server`、`app.auth`、HTTP response/status objects。

## 测试与验证

- `tests/test_runtime_worker_registry.py`
- `tests/test_runtime_worker.py`
- `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_passes_claim_scope_filters_to_queue`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_runtime_queue.py`
- `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_claim_next_can_filter_scope_keys_for_split_worker_lanes`
- `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_claim_event_by_id_honors_scope_filters_for_rabbitmq_consumers`
- `tests/test_deploy_runtime_examples.py`
- `tests/test_deploy_runtime_examples.py::DeployRuntimeExampleTests::test_workbench_workers_split_month_shards_from_all_scope_aggregate`
- `tests/test_deploy_runtime_examples.py::DeployRuntimeExampleTests::test_required_worker_env_examples_do_not_pin_legacy_slow_poll_interval`
- `tests/test_deploy_runtime_examples.py::DeployRuntimeExampleTests::test_runtime_worker_docs_use_registry_manifest_instead_of_manual_matrix`
- `tests/test_runtime_worker.py::RuntimeWorkerTests::test_default_poll_interval_is_fast_enough_for_read_model_slo`
- `tests/test_runtime_worker.py::RuntimeWorkerTests::test_fast_empty_polls_throttle_idle_heartbeat_writes`
- `tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_all_expected_migration_files_exist`
- `tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_runtime_queue_claim_hot_path_index_is_declared`

## 当前缺口和删除条件

- 新增 worker 必须同步 registry、manifest/systemd env、tests、docs。
- 移除 worker 前必须证明 deploy、queue event、RabbitMQ dispatch 和 app health 不再引用。
- 生产 env 示例仍可保留 `--enable-*` flag 作为本地开发和迁移期兼容参数；生产 systemd 主合同是 `--registration`，且 `_apply_registration_args(...)` 会由 registry 写入 handler flags、event types 和 scope lane。后续若要删除 env 示例里的兼容 flags，应单独迁移现有服务器 env 文件，避免扩大本次边界 close 的行为面。
- `0086_runtime_queue_claim_hot_path.sql` 已本地保护，仍需生产发布后用 grouped 1s read model smoke 证明 Workbench/invoice lifecycle 总耗时是否真正低于目标。
