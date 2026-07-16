# 成本统计 Spec-first E2E Coverage

本文件把 `cost-statistics` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

2026-07-13 增量：`COST-E2E-001` 已增加真实 Browser 的按时间/按标签收支分列金额、收入流水和收入标签断言；`COST-E2E-004` / `COST-E2E-009` 由 Browser、Vitest 与后端 API 共同覆盖 time/bank_tag 的资金方向、收入流水、方向摘要和 XLSX 标签列。下表旧描述中的“全银行支出”统一按当前产品合同解释为“全银行收入与支出”。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `COST-E2E-001` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/CostStatisticsApi.test.ts`、`tests/test_cost_statistics_api.py` | Browser 覆盖 fresh 首屏按时间、按项目、按银行和按 OA 费用类型 baseline；按银行/按 OA 费用类型用真实 Chromium 进入对应视图、选择银行账户/费用类型、展示后端 explorer 成本行并打开流水详情；按项目/按银行/按 OA 费用类型/按标签视图切换和时间范围切换已记录 operation latency。更多银行/费用类型组合由 Vitest/API 覆盖，真实生产大数据性能仍归 staging 风险；成本统计标签规则抽屉等待 fresh 的交互由 Vitest 覆盖，真实 Browser 写流待下一轮有基础设施时补。 |
| `COST-E2E-002` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts`、`tests/test_cost_statistics_api.py` | Browser 已证明页面固定 active project scope、已完成项目不在页面展示且项目范围切换 UI 不出现；后端 API tests 保留 `project_scope=all` 合同。 |
| `COST-E2E-003` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/src/test/CostStatisticsPage.test.tsx` | Browser 已覆盖项目/费用类型/流水详情下钻，新增 relation fan-out 后的成本流水详情；项目/费用类型下钻、打开流水详情和关闭详情已记录 operation latency。 |
| `COST-E2E-004` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`tests/test_cost_statistics_sql_projection_rules.py`、`tests/test_cost_statistics_api.py` | Browser 已覆盖 preview query、成功 download event 和 row-limit 错误反馈；导出中心打开、仅预览、导出成功和 row-limit 错误已记录 operation latency。 |
| `COST-E2E-005` | `covered` | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_sql_projection_rules.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_workbench_relation_repository.py` | Browser 已证明 open candidate 不进入成本项目/金额/明细，Workbench confirm 后成本页重新读取并显示 `智能工厂项目`、`58,000.00` 和对应流水详情。 |
| `COST-E2E-006` | `covered` | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | Browser 已覆盖 explorer 暂时 503 时显示“成本统计数据加载暂时失败，请刷新后重试。”、不显示最终空态、不渲染表格、禁用导出中心，并在点击刷新后恢复 fresh 成本行；也覆盖 explorer `refreshing` / `stale` / `failed` payload 不显示最终空态、不泄露旧项目行、不渲染旧 summary card、禁用导出入口，以及 fresh explorer 下 transaction detail 返回 non-fresh 时不打开旧详情、export-preview/export 返回 non-fresh 时显示刷新错误、不渲染导出预览表、不触发 download。API/Vitest/SQL runtime 覆盖真实 read boundary、cache、payload shape 和 enqueue contract；真实 worker drain 仍归 infra-smoke/staging。 |
| `COST-E2E-007` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`tests/test_auth_guard.py`、`tests/test_cost_statistics_api.py` | 全页面 role matrix 覆盖可读性；页面级高风险权限面是 read/export 和成本统计标签规则保存。Browser 已证明 `read_export_only` 可打开导出中心并下载当前 time-view 成本行；`PUT /api/cost-statistics/tag-rules` 缺少写权限时由 API contract 断言拒绝且不调用 settings service；API 标记规则只读时前端禁用保存按钮。真实浏览器按钮级写权限矩阵待下一轮权限 e2e 扩展。 |
| `COST-E2E-008` | `covered` | `web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | 覆盖重复流水 key、常规浏览器布局，以及真实 Chromium 390px 窄屏下 120+ 成本行的 fresh explorer、按时间表/项目下钻表纵横滚动、右侧列 viewport 可见、导出入口/项目/费用类型选择器无遮挡和无浏览器错误；真实生产超大数据性能仍为 staging 风险。 |
| `COST-E2E-009` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts` | Browser 已覆盖 `read_export_only` 下 time-view export-preview/export 请求携带 `view=time`、`month=2026-03`、`project_scope=active` 且不带分页，真实 download event 产生 `成本统计_全部期间_按时间统计.xlsx`，下载内容包含流水 ID、项目、费用类型、费用内容、对方户名和筛选字段；time-view 导出预览和下载已记录 operation latency；真实生产 XLSX workbook 解析/打开属于 staging/manual 风险，不阻塞本地 Spec-first Browser 闭环。 |
| `COST-E2E-010` | `covered` | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/e2e/imports-invoices-flow.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts`、相关 backend lifecycle/read model tests | 已覆盖 Workbench 成本关系 fan-out；银行流水导入、发票导入和 ETC 导入 confirm 后各自模块 Browser 进入成本统计并断言成本统计 read model fresh 或下游影响行；bank-flow selected-row submit 后 Browser 进入成本统计并断言 fresh explorer、流水规则手续费成本项目、费用类型和流水表字段；外部往来手动闭环 confirm 后 Browser 进入成本统计并断言 fresh explorer、外部往来闭环成本项目、费用类型和流水表字段，再回到外部往来完成撤回；settings 项目标记完成并保存后 Browser 进入成本统计并断言 active scope 排除该项目且项目范围切换 UI 不出现。search 当前无独立前端 route，由 relation/search API/runtime 证据覆盖；真实 worker drain、真实导入样本和生产 scope cleanup 仍为 staging/infra 风险。 |

## 下一轮补测建议

1. 有真实基础设施 env 时，补成本统计 write-operation / worker drain staging smoke。
2. 发布前用真实后端 XLSX workbook 做一次打开/字段 smoke。
3. 新增独立 search Browser route、成本页写入口或更多真实导入模板时，按对应功能追加 Browser E2E。
