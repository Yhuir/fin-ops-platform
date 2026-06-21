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

## 2026-06-20 - Orphaned import fact dirty scope repair

- 目标：补齐历史 `import.fact.changed` 兼容事件已完成但 legacy dirty scope 未完成时的运维闭环，避免导入事实已可见而 App Status 继续显示同步中。
- 影响范围：scope contract repair CLI 和 PostgreSQL repository 只读/受控删除路径；不改变 worker claim event types、不改变 `import.fact.changed` legacy bridge 语义。
- 关键决策：repair 只识别 `reason=import_facts_changed`、状态非 done、且不存在同 tenant/scope active `import.fact.changed` outbox 的 dirty scope；默认 dry-run，`--apply` 才删除，并记录 audit/rollback manifest。
- 测试覆盖：`tests/test_read_model_scope_contract.py` 的 orphaned import fact repair 用例。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_scope_contract.py -q`；真实 runtime dry-run `scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json`。
- 未测风险：未对真实 runtime 执行 `--apply`；需要生产窗口或明确批准后操作。

## 2026-06-20 - 发票导入 read model 队列闭环与月级 fan-out

- 目标：修复发票导入后 App Status 长时间显示同步中、关联台逐步可见但 read model 队列不收敛的问题，并减少导入确认后的全量 pending invoice refresh。
- 影响范围：`RuntimeQueueRepository.defer_event(...)`、import worker 的 legacy `import.fact.changed` bridge、发票/银行导入确认后的 derived lifecycle fan-out；不改变 PostgreSQL durable queue/dirty scope/readiness 的事实源边界。
- 关键决策：`defer_event` 的 superseded cover 必须同时满足同 dedupe、更高或相等 `source_version`、且创建顺序晚于当前 processing event；旧 `done` event 即使 source_version 更高，也不能覆盖后来创建的新事件。`save_imports` 完整 snapshot 保存不再写 dirty/outbox refresh；当前导入确认路径按本次 rows 投递真实 refresh。导入影响月份已知时，pending invoice refresh 使用 `expense:all:<month>`、`income:all:<month>`、`income:cash_income:<month>`，不再先投递三个全量 aggregate。`import.fact.changed` handler 仅作为 legacy bridge：对 `bank_detail` 投递真实 `bank_detail.read_model.refresh` 后完成兼容 dirty scope。
- 后续优化：发票导入方向页 read model 由后台 import worker 计算本次确认文件的 batch type 后投递；进项文件只刷新 `input_invoice_usage`，销项文件只刷新 `output_invoice_collection`，混合导入按各自月份分别投递，未命中方向不入队。后台 `tax_offset` helper 同样过滤 batch type，银行流水文件不会再触发税金抵扣刷新。银行导入确认路径在投递 `bank_detail` 月级刷新时同步投递 `bank_account_balance:all`，避免账户余额页只能依赖 API miss 被动补刷。
- 文档影响：同步 runtime-workers、read-models 与 imports-invoices 模块记录；生产运维仍以 durable queue/readiness 状态为准。
- 测试覆盖：`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_does_not_let_older_done_event_cover_newer_processing_event`、`tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot`、`tests/test_import_processing_service.py::test_general_import_confirm_passes_bank_detail_scope_keys_to_persist_state`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_import_fact_changed_handler_completes_matching_dirty_scope`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_invoice_relation_scope_helpers_split_input_and_output_file_months`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_tax_offset_scope_helpers_ignore_bank_transaction_files`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_runtime_monitoring.py tests/test_import_job_queue.py tests/test_runtime_worker_registry.py tests/test_read_model_refresh_gateway.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests/test_write_operation_slo_audit.py -q`。
- 未测风险：本地测试证明 queue/worker 合同；真实生产仍需发布后观察本次导入相关 `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.app_status_readiness` 是否自然 drain，并重新导入小批量发票验证用户链路。

## 2026-06-19 - 生产 worker 只读 runtime gate 复查

- 目标：在不重启、不部署、不写数据库、不触发 read model apply 的前提下，复查当前生产 worker/runtime 外部证据。
- 影响范围：生产 release `main-8b5942e4-http-slo-admin-scope-202606191805` 的 API、RabbitMQ dispatcher、20 个 runtime worker 和 runtime closure gate；不改变 worker 代码或队列状态。
- 关键决策：只读证据可以证明当前 worker service 数量、active 状态和 runtime blocker 为 0；不能替代 direct `read_model_slo_smoke --apply` 的 enqueue-to-fresh 证明，也不能替代真实业务 write-operation E2E。
- 文档影响：同步本实施记录、`docs/modules/app-health-operations/implementation-notes.md`、`docs/modules/read-models/implementation-notes.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：本轮未新增代码测试；既有 runtime worker、runtime queue 和 closure gate 测试继续保护工具合同。
- 验证命令：SSH 只读 `systemctl is-active fin-ops.service`、`systemctl is-active fin-ops-rabbitmq-dispatcher.service`、`systemctl list-units 'fin-ops-worker@*.service'`、`systemctl show ... WorkingDirectory`；公网 `runtime_sync_closure_gate --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --allow-unauthenticated-http --health-ready-target-ms 1000 --json`。
- 生产证据：`fin-ops.service` active，RabbitMQ dispatcher active，20/20 `fin-ops-worker@*.service` active/running；API WorkingDirectory 为 `/opt/fin-ops/releases/main-8b5942e4-http-slo-admin-scope-202606191805/src`；公网 closure gate 中 `runtime_health` 通过，`health_ready_payload` 通过。
- 未测风险：未配置 bearer/admin token，authenticated HTTP/SSE gate 仍未闭合；未配置 write approval ticket 和安全 scenario，mutating write-operation E2E 仍未执行。

