# 系统状态 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- App Health / App Status 是全局运行事实的只读投影，不是页面状态聚合器。前端只展示后端 `app_status`，不能用当前 route、表格 loading 或组件本地状态推导 green/yellow/red。
- 绿色状态必须有 readiness 证明。registry 中的 read model 如果缺少 readiness 记录，必须 busy/yellow；runtime snapshot unavailable 必须 blocked/red，不能空 green。
- Operations dashboard 是 admin-only 只读入口，不执行 retry、acknowledge、requeue、republish 或 repair。运维动作仍走 runbook/CLI/API 专门入口。
- Registry 强一致是本模块的核心防线：新增页面、read model、worker、job type 或 dependency 时，必须同步 domain/read model/job/dependency/worker registries 和测试。
- 本模块页面级 Spec-first 状态为 `spec-first-covered`：本地测试覆盖 service/API/UI contract、admin-only dashboard Browser、session gate 和 strict Browser 错误捕获；真实 systemd/RabbitMQ/Redis/Nginx SSE/大库指标仍需 staging/生产 smoke。

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

## 2026-07-05 - App Health SSE first-event heartbeat

- 目标：让 `/api/app-health/stream` 的首事件在 1 秒 SLO 内稳定到达，避免 SSE smoke 把完整 AppHealth 大 JSON 传输耗时当作连接首事件耗时。
- 影响范围：`Application._handle_api_app_health_stream(...)` 的事件顺序；不改变 `/api/app-health` payload、不改变前端 AppHealth 状态更新事件、不改变 operation barrier 或写安全判断。
- 关键决策：SSE 建连后先发送小型 `heartbeat` 事件，再构建并发送完整 `app_health` snapshot。前端仍只监听 `app_health` 并据此更新状态；SSE probe 的 expected prefixes 已允许 `heartbeat`，因此该改动只优化首事件/保活，不降低运行状态事实要求。
- 文档影响：同步本实施记录。
- 测试覆盖：更新 `tests/test_app_health_api.py::AppHealthApiTests::test_app_health_stream_returns_sse_snapshot_and_heartbeat`，锁定首事件为 connected heartbeat，后续仍发送完整 app_health 和 heartbeat。
- 验证命令：`python3 -m pytest tests/test_app_health_api.py::AppHealthApiTests::test_app_health_stream_returns_sse_snapshot_and_heartbeat tests/test_sse_smoke_probe.py -q`。
- 未测风险：真实生产 Nginx/SSE 仍需发布后复跑 `sse_smoke_probe --target-ms 1000`；本地测试只证明事件顺序和 probe contract。

## 2026-07-05 - App Health first-response hot path

- 目标：压缩 `/api/app-health` 和 SSE first event 的首包耗时，避免运行状态页面自身成为慢操作。
- 影响范围：`Application._build_app_health_snapshot(...)`、展示型 App Status runtime snapshot 读取、ETC 发票列表序列化、Operations dashboard freshness warning 聚合、`/health/ready` runtime summary 和 HTTP SLO probe 默认参数；不改变权限、审计、业务状态或 operation barrier。
- 关键决策：`/api/app-health` 一次请求只构建一次 snapshot，alerts 评估后直接注入同一 payload；`_app_status_runtime_statuses()` 仅对展示型 app-health/oa-sync status 使用 1 秒 TTL，`/api/operation-barrier/status` 继续直读 runtime snapshot；ETC 列表页不逐行探测对象存储附件存在性，只根据已持久化路径给 `has_pdf/has_xml`；`/health/ready` 主动跳过 RabbitMQ Management API，防止可选管理接口拖慢 readiness；历史 optional worker warning 保留行级明细但不污染 dashboard 全局 freshness。
- 文档影响：同步本实施记录和 `docs/operations/monitoring.md`。
- 测试覆盖：`tests/test_app_health_api.py` 覆盖 snapshot 单次构建和 runtime snapshot 短缓存；`tests/test_etc_backend.py` 覆盖 ETC 列表序列化不探测对象存储；`tests/test_operations_dashboard_service.py` 覆盖 optional historical worker warning 不进入全局 freshness；`tests/test_postgres_state_store.py` 覆盖 ready health 跳过 RabbitMQ Management；`tests/test_http_slo_probe.py` 覆盖 workbench groups summary probe。
- 验证命令：`python3 -m pytest tests/test_app_health_api.py::AppHealthApiTests::test_app_health_builds_snapshot_once_per_request tests/test_app_health_api.py::AppHealthApiTests::test_app_health_caches_runtime_snapshot_briefly -q`；`python3 -m pytest tests/test_etc_backend.py::EtcServiceTests::test_etc_invoice_list_serializer_does_not_probe_attachment_storage -q`；`python3 -m pytest tests/test_operations_dashboard_service.py::OperationsDashboardServiceTests::test_optional_historical_worker_warning_stays_row_level_only tests/test_postgres_state_store.py::PostgresStateStoreTests::test_ready_health_summary_uses_lightweight_runtime_summary tests/test_http_slo_probe.py::HttpSloProbeTests::test_default_probes_cover_page_domains_and_known_slow_endpoints -q`。
- 未测风险：本地测试不证明公网 Nginx、真实 PostgreSQL 大库、真实 RabbitMQ Management 或 SSE 网络 p95；发布后仍需 authenticated HTTP/SSE SLO 和 `/health/ready` probe 复跑。

## 2026-06-30 - App Health 流水/发票/OA 导入统计模块化口径

