# 成本统计测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 2026-07-11 - 正式 relation lineage 与全银行支出口径测试收敛

- 变更类型：test fixture contract correction + read model lineage regression。
- 架构结论：成本统计 OA 归因只能消费 active `workbench_relation`，Workbench open/proposed candidate 即使相似度很高也不得进入成本；API fixture 必须通过正式 confirm-link 写边界建立 active relation，禁止直接改 pair query service 或恢复 candidate fallback。`按标签` / `按时间` 的 `bank_flow_time_rows` 是独立的全银行支出 projection，测试数据必须从 canonical bank transactions 构造，不能借用 OA 配对成本行冒充该事实集。
- 更新测试：`tests/test_cost_statistics_api.py`。
- 覆盖点：fixture 通过真实 `/api/workbench/actions/confirm-link` 建立关系；候选关系仍被排除；全银行支出可包含没有 OA relation 的流水，并保持 `未配对OA` / `未分类` 展示口径；project/expense-type export 继续消费 OA 配对成本行。
- 七类测试决策：business core、service-layer、API contract、read model/cache/background job、end-to-end business-flow integration、existing regression 适用并由成本统计 API/服务组合测试覆盖；frontend interaction 行为未变，继续由既有 `CostStatisticsPage.test.tsx` 与 Browser flow 覆盖。

## 2026-07-10 - 成本统计标签规则和双统计口径

- 变更类型：settings-backed rule contract + read model payload contract + frontend drawer interaction。
- 架构结论：成本统计标签规则由 `AppSettingsService` 持久化，暴露主/子标签 leaf code 与虚拟 `__uncategorized__` 未分类标签；默认未配置等价于全选当前有效支出标签 + 未分类，显式空数组表示全部不进入成本统计。`按项目`、`按银行`、`按OA费用类型` 只统计规则过滤后的 OA 配对 `time_rows`；`按标签`、`按时间` 只统计规则过滤后的全部银行支出 `bank_flow_time_rows`。规则保存不触发 read model rebuild，只返回当前成本统计 scope 的 operation barrier target；页面等待 fresh 后关闭抽屉。
- 新增/更新测试：`tests/test_app_settings_service.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`。
- 覆盖点：默认标签选择包含有效支出标签和未分类；保存空选择可持久化；API 读写标签规则并返回 operation barrier target，且缺少写权限时不调用 settings service；query service 对 OA 配对行和全银行支出行按同一标签规则过滤，并证明两组统计口径总额可不同、组内总额一致；前端 mapper 支持 `bank_flow_time_rows`；规则抽屉保存后等待 `cost_statistics` fresh 才关闭，且 API 标记只读时禁用保存。
- 七类测试决策：business core 适用，覆盖标签选择和金额口径过滤；service-layer 适用，覆盖 settings 持久化、query service 过滤和 read model payload 使用；API contract 适用，覆盖 `GET/PUT /api/cost-statistics/tag-rules` 与 explorer 新字段；read model/cache/background job 适用，覆盖 v5 payload、query-time filtering 和不触发 rebuild 的边界；frontend interaction 适用，覆盖紧凑抽屉和等待 fresh；end-to-end business-flow 本轮用 API/service/component 闭环，真实 worker/browser 写流沿用既有成本统计 e2e；existing regression 适用，覆盖旧 explorer mapper、旧五视图按钮和导出/详情不会回退 live fallback。
- 验证命令：见本轮最终说明。

## 2026-07-06 - 按流水标签类型读取银行明细有效主/子标签

