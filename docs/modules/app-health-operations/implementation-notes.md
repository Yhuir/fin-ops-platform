# 系统状态 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- App Health / App Status 是全局运行事实的只读投影，不是页面状态聚合器。前端只展示后端 `app_status`，不能用当前 route、表格 loading 或组件本地状态推导 green/yellow/red。
- 绿色状态必须有 readiness 证明。registry 中的 read model 如果缺少 readiness 记录，必须 busy/yellow；runtime snapshot unavailable 必须 blocked/red，不能空 green。
- Operations dashboard 是 admin-only 只读入口，不执行 retry、acknowledge、requeue、republish 或 repair。运维动作仍走 runbook/CLI/API 专门入口。
- Registry 强一致是本模块的核心防线：新增页面、read model、worker、job type 或 dependency 时，必须同步 domain/read model/job/dependency/worker registries 和测试。
- 本模块首轮闭环状态为 `documented-risk`：本地测试覆盖 service/API/UI contract，真实 systemd/RabbitMQ/Redis/Nginx SSE/大库指标仍需 staging/生产 smoke。

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

## 2026-06-19 - Ready 与 Runtime Read Model 闭环边界

- 目标：明确 `/health/ready` 返回 ready 不等于所有 read model 都已完成业务同步，并补齐本次发票导入后 Runtime Read Model 残留的状态框闭环。
- 影响范围：App Health/App Status 运行口径、`read_model.app_status_readiness` 非 fresh 诊断、生产 ready smoke；不改变 `/health/ready` contract。
- 关键决策：ready endpoint 仍是部署和基础运行门禁；完整同步闭环必须同时证明 `job.outbox_events` 无 dead-letter/current backlog、`job.read_model_dirty_scopes` 无 active dirty scope、`read_model.app_status_readiness` 无 current non-fresh 记录。历史 dead-letter 只有在后续 fresh/done 证明覆盖后才能归档。
- 文档影响：同步 read-models/runtime-workers 实施记录；App Status 产品文案不变。
- 测试覆盖：本轮新增 `pending_invoice` scope policy 单测，避免非法 readiness 进入状态框；生产验证用只读 SQL 和 `runtime_queue_ops` dry-run/execute 证明 current state 收敛。
- 验证命令：见本轮最终交付说明。
- 未测风险：真实 App Status popover 的浏览器可见性仍需用户重新导入发票后观察；后端状态事实已经清零。
- 后续事项：排查“同步中”问题时，先区分 ready gate、App Status current-effective state、以及页面级 read model freshness，不要只凭 `/health/ready` 下结论。

## 2026-06-19 - App Status 导入任务进度文案

- 目标：把上传/导入过程的用户可见状态集中放进运行状态框，并显示导入对象与进度，例如“正在导入发票 210/500”。
- 影响范围：`AppStatusIndicator` background task 展示、发票/ETC/银行流水导入页的 `file_import` job feedback；不改变后端 job payload contract。
- 关键决策：前端状态框优先使用 job `type`、`affected_domains` 与 `route` 推断导入对象名：发票、ETC发票、银行流水。`current/total` 存在且 `total > 0` 时显示为 `正在导入<对象> current/total`；缺少进度时显示 `正在导入<对象>`，避免依赖后端 `short_label` 中的历史空格或泛化文案。
- 文档影响：同步发票导入和关联台实施记录；系统状态 API contract 不变。
- 测试覆盖：`web/src/test/AppStatusIndicator.test.tsx` 覆盖发票导入 `210/500` 和 ETC 导入进度在状态框中的展示。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地测试覆盖状态框 DOM；真实 SSE/轮询延迟、生产 task current/total 是否随导入阶段稳定推进仍需发布后导入 smoke。

## 2026-06-18 - App Status requeued failure current-effective merge

- 目标：修复同一 read model scope 旧 `failed` 记录被新 `pending/processing` 重试覆盖后，App Health 仍把旧错误显示为当前失败的问题；本次现场表现为 `cost_statistics active:2026-03` 重新 processing 时仍显示 `deadlock detected`。
- 影响范围：`RuntimeMonitoringRepository.app_status_runtime_snapshot()` 的 read model scope merge、App Health / App Status current-effective 状态展示；不改变 readiness、dirty scope 或 runtime queue 事实源。
- 关键决策：同一 `(read_model_key, scope_type, scope_key)` 的 readiness/dirty scope 先合并再推导当前状态。只要同一 scope 有当前 `pending/processing`，当前状态显示 `refreshing` 并清空 current `last_error`；旧 `failed` 只保留为历史诊断，不再阻断当前页面状态。
- 文档影响：更新本模块 `state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增 `tests.test_app_status_overview_service.AppStatusRuntimeRepositoryTests.test_runtime_repository_treats_requeued_cost_statistics_deadlock_as_refreshing`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service -v`。
- 未测风险：本地 fake runtime connection 覆盖语义；真实生产 App Health 需要发布后通过 `/api/app-health` 或 popover smoke 确认旧 failed + 当前 processing 不再显示为当前失败。

