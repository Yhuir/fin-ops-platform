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
| 导出和 export preview | P1 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` | covered | XLSX、filename、date range、project/expense filters、project scope 透传。 |
| read model service scope | P0 | `tests/test_cost_statistics_read_model_service.py` | covered | scope validation、schema mismatch discard、deep copy、invalidate months/all。 |
| scope gateway/legacy cleanup | P0 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered | legacy scope normalize、非法 scope reject、production checker dry-run/apply/replacement dedupe。 |
| SQL runtime fresh/miss/stale | P0 | `tests/test_cost_statistics_sql_runtime.py` | covered | SQL read model read、Redis cache、API miss enqueue、production requires SQL model。 |
| parent scope aggregation | P0 | `tests/test_cost_statistics_sql_runtime.py` | covered | `active:all` / `all:all` 从 materialized shard rows 聚合，不读 Workbench all payload。 |
| parent waits for shard readiness | P0 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_app_status_overview_service.py` | covered | missing/stale shards 入队，父 scope refreshing；shards converged 后发布 parent fresh。 |
| App Status scope-level semantics | P0 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py` | covered | 父 scope failed blocks；月份 shard failed/unavailable busy；scope details preserved。 |
| warmup job recovery/retry | P1 | `tests/test_cost_statistics_api.py`、`tests/test_import_job_queue.py` | covered | warmup summary、partial retry、interrupted recovery、duplicate running job guard。 |
| 前端页面交互 | P1 | `web/src/test/CostStatisticsPage.test.tsx` | covered | time/project/bank/expense view、drilldown、range picker、empty/error/refreshing、export center。 |
| 前端 API mapper/cache | P1 | `web/src/test/CostStatisticsApi.test.ts` | covered | project scope 透传、read model status mapping、explorer cache keyed by month/scope。 |
| 真实生产 scope cleanup `--apply` | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres 环境，只能按 runbook 只读检查后受控执行。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py` | 覆盖成本归因、项目范围、特殊业务链路、票据/往来排除或保留规则。 |
| 2. Service-layer tests | 适用 | `tests/test_cost_statistics_read_model_service.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_project_costing_api.py` | 覆盖 read model service、runtime service、project costing 写入/查询边界。 |
| 3. API contract tests | 适用 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts` | 覆盖 explorer、month summary、project scope、export/export-preview、错误和 response shape。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_app_status_overview_service.py` | 覆盖 SQL read model、Redis hot cache、scope contract、worker refresh、parent/shard readiness 和 App Status。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/CostStatisticsApi.test.ts` | 覆盖页面状态、范围选择、drilldown、export center、API mapper 和 cache。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | 覆盖导入确认/Workbench invalidation/read model enqueue 到成本统计；真实导入到 worker drain 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 cost statistics tests，加 imports、invoice lifecycle、workbench、turnover、settings/project scope tests 的按改动选择扩展集 | 成本统计受多模块写入影响；任何导入、关系、规则、项目范围或 worker 改动都要问会影响哪些旧成本视图。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 2026-06-10 | 裸月份/裸 `all` scope 进入 durable queue，导致成本统计 worker 报 scope contract 错误并污染 App Status。 | `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | covered |
| 2026-06-10 | `active:all` / `all:all` 父 scope 错误读取 Workbench `all` 大 payload。 | `tests/test_cost_statistics_sql_runtime.py` | covered |
| 2026-06-10 | 父 scope 等待缺失/stale 月份 shard 时被伪造为 fresh。 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_app_status_overview_service.py` | covered |
| 2026-06-12 | Workbench open/proposed candidate 被当成 confirmed relation 计入成本金额。 | `tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_open_candidate_groups_are_excluded_from_cost_statistics`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` | covered |
| 2026-06-13 | 成本税务 projection 直接从 OA 附件 parser cache 拼进项发票输入，绕过统一 Invoice repository。 | `tests/test_tax_offset_service.py::test_month_payload_includes_oa_attachment_invoices_by_issue_month`、`tests/test_tax_offset_api.py::test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata` | covered by shared tax/workbench boundary |
| 长期 | 月份 shard failed 误把整个成本统计主体验标红。 | `tests/test_app_status_overview_service.py` | covered |
| 长期 | SQL read model miss/stale 时 API 同步 rebuild 或返回假 fresh。 | `tests/test_cost_statistics_sql_runtime.py` | covered |
| 长期 | 导出和页面查询没有透传 project scope 或自定义日期范围。 | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` | covered |
| 长期 | 成本统计错误纳入现金代收代付/票据购买/发票抵扣等特殊关系。 | `tests/test_cost_statistics_service.py` | covered |

## 关键 smoke flows

1. `银行/发票/ETC 导入确认 -> lifecycle domain plan -> cost_statistics dirty scope -> cost-statistics worker -> month shard fresh -> parent scope re-enqueue -> all scope fresh -> 页面展示`
2. `Workbench relation confirm/cancel -> cost statistics invalidation -> affected month shard refresh -> App Status busy -> fresh 后恢复`
3. `project scope setting change -> active/all scope refresh -> active view 排除已完成项目 -> all view 保留全部项目`
4. `active:all 父 scope refresh -> 检查 month shard readiness -> 缺失 shard 入队 -> 父 scope refreshing -> shards fresh 后聚合发布`
5. `页面切换 view/date/project scope -> explorer API -> stale/refreshing 保留当前内容或刷新提示 -> fresh 后 drilldown/export`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service tests.test_project_costing_service tests.test_project_costing_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_read_model_service tests.test_cost_statistics_runtime_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v
cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx
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

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest 和 build，覆盖完整成本统计、App Status、read model gateway 和前端测试集。单轮模块验证只跑最小闭环。

## 未测风险

- 本轮不连接真实生产 PostgreSQL 执行 `scripts/check-read-model-scope-contracts.py --apply`；发布前后需先 dry-run JSON 报告，再按 runbook 受控清理。
- 本地测试不跑真实 RabbitMQ/Redis/cost-statistics worker drain；父 scope 与月份 shard 在真实多 worker 环境中的最终收敛需要生产或 staging smoke。
- 前端 Vitest 覆盖交互和 mapper，不覆盖真实大数据量导出耗时、浏览器下载和视觉性能。
