# 成本统计测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

成本统计是跨银行流水、发票、OA、Workbench relation、项目归因和费用分类的派生 read model。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 业务归因 | `CostStatisticsService`、project costing service、workbench relation/detail payload | 项目、费用类型、费用内容、金额方向、OA 字段、银行字段和 relation distribution 不能由页面重算。 |
| 项目范围 | app settings project status、`project_scope` | `active` 默认，只排除已完成项目；`all` 包含全部；未知项目保持 active；非法 scope 拒绝。 |
| read model scope contract | `ReadModelRefreshGateway`、scope policy registry | 合法 scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all`；裸月份/裸 all 只能在 gateway 归一化。 |
| 月份 shard | `read_model.cost_statistics_rows`、`cost_statistics.read_model.refresh` | 月份 shard 从对应 Workbench 月份 read model 构建；成功后重新入队同 project scope 父 scope。 |
| 全期间父 scope | `read_model.cost_statistics_read_models` | 父 scope 是一等 read model；从已物化月份 rows 聚合，不读 Workbench `all` 全量 payload。 |
| App Status readiness | `read_model.app_status_readiness`、`job.read_model_dirty_scopes`、`job.outbox_events` | 父 scope failed/unavailable 才阻断成本统计主体验；月份 shard failed/unavailable 是局部 busy。 |
| API/read cache | `/api/cost-statistics*`、Redis hot cache、SQL read model | fresh gate 后才能缓存；miss/stale 返回 refreshing 并入队，不同步重建伪 fresh。 |
| 导出 | cost statistics export/export-preview | time/project/expense type/bank view、date range、project scope、advanced export filters 和 filename contract。 |
| 前端交互 | `CostStatisticsPage`、`web/src/features/cost-statistics/api.ts` | all/year/month/custom range、view switch、drilldown、modal、loading/error/empty/refreshing、export center。 |
| 跨模块 fan-out | imports、ETC、pending invoice rules、workbench relation、turnover、project scope settings | 写入后必须通过 lifecycle/dirty scope/outbox 影响成本统计，不能只靠前端事件。 |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 成本统计核心归因 | P0 | `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py` | covered | 支出行、OA cost 字段、relation distribution、现金/票据/往来特殊场景、项目范围；Workbench open/proposed candidate 不计入成本。 |
| API shape、route facade、project scope | P0 | `tests/test_cost_statistics_api.py` | covered | month/explorer/project scope、invalid scope、cache hit/miss、导入 invalidation。 |
| 导出和 export preview | P1 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_service.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | covered | XLSX、filename、date range、project/expense filters、project scope 透传；Browser 覆盖 `read_export_only` 成功 download event、请求不带分页、下载内容字段；超过 20,000 行同步导出上限时结构化返回 `cost_statistics_export_row_limit_exceeded` 并在真实浏览器导出中心展示。 |
| read model service scope | P0 | `tests/test_cost_statistics_read_model_service.py` | covered | scope validation、schema mismatch discard、deep copy、invalidate months/all。 |
| scope gateway/legacy cleanup | P0 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered | legacy scope normalize、非法 scope reject、production checker dry-run/apply/replacement dedupe。 |
| SQL runtime fresh/miss/stale | P0 | `tests/test_cost_statistics_sql_runtime.py` | covered | SQL read model read、Redis cache、API miss enqueue、malformed explorer payload requeue、production requires SQL model。 |
| parent scope aggregation | P0 | `tests/test_cost_statistics_sql_runtime.py` | covered | `active:all` / `all:all` 从 materialized shard rows 聚合，不读 Workbench all payload。 |
| parent waits for shard readiness | P0 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_app_status_overview_service.py` | covered | missing/stale shards 入队，父 scope refreshing；shards converged 后发布 parent fresh。 |
| App Status scope-level semantics | P0 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py` | covered | 父 scope failed blocks；月份 shard failed/unavailable busy；scope details preserved。 |
| 首屏 SLO 探针与有界聚合 | P2 | `tests/test_http_slo_probe.py`、`tests/test_cost_statistics_sql_runtime.py` | covered | 成本统计没有 rows 分页首屏；认证态 SLO 覆盖 page shell、explorer 和 summary，父 scope 从已物化月份 shard 聚合，不读 Workbench 全量 payload。 |
| warmup job recovery/retry | P1 | `tests/test_cost_statistics_api.py`、`tests/test_import_job_queue.py` | covered | warmup summary、partial retry、interrupted recovery、duplicate running job guard。 |
| 前端页面交互 | P1 | `web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | covered | time/project/bank/expense view、drilldown、range picker、empty/error/refreshing/stale/failed、export center、后端导出失败消息展示、OA 登录态缺失错误展示、同一流水拆成多条成本行时项目费用类型下钻不丢行/不触发表格重复 key；真实 Chromium 覆盖 explorer 暂时 503 错误态、普通空态/表格/导出防伪成功、点击刷新后恢复 fresh 成本行，按时间首屏、按项目下钻、按银行选择银行账户/项目/流水详情、按费用类型选择费用类型/流水详情、导出中心成功下载/错误反馈、read model 非 fresh 不显示最终空态/旧项目行/0 条 summary 且禁用导出、fresh explorer 下 detail/export non-fresh 不伪成功和不下载、120+ 成本行在 390px 窄屏下按时间表/项目下钻表纵横滚动、右侧列 viewport 可见、导出入口和选择器无遮挡且无浏览器错误、Workbench 成本关系 candidate 不计入/confirmed 后计入成本、ETC 导入 confirm 后成本统计 fresh read model 与 ETC 成本行展示、no-OA 手续费批次 submit 后成本统计 fresh read model 与免 OA 成本行展示、外部往来 manual closure confirm 后成本统计 fresh read model 与闭环成本行展示，以及 settings 项目标记完成后 active/all project scope 刷新。 |
| Workbench 成本关系 fan-out | P0 | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_service.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_workbench_relation_repository.py` | covered | Browser 已证明 open candidate 不进入成本项目/金额/明细，关联台确认 OA+bank+invoice 成本关系后成本页重新读取并展示 `智能工厂项目`、`58,000.00` 和对应流水详情。 |
| 前端 API mapper/cache | P1 | `web/src/test/CostStatisticsApi.test.ts` | covered | project scope 透传、read model status mapping、explorer cache keyed by month/scope、export 下载错误 JSON message 透出。 |
| 真实生产 scope cleanup `--apply` | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres 环境，只能按 runbook 只读检查后受控执行。 |

## 七类测试适用性

2026-06-24 modular IO 更新：`read-models:next-pilot-selection-after-tax-offset` 已选择 `cost_statistics` 作为第九个非 Go read model 试点。`read-models:cost-statistics-repository-port-extraction` 已新增 `CostStatisticsReadModelRepositoryPort`，证明 cost statistics port 只暴露 `load_cost_statistics_read_models`、`get_cost_statistics_view`、`save_cost_statistics_read_models`，并让 projection save 与 SQL read wiring 使用该 port。`read-models:cost-statistics-refresh-freshness-operation-barrier-audit` 已确认 SQL fresh gate、parent aggregate、force refresh、App Status registry、primary `cost-statistics` worker 和 `cost-tax` compat lane 有本地证据。`read-models:cost-statistics-derived-lifecycle-executor-port-extraction` 已新增 `CostStatisticsDerivedLifecycleExecutor`，移除 `Application._derived_lifecycle_cost_statistics_executor(...)`，并用 `tests/test_cost_statistics_derived_lifecycle_executor.py` 与 platform guard 锁定 lifecycle invalidation/warmup-vs-refresh fallback、metadata 和 `enqueued_jobs` accounting。`read-models:cost-statistics-post-derived-local-implementation-closure-audit` 已确认 warmup/retry/rebuild app 方法均为 runtime delegate。`read-models:cost-statistics-full-state-read-model-snapshot-quarantine` 已移除 broad `_persist_state(...)` 对 `cost_statistics_read_models` 的写入，并扩展 `tests/test_read_model_architecture_guards.py` 防止 cost/tax read model broad full-state snapshot 写入回归。下一边界是 `read-models:cost-statistics-post-full-state-local-implementation-closure-audit`。

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py` | 覆盖成本归因、项目范围、特殊业务链路、票据/往来排除或保留规则。 |
| 2. Service-layer tests | 适用 | `tests/test_cost_statistics_read_model_service.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_project_costing_api.py` | 覆盖 read model service、runtime service、project costing 写入/查询边界。 |
| 3. API contract tests | 适用 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`tests/test_http_slo_probe.py`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖 explorer、month summary、project scope、export/export-preview、默认 SLO 探针、错误和 response shape；e2e 断言 `project_scope=all`、transaction detail、export-preview、export request/response、download filename/content、Workbench confirm 后成本 explorer/detail 重新读取、ETC import confirm 后成本 explorer 返回 `read_model_status=fresh`，no-OA submit 后成本 explorer 返回 fresh，turnover manual closure confirm 后成本 explorer 返回 fresh，以及 settings 保存项目状态后 active/all explorer 均返回 fresh。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_app_status_overview_service.py` | 覆盖 SQL read model、Redis hot cache、payload contract invalid fail-closed、scope contract、worker refresh、parent/shard readiness、父 scope 有界聚合和 App Status。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/CostStatisticsApi.test.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖页面状态、范围选择、drilldown、export center、后端失败消息展示、OA 登录态缺失错误展示、API mapper 和 cache；e2e 保护真实 Chromium tab、explorer 暂时 503 错误态/导出禁用/刷新恢复、time/project/bank/expense baseline、project scope、三段下钻、modal、preview、导出成功/错误反馈、read model 非 fresh 防 false-empty/旧数据、fresh explorer 下 detail/export non-fresh 不伪成功和不下载、120+ 大数据窄屏宽表纵横滚动和控件无遮盖、relation fan-out 后的项目/金额/详情展示、ETC 导入下游成本行展示、no-OA submit 后下游成本行展示、turnover manual closure 后下游成本行展示，以及 settings project scope 保存后的 active/all 可见性。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖导入确认/Workbench invalidation/read model enqueue 到成本统计；Playwright 覆盖 explorer -> project scope -> drilldown -> export preview/download/error、Workbench confirm -> 成本页重新读取 -> 成本项目/流水详情出现、ETC import confirm -> 税金抵扣/成本统计 fresh read model -> ETC 成本项目和流水展示、no-OA submit -> operation barrier -> 成本统计 fresh read model -> 免 OA 手续费成本项目/流水展示、turnover manual closure confirm -> operation barrier -> 成本统计 fresh read model -> 外部往来闭环成本项目/流水展示 -> 回周转页撤回，以及 settings project completed save -> 成本统计 active 排除/all 保留；真实导入/周转/settings 到 worker drain 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 cost statistics tests，加 imports、invoice lifecycle、workbench、turnover、settings/project scope tests 的按改动选择扩展集 | 成本统计受多模块写入影响；任何导入、关系、规则、项目范围或 worker 改动都要问会影响哪些旧成本视图；e2e 防止真实浏览器中 project scope、detail modal、export center 和 candidate/linked relation 成本语义断链。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-18 | 成本统计 explorer 返回 `401 invalid_oa_session` 时，页面吞掉后端业务消息并显示泛化“成本统计数据加载失败”，导致用户误判为成本统计/read model 故障。 | `web/src/test/CostStatisticsPage.test.tsx::surfaces OA session errors from explorer loading` | covered |
| 2026-06-18 | App Health 显示成本统计已同步，但 explorer SQL/Redis payload 仍是旧 shape，缺少当前页面需要的 `summary`、`time_rows`、`project_rows`、`expense_type_rows`，导致前端 mapper 抛错并显示泛化加载失败。 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_api_rejects_malformed_fresh_sql_payload_and_requeues`、`tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_invalid_fresh_cache_payload_contract_misses_and_uses_sql_view`、`test_invalid_sql_payload_contract_enqueues_refresh_without_populating_cache` | covered |
| 2026-06-17 | 成本统计项目视图选中项目后再选择费用类型，若同一 `transaction_id` 对应多条成本行，前端用裸流水 id 作为 HeroUI Table 行 id/key，导致行身份冲突、丢行，真实浏览器可表现为卡死后白屏。 | `web/src/test/CostStatisticsPage.test.tsx::project view keeps split cost rows with the same transaction id renderable` | covered |
| 2026-06-18 | 关联台 open/proposed candidate 被误显示为成本项目或金额，或 OA+bank+invoice 成本关系确认后成本页没有重新读取并展示对应项目/流水。 | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_open_candidate_groups_are_excluded_from_cost_statistics`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` | covered |
| 2026-06-19 | 成本统计 explorer 返回 `refreshing` / `stale` / `failed` 的空 payload 时，页面可能误显示最终空态、旧项目行、0 条 summary 或允许导出非 fresh 数据。 | `web/e2e/cost-statistics-flow.spec.ts::does not treat * read model payloads as final empty cost data`、`web/src/test/CostStatisticsPage.test.tsx::hides read model refresh details without treating empty accepted payload as final empty data` | covered |
| 2026-06-20 | 成本统计 explorer 首屏暂时 503 时，页面可能直接显示正常空态或允许导出中心打开，用户没有显式刷新路径；背景 all-scope 参考数据请求也可能干扰失败恢复测试。 | `web/e2e/cost-statistics-flow.spec.ts::recovers explorer after a transient load failure when refreshed`、`web/src/test/CostStatisticsPage.test.tsx::refreshes explorer data after a transient loading failure` | covered locally; real network/worker drain pending |
| 2026-06-19 | 成本统计 explorer fresh 但流水详情或导出接口返回 non-fresh 时，页面可能打开旧详情、保留旧预览或生成下载文件。 | `web/e2e/cost-statistics-flow.spec.ts::does not treat non-fresh transaction detail or export responses as successful results` | covered locally; real worker drain pending |
| 2026-06-19 | 成本统计导出中心只覆盖 row-limit 错误，缺少真实浏览器 download event、文件名、请求不带分页和导出字段保护。 | `web/e2e/cost-statistics-flow.spec.ts::downloads the current time-view cost rows with request filters and cost fields` | covered locally; real workbook open pending |
| 2026-06-19 | 成本统计在大数据/长字段/390px 窄屏下可能出现表格无法横向滚动、右侧列不可见、项目/费用类型选择器或导出入口被遮挡，或 fresh read model 行数足够但浏览器层面不可用。 | `web/e2e/cost-statistics-flow.spec.ts::keeps large cost tables fresh, scrollable, and usable on narrow screens` | covered locally; real production volume/performance pending |
| 2026-06-10 | 裸月份/裸 `all` scope 进入 durable queue，导致成本统计 worker 报 scope contract 错误并污染 App Status。 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered |
| 2026-06-16 | 外部往来 Postgres 事务写路径绕过 scope policy，再次向成本统计投递裸 `2026-02`、`2026-03`、`all` 并造成生产 dead-letter。 | `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction`、`tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear` | covered locally; production cleanup apply pending |
| 2026-06-16 | 把成本统计误当普通分页列表处理，遗漏 explorer/summary 认证态 SLO 或让父 scope 回退读取 Workbench 全量 payload。 | `tests/test_http_slo_probe.py::HttpSloProbeTests::test_default_probes_cover_page_domains_and_known_slow_endpoints`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows` | covered |
| 2026-06-10 | `active:all` / `all:all` 父 scope 错误读取 Workbench `all` 大 payload。 | `tests/test_cost_statistics_sql_runtime.py` | covered |
| 2026-06-10 | 父 scope 等待缺失/stale 月份 shard 时被伪造为 fresh。 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_app_status_overview_service.py` | covered |
| 2026-06-12 | Workbench open/proposed candidate 被当成 confirmed relation 计入成本金额。 | `tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_open_candidate_groups_are_excluded_from_cost_statistics`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` | covered |
| 2026-06-13 | 成本税务 projection 直接从 OA 附件 parser cache 拼进项发票输入，绕过统一 Invoice repository。 | `tests/test_tax_offset_service.py::test_month_payload_includes_oa_attachment_invoices_by_issue_month`、`tests/test_tax_offset_api.py::test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata` | covered by shared tax/workbench boundary |
| 长期 | 月份 shard failed 误把整个成本统计主体验标红。 | `tests/test_app_status_overview_service.py` | covered |
| 长期 | SQL read model miss/stale 时 API 同步 rebuild 或返回假 fresh。 | `tests/test_cost_statistics_sql_runtime.py` | covered |
| 长期 | 导出和页面查询没有透传 project scope 或自定义日期范围。 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` | covered |
| 2026-06-16 | 成本统计 time/project/expense_type export-preview/export 对大匹配集同步生成预览 rows 或 XLSX，拖慢 API 线程和内存。 | `tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_export_preview_and_download_reject_large_time_export_before_workbook_generation`、`tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_cost_statistics_export_limit_returns_structured_error` | covered |
| 2026-06-16 | 成本统计下载接口收到 `cost_statistics_export_row_limit_exceeded` 等结构化错误时，前端下载路径不解析 JSON 或页面丢弃错误消息，用户只能看到泛化失败。 | `web/src/test/CostStatisticsApi.test.ts::surfaces backend row-limit messages from failed export downloads`、`web/src/test/CostStatisticsPage.test.tsx::shows backend export failure messages inside the export center` | covered |
| 2026-06-17 | 成本统计导出中心在真实浏览器中 preview/export 请求未携带当前项目范围或行数上限错误未展示。 | `web/e2e/cost-statistics-flow.spec.ts` | covered |
| 长期 | 成本统计错误纳入现金代收代付/票据购买/发票抵扣等特殊关系。 | `tests/test_cost_statistics_service.py` | covered |