## 2026-06-16 - Health readiness current-effective blocker gate

- 目标：让 `/health/ready` 的 runtime blocker 口径与 App Status current-effective 口径一致，避免历史 `cost_statistics` 裸 `all` / `YYYY-MM` scope 和非 current-effective optional worker heartbeat 持续污染 readiness gate。
- 影响范围：`RuntimeMonitoringRepository.ready_health_summary()`、ready payload compact worker status summary、health-ready probe 生产门禁；不改变 `/metrics` 完整诊断、App Status 历史诊断或 read model scope contract repair 脚本。
- 关键决策：ready 轻量 summary 只统计 current-effective dirty/outbox/failed/stale/publish/read-model failure facts；legacy cost statistics scope 继续通过 repair manifest 和历史诊断暴露，不作为当前 ready blocker。compact `worker_status_counts` 跳过 `current_effective=false` 的历史 worker，但仍保留 bounded problem samples 供运维定位。
- 文档影响：更新本实施记录和测试矩阵。
- 测试覆盖：`tests.test_runtime_monitoring.RuntimeMonitoringRepositoryTests.test_ready_health_summary_uses_lightweight_runtime_contract` 锁定 legacy scope SQL 过滤；`tests.test_app_postgres_mode.AppPostgresModeTests.test_ready_endpoint_exposes_runtime_infrastructure_contract` 锁定 compact worker status counts 不包含 historical optional worker。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_app_postgres_mode tests.test_runtime_monitoring tests.test_postgres_state_store tests.test_health_ready_payload_probe -v`。
- 未测风险：本地 fake connection 证明 SQL contract 和 payload shape；生产仍需发布后复跑服务器本机 `health_ready_payload_probe`，并在具备 root-owned helper 后执行 `read-model-scope-contract --json/--apply` 清理历史行。

## 2026-06-16 - Health readiness runtime payload compact mode

- 目标：修复生产 `/fin-ops-api/health/ready` 仍携带约 90KB runtime drilldown、探针自身超过一秒的问题，让 readiness endpoint 只返回部署和运行门禁所需的轻量摘要。
- 影响范围：`/health/ready` payload shape、health-ready probe blocker 提取、系统状态测试矩阵；不改变 `/metrics`、operations dashboard、read model/worker 事实源或生产 repair 语义。
- 关键决策：ready payload 删除完整 `entrypoints` 明细并输出 `entrypoint_count`，删除 `storage.runtime_infrastructure` 重复块；顶层 `runtime_infrastructure` 保留 dirty/outbox/failed/stale/required-worker/RabbitMQ/read-model refresh scalar blocker，并把 `worker_metrics`、slow events、by-scope drilldown 等大集合压缩为 count + bounded samples。完整诊断继续由 `/metrics` 和 admin-only operations dashboard 承担。
- 文档影响：更新本模块 `tests.md` 和本实施记录。
- 测试覆盖：`tests.test_app.AppTests.test_ready_endpoint_reports_readiness_without_workbench_api_self_test`、`tests.test_app_postgres_mode.AppPostgresModeTests.test_ready_endpoint_exposes_runtime_infrastructure_contract`、`tests.test_health_ready_payload_probe.HealthReadyPayloadProbeTests.test_extracts_runtime_blockers_from_compact_worker_status_counts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_app tests.test_app_postgres_mode tests.test_health_ready_payload_probe -v`。
- 未测风险：本地测试证明 payload shape 和 blocker contract；真实生产耗时仍需发布后用服务器本机 `health_ready_payload_probe` 复测。dirty/dead-letter/failed job blocker 需要安全 runtime DB env 后单独 read-only 诊断和受控修复。

## 2026-06-16 - Runtime closure gate 纳入 health-ready payload gate

- 目标：防止最终 P2/P3 runtime closure gate 漏掉 `/fin-ops-api/health/ready` 自身慢、大、未截断或 HTML fallback 的生产风险。
- 影响范围：`runtime_sync_closure_gate` 聚合检查、SLO 默认阈值测试、系统状态测试矩阵、运维 monitoring runbook 和 P2/P3 closure ledger；不改变后端 health/readiness API、Prometheus、dashboard 或 runtime facts。
- 关键决策：runtime gate 新增必经 `health_ready_payload` check，默认 `--health-ready-target-ms 1000`、`--health-ready-max-response-bytes 50000`、`--health-ready-max-api-performance-endpoints 20`。该 check 复用 `health_ready_payload_probe`，无需登录态，用同一 `base_url` / `api_prefix` 检查 readiness payload contract。
- 文档影响：更新本模块 `tests.md`、`docs/operations/monitoring.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：`tests.test_runtime_sync_closure_gate.RuntimeSyncClosureGateTests.test_health_ready_payload_failure_prevents_closure_pass`；`tests.test_slo_tool_defaults` 锁定 runtime gate health-ready 默认目标。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_sync_closure_gate tests.test_slo_tool_defaults -v`。
- 未测风险：真实生产仍需发布 bounded readiness fix 后复跑；当前公网 probe 已证明旧 release 仍失败。
- 后续事项：部署后 `runtime_sync_closure_gate` 和单独 `health_ready_payload_probe` 都必须通过，才能把 P2P3-012 readiness payload gate 降为 evidence-added。

## 2026-06-16 - Health readiness payload production probe

- 目标：把 `/fin-ops-api/health/ready` 是否真正一秒级、轻量、bounded 从人工 curl 观察变成可复跑的 P2/P3 production gate。
- 影响范围：新增 `health_ready_payload_probe` CLI、系统状态测试矩阵、监控 runbook 和 P2/P3 closure ledger；不改变后端 health/readiness API、runtime facts、Prometheus 或 dashboard contract。
- 关键决策：probe 默认要求 `status=ready`、HTTP 200 JSON、耗时 `<=1000ms`、response bytes `<=50000`、`api_performance.endpoints<=20` 且必须有 `endpoint_count` / `omitted_endpoint_count`；HTML fallback、未截断 endpoint 和缺 metadata 都 fail-closed。probe 同时从 readiness payload 提取 `runtime_release_name` 和 concise `runtime_blockers`，用于无人值守流程先判断是否是 release 未部署、dirty/outbox backlog、failed jobs、worker mismatch、Postgres/readiness 状态或 runtime guard 问题；`dirty_scopes.done` 等完成态计数不会被当成 blocker。
- 文档影响：更新本模块 `tests.md`、`docs/operations/monitoring.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：`tests/test_health_ready_payload_probe.py` 覆盖 bounded pass、unbounded endpoint fail、慢/大 payload fail、HTML fallback fail、`/fin-ops-api/health/ready` URL prefix 和 runtime blocker 摘要提取。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_health_ready_payload_probe -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.health_ready_payload_probe --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --target-ms 1000 --json`。
- 生产证据：当前 `www.yn-sourcing.com` readiness 仍失败，约 1.9s、约 128KB、105 个 `api_performance` endpoints、缺 `endpoint_count` / `omitted_endpoint_count`，release 为 `main-28878ace-20260616013244`；公开 readiness blocker 摘要显示 `dirty_scopes.pending=3`、`queue_backlog.dead_lettered=3`、`failed_jobs=3`、`stale_dirty_scope_count=3`、`read_model_refresh_failure_rate=0.000463` 和一个 worker `mismatch`。
- 未测风险：probe 证明生产门禁失败，但不执行 deploy、restart 或 DB repair；需发布本地 bounded readiness fix 后复跑。
- 后续事项：部署后该 probe 必须通过，才能把 P2P3-012 的 readiness payload gate 从 `production-gated` 降为 evidence-added。

## 2026-06-16 - P2/P3 closure ledger 机器可读汇总

- 目标：让无人值守 P2/P3 workflow 能从统一 JSON 读取 17 页面、P2/P3 item、priority、classification、gap、closure evidence、remaining gate、gated/pass 状态、per-item next_actions 和 page-level next_actions，并能把上一轮 gate JSON 分类成下一轮分支，避免只靠人工阅读 Markdown 判断下一步。
- 影响范围：新增 `p2p3_closure_summary` / `p2p3_gate_result_classifier` CLI、系统状态测试矩阵和 P2/P3 closure ledger；不改变业务 API、runtime gate、read model 或 worker 行为。
- 关键决策：`p2p3_closure_summary` 解析 `.planning/P2P3-CLOSURE-PLAN.md` 中的聚合 closure item、final gated smoke matrix、17 页面覆盖映射、17 页面当前状态和 current status 表；每个 item 合并 priority、classification、covered pages、gap、closure evidence、当前 status、requires_external_evidence 和按 P2P3 ID 匹配的 next_actions；每个 page 再按 primary closure IDs 聚合 external gate item IDs 和 next_actions。requires_external_evidence 同时看当前 status 和原始 classification，避免 staging-required item 已有本地证据后从页面 gate 中消失。顶层 `next_focus` 按 production-gated、staging-gated、manual-only 与 P2-A/P2-B/P2-C/P2-D/P3 优先级选择下一条外部 gate，当前会指向 P2P3-001 runtime/read-model sync 证据，并附带受影响页面与推荐 gate 命令。`next_focus.next_bounded_action` 进一步输出 goal、evidence_to_inspect、allowed_scope、architecture_constraints、required_action、推荐命令、pass criteria、failure handling 和 stop condition，供主控生成下一轮 bounded action，而不把原始 prompt 写入文档树。`p2p3_gate_result_classifier` 读取任意 gate JSON，将 `configuration_missing`、`auth_missing`、`input_error`、`no_candidates`、`dry_run`、runtime/health-ready failed checks、直接 `health_ready_payload_probe` slow/large/unbounded readiness failure、HTTP/SSE failed checks、read-model/write evidence failed checks 和 pass 分类成稳定分支。缺少 ledger 返回结构化 `input_error`，存在 staging/production/manual gate 时顶层状态为 `gated`。
- 文档影响：更新系统状态测试矩阵和 P2/P3 closure ledger。
- 测试覆盖：`tests/test_p2p3_closure_summary.py` 覆盖 fixture 解析、当前 ledger 17 页面输出、item 分类字段、gated item next_actions、gated page next_actions、top-level next_focus、next_bounded_action 输出和缺文件输入错误；`tests/test_p2p3_gate_result_classifier.py` 覆盖 environment/auth/input/approval/runtime/durable/pass 分类、直接 health-ready payload failure 分类和非法 JSON 输入。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_p2p3_closure_summary tests.test_p2p3_gate_result_classifier -v`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.p2p3_closure_summary --json`；`read_model_slo_smoke --json --target-ms 1000 | p2p3_gate_result_classifier --json`。
- 未测风险：该工具只汇总 ledger 事实，不替代真实认证态 HTTP/read-model/write/SSE/RabbitMQ/worker smoke。
- 后续事项：主控 workflow 应先读取此 JSON，再优先处理 `production-gated`、`staging-gated`、`manual-only` 分支。

## 2026-06-16 - Runtime closure gate 拒绝空 runtime facts 与零样本通过

- 目标：防止 P2/P3 最终闭环在 runtime health 没有 durable queue/worker facts，或 authenticated HTTP、SSE smoke、controlled write E2E 没有任何 probe/sample/result 时，被误判为一秒级页面/API/SSE/写操作已通过。
- 影响范围：`runtime_sync_closure_gate` 的 `runtime_health`、`authenticated_http_slo`、`sse_first_event_smoke` 和 `write_operation_e2e` checks、系统状态测试矩阵、运维 monitoring runbook 和 P2/P3 closure ledger；不改变 runtime monitoring repository、HTTP/SSE/write E2E probe 工具采样逻辑、后端 API、SSE route 或业务写接口。
- 关键决策：runtime health check 只有在 summary 包含 durable queue、dirty scope、required worker counts、read model refresh failure rate 和非空 `worker_metrics` 时才能通过，否则输出 `runtime_health_missing_facts`；HTTP check 只有在 `summary.probe_count > 0` 且 `summary.sample_count > 0` 时才能通过；SSE check 只有在 `summary.probe_count > 0` 时才能通过；write E2E direct API 空 scenario 返回 `scenario_empty` input error；write E2E check 只有在 `scenario_count > 0` 且 `results` 非空时才能通过。否则分别输出 `http_slo_empty_samples` / `sse_smoke_empty_samples` / `write_operation_e2e_empty_samples`。最终闭环的 runtime、HTTP、SSE、read-model、write-audit 和 controlled write E2E 证据都必须非空。
- 文档影响：更新本模块 `tests.md`、`docs/operations/monitoring.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：`tests.test_runtime_sync_closure_gate.RuntimeSyncClosureGateTests.test_runtime_health_empty_summary_prevents_closure_pass`；`test_http_zero_samples_prevents_closure_pass`；`test_sse_zero_probes_prevents_closure_pass`；`test_write_e2e_zero_results_prevents_closure_pass`；`tests.test_write_operation_e2e_smoke.WriteOperationE2ESmokeTests.test_empty_scenarios_return_input_error_instead_of_pass`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_sync_closure_gate -v`。
- 未测风险：本地测试使用 fake report 证明 final gate contract；真实认证态 HTTP/SSE p95 仍需要安全 token/cookie 后在 staging/production 复跑。

## 2026-06-16 - Runtime closure gate 拒绝 write audit 零样本通过

- 目标：防止 P2/P3 最终闭环在没有真实 durable write 样本、或 write audit 意外返回零 expectation 时，被误判为 write-operation SLO 已通过。
- 影响范围：`write_operation_slo_audit` 的无样本回归测试、`runtime_sync_closure_gate` 的 `write_operation_audit` check、系统状态测试矩阵、运维 monitoring runbook 和 P2/P3 closure ledger；不改变业务写接口、outbox schema 或 operation profile。
- 关键决策：write audit 自身在无近期真实写入时必须返回 missing/fail；runtime gate 额外 fail-closed，要求 `event_sample_count > 0` 且 `expectation_count > 0`，否则输出 `write_operation_audit_empty_samples`。这保证最终闭环必须有真实写入证据，不能靠空 audit payload 通过。
- 文档影响：更新本模块 `tests.md`、`docs/operations/monitoring.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：`tests.test_write_operation_slo_audit.WriteOperationSloAuditTests.test_no_recent_write_samples_fail_instead_of_claiming_write_chain_closed`；`tests.test_runtime_sync_closure_gate.RuntimeSyncClosureGateTests.test_write_audit_zero_samples_prevents_closure_pass`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_slo_audit tests.test_runtime_sync_closure_gate -v`。
- 未测风险：本地测试使用 fake connection/report 证明 gate contract；真实生产 write audit 仍需要 Postgres URL、审批后的受控 scenario 和认证态最终 gate。

## 2026-06-16 - Runtime closure gate 暴露 write E2E 缺参 payload

- 目标：让无人值守 P2/P3 主控在最终 runtime gate 失败时，能区分缺少受控写 scenario、只 dry-run、缺认证/环境和真实性能失败。
- 影响范围：`runtime_sync_closure_gate` 的 `write_operation_e2e` check payload、系统状态测试矩阵、运维 monitoring runbook 和 P2/P3 closure ledger；不改变业务写接口、scenario schema 或 SLO 判断。
- 关键决策：缺少 `--write-scenario` 时保持 gate `fail`，payload 输出 `status=input_required`、`missing_args=["--write-scenario"]` 和完整 `required_args`；提供 scenario 但未显式 `--apply-write-scenarios` 时保留 dry-run report，并附加缺失 apply 参数；scenario 文件存在但为空、JSON 非法或 contract 非法时，`write_operation_audit` 和 `write_operation_e2e` 都返回 `input_error`，且不会退回运行 unscoped write audit。最终闭环仍必须真实 apply 受控写 E2E。
- 文档影响：更新本模块 `tests.md`、`docs/operations/monitoring.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：更新 `tests.test_runtime_sync_closure_gate.RuntimeSyncClosureGateTests.test_gate_fails_without_authenticated_http_and_write_scenario`、`test_write_scenario_dry_run_does_not_satisfy_closure` 和 `test_invalid_write_scenario_is_reported_as_input_error_without_running_write_checks`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_sync_closure_gate -v`。
- 未测风险：本地测试只证明 gate 输出契约；真实 apply 仍需要安全认证、已审批 scenario、测试对象和回滚 owner。

## 2026-06-16 - Runtime closure gate 纳入 SSE smoke

- 目标：防止最终 P2/P3 runtime closure gate 只验证 HTTP/read-model/write audit，却漏掉 App Health / Workbench SSE 首事件和 Nginx buffering 风险。
- 影响范围：`runtime_sync_closure_gate` 聚合检查、SLO 默认阈值测试、系统状态测试矩阵、运维 monitoring runbook 和 P2/P3 closure ledger；不改变 SSE route、worker 或业务数据。
- 关键决策：runtime gate 新增必经 `sse_first_event_smoke` check，默认 `--sse-target-ms 1000`。该 check 复用 `sse_smoke_probe`，需要真实认证，验证 `/api/app-health/stream` 与 `/api/workbench/events?month=all` 的首事件、content type、事件名和 HTML fallback。`--allow-unauthenticated-http` 同时用于调试性 HTTP/SSE 无认证采样；最终 closure 不能使用它。
- 文档影响：更新本模块 `tests.md`、`docs/operations/monitoring.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：`tests.test_runtime_sync_closure_gate.RuntimeSyncClosureGateTests.test_sse_smoke_failure_prevents_closure_pass`；`tests.test_slo_tool_defaults` 锁定 runtime gate 的 SSE target 默认 `1000ms`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_sync_closure_gate tests.test_sse_smoke_probe tests.test_slo_tool_defaults -v`。
- 未测风险：真实生产/staging 仍需安全 token/cookie 后运行完整 gate；本地测试只证明 final gate 不会漏掉 SSE 检查。

## 2026-06-16 - SSE first-event smoke probe

- 目标：把 P2/P3 中 “Nginx/OA iframe/SSE buffering 未验证” 从文字 gate 推进为可执行只读 smoke，后续有真实 token/cookie 时可复跑 `/api/app-health/stream` 和 `/api/workbench/events?month=all` 的 event-stream 首事件延迟。
- 影响范围：新增 `sse_smoke_probe` 工具、SLO 默认阈值测试、系统状态测试矩阵、运维 monitoring runbook 和 P2/P3 closure ledger；不改变后端 SSE 路由、前端 EventSource 或业务状态事实源。
- 关键决策：工具默认需要真实认证；无凭据返回 `auth_missing`。SSE endpoint 必须返回 `text/event-stream`、匹配预期事件名前缀，并在 `target_ms` 内读到首个 SSE event。若拿到 200 HTML 页面壳，按 `html_response_for_api_probe` 失败处理，避免把代理 fallback 当成 SSE 成功。
- 文档影响：更新本模块 `tests.md`、`docs/operations/monitoring.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：`tests.test_sse_smoke_probe` 覆盖 auth 缺失、默认 probe/API prefix、HTML fallback、unexpected status、unexpected event 和 first-event SLO miss；`tests.test_slo_tool_defaults` 锁定 SSE target 默认 `1000ms`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_sse_smoke_probe tests.test_slo_tool_defaults -v`。
- 未测风险：真实 Nginx/OA iframe 代理是否缓冲、断线或跨域行为仍需 staging/production 带真实登录态采样；本地测试只证明 gate 可复跑且分类明确。

## 2026-06-16 - Write E2E step 拒绝 API HTML fallback

- 目标：防止 controlled write-operation E2E smoke 在 mutating API prefix、Nginx fallback 或路径配置错误时，把前端 HTML 页面壳的 200 响应误判为写请求成功。
- 影响范围：`write_operation_e2e_smoke` mutating step 判定、测试矩阵和 P2/P3 closure ledger；不改变业务写接口或 write-operation SLO 采样规则。
- 关键决策：写步骤使用和 HTTP SLO probe 一致的 HTML fallback 分类。只有 expected status 已匹配时才把 HTML 页面壳归类为 `html_response_for_api_probe`；401/409/500 等仍保留 `unexpected_status:<code>`。HTML fallback 写步骤失败后跳过 write SLO claim，避免把“未真正打到 API”的场景误报成写后同步超时。
- 文档影响：更新本模块 `tests.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：`tests.test_write_operation_e2e_smoke.WriteOperationE2ESmokeTests.test_write_step_rejects_html_shell_even_when_status_matches`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_e2e_smoke -v`。
- 未测风险：真实 mutating apply 仍需要安全认证、审批的业务对象和回滚 owner；本地测试只证明工具不会把 HTML fallback 当成成功写步骤。

## 2026-06-16 - HTTP SLO probe 拒绝 API HTML fallback

- 目标：防止 P2/P3 authenticated API SLO gate 在 API prefix、Nginx fallback 或健康检查路径配置错误时，把前端 HTML 页面壳的 200 响应误判为 API 通过。
- 影响范围：`http_slo_probe` sample 判定、probe summary error 分类、系统状态测试矩阵和 P2/P3 closure ledger；不改变业务 API、页面 shell probe 或后端路由。
- 关键决策：只有 `kind="api"` 的 probe 会拒绝 HTML；页面 shell probe 继续允许 `text/html`。API probe 若返回 `text/html` 或 body 以 HTML 文档开头，即使 HTTP status 是 200，也记录 `html_response_for_api_probe` 并判定失败。
- 文档影响：更新本模块 `tests.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：`tests.test_http_slo_probe.HttpSloProbeTests.test_api_probe_rejects_html_shell_response`、`tests.test_http_slo_probe.HttpSloProbeTests.test_page_probe_allows_html_shell_response`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe -v`。
- 未测风险：真实生产认证态 API p95/freshness 仍需安全 token/cookie 后运行最终 SLO gate；本地测试只证明工具不会把 HTML fallback 当 API 成功。

## 2026-06-16 - Health readiness API performance payload 上限

- 目标：修复公网 `/fin-ops-api/health/ready` 在 API performance endpoint 过多时返回 100KB+ payload、只读 readiness 采样达到 2 秒级的问题，降低系统状态 P2-D 探针自身的响应负担。
- 影响范围：`ApiPerformanceRecorder.summary(...)`、`Application._health_payload()`、`Application._readiness_health_payload()`、Prometheus metrics 和 operations dashboard API performance contract；不改变 runtime readiness、dirty/outbox、worker 或 App Status 事实源。
- 关键决策：`/health` 与 `/health/ready` 只输出最多 20 个 p95 最慢 endpoint 的 `api_performance.endpoints` 摘要，并暴露 `endpoint_count` / `omitted_endpoint_count`；`/metrics` 继续拿完整 endpoint 明细用于 Prometheus，`/api/operations/app-health-dashboard` 继续通过 recorder full summary 展示完整列表。
- 文档影响：更新 app-health-operations 模块 README、测试矩阵、监控 runbook 和 P2/P3 closure ledger。
- 测试覆盖：`tests/test_api_performance_metrics.py::ApiPerformanceMetricsTests::test_recorder_can_return_bounded_slowest_endpoint_summary`、`tests/test_app.py::AppTests::test_ready_endpoint_bounds_api_performance_payload`、`tests/test_app.py::AppTests::test_metrics_endpoint_exports_full_api_performance_payload`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_api_performance_metrics tests.test_app tests.test_operations_dashboard_service tests.test_prometheus_metrics -v`。
- 未测风险：生产仍需发布后复测 `/fin-ops-api/health/ready` 网络耗时；当前生产 runtime 仍有 3 条 legacy cost_statistics dead-letter/pending/failed 记录，cleanup/apply 需要审批。

