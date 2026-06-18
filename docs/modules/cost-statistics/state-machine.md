# 成本统计状态机

> 修改 `成本统计` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。成本统计使用 scope-level readiness：父 scope 和月份 shard 的状态不能混为一个全局布尔值。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 项目范围 | `active` | app settings project status / cost statistics API query | 默认视图；排除明确已完成项目，未知项目保持 active。 |
| 项目范围 | `all` | app settings project status / cost statistics API query | 用户选择 all project scope 后展示所有项目。 |
| 成本行 | `included` | `CostStatisticsService`、SQL projection payload | 支出流水或可计入成本关系满足项目/费用字段要求后进入统计。 |
| 成本行 | `excluded` | cost attribution policy / relation context | OA 发票抵扣、现金代收代付确认组等不应计入成本的关系被排除。 |
| 月份 shard | `active:YYYY-MM` / `all:YYYY-MM` | `read_model.cost_statistics_rows`、readiness | 由 `cost-statistics` 专用 worker 从对应 Workbench 月份 read model 构建；旧 `cost-tax` 仅作为兼容消费者。 |
| 全期间父 scope | `active:all` / `all:all` | `read_model.cost_statistics_read_models`、readiness | 从已物化月份 shard rows 聚合生成；不读取 Workbench `all` 全量 payload。 |

关键规则：

