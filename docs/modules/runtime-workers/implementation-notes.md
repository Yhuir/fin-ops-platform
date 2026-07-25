# Runtime Worker 实施记录

## 2026-07-25 - Workbench/Cost access proof 有界复用

- 最新候选保留 gate-first 和 exact-scope 合同，但生产证据证明“下一次访问才登记 Cost child”仍有串行空档。当前 gate 发现 Workbench stale 时，同次只登记 exact Workbench 和当前 project/page 的 exact Cost child waiter，不登记 parent 或 sibling。
- 两个 event 携带同次 gate 已计算、token/scope 绑定且受 32 KiB 上限约束的 Workbench expected proof；Workbench/Cost worker 各自验证后复用 expected，并继续用 active generation actual 做 fail-closed 比较。Cost dependency token 只合并 active waiter，不用历史 done 短路完整 Cost freshness。
- 删除评估中的 proof cache/watermark 方案；没有新增表、migration、queue、worker、cache、API 或协调器。

## 2026-07-24 - Workbench generation-set 原子发布与 Cost 依赖顺序收敛（历史时序已由上节取代）

- 生产并发访问证明两个 Workbench 月份可以并行计算，但旧的 per-month publish lock 允许两个事务分别用中间 active-month set 写 all-scope stats；最终 generation-set digest 可能没有对应 stats，System Audit 因此在 confirm checkpoint fail closed，同时保存/统计争用把 handler 拉到约 3.3 秒。
- 最小修复保留 payload计算与 generation staging/COPY并行，只在重型数据写完后用一个 `workbench_generation_set` advisory transaction lock串行化 active切换与 all-scope stats。round 10 当时收窄为 gate-first 两次访问时序；2026-07-25 生产性能矩阵已证明该串行空档不能满足目标，因此登记时序由上节替代。generation-set 原子发布合同保持不变。

## 2026-07-24 - exact scope refresh 覆盖关系

- ensure/wakeup 原子去重不再只按 scope 判断：同一 scope 的覆盖顺序是 `force > full scope > partial delta`。新 delta/full/force 若未被 active event 语义覆盖，必须原子合并或创建 processing 后续事件；相同任务才 no-op。
- 该变化只在既有 PostgreSQL durable queue/repository 边界内完成，不增加协调器、transport、worker 或状态事实源；真实 PostgreSQL relation metadata merge 与定向 queue tests 已通过。

## 2026-07-24 - dependency handler proof 覆盖旧 readiness

- 生产并发访问证明 downstream handler 已用 canonical facts 判定 `*_read_model_not_fresh` 时，`app_status_readiness` 仍可能暂时显示依赖 fresh。旧 `already_fresh` 短路会阻止真实 dependency refresh，使 downstream event 每 250ms 原地 defer。
- Runtime worker 继续先跳过 active dependency；非 active 时直接委托现有 gateway 做 normalize、validate 和 durable 原子去重。没有新增 coordinator、queue、状态表或兼容分支。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- Worker lifecycle 触发 read model refresh 时必须走统一 scope policy/gateway 入队；worker 不直接拼接或投递成本统计等 read model 的业务 scope contract。
- `invoice_lifecycle:YYYY-MM` 遇到 pending-invoice 依赖未 fresh 时，worker 必须补投同月 `expense:all:YYYY-MM` 与 `income:all:YYYY-MM`，禁止生成 scope policy 会拒绝的裸月份。
- 非事务 read model refresh producer 由 architecture guard 约束：不得绕过 `ReadModelRefreshGateway` 直接调用 `RuntimeQueueRepository.enqueue_read_model_refresh(...)`。
- `bank_detail:all` 是显式 fan-out 命令，不是 downstream `*_read_model_not_fresh` 可自动推导的稳定 freshness 依赖 scope；下游 all-scope event 只能等待或补投可识别的具体月份 shard。
- Downstream handler 基于 canonical facts 抛出 `*_read_model_not_fresh` 后，该证明高于可能滞后的 readiness；worker 只允许 active dependency 短路，非 active dependency 必须交给正式 gateway 原子去重并补投。
- `*_read_model_not_fresh` 可携带 `parent_scope_keys=YYYY-MM,...` 表示同一 read model 的 parent shard 依赖；runtime worker 必须允许这类 same-scope parent refresh。若错误包含 `parent_generation_inconsistent`，即使 readiness 显示 fresh，也要强制补投 parent scope，因为 consistency failure 比 readiness 更接近发布边界。
- Same-scope parent dependency 的当前 event 必须使用 retry 级别退避，而不是全局 `dependency_not_fresh_delay_seconds` 的快速 retry；否则 RabbitMQ transport 下 `all` 聚合事件会被快速重新发布并抢占父月 shard，形成 backlog/refreshing 风暴。
- App Status read model registry、runtime worker registry、RabbitMQ dispatch、SLO smoke、migration storage contract 和 Redis/deploy env 模板必须保持本地 parity；生产 worker/read model 不允许新增第二套手写清单。
- `cost-tax` worker 只保留 `tax_offset.read_model.refresh` 兼容职责；`cost_statistics.read_model.refresh` 只由 `cost-statistics` 与 `cost-statistics-secondary` 两个同合同 bounded consumer 处理，二者不拥有第二投影或事实源。
- `job.outbox_events` worker claim hot path 是 runtime worker I/O 边界的一部分；active queue 必须保留 event-type-first priority index，不能靠业务 handler 内部 sleep/retry 或页面补丁掩盖 pickup 尾延迟。
- Workbench 与 Cost 的 sibling month 可各由两个 bounded PostgreSQL consumer 并行 claim；Workbench `all` fan-out 只能由 primary claim。每个 required instance 必须使用独立 worker kind，避免 App Health heartbeat 交叉满足。

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