## 2026-06-16 - Closure/SLO 工具缺配置和输入错误返回结构化状态

- 目标：修复无人值守 P2/P3 workflow 在本地缺少 Postgres/RabbitMQ URL、缺少 write E2E scenario 或 scenario contract 非法时被 traceback 或普通 fail 中断的问题，让主控 prompt 能根据结构化状态继续进入环境配置、输入修复或 gated 分支。
- 影响范围：`read_model_slo_smoke`、`write_operation_slo_audit`、`write_operation_scenario_discovery`、`write_operation_e2e_smoke`、`runtime_sync_closure_gate`、`run_rabbitmq_staging_preflight` CLI 入口、共享 `cli_reports` helper、SLO 工具测试和 P2/P3 闭环台账；不改变已配置数据库/RabbitMQ 环境下的 SLO 判断逻辑。
- 关键决策：缺少 `FIN_OPS_POSTGRES_DATABASE_URL` / `DATABASE_URL` 或 RabbitMQ staging 必需 env 时统一输出 JSON `status=configuration_missing` 和退出码 2；Postgres gate 还输出 `blocking_condition=database_url_required`、`required_env`、安全 `next_actions`、`allowed_remote_evidence` 和 `forbidden_without_approval`，明确只能进入安全 DB URL 配置或生产只读采样分支，不能把缺配置当 pass/skip/SLO 证明。direct read-model apply smoke 必须至少产生一个 planned scope 和结果样本，零 scope/零 result 返回 fail；write E2E scenario 缺失、JSON 非法或 contract 非法时输出 `status=input_error` 和具体 `scenario_*` error；scenario discovery 没有候选时返回 `status=no_candidates`，且不会把空 `scenarios` 写到 `--scenario-output`。它们和 HTTP probe 的 `auth_missing` 一样，是环境/输入门禁，不是业务失败。
- 文档影响：更新本模块 `tests.md` 和本实施记录。
- 测试覆盖：`tests/test_slo_tool_defaults.py::SloToolDefaultTests::test_postgres_gate_tools_return_structured_configuration_missing` 覆盖 runtime/read-model/write audit gates 的 structured configuration_missing、blocking_condition、required_env、安全 next_actions、allowed_remote_evidence 和 forbidden_without_approval；`test_http_sse_and_closure_gate_share_auth_env_defaults` 覆盖 HTTP/SSE/runtime gate 共享认证 env；`tests/test_read_model_slo_smoke.py::ReadModelSloSmokeTests::test_apply_fails_when_no_smoke_scopes_are_discovered` 和 `tests/test_runtime_sync_closure_gate.py::RuntimeSyncClosureGateTests.test_read_model_smoke_zero_samples_prevents_closure_pass` 覆盖零样本 direct smoke 不可通过最终 closure；`tests/test_write_operation_scenario_discovery.py` 覆盖 discovery 缺配置和 no-candidates 不写空 scenario；`tests/test_write_operation_e2e_smoke.py` 覆盖 scenario 输入错误和 apply 缺配置；`tests/test_rabbitmq_staging_preflight.py` 覆盖 RabbitMQ staging env 缺失。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_slo_tool_defaults tests.test_write_operation_scenario_discovery tests.test_write_operation_e2e_smoke tests.test_rabbitmq_staging_preflight -v`；手动复跑 discovery / missing scenario / RabbitMQ preflight CLI 均返回结构化 JSON。
- 未测风险：未连接真实 Postgres 执行 apply/read-only gate；配置存在但网络不可达、权限不足或 SQL 报错仍由后续错误路径处理。
- 后续事项：主控 GSD prompt 应把 `configuration_missing`、`input_error`、`auth_missing` 和 staging/production-gated 明确分流，不能当作实现失败重试。

## 2026-06-16 - HTTP SLO probe 对齐真实首屏参数

- 目标：补齐 P2P3-006 中高行数页面认证态 HTTP SLO 的本地证据，避免 probe 用统一 `page_size=50` 低估真实首屏请求。
- 影响范围：`http_slo_probe` 默认 API probe、`tests/test_http_slo_probe.py`、系统状态测试矩阵和 P2/P3 闭环台账；未改变业务页面或后端业务接口实现。
- 关键决策：probe 代表用户实际首屏而不是任意小样本。进项发票使用、OA 待付款和销项发票收款 rows 使用页面默认 `page_size=20`；no-OA 使用 `page_size=200`；批量账务使用真实双分页参数 `bank_page_size=200` / `oa_page_size=200`；待找发票和关联台保持各自已有首屏边界。
- 文档影响：更新本模块 `tests.md` 和本实施记录；业务模块文档不变，因为页面行为未变。
- 测试覆盖：更新 `tests/test_http_slo_probe.py`，显式断言默认 probe 覆盖高行数页面 rows API、成本统计 explorer/summary、真实 page/page_size 和 auth/freshness 语义。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe -v`。
- 未测风险：本地只锁定 probe contract，不连接真实登录态生产 API；实际 p95/p99、read model fresh 状态、Nginx/worker/DB 长尾仍需带 auth 的 staging/生产 smoke。
- 后续事项：最终门禁使用 `http_slo_probe --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --iterations 20 --warmup 2 --target-ms 1000` 并提供安全的 token/cookie。

