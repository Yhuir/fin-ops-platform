# 系统状态测试矩阵

> 修改本模块前先读取本文件，确认 App Health / App Status 的事实源、状态优先级、测试入口和旧功能回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| App Health page | `web/src/pages/AppHealthOperationsPage.tsx` | admin-only、只读 dashboard、refetch 失败保留旧 payload、unknown 显示 `--` 而不是 0 |
| Global icon/popover | `web/src/components/shell/AppStatusIndicator.tsx` | icon 必须来自全局 `app_status`，路由切换不改变状态；admin 才显示运维入口 |
| Frontend providers/API | `AppHealthStatusContext`、`features/appHealth/api.ts`、`features/appStatus/api.ts` | SSE/轮询、malformed payload 不得默认 green、App Status mapper 字段兼容 |
| HTTP routes | `server.py` `/api/app-health*`、`/api/operations/app-health-dashboard` | auth guard、SSE contract、dashboard admin-only、cache stale after refetch error |
| Overview service | `AppStatusOverviewService` | green/yellow/red 优先级、dependencies、tasks、worker/outbox 状态；不再消费或输出 legacy read-model diagnostics |
| Runtime repository | `RuntimeMonitoringRepository` | outbox/workers/RabbitMQ/API metrics 聚合；legacy dirty scope/readiness 不再作为健康输入，不可用 snapshot 不能变 green |
| Registries | domain/job/dependency/worker registries | 新 worker/job/dependency 必须同步 registry，否则状态 plane 漏报；新页面不得把 page read-model key 加回 domain registry |
| Runtime ops tools | `runtime_queue_ops`、deploy worker examples | dead letter/replay/worker manifest 操作必须依赖 runtime queue 和 registry |

## 场景覆盖清单

