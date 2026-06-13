# 成本统计 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 成本统计 read model refresh scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`；旧裸月份/裸 `all` 必须在统一 read model refresh gateway 中归一化，不能直接进入 durable queue。
- 生产库中已有的成本统计 legacy/invalid runtime scope 通过 `scripts/check-read-model-scope-contracts.py` 检查；`--apply` 删除旧状态，并补投可归一化的规范 replacement scope。
- 成本税务 projection 中的发票输入必须来自 canonical invoice facts；OA 附件正式发票先 promotion 到 Invoice repository / `app.invoices`，不能从 `app.oa_attachment_invoice_cache` 直接拼计划或成本税务输入项。
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
- 未测风险：未在真实生产数据库执行 `scripts/check-read-model-scope-contracts.py --apply`；未跑真实 RabbitMQ/Redis/cost-tax worker drain；未做大数据量导出和真实浏览器下载 smoke。
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
