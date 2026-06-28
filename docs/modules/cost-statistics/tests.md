# 成本统计测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

成本统计是跨银行流水、发票、OA、Workbench relation、项目归因和费用分类的派生页面模块。后端只保留 legacy projection 清理边界；页面通过 direct API 消费 explorer/export payload。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 业务归因 | `CostStatisticsService`、project costing service、workbench relation/detail payload | 项目、费用类型、费用内容、金额方向、OA 字段、银行字段和 relation distribution 不能由页面重算。 |
| 项目范围 | app settings project status、`project_scope` | `active` 默认，只排除已完成项目；`all` 包含全部；未知项目保持 active；非法 scope 拒绝。 |
| historical SQL snapshot tables | `read_model.cost_statistics_*` | 仅作为迁移清理对象；页面 GET 不读取它，不投递旧成本统计刷新事件，旧 cost/tax SQL projection 已删除。 |
| cache warmup | `cost_statistics_cache_warmup` | best-effort 后台优化；不能作为页面可读证明。 |
| API/read path | `/api/cost-statistics*`、`CostStatisticsQueryService` | 页面 GET 直接调用业务 service 组装 payload；不读取 SQL projection / Redis gate，也不返回旧同步字段。 |
| 导出 | cost statistics export/export-preview | time/project/expense type/bank view、date range、project scope、advanced export filters 和 filename contract。 |
| 前端交互 | `CostStatisticsPage`、`web/src/features/cost-statistics/api.ts` | all/year/month/custom range、view switch、drilldown、modal、loading/error/empty、旧同步字段忽略、export center。 |
| 跨模块 fan-out | imports、ETC、pending invoice rules、workbench relation、turnover、project scope settings | 写入后通过 direct refetch / cache warmup 影响成本统计，不能恢复 page projection scope/outbox。 |

## 场景覆盖清单

## 2026-06-28 - 删除旧 cost/tax SQL projection