- 目标：在 AppHealth 运维状态主页面展示流水、手工发票、OA 解析和 OA 单据同步的每次导入数量，默认只展示最新 5 条，并通过右侧抽屉查看全量历史；同时把发票来源统计收敛为 `手工导入` 和 `OA 解析` 两类。
- 影响范围：`OperationsDashboardService`、`/api/operations/app-health-dashboard` response shape、`AppHealthOperationsPage`、前端 AppHealth 类型、模块文档和运维/API 合同；不新增 read model、worker 或写操作。
- 关键决策：发票 inventory 的事实源从 OA OCR cache 改为 canonical `app.invoices.source_links`。`manual_invoice_import` 计入 `手工导入`，`oa_attachment_invoice` 计入 `OA 解析`，同时有 OA 来源但没有手工导入来源的 active 发票计入 `OA 解析` 后面的括号数。`普通导入` 不再展示；`ETC` 已包含在手工导入中，不单独展示。OA 解析仍是校验/补充来源：只有不存在于发票池并被 promotion 的 OA 附件发票才通过 canonical source link 进入统计。
- 导入历史 I/O：后端输出 `data_inventory.import_events` 全量列表。流水/手工发票读取 `app.import_batches.success_count`；OA 解析按 canonical OA source link 创建时间聚合并输出补充数；OA 单据同步读取 `app.oa_sync_runs(sync_type='oa_projection').upserted_count`。前端主页面截取最新 5 条，抽屉展示全量。
- 文档影响：更新本模块 README、boundary-io、tests、运维 monitoring 和 API contracts。
- 测试覆盖：`tests/test_operations_dashboard_service.py` 覆盖 source_links 统计、OA supplementary count、导入事件和 import history 降级；`tests/test_app_health_api.py` 覆盖 admin dashboard API 新 shape；`web/src/test/AppHealthOperationsPage.test.tsx` 覆盖页面不显示 `普通导入`/`ETC`、`OA 解析` 括号数、最新 5 条和抽屉全量历史。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest -q tests/test_operations_dashboard_service.py`；`PYTHONPATH=backend/src python3 -m pytest -q tests/test_app_health_api.py`；`cd web && npm test -- --run src/test/AppHealthOperationsPage.test.tsx`。
- 未测风险：历史 OA 解析“每次导入”目前由 canonical source link `created_at` 按秒聚合，这是现有 durable fact 能提供的最小可追踪粒度；若后续需要严格 worker-run 级别的 OA 附件发票 promotion 批次，需要在 promotion 写入时同步记录专门的 `oa_sync_runs` 或 import event fact。

## 2026-06-21 - App Status outbox 与 ready summary current-effective 口径对齐

- 目标：修复 `/health/ready` 和 ready summary 已显示无 backlog/failed，但左上角 App Status 仍显示一个历史 `oa.sync` failed 的不一致。
- 影响范围：`RuntimeMonitoringRepository.app_status_runtime_snapshot()` 的 outbox 聚合；不改变 `job.outbox_events` durable facts、不改变 OA sync worker、不改变 ready health summary API shape。
- 关键决策：App Status outbox 查询必须在 SQL `where` 层复用 current-effective predicate，并且只有 `status <> 'done'` 的 publish failure 才能作为当前 publish issue。`status='done'` 但保留旧 `publish_status='failed'` 的历史行不应重新映射成当前 failed。
- 文档影响：更新系统状态实施记录和测试矩阵。
- 测试覆盖：`tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_ignores_covered_outbox_statuses` 锁定 App Status outbox SQL 带 current-effective done/fresh 覆盖，并拒绝把 done publish failure 作为当前 issue。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_app_status_overview_service.py tests/test_runtime_monitoring.py -q`。
- 未测风险：本地测试证明 SQL contract；真实生产需要发布后复查 App Status runtime snapshot，确认 read model/outbox/worker attention 均为空。

## 2026-06-21 - Workbench all 聚合事件抢占导致 App Status 长期刷新中

- 目标：解释并修复 Workbench 业务生成已可配对后，左上角仍显示 Workbench refreshing/backlog 的队列层原因。
- 影响范围：App Status runtime summary、Workbench read model pending/backlog 可见性、runtime worker dependency-not-fresh 退避策略；不改变 App Health 前端展示或 `/api/app-health` contract。
- 关键决策：App Health 的 pending/backlog 是正确症状，真实根因在 runtime worker 调度：`workbench:all` aggregate-only 事件遇到 `parent_scope_keys=2026-02` 未 fresh 时按 0.25s 重发，抢占了月 scope refresh。修复应在 worker 层把 same-scope parent dependency 改为 retry 级退避，而不是在 App Status 中隐藏 pending。
- 文档影响：runtime-workers 模块记录调度 contract；本模块记录用户可见状态原因和生产验证要求。
- 测试覆盖：`tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_requeues_same_scope_parent_when_generation_is_inconsistent`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py -q`。
- 未测风险：生产发布后仍需观察 pending `workbench.read_model.refresh` 是否自然 drain 或被后续 fresh readiness 覆盖，确认左上角 queue/read model attention 清零。

## 2026-06-21 - Ready health summary current-effective SQL 修复

- 目标：修复左上角运行状态和 `/health/ready` 相关 runtime summary 在查询 dirty scope current-effective 口径时触发 PostgreSQL syntax error，导致用户看到阻断、failed/backlog/刷新中残留但 readiness 诊断不可信的问题。
- 影响范围：`RuntimeMonitoringRepository.ready_health_summary()`、App Status runtime summary、生产 readiness smoke；不改变 dirty scope/outbox 表结构、不改变 worker claim/complete 行为、不改变业务写入流程。
- 关键决策：`ready_health_summary()` 必须和 `health_summary()` / App Status snapshot 使用同一 current-effective dirty-scope 过滤 SQL；SQL helper 必须在 Python 层插值后再提交给 PostgreSQL，不能把 `{_current_effective_dirty_scope_predicate_sql()}` 之类模板文本原样发给数据库。查询异常应作为 runtime unavailable 暴露，不能吞成空绿色。
- 文档影响：更新系统状态 README、测试矩阵和本实施记录；关联台/往来款文档继续记录业务闭环读模型归属。
- 测试覆盖：`tests/test_runtime_monitoring.py::RuntimeMonitoringRepositoryTests::test_ready_health_summary_uses_lightweight_runtime_contract` 锁定 ready summary 不返回 heavyweight payload、不扫描慢事件明细，并断言执行 SQL 不包含未插值 helper 模板。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_monitoring.py::RuntimeMonitoringRepositoryTests::test_ready_health_summary_uses_lightweight_runtime_contract -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_monitoring.py -q`。
- 未测风险：本地测试证明 SQL contract；真实生产仍需发布后调用 production `ready_health_summary()` 和 App Status snapshot，确认没有 syntax error 且 current-effective queue/dirty counts 收敛。

## 2026-06-21 - Active dirty scope 覆盖历史 outbox/read model 阻断

