# Runtime Worker 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- Worker lifecycle 触发 read model refresh 时必须走统一 scope policy/gateway 入队；worker 不直接拼接或投递成本统计等 read model 的业务 scope contract。
- 非事务 read model refresh producer 由 architecture guard 约束：不得绕过 `ReadModelRefreshGateway` 直接调用 `RuntimeQueueRepository.enqueue_read_model_refresh(...)`。
- `bank_detail:all` 是显式 fan-out 命令，不是 downstream `*_read_model_not_fresh` 可自动推导的稳定 freshness 依赖 scope；下游 all-scope event 只能等待或补投可识别的具体月份 shard。

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

## 2026-06-16 - Bank detail dependency loop guards

- 目标：修复外部往来款管理和免 OA 银行流水批次在生产长期显示“同步中”、页面无数据的问题。
- 影响范围：`RuntimeWorker` 的 dependency-not-fresh scope 推导、`ReadModelRefreshGateway` 的 active coalescing reason 列表、`BankTransactionTagReadFacade` 对 fresh read model 缺失 transaction id 与 blocking scope 的语义；不改变业务写入、projection SQL、RabbitMQ/Redis 事实源。
- 真实原因：生产先被 downstream all-scope `bank_detail_read_model_not_fresh` 推导成 `bank_detail:all` 放大；修正后仍发现 `downstream_bank_tag_read` 持续补投月份 shard。后者有两层：fresh `bank_detail` read model 中找不到部分 transaction id 时，facade 曾把结果降级为 `missing`；并且当多个月份中任一月份 pending/processing 时，facade 曾把所有月份都作为 refresh target，导致刚刷完的月份被父任务下一轮重新打 pending，所有月份无法同时 fresh。
- 关键决策：`bank_detail:all` 保留为 `BankDetailReadModelRefreshService` 内部 fan-out 到月份 shard 的显式命令；`turnover_ledger:all`、`no_oa_bank_batch:all` 等 downstream event 因 `bank_detail_read_model_not_fresh` defer 时，不再自动补投 `bank_detail:all`。`bank_detail_all_shard` 归入 ensure/wakeup reason，目标月份已 pending/processing 时不再 bump 新 source_version。fresh read model 的 `missing_transaction_ids` 是诊断信息，不是 freshness blocker；downstream category provider 返回已存在行的标签，缺失行按无标签处理。非 fresh payload 若携带 `dirty_scopes` / signature `dirty_status`，facade 只补投真正阻塞的 scope，不能重刷已经 fresh 的月份。
- 文档影响：同步更新 runtime-workers、read-models、bank-details 和 turnover-ledger 模块文档。
- 测试覆盖：`RuntimeWorkerTests.test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`ReadModelRefreshGatewayTests.test_bank_detail_all_shard_reason_does_not_bump_active_scope`、`BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_keeps_fresh_status_when_some_rows_are_not_projected`、`BankTransactionTagReadFacadeTests.test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows`、`BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes`，并保留月份 dependency、mutating reason 和 downstream read model 回归。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地测试证明架构边界；真实生产仍需发布后观察旧 dirty/outbox 是否自然 drain，并验证 `turnover_ledger:all`、`no_oa_bank_batch:all` 从 refreshing 收敛到 fresh。
- 后续事项：如果生产仍有历史 stuck `processing` 或 covered dead-letter，必须走 `runtime_queue_ops` 受控 inspect/requeue/resolve，不允许直接 SQL 伪造 fresh。

## 2026-06-14 - Defer unique collision fallback

- 目标：修复 v26 真实 confirm/withdraw 闭环中旧 `bank_detail` / `pending_invoice` processing 事件在 cover 查询后、释放回 pending 前被并发新 pending 事件覆盖，仍触发 `outbox_events_dedupe_uidx`，导致 RabbitMQ worker 重启和 8-11s 长尾。
- 影响范围：`RuntimeQueueRepository.defer_event(...)`；不改变 dirty scope、readiness、RabbitMQ envelope 或 handler 计算结果。
- 关键决策：cover 查询接受更新版本的 `pending`、`processing`、`done` 事件；如果 pending update 仍遇到 PostgreSQL `23505` 唯一冲突，立即回滚当前事务并重新开事务，把当前旧 processing 事件标记 `done`，写入带 `collision=true` 的 `runtime_defer_superseded` 审计。这样不伪造 fresh，也不等待 300s lock timeout。
- 文档影响：同步更新 runtime worker 测试矩阵和历史 bug 回归库。
- 测试覆盖：新增 `RuntimeQueueRepositoryTests.test_defer_event_resolves_unique_collision_from_concurrent_pending_cover`，并更新 cover 分支断言。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py -q`、`PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests tests/test_invoice_lifecycle_read_model_refresh.py tests/test_runtime_worker.py tests/test_runtime_queue.py tests/test_read_model_refresh_gateway.py tests/test_write_operation_slo_audit.py tests/test_runtime_sync_closure_gate.py -q`。
- 未测风险：本地测试证明唯一冲突 fallback；真实闭环仍需发布 v27 后重新跑 approved confirm/withdraw E2E，并确认 bank_detail/pending_invoice 不再出现 worker crash 或 5s+ 长尾。