- 变更类型：read model payload contract + cross-module read boundary。
- 架构结论：成本统计 `time_rows.bank_tag_*` 不再信任 Workbench 行内旧标签字段；月份 shard 使用 `BankTransactionTagReadFacade` 从 fresh `bank_detail` scoped read model 批量读取银行明细有效分类，并把 `bank_detail_source_versions` 写入成本统计 source_versions。当时 payload schema 升级为 `2026-07-cost-statistics-bank-tags-v4`，当前 schema 已在 2026-07-10 升级到 v5；旧 v3/v4 父 scope 即使仍被标记 fresh，也必须返回空刷新态并入队重建，不能继续把旧 `未标记` 行交给页面。`bank_detail` 非 fresh 时成本统计 worker 抛 `bank_detail_read_model_not_fresh`，由 runtime dependency retry 处理，不发布旧标签 payload。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py`、`tests/test_runtime_bootstrap.py`。
- 覆盖点：Workbench bank row 不携带标签字段时，成本统计仍从银行明细 facade 写入主标签、子标签和 label path；成本统计 expected source_versions 包含 bank detail scope 版本；worker wiring 向 `CostStatisticsSqlProjectionBuilder` 传入 `bank_transaction_tag_read_facade`；旧 v3 `active:all` payload 不向页面返回旧行并入队重建；依赖非 fresh 时不保存成本统计 read model。
- 七类测试决策：service-layer、API contract、read model/cache/background job、existing regression 适用并覆盖；frontend interaction 由既有 `CostStatisticsPage.test.tsx::bank tag view drills down from primary tag to sub tag to transaction` 覆盖，本轮 UI 未变；business core 金额归因不变；E2E 写流继续沿用银行明细/成本统计既有 Browser flows，本轮不新增跨模块浏览器用例。
- 验证命令：见本轮最终说明。

## 2026-07-05 - 银行账户全集、标签规则联动、时间格式与表头总金额

- 变更类型：read model payload contract + frontend interaction/layout + cross-module lifecycle。
- 架构结论：按银行统计的银行全集由 settings owner 的 `bank_account_mappings` 经成本统计 SQL projection 写入 explorer `bank_accounts`，页面只合并 `bank_accounts + time_rows`，不再只从当前流水推断银行列表。当时按流水标签类型只读 `time_rows.bank_tag_*`；2026-07-10 后 `按标签` / `按时间` 改为读取 `bank_flow_time_rows`。自动标签规则变化通过 `bank_auto_tag_rules_changed -> cost_statistics.read_model.refresh` 刷新 read model。按时间展示格式化后的 `YYYY-MM-DD HH:mm:ss`，过滤仍使用原始 `trade_time`。五种统计口径表头均展示当前范围总金额。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_bank_details_sql_runtime.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/AppSidebar.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`。
- 覆盖点：explorer payload 必须包含 `bank_accounts`；settings 银行账户映射进入 `source_versions.bank_account_mappings_fingerprint`；标签规则版本继续进入 `source_versions.bank_auto_tag_rules_version`；`bank_auto_tag_rules_changed` lifecycle 计划包含 `cost_statistics.read_model.refresh`；前端 mapper 归一 `bank_accounts`；按银行统计展示设置中的零金额账户；时间列不直出 ISO/T 字符串；各视图表头展示总金额；sidebar 深蓝背景有组件回归断言。
- 七类测试决策：service-layer、API contract、read model/cache/background job、frontend interaction、existing regression 适用并覆盖；business core 金额归因口径不变，不新增独立业务规则测试；end-to-end business-flow 使用既有成本统计/银行明细/settings browser flows，本轮新增的是读模型合同与页面交互，不新增跨模块写流 e2e。
- 验证命令：见本轮最终说明。

## 2026-07-05 - 成本统计页面 I/O、旧 UI 与旧后端 fallback 关闭

- 变更类型：frontend layout / page I/O cleanup + route-owner/query-runtime legacy dependency cleanup。
- 架构结论：成本统计页面主范围选择器只暴露 `all` / `year` / `month` 三种读侧范围，使用单一按钮打开浮层；页面不再暴露自定义日期范围、项目范围切换按钮、顶部三张 summary card 和标题下解释文案。精确日期范围仍属于导出中心 I/O。页面固定以 `project_scope=active` 请求 explorer/detail/export；`project_scope=all` 仍由后端 API/read model 合同测试覆盖。
- 新增/更新测试：`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts`、`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_service.py`、`tests/test_cost_statistics_derived_lifecycle_executor.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_platform_runtime_boundary_guards.py`。
- 覆盖点：旧 summary card 组件/样式删除；主页面范围控件没有 custom date/radio/tab 残留；所有视图的范围按钮可选 all/year/month；项目视图不再出现 `项目范围：进行中/所有项目`；导出中心继续携带 active project scope 和精确日期范围；route owner 不再接收未使用的旧 service 依赖；query service 不再持有 live `CostStatisticsService`、local read model service 或 `_cached_month_entries` fallback；runtime service 不再持有 `explorer_loader` / read model upsert writer；live export helper 与 `ProjectDetailExportService` 已删除；derived lifecycle 计划只报告 `cost_statistics.read_model.refresh`。
- 七类测试决策：service-layer、API contract、read model/cache/background job、frontend interaction、existing regression 适用并覆盖；business core 适用但只保留成本归因测试，删除 live export 专项；end-to-end business-flow 继续沿用 browser/import/settings/Workbench fan-out 覆盖，本轮不新增跨模块业务流。
- 验证命令：见本轮最终说明。