## 2026-07-24 - Workbench/Cost sibling month bounded parallel consumers

- 目标：消除同一访问触发的 2026-02/2026-03 sibling month 在单 worker lane 串行排队，保持页面 access-to-fresh `p99<=3s`，不改变普通写事务。
- 影响范围：只修改 runtime worker registry、registry-derived manifest/deploy contracts、App Health required heartbeats 与对应测试；handler、event payload、durable queue、scope policy、projection 和业务 API 不变。
- 关键决策：保留 `workbench` primary 处理 month + `all` fan-out，新增 `workbench-secondary` 处理同 event type 但排除 `all`；保留 `cost-statistics` primary 并新增同 event type 的 `cost-statistics-secondary`。两个 secondary 均 PostgreSQL only，不引入第二 transport 或新队列；独立 worker kind确保实例级健康门真实有效。
- 旧路径与简化：没有恢复历史 Workbench aggregate lane，没有新增协调器、分片调度表、动态 autoscaling 或 per-page queue。deploy 继续完全由 registry 派生，两个 secondary 复用现有 owner env example。
- 测试与验证：registry/deploy/migration/Cost 定向合同合计 `182 passed`，真实临时 PostgreSQL Cost integration `6 passed`。生产发布后必须证明两个新增 instance 均为 current-effective、sibling months 不再串行、queue drain 且 System Audit 通过。

## 2026-07-22 - Invoice lifecycle 的 pending-invoice 依赖 scope 收敛

- 生产根因：`invoice_lifecycle:YYYY-MM` 等待 pending-invoice 输入时，通用 dependency mapper 把月份直接映射成 `pending_invoice:YYYY-MM`；正式 scope policy 拒绝该非法 scope，enqueue 异常被记录后 lifecycle event 继续短 defer，最终形成无进展循环并让多个依赖 lifecycle 的页面持续显示同步中。
- 最小修复：只在现有 `RuntimeWorker` dependency scope 推导中把 pending-invoice 月份展开为 `expense:all:YYYY-MM` 与 `income:all:YYYY-MM`；显式 all 展开为两个合法基础 scope。后续仍统一经过 `ReadModelRefreshGateway` 的 normalize/validate/active+fresh dedupe 和 PostgreSQL durable queue。
- 边界不变：不新增表、worker、read model、service、repository、event type 或 fallback；不改变 API/DTO、projection 业务规则或页面 I/O。
- 自动验证：`PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_runtime_worker.py tests/test_read_model_refresh_gateway.py tests/test_invoice_lifecycle_read_model_refresh.py tests/test_invoice_lifecycle_sql_projection.py tests/test_pending_invoice_service.py tests/test_runtime_queue.py`。

## 2026-07-16 - 删除 Workbench worker 同步 cache warmer

- 目标：让 Workbench worker 只负责 generation 发布、下游 fan-out 和 durable dirty completion，不承担页面查询与 Redis 写入。
- 影响范围：worker construction、Workbench refresh handler、page-cache helper、测试与 monitoring 文档。
- 关键决策：删除同步 warmer 和 env gate；保留 API query owner 的 fresh-gated versioned read-through cache，不新增后台预热任务。
- 测试覆盖：worker/refresh deletion guard、无 warmup publish 行为，以及现有 query facade cache hit/miss/down 合同。
- 未测风险：未部署、未操作真实 Redis 或 worker；统一发布后再做 cold/warm API 与 handler p95 验证。

## 2026-07-16 - Workbench worker 收口为单 lane

- 目标：让 registry、systemd env 和 handler 回到一个明确 owner，消除只服务已废弃全局聚合的独立 worker。
- 影响范围：`runtime_worker_registry.py`、Workbench worker env、runtime worker deploy helper、refresh handler 和相关合同测试。
- 关键决策：单一 `workbench` registration claim 全部 `workbench.read_model.refresh`；月份执行 active generation 发布，`all` 执行 bounded month fan-out。queue scope filter 能力保留给其它确有隔离需求的 event type，但 Workbench 不再使用。
- 旧逻辑清理：删除独立聚合 registration/env、旧 env 迁移函数和 aggregate drain 配置；部署激活仍由 registry 白名单自动 stop/disable 未登记实例。
- 测试覆盖：registry、deploy example、durable queue、relation producer 与 Workbench refresh handler 定向回归。
- 未测风险：按用户要求未部署，未验证真实 systemd 收敛和 PostgreSQL queue pickup latency。

## 2026-07-05 - Runtime Worker boundary close

- 目标：把 Runtime Worker 模块从 partial 收口为 closed，确认 worker 入口、queue、registry、deployment manifest、RabbitMQ transport 和 App Health readiness 的 I/O 边界都由当前 registry/durable queue 合同驱动。
- 影响范围：`app/worker.py`、`runtime_worker_handlers.py`、部署文档和 deploy runtime examples test；不改变 event type、handler、durable queue schema、dirty scope、readiness 或 worker env 示例行为。
- 关键决策：生产启动主合同是 `--registration <instance>` / `--worker-instance <instance>`；worker 矩阵只从 `runtime_worker_manifest` 派生。部署文档不再维护手写 worker 表或 systemd enable 清单。env 示例中的 `--enable-*` 兼容 flags 暂不批量删除，避免触碰现有服务器 env 迁移；registration 仍会覆盖 handler/event/scope lane。
- 旧逻辑清理：删除无调用 `_handle_import_fact_changed_event(...)` wrapper 和 `required_worker_dependency(...)` helper；移除部署文档中的 `file migration` RabbitMQ 文案、手写 worker 矩阵和 `sudo systemctl enable --now fin-ops-worker@...` 清单。
- 文档影响：同步 `boundary-io.md`、`tests.md`、`docs/operations/deployment.md` 和 `deploy/oa/README.md`。
- 测试覆盖：新增 `DeployRuntimeExampleTests.test_runtime_worker_docs_use_registry_manifest_instead_of_manual_matrix`；复用 platform runtime boundary guards 保护 Application/auth/GridFS/direct queue producer 禁止项。
- 未测风险：本地不证明真实 RabbitMQ broker、真实 Postgres migration、systemd worker 长时间 drain 或生产 grouped 1s SLO；这些仍需 staging/production gate。