- 目标：修复 Workbench parent generation 正在重刷时，App Status 仍显示旧 `workbench_all_scope_parent_inconsistent`、`1 failed` 和 blocked/red 的问题。
- 影响范围：`RuntimeMonitoringRepository.app_status_runtime_snapshot()`、`health_summary()`、dashboard outbox current-effective 过滤、Workbench refresh-status 进入 App Status 的状态口径；不改变业务写接口、worker claim/complete 行为或 read model durable queue 事实源。
- 关键决策：同一 read model scope 已存在 `job.read_model_dirty_scopes.status in ('pending','processing')` 且更新时间覆盖旧 outbox failure 时，旧 failed/dead-letter/publish failure 不再参与当前 queue failed/backlog。Workbench active generation consistency failure 在同 scope 有 active repair 时展示为 `refreshing`，保留 `consistency_status=failed` 和 stale reason 供诊断，但不再把旧 `last_error` 推为当前阻断。
- 文档影响：同步系统状态状态机/测试矩阵、关联台状态机和 runtime worker 测试矩阵。
- 测试覆盖：新增 `tests/test_app_status_overview_service.py::AppStatusRuntimeRepositoryTests::test_runtime_repository_ignores_failed_outbox_row_covered_by_active_dirty_scope`，以及 Workbench repository active repair 回归。
- 验证命令：见本轮最终执行记录。
- 未测风险：本地 fake repository/connection 证明 current-effective contract；真实生产仍需发布后观察对应 dirty/outbox scope 自然 drain，若某个 failed 没有 active dirty scope、later done 或 fresh readiness 覆盖，仍会继续作为真实 failed 暴露。

## 2026-06-21 - Runtime outbox dashboard current-effective 口径收敛

- 目标：修复系统状态后台显示 `Read model fresh` 但 `Worker issue` / `Queue backlog` 仍被历史 RabbitMQ publish failure 长期拉高的问题。
- 影响范围：`RuntimeMonitoringRepository.health_summary()`、`ready_health_summary()`、`dashboard_outbox_metric()` 和 pending outbox scope 聚合；不改变业务写接口、read model refresh worker 执行逻辑或 Operations dashboard API shape。
- 关键决策：dashboard/health summary 与 App Status current-effective outbox 保持同类证明：成本统计 legacy scope 不计当前问题；`failed/dead_lettered/publish_failed` 和 `publish_status=failed` 只有在没有后续同 tenant/event/scope `done` 事件、且没有后续同 scope fresh readiness 时才参与当前 backlog/failed 指标。未覆盖的 publish failure 仍保留为当前问题。
- 文档影响：更新本模块测试矩阵和实施记录。
- 测试覆盖：`tests.test_runtime_monitoring.RuntimeMonitoringRepositoryTests.test_dashboard_outbox_metric_only_scans_current_attention_statuses` 锁定 dashboard outbox SQL；`test_health_summary_reports_backlog_failed_jobs_and_stale_dirty_scopes` 锁定 health summary publish/backlog SQL 也使用 later done/fresh readiness 过滤。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地测试证明 SQL contract；真实 PostgreSQL 上历史 backlog 数字下降幅度需要部署后用生产只读 dashboard/SQL 复验。该修复不声称降低 worker 刷新执行耗时，`workbench` p99 仍需依赖 slow event samples 做后续定量优化。

## 2026-06-21 - OA 解析发票 inventory 口径收敛

- 目标：修正系统状态 `发票 > OA 解析` 把 OCR 候选项总数展示为发票数的问题，只展示 OCR 缓存中可识别为正式发票的去重数量。
- 影响范围：`OperationsDashboardService._oa_attachment_invoice_inventory()`、`/api/operations/app-health-dashboard` 的 dashboard data inventory 语义、系统状态和运维监控文档；不改变 `app.invoices`、OA 附件缓存、Workbench read model 或前端 API shape。
- 关键决策：优先读取 `app.oa_attachment_invoice_cache.invoices`，只保留具备完整发票号码、开票日期、购销方税号、价税合计，且 `document_kind` / `invoice_kind` 可判定为正式发票的 OCR 结果；最终按强 identity 去重。非正式票据、短号码票据、附件总数和 OCR 候选项总数不进入 `OA 解析` 数字。
- 文档影响：更新本模块 README、测试矩阵和 `docs/operations/monitoring.md`。
- 测试覆盖：`tests/test_operations_dashboard_service.py::OperationsDashboardServiceTests::test_oa_attachment_inventory_uses_cache_before_workbench_rows` 锁定 cache SQL 使用正式发票去重口径，并保留 cache missing 时回退 `read_model.workbench_rows` 的旧行为。
- 验证命令：`PYTHONPATH=backend/src pytest -q tests/test_operations_dashboard_service.py`；`PYTHONPATH=backend/src python -m compileall -q backend/src/fin_ops_platform/services/operations_dashboard.py`；生产库只读 SQL 校验当前 OCR 缓存正式发票去重数为 1095，旧候选项总数 1731 不再作为展示口径。
- 未测风险：本地单测锁定 SQL contract，不启动真实前端；已用真实数据库只读 SQL 校验当前数据口径。运行中的后端进程需要重启或重新加载代码后才会显示新数字。

## 2026-06-20 - Read Model / Worker 全局状态摘要可见

- 目标：让用户不用进入具体业务页面，也能从左上角 App Status hover 和 `/operations/app-health` 看到 read model 是否 fresh、worker 是否 active/working、queue 是否存在 backlog。
- 影响范围：`/api/app-health.app_status.runtime_summary`、`AppStatusIndicator`、`AppHealthOperationsPage`、系统状态测试矩阵；不改变 read model refresh、worker 执行、queue 写入或业务写接口。
- 关键决策：后端 `AppStatusOverviewService` 统一聚合 runtime summary，前端只展示后端事实。worker `working/running/processing` 是正常工作态，不计入 issue；warning、stale、missing、mismatch、unavailable 才计入 issue。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md`、`e2e-spec.md` 和本实施记录。
- 测试覆盖：新增/更新 `tests.test_app_status_overview_service.AppStatusOverviewServiceTests.test_runtime_summary_counts_read_models_workers_and_queue_backlog`、`web/src/test/AppStatusApi.test.ts` runtime summary mapper、`web/src/test/AppStatusIndicator.test.tsx` popover runtime summary、`web/src/test/AppHealthOperationsPage.test.tsx` dashboard runtime overview。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service -v`；`cd web && npm test -- --run src/test/AppStatusApi.test.ts src/test/AppStatusIndicator.test.tsx src/test/AppHealthOperationsPage.test.tsx`；`python3 -m py_compile backend/src/fin_ops_platform/services/app_status_overview_service.py`。
- 未测风险：本地测试证明 payload 和 UI contract；真实生产 systemd/RabbitMQ/Redis/Nginx/SSE、大库指标和实际 worker drain 仍需生产只读 smoke 或运行时 gate 证明。
- 后续事项：如果后续新增 read model、worker、job type 或 dependency，必须同步 registry 和 runtime summary 相关测试，不能只改 UI 文案。

## 2026-06-20 - 生产 Browser smoke 使用 Admin-Token 闭合 P1 只读 gate

