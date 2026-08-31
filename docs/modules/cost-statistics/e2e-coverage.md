# 成本统计验收覆盖

| ID | 状态 | 自动化证据 |
| --- | --- | --- |
| `COST-E2E-001` | covered | `tests/test_cost_statistics_policy.py`、`tests/test_cost_statistics_api.py` 三视图根汇总对账 |
| `COST-E2E-002` | covered | policy/API 定向测试；`CostStatisticsPage.test.tsx`；`cost-statistics-flow.spec.ts` |
| `COST-E2E-003` | covered | API mapper、组件与浏览器费用类型下钻测试 |
| `COST-E2E-004` | covered | bank_account API 合同、组件与浏览器账户→项目→明细测试 |
| `COST-E2E-005` | covered | policy 单一/缺失/多账户/退款忽略/无 OA 账户测试 |
| `COST-E2E-006` | covered | policy 与 manual-allocation API 的自动/人工/金额/完整性测试 |
| `COST-E2E-007` | covered | no-OA policy/settings/API 测试及浏览器保存后刷新测试 |
| `COST-E2E-008` | covered | policy 的 4200 支出/2100 收入/2100 净支出合同；API、前端 mapper、组件和真实 Chromium 标签下钻 |
| `COST-E2E-009` | covered | 五种 preview/download 的 API、前端 mapper、组件和浏览器预览测试 |
| `COST-E2E-010` | covered | API 错误/权限测试、组件错误恢复和只读权限测试、权限矩阵 |
| `COST-E2E-011` | covered | 跨模块 E2E 与 runtime boundary tests；发布后 runtime smoke 补证 |
| `COST-E2E-012` | covered | API 负面测试、旧 `bank` 400、旧 route 404、源码全仓扫描和前端旧规则 UI 不存在测试 |
| `COST-E2E-013` | local-covered / production-measure | repository 查询预算、本地 API budget、`http_slo_probe`；发布后记录五视图生产分位数 |

生产性能与真实数据抽样在每次改变成本人口或查询链后重新执行；本地 mock 结果不能替代生产证据。