## 2026-07-03 - Runtime queue enqueue timestamp boundary

- 目标：修复事务内 read model refresh 使用 PostgreSQL transaction-level `now()` 作为 outbox `available_at/created_at` 时，长业务事务会被错误计入 worker enqueue-to-done SLO 的问题。
- 影响范围：`RuntimeQueueRepository.enqueue_read_model_refresh_in_transaction(...)`、批量 `enqueue_read_model_refreshes_in_transaction(...)` 和 `write_operation_slo_audit`；不改变 dirty scope/outbox schema、event type、scope policy、worker handler、priority、dedupe 或 readiness 状态机。
- 关键决策：read model refresh outbox/dirty scope 写入使用 `clock_timestamp()` 表示实际语句执行时间；write-operation SLO 以 `available_at -> processed_at` 计算 enqueue-to-done，`created_at` 仅作为旧数据兼容回退和历史排序字段。
- 旧逻辑清理：禁止继续用事务开始时间解释 worker drain；如果 HTTP write step 本身慢，仍由 request timing 暴露，不混入 durable queue worker SLO。
- 文档影响：同步 read model 合同、runtime worker boundary 和测试矩阵。
- 测试覆盖：`tests/test_runtime_queue.py` 覆盖单条/批量 read model refresh 入队 SQL 保留 `clock_timestamp()` 和 `excluded.available_at`；`tests/test_write_operation_slo_audit.py::WriteOperationSloAuditTests::test_enqueue_duration_uses_available_at_instead_of_transaction_created_at` 覆盖 SLO 读取 available_at。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_workbench_uow_contract.py tests/test_write_operation_slo_audit.py tests/test_write_operation_e2e_smoke.py tests/test_write_operation_scenario_discovery.py -q`。
- 未测风险：生产需要发布后重新执行固定 write scenario，确认 outbox event 的 `available_at` 与 `processed_at` 已反映真实 worker drain；HTTP write step 2s+ 仍需继续按 Workbench facade/UoW timing 优化。

## 2026-07-03 - Write-operation E2E expectation-filtered SLO sampling

- 目标：固定各页面 write scenario / approval ticket 后，修复最小生产 smoke 使用 `--limit 1` 时把写后 outbox 事件采样也压到 1 条，导致真实必需 refresh 已完成却被报告为 missing 的问题。
- 影响范围：`write_operation_e2e_smoke`、`write_operation_slo_audit` 和生产运维说明；不改变业务写 API、scenario schema、approval ticket、read model refresh scope、worker handler 或页面行为。
- 关键决策：E2E smoke 的 write SLO 读取使用当前 scenario operation 的 expectation 作为 SQL 过滤条件，只读取相关 `event_type/scope_type/reason/action_name` outbox 事件；同时对事件采样设置有效下限。`write_operation_scenario_discovery --limit 1` 仍用于最小闭环 scenario 生成，但不再影响写后 SLO 事件窗口。
- 旧逻辑清理：禁止把全局 outbox since-started-at 的第一条事件当作完整写后同步证据；不再让 caller 通过人工记忆额外参数规避采样过小。
- 文档影响：同步 `docs/operations/monitoring.md` 和 runtime worker 测试矩阵。
- 测试覆盖：`tests/test_write_operation_e2e_smoke.py::WriteOperationE2ESmokeTests::test_write_slo_event_sample_uses_effective_floor_when_scenario_limit_is_one` 覆盖最小 limit 不漏必需事件；`tests/test_write_operation_slo_audit.py::WriteOperationSloAuditTests::test_recent_events_since_can_filter_by_operation_expectations_in_sql` 锁定 expectation-filtered SQL。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_write_operation_e2e_smoke.py tests/test_write_operation_slo_audit.py tests/test_write_operation_scenario_discovery.py -q`；`bash scripts/verify.sh docs`。
- 未测风险：本地测试不证明生产 1s SLO 达标；仍需发布后用标准 scenario 文件和 `FINOPS-WRITE-SMOKE-STANDING-20260702` 复跑 production write apply。

## 2026-07-03 - Workbench withdraw transaction duplicate I/O removal