## 关键 smoke flows

1. `银行/发票/ETC 导入确认、no-OA submit 或 turnover manual closure -> lifecycle/domain plan -> cost_statistics dirty scope -> cost-statistics worker -> month shard fresh -> parent scope re-enqueue -> all scope fresh -> 页面展示`；ETC、no-OA 和 turnover 路径已有 Browser 证据断言成本页 fresh explorer 与对应成本行。
2. `Workbench relation confirm/cancel -> cost statistics invalidation -> affected month shard refresh -> App Status busy -> fresh 后恢复 -> 成本页重新读取并只展示 confirmed 成本关系`
3. `project scope setting change -> active/all scope refresh -> active view 排除已完成项目 -> all view 保留全部项目`；`web/e2e/settings-data-reset-flow.spec.ts` 已覆盖 settings 项目标记完成后进入成本统计验证 active/all fresh scope。
4. `active:all 父 scope refresh -> 检查 month shard readiness -> 缺失 shard 入队 -> 父 scope refreshing -> shards fresh 后聚合发布`
5. `页面切换 view/date/project scope -> explorer API -> stale/refreshing/failed 或暂时 503 显示刷新或不可用语义 -> 不显示最终空态或旧项目行 -> 暂时 503 时手动刷新 -> fresh 后 drilldown/export`
6. `真实 Chromium 按时间首屏 -> read_export_only 打开导出中心 -> 导出 preview -> download event -> 文件名/字段/筛选断言 -> 按项目 -> project_scope=all -> 项目/费用类型/流水详情下钻 -> 导出 row-limit 错误反馈`
7. `真实 Chromium 390px 窄屏 -> 120+ 成本行 fresh explorer -> 按时间宽表横向/纵向滚动 -> 右侧列 viewport 可见 -> 按项目选择长项目/费用类型 -> 项目对应流水表横向/纵向滚动 -> 无 console/page/request/dialog 错误`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service tests.test_project_costing_service tests.test_project_costing_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_read_model_service tests.test_cost_statistics_runtime_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v
PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe.HttpSloProbeTests.test_default_probes_cover_page_domains_and_known_slow_endpoints -v
cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx
cd web && npx playwright test e2e/cost-statistics-flow.spec.ts
cd web && npx playwright test e2e/cost-statistics-relation-fanout.spec.ts
cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/no-oa-bank-batches-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium
cd web && npm run e2e:smoke
bash scripts/verify.sh docs
```

扩展回归按改动选择：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_import_job_queue tests.test_derived_data_lifecycle_service tests.test_workbench_v2_api tests.test_turnover_workbench_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_tax_offset_api tests.test_input_invoice_usage_api -v
cd web && npm test -- --run src/test/AppHealth*.test.tsx src/test/WorkbenchSelection.test.tsx src/test/TaxOffsetPage.test.tsx
PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest、deterministic Playwright smoke 和 build，覆盖完整成本统计、App Status、read model gateway、前端测试集、成本统计 browser 主流程和 Workbench 成本关系 fan-out e2e。单轮模块验证只跑最小闭环。

## 未测风险

- 本轮不连接真实生产 PostgreSQL 执行 `scripts/check-read-model-scope-contracts.py --apply`；发布前后需先 dry-run JSON 报告，再按 runbook 受控清理。
- 本地测试不跑真实 RabbitMQ/Redis/cost-statistics worker drain；Workbench 成本关系确认后到 `cost_statistics` worker 的真实 enqueue-to-fresh 收敛、父 scope 与月份 shard 在真实多 worker 环境中的最终收敛，以及真实网络中断后的浏览器重试体验需要生产或 staging smoke。
- 本地已覆盖成本统计超过 20,000 行同步导出 fail-closed、导出中心错误反馈，以及 120+ 行窄屏宽表滚动/控件可用性；真实浏览器文件打开、真实生产超大数据查询/下载耗时和生产视觉性能仍需 staging/manual smoke。