## 2026-06-19 - Runtime Read Model closure repair

- 目标：在发票导入 worker 修复后，把生产遗留的 dead-letter、dirty scope 和非 fresh readiness 收敛到干净状态，并保留可审计的运维证据。
- 影响范围：`bank_detail`、`no_oa_bank_batch`、`invoice_lifecycle`、`pending_invoice` read model refresh 事件；生产 `runtime_queue_ops` 受控 dead-letter resolution；不改变 worker handler 的业务投影逻辑。
- 关键决策：先通过 `ReadModelRefreshGateway` 对真实依赖 scope 重新入队，让 worker 自然发布 fresh readiness 和 complete dirty scope；只有在 `fresh_readiness` / `later_done` / `active_dirty_count=0` 证明成立后，才用 `runtime_queue_ops resolve-covered-dead-letters --execute` 归档历史 dead-letter。无效 `pending_invoice` 裸月份 readiness 是非 canonical 残留，按 repository 边界删除，不重放。
- 文档影响：同步 read-models 和 app-health-operations 实施记录；生产运维原则仍以 `docs/operations/runtime-worker-governance.md` 为准。
- 测试覆盖：本轮代码测试覆盖 `pending_invoice` scope policy，防止同类非法 scope 再次入队；生产修复通过只读 SQL 和受控 CLI 证明运行状态收敛。
- 验证命令：见本轮最终交付说明。
- 未测风险：生产修复证明现有 runtime state 已闭环；仍需用户执行真实发票重新导入来验证业务入口从上传到下游页面的完整用户链路。
- 后续事项：遇到 `*_read_model_not_fresh` 历史残留时，优先重放已收敛依赖 scope，再归档 covered dead-letter；不要绕过 queue/readiness 直接写 fresh。

## 2026-06-19 - RabbitMQ import fact changed drain 闭环

- 目标：修复发票上传/导入成功后，关联台和下游 read model 长时间显示同步中的问题。
- 影响范围：`import` worker registration、RabbitMQ dispatcher event types、`--enable-import-job-processing --check` 输出、发票导入到关联台 refresh 的后台链路；不改变 PostgreSQL durable queue / dirty scope / readiness 事实源。
- 关键决策：`import.fact.changed` 是导入事实写入后下游 read model dirty/outbox fan-out 的确认事件。RabbitMQ transport 下 import worker 不能只 claim `import.process.requested`，否则 `import.fact.changed` 会长期停留在 PostgreSQL `pending`，App Status 和关联台 freshness 都不会收敛。import worker 现在在所有 transport 下同时 claim `import.process.requested` 与 `import.fact.changed`，RabbitMQ dispatcher route/env 也覆盖 `import.fact.changed`。
- 文档影响：更新 runtime-workers、imports-invoices、reconciliation-workbench 和 app-health-operations 模块文档。
- 测试覆盖：`tests/test_runtime_worker_registry.py` 覆盖 import worker 在 PostgreSQL/RabbitMQ 下的 claim event types 与 registry-derived dispatch events；`tests/test_import_job_queue.py` 覆盖 RabbitMQ 模式 worker check 输出两个 event type 和 `finops.import.fact.changed` route。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地测试证明 registry/worker check contract；真实生产仍需发布后观察历史 `import.fact.changed` backlog、`job.read_model_dirty_scopes` 和关联台 read model 是否自然 drain。
- 后续事项：发布后优先只读核对 `job.outbox_events(event_type='import.fact.changed')` 非 done 数量是否归零，再重新导入少量发票验证完整链路。

## 2026-06-16 - P2/P3 一秒级 SLO 门禁口径