- 目标：固定 Workbench withdraw write-operation gate 中，`workbench_relation` outbox 事件看似 publish 延迟约 2.9s，但进一步对比 HTTP step 与 event visibility 后确认主要窗口来自 withdraw HTTP 事务耗时；需要从写事务内移除重复 relation snapshot/freshness I/O。
- 影响范围：`WorkbenchRelationCommandService.withdraw_relation(...)` submit 路径；不改变 runtime queue、RabbitMQ dispatcher/consumer、event type、scope policy、dirty scope 或 worker handler。
- 关键决策：dispatcher poll 已是 `0.05s`，不能继续在 worker/dispatcher 层堆补丁。submit 路径复用同一个 canonical pair-service snapshot 计算 preview lock 和执行 withdraw，只做一次 relation read model fresh precondition。
- 旧逻辑清理：禁止在 submit 事务内部调用 public preview API 重新加载 relation snapshot；禁止重复 fresh check 扩大 transaction window。
- 文档影响：同步 workbench-relations boundary、implementation notes 和测试矩阵。
- 测试覆盖：`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_withdraw_relation_submit_reuses_loaded_snapshot_for_preview_lock`，并复跑 Workbench withdraw UoW/API delegation 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_link_preview_and_submit_delegate_to_relation_command_service tests/test_workbench_write_characterization.py::WorkbenchWriteCharacterizationTests::test_withdraw_link_uses_uow_transaction_when_available tests/test_workbench_relation_sql_projection.py -q`。
- 未测风险：需发布后复跑固定 scenario/ticket，确认 HTTP write step 和 outbox enqueue-to-done 均收敛。

## 2026-07-03 - Workbench relation changed rebuild source-object补读快路径

- 目标：固定 write-operation Workbench withdraw 场景中，撤回写入成功但 `workbench_relation.read_model.refresh` enqueue-to-done 超过 1s；生产 runtime result 显示 changed rebuild handler 接近 1s，需先移除 handler 内重复源对象读取。
- 影响范围：`workbench-relation` worker 调用的 SQL projection builder；不改变 durable queue claim/complete/defer 状态机、event type、scope policy、dirty scope、readiness 或 RabbitMQ envelope。
- 关键决策：worker handler 不做 sleep/retry/cache 补丁；把慢点收敛到 projection 输入 I/O。普通同月 relation rebuild 只读取一次月分片源对象；跨月 relation 缺失成员只按 row_id 和 row type 补读必要源表。
- 旧逻辑清理：禁止让 changed rebuild 在 skip 不成立时无条件执行第二次全月 bank/OA/invoice 读取；这会污染 fixed write-operation SLO 链路。
- 文档影响：同步 workbench-relations、read-models 和 runtime-workers 测试矩阵。
- 测试覆盖：`tests/test_workbench_relation_sql_projection.py` 新增同月源表读取次数和跨月显式补读断言。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_sql_projection.py -q`；`python3 -m py_compile backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py`。
- 未测风险：需要生产发布后复跑 fixed write-operation apply；如果 handler 已收敛但 enqueue-to-done 仍超 1s，再按 queue pickup/lane 证据处理，不在 projection 里扩大缓存。

## 2026-07-03 - Bank batch unchanged skip source-version probe

- 目标：让 bank-flow/no-OA 月份 read model worker 在 source_versions 未变化时先跳过，再决定是否读取交易行、分类行和关系行，压缩 full critical read model smoke 的 handler 长尾。
- 影响范围：bank-flow/no-OA read model refresh handler、BankTransactionTagReadFacade source-version-only I/O、BankBatch/NoOaBankBatch application service source-version precheck；不改变 queue schema、event type、dirty scope/readiness 状态机或 API payload。
- 关键决策：worker 内部可在当前 dirty scope 为 `processing` 时读取持久化 summary 并接受 `refreshing` 状态做 unchanged 比较；页面/API 读路径仍必须保持 fresh gate，不允许返回旧 projection 并伪装 fresh。`all` scope 不走月份 precheck，避免额外 snapshot 成本。
- 旧逻辑清理：unchanged scope 不再先执行 `bulk_get_for_rows(...)`、relation `list_by_month(...)` 或 snapshot save；无法证明 source_versions 一致时才进入完整 rebuild。
- 文档影响：同步 read-models、bank-flow、no-OA 实施记录和测试矩阵。
- 测试覆盖：`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_source_versions_for_scope_keys_uses_scope_summary_without_loading_rows`、`tests/test_bank_flow_rule_batch_application_service.py::BankFlowRuleBatchApplicationServiceTests::test_bank_flow_scope_source_versions_use_probe_ports_before_row_loading`、`tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_unchanged_scope_skips_rebuild_and_snapshot_save`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests tests/test_bank_flow_rule_batch_application_service.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_read_model_manifest.py -q`。
- 未测风险：需发布后用生产 read model SLO 和 write-operation apply 证明真实 worker 并发下的耗时收敛。

## 2026-07-03 - 固定 write-operation scenario 与常驻审批 ticket

- 目标：把各页面生产写入 smoke 的 scenario 与 approval ticket 固定为可执行合同，避免每轮生产验证都临时询问、临时选候选或重复放大同一月份写入。
- 影响范围：`write_operation_scenario_discovery`、write-operation E2E/SLO 工具输入、deploy env 示例、runtime worker 测试矩阵和运维治理文档；不改变业务 API、权限、审计或 read model payload shape。
- 关键决策：标准 scenario path 是 `/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json`，标准 ticket 是 `FINOPS-WRITE-SMOKE-STANDING-20260702`。`turnover-ledger`、`reconciliation-workbench`、`workbench-relations`、`no-oa-bank-batches` 使用 standing apply；银行明细、账户余额、待找发票、发票生命周期、税金、成本、搜索等页面使用 fan-out evidence；导入、设置、数据重置页面不允许常驻生产 apply，只能用 staging 或单次审批 scenario。
- 旧逻辑清理：scenario discovery 不再输出 `requires_manual_approval_before_apply` 口径；每个 operation 每轮最多生成 1 个受控 scenario；no-OA withdraw 候选必须匹配 active `no_oa_bank_batch` relation，不能把 `bank_flow_rule_batch` relation-mode 候选送入 no-OA withdraw endpoint。
- 文档影响：同步 `docs/operations/runtime-worker-governance.md` 和本测试矩阵。
- 测试覆盖：`tests/test_write_operation_scenario_discovery.py` 覆盖页面策略、常驻 ticket、scenario cap 和 no-OA active relation contract；`tests/test_write_operation_e2e_smoke.py` 与 `tests/test_write_operation_slo_audit.py` 继续保护 apply/audit 合同；`tests/test_deploy_runtime_examples.py` 保护 env 示例固定输入。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_write_operation_scenario_discovery.py tests/test_write_operation_e2e_smoke.py tests/test_write_operation_slo_audit.py -q`。
- 未测风险：生产 apply 仍需要真实 OA/Admin auth 和可连接的生产 release；本轮发布在 SSH 密码提示处中止，尚未用新 release 复跑 write-operation apply。
- 后续事项：生产发布后先运行 discovery 写入标准 scenario file，再用标准 ticket 执行 apply，并把 operation-to-fresh 结果记录到 read model/runtime closure evidence。

