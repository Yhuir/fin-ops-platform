# Runtime Worker 模块边界与 I/O

日期：2026-08-06

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：所有后台 worker 由 registry、durable queue、handler 和部署 manifest 显式声明。
- 当前 worker 入口使用 registration contract；instance、event type、env、manifest/check 与 App Health 由 `runtime_worker_registry.py` 派生。唯一 required 集合是 `oa-sync`、`workbench-matching`、`workbench-relation`、`import`、`settings-maintenance`。关联台 page worker、Search、no-OA projection、`workbench-secondary` 与其它页面 projector worker 已删除；关联台和其它财务页面直接 canonical read。
- 生产证据状态：runtime 合同已关闭；每次发布仍必须以当前 registry/App Health、队列 backlog、页面读性能及 confirm/withdraw 跨页一致性 smoke 形成 point-in-time 证据，不沿用历史“待发布”结论。
- 旧代码删除状态：旧 `worker_legacy_application` / `RuntimeWorkerApplicationBridge` / GridFS migration worker / 手写生产 worker 矩阵已移除；`import.fact.changed` 与 `turnover_ledger.read_model.refresh` 的 registration、handler、env event type 和 runtime derived-lifecycle bridge 均已删除。import worker 只 claim `import.process.requested`。API 进程内 `ThreadPoolExecutor`、startup recovery/reconcile/stale scan 和同步 settings reset route 已删除。

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
| Outbox/job event | PostgreSQL durable queue | event type 必须在 registry 中登记。read model refresh metadata 只允许白名单字段进入 outbox；操作级 `row_ids` / `case_ids` 只能作为 worker 局部投影提示，`relation_deltas + row_ids` 才能授权 relation-only delta，均不能替代 dirty scope/source_version 事实源；`force_refresh=true` 仅用于显式运维重建并强制 full projection。支持 fan-out 的 handler 必须把 force 传播给每个具体 shard。普通命令、import confirm 与 OA 权威 integration snapshot 都不产生页面 refresh outbox；显式 `all` 仅用于低优先级运维 fan-out。同 scope pending 事件合并时必须删除 row 级 metadata并让 handler full rebuild；禁止保留不完整 delta却继续局部发布。关联台 GET 不产生任何 outbox event。 |
| Settings reset event | `settings.data_reset.requested` | 包含 job id、owner、action、reason、request id、impact fingerprint 和 recovery receipt id；OA 密码只在 API 请求内复核，禁止持久化。worker 锁定目标表、重算 fingerprint、验证 receipt 属于当前 job 后才可删除；未知 interrupted destructive reset fail closed，不自动重放。 |
| Bank requirement recalculation | `settings.bank_relation_requirements.recalculate.requested` | 包含 job id、owner、目标规则版本和 semantic changed tag codes。settings-maintenance worker 从当前 settings 和 active relation tag proof 集合式定位，并以关系成员对应 canonical 银行流水月份作为 exact scope 证明；先全量预验证再通过正式 relation command 逐 case 幂等更新。只 enqueue 实际写入关系的精确 `workbench_relation` 月份并标记同月 matching dirty；关联台页面在下一次 direct GET 读取已提交事实。禁止信任旧 payload scope、禁止 `all` 和页面请求内执行。 |
| Worker retry contract | `RuntimeWorker` + business job repository | durable event 采用 at-least-once；瞬时失败先把业务 job 归还 pending，再由 outbox 安排重试。达到最大次数才把业务 job 与 event 收敛为终态；processing lease 仅在超时后允许接管，活跃 lease 不得被第二个 worker 抢占。 |
| Manual import retry contract | import/background job repository | API 对同一 owner/type/idempotency key 的确认必须在数据库事务内按 request fingerprint 查重。terminal failed/partial 且 fingerprint 相同的 job 复用原 job id，原子清理失败结果、租约和 attempt state 后重新 queued/pending；succeeded/active job 原样返回；fingerprint 不同 fail closed。后台任务进度/完成/失败更新只能按 canonical `job_id` 单行读写，并用正式列覆盖历史 raw payload 中可能漂移的 `job_id`；禁止先读写全量 job snapshot、重放无关历史 job、再新建 UUID，或依赖仅按 job id 的全量 upsert 掩盖唯一键冲突。 |
| Candidate import dead-letter recovery | `import-audit-repair` + candidate import processor | 只读 discovery 可从一个明确 import job id 推导唯一 event/background job/session/file 白名单，歧义或缺失即拒绝；执行仍只接受显式完整 target 及 dry-run fingerprint。仅当原事件 dead-lettered、原 import job 为已知 background job 唯一键失败（或该精确恢复曾被正式 `preview_stale` 门禁中止）、文件仍为 untouched、可正式确认的 bank preview（包括仅含弱指纹 `suspected_duplicate`、无解析错误的 `preview_ready_with_errors`）且 canonical 写入为零时，候选版本可复用原 job/event。执行前必须用已归档原文件按当前 canonical facts 重新预览并持久化，再走正式 import processor；必须先验证 import/background job、batch/file 和 canonical facts 全部成功，最后才 resolve 精确 dead letter。禁止绕过 stale gate、通用 requeue、扫描历史失败任务或先标记 event done。 |
| Active refresh state | PostgreSQL outbox + dirty scope | gateway 的 ensure/wakeup coalescing 必须通过 repository 的 exact-scope 原子入口执行。单 scope 委托同一个 batch 入口；多 scope 在一个事务内按稳定顺序 advisory-lock 全部 `tenant/type/key`，一次读取 `job.outbox_events pending/processing`，再以既有 set-based CTE 只写未覆盖 scopes。覆盖关系为 `force > full scope > partial delta`；partial 不得吞掉 full，非 force 不得吞掉 force，partial 之间只有语义覆盖才 no-op。新增语义在该锁内合并 pending event，或为 processing event 建立 pending follow-up。只有活跃事件才证明 worker 会继续推进；最新完成的 `force_refresh` 只证明当次运维任务，不得覆盖后续访问产生的新 target；orphan dirty 必须允许重新 enqueue。handler 返回 `stale_source_version` 或 `stale_source_version_after_publish` 时，worker 必须先通过 durable gateway 建立同 scope successor，再 ACK 原事件；successor enqueue 失败时禁止 ACK。禁止逐 scope 事务/SQL N+1、两事务竞态或同 scope 丢失新语义。canonical mutation、显式 repair/reapply 与 force 不走此 ensure 合并边界 |
| Refresh availability timestamp | `job.outbox_events.available_at` | write-operation / read-model refresh SLO 以 `available_at -> processed_at` 衡量 enqueue-to-done；事务内 writer 必须用 `clock_timestamp()` 写实际入队可处理时间，不能让 transaction-level `now()` 把业务写事务耗时计入 worker drain；同 scope pending refresh 被新 source_version 合并时，active outbox event 的 `created_at`/`updated_at` 也必须重置为当前 enqueue 时间，避免兼容报表继续读到旧 pending 年龄 |
| RabbitMQ publisher confirm | Pika blocking publish | 单次 confirm 必须受 `RABBITMQ_PUBLISH_TIMEOUT_SECONDS` 硬截止约束；超时关闭连接并复用既有 `mark_publish_failed` 重试合同，禁止让 dispatcher 永久停在 `publishing`。PostgreSQL durable queue 仍是状态事实源。 |
| Worker instance env | deploy/systemd | 生产 systemd 必须传 `--registration <instance>` 与 `--worker-instance <instance>`；instance name、event types、claim scope filters 与 handler flags 由 registry 派生。`release-gate-activate` 在切换前后必须比较 registry required instances 与 systemd concrete units，`unknown_worker_count` 和 `required_worker_not_ready` 均为 0 才允许 PASS；已启用、运行或失败但不在当前 registry 中的 `fin-ops-worker@*.service` 必须先 stop/disable/reset-failed。PostgreSQL durable queue worker 默认 idle poll 为 `0.05s`；已退役 Workbench page/Search/no-OA/secondary worker 参数不得迁移或启动。 |
| Worker PostgreSQL statement timeout | worker env / `RuntimeQueueRepository` | worker 入口必须在构造专用 polling worker 前把 registration 的 `FIN_OPS_WORKER_STATEMENT_TIMEOUT_SECONDS` 应用到共享 PostgreSQL connection；不能只依赖通用 `RuntimeWorker` 初始化，否则 `workbench-matching` 这类独立 dirty-scope worker 会静默退回 10 秒默认值。 |
| Workbench matching source versions | matching worker / matching orchestrator | 只包含会改变确定性正式关系结果的规则、OA、附件解析、银行标签和异常版本；direct page query 的 DTO/SQL schema 不得进入 matching stale-scan 输入，也不得无关重算全部历史 matching scope。 |
| Claim scope filter | worker registry / worker env | 只用于有生产证据的同 event type 吞吐隔离；scope contract 仍由 read-model policy 负责。成本统计不参与 claim |
| OA sync canonical commit | `OAProjectionSyncService` | runtime `oa.sync` 只调用 dual-view source batch；任一启用 form 失败整轮失败并记录 run，不提交部分 source snapshot。成功时提交 completed/admission/payment-status/watermark facts，并通过独立 `OAAttachmentInvoicePromotionService` 把 completed records 已缓存解析的正式附件发票按强身份批量 link/create 到 canonical invoice pool；in-progress source 不解析附件/OCR。completed 附件解析必须先经过共享 untrusted-document policy，安全版本进入 cache key；拒绝结果不得提升发票或写 cache 成功态。PostgreSQL attachment persistence 必须在同一事务写 canonical invoice 与该 OA 月份扩展窗口的 durable matching dirty scopes，避免发票已写入但正式关系永不扩展；任一写入失败整体回滚。OA workflow 从 in-progress 进入 completed 不执行 pending-relation promotion；两种状态共用 formal Workbench relation，source snapshot 只在 OA 同时退出 completed/admitted 集合时调用 relation command 做成员清理。自动 sync 的幂等输入零 invoice write、零重复 dirty write；管理员精确附件刷新可在零 invoice write 时显式补发同一 bounded matching window，用于历史关系修复。sync 本身不持有 queue、search producer、独立 matching invalidator 或 shared page fan-out；禁止恢复 OA pending relation promoter、HTTP promotion、多 list 扫描、fingerprint polling、snapshot repository enqueue 或 downstream fan-out |
| Bank-flow live candidate | 页面 API / shared live builder | 候选读取仍在请求内读取 canonical 银行流水、有效分类、paired policy 和 active relation，不使用页面 read model。正式 batch/event 由业务 command/UoW 写入；标签 requirement 语义变化是独立 settings-maintenance domain job，不是 candidate projection worker。legacy no-OA 仅保留 canonical API/service I/O，没有独立 worker 或 projection。 |
| Cost statistics exclusion | registry / worker runtime | 不得注册 Cost worker、event、scope、manifest dependency 或 env；页面直接读 canonical snapshot |
| Cross-read-model dependency | manifest / worker runtime | 只有 source manifest entry 显式声明的 `read_dependencies` 才允许 worker 补投 dependency refresh；当前两个保留 read model 均未声明跨模型依赖。已退休 scope 或 manifest 外 event 不得重新创建旧 refresh。 |
| Shared relation proof | `workbench_relation` worker / canonical relation repository | `workbench_relation` 作为独立共享 read model 保留；页面自身不再等待或投递已退休的页面 projection。confirm/withdraw/cancel 继续推进 canonical relation version，关系分发状态由共享 relation worker 单独维护。 |
| Claim hot path index | PostgreSQL migration | `job.outbox_events` active queue claim 必须保留 event-type-first 索引 `outbox_events_claim_event_type_priority_idx`，覆盖 `event_type/status/priority rank/available_at/created_at/id`；该索引只优化 worker lane claim I/O，不改变 durable queue 状态机、priority 语义或 freshness/readiness 事实源 |
| Handler call | runtime worker | handler 只处理登记 event type |
| Import processor state | PostgreSQL canonical/import file facts | import worker 只缓存 processor 类型；每个 job 调用必须重新构造 durable processor state，禁止启动时 snapshot 污染后来创建的 file session、canonical dedupe 或确认结果。候选版本的受控银行恢复重放还必须显式接收每个 source session 的精确 repaired-duplicate 数和固定 repair reason，只能跳过仍命中同一 keeper 的来源 row；普通 import handler 不携带该授权。 |
| Import archive object storage | API/worker 共享 object storage env | import worker 构造 `PostgresStateStore` 时必须注入启用的 `S3ObjectStorageRepository`，使 durable ETC session 中的 `minio://` / S3 archive ref 可被独立 worker 重载；不得回退到 Web 进程内 bytes 或本地隐藏副本 |
| Import persistence delta | import processing service | confirm job 只接收并持久化所选 session/batch 与本次创建或状态更新的 canonical facts；不得从 worker service 实例重取全量 snapshot，也不得回写 ETC、tax-certified 或其它未受影响事实域 |
| ETC canonical invoice metadata | ETC existing-invoice link service | 只把实际发生 ETC 关联的 invoice 列表交给 `save_invoice_etc_metadata`；禁止借 file import/full-state writer 回写全部 invoice |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Job result/status | runtime queue/app health | 成功、失败、重试和 readiness 可观察；影响 read model 的 job completion result summary 必须携带 target envelope 或明确不适用 |
| Execution attempt history | `job.runtime_event_attempts` | 每次 claim 都新增独立 attempt；成功、retry、失败、dead-letter、graceful release、defer 和 lease expiry 都记录 worker、起止时间、耗时、错误与安全结果摘要，不复制业务 payload。release/defer 即使不消耗 retry budget 也必须保留独立历史。 |
| Background job affected months | `job.background_jobs.affected_months` | 只保存实际 `YYYY-MM`；无月份归属保存空数组。全量运维 scope 使用 scope/event 合同中的 `all`，不得再写入月份数组。migration `0131` 已清理历史 `all` 并验证该约束。 |
| Fan-out parent result | readiness / app health | manifest 为 `fan_out_command` 的 command-only `all` parent 只负责入队 child scopes，不写 current readiness；parent event/dirty scope 的当前失败仍可观察，历史 readiness 只作为 diagnostics。 |
| Worker heartbeat | `job.runtime_worker_heartbeats` | 空轮询 `idle` heartbeat 必须节流，禁止每个 0.05s poll 同步写库；`processing`、`deferred`、`failed`、`stopping`、`stopped` 等事件状态必须即时写入 |
| Read model projection | 对应 repository | 只写 worker 对应投影 |
| Import canonical delta | state-store/import repository | 只通过 `save_import_delta` 窄端口；PostgreSQL 幂等 upsert、本地按稳定 id 合并，禁止 generic full-state replace。durable delta 成功后只允许当前 import 合同明确的非页面领域任务；页面 write target/freshness/barrier 均为空。持久化失败时不得产生任何下游事件 |
| Wakeup/transport | RabbitMQ 可选 | 不能作为状态事实源；dispatcher 发布的每个 registry event 必须有 required consumer，缺失 metrics 或 consumer=0 时 release gate 阻断；正式切换由 deploy-control 根据 registry 精确备份、执行并失败回滚 |
| Publish terminal recovery | PostgreSQL outbox / RabbitMQ dispatcher | consumer 已把 durable event 完成后，`status=done/publish_status=publishing` 由 dispatcher 或 release checkpoint 立即幂等收敛为 `published`，不得等待超时或重复发布；release gate 必须同时证明 unpublished/publishing/publish-failed backlog 为 0 |
| Queue history retention result | runtime queue ops / deploy timer | 只删除 `done` 历史；输出按 outbox event type 与 dirty scope type 聚合的 candidate/deleted count |

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Runtime queue | `backend/src/fin_ops_platform/services/runtime_queue.py` |
| Runtime queue migrations | `backend/src/fin_ops_platform/postgres/migrations/*runtime_queue*.sql`、`0139_idempotency_and_worker_attempt_history.sql` |
| Worker registry | `backend/src/fin_ops_platform/services/runtime_worker_registry.py` |
| Worker runtime | `backend/src/fin_ops_platform/services/runtime_worker.py`、`runtime_worker_handlers.py` |
| App worker entry | `backend/src/fin_ops_platform/app/worker.py`、`backend/src/fin_ops_platform/services/oa_attachment_invoice_promotion_service.py` |
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
- `tests/test_runtime_infrastructure_postgres_integration.py`
- `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_claim_next_can_filter_scope_keys_for_split_worker_lanes`
- `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_claim_event_by_id_honors_scope_filters_for_rabbitmq_consumers`
- `tests/test_deploy_runtime_examples.py`
- `tests/test_deploy_oa_script.py`
- `tests/test_runtime_sync_closure_gate.py`
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
- migration `0127` 是无数据变更、无 DROP 的退休标记：历史 outbox、dirty scope、readiness 和 projection 表全部保留为上一版本回滚证据。发布 helper 先停止并 disable 新 registry 未登记的退休页面 instance，再确认退休 read-model event/dirty scope 没有 `processing`；门禁通过后才停止其余上一版本 worker、运行 migration 并激活新版本。门禁失败时已登记的 import/matching/保留 read-model worker 继续运行，不把生产 runtime 留在全停状态。新 registry、dispatcher 与 App Status 不 claim/展示退休历史行。回滚时恢复上一版本 registry/env 后可继续消费保留 backlog，普通新页面访问不得隐式触发。
- 生产 env 示例仍可保留当前 registration 对应的 `--enable-*` flag 作为本地开发参数；生产 systemd 主合同是 `--registration`，且 `_apply_registration_args(...)` 会由 registry 写入 handler flags、event types 和 scope lane。已退出 registration 的兼容 flag 必须由 release helper 精确、幂等迁移，不能依赖只安装新 env 示例。
- `0086_runtime_queue_claim_hot_path.sql` 继续保护保留 worker 的队列 claim；生产发布后需要验证两个保留 read model 及其他登记任务的 backlog、耗时和失败率，并确认 retired Search/no-OA/BankFlow draft event 与 worker 为零。
