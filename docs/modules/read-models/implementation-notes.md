# Read Model 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- read model refresh 入队前由统一 scope policy/gateway 负责 normalize、validate 和 dedupe；`RuntimeQueueRepository` 继续只负责 PostgreSQL durable queue 持久化。
- 生产旧 runtime 状态的 scope contract 检查/清理由 `ReadModelScopeContractService` 编排，SQL 限定在 `PostgresReadModelScopeContractRepository`，清理后通过 `ReadModelRefreshGateway` 补投规范 replacement scope。
- RabbitMQ real consumers 只负责 transport/wakeup；`job.outbox_events`、`job.read_model_dirty_scopes` 与 `read_model.app_status_readiness` 仍是 read model 状态事实源。Redis payload 只能在 fresh gate 后缓存。
- authenticated HTTP SLO gate 的当前 P2/P3 默认目标是首屏 API p95 <= 1000ms，并且必须同时满足 HTTP status、latency 和 freshness：任何 `read_model_status != fresh` 或 `refresh_enqueued=true` 都算失败，不能把快速返回的 refreshing 当作“已同步”。写操作同步门禁使用 operation-to-fresh p95 <= 1000ms、p99 <= 3000ms；历史 5 秒记录仅作为旧基线，不作为当前 closure 上限。
- `bank_detail:all` 不是可读 freshness scope，而是 fan-out 控制 scope；真实 readiness 和 downstream dependency 应以具体月份 shard 或明确 read model status 为准。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-16 - 事务型 producer 补齐成本统计 scope policy

- 目标：修复外部往来 Postgres 事务写路径绕过 read model scope policy，导致 `turnover_relation_changed` 继续生成 legacy `cost_statistics` scope 的风险。
- 影响范围：`TurnoverLedgerDirtyOutboxWriter` 事务入队、`TurnoverLedgerWriteUnitOfWork` source version 映射、成本统计 scope contract repair dry-run。
- 关键决策：非事务 producer 继续走 `ReadModelRefreshGateway`；事务内 producer 在同一事务中复用 `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY.normalize_and_validate(...)` 后再调用 `enqueue_read_model_refresh_in_transaction`。不把 stale 伪装 fresh，不手工改 readiness。
- 文档影响：更新 read-models、turnover-ledger、cost-statistics 和 P2/P3 closure ledger。
- 测试覆盖：`tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction` 保护事务 producer；`tests/test_read_model_scope_contract.py` 继续覆盖生产 legacy row dry-run/apply。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`。
- 未测风险：生产 cleanup apply、worker drain 到 fresh、authenticated HTTP SLO 仍需发布后受控验证。
- 后续事项：新增事务型 read model producer 时必须显式复用 scope policy registry 或提供等价 contract 测试。

## 2026-06-16 - Bank detail fan-out scope 与 downstream dependency 边界

- 目标：修复外部往来款管理和免 OA 批次依赖 `bank_detail` 时的 all-scope fan-out 循环，避免页面无数据但 App Status 长时间显示同步中。
- 影响范围：read model dependency defer 语义、`bank_detail` all-scope fan-out、active coalescing reason、bank tag read facade 的 missing transaction 与 blocking scope 语义；不改变 `bank_detail` 月份 shard rebuild 和 readiness 发布规则。
- 关键决策：`bank_detail:all` 只作为显式 fan-out command，不能由 downstream all-scope `bank_detail_read_model_not_fresh` 自动补投；`bank_detail_all_shard` 是 ensure/wakeup 类 reason，目标月份已 active 时不重复 bump dirty source_version。真实写入 reason 仍保持 bump active scope，避免新事实被旧 worker 覆盖。fresh `bank_detail` read model 中没有某些 transaction id 时，不再降级为 non-fresh；缺失 id 作为诊断返回，downstream projection 按无标签处理。非 fresh 依赖读取必须只补投 `dirty_scopes` / signature `dirty_status` 标记的 blocking scope，不能因为一个月份 pending 而重刷所有相关月份。
- 文档影响：同步更新 runtime-workers、bank-details、turnover-ledger 模块。
- 测试覆盖：`tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_detail_all_shard_reason_does_not_bump_active_scope`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes`。
- 验证命令：见本轮最终交付说明。
- 未测风险：真实生产历史 dirty/outbox 需要发布后 drain 观测；如果存在旧版本遗留 dead-letter/processing，必须通过 runtime ops 工具恢复。