- 目标：把 runtime worker/read model 当前维护口径从历史 5 秒基线收紧到 17 页面 P2/P3 closure 的一秒级门禁，避免后续无人值守流程继续按旧阈值验收。
- 影响范围：runtime worker、read model SLO 工具、页面首屏 API 和写操作 operation-to-fresh gate；不改历史 5 秒运行记录。
- 关键决策：首屏 API 与 direct read model refresh 默认按 p95 <= 1000ms 验收；写操作同步链路同时要求 p95 <= 1000ms、p99 <= 3000ms。缺少 Postgres/RabbitMQ/env/auth/scenario 时应返回结构化 gated 状态，而不是把门禁误判为通过。
- 文档影响：同步更新 runtime-workers、read-models、cost-statistics、pending-invoices、tax-offset 和 runtime worker governance 当前边界。
- 测试覆盖：`tests/test_slo_tool_defaults.py` 锁定 SLO 工具默认阈值；`tests/test_rabbitmq_staging_preflight.py`、`tests/test_write_operation_scenario_discovery.py`、`tests/test_write_operation_e2e_smoke.py` 覆盖缺 env/input 时的结构化门禁状态。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_slo_tool_defaults tests.test_rabbitmq_staging_preflight tests.test_write_operation_scenario_discovery tests.test_write_operation_e2e_smoke -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实生产/staging worker drain、RabbitMQ transport、authenticated API 和受控写场景仍需真实环境 gate；不能用本地 mock 或 unauthenticated shell smoke 宣称完成。

## 2026-06-16 - RabbitMQ staging preflight 缺环境结构化门禁

- 目标：让无人值守 P2/P3 workflow 在缺少 `FIN_OPS_TEST_DATABASE_URL` 或 `RABBITMQ_TEST_URL` 时得到可分流的 `configuration_missing` 状态，而不是把 staging 环境缺失当作普通实现失败。
- 影响范围：`run_rabbitmq_staging_preflight` CLI 顶层状态、`tests/test_rabbitmq_staging_preflight.py`、runtime-workers/app-health 测试矩阵和 P2/P3 闭环台账；不改变已有 RabbitMQ topology、dispatcher、consumer 或 worker 检查命令。
- 关键决策：`env.required` check 仍保留为 `fail` 详情，顶层 report 在缺必需 env 时升级为 `status=configuration_missing`、`error=staging_preflight_environment_missing`、`required_env=[...]`，退出码为 2；真实命令失败仍保持 `status=fail` 和退出码 1。
- 文档影响：更新本模块 `tests.md`、app-health-operations 测试矩阵和 P2/P3 closure ledger。
- 测试覆盖：`tests/test_rabbitmq_staging_preflight.py::RabbitMqStagingPreflightTests::test_missing_env_returns_configuration_missing_before_running_commands`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_staging_preflight -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight --json --skip-real-tests`。
- 未测风险：本地只证明 preflight contract；真实 RabbitMQ broker、queue depth、consumer count、DLQ 和 systemd long-run drain 仍需要 staging/生产环境。
- 后续事项：具备 staging URL 后运行 preflight 不带 `--skip-real-tests`，再根据失败项分别处理 topology、dispatcher、worker 或 broker 权限问题。

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
- 关键决策：dependency-not-fresh 时只在依赖 read model 没有 active outbox refresh event 时补投 refresh；如果依赖 refresh event 已经 `pending` 或 `processing`，当前事件只短延迟 defer，不再 bump 依赖 `source_version`。dirty scope 继续作为 freshness 事实源，但不能单独代表 active worker work item。
- 文档影响：更新 runtime worker 实施记录和测试矩阵。
- 测试覆盖：`RuntimeWorkerTests.test_run_once_does_not_bump_dependency_refresh_when_scope_already_active`、`RuntimeQueueRepositoryTests.test_read_model_refresh_is_active_checks_pending_or_processing_outbox_event`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py tests/test_runtime_queue.py -q`。
- 未测风险：真实生产仍需发布后用 confirm/withdraw write audit 证明 pending_invoice enqueue-to-done 回到 5s 内。

## 2026-06-21 - Dependency refresh orphan dirty recovery

