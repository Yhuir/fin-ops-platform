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
| `COST-E2E-008` | covered | `tests/test_cost_statistics_policy.py` 的关系净支出两级比例、多支出多账户、最大余数按分闭合、OA mismatch 方向与详情合同；`tests/test_cost_statistics_api.py` |
| `COST-E2E-009` | covered | `tests/test_cost_statistics_policy.py` 的同关系付错退款/普通收入隔离、无退款归因行与原始流水不变；`tests/test_cost_statistics_api.py` 的 explorer/detail contract；`web/src/test/CostEntryDetailPanel.test.tsx` 的负数退款证据 |
| `COST-E2E-010` | covered | `tests/test_cost_statistics_policy.py` 的进行中关系只从归因集合排除与银行日期；`tests/test_cost_statistics_api.py` 的原始流水/归因集合隔离 |
| `COST-E2E-011` | covered | `tests/test_cost_statistics_policy.py` 的零权重保护与 duplicate ownership；`tests/test_cost_statistics_api.py` 的冲突合同 |
| `COST-E2E-012` | covered | `tests/test_cost_statistics_api.py` 的真实候选、默认空、多项目保存、互斥校验及同标签有/无 OA 逐笔隔离；`tests/test_app_settings_service.py`；前端抽屉组件测试 |
| `COST-E2E-013` | covered / production-measure | `tests/test_mongo_oa_adapter.py` 的 form-specific 字段；发布后以 OA v8 同步和生产有效源字段恢复量补证 |
| `COST-E2E-014` | covered | `tests/test_cost_statistics_api.py` 的默认 all/custom 空选择与旧 endpoint 404；`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` 的两套规则互不影响 |
| `COST-E2E-015` | covered | `tests/test_cost_statistics_canonical_repository.py` 的全关系银行证据/声明 OA 成员；`tests/test_cost_statistics_policy.py` 的跨月退款与 partial OA fail-closed |

候选门禁使用成本统计后端/API/Audit/边界测试、前端定向测试和生产 build；真实正确性、抽屉视觉与性能由部署后的集中生产验证补齐。
