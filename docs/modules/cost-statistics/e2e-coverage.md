# 成本统计 Spec-first E2E Coverage

本文件把 `cost-statistics` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `COST-E2E-001` | `partial` | `web/e2e/cost-statistics-flow.spec.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/CostStatisticsApi.test.ts`、`tests/test_cost_statistics_api.py` | Browser 覆盖首屏按时间和按项目；银行/费用类型更多组合主要由 Vitest/API 覆盖。 |
| `COST-E2E-002` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`tests/test_cost_statistics_api.py` | Browser 已证明 `project_scope=all` 请求和已完成项目展示。 |
| `COST-E2E-003` | `covered` | `web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/src/test/CostStatisticsPage.test.tsx` | Browser 已覆盖项目/费用类型/流水详情下钻，新增 relation fan-out 后的成本流水详情。 |
| `COST-E2E-004` | `partial` | `web/e2e/cost-statistics-flow.spec.ts`、`tests/test_cost_statistics_service.py`、`tests/test_cost_statistics_api.py` | Browser 已覆盖 preview query 和 row-limit 错误反馈；缺真实 download event 和文件字段断言。 |
| `COST-E2E-005` | `covered` | `web/e2e/cost-statistics-relation-fanout.spec.ts`、`tests/test_cost_statistics_service.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_workbench_relation_repository.py` | Browser 已证明 open candidate 不进入成本项目/金额/明细，Workbench confirm 后成本页重新读取并显示 `智能工厂项目`、`58,000.00` 和对应流水详情。 |
| `COST-E2E-006` | `partial` | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsPage.test.tsx` | API/Vitest 覆盖 refreshing/stale/failed；缺 Browser negative 场景。 |
| `COST-E2E-007` | `partial` | `web/e2e/permissions-role-matrix.spec.ts`、`tests/test_auth_guard.py`、`tests/test_cost_statistics_api.py` | 全页面 role matrix 覆盖可读性；成本页暂无写入口，导出权限仍缺真实 download event。 |
| `COST-E2E-008` | `partial` | `web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | 覆盖重复流水 key 和常规浏览器布局；缺大数据/宽表/视觉像素 smoke。 |
| `COST-E2E-009` | `missing` | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts` | 缺真实浏览器 download event 和 XLSX 字段断言。 |
| `COST-E2E-010` | `partial` | `web/e2e/cost-statistics-relation-fanout.spec.ts`、相关 backend lifecycle/read model tests | 已覆盖 Workbench 成本关系 fan-out；导入、settings、turnover/no-OA/ETC 到成本统计仍缺 Browser fan-out。 |

## 下一轮补测建议

1. 为 `COST-E2E-006` 补 Browser refreshing/stale/failed 负面场景。
2. 为 `COST-E2E-009` 补真实下载事件和字段断言。
3. 为 `COST-E2E-010` 补导入、turnover/no-OA/ETC 或项目范围设置到成本统计的 Browser fan-out。
4. 为 `COST-E2E-008` 补大数据宽表/滚动/视觉稳定性 smoke。