| 场景 | 保护测试 | 说明 |
| --- | --- | --- |
| idle / busy / blocked health API | `tests/test_app_health_api.py`、`tests/test_app_health_service.py`、`tests/test_app_health_alert_service.py` | 覆盖 dirty OA scopes、dependency error、background jobs、SSE 和 alert，并断言不再返回或消费 `workbench_read_model` / `workbench_relation_read_model` |
| App Status overview | `tests/test_app_status_overview_service.py`、`tests/test_background_job_service.py` | 覆盖 registry 一致性、background task、job accepted/progress visible payload、worker missing、runtime unavailable、runtime summary worker/queue 计数、current-effective blocker、covered pending outbox 不进入 backlog、done publish failure 不回流为当前 outbox failed、`oa.sync` 只影响 OA 待付款核对而不把设置页误标 busy、API contract，并断言 `runtime_summary` 不再包含 `read_models` |
| Runtime monitoring metrics | `tests/test_runtime_monitoring.py` | 覆盖 backlog、failed jobs、RabbitMQ、worker metrics、worker mismatch、ready health summary outbox-only SQL；App Status runtime repository 在 `tests/test_app_status_overview_service.py` 额外覆盖 legacy scope、covered outbox row、old failed + current processing 合并、old failed + later pending retry 不重复计入 failed，并断言不再读取 `job.read_model_dirty_scopes` 或 `read_model.app_status_readiness` |
| Operations dashboard data inventory | `tests/test_operations_dashboard_service.py` | 覆盖 dashboard 发票 inventory 读取 `app.oa_attachment_invoice_cache` 时只统计可判定正式发票的去重数量；cache 不可用时显示 unknown，不回退 read_model |
| Health payload size guard | `tests/test_app.py`、`tests/test_app_postgres_mode.py`、`tests/test_api_performance_metrics.py`、`tests/test_prometheus_metrics.py`、`tests/test_health_ready_payload_probe.py` | 覆盖 `/health/ready` 只输出 bounded 最慢 endpoint API performance 摘要和 compact runtime 摘要，不重复 `storage.runtime_infrastructure`、不输出完整 `entrypoints` / `worker_metrics` 明细；Prometheus `/metrics` 与 operations dashboard 仍保留完整 endpoint 明细；生产 probe 会在 readiness 慢、大、未截断、缺 bound metadata 或 HTML fallback 时失败，并从 readiness JSON 提取 `runtime_release_name` / `runtime_blockers`，同时不把 legacy cost statistics historical scope 或 `current_effective=false` optional worker 等非当前事实误判为 blocker，也能从 compact `worker_status_counts` 提取 current-effective worker blocker。 |
| HTTP SLO probe defaults | `tests/test_http_slo_probe.py` | 覆盖 17 个页面 shell、认证态首屏 API、真实首屏 page/page_size、auth 缺失语义、admin-only dashboard probe 的 admin auth scope、默认 gzip 请求/解压通用 metadata 且 `response_bytes` 记录传输字节，以及 API probe 误打到 HTML 页面壳时必须失败；探针不再聚合或判定旧 read-model freshness。 |
| SSE first-event smoke | `tests/test_sse_smoke_probe.py` | 覆盖 `/api/app-health/stream` 的 event-stream 首事件 SLO、auth 缺失、HTML fallback、错误状态码和事件名校验；Workbench page read-model SSE 已移除，不再作为默认 smoke。 |
| P2/P3 closure summary/result classifier | `tests/test_p2p3_closure_summary.py`、`tests/test_p2p3_gate_result_classifier.py` | 覆盖 `.planning/P2P3-CLOSURE-PLAN.md` 的聚合 closure item、final gated smoke matrix、17 页面覆盖映射、当前状态表和 P2/P3 item 表可被解析为 JSON；输出 priority、classification、covered pages、gap、closure evidence、requires_external_evidence、per-item next_actions、page-level next_actions、top-level next_focus 和 next_bounded_action；缺少 ledger 时返回结构化 `input_error`。gate result classifier 读取上一轮 gate JSON 并分类为 environment-required、auth-required、input-required、approval-required、runtime-deploy-or-config-required、durable-evidence-required 或 passed；直接读取 `health_ready_payload_probe` 的 slow/large/unbounded readiness failure 时也进入 runtime-deploy-or-config-required，方便无人值守 workflow 分支。 |
| Closure tool config/input state | `tests/test_slo_tool_defaults.py`、`tests/test_runtime_sync_closure_gate.py`、`tests/test_write_operation_scenario_discovery.py`、`tests/test_write_operation_e2e_smoke.py`、`tests/test_write_operation_slo_audit.py`、`tests/test_rabbitmq_staging_preflight.py` | 覆盖一秒级默认阈值，HTTP/SSE/runtime gate 共享 `FIN_OPS_HTTP_SLO_*` 认证 env，runtime gate 会把普通 bearer headers 和 admin headers 分别传给 HTTP SLO probe，缺少 Postgres/RabbitMQ URL 时 runtime/write/RabbitMQ gates 和 scenario discovery 返回结构化 `configuration_missing`；Postgres gate 缺 URL 时同时输出 `blocking_condition=database_url_required`、`required_env`、安全 `next_actions`、允许的只读远程证据和未经批准禁止动作。runtime health 缺 durable queue/worker facts 不能当 pass，runtime gate 必须包含 health-ready payload check 和 SSE first-event check，authenticated HTTP 零 probe/sample、SSE 零 probe、write-operation audit 零 event/expectation 样本和 write E2E 零 scenario/result 都不能当 pass，scenario discovery 无候选时不写空 scenario 文件，write E2E direct API 空 scenario 返回 `scenario_empty` input error，缺少 `--write-scenario`、`--apply-write-scenarios` 或 `--write-approval-ticket` 时暴露 `missing_args` / `required_args`，direct write E2E `--apply` 缺 `--approval-ticket` 时返回 `approval_missing` 且不连接 Postgres/不发 mutating HTTP，invalid runtime scenario 暴露 `input_error` 且不运行 unscoped write audit，write E2E 缺 scenario/非法 scenario 返回结构化 `input_error`，mutating step 拿到 HTML 页面壳必须失败，均不得 traceback。 |
| Worker/queue ops | `tests/test_runtime_worker_registry.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_queue_ops.py`、`tests/test_deploy_runtime_examples.py` | 覆盖 registry-derived worker、page read-model worker 不回流、outbox replay/release、dead letter handling、deployment examples |
| Frontend dashboard | `web/src/test/AppHealthOperationsPage.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/production-admin-app-health.spec.ts`、`docs/modules/app-health-operations/e2e-spec.md`、`docs/modules/app-health-operations/e2e-coverage.md` | 覆盖只读 dashboard、admin gate、unknown metrics、runtime failure stale payload、worker/queue 总览和状态表格；真实 Chromium 下 admin-only route、protected dashboard API 调用边界和严格浏览器错误捕获。生产 admin smoke 默认 skip，只有显式 `FIN_OPS_E2E_PRODUCTION_ADMIN_SMOKE=1` 和 `FIN_OPS_E2E_ADMIN_TOKEN` 时才用真实 admin cookie 只读验证 `/fin-ops/operations/app-health`、dashboard API、数据/请求/后台三块和零 mutating request。 |
| Frontend global status | `web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/AppStatusApi.test.ts`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/AppHealthResolver.test.ts`、`web/src/test/AppHealthBroadcast.test.tsx` | 覆盖 mapper、icon/popover runtime summary、route independence、SSE/轮询和 BroadcastChannel sync |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_app_status_overview_service.py`、`tests/test_app_health_service.py`、`tests/test_app_health_alert_service.py` | 覆盖状态优先级、domain level、alert/job/dependency 判定；alert 不再消费 legacy page read-model payload。 |
| 2. Service-layer tests | 适用 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py`、`tests/test_operations_dashboard_service.py`、`tests/test_runtime_queue_ops.py`、`tests/test_slo_tool_defaults.py`、`tests/test_runtime_sync_closure_gate.py`、`tests/test_write_operation_scenario_discovery.py`、`tests/test_write_operation_e2e_smoke.py`、`tests/test_write_operation_slo_audit.py`、`tests/test_rabbitmq_staging_preflight.py`、`tests/test_p2p3_closure_summary.py` | 覆盖 service/repository 边界、dashboard inventory 统计口径、runtime snapshot、worker metrics、ops 操作约束、closure gate 配置缺失状态、closure gate health-ready/SSE 必经检查、RabbitMQ staging env gate、runtime health durable queue/worker fact 要求、HTTP/SSE/write audit/write E2E 非空样本要求、write scenario 输入契约、mutating step HTML fallback 拒绝，以及 P2/P3 ledger 到 JSON 的闭环状态解析和 next_focus 分支选择。 |
| 3. API contract tests | 适用 | `tests/test_app.py`、`tests/test_app_health_api.py`、`tests/test_app_status_overview_service.py`、`tests/test_http_slo_probe.py`、`tests/test_sse_smoke_probe.py`、`tests/test_health_ready_payload_probe.py`、`web/src/test/AppStatusApi.test.ts` | 覆盖 `/health/ready` bounded metrics、`/metrics` full metrics、`/api/app-health`、SSE、dashboard admin-only、`app_status` shape 和 `runtime_summary` 映射、SLO probe 首屏 API contract、SSE 首事件 contract、HTML 页面壳误当 API/health-ready 响应的拒绝逻辑、runtime blocker 摘要、malformed payload 拒绝。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_runtime_monitoring.py`、`tests/test_runtime_queue.py`、`tests/test_runtime_worker_registry.py`、`tests/test_background_job_service.py`、`tests/test_app_health_api.py`、`tests/test_app_status_overview_service.py` | 覆盖 outbox、worker heartbeat、RabbitMQ、后台任务 accepted 后 queued payload 立即可见、progress 更新后 active payload 同步变化，并回归 App Health/App Status/operations dashboard 不再暴露 read-model readiness/status 字段。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/AppHealthBroadcast.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/production-admin-app-health.spec.ts`、`docs/modules/app-health-operations/e2e-spec.md`、`docs/modules/app-health-operations/e2e-coverage.md` | 覆盖 dashboard、全局 icon、popover runtime summary、admin link、SSE/轮询、BroadcastChannel、真实浏览器 dashboard/admin gate/session gate smoke、生产 admin AppHealth 只读 smoke 和严格浏览器错误捕获。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_app_health_api.py`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/production-admin-app-health.spec.ts` | 覆盖 job/outbox/worker -> API -> 前端展示的关键路径，以及 session -> route -> dashboard API 的真实浏览器 smoke。生产 admin AppHealth smoke 已有显式 env gate；真实 runtime worker facts 到 UI 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/app-shell.spec.ts`、`web/e2e/production-admin-app-health.spec.ts` | 保护旧页面 route registry、worker manifest、deploy env、App Status 不因路由切换或新 domain 漏报，并保护 dashboard admin-only 浏览器行为和生产只读 gate 不误发写请求。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-21 | Workbench parent generation 正在重试时，旧 `workbench_all_scope_parent_inconsistent` failed outbox 仍进入 App Status queue failed，导致 hover 同时显示 syncing 和 blocked。 | 当前由 outbox-only current-effective 过滤和 Workbench generation consistency 测试覆盖；legacy active dirty scope 覆盖路径已删除。 | covered |
| 2026-06-21 | `/health/ready` 已无 backlog，但 App Status outbox 仍把 `status='done'` 的历史 `publish_status='failed'` / `oa.sync` 行算成当前 failed。 | `tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_ignores_covered_outbox_statuses` | covered |
| 2026-06-21 | `/health/ready` / App Status runtime summary 曾依赖 dirty scope current-effective SQL helper；该路径已删除，测试保护 runtime health 不再读取 dirty scope/readiness。 | `tests/test_runtime_monitoring.py::RuntimeMonitoringRepositoryTests::test_ready_health_summary_uses_lightweight_runtime_contract` | covered |
| 2026-06-21 | Operations dashboard / health summary 直接统计历史 `publish_status=failed` outbox，导致 read model 已 fresh 后仍显示 Worker issue / Queue backlog。 | `tests/test_runtime_monitoring.py::RuntimeMonitoringRepositoryTests::test_dashboard_outbox_metric_only_scans_current_attention_statuses`、`test_health_summary_reports_backlog_failed_jobs_and_worker_status` | covered |
| 2026-06-19 | 生产公网 HTTP SLO probe 未请求 gzip，导致大 JSON API 按非浏览器未压缩传输口径被误判为慢。 | `tests/test_http_slo_probe.py::HttpSloProbeTests::test_collects_samples_with_api_prefix_without_leaking_auth`、`tests/test_http_slo_probe.py::HttpSloProbeTests::test_gzip_json_response_is_decoded_for_metadata` | covered；2026-06-27 已移除同探针的 旧 read-model freshness 聚合，只保留 HTTP/status/latency/cache metadata 口径 |
| 2026-06-19 | 生产 authenticated HTTP SLO 用普通目标 OA bearer 采样 admin-only `/api/operations/app-health-dashboard`，导致 dashboard 固定 403 并把真实 admin credential 缺口混成 API 性能失败。 | `tests/test_http_slo_probe.py::HttpSloProbeTests::test_admin_scoped_probe_uses_admin_headers_without_overriding_user_probes`、`tests/test_runtime_sync_closure_gate.py::RuntimeSyncClosureGateTests::test_gate_passes_admin_headers_to_http_slo_probe` | covered |
| 2026-06-18 | 同一 `cost_statistics active:2026-03` scope 旧 `failed deadlock detected` 已被新 `processing` 重试覆盖，但 App Health 仍显示当前失败，误导用户认为数据域阻断。 | `tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_treats_requeued_cost_statistics_deadlock_as_refreshing` | covered |