## 2026-06-14 - Defer superseded branch isolation

- 目标：修复 v25 真实 confirm/withdraw 写后审计中 `pending_invoice` 旧 `processing` 事件被新同 dedupe `pending` 事件覆盖时，`defer_event(...)` 仍因多写 CTE 执行顺序触发 `outbox_events_dedupe_uidx`，导致 worker 重启并留下 processing 长尾。
- 影响范围：`RuntimeQueueRepository.defer_event(...)`；不改变 PostgreSQL durable queue、dirty scope、readiness 或 RabbitMQ wakeup 的事实源边界。
- 关键决策：把 defer 逻辑拆成显式事务分支：先锁定当前 worker 持有的 processing 事件，再查同 dedupe pending 覆盖事件；有覆盖时只把当前事件标记 `done` 并写 `runtime_defer_superseded`，没有覆盖时才释放回 `pending`。释放分支额外带 `not exists` 保护，避免把已覆盖事件重新置回 pending。
- 文档影响：同步更新 runtime worker 测试矩阵和历史 bug 回归库。
- 测试覆盖：`RuntimeQueueRepositoryTests.test_defer_event_resolves_current_processing_when_pending_same_dedupe_exists` 改为行为式断言，证明覆盖分支不会执行 pending 更新；`RuntimeQueueRepositoryTests.test_defer_event_delays_dependency_retry_without_failure_or_dead_letter` 覆盖无覆盖时的短延迟释放。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py -q`、`PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests tests/test_invoice_lifecycle_read_model_refresh.py tests/test_runtime_worker.py tests/test_runtime_queue.py tests/test_read_model_refresh_gateway.py tests/test_write_operation_slo_audit.py tests/test_runtime_sync_closure_gate.py -q`。
- 未测风险：本地 fake transaction 能证明 repository 分支行为；真实闭环仍必须发布后清理 v25 残留 superseded processing，并重新跑 approved confirm/withdraw E2E 与 write audit。

## 2026-06-14 - Bank detail stale source skip for write SLO

- 目标：修复真实 confirm/withdraw 闭环中快速连续写入产生的旧 `bank_detail` source_version 仍执行完整 rebuild，导致新版本事件排队、`bank_detail` 和依赖它的 `pending_invoice` 写后 SLO 超过 5s。
- 影响范围：`BankDetailReadModelRefreshService`，复用现有 `RuntimeQueueRepository.read_model_refresh_is_current(...)` 边界；不改变 dirty/outbox/readiness 事实源，不写假 fresh。
- 关键决策：在 bank detail handler 开始前和 rebuild 后都检查当前 event source_version 是否仍是 dirty scope 当前版本；若已被更新版本覆盖，则 ack 为 skipped，不 complete dirty scope，也不发布旧 readiness。
- 文档影响：同步更新 runtime worker 与 bank-details 模块测试矩阵。
- 测试覆盖：`tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests::test_stale_source_version_does_not_rebuild_or_complete`、`tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests::test_source_version_that_becomes_stale_after_rebuild_does_not_complete`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py::BankDetailReadModelRefreshServiceTests -q`、`PYTHONPATH=backend/src python3 -m pytest tests/test_invoice_lifecycle_read_model_refresh.py tests/test_runtime_worker.py tests/test_runtime_queue.py -q`。
- 未测风险：本地测试证明旧事件跳过语义；真实收益必须发布后重新执行 approved confirm/withdraw E2E 和 write audit。