- 目标：用真实生产 `Admin-Token` 执行只读 Playwright smoke，验证 admin AppHealth 页面和核心 route shell 不再停留在登录态、加载态或隐藏浏览器错误。
- 影响范围：生产 Browser smoke 证据和 P1 gate 状态；不改变产品代码、后端 API、权限、read model、worker 或生产数据。
- 执行方式：通过 macOS 隐藏输入框临时接收 `Admin-Token`，仅注入当前 Playwright 进程环境，不打印 token、不写入文件；`FIN_OPS_E2E_SKIP_WEBSERVER=1`，`PLAYWRIGHT_BASE_URL=https://www.yn-sourcing.com`。
- 生产证据：`web/e2e/production-admin-app-health.spec.ts` 1/1 passed，admin-only AppHealth 页面打开、dashboard API 返回 200，且无 `POST`/`PUT`/`PATCH`/`DELETE` 请求；同一 token 作为 `FIN_OPS_E2E_OA_TOKEN` 运行 `web/e2e/production-route-shell.spec.ts` 1/1 passed，核心页面 route shell 均未触发“缺少 OA 登录态”“正在加载页面”或 mutating request。
- 关键决策：该 smoke 证明生产浏览器外壳、admin AppHealth 入口和核心页面 session gate 可用；它仍是 route-shell 级只读 smoke，不替代每个页面的完整业务流程 E2E，也不证明 write-operation apply。
- 测试覆盖：复用 `production-admin-app-health.spec.ts` 和 `production-route-shell.spec.ts` 的只读 request guard、session/loading 文案检查和 dashboard 200 断言。
- 验证命令：`FIN_OPS_E2E_PRODUCTION_ADMIN_SMOKE=1 FIN_OPS_E2E_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=https://www.yn-sourcing.com npx playwright test e2e/production-admin-app-health.spec.ts --project=chromium`；`FIN_OPS_E2E_PRODUCTION_SMOKE=1 FIN_OPS_E2E_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=https://www.yn-sourcing.com npx playwright test e2e/production-route-shell.spec.ts --project=chromium`。
- 未测风险：P2 direct read model SLO dry-run 仍需安装 root-owned DryRun helper 或提供安全 DB URL；6 个 OA attachment invoice cross-OA duplicate 仍需单独只读语义审计。

## 2026-06-20 - P0/P1/P2 生产安全 gate 闭合

- 目标：完成 P0 runtime/DB 表级只读证据、P1 production read-only Browser smoke 和 P2 critical read model dry-run，作为后续逐页面 Spec-first E2E 的生产基础设施前置 gate。
- P0 证据：公网 `health_ready_payload_probe` 通过，`health_status=ready`、`runtime_blocker_count=0`、release 为 `codex-http-slo-gzip-probe-3546e985-20260619210708`；生产 API、RabbitMQ dispatcher 和 20 个 worker active；PostgreSQL `BEGIN READ ONLY` 聚合显示 `job.outbox_events` 157144 行全部 `done`、非 done 为空、recent `failed`/`dead_lettered`/`publish_failed` 样本为空，`job.read_model_dirty_scopes` 143101 行全部 `done`，`read_model.app_status_readiness` 169 行全部 `fresh`。
- P1 证据：`production-admin-app-health.spec.ts` 和 `production-route-shell.spec.ts` 均通过，无 mutating request，无 session/permission/loading gate。
- P2 证据：生产 helper 已安装 `read-model-slo-smoke` dry-run 子命令，SHA256 `9e8d57011e0b5b63e136a2159153cb943a31e6987162900a34a849f73eff7e89`；`read-model-slo-smoke ... --critical-only --target-ms 5000` 返回 `status=dry_run`、`planned_scope_count=15`、`missing_read_model_keys=[]`，未执行 `--apply`、未 enqueue、未写 DB。
- 关键决策：本 gate 完成的是生产基础设施只读闭环，不等于每个页面每个功能完整业务 E2E；direct read model `--apply` 和业务 write-operation E2E 仍需要单独审批与安全 scenario。
- 文档影响：同步 read-models 实施记录中的 P0 DB 表级聚合和 P2 dry-run 证据。
- 未测风险：6 个 OA attachment invoice cross-OA duplicate 仍需单独只读语义审计与 source alias/migration identity 修复设计。

## 2026-06-20 - health-ready probe gzip JSON 解压与公网只读复验

