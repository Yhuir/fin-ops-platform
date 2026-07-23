# 系统状态测试矩阵

> 修改本模块前先读取本文件，确认 App Health / App Status 的事实源、状态优先级、测试入口和旧功能回归范围。实现后按实际影响更新矩阵。

## 2026-07-23 - App Health 冷缓存 scope evidence 热路径

- 变更类型：生产大库只读查询性能修复；API shape、Dashboard cache/fallback、状态语义、权限和业务事实源不变。
- 生产根因证据：30 秒 cache miss 时 dashboard 约 6.7 秒，API rolling metrics 的 SQL execute/fetch p95 约 10.3 秒，而 connection acquire p95 低于 1ms；scope-evidence owner 对每个 read-model event type 分别执行 recent-event lateral lookup，但现有 partial indexes 只覆盖带 duration 的 done 或 failed/dead-lettered 事件，不能覆盖 pending/processing/latest-any-status 合同。
- 新增/更新测试：migration 清单和 SQL contract 必须包含 `outbox_events_read_model_scope_evidence_idx (event_type, updated_at desc) where event_type like '%.read_model.refresh'`；既有 `tests/test_operations_dashboard_service.py` 继续锁定 current/full-history、readiness/source_versions、timing/retry payload 不变。
- 回归重点：不扩大 Dashboard 查询范围，不添加 stale-while-revalidate 或并行 DB fan-out；发布后跨至少三个 TTL 周期验证冷/热响应、payload 状态和 System Audit。

## 2026-07-23 - App Health/readiness 重复 I/O 收敛

- 变更类型：只读运行状态性能修复；API shape、状态优先级、durable facts 和权限不变。
- 新增/更新测试：App Health cache disabled 时单请求仍只取一次 runtime snapshot，active/attention jobs 共用一次 durable snapshot；既有完整 Workbench generation consistency failure/repair 回归保持，Workbench outbox backlog 禁止扫描历史 done；ready summary 的 outbox/dirty current-effective CTE 各只 materialize 一次，dirty status count 只来自 current-effective CTE，禁止恢复历史 `done` 全表扫描。
- 回归重点：不得用 TTL 缓存伪装 readiness；consistency failure、active repair、worker/read-model/outbox blocker 语义保持；完整 AppHealth 与 `/health/ready` 都必须在生产重新取样。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| App Health page | `web/src/pages/AppHealthOperationsPage.tsx` | admin-only、只读 dashboard、页面 Audit icon 只读按钮、刷新失败保留旧 payload、unknown 显示 `--` 而不是 0 |
| Global icon/popover | `web/src/components/shell/AppStatusIndicator.tsx` | icon 必须来自全局 `app_status`，路由切换不改变状态；admin 才显示运维入口 |
| Frontend providers/API | `AppHealthStatusContext`、`features/appHealth/api.ts`、`features/appStatus/api.ts` | SSE/轮询、malformed payload 不得默认 green、App Status mapper 字段兼容 |
| HTTP routes | `server.py` `/api/app-health*`、`/api/operations/app-health-dashboard`、统一 `/api/operations/app-health/page-audit`、`/api/operations/app-health/input-invoice-usage-refresh`、`/api/operations/app-health/output-invoice-collection-refresh` | auth guard、SSE contract、dashboard admin-only、整体构建失败时 cache stale fallback、局部指标失败时仍刷新当前 inventory/import status、页面审计 admin-only/只读/fail-closed、进项/销项刷新 admin-only 且只通过 runtime queue 入队 |
| Overview service | `AppStatusOverviewService` | green/yellow/red 优先级、readiness missing、critical failed/unavailable、dependencies、tasks、scope diagnostics |
| Runtime repository | `RuntimeMonitoringRepository` | dirty scopes/outbox/workers/readiness/RabbitMQ/API metrics 聚合，不可用 snapshot 不能变 green |
| Registries | domain/read model/job/dependency/worker registries | 新页面/read model/worker/job/dependency 必须同步 registry，否则状态 plane 漏报 |
| External evidence | `external_control_evidence` service/repository/CLI/exact audit | partial coverage、自证 manifest、count-only、latest revoke 回退、过期证据和字段漂移不得变绿；登记/撤销必须审计且无 HTTP 写入口 |
| Readiness backfill | `app_status_readiness_backfill` | 只能从真实 projection 计算 readiness，不能批量伪造 fresh |
| Runtime ops tools | `runtime_queue_ops`、deploy worker examples | dead letter/replay/worker manifest 操作必须依赖 readiness 和 registry |

## 场景覆盖清单