## 2026-06-14 - Dependency refresh active gate

- 目标：修复 v21 真实 confirm/withdraw audit 中 `pending_invoice` 因 `bank_detail_read_model_not_fresh` 多轮 defer 后仍约 5.7s 的长尾。
- 影响范围：`RuntimeWorker._enqueue_dependency_refreshes(...)`、`RuntimeQueueRepository.read_model_refresh_is_active(...)`、runtime worker/queue 测试。
- 关键决策：dependency-not-fresh 时只在依赖 read model 没有 active dirty scope 时补投 refresh；如果依赖已经 `pending` 或 `processing`，当前事件只短延迟 defer，不再 bump 依赖 `source_version`。这保持 PostgreSQL dirty scope 为事实源，不写 readiness，也不伪造 fresh。
- 文档影响：更新 runtime worker 实施记录和测试矩阵。
- 测试覆盖：`RuntimeWorkerTests.test_run_once_does_not_bump_dependency_refresh_when_scope_already_active`、`RuntimeQueueRepositoryTests.test_read_model_refresh_is_active_checks_pending_or_processing_dirty_scope`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py tests/test_runtime_queue.py -q`。
- 未测风险：真实生产仍需发布后用 confirm/withdraw write audit 证明 pending_invoice enqueue-to-done 回到 5s 内。

## 2026-06-14 - Write SLO tail retry tightening

- 目标：修复 v20 生产真实 confirm/withdraw audit 中 `pending_invoice` 依赖 retry 约 6.6s、快速 withdraw 的第二个 `search` scope 约 5.5s 的剩余长尾。
- 影响范围：`RuntimeWorkerConfig.dependency_not_fresh_delay_seconds`、worker CLI、`RuntimeQueueRepository.defer_event(...)`、生产 worker systemd 模板、`search-tertiary` worker registration/env/deploy docs。
- 关键决策：不引入 Kafka，也不改变 PostgreSQL durable queue / dirty scope / readiness 事实源。`*_read_model_not_fresh` defer 支持 sub-second delay，并把生产模板默认调为 0.25s；新增第三条 required `search-tertiary` RabbitMQ consumer，只并发 claim `search.read_model.refresh`，用于快速 confirm/withdraw 连续写入的同 scope search 长尾。
- 文档影响：更新 runtime worker 测试矩阵、部署 runbook、worker 治理和 Workbench relation 实施记录。
- 测试覆盖：`RuntimeWorkerTests.test_run_once_defers_dependency_not_fresh_without_marking_failed`、`RuntimeQueueRepositoryTests.test_defer_event_delays_dependency_retry_without_failure_or_dead_letter`、`RuntimeWorkerRegistryTests.test_hot_read_model_workers_have_dedicated_parallel_consumers`、deploy/runtime example 回归。
- 验证命令：本地 targeted pytest、py_compile、`git diff --check`、`bash scripts/verify.sh docs`；生产仍需 release 后跑 read model SLO、authenticated HTTP SLO 和 confirm/withdraw write audit。
- 未测风险：本地测试不证明真实 systemd drop-in 已加载 0.25s 或 `search-tertiary` 已启动；必须用生产 `systemctl show` 和 write audit 闭环。

## 2026-06-13 - Dependency defer dedupe collision guard

- 目标：修复生产 Workbench confirm/withdraw 后下游 worker 因 `workbench_relation_read_model_not_fresh` 调用 `defer_event(...)`，但同一 dedupe 已有新的 pending 事件时触发 `outbox_events_dedupe_uidx` 唯一冲突，导致 worker 进程崩溃、原事件卡在 `processing` 直到 300s lock timeout 的问题。
- 影响范围：`RuntimeQueueRepository.defer_event(...)`、`write_operation_slo_audit` 验证入口、Workbench withdraw auth/audit 生产闭环。
- 关键决策：`defer_event` 改为单条 CTE。若当前 processing 事件已有同 dedupe pending 覆盖事件，则把当前事件标记 `done` 并写 `raw_payload.runtime_defer_superseded`；否则才把当前事件释放回 `pending`。不写 readiness，不伪造 fresh。
- 文档影响：更新 runtime worker 实施记录、测试矩阵和 Workbench relation 实施记录。
- 测试覆盖：`RuntimeQueueRepositoryTests.test_defer_event_resolves_current_processing_when_pending_same_dedupe_exists`、既有 defer/release/superseded 测试、Workbench auth/idempotency 和 write audit profile 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_write_operation_slo_audit tests.test_workbench_auth_context_idempotency tests.test_workbench_write_characterization -v`。
- 未测风险：该修复消除 300s 崩溃长尾，但不单独解决 all-scope/shard fan-out 的吞吐问题；生产仍需 confirm/withdraw 后用 `write_operation_slo_audit --since <release-time>` 验证每个 scope 的 enqueue-to-done。
- 后续事项：若 all-scope 或 pending invoice shard 仍超过 5s，应继续做 worker replica/DAG 调度或 all-scope SQL-side publish，不可用删 `all` 的方式制造假 fresh。

