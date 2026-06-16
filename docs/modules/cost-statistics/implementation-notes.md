# 成本统计 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 成本统计 read model refresh scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`；旧裸月份/裸 `all` 必须在统一 read model refresh gateway 中归一化，不能直接进入 durable queue。
- 生产库中已有的成本统计 legacy/invalid runtime scope 通过 `scripts/check-read-model-scope-contracts.py` 检查；`--apply` 删除旧状态，并补投可归一化的规范 replacement scope。
- 成本税务 projection 中的发票输入必须来自 canonical invoice facts；OA 附件正式发票先 promotion 到 Invoice repository / `app.invoices`，不能从 `app.oa_attachment_invoice_cache` 直接拼计划或成本税务输入项。
- 成本统计 export-preview/export 是同步生成路径；time、month、project、expense_type 导出超过 20,000 行时必须返回 `cost_statistics_export_row_limit_exceeded`，不能继续生成大预览或 XLSX。
- 2026-06-11 测试闭环审计确认：现有 P0/P1 覆盖成本归因、API/导出、SQL read model、parent/shard readiness、scope gateway、App Status 和前端交互；本轮不新增重复代码测试，主要补齐模块测试矩阵和状态机文档。

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

## 2026-06-16 - 成本统计导出错误反馈闭环

- 目标：确保成本统计同步导出被后端行数上限拒绝时，前端下载路径解析结构化错误并在导出中心展示具体原因。
- 影响范围：`web/src/features/cost-statistics/api.ts`、`web/src/pages/CostStatisticsPage.tsx`、成本统计前端 API/page 测试和 P2/P3 闭环台账。
- 关键决策：非 2xx 下载响应先读取 `message` / nested `error.message` / `error`，HTML fallback 仍按代理配置错误处理；页面导出和预览 catch 保留后端消息，不再统一覆盖成泛化失败。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；长期产品/API 文档不变。
- 测试覆盖：新增 `web/src/test/CostStatisticsApi.test.ts::surfaces backend row-limit messages from failed export downloads`；新增 `web/src/test/CostStatisticsPage.test.tsx::shows backend export failure messages inside the export center`。
- 验证命令：`npm run test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx src/test/TurnoverLedgerApi.test.ts src/test/PendingInvoicesApi.test.ts`。
- 未测风险：真实浏览器下载、代理错误页面、生产网络中断和大文件打开仍需 staging/manual smoke。
- 后续事项：如业务需要超过 20,000 行导出，应改异步导出任务并补任务进度/下载链接闭环。

## 2026-06-16 - P2/P3 成本统计同步导出上限