## 2026-07-03 - Runtime queue claim hot path index

- 目标：收敛 grouped 1s read model smoke 中的 worker pickup/claim 尾延迟。Search 和 invoice lifecycle handler 已分别降到约 `231ms` / `300ms` 后，仍存在 handler 很短但 enqueue-to-fresh 超 1s 的漂移，说明部分长尾落在 durable queue claim I/O。
- 影响范围：新增 PostgreSQL migration `0086_runtime_queue_claim_hot_path.sql`；不改变 `RuntimeQueueRepository.claim_next(...)` 的状态机、priority 排序、scope filter、RabbitMQ envelope、dirty scope、readiness 或任何业务 projection。
- 关键决策：在 `job.outbox_events` active queue 上新增 `outbox_events_claim_event_type_priority_idx`，索引列覆盖 `event_type`、`status`、priority rank、`available_at`、`created_at`、`id`，并限制 `where status in ('pending', 'processing')`。索引用于让不同 worker lane 先按 event type 收窄候选，避免 grouped smoke 扫描无关 event type。
- 文档影响：同步 runtime worker `boundary-io.md`、`tests.md`、read model implementation notes 和 operations runbook。
- 测试覆盖：`tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_runtime_queue_claim_hot_path_index_is_declared`；复跑 `tests/test_runtime_queue.py`、`tests/test_runtime_worker.py` 与 Workbench refresh handler tests，证明 queue/worker 语义不变。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_migrations.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_preserves_hot_priority_for_all_aggregate_after_month_publish tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_uses_coalescing_all_aggregate_enqueue_when_available tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done -q`。
- 未测风险：本地 SQL 合同不能证明生产 optimizer 选择和 grouped 1s 收益；必须发布 migration 后复跑 critical grouped read model smoke、scope contract 和 write-operation gate。
- 后续事项：生产发布前确认 migration 窗口；发布后重点比较 `workbench:2026-02`、`invoice_lifecycle:2026-02` 和其它短 handler scope 的 enqueue-to-fresh 与 handler delta。

## 2026-07-02 - Runtime worker durable queue poll latency baseline

- 目标：解决生产 read model 1s SLO 分层中暴露的 worker pickup latency。No-OA targeted handler 已约 `886.764ms`，但 enqueue-to-fresh `1644.218ms`，继续在业务 service/repository 内堆补丁不是正确边界。
- 影响范围：`RuntimeWorkerConfig` 默认 idle poll、worker CLI 默认值、PostgreSQL worker env 模板、`finops-ensure-runtime-workers` env 迁移逻辑；不改变 durable queue schema、RabbitMQ transport、read model scope、handler projection 或业务写接口。
- 关键决策：PostgreSQL durable queue worker 默认 idle poll 收敛到 `0.25s`；模板中历史 `--poll-interval-seconds 2` 改为 `0.25`；deploy helper 仅在已有生产 env 精确命中旧 `2s` 配置且当前 release 模板声明 `0.25s` 时替换该参数，不重装 env 文件，避免覆盖 RabbitMQ 灰度、自定义 event types 或 per-worker throughput。Release deploy 必须在 activate 前安装当前 release 的 `finops-ensure-runtime-workers` helper，防止服务器继续调用旧 helper。
- 保留例外：`workbench-matching` 是独立的脏 scope 批处理 worker，仍保留显式 `--poll-interval-seconds 5`，不纳入 read model outbox pickup latency 默认值。
- 测试覆盖：`RuntimeWorkerTests.test_default_poll_interval_is_fast_enough_for_read_model_slo`、`DeployRuntimeExampleTests.test_required_worker_env_examples_do_not_pin_legacy_slow_poll_interval`、`DeployRuntimeExampleTests.test_runtime_worker_env_install_migrates_only_legacy_poll_interval`、`DeployOAScriptTest.test_release_remote_script_uses_versioned_release_and_deploy_control`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py tests/test_deploy_runtime_examples.py -q`；`git diff --check`。
- 未测风险：该切片降低 pickup latency，但不能证明所有 handler 本身都低于 1s；仍需发布后复跑 critical read model SLO、健康检查、scope contract 和写操作 audit。若 1s 仍失败，应按 SLO profile 定位 handler 热点或 App/API 读路径，而不是恢复慢 poll。

## 2026-06-25 - Workbench matching worker constructor port wiring