## 2026-06-13 - Dependency-not-fresh runtime defer

- 目标：避免 downstream read model 在 source read model 尚未 fresh 时走普通 60s retry/dead-letter，缩短页面从失败恢复到同步的尾延迟。
- 影响范围：`RuntimeWorker`、`RuntimeQueueRepository.defer_event(...)`、worker CLI `--dependency-not-fresh-delay-seconds`；所有抛出 `*_read_model_not_fresh` 的 read model refresh handler 共享受益。
- 关键决策：defer 只延后 outbox event 再 claim，不写 fresh readiness，不缓存 payload；普通异常和真实 handler bug 仍保留原 failure/dead-letter 语义。
- 文档影响：同步更新 read-models 状态机、runtime-workers 状态机/测试矩阵/实施记录。
- 测试覆盖：`tests/test_runtime_worker.py`、`tests/test_runtime_queue.py`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_defer_event_delays_dependency_retry_without_failure_or_dead_letter -v`。
- 未测风险：未在真实生产库重新采集全 app enqueue-to-fresh p95；如果 source projection 本身慢，defer 只能避免长 retry，不能替代 SQL/projection 优化。
- 后续事项：用 closure gate 观察 `runtime_worker.event_deferred` 与各 read model pending age，把持续高频 defer 的 source projection 纳入下一轮优化。

## 2026-06-13 - Workbench relation fan-out priority

- 目标：在 relation 写入 fan-out 中优先刷新 `workbench_relation` source read model，降低 downstream projection 因 relation distribution 未 fresh 而失败重试的概率。
- 影响范围：事务内 relation producer 写入 `job.read_model_dirty_scopes` 与 `job.outbox_events` 的 priority 字段。
- 关键决策：不改变 freshness 事实源，不新增缓存或队列；`workbench_relation` 使用 `high` priority，下游 read model 保持 `normal`。
- 文档影响：同步记录到 workbench-relations 和 runtime-workers；完整 dependency DAG 仍未完成。
- 测试覆盖：`tests/test_workbench_relation_repository.py` 和 runtime queue priority contract tests。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_enqueue_read_model_refresh_increments_and_returns_source_version tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_enqueue_read_model_refresh_in_transaction_preserves_source_version_payload_and_outbox_contract -v`。
- 未测风险：未连接真实生产 PostgreSQL 重新采集 enqueue-to-fresh p95；priority 不能保证跨 lane 的完整依赖顺序。
- 后续事项：补 dependency-aware scheduler/deferral，并运行 `sync_slo_baseline` / `runtime_sync_closure_gate` 对比优化前后指标。

## 2026-06-13 - authenticated HTTP SLO fresh gate 收紧

- 目标：让全 app 页面“5 秒内已同步”的验收不再只看 HTTP 200/202 和耗时，而是检查真实 read model freshness。
- 影响范围：`http_slo_probe.py` 默认 probe 参数、`runtime_sync_closure_gate.py` 默认 HTTP target、闭环验收报告语义。
- 关键决策：默认 HTTP target 调整为 5000ms；默认探针使用更贴近前端首屏的参数，包括银行明细当前年日期范围和非空 search 查询；probe 只读取显式 `read_model_status`/`readModelStatus`，不把普通业务 `status` 字段误判为 read model 状态；非 fresh 或 refresh enqueued 直接失败。
- 文档影响：更新 read-models 实施记录和测试矩阵。
- 测试覆盖：`tests/test_http_slo_probe.py` 覆盖默认 probe、普通 status 字段、非 fresh/refresh enqueued 失败。
- 验证命令：见最终交付说明。
- 未测风险：authenticated HTTP SLO 的最终证明依赖真实登录态 cookie/token 和生产发布后的接口。
- 后续事项：接入 Prometheus/Grafana 或 OpenTelemetry 后，应把 enqueue-to-fresh latency、HTTP SLO p95、non-fresh count 和 refresh_enqueued count 变成持续指标。

## 2026-06-13 - Required RabbitMQ real consumers 生产切换

