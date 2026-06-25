# 成本统计模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：成本统计页面读取 `cost_statistics` read model，经 query gateway 暴露 parent rollup fresh 状态。
- 当前缺口：模块 README 只登记了前端入口，后端 route/service/read model 文件已在本文件补齐。
- 旧代码删除条件：旧成本统计 service 查询不再绕过 read model query gateway。

## 职责边界

### 负责

- 成本统计页面汇总、筛选、父聚合和明细读取。
- `cost_statistics` read model 的 parent rollup 投影。
- 与税金抵扣共享 cost/tax 投影 worker 时保持明确 event/scope。

### 不负责

- 不拥有税金抵扣业务状态。
- 不直接处理发票导入和 ETC 源事实。
- 不把 `all` 当成无界重建入口；`all` 是 queryable parent aggregate 合同。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面筛选/月份/父级聚合查询 | `CostStatisticsPage.tsx`、`features/cost-statistics/api.ts` | 进入成本统计 API/query service |
| Refresh scope | `cost_statistics` manifest | active/all month + parent aggregate |
| 关系变更 | workbench relation/downstream lifecycle | 转换为受影响 cost_statistics scopes |
| 导入确认 | import processing service/job result | 返回规范化后的 cost_statistics operation barrier targets，月份输入经 scope policy 展开为 active/all shards 与 parent aggregate |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 成本统计 rows/summary | 前端页面 | query gateway 后返回 freshness |
| Parent rollup | read model repository | scoped parent aggregate |
| Dirty scope | runtime queue | fan-out 到必要 parent/month scopes |
| Write target visibility | 导入/关系写 API | 上游写操作必须显式透出 `cost_statistics` targets，成本统计页面自身保持纯读面 |

## 持久化与投影

- Read model：`cost_statistics`
- Projection：`partitioned_scoped_parent_rollup`
- `all` 语义：`queryable_parent_aggregate`
- Worker：`cost-statistics`，辅助 `cost-tax`
- Query owner：`CostStatisticsQueryService`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/CostStatisticsPage.tsx` |
| Frontend components | `web/src/components/cost-statistics/*`、`web/src/features/cost-statistics/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Backend service | `cost_statistics_query_service.py`、`cost_statistics_runtime_service.py`、`cost_statistics_service.py`、`cost_statistics_read_model_service.py` |
| Repository / SQL | `cost_statistics_read_model_repository.py`、`cost_tax_sql_projection.py` |
| Worker/read model | `cost_statistics_read_model_refresh.py`、`cost_statistics_derived_lifecycle_executor.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_cost_statistics*.py`、`web/src/test/CostStatistics*.test.*`、`web/e2e/cost-statistics-*.spec.ts` |

## 依赖方向

- 允许依赖：workbench relation read model、cost/tax projection, query gateway。
- 必须通过：CostStatisticsQueryService 和 read model query gateway。
- 禁止绕过：页面/API 直接扫描源表伪装 fresh；把税金抵扣状态写入成本统计模块。

## 测试与验证

- `tests/test_cost_statistics_sql_runtime.py`
- `tests/test_cost_statistics_api.py`
- `tests/test_cost_statistics_runtime_service.py`
- `tests/test_import_processing_service.py`
- `web/e2e/cost-statistics-flow.spec.ts`
- `web/e2e/cost-statistics-relation-fanout.spec.ts`

## 当前缺口和删除条件

- 将后端 read model 文件范围同步回模块 README。
- 删除旧查询路径前必须验证 parent rollup、relation/import fan-out、fresh/stale UI。
- 成本统计页面无直接写 API；若新增设置或来源修正写入口，必须返回 cost_statistics operation barrier targets，不能只依赖页面刷新兜底。