- 目标：修复 `health_ready_payload_probe` 对公网 gzip JSON readiness 响应的误判，避免将真实 `ready` payload 记录为 `invalid_json_response`。
- 影响范围：`fin_ops_platform.tools.health_ready_payload_probe`、App Health 生产只读 readiness 证据；不改变后端 `/health/ready` API、Nginx 配置、业务 API、权限或 read model/worker 行为。
- 根因：`health_ready_payload_probe` 复用 `http_slo_probe._auth_headers()`，默认发送 `Accept-Encoding: gzip`，但读取响应后没有复用 gzip 解压逻辑；公网 `https://www.yn-sourcing.com/fin-ops-api/health/ready` 返回 gzip 压缩 JSON 时，probe 在解析压缩字节流前就进入 `invalid_json_response`。
- 修复：`health_ready_payload_probe` 读取 body 后先调用 `http_slo_probe._decoded_response_body(...)`，与 HTTP SLO probe 的 gzip 处理保持一致。
- 生产复验证据：公网 `health_ready_payload_probe --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --target-ms 1000 --json` 通过，`elapsed_ms=195.12`、`health_status=ready`、`runtime_blocker_count=0`、`api_performance_endpoints_returned=20`、`api_performance_endpoint_count=73`、`runtime_release_name=codex-http-slo-gzip-probe-3546e985-20260619210708`。
- 当前 closure gate：本地 `runtime_sync_closure_gate --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --allow-unauthenticated-http --health-ready-target-ms 1000 --json` 仍按安全合同返回 `postgres_configuration_missing` / `database_url_required`，不能把缺 DB URL 当通过；该命令未触发 `--apply`、未执行业务写操作。
- 测试覆盖：`tests.test_health_ready_payload_probe.HealthReadyPayloadProbeTests.test_decodes_gzip_ready_payload` 覆盖 gzip JSON readiness 解压；既有 bounded payload、HTML fallback、runtime blocker 提取测试保持通过。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_health_ready_payload_probe -v`；`python3 -m py_compile backend/src/fin_ops_platform/tools/health_ready_payload_probe.py tests/test_health_ready_payload_probe.py`；公网 health-ready probe；runtime closure gate 只读缺配置检查。
- 未测风险：P1 Browser smoke 仍缺 `FIN_OPS_E2E_OA_TOKEN` / `FIN_OPS_E2E_ADMIN_TOKEN`；P2 direct read model SLO dry-run 仍需安装已补强的 root-owned helper 或提供安全 DB URL。

## 2026-06-19 - 生产外部 gate 输入预检

- 目标：把生产 admin Browser、authenticated HTTP/SSE 和 controlled write-operation apply 的缺凭证/缺审批状态从人工判断改为可复跑的只读预检，避免无人值守流程把外部输入缺失误判为产品代码失败。
- 影响范围：`fin_ops_platform.tools.production_external_gate_preflight`、`scripts/verify.sh infra-smoke`、全局 testing/nightly 文档、运维 monitoring runbook 和 testing closure 状态；不改变 AppHealth 页面、dashboard 权限、HTTP SLO 采样逻辑或写操作 smoke 的审批约束。
- 关键决策：预检只输出 gate 状态和 env 名称，不输出 token、cookie、数据库 URL 或 scenario 内容；`--require-ready` 缺输入返回 `2`。生产 write-operation apply 仍必须同时具备真实认证、PostgreSQL URL、安全隔离 scenario 和审批 ticket。
- 文档影响：更新本文件、`docs/dev/testing.md`、`docs/dev/nightly-ci.md`、`docs/operations/monitoring.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `tests/test_production_external_gate_preflight.py`，覆盖缺输入、全输入和 `--require-ready` 退出码，并断言 secret 值不会出现在 JSON 报告中。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_production_external_gate_preflight -v`；`python3 -m py_compile backend/src/fin_ops_platform/tools/production_external_gate_preflight.py tests/test_production_external_gate_preflight.py`；`PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.production_external_gate_preflight --json`；`bash scripts/verify.sh docs`。
- 未测风险：当前生产仍缺真实 admin token/cookie 和写操作 approval ticket，因此 admin AppHealth Browser smoke 与真实 mutating write-operation apply 仍不能标记通过。

## 2026-06-19 - 生产 admin AppHealth Browser smoke gate

- 目标：把 admin-only AppHealth 页面从“缺真实 admin 浏览器验证”推进为可复跑的生产只读 Playwright gate，避免只靠 API probe 或本地 mock 证明页面可用。
- 影响范围：`web/e2e/production-admin-app-health.spec.ts`、`web/package.json`、Playwright strict diagnostics guard、系统状态测试矩阵和全局 testing closure 状态；不改变 AppHealth 产品逻辑、dashboard 权限、API contract 或运行时指标采集。
- 关键决策：生产 admin smoke 默认跳过；只有显式设置 `FIN_OPS_E2E_PRODUCTION_ADMIN_SMOKE=1` 和 `FIN_OPS_E2E_ADMIN_TOKEN` 时才向 `www.yn-sourcing.com` 注入 `Admin-Token` cookie。测试关闭 screenshot/trace/video，监听并拒绝 `POST`/`PUT`/`PATCH`/`DELETE`，断言 `/fin-ops/operations/app-health` 展示 `AppHealth 运维状态`、数据/请求/后台三块，且 `/api/operations/app-health-dashboard` 返回 200。
- 文档影响：更新本文件、`tests.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/production-admin-app-health.spec.ts`；扩展 `tests/test_playwright_e2e_strict_diagnostics.py`，静态锁定 env gate、token 来源、只读请求 guard、关闭敏感产物和 npm script。
- 验证命令：`cd web && FIN_OPS_E2E_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=https://www.yn-sourcing.com npx playwright test e2e/production-admin-app-health.spec.ts --project=chromium` 默认 skip；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`；`cd web && npx tsc --noEmit --pretty false`；`bash scripts/verify.sh docs`。
- 未测风险：当前没有真实 admin token/cookie，因此本轮只能证明生产 admin Browser gate 已编码、默认安全、可复跑；实际 dashboard 200 和大库指标渲染仍需 admin 凭据后执行。

## 2026-06-19 - gzip-aware HTTP SLO probe 生产复验