## 2026-06-13 - RabbitMQ stale processing release

- 目标：修复 RabbitMQ transport 下 PostgreSQL `processing` 事件超过 lock timeout 后没有对应 RabbitMQ envelope 时无法被普通 consumer 自动 reclaim，导致 source read model 长时间 not fresh、downstream 反复 defer 的长尾。
- 影响范围：`RuntimeQueueRepository.release_stale_processing_events(...)`、`RuntimeQueueRepository.resolve_superseded_processing_events(...)`、`runtime_queue_ops release-stale-processing` / `resolve-superseded-processing` 运维入口、runtime worker 状态机和测试矩阵；不改变 RabbitMQ 只做 wakeup/transport 的事实源边界。
- 关键决策：release 只能把可重新处理的 stale `processing` 事件恢复为 `pending`、重置 publish 状态为 `unpublished` 并写入 `raw_payload.operator_stale_processing_release`；如果同一 dedupe 已有更新的 pending/processing/done event 覆盖旧 `processing`，先用 superseded resolution 标记旧事件 `done` 并写 `raw_payload.operator_superseded_processing_resolution`。两者都不写 readiness，不伪造 fresh。CLI 必须显式 `--dry-run` 或 `--execute`。
- 文档影响：更新 runtime worker 状态机、测试矩阵和运维 runbook。
- 测试覆盖：`RuntimeQueueRepositoryTests.test_release_stale_processing_events_requeues_with_operator_audit`、`RuntimeQueueRepositoryTests.test_resolve_superseded_processing_events_marks_obsolete_processing_done`、`RuntimeQueueOpsTests.test_release_stale_processing_dry_run_lists_candidates_without_update`、`RuntimeQueueOpsTests.test_release_stale_processing_execute_uses_repository_boundary`、`RuntimeQueueOpsTests.test_resolve_superseded_processing_dry_run_lists_candidates_without_update`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_queue_ops -v`。
- 未测风险：本地单元测试不证明真实 RabbitMQ dispatcher 重新 publish；生产发布后必须先 dry-run，再 execute，并观察 outbox/dirty/readiness 收敛。
- 后续事项：长期可把 stale processing sweep 做成受控 periodic ops job，但仍必须保留 PostgreSQL durable queue 为事实源。

## 2026-06-14 - Hot read model dedicated RabbitMQ consumers

- 目标：把真实 confirm/withdraw 后仍超过 5s 的下游 read model 长尾从单实例串行 drain 改为专用 RabbitMQ consumer 并行 drain。
- 影响范围：`runtime_worker_registry.py`、`App Status` read model/domain registry、`deploy/oa/env/fin-ops.worker.*.env.example`、runtime worker manifest/deploy helper。
- 关键决策：不改变 PostgreSQL durable queue、dirty scope、readiness 或业务 fan-out 事实源；保留旧 `search-pending`、`cost-tax` combined worker 作为兼容消费者，同时新增 required `search`、`search-secondary`、`search-tertiary`、`pending-invoice`、`cost-statistics`、`tax-offset`、`invoice-lifecycle-secondary` 专用 worker。生产发布时 helper 从 registry 自动安装缺失 env 并启动这些实例。
- 文档影响：更新 runtime worker 测试矩阵、运维治理、部署 worker 表和相关页面模块入口。
- 测试覆盖：`RuntimeWorkerRegistryTests.test_hot_read_model_workers_have_dedicated_parallel_consumers`，以及 deploy/App Status/runtime monitoring 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_registry tests.test_deploy_runtime_examples tests.test_deploy_oa_script tests.test_app_status_overview_service tests.test_runtime_monitoring -v`。
- 未测风险：本地测试只能证明 registry/manifest/env/App Status 契约；真实 5s SLO 必须发布后用 `read_model_slo_smoke`、登录态 `http_slo_probe` 和真实 confirm/withdraw `write_operation_slo_audit --since <scenario-start>` 验证。