- 变更类型：legacy projection deletion。
- 背景：成本统计页面和 API 已转 direct API，旧 `cost_tax_sql_projection.py` 与 `tests/test_cost_statistics_sql_runtime.py` 只保护已下线的页面派生 worker/projection。
- 删除测试：`tests/test_cost_statistics_sql_runtime.py`。
- 七类测试决策：service-layer、API contract、cache/background job、existing feature regression 适用；由 `tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_service.py`、platform/runtime guard 和 Browser/Vitest tests 覆盖。Frontend/E2E/business core 不因本删除新增，因为页面 contract 和成本归因未改变。
- 验证结果：本轮用 platform/runtime guard 与 residual scan 证明删除后不存在生产 caller；完整成本统计回归仍按下方 direct API 命令执行。

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 成本统计核心归因 | P0 | `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py` | covered | 支出行、OA cost 字段、relation distribution、现金/票据/往来特殊场景、项目范围；Workbench open/proposed candidate 不计入成本。 |
| API shape、route facade、project scope | P0 | `tests/test_cost_statistics_api.py` | covered | month/explorer/project scope、invalid scope、cache hit/miss、导入 invalidation。 |
| 导出和 export preview | P1 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_service.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | covered | XLSX、filename、date range、project/expense filters、project scope 透传；Browser 覆盖 `read_export_only` 成功 download event、请求不带分页、下载内容字段；超过 20,000 行同步导出上限时结构化返回 `cost_statistics_export_row_limit_exceeded` 并在真实浏览器导出中心展示。 |
| runtime/cache scope | P0 | `tests/test_cost_statistics_runtime_service.py` | covered | runtime service 覆盖 scope normalization、schema key、invalidate months/all；不再通过 SQL projection 写页面派生存储。 |
| scope gateway/legacy cleanup | P0 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_manifest.py` | covered | legacy scope normalize、非法 scope reject；production checker dry-run/apply 已删除。 |
| Direct API/runtime no page projection worker | P0 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_runtime_state_policy.py` | covered | 页面 API 直接返回业务 payload；runtime/guard 防止 worker/AppStatus/production path 重新依赖 page projection。 |
| App Status scope-level semantics | P0 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py` | covered | 父 scope failed blocks；月份 shard failed/unavailable busy；scope details preserved。 |
| 首屏 SLO 探针 | P2 | `tests/test_http_slo_probe.py`、`tests/test_cost_statistics_api.py` | covered | 成本统计没有 rows 分页首屏；认证态 SLO 覆盖 page shell、explorer 和 summary，不读 Workbench 全量 payload。 |
| warmup job recovery/retry | P1 | `tests/test_cost_statistics_api.py`、`tests/test_import_job_queue.py` | covered | warmup summary、partial retry、interrupted recovery、duplicate running job guard。 |
| 前端页面交互 | P1 | `web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | covered | time/project/bank/expense view、drilldown、range picker、empty/error、旧同步字段忽略、export center、后端导出失败消息展示、OA 登录态缺失错误展示、同一流水拆成多条成本行时项目费用类型下钻不丢行/不触发表格重复 key；真实 Chromium 覆盖 explorer 暂时 503 错误态、普通空态/表格/导出防伪成功、点击刷新后恢复成本行，按时间首屏、按项目下钻、按银行选择银行账户/项目/流水详情、按费用类型选择费用类型/流水详情、导出中心成功下载/错误反馈、transaction detail 局部 unavailable 不打开旧详情且不影响导出、120+ 成本行在 390px 窄屏下按时间表/项目下钻表纵横滚动、右侧列 viewport 可见、导出入口和选择器无遮挡且无浏览器错误、Workbench 成本关系 candidate 不计入/confirmed 后计入成本、ETC 导入 confirm 后成本统计展示 ETC 成本行、no-OA 手续费批次 submit 后成本统计展示免 OA 成本行、外部往来 manual closure confirm 后成本统计展示闭环成本行，以及 settings 项目标记完成后 direct API 在 active/all project scope 下分别展示。 |
| Workbench 成本关系 fan-out | P0 | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_service.py`、`tests/test_workbench_relation_repository.py` | covered | Browser 已证明 open candidate 不进入成本项目/金额/明细，关联台确认 OA+bank+invoice 成本关系后成本页重新读取并展示 `智能工厂项目`、`58,000.00` 和对应流水详情。 |
| 前端 API mapper/cache | P1 | `web/src/test/CostStatisticsApi.test.ts` | covered | project scope 透传、direct explorer payload mapper、explorer cache keyed by month/scope、export 下载错误 JSON message 透出。 |
| 真实生产 scope cleanup `--apply` | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres 环境，只能按 runbook 只读检查后受控执行。 |

## 七类测试适用性

2026-06-28 modular IO 更新：旧 `cost_tax_sql_projection.py` 与成本统计 SQL runtime 测试已删除；成本统计当前测试事实源转为 direct API、业务 service、runtime/cache 和 boundary guard。历史 `read_model.cost_statistics_*` 表仅作为迁移清理对象，不再作为页面或 worker 覆盖入口。

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py` | 覆盖成本归因、项目范围、特殊业务链路、票据/往来排除或保留规则。 |
| 2. Service-layer tests | 适用 | `tests/test_cost_statistics_runtime_service.py`、`tests/test_project_costing_api.py` | 覆盖 runtime service、project costing 写入/查询边界。 |
| 3. API contract tests | 适用 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`tests/test_http_slo_probe.py`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖 explorer、month summary、project scope、export/export-preview、默认 SLO 探针、错误和 response shape；e2e 断言 `project_scope=all`、transaction detail、export-preview、export request/response、download filename/content、Workbench confirm 后成本 explorer/detail 重新读取，以及 ETC/no-OA/turnover/settings 后成本页面展示对应影响行。 |
| 4. Cache/background job tests | 适用 | `tests/test_cost_statistics_runtime_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_runtime_state_policy.py`、`tests/test_app_status_overview_service.py` | 覆盖 runtime/cache 边界、production path 不回退 Application/snapshot、App Status 不绑定已下线 worker；legacy SQL projection 测试已删除。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/CostStatisticsApi.test.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖页面状态、范围选择、drilldown、export center、后端失败消息展示、OA 登录态缺失错误展示、API mapper 和 cache；e2e 保护真实 Chromium tab、explorer 暂时 503 错误态/导出禁用/刷新恢复、direct explorer no-polling、time/project/bank/expense baseline、project scope、三段下钻、modal、preview、导出成功/错误反馈、transaction detail 局部 unavailable 不伪成功、120+ 大数据窄屏宽表纵横滚动和控件无遮盖、relation fan-out 后的项目/金额/详情展示、ETC 导入下游成本行展示、no-OA submit 后下游成本行展示、turnover manual closure 后下游成本行展示，以及 settings project scope 保存后的 active/all 可见性。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_cost_statistics_api.py`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖导入确认/Workbench relation 后成本统计 direct refetch；Playwright 覆盖 explorer -> project scope -> drilldown -> export preview/download/error、Workbench confirm -> 成本页重新读取 -> 成本项目/流水详情出现、ETC import confirm -> 成本项目和流水展示、no-OA submit -> 成本统计免 OA 手续费成本项目/流水展示、turnover manual closure confirm -> 成本统计外部往来闭环成本项目/流水展示 -> 回周转页撤回，以及 settings project completed save -> 成本统计 active 排除/all 保留；真实导入/周转/settings staging smoke 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 cost statistics tests，加 imports、invoice lifecycle、workbench、turnover、settings/project scope tests 的按改动选择扩展集 | 成本统计受多模块写入影响；任何导入、关系、规则、项目范围或 worker 改动都要问会影响哪些旧成本视图；e2e 防止真实浏览器中 project scope、detail modal、export center 和 candidate/linked relation 成本语义断链。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-18 | 成本统计 explorer 返回 `401 invalid_oa_session` 时，页面吞掉后端业务消息并显示泛化“成本统计数据加载失败”，导致用户误判为成本统计同步故障。 | `web/src/test/CostStatisticsPage.test.tsx::surfaces OA session errors from explorer loading` | covered |
| 2026-06-18 | App Health 显示成本统计已同步，但 legacy explorer SQL/Redis payload 仍是旧 shape，缺少当前页面曾需要的 `summary`、`time_rows`、`project_rows`、`expense_type_rows`，导致旧前端 mapper 抛错并显示泛化加载失败。 | 页面 API 已改为 direct service read；legacy payload shape 风险由成本统计 SQL/runtime tests 保留。 | covered |
| 2026-06-17 | 成本统计项目视图选中项目后再选择费用类型，若同一 `transaction_id` 对应多条成本行，前端用裸流水 id 作为 HeroUI Table 行 id/key，导致行身份冲突、丢行，真实浏览器可表现为卡死后白屏。 | `web/src/test/CostStatisticsPage.test.tsx::project view keeps split cost rows with the same transaction id renderable` | covered |
| 2026-06-18 | 关联台 open/proposed candidate 被误显示为成本项目或金额，或 OA+bank+invoice 成本关系确认后成本页没有重新读取并展示对应项目/流水。 | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_open_candidate_groups_are_excluded_from_cost_statistics`、`tests/test_workbench_relation_repository.py` | covered |
| 2026-06-19 | 成本统计 explorer 页面级旧同步诊断可能让页面显示刷新诊断、禁用导出或隐藏 direct payload。 | `web/e2e/cost-statistics-flow.spec.ts::keeps direct explorer rows visible without page-level polling`、`web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/CostStatisticsApi.test.ts::maps direct explorer payloads` | covered |
| 2026-06-20 | 成本统计 explorer 首屏暂时 503 时，页面可能直接显示正常空态或允许导出中心打开，用户没有显式刷新路径；背景 all-scope 参考数据请求也可能干扰失败恢复测试。 | `web/e2e/cost-statistics-flow.spec.ts::recovers explorer after a transient load failure when refreshed`、`web/src/test/CostStatisticsPage.test.tsx::refreshes explorer data after a transient loading failure` | covered locally; real network/direct API convergence pending |
| 2026-06-19 | 成本统计 explorer direct payload 下，流水详情局部错误不能打开旧详情；导出不再消费旧同步诊断。 | `web/e2e/cost-statistics-flow.spec.ts::keeps transaction detail unavailable local while export remains direct` | covered locally; real direct API convergence pending |
| 2026-06-19 | 成本统计导出中心只覆盖 row-limit 错误，缺少真实浏览器 download event、文件名、请求不带分页和导出字段保护。 | `web/e2e/cost-statistics-flow.spec.ts::downloads the current time-view cost rows with request filters and cost fields` | covered locally; real workbook open pending |
| 2026-06-19 | 成本统计在大数据/长字段/390px 窄屏下可能出现表格无法横向滚动、右侧列不可见、项目/费用类型选择器或导出入口被遮挡，或 direct payload 行数足够但浏览器层面不可用。 | `web/e2e/cost-statistics-flow.spec.ts::keeps large cost tables direct, scrollable, and usable on narrow screens` | covered locally; real production volume/performance pending |
| 2026-06-10 | 裸月份/裸 `all` scope 进入 durable queue，导致成本统计 worker 报 scope contract 错误并污染 App Status。 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_manifest.py` | covered；scope-contract repair 已删除 |
| 2026-06-16 | 外部往来 Postgres 事务写路径绕过 scope policy，再次向成本统计投递裸 `2026-02`、`2026-03`、`all` 并造成生产 dead-letter。 | `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction`、`tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear` | covered locally; production cleanup apply pending |
| 2026-06-16 | 把成本统计误当普通分页列表处理，遗漏 explorer/summary 认证态 SLO 或让页面回退读取 Workbench 全量 payload。 | `tests/test_http_slo_probe.py::HttpSloProbeTests::test_default_probes_cover_page_domains_and_known_slow_endpoints`、`tests/test_cost_statistics_api.py`、`tests/test_platform_runtime_boundary_guards.py` | covered |
| 2026-06-10 | 旧 `active:all` / `all:all` 父 scope 或 Workbench `all` 大 payload 模式回流。 | `tests/test_cost_statistics_api.py`、`tests/test_platform_runtime_boundary_guards.py` | covered |
| 2026-06-10 | 父 scope 等待缺失/过期月份 shard 时被伪造为已同步。 | 已下线：不再存在 cost statistics page projection parent scope；由 direct API/API tests 防止返回旧同步字段。 | retired |
| 2026-06-12 | Workbench open/proposed candidate 被当成 confirmed relation 计入成本金额。 | `tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_open_candidate_groups_are_excluded_from_cost_statistics`、`tests/test_workbench_relation_repository.py` | covered |
| 2026-06-13 | 成本税务 projection 直接从 OA 附件 parser cache 拼进项发票输入，绕过统一 Invoice repository。 | `tests/test_tax_offset_service.py::test_month_payload_includes_oa_attachment_invoices_by_issue_month`、`tests/test_tax_offset_api.py::test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata` | covered by shared tax/workbench boundary |
| 长期 | 月份 shard failed 误把整个成本统计主体验标红。 | `tests/test_app_status_overview_service.py` | covered |
| 长期 | legacy SQL projection miss/outdated 时 worker/runtime 返回假同步状态。 | 已下线：旧 cost/tax SQL projection 和 worker lane 已删除；platform/runtime guard 防回归。 | retired |
| 长期 | 导出和页面查询没有透传 project scope 或自定义日期范围。 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` | covered |
| 2026-06-16 | 成本统计 time/project/expense_type export-preview/export 对大匹配集同步生成预览 rows 或 XLSX，拖慢 API 线程和内存。 | `tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_export_preview_and_download_reject_large_time_export_before_workbook_generation`、`tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_cost_statistics_export_limit_returns_structured_error` | covered |
| 2026-06-16 | 成本统计下载接口收到 `cost_statistics_export_row_limit_exceeded` 等结构化错误时，前端下载路径不解析 JSON 或页面丢弃错误消息，用户只能看到泛化失败。 | `web/src/test/CostStatisticsApi.test.ts::surfaces backend row-limit messages from failed export downloads`、`web/src/test/CostStatisticsPage.test.tsx::shows backend export failure messages inside the export center` | covered |
| 2026-06-17 | 成本统计导出中心在真实浏览器中 preview/export 请求未携带当前项目范围或行数上限错误未展示。 | `web/e2e/cost-statistics-flow.spec.ts` | covered |
| 长期 | 成本统计错误纳入现金代收代付/票据购买/发票抵扣等特殊关系。 | `tests/test_cost_statistics_service.py` | covered |