- 目标：修正公网 HTTP SLO 探针与真实浏览器传输口径不一致的问题，并复验上一轮 user-level 慢项是否仍真实存在。
- 影响范围：`http_slo_probe`、App Health runtime closure 证据、全局 testing closure 状态；不改变业务 API、read model、dashboard 权限或 Nginx 配置。
- 关键决策：生产 Nginx 已启用 gzip，浏览器首屏会请求压缩响应；SLO 工具应默认发送 `Accept-Encoding: gzip`，解压后提取 JSON metadata 和 HTML fallback，但 `response_bytes` 记录压缩传输字节。此前未压缩口径下的大 JSON p95 超时不能直接等同浏览器慢。
- 发布证据：hotfix commit `3546e985 Make HTTP SLO probe gzip-aware` 已通过 release `codex-http-slo-gzip-probe-3546e985-20260619210708` 激活；API、RabbitMQ dispatcher、RabbitMQ broker 和 20 个 worker 均 active；生产 release import 断言 `_auth_headers().Accept-Encoding=gzip`。
- 生产复验证据：使用生产目标 OA 凭据在远端内存中临时登录为 full-access user bearer，不输出 token、不落盘、不执行写接口。关键 probe `session_me`、`workbench_groups_all_paired`、`cost_statistics_explorer_all`、`turnover_ledger_grouped`、`etc_reconciliation_tasks` 运行 1 warmup + 2 measured，`status=pass`、`failure_count=0`、`probe_count=5`、`sample_count=10`、`max_p95_ms=190.321`；随后排除 admin-only dashboard 后完整 user-scope authenticated HTTP matrix 运行 37 个 API probes、111 个 measured samples，`status=pass`、`failure_count=0`、`max_p95_ms=735.265`；authenticated SSE 2/2 pass，`max_first_event_ms=343.0`。
- 测试覆盖：`tests.test_http_slo_probe.HttpSloProbeTests.test_collects_samples_with_api_prefix_without_leaking_auth` 锁定默认 gzip header；`test_gzip_json_response_is_decoded_for_metadata` 锁定 gzip JSON 解压、metadata 提取和压缩传输字节记录；既有 admin-scope 测试继续保护 dashboard 凭证分流。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe tests.test_runtime_sync_closure_gate tests.test_slo_tool_defaults -v`；`python3 -m py_compile backend/src/fin_ops_platform/tools/http_slo_probe.py tests/test_http_slo_probe.py`；生产只读 `finops-deploy-control status` / systemd active 检查和关键 authenticated HTTP probe。
- 未测风险：本轮没有 admin token/cookie 证明 `/api/operations/app-health-dashboard` 200，也没有执行业务写操作 apply；full closure 仍依赖 admin 登录态、审批 ticket、安全 scenario 和生产 Browser smoke。

## 2026-06-19 - 生产只读 runtime gate 复查

- 目标：在不执行写操作、不重启服务、不触发 read model apply 的前提下，复查当前生产 release 的 runtime/read model/worker 外部证据，推进 Spec-first E2E 总目标中的真实基础设施闭环。
- 影响范围：系统状态实施记录和全局 testing closure 状态；不改变产品代码、不改变 dashboard 权限、不执行业务写操作。
- 生产证据：公网 `/fin-ops-api/health/ready` 通过，`elapsed_ms=144.671`、`runtime_blocker_count=0`、release 为 `main-8b5942e4-http-slo-admin-scope-202606191805` 且 `runtime_release.consistent=true`。SSH 只读检查显示 `fin-ops.service`、RabbitMQ dispatcher 和 20 个 `fin-ops-worker@*.service` 均 `active/running`，三类 systemd WorkingDirectory 均指向同一 release。加载 systemd env 后，`read_model_slo_smoke --critical-only` dry-run 规划 15 个 critical scopes；生产 PostgreSQL 权威表只读汇总显示 `job.outbox_events=[["done", 157060]]`、`job.read_model_dirty_scopes=[["done", 143020]]`、`read_model.app_status_readiness=[["fresh", 169]]`。公网 `runtime_sync_closure_gate` 的 `runtime_health` 和 `health_ready_payload` checks 通过。
- 关键决策：本轮只读取证据，不把 dry-run 当作 enqueue-to-fresh 证明，不把缺认证的 HTTP/SSE 401 或本机 backend port 上的页面 shell 404 当作业务失败，也不绕过 write-operation 审批闸门。
- 文档影响：更新本实施记录和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：本轮是生产只读取证，不新增代码测试；既有 `health_ready_payload_probe`、`read_model_slo_smoke` 和 `runtime_sync_closure_gate` 测试继续覆盖工具合同。
- 验证命令：公网 `health_ready_payload_probe --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --target-ms 1000 --json`；SSH 只读 `systemctl list-units 'fin-ops*'`、`systemctl show ... WorkingDirectory`；生产本机加载 systemd env 后使用 `/opt/fin-ops/venv/bin/python` 执行 `read_model_slo_smoke --critical-only --target-ms 5000 --json`；生产 PostgreSQL 只读汇总 `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.app_status_readiness`；公网 `runtime_sync_closure_gate --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --allow-unauthenticated-http --health-ready-target-ms 1000 --json`。
- 未测风险：没有运行 `read_model_slo_smoke --apply`，因此本轮不证明新的 direct enqueue-to-fresh worker drain；没有配置 bearer/admin token，所以 authenticated HTTP/SSE gate 仍未闭合；没有 write scenario、approval ticket 和真实认证，所以 write-operation E2E 仍未闭合；write-operation audit 仍显示缺少近期高影响真实写入 profile 样本。

## 2026-06-19 - 当前 release read model apply gate 复验

- 目标：在只读 runtime gate 通过后，补齐当前生产 release 的 direct read model enqueue-to-fresh 证据。
- 影响范围：App Health closure ledger、read-models 和 runtime-workers 运行证据；不执行业务写接口，不改变 dashboard 权限。
- 生产证据：`runtime_sync_closure_gate --apply-read-model-smoke` 首轮证明 `runtime_health` 和 `health_ready_payload` 通过，但 `invoice_lifecycle:2026-04` 与 `cost_statistics:active:2026-04` 超过 5 秒目标；两项聚焦复验 2/2 pass；最终完整 `read_model_slo_smoke --apply --critical-only --target-ms 5000 --timeout-seconds 120` 15/15 pass，summary p50 约 580.34ms，p95/max 约 3863.253ms。复验后 PostgreSQL 汇总为 `job.outbox_events=[["done", 157126]]`、`job.read_model_dirty_scopes=[["done", 143083]]`、`read_model.app_status_readiness=[["fresh", 169]]`。
- 关键决策：direct read model apply 已能证明当前 release 的 worker drain/readiness 收敛；full closure gate 仍不能标记 complete，因为 authenticated HTTP/SSE 和真实 write-operation E2E 仍缺 token、approval ticket 和安全 scenario。
- 文档影响：同步 `docs/dev/testing-closure-state.md`、`docs/modules/read-models/e2e-coverage.md`、`docs/modules/read-models/implementation-notes.md` 和 `docs/modules/runtime-workers/e2e-coverage.md`。
- 测试覆盖：本轮运行生产 gate，没有新增代码测试；既有 closure/read-model gate 单测继续保护工具合同。
- 未测风险：admin dashboard authenticated gate、SSE authenticated gate 和 mutating write-operation E2E 仍未闭合。

## 2026-06-19 - 当前 release authenticated user HTTP/SSE gate 复验

- 目标：在 direct read model apply 通过后，继续推进 authenticated runtime gate，区分 user-level 认证/SSE、admin-only dashboard 和 HTTP 性能慢项。
- 影响范围：App Health closure ledger、`http_slo_probe` / `sse_smoke_probe` 生产证据和全局 testing closure 状态；不执行业务写接口，不输出 token。
- 生产证据：生产有 2 个 configured target OA credentials；使用目标 OA 申请人凭据临时登录得到的 bearer token 调用 `/api/session/me`，两者均返回 `200`、`access_tier=full_access`、`can_access_app=true`、`can_mutate_data=true`、`can_admin_access=false`。因此 user-level 认证可用，但没有 admin session。
- User-level HTTP 结果：排除 admin-only dashboard 后，37 个 API probes、111 个 measured samples 中失败 5 项，均为 `200` 或 `200 fresh` 的耗时超标；focused rerun 后 `bank_details_auto_tag_rules` 通过，剩余 4 项仍超 1 秒：`workbench_groups_all_paired` p95 约 2680.029ms、`cost_statistics_explorer_all` p95 约 1160.09ms、`turnover_ledger_grouped` p95 约 1181.292ms、`etc_reconciliation_tasks` p95 约 1396.46ms。
- SSE 结果：`/api/app-health/stream` 与 `/api/workbench/events?month=all` 2/2 pass，first event 分别约 350.665ms 和 217.741ms。
- 关键决策：user-level authenticated session 和 SSE gate 已闭合；HTTP gate 仍为 performance partial，不应被标记 complete。admin-only dashboard 仍需要真实 admin token/cookie，不能用 full_access 非 admin token 代替。
- 文档影响：更新本实施记录和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：本轮运行生产 probes，没有新增代码测试；既有 `tests/test_http_slo_probe.py`、`tests/test_sse_smoke_probe.py` 和 `tests/test_runtime_sync_closure_gate.py` 继续保护工具合同。
- 未测风险：4 个 user-level HTTP 慢项尚未优化或重新定标；admin dashboard 和 mutating write-operation E2E 仍未闭合。

## 2026-06-19 - HTTP SLO admin-only probe 凭证分流

- 目标：让最终 authenticated HTTP gate 能同时使用普通 OA bearer token 和 admin token 验证所有默认 API probes，避免 admin-only dashboard 只能全局使用普通 token 导致稳定 403。
- 影响范围：`http_slo_probe`、`runtime_sync_closure_gate`、系统状态测试矩阵和全局 testing closure 状态；不改变 dashboard 权限、不改变业务 API。
- 关键决策：`HttpProbe` 新增 `auth_scope`，默认 `user`；`operations_app_health_dashboard` 标记为 `admin`。`collect_http_slo(...)` 支持 `admin_headers`，admin-scoped probe 使用 admin headers，普通 probe 使用 user headers。CLI 同时提供 `FIN_OPS_HTTP_SLO_BEARER_TOKEN` 和 `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` 时会分流；只有 admin token 时保留兼容，允许用 admin token 跑全部 probes；没有 admin token 时 admin-only probe 继续失败，不能把 403 当性能通过。
- 文档影响：更新本模块 `tests.md`、本实施记录和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `tests.test_http_slo_probe.HttpSloProbeTests.test_admin_scoped_probe_uses_admin_headers_without_overriding_user_probes`，并更新默认 probe 测试断言 dashboard auth scope；新增 `tests.test_runtime_sync_closure_gate.RuntimeSyncClosureGateTests.test_gate_passes_admin_headers_to_http_slo_probe`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe tests.test_runtime_sync_closure_gate tests.test_slo_tool_defaults -v`；`python3 -m py_compile backend/src/fin_ops_platform/tools/http_slo_probe.py backend/src/fin_ops_platform/tools/runtime_sync_closure_gate.py tests/test_http_slo_probe.py tests/test_runtime_sync_closure_gate.py`。
- 未测风险：生产仍缺真实 `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` 或 admin cookie，因此还不能完成 admin-only dashboard authenticated gate；本轮只证明工具能正确分流凭证。