- 目标：修复生产 `fin-ops-worker@workbench-matching.service` 启动后反复重启的问题；生产日志显示 `WorkbenchMatchingOrchestrator.__init__()` 拒绝旧关键字 `pair_relation_service`。
- 影响范围：`WorkbenchMatchingWorkerFactory.build_dirty_scope_worker(...)` 的构造 wiring；不改变 PostgreSQL durable queue、dirty scope、readiness、RabbitMQ transport、Workbench matching rules 或 read model projection 语义。
- 关键决策：`WorkbenchMatchingOrchestrator` 的当前合同是 `relation_read_port: WorkbenchMatchingRelationReadPort`；runtime worker 继续从 `WorkbenchPairRelationService.from_snapshot(...)` 读取关系快照，但只通过 `WorkbenchMatchingRelationReadPort(pair_relation_service)` 暴露读端口给 matching orchestrator。`pair_relation_service` 仍用于 relation command service 的写命令边界。
- 文档影响：同步本实施记录、runtime worker 测试矩阵和 refactor controller analysis；状态机定义不变。
- 测试覆盖：扩展 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_workbench_matching_uses_relation_read_port_not_pair_service`，防止 runtime worker factory 再向 orchestrator 传 `pair_relation_service=`。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地验证不启动真实 systemd worker；生产 worker restart/convergence 需要后续独立 deploy/runbook 证明。
- 后续事项：本修复提交后，选择单独的生产 deploy/convergence 边界，验证 `fin-ops-worker@workbench-matching.service` 不再 restart loop。

## 2026-06-24 - Worker queue/App Status contract audit hardening

- 目标：审计并加固 worker registry、durable queue、App Status registry 和 operation barrier 的合同守卫，确认不引入 Go Worker、不写生产 queue/readiness。
- 影响范围：本地测试与模块文档；不改变 runtime worker loop、PostgreSQL queue schema、RabbitMQ transport、readiness 写入或生产状态。
- 关键决策：非事务 refresh producer 继续由 `ReadModelRefreshGateway` 与 scope policy registry 保护；事务内 writer 保留同事务 dirty/outbox 写入，但必须由测试证明其输出 scope 仍符合共享 scope policy；App Status/worker registry 需要双向 parity，避免新增 read-model worker 漏进全局状态 plane。
- 文档影响：同步 runtime-workers 测试矩阵，并新增 `.planning/refactors/modular-io-boundaries/parallel/handoffs/T3-worker-queue-app-status.md` 作为本轮审计交接记录。
- 测试覆盖：新增 `tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_worker_read_model_registrations_are_visible_to_app_status_registry` 和 `tests/test_postgres_repositories_boundaries.py::test_workbench_relation_transactional_refresh_scopes_match_scope_policy_contracts`。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地测试不连接真实 PostgreSQL/RabbitMQ/systemd，不证明真实 worker drain；生产运行仍以 `infra-smoke`、read model SLO smoke、write-operation audit 和 App Status 只读证据闭环。

## 2026-06-24 - T7 Go admission evidence deferred

- 目标：准备 Go/Fiber/Go Worker admission evidence，但不实现 Go、不改变 Python runtime 行为。
- 影响范围：Go hot-path admission planning、Workbench matching compute evidence、runtime worker admission gates；不改变 worker registry、durable queue、dirty scope、readiness、RabbitMQ transport 或 Redis cache。
- 关键决策：`workbench:matching-grouping-check` 属于 `11-GO-HOT-PATH-CARVE-OUT.md` P1-A candidate，可以被评估，但本轮 gate 失败，记录为 `go-candidate-deferred`。失败原因是缺少真实 p95/p99 performance evidence、Workbench active generation enqueue-to-fresh proof、shadow diff evidence 和 rollback switch proof。
- 文档影响：新增 `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-t7-admission-evidence.md` 和 T7 handoff；长期 runtime worker 事实源不变。
- 测试覆盖：复跑 `tests.test_workbench_compute_evidence`，证明 collector read-only 且缺 evidence 时 fail closed；复跑 Workbench compute Python reference ownership 和 Go shadow admission guard。
- 验证命令：`env -u FIN_OPS_POSTGRES_DATABASE_URL -u DATABASE_URL PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.workbench_compute_evidence --json` 返回 `configuration_missing`、`production_evidence_required=true`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_compute_evidence -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_reference_state_writes_stay_in_python_boundaries tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v`。
- 未测风险：本地无 PostgreSQL URL，未证明真实 Workbench high-row performance、worker drain、query timing、shadow equivalence 或 operational rollback。Go/Fiber/Go Worker implementation 继续 blocked。

## 2026-06-22 - App Health active repair current-effective 聚合

- 目标：修复 Workbench active repair 已经 pending/processing 时，App Health 仍把旧 generation consistency failure 提升成全局 `blocked` 的矛盾状态。
- 影响范围：`/api/app-health` snapshot、App Status overview、Workbench read model dependency summary；不改变 worker claim、dirty scope、readiness 或 RabbitMQ transport。
- 关键决策：runtime/App Health 聚合必须先看 current-effective refresh facts。`read_model_status=refreshing/rebuilding` 表示 worker 正在修复，旧 consistency failure 只保留在诊断字段；没有 active repair 的 failed/dead-letter 才是 blocker。
- 文档影响：同步 runtime-workers、read-models 和 reconciliation-workbench 状态机/测试矩阵。
- 测试覆盖：新增 `tests/test_app_health_api.py::AppHealthApiTests::test_app_health_keeps_workbench_consistency_failure_busy_during_active_repair`，并复跑 App Status overview/runtime monitoring 相关回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_app_health_api tests.test_app_status_overview_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier tests.test_runtime_monitoring -v`。
- 未测风险：本地 fake runtime 不证明生产 worker drain；发布后仍需观察 `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.app_status_readiness` 是否自然收敛。

## 2026-06-22 - Production runtime parity guard

- 目标：防止生产 schema、worker、RabbitMQ、Redis 与本地测试覆盖再次分叉。历史问题不是某个 worker/Redis/RabbitMQ 事实源重写，而是多个 registry、migration 和 env 模板缺少交叉断言，新增 read model 容易只改一处。
- 影响范围：runtime worker registry、read model SLO smoke、PostgreSQL migration table baseline、RabbitMQ deploy env、Redis runtime env contract；不改变 worker loop、queue schema、RabbitMQ envelope 或 Redis helper 行为。
- 关键决策：继续保持 PostgreSQL durable queue/readiness 为状态事实源，RabbitMQ 只做 transport/wakeup，Redis 只做 fresh gate 后 cache。新增本地门禁要求 `APP_STATUS_READ_MODEL_REGISTRY` 每个 key 都能映射到 required worker、refresh event、RabbitMQ dispatch event、critical SLO smoke scope 和 migration storage contract；共享 `fin-ops.rabbitmq-worker.env` 不得设置 `FIN_OPS_QUEUE_BACKEND`，只能 per-worker 灰度；Redis 模板变量必须和 `RuntimeRedisSettings.from_env()` 对齐。
- 文档影响：同步本记录、runtime-workers/read-models 测试矩阵和 worker/read model 运维治理文档。
- 测试覆盖：新增 `tests/test_runtime_worker_registry.py`、`tests/test_read_model_slo_smoke.py`、`tests/test_postgres_migrations.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_runtime_redis.py` 中的 parity guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_registry tests.test_read_model_slo_smoke tests.test_postgres_migrations tests.test_deploy_runtime_examples tests.test_runtime_redis -v`。
- 未测风险：本地 guard 不连接真实 broker、Redis、systemd 或生产 PostgreSQL；真实 drain 仍由 `infra-smoke`、RabbitMQ staging preflight 和生产/staging read model SLO smoke 证明。