- 目标：把 required RabbitMQ eligible read model worker 从 PostgreSQL polling/wakeup 切到 RabbitMQ real consumer，降低 queue wakeup latency，并让 RabbitMQ Management metrics、queue depth、DLQ 和 consumer count 进入 `/health/ready` 观测闭环。
- 影响范围：`run_rabbitmq_staging_preflight` required/optional 检查边界、worker systemd 共享 RabbitMQ env、`RabbitMqConsumer.consume_forever()` interrupt 行为、生产 required worker env 和 RabbitMQ topology。
- 关键决策：preflight 默认只检查 required eligible worker；optional worker 需显式 `--include-optional-workers`。`/etc/fin-ops/fin-ops.rabbitmq-worker.env` 只存共享 `RABBITMQ_URL`，单 worker 是否切换仍由 `/etc/fin-ops/fin-ops.worker.<instance>.env` 的 `FIN_OPS_QUEUE_BACKEND` 决定。RabbitMQ DLQ 中没有 PostgreSQL outbox 对应行的 envelope 视为 transport orphan，先导出审计摘要再清理。
- 文档影响：更新 `docs/operations/runtime-sync-repair-2026-06-12.md`、`docs/operations/runtime-worker-governance.md` 和 `docs/operations/postgresql-runtime.md`。
- 测试覆盖：`tests/test_rabbitmq_staging_preflight.py` 覆盖 optional worker flag；`tests/test_deploy_oa_script.py` 覆盖共享 worker env 加载顺序；`tests/test_rabbitmq_runtime.py` 覆盖 consumer 收到 interrupt 后干净返回。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_staging_preflight tests.test_rabbitmq_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script tests.test_rabbitmq_staging_preflight tests.test_rabbitmq_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_runtime tests.test_runtime_worker tests.test_deploy_oa_script -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --help`；`bash scripts/verify.sh docs`；生产 preflight、topology apply、required worker cutover 和 `/health/ready` 检查。
- 未测风险：Prometheus/Grafana 或 OpenTelemetry 尚未接入；`read_model_refresh_duration_ms.p95` 仍约 17.77s，RabbitMQ 只解决 wakeup/transport，不解决重型 projection 执行耗时或慢 API N+1。
- 后续事项：进入 EXPLAIN/pg_stat 驱动的 relation-details、workbench groups、cost_statistics、pending_invoice 查询优化；再按 fresh gate 引入 Redis fresh-cache，并把 SLO 指标接入持续监控。

## 2026-06-12 - Worker shutdown release processing lease

- 目标：修复发布或 systemd stop 在 worker 已 claim outbox event 后留下 `processing` lease、导致页面等待 300s lock timeout 的尾延迟。
- 影响范围：`RuntimeQueueRepository.release_event()`、`RuntimeWorker.run_forever()` shutdown signal handling、runtime worker 测试和运维说明。
- 关键决策：shutdown 只释放当前 `worker_id` 持有的 `processing` event，恢复 `pending`、清 lock、回退本次 claim 增加的 `attempts`，写 `raw_payload.runtime_shutdown_release`；不释放其他 worker 的 lock，不伪造 done/fresh。
- 文档影响：更新 `docs/operations/runtime-worker-governance.md` 和 `docs/operations/runtime-sync-repair-2026-06-12.md`。
- 测试覆盖：`tests/test_runtime_queue.py::test_release_event_restores_worker_locked_processing_event_to_pending`；`tests/test_runtime_worker.py::test_run_forever_releases_claimed_event_on_shutdown_request`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_queue tests.test_runtime_queue_ops tests.test_rabbitmq_runtime -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --help`；`bash scripts/verify.sh docs`；生产发布 `main-3933b00f-stage6-202606122329` 后核对 `/health/ready`、队列表和 `fin-ops-worker@workbench.service` 日志。
- 未测风险：重型 handler 如果被 C 扩展或数据库调用长时间阻塞，Python signal 处理仍可能延迟到控制权返回；`read_model_refresh_duration_ms.p95` 仍约 17.77s，Stage 6 不解决真实重型 rebuild 的执行耗时。
- 后续事项：继续 RabbitMQ real consumers、Redis fresh-cache、EXPLAIN 驱动的索引/分区和 Prometheus/Grafana 或 OpenTelemetry SLO 阶段。

## 2026-06-12 - covered historical dead-letter 归档与 lock-timeout 风险定位

