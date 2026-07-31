# 成本统计验收覆盖

| ID | 状态 | 自动化证据 |
| --- | --- | --- |
| `COST-E2E-001` | covered | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_projection_rules.py` |
| `COST-E2E-002` | covered | `tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_next_request_observes_relation_withdrawal_without_refresh_job`、写操作影响矩阵测试 |
| `COST-E2E-003` | covered | `tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_project_view_and_detail_use_the_same_active_relation` |
| `COST-E2E-004` | covered | `tests/test_cost_statistics_api.py`、`web/src/test/CostStatisticsApi.test.ts` |
| `COST-E2E-005` | covered | `web/src/test/CostStatisticsPage.test.tsx` |
| `COST-E2E-006` | covered | `tests/test_platform_runtime_boundary_guards.py`、registry/manifest/deploy 回归 |
| `COST-E2E-007` | local-covered / production-measure | 本地 API budget 测试；发布后记录生产多次请求分布 |
| `COST-E2E-008` | covered | `tests/test_cost_statistics_policy.py::CostStatisticsPolicyTests::test_daily_reimbursement_splits_by_canonical_expense_items`、`tests/test_cost_statistics_api.py` |
| `COST-E2E-009` | covered | `tests/test_cost_statistics_policy.py::CostStatisticsPolicyTests::test_daily_reimbursement_invalid_items_fail_closed`、`tests/test_cost_statistics_policy.py::CostStatisticsPolicyTests::test_projection_does_not_split_multiple_bank_rows` |

本轮不运行 183 个浏览器测试。候选门禁使用成本统计后端/API/Audit/边界测试、34 个前端定向测试和生产 build；真实正确性与性能由一次部署后的集中生产验证补齐。