## 2026-07-04 - 按流水标签类型视图与 bank tag payload 合同

- 变更类型：read model payload contract + frontend 派生视图。
- 架构结论：流水标签统计属于成本统计 explorer read model 的读侧派生功能；页面只能读取 `cost_statistics.time_rows.bank_tag_*`，不得直接调用银行明细页 read model 或本地重算银行标签事实。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows`、`tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_month_statistics_only_counts_outflow_rows_with_complete_oa_cost_fields`、`tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_explorer_all_aggregates_entries_across_multiple_months`、`web/src/test/CostStatisticsApi.test.ts::maps bank tag fields from explorer time rows`、`web/src/test/CostStatisticsPage.test.tsx::bank tag view drills down from primary tag to sub tag to transaction`。
- 覆盖点：Workbench bank row 的 `effective_category_*` / `category_*` 字段进入成本统计 month shard payload；parent scope 从 materialized rows 聚合时保留标签字段；SQL projection 与 read-model query/export 输出同一 shape；前端 mapper 归一 snake_case 标签字段；页面三栏为 `主标签 / 子标签 / 流水`，第一、第二栏合计 50% 宽度。
- 七类测试决策：business core 不新增独立规则测试，因为成本归因金额口径不变；service-layer、API contract、read model/cache、frontend interaction、existing regression 适用并覆盖；E2E 本轮先不新增，因为该功能不新增跨模块写流，后续可并入成本统计浏览器 smoke。
- 验证命令：见本轮最终说明。

## 2026-07-02 - secondary read/export route read-model closure

- 变更类型：route-owner/query-service 边界收口。
- 新增/更新测试：`tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_cost_statistics_secondary_read_routes_delegate_to_query_service_and_fail_closed`、导出/preview 用例显式预热 read model、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_cost_statistics_routes_use_route_owner`。
- 覆盖点：project/detail/export/export-preview 路由只调用 `CostStatisticsQueryService`；read model 未 fresh 返回 `409 cost_statistics_read_model_not_fresh`；导出 row limit 仍返回 `cost_statistics_export_row_limit_exceeded`；静态 guard 禁止 route owner 回调旧 `CostStatisticsService` 二级读方法。
- 验证命令：见本轮最终说明。

## 修改前影响面清单