- 目标：收敛成本统计 time/project/expense_type 大数据 export-preview/export 的同步生成风险，避免大匹配集继续构造预览 rows 或 XLSX。
- 影响范围：`CostStatisticsService`、`CostStatisticsApiRoutes`、成本统计 service/API 测试、模块测试矩阵和 P2/P3 闭环台账。
- 关键决策：导出上限为 20,000 行；超过上限返回 `cost_statistics_export_row_limit_exceeded`，details 包含 `view`、`total` 和 `limit`。transaction 单笔详情不使用该上限。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；产品/API 长期文档未扩展，因为这是性能保护边界。
- 测试覆盖：新增 `tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_export_preview_and_download_reject_large_time_export_before_workbook_generation`；新增 `tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_cost_statistics_export_limit_returns_structured_error`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service.CostStatisticsServiceTests.test_export_preview_and_download_reject_large_time_export_before_workbook_generation tests.test_cost_statistics_api.CostStatisticsApiTests.test_cost_statistics_export_limit_returns_structured_error -v`。
- 未测风险：真实 PostgreSQL EXPLAIN、生产数据分布、浏览器下载/打开文件和视觉性能仍需 staging/manual smoke；本地只证明超大匹配集不会继续同步生成预览或 XLSX。
- 后续事项：继续执行 authenticated HTTP/SSE/read model final gate；若真实用户需要超过 20,000 行导出，应另设异步导出任务而不是放宽同步路径。

## 2026-06-16 - P2/P3 首屏 SLO 与父 scope 有界聚合证据

- 目标：复核成本统计在 P2/P3 一秒级推进中的真实性能护栏，避免把该页误按普通 rows 分页列表处理。
- 影响范围：`tests/test_http_slo_probe.py`、成本统计测试矩阵和 P2/P3 闭环台账；未改变成本统计业务代码、API contract 或页面行为。
- 关键决策：成本统计页面首屏事实源是 explorer/summary 聚合 read model，不是可追加 `page_size` 的 rows 列表；本地证据应锁定认证态 SLO 探针覆盖 `/api/cost-statistics/explorer` 与 `/api/cost-statistics`，并复用 SQL runtime 中父 scope 从已物化月份 shard 聚合、不读 Workbench 全量 payload 的测试。
- 文档影响：更新 `tests.md` 和本实施记录；长期产品/API 文档不变。
- 测试覆盖：更新 `tests/test_http_slo_probe.py::HttpSloProbeTests::test_default_probes_cover_page_domains_and_known_slow_endpoints`，显式断言成本统计 explorer/summary 默认探针；沿用 `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe.HttpSloProbeTests.test_default_probes_cover_page_domains_and_known_slow_endpoints -v`。
- 未测风险：未连接真实 PostgreSQL 执行 EXPLAIN、pg_stat 或生产旧 scope `--apply`；真实登录态 p95/p99、worker drain、导出耗时和浏览器下载仍需 staging/生产 smoke。
- 后续事项：生产 scope contract repair 获批后，复跑认证态 HTTP SLO 和 cost-statistics App Status。

## 2026-06-16 - 外部往来 Postgres 写路径补齐成本统计 scope contract

- 目标：补齐 `turnover_relation_changed` 下游对成本统计的事务内入队 contract，避免再次产生裸月份/裸 `all` 的 `cost_statistics.read_model.refresh`。
- 影响范围：外部往来确认/撤回后的成本统计 dirty scope、outbox、readiness，以及生产 scope contract repair。
- 关键决策：成本统计 canonical scope 仍只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all`；事务入队路径在写入 durable queue 前归一化，不改变 worker projection contract。
- 文档影响：更新成本统计、read-models、turnover-ledger 和 P2/P3 closure ledger。
- 测试覆盖：新增 turnover Postgres dirty outbox writer 回归；保留 `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` 的成本统计 scope policy/repair 覆盖。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`。
- 未测风险：生产现存 legacy rows 只完成 dry-run 取证，未执行 `--apply`；一秒级 worker drain 需在发布和 cleanup 后复测。
- 后续事项：批准后执行 production scope contract repair，再复查 cost-statistics App Status 和 write-operation SLO。

## 2026-06-13 - 成本税务发票输入收敛到 canonical invoice facts

- 目标：删除成本税务 SQL projection 直接读取 `app.oa_attachment_invoice_cache` 拼进项计划项的旁路，跟随统一 Invoice repository 事实源。
- 影响范围：`CostTaxSqlProjectionBuilder._build_tax_payload`、税金抵扣服务共享发票读取链路、Workbench OA 附件发票 promotion。
- 关键决策：`app.oa_attachment_invoice_cache` 继续作为 OA 附件 parser cache 和运维审计对象，但不作为成本税务 read model 的正式发票输入。OA 附件正式发票进入 `app.invoices` 后由 `_invoice_items(..., output=False)` 统一读取。
- 文档影响：更新本模块记录，并同步 Workbench/Tax Offset 记录。
- 测试覆盖：通过 `tests/test_tax_offset_service.py`、`tests/test_tax_offset_api.py` 和 Workbench canonical projection tests 间接覆盖；本模块未新增重复成本统计专测。
- 验证命令：见本轮最终执行记录。
- 未测风险：未跑完整成本统计 API/SQL 回归；若后续修改成本归因或 projection scope，应按本模块测试矩阵补跑最小闭环。

## 2026-06-11 - 成本统计测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `cost-statistics` 模块轮次，确认新功能改动不会绕过成本归因、read model freshness、App Status 或页面交互回归保护。
- 影响范围：`docs/modules/cost-statistics/tests.md`、`docs/modules/cost-statistics/state-machine.md`、`docs/modules/cost-statistics/implementation-notes.md`；未改变业务代码或测试代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖成本归因规则、项目范围、API 契约、导出 shape、SQL read model、`active/all` parent 与 month shard readiness、scope gateway、worker/App Status 语义和前端 loading/empty/error/refreshing/stale 交互；本轮不新增重复测试。
- 文档影响：补齐七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py`、`tests/test_project_costing_api.py`、`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_read_model_service.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service tests.test_project_costing_service tests.test_project_costing_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_read_model_service tests.test_cost_statistics_runtime_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v`；`cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx`。
- 未测风险：未在真实生产数据库执行 `scripts/check-read-model-scope-contracts.py --apply`；未跑真实 RabbitMQ/Redis/cost-statistics worker drain；未做大数据量导出和真实浏览器下载 smoke。
- 后续事项：下一轮处理 `tax-offset`，重点审计税金认证导入、ETC、invoice lifecycle 与成本税务共享链路。

## 2026-06-10 - 成本统计生产旧 scope 检查与清理

- 目标：清理历史 `2026-03`、`2026-04`、裸 `all` 或未知 project scope 造成的成本统计 App Status readiness、dirty scope 和 dead-letter/outbox 污染。
- 影响范围：`read_model.app_status_readiness`、`job.read_model_dirty_scopes`、`job.outbox_events` 中 `cost_statistics` 相关旧状态。
- 关键决策：只删除当前 scope policy registry 不认为是 canonical 的成本统计状态；legacy scope 会通过 gateway 补投 `active/all` replacement scope，invalid scope 不猜测含义。
- 文档影响：更新成本统计测试矩阵和 runtime worker 运维 runbook。
- 测试覆盖：`tests/test_read_model_scope_contract.py` 覆盖检查、删除和 replacement enqueue 去重。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`。
- 未测风险：未在真实生产数据库执行 `--apply`。
- 后续事项：无。

## 2026-06-10 - 成本统计 read model refresh scope contract

- 目标：阻止裸月份/裸 `all` 作为 `cost_statistics.read_model.refresh` scope 进入 durable queue，避免 SQL projection 报 `scope_key must use project_scope:month` 并污染 App Status readiness。
- 影响范围：成本统计 read model refresh 入队 contract、worker lifecycle 触发链路。
- 关键决策：合法成本统计 scope 统一为 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`。旧裸月份/裸 `all` 只允许在统一 gateway 中归一化；未知 project scope 直接拒绝。
- 文档影响：更新成本统计、read-models、runtime-workers 模块入口和测试矩阵。
- 测试覆盖：`tests/test_read_model_refresh_gateway.py` 覆盖成本统计 policy，`tests/test_runtime_worker_read_model_refresh_scopes.py` 覆盖 worker lifecycle。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes -v`。
- 未测风险：阶段 1 未执行真实生产库清理。
- 后续事项：已由后续 scope contract 检查/清理入口补齐。