## 2026-06-14 - Workbench closure hot-path cleanup

- 目标：修复真实 confirm/withdraw 闭环中两个尾部问题：`invoice_lifecycle` 旧 `source_version` 在快速连续写入时可能继续重建并污染审计；`worker-workbench` 同步 Redis page-cache warmup 被计入 fresh/ack 热路径，导致连续 confirm/withdraw 下第二个 workbench refresh 接近或超过 5s。
- 影响范围：`InvoiceLifecycleReadModelRefreshService`、`worker-workbench` 构造、Workbench groups Redis warmup 配置。
- 关键决策：`invoice_lifecycle` 与 workbench/search/no-oa 一样，在处理前和发布前检查 `read_model_refresh_is_current(...)`；旧版本事件返回 `skipped` 并由 worker ack，不写 fresh readiness、不 complete 新 dirty scope。Workbench Redis page-cache warmup 改为显式开关 `FIN_OPS_WORKBENCH_GROUPS_SYNC_CACHE_WARMUP_ENABLED=1` 后才进入同步 hot path；默认页面仍从 fresh SQL read model 读取，API 读路径只在 fresh gate 后写 Redis payload。
- 测试覆盖：`tests/test_invoice_lifecycle_read_model_refresh.py`、`tests/test_workbench_query_facade.py::WorkbenchGroupsPageCacheWarmerTests::test_sync_cache_warmup_is_disabled_by_default_and_explicitly_enabled`。
- 未测风险：同步 warmup 关闭后，特定 workbench groups 首个 Redis miss 会由 API 读路径承担一次 DB page 查询；HTTP SLO 已覆盖该读路径，后续如需预热应改成独立低优先级 warmup event，而不是放回 refresh ack 前。

## 2026-06-14 - Ensure refresh active coalescing

- 目标：修复 downstream projection/facade 在依赖 read model 已经 `pending`/`processing` 时反复 enqueue 同一 scope，导致 `source_version` 被读路径不断 bump、写操作后 enqueue-to-fresh 被放大到 40s+ 的长尾。
- 影响范围：`ReadModelRefreshGateway` 非事务 producer；事务内真实写入 producer 保持原 source_version bump 语义。
- 关键决策：只对 ensure/wakeup 类 reason 做 active coalescing，包括 `dependency_not_fresh`、`pending_invoice_sql_projection`、`bank_detail_relation_tags_read`、`workbench_relation_write_precondition`、`downstream_bank_tag_read` 和 `api_*`。这些 reason 只表示“确保已有刷新在跑”，不是事实写入；当目标 dirty scope 已 active 时，gateway 返回规范化 scope 但不再写新的 dirty/outbox。`workbench_relation_changed` 等真实写入原因仍必须 bump active scope，避免旧 worker 把新写入误标 done。
- 测试覆盖：`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_ensure_refresh_reason_does_not_bump_active_scope`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_mutating_refresh_reason_still_bumps_active_scope`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_refresh_gateway.py -q`、`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py tests/test_runtime_queue.py -q`。
- 未测风险：本地测试证明 gateway 边界；真实收益必须发布后用受控 confirm/withdraw 和 `write_operation_slo_audit --since <scenario-start>` 验证 `pending_invoice` 与 `bank_detail` 均在 5s SLO 内。