成本统计是跨银行流水、发票、OA、Workbench relation、项目归因和费用分类的派生 read model。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 业务归因 | `CostStatisticsService`、project costing service、workbench relation/detail payload | 项目、费用类型、费用内容、金额方向、OA 字段、银行字段和 relation distribution 不能由页面重算。 |
| 项目范围 | app settings project status、`project_scope` | `active` 默认，只排除已完成项目；`all` 包含全部；未知项目保持 active；非法 scope 拒绝。 |
| read model scope contract | `ReadModelRefreshGateway`、scope policy registry | 合法 scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all`；裸月份/裸 all 只能在 gateway 归一化。 |
| 月份 shard | `read_model.cost_statistics_rows`、`cost_statistics.read_model.refresh` | 月份 shard 从对应 Workbench 月份 read model 构建；成功后重新入队同 project scope 父 scope。 |
| Workbench 输入边界 | `read_model.workbench_generations` active generation、`read_model.workbench_groups`、`read_model.workbench_group_rows`、`read_model.workbench_rows` | 成本统计必须先定位 active generation，再按 `generation_id + scope_key` 消费 groups 和成员 row；`workbench_groups.payload` 只作为组级 metadata 输入，OA/银行成员必须从 `workbench_group_rows + workbench_rows` materialize，不能按裸 `scope_key` 扫描历史 generation 或继续读旧 group JSON 成员数组。 |
| 全期间父 scope | `read_model.cost_statistics_read_models` | 父 scope 是一等 read model；从已物化月份 rows 聚合，不读 Workbench `all` 全量 payload。 |
| App Status readiness | `read_model.app_status_readiness`、`job.read_model_dirty_scopes`、`job.outbox_events` | 父 scope failed/unavailable 才阻断成本统计主体验；月份 shard failed/unavailable 是局部 busy。 |
| API/read cache | `/api/cost-statistics*`、Redis hot cache、SQL read model | fresh gate 后才能缓存；miss/stale 返回 refreshing 并入队，不同步重建伪 fresh。 |
| 导出 | cost statistics export/export-preview | time/project/expense type/bank view、date range、project scope、advanced export filters 和 filename contract。 |
| 前端交互 | `CostStatisticsPage`、`web/src/features/cost-statistics/api.ts` | 单按钮 all/year/month range、view switch、drilldown、modal、loading/error/empty/refreshing、export center；自定义日期范围只属于导出中心。 |
| 跨模块 fan-out | imports、ETC、pending invoice rules、workbench relation、turnover、project scope settings | 写入后必须通过 lifecycle/dirty scope/outbox 影响成本统计，不能只靠前端事件。 |

## 场景覆盖清单

## 2026-06-26 - Month-scope unchanged source_versions skip

- 变更类型：narrow implementation slice。
- 背景：生产 direct read model SLO 显示 `cost_statistics` 月度 scope 在输入未变化时仍重扫 Workbench active generation 输入并重写 payload，影响 p95。月度 projection 现在把 workbench active generation `source_versions` 纳入自身 source_versions，只有 SQL view 已 fresh 且版本完全一致时才返回 `skipped/source_versions_unchanged`。
- 新增/更新测试：`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_skips_unchanged_month_scope_without_workbench_scan`。
- 七类测试决策：service-layer、read model/cache/background job、existing feature regression 适用并覆盖；API contract/frontend/E2E/business core 不新增，因为 response shape、页面行为、成本归因和导出语义不变。
- 验证结果：`python -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_cost_statistics_runtime_service.py tests/test_read_model_manifest.py -q` 已作为扩展集合的一部分通过；完整 backend verify 仍需本轮最终执行。

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 成本统计核心归因 | P0 | `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py` | covered | 支出行、OA cost 字段、relation distribution、现金/票据/往来特殊场景、项目范围；Workbench open/proposed candidate 不计入成本。 |
| API shape、route facade、project scope | P0 | `tests/test_cost_statistics_api.py` | covered | month/explorer/project scope、invalid scope、cache hit/miss、导入 invalidation。 |
| 导出和 export preview | P1 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | covered | XLSX、filename、date range、project/expense filters、project scope 透传；导出只从 fresh explorer read model 组装；Browser 覆盖 `read_export_only` 成功 download event、请求不带分页、下载内容字段；超过 20,000 行同步导出上限时结构化返回 `cost_statistics_export_row_limit_exceeded` 并在真实浏览器导出中心展示。 |
| read model service scope | P0 | `tests/test_cost_statistics_read_model_service.py` | covered | scope validation、schema mismatch discard、deep copy、invalidate months/all。 |
| scope gateway/legacy cleanup | P0 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered | legacy scope normalize、非法 scope reject、production checker dry-run/apply/replacement dedupe。 |
| SQL runtime fresh/miss/stale | P0 | `tests/test_cost_statistics_sql_runtime.py` | covered | SQL read model read、Redis cache、API miss enqueue、malformed explorer payload requeue、production requires SQL model。 |
| parent scope aggregation | P0 | `tests/test_cost_statistics_sql_runtime.py` | covered | `active:all` / `all:all` 从 materialized shard rows 聚合，不读 Workbench all payload。 |
| parent waits for shard readiness | P0 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_app_status_overview_service.py` | covered | missing/stale shards 入队，父 scope refreshing；shards converged 后发布 parent fresh。 |
| App Status scope-level semantics | P0 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py` | covered | 父 scope failed blocks；月份 shard failed/unavailable busy；scope details preserved。 |
| 首屏 SLO 探针与有界聚合 | P2 | `tests/test_http_slo_probe.py`、`tests/test_cost_statistics_sql_runtime.py` | covered | 成本统计没有 rows 分页首屏；认证态 SLO 覆盖 page shell、explorer 和 summary，父 scope 从已物化月份 shard 聚合，不读 Workbench 全量 payload。 |
| legacy warmup compatibility bridge | P2 | `tests/test_cost_statistics_api.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | 历史 `cost_statistics_cache_warmup` job retry 会关闭旧 job 并转入 `cost_statistics.read_model.refresh`；新 query/runtime/invalidation 不再创建 warmup job 或写 read model。 |
| 前端页面交互 | P1 | `web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | covered | time/project/bank/expense/bank-tag view、drilldown、单按钮 range picker、empty/error/refreshing/stale/failed、export center、后端导出失败消息展示、OA 登录态缺失错误展示、同一流水拆成多条成本行时项目费用类型下钻不丢行/不触发表格重复 key；真实 Chromium 覆盖 explorer 暂时 503 错误态、普通空态/表格/导出防伪成功、点击刷新后恢复 fresh 成本行，按时间首屏、按项目下钻、按银行选择银行账户/项目/流水详情、按费用类型选择费用类型/流水详情、导出中心成功下载/错误反馈、read model 非 fresh 不显示最终空态/旧项目行/旧 summary card 且禁用导出、fresh explorer 下 detail/export non-fresh 不伪成功和不下载、120+ 成本行在 390px 窄屏下按时间表/项目下钻表纵横滚动、右侧列 viewport 可见、导出入口和选择器无遮挡且无浏览器错误、Workbench 成本关系 candidate 不计入/confirmed 后计入成本、ETC 导入 confirm 后成本统计 fresh read model 与 ETC 成本行展示、bank-flow selected-row submit 后成本统计 fresh read model 与流水规则手续费成本行展示、外部往来 manual closure confirm 后成本统计 fresh read model 与闭环成本行展示，以及 settings 项目标记完成后 active scope 排除已完成项目且项目范围切换 UI 不出现。 |
| Workbench 成本关系 fan-out | P0 | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_service.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_workbench_relation_repository.py` | covered | Browser 已证明 open candidate 不进入成本项目/金额/明细，关联台确认 OA+bank+invoice 成本关系后成本页重新读取并展示 `智能工厂项目`、`58,000.00` 和对应流水详情。 |
| 前端 API mapper/cache | P1 | `web/src/test/CostStatisticsApi.test.ts` | covered | project scope 透传、read model status mapping、explorer cache keyed by month/scope、export 下载错误 JSON message 透出。 |
| 真实生产 scope cleanup `--apply` | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres 环境，只能按 runbook 只读检查后受控执行。 |