- 目标：修复 dependency dirty scope 已 pending 但 outbox 已 done/缺失时，worker 仍把依赖当 active，导致 downstream read model 长期 `refreshing` 的生产状态。
- 影响范围：`RuntimeQueueRepository.read_model_refresh_is_active(...)`、`RuntimeWorker._enqueue_dependency_refreshes(...)`、read model scope contract repair CLI。
- 关键决策：active gate 只查询 `job.outbox_events` 中同 scope/type 的 `pending`/`processing` read model refresh event；dirty scope 是否阻塞由 `read_model_refresh_is_fresh(...)` 判断。如果 dirty 存在但没有 active outbox，下一次 dependency-not-fresh 会补投依赖 refresh。无效 scope 由 `scripts/check-read-model-scope-contracts.py --repair invalid-read-model-scopes` 清理，不让 worker 无限重试。
- 文档影响：同步 read-model 实施记录、测试矩阵和运维治理。
- 测试覆盖：`RuntimeQueueRepositoryTests.test_read_model_refresh_is_active_checks_pending_or_processing_outbox_event`、`ReadModelScopeContractServiceTests.test_apply_deletes_invalid_policy_managed_read_model_scopes_and_records_audit`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_runtime_monitoring.py -q`。
- 未测风险：生产发布后必须执行 invalid scope repair、runtime closure gate，并观察 dependency refresh backlog 是否 drain。

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
- 生产验证：该历史阶段发布后重启 RabbitMQ worker，并以当时的 `read_model_slo_smoke --apply --target-ms 5000` 验证 RabbitMQ publish 重试场景；当前 P2/P3 closure 复跑必须使用 `--target-ms 1000`，不能沿用历史 5 秒阈值作为通过标准。

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

## 2026-06-20 - 当前 gzip release runtime health 与 critical drain 复验

- 目标：在唯一 production 环境中验证 runtime worker、durable queue、dirty scope 和 App Status readiness 当前是否健康；只做只读巡检和受控 read model refresh enqueue，不执行业务写接口。
- 生产运行状态：release `codex-http-slo-gzip-probe-3546e985-20260619210708` 为 API、RabbitMQ dispatcher 和 worker 的 active WorkingDirectory；`fin-ops.service`、`fin-ops-rabbitmq-dispatcher.service` 和 20 个 worker unit 均为 active。
- Runtime health：本机 `/health` 与 `/health/ready` 返回 ready，`runtime_release.consistent=true`、`production_runtime_guard.consistent=true`、`runtime_blocker_count=0`。`runtime_sync_closure_gate` 的 `runtime_health` check 通过，snapshot 显示 `queue_backlog={}`、`failed_jobs=0`、`missing_required_worker_count=0`、`stale_required_worker_count=0`、`mismatched_required_worker_count=0`、`stale_dirty_scope_count=0`。
- Direct drain 证据：`read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 90` enqueue 15 个 critical read model refresh。首轮全部被 worker 处理为 outbox/dirty `done` 且 readiness `fresh` 或 `dirty_done`，但 5 个 scope 超过 5s target；聚焦复验后只剩 `invoice_lifecycle` 接近阈值，单项复验通过；最终完整 15 scope 复跑 15/15 pass，p95/max 约 `4122.628ms`。
- 当前结论：本轮没有 worker 卡住、queue 积压、failed job 或 readiness 未 fresh；当前 direct critical worker drain 已闭合。首轮长尾仍需作为性能观察项保留，后续真实业务写场景应继续看 enqueue-to-done p95/p99，而不是只看最终 fresh。
- Closure gate 外部缺口：未配置真实 user/admin auth 时，authenticated HTTP/SSE gate 会失败；未提供 `--write-scenario`、`--apply-write-scenarios` 和 `--write-approval-ticket` 时，write-operation E2E 必须保持 input_required。生产 route/API base path 的 gate 配置也必须与公网部署路径匹配，不能用本机 API 端口验证 SPA page shell。
- 验证命令：生产 systemd status；生产本机 `/health`、`/health/ready`；生产 `runtime_sync_closure_gate --base-url http://127.0.0.1:18001 --api-prefix '' --allow-unauthenticated-http --json`；生产 direct `read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 90`；生产 PostgreSQL 只读状态聚合。

## 2026-06-20 - Dependency refresh already-fresh guard

- 目标：修复生产 Workbench bank/turnover withdraw 后 `pending_invoice` read model 慢尾。只读证据显示 pending handler 自身耗时只有约 `25-176ms`，但多个 pending scope 因 `bank_detail_read_model_not_fresh` 反复 defer，并连续补投 `bank_detail:2026-03`，把 source version 从 `44635` bump 到 `44638`，导致下游等待被自身依赖 refresh 放大到约 `9.8s`。
- 影响范围：`RuntimeWorker._enqueue_dependency_refreshes(...)`；不改变业务写接口、read model scope contract、queue schema 或 handler projection。
- 关键决策：已有 guard 会在依赖 scope active 时不补投；本轮新增依赖 scope 已 fresh 时也不补投，只在 heartbeat payload 中记录 `already_fresh` 并继续 defer 当前事件。这样多个下游 scope 在依赖已经 fresh 后不会继续 bump 依赖 source version。
- 测试覆盖：`tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_bump_dependency_refresh_when_scope_already_fresh`，并保留 `already_active` 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py tests/test_write_operation_slo_audit.py -q`；`python3 -m py_compile backend/src/fin_ops_platform/services/runtime_worker.py tests/test_runtime_worker.py`。
- 未测风险：该修复尚未发布到生产，也未在真实 Workbench withdraw 场景重跑；`workbench:all` aggregate 约 `20.8s` 和 `cost_statistics` 2026-03 约 `7.2s` 仍需后续独立优化或重新归类为后台追赶 SLO。