## 关键 smoke flows

1. `银行/发票/ETC 导入确认、no-OA submit 或 turnover manual closure -> lifecycle/domain plan -> direct API / cache warmup -> 页面 direct API 展示`；ETC、no-OA 和 turnover 路径已有 Browser 证据断言成本页展示对应成本行。
2. `Workbench relation confirm/cancel -> cost statistics affected scopes/cache warmup -> 成本页 direct refetch -> 只展示 confirmed 成本关系`
3. `project scope setting change -> direct API 重新读取 active/all scope -> active view 排除已完成项目 -> all view 保留全部项目`；`web/e2e/settings-data-reset-flow.spec.ts` 已覆盖 settings 项目标记完成后进入成本统计验证 active/all direct API 结果。
4. 旧 `active:all` 父 scope 聚合发布流程已下线；如发现历史残留，只进入 cleanup wave，不作为 smoke flow。
5. `页面切换 view/date/project scope -> explorer API -> 暂时 503 显示错误语义 -> 不显示最终空态或旧项目行 -> 手动刷新 -> direct payload 后 drilldown/export`
6. `真实 Chromium 按时间首屏 -> read_export_only 打开导出中心 -> 导出 preview -> download event -> 文件名/字段/筛选断言 -> 按项目 -> project_scope=all -> 项目/费用类型/流水详情下钻 -> 导出 row-limit 错误反馈`
7. `真实 Chromium 390px 窄屏 -> 120+ 成本行 direct explorer -> 按时间宽表横向/纵向滚动 -> 右侧列 viewport 可见 -> 按项目选择长项目/费用类型 -> 项目对应流水表横向/纵向滚动 -> 无 console/page/request/dialog 错误`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service tests.test_project_costing_service tests.test_project_costing_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_runtime_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_runtime_state_policy -v
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
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_read_model_refresh_gateway -v
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest、deterministic Playwright smoke 和 build，覆盖完整成本统计、App Status、legacy gateway guard、前端测试集、成本统计 browser 主流程和 Workbench 成本关系 fan-out e2e。单轮模块验证只跑最小闭环。

## 未测风险

- 旧 `scripts/check-read-model-scope-contracts.py --apply` 已删除；生产 legacy runtime 残留不再通过页面 projection repair helper 清理。
- 本地测试不跑真实 RabbitMQ/Redis/systemd smoke；Workbench 成本关系确认后 direct API / cache warmup 的真实收敛，以及真实网络中断后的浏览器重试体验需要生产或 staging smoke。
- 本地已覆盖成本统计超过 20,000 行同步导出 fail-closed、导出中心错误反馈，以及 120+ 行窄屏宽表滚动/控件可用性；真实浏览器文件打开、真实生产超大数据查询/下载耗时和生产视觉性能仍需 staging/manual smoke。