## 七类测试适用性

2026-07-05 modular IO Close：`cost_statistics` 当前模块状态为 `closed`。`CostStatisticsQueryService` 只读 SQL read model/Redis fresh cache，miss/stale/repository unavailable 只返回 `refreshing` 并入队 `cost_statistics.read_model.refresh`；`CostStatisticsRuntimeService` 不再接收 live `explorer_loader` 或写 explorer read model/Redis cache；`CostStatisticsService` 不再拥有 live export-preview/export helper，旧 `ProjectDetailExportService` 已删除。历史 `cost_statistics_cache_warmup` job type 只保留兼容 retry/健康展示，不再作为成本统计 payload 写入路径。`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_query_runtime_do_not_keep_legacy_live_fallbacks` 锁定这些旧链路不得回归。

2026-07-01 modular IO 更新：`cost_statistics` 刷新链路移除旧 `cost-tax` 成本统计兼容消费者，只保留 `cost-statistics` 专用 worker；`cost-tax` 仅属于 `tax_offset` 兼容链路。`tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests::test_cost_tax_worker_no_longer_consumes_cost_statistics_refreshes`、`tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts` 和 `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_cost_statistics_shard_convergence_reasons_do_not_bump_active_scope` 锁定 worker I/O、manifest 辅助 worker 边界和 active scope 内部分片收敛不重复 bump 的性能合同。生产性能 smoke 发现月度 projection 按裸 `scope_key` 扫描 `workbench_groups` 历史 generation，`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` 现在锁定 active generation join、结构化 `workbench_group_rows + workbench_rows` 成本输入，并禁止继续通过 `jsonb_path_exists(workbench_groups.payload, ...)` 读取旧成员数组；`test_cost_statistics_scope_shards_are_listed_from_active_workbench_generations` 锁定父 scope shard 枚举只能来自 active `workbench_generations`。