- 目标：把 Stage 4 后剩余的 10 条已被同 scope fresh/done 覆盖的历史 read-model dead-letter 归档，清零 `/health/ready.failed_jobs`，并保持真实后端同步证明。
- 影响范围：`backend/src/fin_ops_platform/tools/runtime_queue_ops.py`、`tests/test_runtime_queue_ops.py`、`RuntimeQueueRepository.resolve_dead_letter_event()` 的运维调用路径、生产 `job.outbox_events.raw_payload.operator_resolution`。
- 关键决策：新增 `resolve-covered-dead-letters --dry-run/--execute`，要求同一 `tenant_id + read_model_key + scope_type + scope_key` 有 `fresh_readiness` 或后续 `done` outbox proof，且同 scope 无 active dirty；execute 仍复用 repository 标记 `done` 并写 `operator_resolution`，不直接 SQL 改状态。
- 文档影响：更新 `docs/operations/runtime-worker-governance.md` 和 `docs/operations/runtime-sync-repair-2026-06-12.md`。
- 测试覆盖：`tests/test_runtime_queue_ops.py` 覆盖 exact-scope proof、无 proof 拒绝、bulk dry-run 不写、bulk execute 只处理 eligible event；`tests/test_runtime_queue.py` 覆盖 repository 写 `operator_resolution`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue_ops tests.test_runtime_queue -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --help`；`bash scripts/verify.sh docs`；生产 dry-run/execute/post dry-run 和 `/health/ready`。
- 未测风险：`/api/app-health` 认证态 UI 未用浏览器登录态直接截图验证；`/health/ready.read_model_refresh_duration_ms.p95` 仍是历史滚动窗口约 17.7s，不能证明 SLO 已达成。
- 后续事项：发布过程定位到 worker 被 systemd 重启后会留下 `processing` outbox，依赖 300s lock timeout 回收，必须优先做 worker graceful shutdown、lease release/reclaim 或 deploy restart 顺序修复。

## 2026-06-15 - Workbench all aggregate 自等待修复与操作级 projection

- 目标：修复 `workbench:all` aggregate-only event 已经发布 active generation 后，又因 `job.read_model_dirty_scopes` 中自身 pending 被 `get_workbench_refresh_status("all")` 判为 `refreshing`，导致 `workbench_all_scope_aggregate_not_published` 重试直至 dead-letter 的循环；同时缩短确认/撤回 overlay 的用户可见阻塞时间。
- 影响范围：`WorkbenchSqlProjectionBuilder.refresh_workbench_all_scope_from_active_shards()`、`WorkbenchReadModelRefreshService` aggregate publish gate、`WorkbenchWriteFacade` confirm/withdraw response contract、`ReconciliationWorkbenchPage` operation overlay。
- 关键决策：all aggregate 发布结果新增 `aggregate_published=true` 明确表达 active generation 已成功写出；handler 用该信号完成 dirty scope，再由完成动作让 readiness 收敛。确认/撤回写 API 返回受影响月份的操作级 `workbench_relation` freshness targets 与后端 operation projection，前端等 relation distribution fresh 后应用 projection；`workbench` month shard、`workbench:all` 和下游 read model 后台追赶但不阻塞用户操作，并通过 `*_cross_page` SLO profile 单独监控。
- 运维闭环：生产中已由旧版本产生的 `workbench/all` pending dirty scope 与 `workbench/all` dead-letter outbox 不能直接 SQL 改 green；发布修复后先让 worker 重新处理当前 pending/aggregate，已被后续 done/fresh 覆盖的 dead-letter 使用 `runtime_queue_ops resolve-covered-dead-letters --dry-run/--execute` 归档，并复查 `/health/ready`、dirty/outbox、active generation consistency。
- 验证命令：`python3 -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_completes_all_when_aggregate_publish_is_confirmed_despite_self_dirty_status tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_confirm_link_response_returns_operation_freshness_targets_for_affected_scopes tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_link_response_returns_operation_freshness_targets_for_affected_scopes -q`；`npm test -- --run src/test/WorkbenchSelection.test.tsx`；`npm run build`。

## 2026-06-12 - 生产 legacy scope repair apply 与收敛验证

- 目标：发布包含 current-effective App Status、repair manifest 和 production dry-run SQL 修复的 release，并执行受控生产 repair apply，清理旧 `cost_statistics` legacy scope 对 App Status 的污染。
- 影响范围：生产 `job.read_model_dirty_scopes`、`job.outbox_events`、`read_model.app_status_readiness` 中的 legacy cost runtime 行；replacement scope 通过 `ReadModelRefreshGateway` 入队后由 worker 真实重建。
- 关键决策：只有 dry-run 证明 `current_uncovered_outbox_failure_count=0` 才执行 `--apply`；apply 删除 9 条 legacy runtime 行、补投 6 个规范 scope、记录 audit event `98e118a0-0209-4dc0-8ad6-56d30e4e9043`，不手工写 fresh readiness。
- 文档影响：新增 `docs/operations/runtime-sync-repair-2026-06-12.md` 并登记到 operations index。
- 测试覆盖：沿用 `tests/test_read_model_scope_contract.py` 覆盖 dry-run/apply/audit/rollback/current blocker 保留；生产验证覆盖真实 dirty/outbox/readiness 收敛。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`；`bash scripts/verify.sh docs`；生产 `scripts/check-read-model-scope-contracts.py --json`、`--apply --reason production_scope_contract_repair --json`、post-check 和 `/health/ready`。
- 未测风险：`/api/app-health` 未认证请求返回 401，页面认证态 App Status 只通过后端事实源间接验证；剩余 10 条 covered historical dead-letter 未归档，仍会出现在 `/health/ready.failed_jobs`，但不再是 current-effective 页面 blocker。
- 后续事项：下一阶段用独立受控 dead-letter resolve/归档把历史已覆盖失败从 runtime failed count 中移除，然后进入 RabbitMQ real consumers、Redis fresh-cache、索引/分区和持续观测阶段。