- 成本统计页面不重新定义项目归因、发票生命周期、银行标签或 relation identity。
- 只有 confirmed/linked 成本关系可以进入金额统计；Workbench open/proposed candidate 只作为候选关系展示事实，不能被 live service 或 SQL projection 计入成本行。
- 合法 read model scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all`。
- 裸月份或裸 `all` 只能通过 `ReadModelRefreshGateway` 归一化后入队；未知 project scope 必须拒绝。
- 月份 shard 成功发布后必须重新入队同 project scope 的父 scope，推动全期间视图收敛。
- 父 scope 等待缺失、stale 或 failed 月份 shard 时只能记录 `refreshing`，不能伪造 `fresh`。

禁止流转：

- 禁止 API 请求线程同步重建 read model 来掩盖缺失或 stale。
- 禁止把月份 shard failed/unavailable 直接解释为整个成本统计主体验 blocked。
- 禁止把父 scope failed/unavailable 降级为普通 busy。
- 禁止手工把 historical failed readiness 改成 fresh；只能由真实成功 rebuild 覆盖。
- 禁止父 scope 读取 Workbench `all` 大 payload 作为全期间统计事实。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 页面首次请求 explorer/month/export preview | 展示加载态；不渲染假数据。 |
| refreshing | API 返回 `read_model_status=refreshing` 或空 202 payload | 保留当前内容或展示刷新提示；不能把空 accepted payload 当最终空结果。 |
| stale | API 返回 stale/schema/source mismatch 或 App Status 显示对应 scope stale | 显示陈旧/刷新语义，等待 worker 收敛。 |
| empty | fresh payload 且 summary row count 为 0 | 只有 fresh 后才代表当前 view/range/project scope 真实无成本数据。 |
| error | explorer/export/detail 请求失败 | 显示错误态；不暴露底层 SQL 或 worker internals。 |
| export loading | export preview/download 进行中 | 弹窗内反馈进度和错误，保留当前页面上下文。 |
| permission disabled/hidden | 当前模块主要为只读/导出 | 若未来增加写操作，必须按 session 权限和 App Status mutation gate 禁用。 |

前端事件：

- `workbenchRelationUpdated`、`bankTransactionCategoryUpdated`、`turnoverRelationUpdated`、`invoiceFactUpdated`、`etcBusinessBatchUpdated` 等事件只能触发页面 refetch 或刷新提示。
- 前端事件不是事实源；后端 dirty scope/outbox/worker/readiness 才证明成本统计已收敛。
- 离开页面后 React tree 卸载，inactive 页面不 replay 事件；返回页面重新通过 API/read boundary 加载。

## Read Model / Worker 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `fresh` | scope schema/source/readiness 与当前事实一致，且没有 active dirty scope | 页面可展示；Redis/hot cache 可缓存该 scope payload。 |
| `missing` | 没有对应 scope readiness 或 read model payload | 入队对应 scope refresh；页面/API 返回 refreshing 或 busy。 |
| `refreshing` | dirty scope pending/processing，或父 scope 正等待 shard | worker 继续处理；父 scope 不能 complete 为 fresh。 |
| `stale` / `source_mismatch` / `schema_mismatch` | source/schema/version 落后 | 入队重建；不得同步 rebuild 伪装 fresh。 |
| `failed` | worker refresh 失败或 readiness 记录失败 | 父 scope failed 阻断成本统计主体验；月份 shard failed 只标记局部 busy/attention。 |
| `unavailable` | repository/queue/worker dependency 不可用 | App Status blocked 或 busy，视父 scope/月 shard 和 dependency 关键性判定。 |

Refresh 触发来源：

- 银行流水、发票、ETC 导入确认。
- Workbench relation 确认/撤回、批量账务、往来款手动闭环。
- 待找发票规则、银行标签、税金认证、发票生命周期变化。
- 项目范围或项目状态设置变化。
- scope contract repair、App Health/backfill 运维任务。
- `startup_stale_scan` 默认关闭，且不直接刷新成本统计 read model；只有后续 matching 结果真实变化并触发业务 lifecycle 时才影响成本。

父 scope 流程：

1. 收到 `active:all` 或 `all:all` refresh。
2. 检查同 project scope 的月份 shard readiness。
3. 缺失、stale 或 failed shard 通过 `ReadModelRefreshGateway` 入队。
4. 父 scope 写/返回 `refreshing`，不写 fake rows，不 complete dirty scope 为 fresh。
5. 所有 shard fresh 后，从 `read_model.cost_statistics_rows` 聚合父 scope snapshot。
6. 原子发布 `read_model.cost_statistics_read_models` 并写父 scope fresh readiness。

失败恢复：

1. 先看 `/api/app-health.app_status` 中 `cost_statistics.read_model_scopes[]`，区分父 scope 和月份 shard。
2. 对 legacy/invalid scope，先运行 `scripts/check-read-model-scope-contracts.py --json`，确认后再按 runbook `--apply`。
3. 对月份 shard failed，重跑对应 `active:YYYY-MM` 或 `all:YYYY-MM`；不要手工改父 scope。
4. 对父 scope failed/unavailable，确认所有月份 shard readiness 后重跑 `active:all` 或 `all:all`。
5. 若是 Redis/hot cache 问题，清 cache 后仍必须通过 SQL/readiness fresh gate，不得缓存 stale payload。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-18 | Browser e2e 补齐 Workbench 成本关系 fan-out | 真实 Chromium 证明 open/proposed candidate 不进入成本项目、金额或明细；确认 OA+bank+invoice 成本关系后，成本页重新读取并展示对应项目、金额、流水和详情；不改变业务/read model 状态机 | `cd web && npx playwright test e2e/cost-statistics-relation-fanout.spec.ts` |
| 2026-06-17 | Browser e2e 补齐项目下钻与导出错误反馈闭环 | 真实 Chromium 保护按时间首屏、按项目视图、`project_scope=all`、项目/费用类型/流水详情下钻、导出 preview 和 row-limit 错误反馈；不改变业务/read model 状态机 | `cd web && npx playwright test e2e/cost-statistics-flow.spec.ts` |
| 2026-06-12 | Workbench candidate 关系不再计入成本统计 | live 成本查询、cost statistics SQL projection、月份 shard rows | `tests.test_cost_statistics_service`、`tests.test_cost_statistics_sql_runtime` |
| 2026-06-11 | 补齐测试闭环状态机 | 业务归因、UI、父 scope、月份 shard、App Status 和 worker 状态边界 | `tests.test_cost_statistics_service`、`tests.test_project_costing_service`、`tests.test_project_costing_api`、`tests.test_cost_statistics_api`、`tests.test_cost_statistics_read_model_service`、`tests.test_cost_statistics_runtime_service`、`tests.test_cost_statistics_sql_runtime`、`tests.test_read_model_refresh_gateway`、`tests.test_runtime_worker_read_model_refresh_scopes`、`tests.test_read_model_scope_contract`、`tests.test_app_status_overview_service`、`tests.test_runtime_monitoring`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` |
| 2026-06-10 | 成本统计 scope contract 修复 | 裸月份/裸 `all` 只能经 gateway 归一化，非法 scope 拒绝 | `tests.test_read_model_refresh_gateway`、`tests.test_runtime_worker_read_model_refresh_scopes`、`tests.test_read_model_scope_contract` |