2026-06-24 modular IO 历史上下文：`read-models:next-pilot-selection-after-tax-offset` 选择 `cost_statistics` 作为第九个非 Go read model 试点。`read-models:cost-statistics-repository-port-extraction` 已新增 `CostStatisticsReadModelRepositoryPort`，证明 cost statistics port 只暴露 `load_cost_statistics_read_models`、`get_cost_statistics_view`、`save_cost_statistics_read_models`，并让 projection save 与 SQL read wiring 使用该 port。`read-models:cost-statistics-refresh-freshness-operation-barrier-audit` 已确认 SQL fresh gate、parent aggregate、force refresh、App Status registry 和 primary `cost-statistics` worker 有本地证据。`read-models:cost-statistics-derived-lifecycle-executor-port-extraction` 已新增 `CostStatisticsDerivedLifecycleExecutor`，移除 `Application._derived_lifecycle_cost_statistics_executor(...)`，并用 `tests/test_cost_statistics_derived_lifecycle_executor.py` 与 platform guard 锁定 lifecycle invalidation、metadata 和 `enqueued_jobs` accounting。`read-models:cost-statistics-post-derived-local-implementation-closure-audit` 当时确认 warmup/retry/rebuild app 方法均为 runtime delegate，但真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred，所以当时未声明 closed；该状态已由 2026-07-05 Close 记录取代。`read-models:cost-statistics-full-state-read-model-snapshot-quarantine` 已移除 broad `_persist_state(...)` 对 `cost_statistics_read_models` 的写入，并扩展 `tests/test_read_model_architecture_guards.py` 防止 cost/tax read model broad full-state snapshot 写入回归。

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py` | 覆盖成本归因、项目范围、特殊业务链路、票据/往来排除或保留规则。 |
| 2. Service-layer tests | 适用 | `tests/test_cost_statistics_read_model_service.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_project_costing_api.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 read model service、runtime service、project costing 写入/查询边界，并静态禁止 query/runtime 恢复 live fallback 或旧 writer。 |
| 3. API contract tests | 适用 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`tests/test_http_slo_probe.py`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖 explorer、month summary、project scope、export/export-preview、默认 SLO 探针、错误和 response shape；后端/API tests 覆盖 `project_scope=all` 合同，页面 e2e 断言 active scope、transaction detail、export-preview、export request/response、download filename/content、Workbench confirm 后成本 explorer/detail 重新读取、ETC import confirm 后成本 explorer 返回 `read_model_status=fresh`，bank-flow selected-row submit 后成本 explorer 返回 fresh，turnover manual closure confirm 后成本 explorer 返回 fresh，以及 settings 保存项目状态后 active explorer 返回 fresh 并排除已完成项目。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_app_status_overview_service.py` | 覆盖 SQL read model、Redis hot cache、payload contract invalid fail-closed、scope contract、worker refresh、parent/shard readiness、父 scope 有界聚合和 App Status。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/CostStatisticsApi.test.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖页面状态、范围选择、drilldown、export center、后端失败消息展示、OA 登录态缺失错误展示、API mapper 和 cache；e2e 保护真实 Chromium tab、explorer 暂时 503 错误态/导出禁用/刷新恢复、time/project/bank/expense/bank-tag baseline、active project scope、三段下钻、modal、preview、导出成功/错误反馈、read model 非 fresh 防 false-empty/旧数据、fresh explorer 下 detail/export non-fresh 不伪成功和不下载、120+ 大数据窄屏宽表纵横滚动和控件无遮盖、relation fan-out 后的项目/金额/详情展示、ETC 导入下游成本行展示、bank-flow selected-row submit 后下游成本行展示、turnover manual closure 后下游成本行展示，以及 settings project scope 保存后的 active 可见性。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts` | 覆盖导入确认/Workbench invalidation/read model enqueue 到成本统计；Playwright 覆盖 explorer -> project scope -> drilldown -> export preview/download/error、Workbench confirm -> 成本页重新读取 -> 成本项目/流水详情出现、ETC import confirm -> 税金抵扣/成本统计 fresh read model -> ETC 成本项目和流水展示、bank-flow selected-row submit -> operation barrier -> 成本统计 fresh read model -> 流水规则手续费成本项目/流水展示、turnover manual closure confirm -> operation barrier -> 成本统计 fresh read model -> 外部往来闭环成本项目/流水展示 -> 回周转页撤回，以及 settings project completed save -> 成本统计 active 排除/all 保留；真实导入/周转/settings 到 worker drain 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 cost statistics tests，加 imports、invoice lifecycle、workbench、turnover、settings/project scope tests 的按改动选择扩展集 | 成本统计受多模块写入影响；任何导入、关系、规则、项目范围或 worker 改动都要问会影响哪些旧成本视图；e2e 防止真实浏览器中 project scope、detail modal、export center 和 candidate/linked relation 成本语义断链。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-18 | 成本统计 explorer 返回 `401 invalid_oa_session` 时，页面吞掉后端业务消息并显示泛化“成本统计数据加载失败”，导致用户误判为成本统计/read model 故障。 | `web/src/test/CostStatisticsPage.test.tsx::surfaces OA session errors from explorer loading` | covered |
| 2026-06-18 | App Health 显示成本统计已同步，但 explorer SQL/Redis payload 仍是旧 shape，缺少当前页面需要的 `summary`、`time_rows`、`project_rows`、`expense_type_rows`，导致前端 mapper 抛错并显示泛化加载失败。 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_api_rejects_malformed_fresh_sql_payload_and_requeues`、`tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_invalid_fresh_cache_payload_contract_misses_and_uses_sql_view`、`test_invalid_sql_payload_contract_enqueues_refresh_without_populating_cache` | covered |
| 2026-06-17 | 成本统计项目视图选中项目后再选择费用类型，若同一 `transaction_id` 对应多条成本行，前端用裸流水 id 作为 HeroUI Table 行 id/key，导致行身份冲突、丢行，真实浏览器可表现为卡死后白屏。 | `web/src/test/CostStatisticsPage.test.tsx::project view keeps split cost rows with the same transaction id renderable` | covered |
| 2026-06-18 | 关联台 open/proposed candidate 被误显示为成本项目或金额，或 OA+bank+invoice 成本关系确认后成本页没有重新读取并展示对应项目/流水。 | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_open_candidate_groups_are_excluded_from_cost_statistics`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` | covered |
| 2026-06-19 | 成本统计 explorer 返回 `refreshing` / `stale` / `failed` 的空 payload 时，页面可能误显示最终空态、旧项目行、旧 summary card 指标或允许导出非 fresh 数据。 | `web/e2e/cost-statistics-flow.spec.ts::does not treat * read model payloads as final empty cost data`、`web/src/test/CostStatisticsPage.test.tsx::hides read model refresh details without treating empty accepted payload as final empty data` | covered |
| 2026-06-20 | 成本统计 explorer 首屏暂时 503 时，页面可能直接显示正常空态或允许导出中心打开，用户没有显式刷新路径；背景 all-scope 参考数据请求也可能干扰失败恢复测试。 | `web/e2e/cost-statistics-flow.spec.ts::recovers explorer after a transient load failure when refreshed`、`web/src/test/CostStatisticsPage.test.tsx::refreshes explorer data after a transient loading failure` | covered locally; real network/worker drain pending |
| 2026-06-19 | 成本统计 explorer fresh 但流水详情或导出接口返回 non-fresh 时，页面可能打开旧详情、保留旧预览或生成下载文件。 | `web/e2e/cost-statistics-flow.spec.ts::does not treat non-fresh transaction detail or export responses as successful results` | covered locally; real worker drain pending |
| 2026-06-19 | 成本统计导出中心只覆盖 row-limit 错误，缺少真实浏览器 download event、文件名、请求不带分页和导出字段保护。 | `web/e2e/cost-statistics-flow.spec.ts::downloads the current time-view cost rows with request filters and cost fields` | covered locally; real workbook open pending |
| 2026-06-19 | 成本统计在大数据/长字段/390px 窄屏下可能出现表格无法横向滚动、右侧列不可见、项目/费用类型选择器或导出入口被遮挡，或 fresh read model 行数足够但浏览器层面不可用。 | `web/e2e/cost-statistics-flow.spec.ts::keeps large cost tables fresh, scrollable, and usable on narrow screens` | covered locally; real production volume/performance pending |
| 2026-06-10 | 裸月份/裸 `all` scope 进入 durable queue，导致成本统计 worker 报 scope contract 错误并污染 App Status。 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered |
| 2026-06-16 | 外部往来 Postgres 事务写路径绕过 scope policy，再次向成本统计投递裸 `2026-02`、`2026-03`、`all` 并造成生产 dead-letter。 | `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction`、`tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear` | covered locally; production cleanup apply pending |
| 2026-06-16 | 把成本统计误当普通分页列表处理，遗漏 explorer/summary 认证态 SLO 或让父 scope 回退读取 Workbench 全量 payload。 | `tests/test_http_slo_probe.py::HttpSloProbeTests::test_default_probes_cover_page_domains_and_known_slow_endpoints`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows` | covered |
| 2026-07-03 | Workbench group payload 去重后，成本统计若继续从 `workbench_groups.payload` 的 `oa_rows` / `bank_rows` JSON 数组读成员，会重新依赖旧大 payload 并漏掉 metadata-only group。 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` | covered |
| 2026-07-01 | 成本统计月份 projection 绕过 Workbench active generation 边界，按裸 `scope_key` 扫描 `read_model.workbench_groups` 历史 generation，导致生产 `2026-06` 扫描 126k groups / 629MB JSON，并存在旧 generation 污染风险。 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts`、`test_cost_statistics_scope_shards_are_listed_from_active_workbench_generations` | covered |
| 2026-06-10 | `active:all` / `all:all` 父 scope 错误读取 Workbench `all` 大 payload。 | `tests/test_cost_statistics_sql_runtime.py` | covered |
| 2026-06-10 | 父 scope 等待缺失/stale 月份 shard 时被伪造为 fresh。 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_app_status_overview_service.py` | covered |
| 2026-06-12 | Workbench open/proposed candidate 被当成 confirmed relation 计入成本金额。 | `tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_open_candidate_groups_are_excluded_from_cost_statistics`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` | covered |
| 2026-06-13 | 成本税务 projection 直接从 OA 附件 parser cache 拼进项发票输入，绕过统一 Invoice repository。 | `tests/test_tax_offset_service.py::test_month_payload_includes_oa_attachment_invoices_by_issue_month`、`tests/test_tax_offset_api.py::test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata` | covered by shared tax/workbench boundary |
| 长期 | 月份 shard failed 误把整个成本统计主体验标红。 | `tests/test_app_status_overview_service.py` | covered |
| 长期 | SQL read model miss/stale 时 API 同步 rebuild 或返回假 fresh。 | `tests/test_cost_statistics_sql_runtime.py` | covered |
| 长期 | 导出和页面查询没有透传 project scope，或导出中心没有透传精确日期范围。 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` | covered |
| 2026-06-16 | 成本统计 time/project/expense_type export-preview/export 对大匹配集同步生成预览 rows 或 XLSX，拖慢 API 线程和内存。 | `tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_cost_statistics_export_limit_returns_structured_error`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_query_runtime_do_not_keep_legacy_live_fallbacks` | covered |
| 2026-06-16 | 成本统计下载接口收到 `cost_statistics_export_row_limit_exceeded` 等结构化错误时，前端下载路径不解析 JSON 或页面丢弃错误消息，用户只能看到泛化失败。 | `web/src/test/CostStatisticsApi.test.ts::surfaces backend row-limit messages from failed export downloads`、`web/src/test/CostStatisticsPage.test.tsx::shows backend export failure messages inside the export center` | covered |
| 2026-06-17 | 成本统计导出中心在真实浏览器中 preview/export 请求未携带当前项目范围或行数上限错误未展示。 | `web/e2e/cost-statistics-flow.spec.ts` | covered |
| 长期 | 成本统计错误纳入现金代收代付/票据购买/发票抵扣等特殊关系。 | `tests/test_cost_statistics_service.py` | covered |

