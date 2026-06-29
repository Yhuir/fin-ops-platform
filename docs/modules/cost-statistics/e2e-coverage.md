# 成本统计 Spec-first E2E Coverage

本文件把 `cost-statistics` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `COST-E2E-001` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/CostStatisticsApi.test.ts`、`tests/test_cost_statistics_api.py` | Browser 覆盖 fresh 首屏按时间、按项目、按银行和按费用类型 baseline；按银行/按费用类型用真实 Chromium 进入对应视图、选择银行账户/费用类型、展示后端 explorer 成本行并打开流水详情。更多银行/费用类型组合由 Vitest/API 覆盖，真实生产大数据性能仍归 staging 风险。 |
| `COST-E2E-002` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`tests/test_cost_statistics_api.py` | Browser 已证明 `project_scope=all` 请求和已完成项目展示。 |
| `COST-E2E-003` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/src/test/CostStatisticsPage.test.tsx` | Browser 已覆盖项目/费用类型/流水详情下钻，新增 relation fan-out 后的成本流水详情。 |
| `COST-E2E-004` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`tests/test_cost_statistics_service.py`、`tests/test_cost_statistics_api.py` | Browser 已覆盖 preview query、成功 download event 和 row-limit 错误反馈。 |
| `COST-E2E-005` | `covered` | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_service.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_workbench_relation_repository.py` | Browser 已证明 open candidate 不进入成本项目/金额/明细，Workbench confirm 后成本页重新读取并显示 `智能工厂项目`、`58,000.00` 和对应流水详情。 |
| `COST-E2E-006` | `covered` | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | Browser 已覆盖 explorer 暂时 503 时显示“成本统计数据加载暂时失败，请刷新后重试。”、不显示最终空态、不渲染表格、禁用导出中心，并在点击刷新后恢复 fresh 成本行；也覆盖 explorer `refreshing` / `stale` / `failed` payload 不显示最终空态、不泄露旧项目行、summary card 不伪装 0 条 fresh 数据、禁用导出入口，以及 fresh explorer 下 transaction detail 返回 non-fresh 时不打开旧详情、export-preview/export 返回 non-fresh 时显示刷新错误、不渲染导出预览表、不触发 download。API/Vitest/SQL runtime 覆盖真实 read boundary、cache、payload shape 和 enqueue contract；真实 worker drain 仍归 infra-smoke/staging。 |
| `COST-E2E-007` | `covered` | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`tests/test_auth_guard.py`、`tests/test_cost_statistics_api.py` | 全页面 role matrix 覆盖可读性；成本页暂无写入口，页面级高风险权限面是 read/export。Browser 已证明 `read_export_only` 可打开导出中心并下载当前 time-view 成本行；forbidden/expired/API auth 由全局权限和 API contract 覆盖。每按钮写权限矩阵对成本页不适用，新增写入口时再补。 |
| `COST-E2E-008` | `covered` | `web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | 覆盖重复流水 key、常规浏览器布局，以及真实 Chromium 390px 窄屏下 120+ 成本行的 fresh explorer、按时间表/项目下钻表纵横滚动、右侧列 viewport 可见、导出入口/项目/费用类型选择器无遮挡和无浏览器错误；真实生产超大数据性能仍为 staging 风险。 |
| `COST-E2E-009` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts` | Browser 已覆盖 `read_export_only` 下 time-view export-preview/export 请求携带 `view=time`、`month=2026-03`、`project_scope=active` 且不带分页，真实 download event 产生 `成本统计_全部期间_按时间统计.xlsx`，下载内容包含流水 ID、项目、费用类型、费用内容、对方户名和筛选字段；真实生产 XLSX workbook 解析/打开属于 staging/manual 风险，不阻塞本地 Spec-first Browser 闭环。 |
| `COST-E2E-010` | `covered` | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/e2e/imports-invoices-flow.spec.ts`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/settings-data-reset-flow.spec.ts`、相关 backend lifecycle/read model tests | 已覆盖 Workbench 成本关系 fan-out；银行流水导入、发票导入和 ETC 导入 confirm 后各自模块 Browser 进入成本统计并断言成本统计 read model fresh 或下游影响行；no-OA 手续费批次 submit 后 Browser 进入成本统计并断言 fresh explorer、免 OA 成本项目、费用类型和流水表字段；外部往来手动闭环 confirm 后 Browser 进入成本统计并断言 fresh explorer、外部往来闭环成本项目、费用类型和流水表字段，再回到外部往来完成撤回；settings 项目标记完成并保存后 Browser 进入成本统计并断言 active scope 排除该项目、all scope 保留该项目且 explorer 为 fresh。search 当前无独立前端 route，由 relation/search API/runtime 证据覆盖；真实 worker drain、真实导入样本和生产 scope cleanup 仍为 staging/infra 风险。 |

## 下一轮补测建议

1. 有真实基础设施 env 时，补成本统计 write-operation / worker drain staging smoke。
2. 发布前用真实后端 XLSX workbook 做一次打开/字段 smoke。
3. 新增独立 search Browser route、成本页写入口或更多真实导入模板时，按对应功能追加 Browser E2E。