## 2026-06-12 - 生产 dry-run SQL pattern 修复与基线记录

- 目标：执行生产只读 dry-run 和同步基线采集，验证 repair manifest 能在真实 PostgreSQL 上运行。
- 影响范围：`PostgresReadModelScopeContractRepository.list_read_model_outbox_failures()`、`tests/test_read_model_scope_contract.py`、生产同步基线文档。
- 关键决策：psycopg SQL 字符串中的 literal `%` 必须写成 `%%`，否则会被当成占位符解析；新增 repository 级测试锁定 `like '%%.read_model.refresh'`。
- 文档影响：新增 `docs/operations/runtime-sync-baseline-2026-06-12.md` 并登记到 operations index。
- 测试覆盖：`tests/test_read_model_scope_contract.py::test_postgres_repository_outbox_failure_query_escapes_psycopg_percent_pattern`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v`；生产只读 `scripts/check-read-model-scope-contracts.py --json`。
- 未测风险：本阶段未执行生产 `--apply`；App Status 变绿仍需下一阶段发布、repair、replacement scope 收敛后验证。
- 后续事项：发布包含 current-effective App Status、repair manifest 和本 SQL 修复的 release 后，再执行受控 repair apply。

## 2026-06-12 - Repair manifest 与 current-effective failure 分类

- 目标：把 scope contract dry-run 从单纯 cost statistics legacy 行检查，扩展为可审计 repair manifest，支持区分 legacy/invalid cost statistics runtime 状态、已被 later done/fresh readiness 覆盖的历史 outbox failure，以及仍然 current-effective 的未覆盖 failure。
- 影响范围：`ReadModelScopeContractService`、`PostgresReadModelScopeContractRepository`、`scripts/check-read-model-scope-contracts.py` 输出 contract、read-models 运维文档和测试矩阵。
- 关键决策：`--apply` 只删除非规范 cost statistics runtime 行并补投规范 replacement scope；current uncovered outbox failure 必须保留为真实 blocker，不自动删除、不伪造 fresh。apply 报告带 cleanup、rollback 和 audit event，便于生产修复留痕和回滚。
- 文档影响：更新 read-models `README.md`、`state-machine.md`、`tests.md`，并同步 runtime worker 运维说明。
- 测试覆盖：`tests/test_read_model_scope_contract.py` 新增 repair manifest 分类、audit/rollback、current blocker 保留和幂等 apply 覆盖；平台边界与 runtime queue 回归测试一起运行。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract tests.test_platform_runtime_boundary_guards tests.test_runtime_queue_ops -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`。
- 未测风险：当前本地 shell 未配置 PostgreSQL 连接串，未对真实生产库执行 `scripts/check-read-model-scope-contracts.py --json` dry-run 或 `--apply`。
- 后续事项：下一阶段先在生产连接配置下生成 baseline/dry-run JSON，确认 current uncovered failure 的真实原因，再决定 repair apply、requeue 或 worker/query 修复。