## 关键 smoke flows

1. `银行/发票/ETC 导入确认、bank-flow selected-row submit 或 turnover manual closure -> lifecycle/domain plan -> cost_statistics dirty scope -> cost-statistics worker -> month shard fresh -> parent scope re-enqueue -> all scope fresh -> 页面展示`；ETC、bank-flow 和 turnover 路径已有 Browser 证据断言成本页 fresh explorer 与对应成本行。
2. `Workbench relation confirm/cancel -> cost statistics invalidation -> affected month shard refresh -> App Status busy -> fresh 后恢复 -> 成本页重新读取并只展示 confirmed 成本关系`
3. `project scope setting change -> active/all scope refresh -> active view 排除已完成项目`；`web/e2e/settings-data-reset-flow.spec.ts` 已覆盖 settings 项目标记完成后进入成本统计验证 active fresh scope，`project_scope=all` 保留为后端 API/read model 合同。
4. `active:all 父 scope refresh -> 检查 month shard readiness -> 缺失 shard 入队 -> 父 scope refreshing -> shards fresh 后聚合发布`
5. `页面切换 view/date scope -> explorer API -> stale/refreshing/failed 或暂时 503 显示刷新或不可用语义 -> 不显示最终空态或旧项目行 -> 暂时 503 时手动刷新 -> fresh 后 drilldown/export`
6. `真实 Chromium 按时间首屏 -> read_export_only 打开导出中心 -> 导出 preview -> download event -> 文件名/字段/筛选断言 -> 按项目 -> active scope 项目/费用类型/流水详情下钻 -> 导出 row-limit 错误反馈`
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
cd web && npx playwright test e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium
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
