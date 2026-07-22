# Runtime Worker 模块边界与 I/O

日期：2026-07-23

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：所有后台 worker 由 registry、durable queue、handler 和部署 manifest 显式声明。
- 当前闭环：worker 入口使用 registration contract；worker instance、event type、env example、manifest/check command 和 App Health readiness 均由 `runtime_worker_registry.py` 派生。单一 `workbench` instance 同时 claim 月份 shard 与 `all` fan-out command；普通写后可见性走月份 shard + query-composed all，不存在全局 aggregate publish。OA 待付款由 `oa-pending-payment` 专属实例 claim `oa_pending_payment.read_model.refresh`，共享 `invoice-usage-collection` 只保留进项使用/销项收款。外部往来只保留单一 `turnover-ledger` owner；已证实无收益且引入数据库竞争的 secondary 实验已删除。部署文档不再维护手写 worker 矩阵或 `sudo systemctl enable --now fin-ops-worker@...` 清单。
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
| Outbox/job event | PostgreSQL durable queue | event type 必须在 registry 中登记。read model refresh metadata 只允许白名单字段进入 outbox；操作级 `row_ids` / `case_ids` 只能作为 worker 局部投影提示，`relation_deltas + row_ids` 才能授权 relation-only delta，均不能替代 dirty scope/source_version 事实源；`force_refresh=true` 仅用于显式运维重建并强制 full projection。支持 fan-out 的 handler 必须把 force 传播给每个具体 shard。`invoice-usage-collection` 只处理进项使用/销项收款；`oa-pending-payment` 只处理 OA 待付款，二者不得互相 claim。OA 普通业务事件只用精确月份，显式 `all` 为低优先级 fan-out。同 scope pending 事件合并时必须删除 row 级 metadata并让 handler full rebuild；禁止保留不完整 delta却继续局部发布 |
| Refresh availability timestamp | `job.outbox_events.available_at` | write-operation / read-model refresh SLO 以 `available_at -> processed_at` 衡量 enqueue-to-done；事务内 writer 必须用 `clock_timestamp()` 写实际入队可处理时间，不能让 transaction-level `now()` 把业务写事务耗时计入 worker drain；同 scope pending refresh 被新 source_version 合并时，active outbox event 的 `created_at`/`updated_at` 也必须重置为当前 enqueue 时间，避免兼容报表继续读到旧 pending 年龄 |
| Worker instance env | deploy/systemd | 生产 systemd 必须传 `--registration <instance>` 与 `--worker-instance <instance>`；instance name、event types、claim scope filters 与 handler flags 由 registry 派生。激活 release 时，已启用、运行或失败但不在当前 registry 中的 `fin-ops-worker@*.service` 必须先被 stop/disable，禁止 WIP/历史实例继续消费队列或 crash-loop；该收敛不删除 env 文件，保留受控回滚能力。PostgreSQL durable queue worker 的默认 idle poll 为 `0.05s`，`workbench` 使用 `0.01s`；历史 `--poll-interval-seconds 2`、`0.25`、`0.1`、`0.05` 只允许由 deploy helper 精确迁移到当前 release env 示例声明值。OA worker 拆分时，helper 还必须幂等删除既有 `invoice-usage-collection` env 中精确命中的 OA handler/event 参数，禁止旧 env 重新扩张 registry claim 边界 |
| Worker PostgreSQL statement timeout | worker env / `RuntimeQueueRepository` | worker 入口必须在构造专用 polling worker 前把 registration 的 `FIN_OPS_WORKER_STATEMENT_TIMEOUT_SECONDS` 应用到共享 PostgreSQL connection；不能只依赖通用 `RuntimeWorker` 初始化，否则 `workbench-matching` 这类独立 dirty-scope worker 会静默退回 10 秒默认值。 |
| Workbench matching source versions | matching worker / matching orchestrator | 只包含会改变确定性正式关系结果的规则、OA、附件解析、银行标签和异常版本；`workbench_read_model_schema_version` 属于展示投影 owner，不得进入 matching stale-scan 输入。展示 schema 升级只通过正式 Workbench refresh/rehydrate 发布，不得无关重算全部历史 matching scope。 |
| Claim scope filter | worker registry / worker env | 只用于确有当前吞吐隔离需求的同 event type worker；Workbench 不拆 lane，单一 `workbench` registration claim 月份与 `all`。scope contract 仍由 read model scope policy 负责，不能把业务 scope 规则塞进 queue 层 |
| Workbench all fan-out | `WorkbenchReadModelRefreshService` | `scope_key=all` 只列出当前月份 scopes，通过既有 gateway 投递月份 refresh，传播 tenant/priority/trace/force metadata，并在 fan-out 接受后完成 command；不得构建或发布 `workbench:all` generation。`all` 只由显式访问/运维合同触发；relation 普通写入无论能否解析月份都不投递 month 或 `all` |
| OA sync source/fan-out | `OAProjectionSyncService` | runtime `oa.sync` 只调用 dual-view source batch；任一启用 form 失败整轮失败并记录 run，不提交部分 snapshot。admission/payment-status-only 变化只投递 OA pending 精确月份；completed canonical 真实变化才进入 shared owner fan-out。in-progress source 不解析附件/OCR；禁止恢复多 list 扫描、fingerprint polling 或 snapshot repository 的 shared fan-out |
| Workbench dependent publish | `WorkbenchReadModelRefreshService` | Workbench 月分片 projection commit 只原子发布自身 generation 并完成自身 dirty scope，不 enqueue `cost_statistics` 或任何其他页面。Cost 消费者在访问时先比较 Workbench expected/active versions，依赖 fresh 后才能 enqueue 当前 Cost scope。禁止恢复 `workbench_shard_published` fan-out |
| Bank-flow canonical relation source | `BankFlowRuleBatchReadModelRefreshService` | bank-flow worker 先按 scope 读取银行流水，再用一次 canonical PostgreSQL source bundle 按这些 row id 获取 active relation rows 与同一 snapshot source versions；unchanged skip 和 rebuild 必须共用该版本。worker 启动不得加载全量 Workbench relation snapshot，不得使用 `workbench_relation` read model facade 生成未提交候选；需要 rebuild 时才读取完整分类 snapshot。该约束不改变 no-OA legacy worker 的独立 I/O。 |
| Cost statistics versioned publish | `CostStatisticsReadModelRefreshService` / repository | handler 必须从 event 取得非负整数 `source_version` 并显式传入 month/parent builder。repository 复用现有 partial unique index，在一个事务内锁定该 scope 唯一 `pending` / `processing` dirty row，版本精确相等才写 read model；随后 handler 以同一版本条件完成。发布被拒绝或完成竞态失败都保持 `refreshing`，不得污染 Redis 或投递 parent；月份仅在发布和完成都成功后 fan-out parent |
| Cost statistics structured publish | `CostStatisticsSqlProjectionBuilder` / repository | 月份发布把 OA rows 和 bank-flow rows 分别批量写入两张 cost-owned 行表，parent metadata 必须剥离两类大数组；parent 只从结构化 shard rows 聚合并原子删除 obsolete scope 的两类 rows。projection 不写 Redis，禁止恢复旧无版本 cache writer 或 JSON dual-write |
| Shared relation proof consumers | consumer query owner / canonical relation repository | shared relation confirm/withdraw/cancel 只推进 canonical relation version，不由 UoW/repository 投递 `oa_pending_payment` 或其它 consumer。各消费者在页面访问时检测自身 source mismatch 并精确 enqueue；worker 读取 relation proof 必须经 canonical repository/freshness gate，不得伪造 queue-drained/fresh |
| Relation-dependent invoice publish | `InvoiceUsageCollectionSqlProjectionBuilder` / runtime worker | input/output invoice projection 读取共享 relation scope 前必须通过 `workbench_relation` freshness gate；关系 scope pending/processing/stale 时抛出 `workbench_relation_read_model_not_fresh` 并由 worker 短延迟 defer，禁止把并行 claim 的旧 relation source versions 写成 fresh。 |
| Invoice lifecycle pending source | `InvoiceLifecycleSqlProjectionBuilder` / `InvoiceLifecycleReadModelRepositoryPort` | worker 先验证 exact pending-invoice 月分片 fresh，再读取该分片已发布 rows；禁止在 lifecycle worker 内重新执行 `SearchPendingSqlProjectionBuilder._pending_invoice_rows(...)` 或其它 canonical/live 构建链。 |
| Invoice lifecycle pending dependency refresh | `RuntimeWorker` / `ReadModelRefreshGateway` | `invoice_lifecycle:YYYY-MM` 等待 pending-invoice 时只补投同月 `expense:all:YYYY-MM` 与 `income:all:YYYY-MM`，禁止非法裸月份；显式 lifecycle `all` 只补投 `expense:all` 与 `income:all`。normalize、validate、active/fresh dedupe 和持久化继续由正式 gateway / PostgreSQL durable queue 负责。 |
| Claim hot path index | PostgreSQL migration | `job.outbox_events` active queue claim 必须保留 event-type-first 索引 `outbox_events_claim_event_type_priority_idx`，覆盖 `event_type/status/priority rank/available_at/created_at/id`；该索引只优化 worker lane claim I/O，不改变 durable queue 状态机、priority 语义或 freshness/readiness 事实源 |
| Handler call | runtime worker | handler 只处理登记 event type |
| Import processor state | PostgreSQL canonical/import file facts | import worker 只缓存 processor 类型；每个 job 调用必须重新构造 durable processor state，禁止启动时 snapshot 污染后来创建的 file session、canonical dedupe 或确认结果 |
| Import archive object storage | API/worker 共享 object storage env | import worker 构造 `PostgresStateStore` 时必须注入启用的 `S3ObjectStorageRepository`，使 durable ETC session 中的 `minio://` / S3 archive ref 可被独立 worker 重载；不得回退到 Web 进程内 bytes 或本地隐藏副本 |
| Import persistence delta | import processing service | confirm job 只接收并持久化所选 session/batch 与本次创建或状态更新的 canonical facts；不得从 worker service 实例重取全量 snapshot，也不得回写 ETC、tax-certified 或其它未受影响事实域 |
| ETC canonical invoice metadata | ETC existing-invoice link service | 只把实际发生 ETC 关联的 invoice 列表交给 `save_invoice_etc_metadata`；禁止借 file import/full-state writer 回写全部 invoice |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Job result/status | runtime queue/app health | 成功、失败、重试和 readiness 可观察；影响 read model 的 job completion result summary 必须携带 target envelope 或明确不适用 |
| Fan-out parent result | readiness / app health | manifest 为 `fan_out_command` 的 command-only `all` parent 只负责入队 child scopes，不写 current readiness；parent event/dirty scope 的当前失败仍可观察，历史 readiness 只作为 diagnostics。真实 queryable all scope（当前 `bank_account_balance:all`）和 queryable parent 不适用该忽略规则。 |
| Worker heartbeat | `job.runtime_worker_heartbeats` | 空轮询 `idle` heartbeat 必须节流，禁止每个 0.05s poll 同步写库；`processing`、`deferred`、`failed`、`stopping`、`stopped` 等事件状态必须即时写入 |
| Read model projection | 对应 repository | 只写 worker 对应投影 |
| Import canonical delta | state-store/import repository | 只通过 `save_import_delta` 窄端口；PostgreSQL 幂等 upsert、本地按稳定 id 合并，禁止 generic full-state replace；必须在 durable delta 成功后才 fan-out write target envelope、tax invalidation 与 Workbench matching，持久化失败时不得产生下游事件 |
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
| Queue ops | `backend/src/fin_ops_platform/tools/runtime_queue_ops.py`、`backend/src/fin_ops_platform/tools/workbench_matching_scope_retry_ops.py` |
| RabbitMQ | `backend/src/fin_ops_platform/app/rabbitmq_dispatcher.py`、`rabbitmq_topology.py`、`services/rabbitmq_runtime.py` |
| Deploy | `deploy/oa/systemd/*.service.example`、`deploy/oa/env/*.env.example`、`deploy/oa/bin/finops-deploy-control.sh`、`deploy/oa/bin/finops-ensure-runtime-workers.sh`、`deploy/oa/bin/finops-prune-runtime-queue-history.sh` |
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
- 生产 env 示例仍可保留当前 registration 对应的 `--enable-*` flag 作为本地开发参数；生产 systemd 主合同是 `--registration`，且 `_apply_registration_args(...)` 会由 registry 写入 handler flags、event types 和 scope lane。已退出 registration 的兼容 flag 必须由 release helper 精确、幂等迁移，不能依赖只安装新 env 示例。
- `0086_runtime_queue_claim_hot_path.sql` 已本地保护，仍需生产发布后用 grouped 1s read model smoke 证明 Workbench/invoice lifecycle 总耗时是否真正低于目标。