## 2026-06-14 - Dependency-not-fresh production delay default

- 目标：把生产 worker 已知 `*_read_model_not_fresh` defer 默认从 2s 降到 0.25s，缩短 relation fan-out 中 invoice/pending/input 等依赖链的尾部等待。
- 影响范围：`deploy/oa/systemd/fin-ops-worker@.service.example`；运行时仍复用 `RuntimeWorkerConfig.dependency_not_fresh_delay_seconds` 和 `RuntimeQueueRepository.defer_event(...)`。
- 关键决策：只调整生产 systemd 模板默认值，不改变普通 retry/dead-letter，也不写 readiness；这是缩短已知依赖竞态的 wakeup 延迟，不是伪造 fresh。0.25s 只影响已知 dependency-not-fresh defer，普通 retry 仍走原 retry/dead-letter 规则。
- 测试覆盖：`DeployOaScriptTests.test_systemd_worker_template_uses_registry_registration_contract`。
- 未测风险：需要发布后用 systemd `ExecStart`/`Environment` 和生产 closure gate 证明模板已生效。

## 2026-06-13 - Dependency-not-fresh worker defer

- 目标：把 downstream read model 因 source read model 尚未 fresh 产生的已知顺序竞态，从普通 60s retry/dead-letter 路径改为短延迟 defer，缩短失败到同步的长尾。
- 影响范围：`RuntimeWorker` 异常分流、`RuntimeQueueRepository.defer_event(...)`、worker CLI `--dependency-not-fresh-delay-seconds`。
- 关键决策：只匹配 `read_model_not_fresh` 错误码文本；普通 handler 异常仍走原 `fail_event`、exponential retry 和 max attempts。defer 只改 outbox claim 时机，不写 fresh readiness，不改变 Redis/RabbitMQ 事实源边界。
- 文档影响：更新 runtime worker 状态机、测试矩阵和本实施记录。
- 测试覆盖：`RuntimeWorkerTests.test_run_once_defers_dependency_not_fresh_without_marking_failed`、`RuntimeQueueRepositoryTests.test_defer_event_delays_dependency_retry_without_failure_or_dead_letter`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_defer_event_delays_dependency_retry_without_failure_or_dead_letter tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_fail_event_dead_letters_after_max_attempts_and_preserves_trace tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_release_event_restores_worker_locked_processing_event_to_pending -v`。
- 未测风险：真实生产依赖链还需要 closure gate 验证 enqueue-to-fresh p95；defer 不能替代 source read model handler 性能优化。
- 后续事项：生产发布后核对 `runtime_worker.event_deferred` 频率，若持续出现，应继续优化对应 source projection 或引入显式 DAG dependency scheduler。

## 2026-06-13 - Worker per-instance throughput preservation

- 目标：确保 deploy-control 生成的 worker drop-in 不覆盖各 read model worker env 中的 `FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION`，让 bank-detail/workbench-relation/no-oa 等高吞吐配置真实生效。
- 影响范围：`deploy/oa/bin/finops-deploy-control.sh` worker drop-in；不改变 worker runtime loop、queue schema 或单个 env example 的既有配置。
- 关键决策：保留 systemd template 的安全默认值 `1`，由 `EnvironmentFile=-/etc/fin-ops/fin-ops.worker.%i.env` 提供 per-worker 覆盖；deploy-control drop-in 只重定向 release working directory/PYTHONPATH/ExecStart，不再在 drop-in 尾部强制写回 `1`。
- 文档影响：本记录；长期部署入口仍以 `deploy/oa/README.md` 和 `docs/operations/runtime-worker-governance.md` 为准。
- 测试覆盖：`DeployRuntimeExampleTests.test_deploy_control_worker_dropin_preserves_per_worker_throughput_env`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_runtime_examples -v`。
- 未测风险：真实生产 systemd drop-in 需要发布后执行 `systemctl daemon-reload` 并重启 worker 才会生效；本地无生产 systemd 环境。
- 后续事项：生产 closure gate 需要核对 `systemctl show fin-ops-worker@bank-detail.service -p Environment` 中的实际 `FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION`。