| 场景 | 保护测试 | 说明 |
| --- | --- | --- |
| idle / busy / blocked health API | `tests/test_app_health_api.py`、`tests/test_app_health_service.py` | 覆盖 dirty OA scopes、workbench consistency failure、dependency error、background jobs、SSE |
| App Status overview | `tests/test_app_status_overview_service.py`、`tests/test_background_job_service.py` | 覆盖 registry 一致性、background task、job accepted/progress visible payload、read model missing/failed、worker missing、runtime unavailable、runtime summary read model/worker/queue 计数、current-effective blocker、历史 scope 诊断、同 scope requeued failure -> refreshing、covered pending outbox 不进入 backlog、active dirty scope 覆盖历史 failed outbox、done publish failure 不回流为当前 outbox failed、covered dirty scope 不让 read model/domain 长期同步中、`oa.sync` 只影响 OA 待付款核对而不把设置页误标 busy、API contract |
| Runtime monitoring metrics | `tests/test_runtime_monitoring.py` | 覆盖 backlog、failed jobs、stale dirty scopes、RabbitMQ、worker metrics、worker mismatch、ready health summary current-effective SQL 插值；App Status runtime repository 在 `tests/test_app_status_overview_service.py` 额外覆盖 legacy scope、covered outbox row 与 covered dirty scope 过滤、old failed + current processing 合并、old failed + later pending retry 不重复计入 failed、old failed outbox + same-scope active dirty scope 不重复计入 failed |
| Operations dashboard data inventory | `tests/test_operations_dashboard_service.py` | 覆盖 dashboard 发票 inventory 从 canonical `app.invoices.source_links` 统计 `manual` / `oa_attachment`，从 `app.invoices.invoice_type` 统计 `input_invoice` / `output_invoice`，`oa_attachment.supplementary_count` 统计 OA 解析进入发票池但不在手工导入中的数量；OA inventory 上次同步时间优先使用 `app.oa_sync_runs(sync_type='oa_projection')` 成功 run，已完成 OA 按 `app.oa_applications` 完成态统计，进行中 OA 按 OA 待付款 read model all-scope 的 `viewCounts.in_progress` 等价唯一 OA ID 统计并防止回退到 `app.oa_applications.workflow_status`；同时覆盖导入历史只包含手工银行流水和发票批次、import history 查询失败时只降级 history 不阻断总览，以及 read-model 指标只扫描 pending/processing/failed dirty scopes |
| 进项/销项全量审计 API | `tests/test_app_health_api.py`、两个 invoice audit tool tests | 覆盖统一 page-key API、canonical/shared/consumer typed edge 双向 equality、outbox/dirty、缺失/多余 consumer edge、只读与 fail-closed；旧 specialized HTTP path guard 必须保持归零。 |
| 进项/销项受控刷新 API | `tests/test_app_health_api.py` | 覆盖 `/api/operations/app-health/input-invoice-usage-refresh` 和 `/api/operations/app-health/output-invoice-collection-refresh` admin-only、runtime queue 缺失 fail-closed、scope policy 拒绝非法 scope、合法 scope 去重后通过 `ReadModelRefreshGateway` 入队 high-priority read model refresh，不直接写 read model 或 relation。 |
| 页面业务全量 Audit icon | `tests/test_app_health_api.py`、`tests/test_audit_page_business_read_model_tool.py`、`web/src/test/AppHealthPageAuditApi.test.ts`、页面组件测试按页面归属覆盖 | 待找发票、外部往来款管理、批量账务、流水规则批量处理、OA 待付款核对、银行明细、成本统计页面标题右侧 admin-only Audit icon 调用 `/api/operations/app-health/page-audit`；后端只读审计页面 canonical facts、read model rows/scopes/source_versions、durable refresh state 和 relation distribution。通过只证明 App 内部事实和投影一致，不证明外部银行/OA 系统本身没有漏同步。 |
| 17 页 system Audit | `tests/test_audit_app_health_system.py`、`tests/test_operations_audit_service.py`、`tests/test_app_health_api.py`、`tests/test_audit_external_control_evidence.py`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/e2e/app-shell.spec.ts` | 覆盖单一 outer snapshot、16 个 caller-owned page proof、snapshot/revision/version set、dashboard inventory 独立重算、manifest/status registry、required worker/current outbox、external unknown/pass/fail、显式 page coverage、子页/字段/queue破坏性反证，以及旧 App Health 进项专项 panel/URL 与 free-text external classifier 删除。PostgreSQL integration 应用全量 migrations 后验证 clean pass、inventory drift、canonical omission、字段漂移和 latest revoke fail closed。 |
| Health payload size guard | `tests/test_app.py`、`tests/test_app_postgres_mode.py`、`tests/test_api_performance_metrics.py`、`tests/test_prometheus_metrics.py`、`tests/test_health_ready_payload_probe.py` | 覆盖 `/health/ready` 只输出 bounded 最慢 endpoint API performance 摘要和 compact runtime 摘要，不重复 `storage.runtime_infrastructure`、不输出完整 `entrypoints` / `worker_metrics` 明细；Prometheus `/metrics` 与 operations dashboard 仍保留完整 endpoint 明细；生产 probe 会在 readiness 慢、大、未截断、缺 bound metadata 或 HTML fallback 时失败，并从 readiness JSON 提取 `runtime_release_name` / `runtime_blockers`，同时不把 `dirty_scopes.done`、legacy cost statistics historical scope 或 `current_effective=false` optional worker 等非当前事实误判为 blocker，也能从 compact `worker_status_counts` 提取 current-effective worker blocker。 |
| HTTP SLO probe defaults | `tests/test_http_slo_probe.py` | 覆盖 17 个页面 shell、认证态首屏 API、真实首屏 page/page_size、read model freshness 失败判定、auth 缺失语义、admin-only dashboard probe 的 admin auth scope、ETC 默认探针只覆盖 canonical `business-batches` 而不覆盖 legacy `/api/etc/batches`、默认 gzip 请求/解压 metadata 且 `response_bytes` 记录传输字节，以及 API probe 误打到 HTML 页面壳时必须失败。 |
| SSE first-event smoke | `tests/test_sse_smoke_probe.py` | 覆盖 `/api/app-health/stream` 与 `/api/workbench/events?month=all` 的 event-stream 首事件 SLO、auth 缺失、HTML fallback、错误状态码和事件名校验。 |
| P2/P3 closure summary/result classifier | `tests/test_p2p3_closure_summary.py`、`tests/test_p2p3_gate_result_classifier.py` | 覆盖 `.planning/P2P3-CLOSURE-PLAN.md` 的聚合 closure item、final gated smoke matrix、17 页面覆盖映射、当前状态表和 P2/P3 item 表可被解析为 JSON；输出 priority、classification、covered pages、gap、closure evidence、requires_external_evidence、per-item next_actions、page-level next_actions、top-level next_focus 和 next_bounded_action；缺少 ledger 时返回结构化 `input_error`。gate result classifier 读取上一轮 gate JSON 并分类为 environment-required、auth-required、input-required、approval-required、runtime-repair-or-deploy-required、durable-evidence-required 或 passed；直接读取 `health_ready_payload_probe` 的 slow/large/unbounded readiness failure 时也进入 runtime-repair-or-deploy-required，方便无人值守 workflow 分支。 |
| Closure tool config/input state | `tests/test_slo_tool_defaults.py`、`tests/test_runtime_sync_closure_gate.py`、`tests/test_read_model_slo_smoke.py`、`tests/test_write_operation_scenario_discovery.py`、`tests/test_write_operation_e2e_smoke.py`、`tests/test_write_operation_slo_audit.py`、`tests/test_rabbitmq_staging_preflight.py` | 覆盖一秒级默认阈值，HTTP/SSE/runtime gate 共享 `FIN_OPS_HTTP_SLO_*` 认证 env，runtime gate 会把普通 bearer headers 和 admin headers 分别传给 HTTP SLO probe，缺少 Postgres/RabbitMQ URL 时 runtime/read-model/write/RabbitMQ gates 和 scenario discovery 返回结构化 `configuration_missing`；Postgres gate 缺 URL 时同时输出 `blocking_condition=database_url_required`、`required_env`、安全 `next_actions`、允许的只读远程证据和未经批准禁止动作。runtime health 缺 durable queue/worker facts 不能当 pass，runtime gate 必须包含 health-ready payload check 和 SSE first-event check，authenticated HTTP 零 probe/sample、SSE 零 probe、direct read-model apply smoke 零 scope/零 result 都不能当 pass，write-operation audit 零 event/expectation 样本和 write E2E 零 scenario/result 都不能当 pass，scenario discovery 无候选时不写空 scenario 文件，write E2E direct API 空 scenario 返回 `scenario_empty` input error，缺少 `--write-scenario`、`--apply-write-scenarios` 或 `--write-approval-ticket` 时暴露 `missing_args` / `required_args`，direct write E2E `--apply` 缺 `--approval-ticket` 时返回 `approval_missing` 且不连接 Postgres/不发 mutating HTTP，invalid runtime scenario 暴露 `input_error` 且不运行 unscoped write audit，write E2E 缺 scenario/非法 scenario 返回结构化 `input_error`，mutating step 拿到 HTML 页面壳必须失败，write E2E 的写后 SLO 事件读取必须按 operation expectation 过滤并保留有效采样下限，均不得 traceback。 |
| Readiness backfill | `tests/test_app_status_readiness_backfill.py` | 覆盖 dry-run/apply、missing projection 不伪造 fresh |
| Worker/queue ops | `tests/test_runtime_worker_registry.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_queue_ops.py`、`tests/test_deploy_runtime_examples.py` | 覆盖 registry-derived worker、App Status/read-model worker 双向 registry parity、outbox/dirty queue、dead letter resolve、deployment examples |
| Frontend dashboard | `web/src/test/AppHealthOperationsPage.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/production-admin-app-health.spec.ts`、`docs/modules/app-health-operations/e2e-spec.md`、`docs/modules/app-health-operations/e2e-coverage.md` | 覆盖只读 dashboard、admin gate、System Audit 只调用 `GET page-audit?page=app-health-operations`、snapshot id/time、App 内部 pass 与 external unknown 并列文案、后续 dashboard refresh 清除旧结果、unknown metrics、refresh failure stale payload、read model/worker/queue 总览、inventory 和导入历史；真实 Chromium 下 admin-only route、零 mutating request 和严格浏览器错误捕获。 |
| Frontend global status | `web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/AppStatusApi.test.ts`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/AppHealthResolver.test.ts`、`web/src/test/AppHealthBroadcast.test.tsx` | 覆盖 mapper、icon/popover runtime summary、route independence、SSE/轮询和 BroadcastChannel sync |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_app_status_overview_service.py`、`tests/test_app_health_service.py`、`tests/test_app_health_alert_service.py`、`tests/test_external_control_evidence_service.py` | 覆盖状态优先级、domain level、manifest normalization、identity/fingerprint/control、partial/duplicate/invalid input fail-closed。 |
| 2. Service-layer tests | 适用 | `tests/test_audit_app_health_system.py`、`tests/test_audit_external_control_evidence.py`、`tests/test_external_control_evidence_repository.py`、`tests/test_operations_audit_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py`、`tests/test_operations_dashboard_service.py`、页面 proof tests、runtime/closure tool tests | 覆盖 caller-owned snapshot I/O、单一 system transaction、四域 exact comparer、immutable register/revoke/audit、dashboard inventory 与 runtime/external evidence plane、全部页面 proof orchestration、service/repository 边界和既有运维 closure gates。 |
| 3. API contract tests | 适用 | `tests/test_app.py`、`tests/test_app_health_api.py`、`tests/test_app_status_overview_service.py`、`tests/test_http_slo_probe.py`、`tests/test_sse_smoke_probe.py`、`tests/test_health_ready_payload_probe.py`、`web/src/test/AppStatusApi.test.ts`、`web/src/test/AppHealthPageAuditApi.test.ts` | 覆盖 `/health/ready` bounded metrics、`/metrics` full metrics、`/api/app-health`、SSE、dashboard admin-only、进项/销项审计 API admin-only/503/report shape、页面业务审计 API admin-only/503/400/report shape、进项/销项刷新 API admin-only/503/400/202 shape、`app_status` shape 和 `runtime_summary` 映射、SLO probe 首屏 API contract、SSE 首事件 contract、HTML 页面壳误当 API/health-ready 响应的拒绝逻辑、readiness runtime blocker 摘要、malformed payload 拒绝。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_runtime_monitoring.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_readiness_backfill.py`、`tests/test_background_job_service.py`、`tests/test_audit_input_invoice_usage_read_model_tool.py`、`tests/test_audit_page_business_read_model_tool.py` | 覆盖 dirty scopes、outbox、worker heartbeat、RabbitMQ、readiness missing/stale/failed、进项使用/Workbench relation read model scope 对账、页面 read model/Workbench relation 全量对账，以及后台任务 accepted 后 queued payload 立即可见、progress 更新后 active payload 同步变化。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/AppHealthBroadcast.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/production-admin-app-health.spec.ts`、`docs/modules/app-health-operations/e2e-spec.md`、`docs/modules/app-health-operations/e2e-coverage.md` | 覆盖 dashboard、全局 icon、popover runtime summary、admin link、SSE/轮询、BroadcastChannel、真实浏览器 dashboard/admin gate/session gate smoke、生产 admin AppHealth 只读 smoke 和严格浏览器错误捕获。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_audit_external_control_evidence.py` 与 `tests/test_audit_app_health_system.py` PostgreSQL integration、`tests/test_app_health_api.py`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/production-admin-app-health.spec.ts` | 覆盖全迁移 PostgreSQL -> external manifest register -> 四域 exact proof -> 17 页同快照 proof -> API -> system Audit UI，以及 canonical omission/field drift/latest revoke/inventory drift/queue-worker failure；生产登记与 admin smoke 仍需明确授权、真实 manifest 和 token。 |
| 7. Existing feature regression tests | 适用 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/production-admin-app-health.spec.ts` | 保护旧页面 route registry、worker manifest、deploy env、App Status 不因路由切换或新 domain 漏报，并保护 dashboard admin-only 浏览器行为和生产只读 gate 不误发写请求。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-07-23 | App Health 周期性超过 1 秒：1 秒 runtime snapshot cache 失效时，App Status summary 从全部 readiness scopes 解码未消费的 `source_versions` JSON；生产 709 行约 366KB 版本向量使该查询由约 170ms 上升到 0.7–1.1s。 | `tests/test_runtime_monitoring.py::RuntimeMonitoringRepositoryTests::test_app_status_readiness_summary_does_not_load_unconsumed_source_versions` | covered；summary I/O 禁止该列回流，详细版本证据继续归 Operations dashboard |
| 2026-07-23 | App Health 30 秒冷缓存约 6.7 秒：scope-evidence 对每个 read-model event type 读取任意状态最近事件，现有只覆盖 terminal metric rows 的 partial indexes 无法服务该查询，导致重复扫描/排序 outbox 历史。 | `tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_app_health_dashboard_metrics_indexes_are_declared`、`tests/test_operations_dashboard_service.py::OperationsDashboardServiceTests::test_runtime_repository_uses_recent_window_for_read_model_health_duration` | covered；新增 exact partial index，response shape 和只读合同不变 |
| 2026-06-21 | Workbench parent generation 正在重刷时，旧 `workbench_all_scope_parent_inconsistent` failed outbox 仍进入 App Status queue failed，导致 hover 同时显示 syncing 和 blocked。 | `tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_ignores_failed_outbox_row_covered_by_active_dirty_scope` | covered |
| 2026-06-21 | `/health/ready` 已无 backlog，但 App Status outbox 仍把 `status='done'` 的历史 `publish_status='failed'` / `oa.sync` 行算成当前 failed。 | `tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_ignores_covered_outbox_statuses` | covered |
| 2026-06-21 | `/health/ready` / App Status runtime summary 的 dirty scope current-effective SQL helper 未插值，生产 PostgreSQL 收到 `{_current_effective_dirty_scope_predicate_sql()}` 后 syntax error，导致 runtime 诊断自身不可信。 | `tests/test_runtime_monitoring.py::RuntimeMonitoringRepositoryTests::test_ready_health_summary_uses_lightweight_runtime_contract` | covered |
| 2026-06-21 | Operations dashboard / health summary 直接统计历史 `publish_status=failed` outbox，导致 read model 已 fresh 后仍显示 Worker issue / Queue backlog。 | `tests/test_runtime_monitoring.py::RuntimeMonitoringRepositoryTests::test_dashboard_outbox_metric_only_scans_current_attention_statuses`、`test_health_summary_reports_backlog_failed_jobs_and_stale_dirty_scopes` | covered |
| 2026-06-19 | 生产公网 HTTP SLO probe 未请求 gzip，导致大 JSON API 按非浏览器未压缩传输口径被误判为慢。 | `tests/test_http_slo_probe.py::HttpSloProbeTests::test_collects_samples_with_api_prefix_without_leaking_auth`、`tests/test_http_slo_probe.py::HttpSloProbeTests::test_gzip_json_response_is_decoded_for_metadata` | covered |
| 2026-06-19 | 生产 authenticated HTTP SLO 用普通目标 OA bearer 采样 admin-only `/api/operations/app-health-dashboard`，导致 dashboard 固定 403 并把真实 admin credential 缺口混成 API 性能失败。 | `tests/test_http_slo_probe.py::HttpSloProbeTests::test_admin_scoped_probe_uses_admin_headers_without_overriding_user_probes`、`tests/test_runtime_sync_closure_gate.py::RuntimeSyncClosureGateTests::test_gate_passes_admin_headers_to_http_slo_probe` | covered |
| 2026-06-18 | 同一 `cost_statistics active:2026-03` scope 旧 `failed deadlock detected` 已被新 `processing` 重试覆盖，但 App Health 仍显示当前失败，误导用户认为数据域阻断。 | `tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_treats_requeued_cost_statistics_deadlock_as_refreshing` | covered |
| 2026-07-03 | AppHealth OA 卡片显示上次读取 OA 为旧日期，根因是 dashboard/status 口径混用 projection row `synced_at`、watermark、run 和 HTTP 进程内内存状态。 | `tests/test_operations_dashboard_service.py::OperationsDashboardServiceTests::test_build_payload_reports_inventory_performance_and_runtime_metrics`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_sync_status_endpoint_reads_durable_queue_status`、`tests/test_app_health_api.py::AppHealthApiTests::test_app_health_reports_dirty_oa_scopes_as_busy_and_stale` | covered |

本轮同时继续保留“malformed payload 不得默认 green”“runtime unavailable 不得空 green”“dashboard refresh 失败保留旧 payload 但标 warning”“HTTP SLO probe 不得用偏小 page_size 低估真实首屏”“admin-only dashboard probe 必须使用独立 admin auth scope”“P2/P3 SLO 工具缺 DB URL 或 scenario 输入时不得 traceback”“P2/P3 final gate 不得用空 runtime facts 或 HTTP/SSE/read-model/write-audit/write-E2E 零样本通过最终闭环”等已有回归保护。

## 关键 smoke flows

- dirty scope/outbox pending -> `/api/app-health` busy/yellow -> App Status popover 显示受影响 domain。
- 真实 Chromium 打开 `/operations/app-health`：admin 渲染 dashboard 数据/请求区；read_export_only、forbidden、expired 不请求 dashboard API。
- 生产 admin Browser smoke：`FIN_OPS_E2E_ADMIN_TOKEN` 注入 `Admin-Token` cookie 后打开 `/fin-ops/operations/app-health`，必须看到 `AppHealth 运维状态`、`app-health-data`、`app-health-requests`、`app-health-runtime`，dashboard API 必须返回 200，页面不能显示 session/admin 权限拦截，且 `POST`/`PUT`/`PATCH`/`DELETE` 请求列表必须为空。
- critical read model failed/unavailable -> App Status blocked/red -> 页面不能把旧数据当 fresh，但普通 read model failure 不应让 `overall.write_safety.blocks_mutations=true`。
- 同一 current-effective scope 旧 failed + 当前 pending/processing -> App Status 显示 refreshing，不把旧 last_error 当作当前 failure banner。
- 同一 read model refresh scope 旧 failed outbox + 当前 active dirty scope -> App Status queue 显示当前 pending/processing/backlog，不把旧 failed outbox 当作当前阻断。
- legacy cost statistics scope 或已被后续真实完成事实覆盖的 outbox failure -> App Status 保持当前 canonical 状态，同时通过历史诊断暴露 repair/audit 信息。
- required worker missing/stale/mismatch -> runtime infrastructure warning -> App Health dashboard 和 App Status domain 可定位。
- import/data reset/background job running -> active background task -> App Status 显示任务进度和 affected domains；`BackgroundJobServiceTests.test_job_acceptance_and_progress_visibility_contract` 锁定 job accepted 后 queued payload 立即可见、progress 更新后 active payload 同步变化。
- dashboard refresh 成功后展示数据/请求/后台三块；下一次刷新失败时保留旧 dashboard 并显示 warning。
- dashboard 发票来源展示 `手工导入`、`进项发票`、`销项发票` 和 `OA 解析`；`进项发票` / `销项发票` 来自 canonical invoice `invoice_type`，`OA 解析` 来自 canonical invoice `source_links[].source_type='oa_attachment_invoice'`，括号内数量是 OA 解析来源且不含 `manual_invoice_import` source link 的发票数，前端标签说明括号代表“进入统一发票池的数量”。`普通导入` 和 `ETC` 不再作为 App Health 发票来源展示；OA 附件 OCR cache 不作为 dashboard 发票 inventory 事实源。
- dashboard OA 来源展示 `单据`、`已完成 OA`、`进行中 OA` 和 `明细`；`单据` 是 `app.oa_applications` 申请主表行数，`明细` 是 `app.oa_application_items` 明细行数，`已完成 OA` 按 OA projection 的完成态合同统计，`进行中 OA` 按 OA 待付款 read model 的 `viewCounts.in_progress` 等价唯一 OA ID 统计。
- dashboard OA 卡片上次读取时间来自最近成功 `app.oa_sync_runs(sync_type='oa_projection')`；`/api/oa-sync/status` 只读 `oa.sync` outbox、`oa-sync` worker heartbeat 和最新 projection run，不能从 HTTP 进程内 polling 状态或 projection row `synced_at` 推断。
- dashboard 主页面只展示最新 5 条导入历史，右侧抽屉展示全量历史；导入历史只包含手工银行流水和发票批次，每条数量使用 `app.import_batches.success_count`，不用预览候选数、附件数、OA 解析数或 OA 同步数。
- admin 调用进项/销项 audit -> `server -> OperationsAuditService -> PostgresOperationsAuditRepository` 只读检查 canonical facts、页面 read model、Workbench relation 和 freshness；只有结构化 integrity/freshness 通过才可作为已登记 invariant 一致的证据。非 admin 403、无 PostgreSQL 连接 503，发现问题返回 200 + 有上限样本，不写入修复。
- admin 在 16 个业务/导入页面运行各自 page Audit，或在 App Health 运行 17 页同快照 System Audit -> 同一 service/repository 边界检查 canonical source、read model/source_versions、durable refresh 和已登记 relation consumer；dirty/outbox 查询按 tenant 隔离，返回 integrity/freshness/queue 三类状态。unknown 页面状态不得显示 Fresh，样本截断必须显式标记。
- System Audit external proof -> 每页通过 registry 显式映射到 bank/OA/invoice/ETC domain；四份 complete manifest 与 canonical exact item set、关键字段 fingerprint、count/amount/tax controls 双向 equality。相同 count/总额替换一条、字段漂移、漏项、多项、重复、latest revoked/expired 都失败关闭；缺证据为 unknown。旧 free-text `_external_evidence` classifier 由静态 guard 禁止回流。
- admin 调用 `/api/operations/app-health/input-invoice-usage-refresh` -> 后端只校验 scope 并通过 durable runtime queue 入队 `input_invoice_usage.read_model.refresh` -> 返回 `202` 只表示 refresh 已入队；完成后仍必须复跑 audit 或 operation barrier，不能把 enqueue 成功当成全量正确性证明。
- admin 调用 `/api/operations/app-health/output-invoice-collection-refresh` -> 后端只校验 scope 并通过 durable runtime queue 入队 `output_invoice_collection.read_model.refresh` -> 返回 `202` 只表示 refresh 已入队；完成后仍必须复跑 audit 或 operation barrier，不能把 enqueue 成功当成全量正确性证明。
- authenticated HTTP SLO smoke -> 页面 shell + 真实首屏 API 参数 -> p95/p99 与 freshness 一起判定；普通 API probe 使用 bearer/cookie 登录态，`/api/operations/app-health-dashboard` 标记为 admin auth scope 并在提供 `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` 时使用 admin headers；默认请求 gzip 以匹配浏览器传输口径，解压后提取 read model/cache metadata，`response_bytes` 记录压缩传输字节；如果未提供 token/cookie 返回 auth_missing，不把 401/403 当性能通过；如果 API probe 拿到 `text/html`/HTML 页面壳，按 `html_response_for_api_probe` 失败处理，不能把 Nginx/API prefix 路由错误当成 API 通过；最终 `runtime_sync_closure_gate` 要求 HTTP probe/sample 非空，否则按 `http_slo_empty_samples` 失败。
- readiness payload smoke -> `/fin-ops-api/health/ready` 必须在 1000ms 内返回 JSON，payload 保持轻量，`api_performance.endpoints` 只包含 bounded slow endpoints，并带 `endpoint_count` / `omitted_endpoint_count`；ready payload 不能重复 `storage.runtime_infrastructure`，不能输出完整 `entrypoints` / `worker_metrics` 明细，只保留 counts、status summary 和 bounded problem samples。否则 `health_ready_payload_probe` 按 `slo_miss`、`response_too_large`、`api_performance_endpoints_unbounded`、`api_performance_bound_metadata_missing` 或 `html_response_for_health_ready_probe` 失败。probe 还会输出 `runtime_release_name`、`runtime_blocker_count` 和 `runtime_blockers`，用于无人值守流程先区分 release 未部署、dirty/outbox backlog、failed jobs、worker mismatch 或 Postgres/readiness 状态异常。
- SSE smoke -> `/api/app-health/stream` 和 `/api/workbench/events?month=all` 必须返回 `text/event-stream`，首事件 p95 目标按 `<= 1000ms` 解释；缺 token/cookie 返回 `auth_missing`，HTML fallback、错误事件名、首事件超时或零 probe 均失败；最终 `runtime_sync_closure_gate` 必须把 `sse_first_event_smoke` 纳入必经检查，并用 `sse_smoke_empty_samples` 拒绝空证据。
- runtime/read-model/write/RabbitMQ closure gates 和 scenario discovery -> 缺少 Postgres/RabbitMQ URL 时返回 `configuration_missing` JSON 和退出码 2；Postgres gate 的 payload 必须包含 `blocking_condition=database_url_required`、`required_env`、`next_actions`、`allowed_remote_evidence` 和 `forbidden_without_approval`，主控 workflow 据此进入安全环境配置或生产只读采样分支，不能把缺配置当 pass/skip/SLO 证明。runtime health 必须包含 durable queue、dirty scope、required worker 和 refresh failure facts，空 summary 或缺 worker metrics 按 `runtime_health_missing_facts` 失败；runtime gate 必须包含 health-ready payload check，慢/大/unbounded readiness 不能被最终 gate 漏掉；`read_model_slo_smoke --apply` 必须至少产生一个 planned scope 和结果样本，零 scope/零 result 返回 fail；write-operation audit 必须有真实 event 样本和 expectation 样本，零样本通过会被 runtime gate 按 `write_operation_audit_empty_samples` 拒绝；runtime gate 缺 `--write-scenario`、只 dry-run 或缺 `--write-approval-ticket` 时在 `write_operation_e2e` check 暴露 `missing_args` / `required_args`；runtime gate scenario 文件非法时返回 `input_error`，并阻止 write audit 退回 unscoped real-write audit；write E2E 缺 scenario、空 scenario、scenario contract 非法或 `--apply` 缺 `--approval-ticket` 时返回结构化 JSON，空 scenario error code 为 `scenario_empty`，approval 缺失 error code 为 `write_operation_e2e_requires_approval_ticket` 且不会连接 Postgres 或执行写请求，apply 后零 scenario/result 会按 `write_operation_e2e_empty_samples` 失败；mutating write step 若拿到 200 HTML 页面壳则按 `html_response_for_api_probe` 失败并跳过 write SLO claim；主控 workflow 据此进入环境配置、输入修复、安全凭据、审批或路由修复分支。
- malformed app_status payload -> 前端 mapper 返回 null，不能默认 green。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_app_health_api \
  tests.test_app \
  tests.test_api_performance_metrics \
  tests.test_app_health_service \
  tests.test_audit_input_invoice_usage_read_model_tool \
  tests.test_audit_output_invoice_collection_read_model_tool \
  tests.test_audit_page_business_read_model_tool \
  tests.test_app_health_alert_service \
  tests.test_app_status_overview_service \
  tests.test_background_job_service \
  tests.test_runtime_monitoring \
  tests.test_app_status_readiness_backfill \
  tests.test_runtime_worker_registry \
  tests.test_external_control_evidence_service \
  tests.test_external_control_evidence_repository \
  tests.test_external_control_evidence_tool \
  tests.test_audit_external_control_evidence \
  tests.test_audit_app_health_system \
  tests.test_runtime_queue \
  tests.test_runtime_queue_ops \
  tests.test_deploy_runtime_examples \
  tests.test_http_slo_probe \
  tests.test_sse_smoke_probe \
  tests.test_health_ready_payload_probe \
  tests.test_runtime_sync_closure_gate \
  tests.test_slo_tool_defaults \
  tests.test_write_operation_scenario_discovery \
  tests.test_write_operation_e2e_smoke \
  tests.test_write_operation_slo_audit \
  tests.test_rabbitmq_staging_preflight \
  tests.test_p2p3_closure_summary \
  -v

cd web && npm test -- --run \
  src/test/AppHealthOperationsPage.test.tsx \
  src/test/AppHealthPageAuditApi.test.ts \
  src/test/AppStatusIndicator.test.tsx \
  src/test/AppStatusApi.test.ts \
  src/test/AppHealthStatusContext.test.tsx \
  src/test/AppHealthResolver.test.ts \
  src/test/AppHealthBroadcast.test.tsx

cd web && npm run e2e:smoke

cd web && npm run e2e:production-admin

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

Nightly full suite 应覆盖本模块的后端 app health/status/runtime tests、前端 AppHealth/AppStatus tests、Playwright AppHealth browser smoke、docs verify。模块级快速验证使用上方命令。

## 未测风险

- 系统状态页已补 Spec-first E2E 合同和覆盖映射；本地 covered 不代表真实 PostgreSQL/RabbitMQ/Redis/systemd/Nginx/OA iframe、真实大库 metrics 或 authenticated HTTP/SSE/write-operation SLO 已完成。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker 的 heartbeat、queue backlog、DLQ、readiness convergence 需要 staging 或生产 smoke；本地测试使用 fake repository/connection 证明 contract。
- `tests/test_operations_audit_report.py` 锁定 Audit 使用单一 `REPEATABLE READ READ ONLY` transaction snapshot；`tests/test_audit_page_business_read_model_tool.py` 锁定 canonical expected-set、关键字段/账户余额重算和双向 relation edge mismatch 都是 blocking integrity gate；进/销项 Audit 工具测试锁定共享 relation edge equality 参与 pass gate。
- SSE 经过 Nginx/OA iframe 代理后是否缓冲、断线、回退轮询，需要真实部署 smoke。
- `/api/operations/app-health-dashboard` 的真实大库指标性能、pg_stat_statements 可用性和短 TTL cache 行为需要生产观测；生产 admin Browser smoke 已有脚本和只读 guard，但仍需要真实 admin token/cookie 才能执行通过。
- App Status 和现有 Playwright smoke 只能证明全局运行事实 plane 与 AppHealth dashboard 浏览器 gate，不替代每个业务页面自己的 stale/error/loading 交互测试。

## 2026-07-22 Phase 27 scope 级运行证据

- `tests/test_operations_dashboard_service.py` 覆盖最近 read-model scope evidence：current-scope/full-history 分类、expected/projection source versions、lag、queue wait、handler duration、attempt/retry、dedupe 与 error。
- `web/src/test/AppHealthOperationsPage.test.tsx` 覆盖 scope 类型和 timing/retry 证据展示，不再用一个“同步中”总状态解释所有后台工作。
- 真实 p50/p95/p99、队列等待与逐页面访问收敛仍必须在 Phase 27-07 使用 test-owned 生产 fixture 采集；本地 fake repository 不作为性能结论。