## 2026-06-11 - 测试闭环矩阵与状态机补齐

- 目标：按测试闭环 master goal 将 Read Model 模块迁入标准测试矩阵，明确影响面、场景覆盖、七类测试、历史 bug 回归库、关键 smoke flows、nightly 覆盖和未测风险。
- 影响范围：只改文档；覆盖 `ReadModelQueryGateway`、`ReadModelRefreshGateway`、scope policy/contract、runtime queue、readiness reporter、worker refresh scope 和 App Status readiness 的测试入口说明。
- 关键决策：当前无 P0 自动化缺口；生产真实 PostgreSQL `--apply`、真实 Redis/RabbitMQ/worker drain、业务页面 stale/refreshing UI 行为分别记录为 documented-risk，并交给发布前 dry-run、runtime-workers 和具体页面模块闭环处理。
- 文档影响：更新 `tests.md` 和 `state-machine.md`；全局状态文件记录 read-models 下一步状态。
- 测试覆盖：未新增测试；现有 `tests/test_read_model_freshness.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_readiness_reporter.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_runtime_queue.py`、`tests/test_platform_runtime_boundary_guards.py` 覆盖 P0 边界。
- 验证命令：见本次最终说明。
- 未测风险：未连接真实生产 PostgreSQL 执行 scope contract `--apply`；未在本模块逐页面证明 stale/refreshing UI 行为；未验证真实 Redis/RabbitMQ 网络。
- 后续事项：下一模块处理 `runtime-workers`，继续补 worker/transport/readiness 运行风险。

## 2026-06-10 - Read model scope contract 生产检查与清理

- 目标：为生产库中已有的 legacy/invalid `cost_statistics` dirty scope、outbox event 和 App Status readiness 提供只读检查与受控修复入口。
- 影响范围：`ReadModelScopeContractService`、`PostgresReadModelScopeContractRepository`、`scripts/check-read-model-scope-contracts.py`、平台架构守卫。
- 关键决策：检查按当前 scope policy registry 判定 canonical、legacy 和 invalid；`--apply` 删除非规范旧状态，并通过 `ReadModelRefreshGateway` 去重补投可归一化的 replacement scope。完全非法 scope 只清理，不猜测 replacement。
- 文档影响：更新 read-models、cost-statistics、runtime-workers 和 runtime worker 运维文档。
- 测试覆盖：`tests/test_read_model_scope_contract.py` 覆盖只读检查、受控清理和 replacement scope 去重；`tests/test_platform_runtime_boundary_guards.py` 将新 repository 显式登记为允许写 job runtime 表的平台边界。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract tests.test_platform_runtime_boundary_guards -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`。
- 未测风险：未在真实生产数据库执行 `--apply`；上线操作需先 dry-run 检查报告。
- 后续事项：无。

## 2026-06-10 - Read model refresh scope gateway 阶段 1

- 目标：封住 worker lifecycle 向 `cost_statistics.read_model.refresh` 投递裸月份/裸 `all` 的入口，并建立轻量本地 scope policy/gateway 边界。
- 影响范围：`ReadModelScopePolicyRegistry`、`ReadModelRefreshGateway`、worker lifecycle read model refresh 入队。
- 关键决策：成本统计 scope policy 复用 `CostStatisticsRuntimeService.refresh_scope_keys_from_scope_keys(...)`，接受旧裸月份/裸 `all` 并展开为 `active/all` project scopes；未知 project scope fail fast。非成本统计 read model 暂使用通用 dedupe policy，保持现有 scope shape。
- 文档影响：更新 read-models、runtime-workers、cost-statistics 模块入口和测试矩阵。
- 测试覆盖：`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes`、`tests/test_platform_runtime_boundary_guards.py`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`。
- 未测风险：阶段 1 未包含真实生产库清理。
- 后续事项：已由后续 scope contract 检查/清理入口和架构守卫补齐。