## 2026-06-21 - Same-scope parent dependency 长退避防止 all 聚合抢占

- 目标：修复 Workbench `all` aggregate-only 事件在父月 scope 未 fresh 时每 0.25s defer/republish，持续抢占 `2026-01/02/04` 月 scope refresh，导致 App Status 保持 `refreshing/backlog` 的问题。
- 影响范围：`RuntimeWorker` dependency-not-fresh defer 策略、RabbitMQ transport 下同一 read model parent/aggregate 调度；不改变 PostgreSQL durable queue、readiness、dirty scope 或 Workbench projection 业务逻辑。
- 关键决策：普通跨 read model 依赖仍使用 `dependency_not_fresh_delay_seconds` 短退避；错误中同时出现当前 event scope type 和 `parent_scope_keys=...` 时，当前 event 用 `retry_delay_seconds` 级别退避，并先通过 dependency refresh path 补投/让出 parent month scope。这样 parent shard 有机会先被 worker claim，`all` 聚合不会以亚秒级重发淹没队列。
- 文档影响：更新 runtime-workers README、测试矩阵、系统状态实施记录和本 GSD debug 记录。
- 测试覆盖：加强 `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_requeues_same_scope_parent_when_generation_is_inconsistent`，断言 same-scope parent dependency defer 使用 `retry_delay_seconds`，同时保留普通 dependency-not-fresh 测试证明短退避不变。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py -q`。
- 未测风险：本地测试证明调度 contract；生产仍需发布后观察 Workbench parent month scopes 是否先 drain，再确认 App Status queue/read model attention 清零。

## 2026-06-21 - Same-scope parent dependency refresh

- 目标：修复 `workbench:all` aggregate-only 遇到 parent generation inconsistent 时只能把 all 事件标 failed、无法自动重刷 parent month scope 的问题。
- 影响范围：`RuntimeWorker._dependency_refresh_scopes(...)`、dependency-not-fresh defer、Workbench all-scope aggregate 自愈链路。
- 关键决策：默认仍禁止从同一 scope type 的 `*_read_model_not_fresh` 盲目补投自己，避免循环；只有错误明确携带 `parent_scope_keys` 时才允许补投 same-scope parent。`parent_generation_inconsistent` 标记会跳过 fresh readiness 短路，但仍尊重 active refresh dedupe。
- 文档影响：更新本实施记录和测试矩阵；运行事实源和 queue 状态流转不变。
- 测试覆盖：新增 `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_requeues_same_scope_parent_when_generation_is_inconsistent`。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产若历史事件已 `failed`/`dead_lettered` 而没有新的 pending/backlog 同 scope 事件，需要用 `runtime_queue_ops requeue` 或重新 enqueue 对应 read model refresh 后才会进入新自愈路径。

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
- 测试覆盖：`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_does_not_let_older_done_event_cover_newer_processing_event`、`tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot`、`tests/test_import_processing_service.py::test_file_import_confirm_job_returns_import_write_targets`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_import_fact_changed_handler_completes_matching_dirty_scope`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_invoice_relation_scope_helpers_split_input_and_output_file_months`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_tax_offset_scope_helpers_ignore_bank_transaction_files`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes`。
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
- 关键决策：新增 `RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS`，当前默认 `0.05s`。RabbitMQ consumer 独立按该间隔调用 `RuntimeWorker.run_once()` 扫 PostgreSQL durable queue；`process_data_events(...)` 的 time limit 也不得高于该 fallback 间隔，否则无消息时仍会硬等 1s。heartbeat 仍低频记录，避免把 idle heartbeat 写成高频噪声。这样 RabbitMQ publish 失败或 envelope 丢失时，PostgreSQL fallback 仍能满足 1s SLO。
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

## 2026-06-20 - Dependency refresh already-fresh guard（已于 2026-07-24 取代）

- 目标：修复生产 Workbench bank/turnover withdraw 后 `pending_invoice` read model 慢尾。只读证据显示 pending handler 自身耗时只有约 `25-176ms`，但多个 pending scope 因 `bank_detail_read_model_not_fresh` 反复 defer，并连续补投 `bank_detail:2026-03`，把 source version 从 `44635` bump 到 `44638`，导致下游等待被自身依赖 refresh 放大到约 `9.8s`。
- 影响范围：`RuntimeWorker._enqueue_dependency_refreshes(...)`；不改变业务写接口、read model scope contract、queue schema 或 handler projection。
- 历史决策：当时新增 readiness fresh 短路以避免重复 bump；2026-07-24 生产证据证明 handler canonical proof 与 readiness 发生冲突时，该短路会让真实依赖永远不修复，现已删除。active guard 与 durable gateway 原子去重继续承担防重复职责。
- 测试覆盖：原 `test_run_once_does_not_bump_dependency_refresh_when_scope_already_fresh` 已由 `test_run_once_handler_proof_overrides_stale_fresh_readiness` 取代，并保留 `already_active` 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py tests/test_write_operation_slo_audit.py -q`；`python3 -m py_compile backend/src/fin_ops_platform/services/runtime_worker.py tests/test_runtime_worker.py`。
- 未测风险：该修复尚未发布到生产，也未在真实 Workbench withdraw 场景重跑；`workbench:all` aggregate 约 `20.8s` 和 `cost_statistics` 2026-03 约 `7.2s` 仍需后续独立优化或重新归类为后台追赶 SLO。