本轮同时继续保留“malformed payload 不得默认 green”“runtime unavailable 不得空 green”“dashboard refetch 失败保留旧 payload 但标 warning”“HTTP SLO probe 不得用偏小 page_size 低估真实首屏”“admin-only dashboard probe 必须使用独立 admin auth scope”“P2/P3 SLO 工具缺 DB URL 或 scenario 输入时不得 traceback”“P2/P3 final gate 不得用空 runtime facts、HTTP/SSE、write-audit 或 write-E2E 零样本通过最终闭环”等已有回归保护。

## 关键 smoke flows

- outbox pending/processing -> `/api/app-health` busy/yellow -> App Status popover 显示受影响 domain。
- 真实 Chromium 打开 `/operations/app-health`：admin 渲染 dashboard 数据/请求区；read_export_only、forbidden、expired 不请求 dashboard API。
- 生产 admin Browser smoke：`FIN_OPS_E2E_ADMIN_TOKEN` 注入 `Admin-Token` cookie 后打开 `/fin-ops/operations/app-health`，必须看到 `AppHealth 运维状态`、`app-health-data`、`app-health-requests`、`app-health-runtime`，dashboard API 必须返回 200，页面不能显示 session/admin 权限拦截，且 `POST`/`PUT`/`PATCH`/`DELETE` 请求列表必须为空。
- legacy read model failed/unavailable -> App Status 不再返回 diagnostics/runtime summary，也不把页面域或 overall 标为 blocked/red；写入是否禁用由 `overall.write_safety` 和具体写 API precondition 决定。
- 同一 current-effective scope 旧 failed + 当前 pending/processing -> App Status 显示 runtime processing，不把旧 last_error 当作当前 failure banner。
- 同一 scope 旧 failed outbox + 当前 pending/processing 重试 -> App Status queue 显示当前 pending/processing/backlog，不把旧 failed outbox 当作当前阻断。
- legacy cost statistics scope 或已被后续真实完成事实覆盖的 outbox failure -> App Status 保持当前 canonical 状态，同时通过历史诊断暴露 audit 信息。
- required worker missing/stale/mismatch -> runtime infrastructure warning -> App Health dashboard 和 App Status domain 可定位。
- import/data reset/background job running -> active background task -> App Status 显示任务进度和 affected domains；`BackgroundJobServiceTests.test_job_acceptance_and_progress_visibility_contract` 锁定 job accepted 后 queued payload 立即可见、progress 更新后 active payload 同步变化。
- dashboard refetch 成功后展示数据/请求/后台三块；下一次 refetch 失败时保留旧 dashboard 并显示 warning。
- dashboard 发票来源 `OA 解析` 只展示 OCR 缓存中可判定为正式发票并按强 identity 去重后的数量；附件总数、OCR 候选项总数、短号码票据和非正式票据不得进入该数字。
- authenticated HTTP SLO smoke -> 页面 shell + 真实首屏 API 参数 -> p95/p99 按 HTTP status、latency、HTML fallback 和通用 cache metadata 判定；普通 API probe 使用 bearer/cookie 登录态，`/api/operations/app-health-dashboard` 标记为 admin auth scope 并在提供 `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` 时使用 admin headers；默认请求 gzip 以匹配浏览器传输口径，解压后提取 cache metadata，`response_bytes` 记录压缩传输字节；如果未提供 token/cookie 返回 auth_missing，不把 401/403 当性能通过；如果 API probe 拿到 `text/html`/HTML 页面壳，按 `html_response_for_api_probe` 失败处理，不能把 Nginx/API prefix 路由错误当成 API 通过；最终 `runtime_sync_closure_gate` 要求 HTTP probe/sample 非空，否则按 `http_slo_empty_samples` 失败。
- readiness payload smoke -> `/fin-ops-api/health/ready` 必须在 1000ms 内返回 JSON，payload 保持轻量，`api_performance.endpoints` 只包含 bounded slow endpoints，并带 `endpoint_count` / `omitted_endpoint_count`；ready payload 不能重复 `storage.runtime_infrastructure`，不能输出完整 `entrypoints` / `worker_metrics` 明细，只保留 counts、status summary 和 bounded problem samples。否则 `health_ready_payload_probe` 按 `slo_miss`、`response_too_large`、`api_performance_endpoints_unbounded`、`api_performance_bound_metadata_missing` 或 `html_response_for_health_ready_probe` 失败。probe 还会输出 `runtime_release_name`、`runtime_blocker_count` 和 `runtime_blockers`，用于无人值守流程先区分 release 未部署、outbox backlog、failed jobs、worker mismatch 或 Postgres/readiness 状态异常。
- SSE smoke -> `/api/app-health/stream` 必须返回 `text/event-stream`，首事件 p95 目标按 `<= 1000ms` 解释；缺 token/cookie 返回 `auth_missing`，HTML fallback、错误事件名、首事件超时或零 probe 均失败；最终 `runtime_sync_closure_gate` 必须把 `sse_first_event_smoke` 纳入必经检查，并用 `sse_smoke_empty_samples` 拒绝空证据。Workbench page read-model SSE 已移除，不再作为默认 probe。
- runtime/write/RabbitMQ closure gates 和 scenario discovery -> 缺少 Postgres/RabbitMQ URL 时返回 `configuration_missing` JSON 和退出码 2；Postgres gate 的 payload 必须包含 `blocking_condition=database_url_required`、`required_env`、`next_actions`、`allowed_remote_evidence` 和 `forbidden_without_approval`，主控 workflow 据此进入安全环境配置或生产只读采样分支，不能把缺配置当 pass/skip/SLO 证明。runtime health 必须包含 durable queue、required worker 和 runtime failure facts，空 summary 或缺 worker metrics 按 `runtime_health_missing_facts` 失败；runtime gate 必须包含 health-ready payload check，慢/大/unbounded readiness 不能被最终 gate 漏掉；write-operation audit 必须有真实 event 样本和 expectation 样本，零样本通过会被 runtime gate 按 `write_operation_audit_empty_samples` 拒绝；runtime gate 缺 `--write-scenario`、只 dry-run 或缺 `--write-approval-ticket` 时在 `write_operation_e2e` check 暴露 `missing_args` / `required_args`；runtime gate scenario 文件非法时返回 `input_error`，并阻止 write audit 退回 unscoped real-write audit；write E2E 缺 scenario、空 scenario、scenario contract 非法或 `--apply` 缺 `--approval-ticket` 时返回结构化 JSON，空 scenario error code 为 `scenario_empty`，approval 缺失 error code 为 `write_operation_e2e_requires_approval_ticket` 且不会连接 Postgres 或执行写请求，apply 后零 scenario/result 会按 `write_operation_e2e_empty_samples` 失败；mutating write step 若拿到 200 HTML 页面壳则按 `html_response_for_api_probe` 失败并跳过 write SLO claim；主控 workflow 据此进入环境配置、输入修复、安全凭据、审批或路由修复分支。
- malformed app_status payload -> 前端 mapper 返回 null，不能默认 green。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_app_health_api \
  tests.test_app \
  tests.test_api_performance_metrics \
  tests.test_app_health_service \
  tests.test_app_health_alert_service \
  tests.test_app_status_overview_service \
  tests.test_background_job_service \
  tests.test_runtime_monitoring \
  tests.test_runtime_worker_registry \
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
- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker 的 heartbeat、queue backlog、DLQ、runtime convergence 需要 staging 或生产 smoke；本地测试使用 fake repository/connection 证明 contract。
- SSE 经过 Nginx/OA iframe 代理后是否缓冲、断线、回退轮询，需要真实部署 smoke。
- `/api/operations/app-health-dashboard` 的真实大库指标性能、pg_stat_statements 可用性和短 TTL cache 行为需要生产观测；生产 admin Browser smoke 已有脚本和只读 guard，但仍需要真实 admin token/cookie 才能执行通过。
- App Status 和现有 Playwright smoke 只能证明全局运行事实 plane 与 AppHealth dashboard 浏览器 gate，不替代每个业务页面自己的 stale/error/loading 交互测试。