## 2026-06-19 - 生产 authenticated API SLO 复跑只剩 admin 凭证缺口

- 目标：复核 output invoice all-scope hotfix 后的生产 authenticated API-only SLO 当前状态，区分真实性能/read-model 问题和 admin-only 凭证缺口。
- 影响范围：app-health-operations runtime gate 事实记录、`http_slo_probe` 生产使用方式和全局 testing closure ledger；本轮不改变业务代码、不改变 dashboard 权限。
- 关键决策：使用现有目标 OA 申请人凭据临时登录，只在内存中作为 Bearer token 调用只读 GET，不输出 token、不落盘、不执行业务写操作。非 admin 登录态访问 `/api/operations/app-health-dashboard` 返回 403 是权限合同，不应通过放宽 dashboard 权限或把 admin-only endpoint 混入普通用户性能通过条件来修复。
- 生产证据：Workbench 单项 `/api/workbench/groups?month=all&zone=paired&page=1&page_size=50` 使用正式 `http_slo_probe.collect_http_slo` 运行 1 次 warmup + 8 次 measured，全部 `200 fresh`，p95 `274.362ms`。全量 API-only authenticated probe 运行默认 38 个 API、1 次 warmup + 3 次 measured，总 114 个 measured samples，`max_p95_ms=710.177`，无 `>800ms` 慢项；Workbench、成本统计和 ETC 均已通过 1000ms 目标。
- Read model / worker 证据：生产只读巡检显示当前 release 为 `main-9e9546ac-output-invoice-all-scope-20260619173552`，API、RabbitMQ dispatcher 和 20 个 worker service 共 22 个 fin-ops systemd service running；`job.read_model_dirty_scopes` 非 done 为空，`job.outbox_events` 非 done 为空，recent failed/dead-letter/publish-failed outbox 为空；App Status readiness 中所有登记 read model key 均只有 `fresh`。heartbeat 表仍保留历史旧 worker id 的 stale/stopped 行，但 `/health/ready` 返回 `status=pass`、`elapsed_ms=82.849`、`runtime_blocker_count=0`、`runtime_release.consistent=true`，因此这些历史 heartbeat 行当前不构成 runtime blocker。
- 当前剩余 gate：唯一失败是 admin-only `/api/operations/app-health-dashboard` 三次 `403`。生产环境存在 `FIN_OPS_ADMIN_USERNAMES`，但没有 `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` 或 cookie；现有 2 个目标 OA 凭据均为 `access_tier=full_access`、`can_mutate_data=true`、`can_admin_access=false`。
- 文档影响：更新 `docs/dev/testing-closure-state.md` 和本实施记录。
- 测试覆盖：本轮是生产只读取证，不新增代码测试；既有 `tests/test_http_slo_probe.py` 和 app-health API/权限测试继续覆盖 probe contract 和 admin-only dashboard contract。
- 验证命令：生产只读 `http_slo_probe.collect_http_slo` Workbench 单项和全量 API-only authenticated probe；本地 `bash scripts/verify.sh docs`、`git diff --check -- docs/dev/testing-closure-state.md`。
- 未测风险：admin-only dashboard 仍需要真实 admin token/cookie 或目标 OA admin 凭据；真实业务 write-operation apply 仍需要审批 ticket。

## 2026-06-19 - Write-operation E2E apply 审批闸门