## 2026-07-03 - Workbench UoW read model refresh batch enqueue

- 目标：压缩 Workbench relation withdraw/confirm 写事务内的 dirty scope/outbox 写入耗时。生产样本显示 `workbench_relation` handler 已低于 1s，但 POST 到 outbox 可见仍接近 2.8s；瓶颈集中在同一业务事务内对多个 read model target 逐个执行入队 SQL。
- 影响范围：`RuntimeQueueRepository`、`RuntimeQueueReadModelRefreshWriter`、`WorkbenchWriteUnitOfWork`。不改变 runtime worker claim、handler、readiness、RabbitMQ envelope 或页面 API response shape。
- 关键决策：新增 `RuntimeQueueRepository.enqueue_read_model_refreshes_in_transaction(...)`，用一个 CTE 批量写 `job.read_model_dirty_scopes` 与 `job.outbox_events` 并按输入顺序返回 event；`RuntimeQueueReadModelRefreshWriter.enqueue_refreshes(...)` 优先调用批量接口，旧 queue 实现仍 fallback 单条入队；`WorkbenchWriteUnitOfWork` 对支持批量 writer 的生产链路一次性提交 targets，并校验返回 event 数量。
- 边界：批量入队仍使用相同 source_version bump、pending dedupe key、priority、trace_id 和 JSON payload 合同；它不是新的状态事实源，也不允许绕过 scope policy/target planner。`Application._workbench_uow_repository_factory(...)` 继续注入 `PostgresWorkbenchRelationRepository(transaction, enqueue_refreshes=False)`，避免 repository hidden fan-out 回到生产主链路。
- 本地保护：`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_enqueue_read_model_refreshes_in_transaction_batches_dirty_scope_and_outbox_writes`、`tests/test_workbench_uow_contract.py::WorkbenchUoWContractTests::test_read_model_refresh_writer_uses_batch_repository_interface_when_available`、`test_relation_write_uow_uses_batch_read_model_refresh_writer_when_available`。
- 未闭合：本地测试证明 I/O 合同与 UoW wiring；必须发布后用固定 `/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json` 与 `FINOPS-WRITE-SMOKE-STANDING-20260702` 复跑 Workbench withdraw 写操作 SLO，才能确认生产 POST/outbox 可见耗时降到目标内。

## 2026-07-15 - 未注册 worker 实例发布收敛

- 目标：修复生产残留 WIP secondary worker 不在当前 registry、env 已缺失但仍被 systemd 持续重启的问题。
- 影响范围：runtime worker manifest、release activate 控制脚本、部署合同测试与 worker 运维文档；不改变 event、scope、queue、read model、API 或数据库结构。
- 关键决策：registry 是唯一允许运行实例集合。激活 release 时只对已启用、运行或失败的未注册 `fin-ops-worker@*.service` 执行 stop/disable；不删除 env，保持回滚可逆。禁止把历史/WIP 实例重新登记为正式 worker 来掩盖配置缺失。
- 生产验收：发布后所有未注册实例必须为 disabled/inactive，注册 required worker 必须 active，durable queue 与 dirty scope 必须 drained，readiness 必须 ready。
- 测试覆盖：`RuntimeWorkerRegistryTests.test_manifest_cli_lists_required_instances_and_env_examples`、`DeployRuntimeExampleTests.test_deploy_control_retires_unregistered_worker_instances_before_restart`。

## 2026-07-20 - 删除无收益的 Turnover secondary 实验

- 生产反证：部署 `turnover-ledger-secondary` 后，confirm response-to-fresh 仍为 `4.46s`，withdraw 从单 worker 的 `1.28–1.49s` 退化到 `4.33s`，另有一次数据库竞争长尾达到 `11.64s`。双 consumer 没有解决 own source 重建，反而让相同 projection 争用数据库。
- 决策：从 registry、manifest、env、部署文档、测试和 active module contract 完整删除 secondary，并恢复原 CLI worker-kind 推断。部署控制会按既有“退役未注册实例”合同自动 stop/disable 生产旧实例，保留回滚能力。
- 替代方案不在 worker 层：现代 closure 改为 canonical Workbench relation 单事实写入，使 turnover 只执行既有 relation-context refresh；不再通过并发 worker 掩盖重复事实写入。

## 2026-07-22 - 专用 matching worker timeout 与失败 scope 恢复

- 根因：通用 `RuntimeWorker` 会应用 `--statement-timeout-seconds`，但只启用 `workbench-matching` 时入口在构造通用 worker 前直接进入专用 dirty-scope loop，导致 env 声明的 120 秒未生效、PostgreSQL connection 使用 10 秒默认值。
- 修复：worker entry 在所有 handler 分支前通过既有 `RuntimeQueueRepository.set_statement_timeout_seconds(...)` 应用同一 config；通用 worker 后续重复设置相同值，不改变其它 registration 合同。
- 恢复入口：`workbench_matching_scope_retry_ops` 只允许 failed exact month，dry-run 生成包含当前 status/attempt/request/error hash/source versions 的 fingerprint，execute 漂移即零写；写入复用 matching repository，不暴露 SQL/DSN。
- 不变项：未新增 worker、event type、queue/table、HTTP API 或 fallback；matching claim、relation UoW、heartbeat 和 complete/fail owner 不变。