## 2026-06-16 - 后台任务 accepted/progress 可见性回归

- 目标：补强 P2/P3 一秒级闭环中“导入/后台任务被接受后，页面能立刻看到 queued 反馈并随后看到 progress 更新”的本地证据。
- 影响范围：`BackgroundJobService` 的现有契约、App Status background task 事实面、P2/P3 closure ledger；本轮不改变业务逻辑。
- 关键决策：不做 wall-clock 单测断言，避免把本地机器调度抖动写成错误契约；测试锁定同步持久化和 active payload shape，包括 status、phase、current/total、percent、short_label、created/updated timestamp、affected domains 和 route。
- 文档影响：更新本模块 `tests.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：新增 `tests.test_background_job_service.BackgroundJobServiceTests.test_job_acceptance_and_progress_visibility_contract`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_background_job_service -v`。
- 未测风险：真实 RabbitMQ/systemd worker drain、Nginx/SSE 推送、生产大导入进度刷新延迟仍需 staging/production smoke。
- 后续事项：生产验证失败时先区分 job accepted HTTP latency、background job persistence、worker queue lag、SSE/轮询传播和前端渲染延迟。

## 2026-06-12 - App Status current-effective blocker

- 目标：修复历史 cost statistics legacy scope、历史 dead-letter/outbox failure 把当前页面同步状态长期拖成 busy/failed 的问题。
- 影响范围：`RuntimeMonitoringRepository.app_status_runtime_snapshot()`、`AppStatusOverviewService`、`/api/app-health.app_status.domains[]` 的诊断字段、App Health / App Status 文档、outbox App Status 热路径索引。
- 关键决策：`read_model_statuses[*].scopes[]` 只保留 current-effective scope；成本统计 legacy scope `all` 和裸 `YYYY-MM` 进入 `historical_scopes[]`。outbox `failed/dead_lettered/publish_failed` 只有在没有后续同 scope `done` 事件、且没有后续同 scope fresh readiness 时才参与当前状态。新增 `domains[*].historical_read_model_scopes[]` 只做历史诊断，不作为 fresh 证明。新增 `0067_app_status_current_effective_outbox_index.sql`，保护 App Status current-effective outbox 查询不退化为全表扫描。
- 文档影响：更新 `docs/dev/api-contracts.md`、`docs/app-architecture/runtime-and-ownership.md`、本模块 `state-machine.md` 和 `tests.md`。
- 测试覆盖：新增 legacy cost scope、historical read model scope diagnostics、covered outbox failure 回归测试；保留旧 missing/failed/worker/runtime unavailable/API contract 测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v`。
- 未测风险：本地 fake connection 已覆盖语义；真实生产数据仍需要部署后 smoke `/api/app-health`，确认 historical failures 不再影响 current App Status，同时 repair 脚本仍需在后续阶段处理历史 dirty/dead-letter 记录。
- 后续事项：生产 repair 阶段应 dry-run 旧 cost statistics scope、covered dead-letter 和 readiness 记录，写审计/回滚记录后再清理；不要把语义过滤当作数据修复完成。

## 2026-06-11 - app-health-operations 测试闭环首轮

- 目标：补齐 App Health / App Status 的影响面、七类测试矩阵、状态机、验证命令和真实环境风险。
- 影响范围：`AppHealthOperationsPage`、`AppStatusIndicator`、`AppHealthStatusContext`、App Health API、App Status overview、RuntimeMonitoringRepository、registries、readiness backfill、runtime queue ops。
- 关键决策：不新增低价值代码测试；已有后端/前端测试覆盖主要状态优先级、API shape、runtime facts、registry、dashboard 和全局 icon 行为。本轮补齐文档闭环。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`implementation-notes.md` 和全局 `testing-closure-dependency-map.md`。
- 测试覆盖：后端覆盖 app health/status/runtime monitoring/readiness/worker registry/runtime queue；前端覆盖 dashboard、App Status mapper/provider/icon、SSE/轮询和 BroadcastChannel。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Nginx/OA iframe SSE、真实大库 dashboard metrics、pg_stat_statements 配置。
- 后续事项：如果生产出现状态误判，先补 regression test 到 App Status overview 或 runtime repository，再登记到 `docs/dev/regression-bug-bank.md`。