## 2026-06-14 - Workbench matching worker max-events env

- 目标：修复生产 closure gate 发现的 `workbench-matching` worker 因缺少 `FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION` 被 systemd 展开为空字符串而持续重启的问题。
- 影响范围：`deploy/oa/env/fin-ops.worker.workbench-matching.env.example` 和部署示例测试；不改变 matching worker 的业务批量大小，实际匹配吞吐仍由 `--workbench-matching-batch-size` 控制。
- 关键决策：给 `workbench-matching` 显式设置 `FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=1`。它不是 outbox/RabbitMQ read model worker，该值只满足统一 worker CLI contract，避免空参数导致启动失败。
- 测试覆盖：`DeployRuntimeExampleTests.test_required_worker_env_examples_define_max_events_per_iteration` 会校验所有 required worker 主 env example 都定义该变量。
- 生产验证：发布或手动同步 env 后，必须执行 `systemctl restart fin-ops-worker@workbench-matching.service`，确认 unit active/running 且 v27 后日志不再出现 `invalid int value: ''`。

## 2026-06-14 - RabbitMQ consumer PostgreSQL fallback drain interval

- 目标：修复生产 read model SLO smoke 中 `workbench` handler 仅约 0.8s，但 RabbitMQ dispatcher publish 瞬时断连后 consumer 依赖 heartbeat 才 fallback drain PostgreSQL，导致 enqueue-to-fresh 约 17s 的问题。
- 影响范围：`RuntimeQueueSettings`、`RabbitMqConsumer.consume_forever(...)`、`deploy/oa/env/fin-ops.rabbitmq-worker.env.example`；不改变 outbox/dirty/readiness 事实源，也不改变 RabbitMQ envelope 合约。
- 关键决策：新增 `RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS`，默认 1s。RabbitMQ consumer 独立按该间隔调用 `RuntimeWorker.run_once()` 扫 PostgreSQL durable queue；heartbeat 仍低频记录，避免把 idle heartbeat 写成 1s 噪声。这样 RabbitMQ publish 失败或 envelope 丢失时，PostgreSQL fallback 仍能满足 5s SLO。
- 测试覆盖：`RabbitMqRuntimeTests.test_consumer_drains_postgres_queue_on_short_interval_independent_of_heartbeat`、`RabbitMqRuntimeTests.test_runtime_queue_settings_parses_consumer_postgres_drain_interval`。
- 生产验证：发布后重启 RabbitMQ worker，确认 `read_model_slo_smoke --apply --target-ms 5000` 在 RabbitMQ publish 重试场景下仍能通过。

## 2026-06-13 - Workbench relation fan-out priority