- 目标：防止最终 runtime closure 或直接 `write_operation_e2e_smoke --apply` 在只有 auth/scenario 的情况下误触生产 mutating HTTP，把“人工/业务已批准”变成机器可验证的显式输入。
- 影响范围：`write_operation_e2e_smoke`、`runtime_sync_closure_gate`、`p2p3_gate_result_classifier`、系统状态测试矩阵和长期监控 runbook；不改变业务写接口、operation profile、read model/worker SLO 判断或 scenario schema。
- 关键决策：直接 write E2E `--apply` 必须提供 `--approval-ticket` 或 `FIN_OPS_WRITE_E2E_APPROVAL_TICKET`；缺失时返回 `status=approval_missing`、`error=write_operation_e2e_requires_approval_ticket`，且在连接 Postgres 或发起 mutating HTTP 前停止。最终 closure gate 的 required args 扩展为 `--write-scenario`、`--apply-write-scenarios`、`--write-approval-ticket`；缺 approval 时 `write_operation_e2e` check 失败并且不调用 write E2E 执行器。
- 文档影响：更新本模块 `tests.md`、`docs/operations/monitoring.md`、read-models 实施记录和全局 testing closure 状态。
- 测试覆盖：新增/更新 `tests.test_write_operation_e2e_smoke.WriteOperationE2ESmokeTests.test_cli_apply_requires_approval_before_postgres_configuration`、`test_apply_requires_approval_before_mutating_requests`、`tests.test_runtime_sync_closure_gate.RuntimeSyncClosureGateTests.test_write_scenario_apply_requires_approval_ticket_before_write_e2e_runs`、`tests.test_p2p3_gate_result_classifier.P2P3GateResultClassifierTests.test_classifies_nested_write_approval_missing_as_approval_required`；既有 apply 正路径测试传入测试 approval。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_e2e_smoke tests.test_runtime_sync_closure_gate tests.test_p2p3_gate_result_classifier -v`；`python3 -m py_compile backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py backend/src/fin_ops_platform/tools/runtime_sync_closure_gate.py backend/src/fin_ops_platform/tools/p2p3_gate_result_classifier.py tests/test_write_operation_e2e_smoke.py tests/test_runtime_sync_closure_gate.py tests/test_p2p3_gate_result_classifier.py`；生产 release `main-33a150e7-write-e2e-approval-gate-20260619151922` 激活后 `/health/ready` 为 ready，缺 approval 的 minimal turnover `--apply` smoke 返回 `approval_missing` / exit code 2；发布后 critical read-model apply 15/15 pass，p95/max 约 4960.071ms，outbox/dirty/readiness 汇总为 done/done/fresh。
- 未测风险：审批闸门已在生产阻止缺 approval 的 apply；真实 write-operation closure 仍需要业务批准、真实认证和生产 apply smoke 样本。

## 2026-06-19 - 系统状态页面级 Spec-first E2E covered

- 目标：把 `app-health-operations` 从首轮 `documented-risk` 校准为页面级 `spec-first-covered`，明确 Browser 合同、覆盖映射和真实基础设施风险边界。
- 影响范围：`web/e2e/app-shell.spec.ts`、`docs/modules/app-health-operations/e2e-spec.md`、`docs/modules/app-health-operations/e2e-coverage.md`、系统状态测试矩阵和全局 Spec-first E2E inventory。
- 关键决策：
  - 不改产品逻辑；现有 service/API/component/Browser 测试已经覆盖系统状态页面主要业务合同。
  - 给 App Health Browser smoke 补严格浏览器错误捕获，确保 admin dashboard、read-export admin-only gate、forbidden 和 expired session gate 期间隐藏 `pageerror`、`console.error`、非 abort request failure 或未预期 dialog 会失败。
  - 真实 PostgreSQL/RabbitMQ/Redis/systemd/Nginx/OA iframe、大库 metrics、authenticated HTTP/SSE 和 controlled write-operation E2E 不用本地 deterministic E2E 伪装覆盖，继续登记为 staging/runtime smoke external-risk。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 `README.md`、`tests.md`、本文件和全局 testing closure 文档。
- 测试覆盖：更新 `web/e2e/app-shell.spec.ts`。
- 验证命令：`cd web && npx playwright test e2e/app-shell.spec.ts --project=chromium`；`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker heartbeat、queue backlog、Nginx/OA iframe SSE、真实大库 dashboard metrics、`pg_stat_statements`、authenticated HTTP/SSE/write-operation SLO。

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
- 关键决策：缺少 `--write-scenario` 时保持 gate `fail`，payload 输出 `status=input_required`、`missing_args=["--write-scenario"]` 和完整 `required_args`；提供 scenario 但未显式 `--apply-write-scenarios` 时保留 dry-run report，并附加缺失 apply 参数；显式 apply 但缺少 `--write-approval-ticket` 时返回 `approval_missing`，且不调用 write E2E 执行器；scenario 文件存在但为空、JSON 非法或 contract 非法时，`write_operation_audit` 和 `write_operation_e2e` 都返回 `input_error`，且不会退回运行 unscoped write audit。最终闭环仍必须真实 apply 受控写 E2E。
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

## 2026-06-19 - admin-scoped HTTP SLO probe 发布验证

- 目标：修复生产 authenticated HTTP SLO 中 admin-only `/api/operations/app-health-dashboard` 被普通目标 OA bearer 固定采样为 403 的 gate 设计缺口。
- 影响范围：`http_slo_probe`、`runtime_sync_closure_gate`、App Health admin dashboard SLO gate 和测试闭环状态；不改变 App Health 业务权限、页面路由或 dashboard API 行为。
- 关键决策：不放宽 dashboard 权限，也不把 403 当性能通过；普通 API probe 继续使用 user bearer/cookie，admin-only dashboard probe 只在提供 `FIN_OPS_HTTP_SLO_ADMIN_TOKEN`、`--admin-token` 或 admin cookie 时使用 admin headers。
- 发布：hotfix commit `8b5942e4 Support admin-scoped HTTP SLO probes` 已通过 release `main-8b5942e4-http-slo-admin-scope-202606191805` 激活到生产。
- 发布后验证：发布脚本完成 backend readiness、worker ensure、frontend hash 和 public session route checks；生产只读检查显示 API/dispatcher active、20 个 worker running、`/health/ready` ready，`job.outbox_events` 非 done、`job.read_model_dirty_scopes` 非 done、`read_model.app_status_readiness` 非 fresh 和近 30 分钟 failed/dead-letter/publish-failed outbox 均为空；生产 release `py_compile` 通过，import 断言 `operations_app_health_dashboard_auth_scope=admin`。
- 测试覆盖：`tests.test_http_slo_probe.HttpSloProbeTests.test_admin_scoped_probe_uses_admin_headers_without_overriding_user_probes`、`tests.test_runtime_sync_closure_gate.RuntimeSyncClosureGateTests.test_gate_passes_admin_headers_to_http_slo_probe`，并复跑 `tests.test_slo_tool_defaults`。
- 未测风险：生产仍缺真实 admin token/cookie 或目标 OA admin 凭据，因此 full authenticated HTTP gate 不能最终闭合；真实 write-operation apply 仍需审批 ticket。

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