- 目标：复用 runtime queue priority，让 relation source read model 在 relation fan-out 中先于 downstream read models 被 claim，降低依赖未 fresh 的普通 retry 长尾。
- 影响范围：`PostgresWorkbenchRelationRepository` 事务内 outbox/dirty producer；未改 `RuntimeWorker` loop、claim SQL 或 RabbitMQ transport。
- 关键决策：继续使用现有 `priority` 排序；`workbench_relation` refresh 为 `high`，下游 refresh 为 `normal`。这不是新的状态事实源，也不是完整 DAG scheduler。
- 文档影响：同步记录到 workbench-relations 和 read-models。
- 测试覆盖：relation repository priority test 与 runtime queue priority contract tests。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_repository.py -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_enqueue_read_model_refresh_increments_and_returns_source_version tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_enqueue_read_model_refresh_in_transaction_preserves_source_version_payload_and_outbox_contract -v`。
- 未测风险：真实 RabbitMQ/systemd 多 lane 并行仍可能让 downstream 先开始；priority 只降低概率，后续需要 dependency-aware deferral 或 scheduler 才能彻底避免已知依赖未 fresh 的 retry storm。
- 后续事项：实现 `workbench_relation -> bank_detail -> pending_invoice/no_oa` 的依赖调度，并用生产 baseline 验证 enqueue-to-fresh p95。

## 2026-06-11 - 测试闭环矩阵与状态机补齐

- 目标：执行测试闭环 master goal 的 runtime-workers 模块轮次，先审计 worker/queue/readiness/transport 影响面，再补齐模块文档。
- 影响范围：`runtime-workers` 模块文档、状态机、测试矩阵、历史 bug 回归库、模块验证命令。
- 关键决策：本轮未发现 P0 自动化缺口；现有测试已覆盖 worker loop、durable queue、registry/manifest、readiness reporter、runtime monitoring、RabbitMQ envelope/dispatcher/consumer、ops 命令和平台边界守卫。真实 RabbitMQ、真实 Postgres migration、systemd worker drain 保持 documented-risk，由 staging/运维 gate 验证。
- 文档影响：更新 `tests.md` 和 `state-machine.md`；长期 worker/read model 治理事实仍以 `docs/operations/runtime-worker-governance.md` 为准。
- 测试覆盖：沿用 `tests/test_runtime_worker.py`、`tests/test_runtime_worker_registry.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_monitoring.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_read_model_readiness_reporter.py`、`tests/test_rabbitmq_runtime.py`、`tests/test_runtime_queue_ops.py`、`tests/test_runtime_state_policy.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_platform_runtime_boundary_guards.py` 和 `tests/test_app_status_readiness_backfill.py`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_worker_registry tests.test_runtime_queue tests.test_runtime_monitoring -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract tests.test_read_model_readiness_reporter -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_runtime tests.test_runtime_queue_ops tests.test_runtime_state_policy tests.test_deploy_runtime_examples -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_app_status_readiness_backfill -v`。
- 未测风险：无真实基础设施环境变量时，不运行 `tests/test_runtime_infrastructure_postgres_integration.py`、`tests/test_rabbitmq_integration.py` 和真实 staging preflight。
- 后续事项：下一模块继续处理 `domain-events-lifecycle`。

## 2026-06-10 - Read model refresh producer gateway guard

- 目标：防止 app/API、service、backfill 或 worker lifecycle 新增 producer 时绕过统一 scope policy/gateway。
- 影响范围：非事务 read model refresh 入队调用点、运维脚本、平台 runtime 边界测试。
- 关键决策：已有非事务 producer 分批迁到 `ReadModelRefreshGateway`；事务内 writer 保留同事务 dirty/outbox 语义，不机械改造成普通 gateway。
- 文档影响：更新 runtime-workers 和 read-models 测试矩阵。
- 测试覆盖：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_read_model_refresh_producers_use_scope_gateway_boundary`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`。
- 未测风险：未覆盖真实生产 worker 长时间运行行为。
- 后续事项：无。

## 2026-06-10 - Worker lifecycle 成本统计 scope 归一化

- 目标：修复 worker lifecycle 在 ETC/导入等事件后向 `cost_statistics.read_model.refresh` 投递裸月份/裸 `all`，导致成本统计 SQL projection 拒绝 scope 的问题。
- 影响范围：`_RuntimeWorkerDerivedLifecycle._enqueue_scopes`、read model refresh gateway。
- 关键决策：保留 `RuntimeQueueRepository` durable queue 边界，worker 只通过 gateway 入队；成本统计 scope contract 在入队前统一 normalize、validate、dedupe。
- 文档影响：更新 runtime-workers、read-models、cost-statistics 模块文档和测试矩阵。
- 测试覆盖：新增 `tests/test_runtime_worker_read_model_refresh_scopes.py`，覆盖 worker lifecycle 不再投递 `2026-03`、`2026-04`、`all` 给成本统计，并验证 `tax_offset` 等非成本 read model 不被成本统计规则误改。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`。
- 未测风险：未运行真实 import worker 到 SQL projection 完成的端到端场景。
- 后续事项：已由后续 architecture guard 补齐。
