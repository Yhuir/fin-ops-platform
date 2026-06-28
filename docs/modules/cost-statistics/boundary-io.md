# 成本统计模块边界与 I/O

日期：2026-06-28

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：成本统计页面通过 direct API 读取 explorer、summary、export-preview 和 export；页面不消费 `cost_statistics` 旧同步诊断字段。
- 当前缺口：旧 cost/tax SQL projection 已删除；历史 read_model 表、迁移和少量 storage cleanup 仍需后续清理。
- 旧代码删除条件：页面级旧同步状态、export gate、legacy mapper 和 cost/tax SQL projection 已清零；后续删除历史表/迁移前保留 direct API、relation/import fan-out 和导出回归。

## 职责边界

### 负责

- 成本统计页面汇总、筛选、父聚合和明细读取。
- direct API explorer、summary、export-preview 和 export 合同。
- 历史 `cost_statistics` SQL snapshot 表的受控清理；页面不得依赖其旧同步状态。

### 不负责

- 不拥有税金抵扣业务状态。
- 不直接处理发票导入和 ETC 源事实。
- 不把 `all` 当成无界重建入口；`all` 是 queryable parent aggregate 合同。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面筛选/月份/父级聚合查询 | `CostStatisticsPage.tsx`、`features/cost-statistics/api.ts` | 直接请求成本统计 API；后端 route/query service 返回 direct payload，不返回旧同步字段 |
| Cache warmup scope | derived lifecycle / runtime service | affected months 或 `all`；不投递旧成本统计刷新事件 |
| 关系变更 | workbench relation/downstream lifecycle | 转换为受影响 cost_statistics scopes |
| 导入确认 | import processing service/job result | 返回规范化后的 cost_statistics affected scopes/job diagnostics，月份输入经 scope policy 展开为 active/all shards 与 parent aggregate |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 成本统计 rows/summary/export-preview/export | 前端页面 | direct API payload；页面展示 loading/error/empty/table/export，不展示旧同步状态 |
| Historical SQL snapshot tables | migration/cleanup only | 不作为页面可读证明，不再由 cost/tax projection 写入 |
| Cache warmup | background job/cache runtime | best-effort；不作为页面 gate |
| Affected scope visibility | 导入/关系写 API | 上游写操作必须显式透出 `cost_statistics` affected scopes/job diagnostics，成本统计页面自身保持纯读面 |

## 持久化与投影

- Page projection：无当前页面 projection；历史表待清理
- Projection：无当前 cost/tax SQL projection
- `all` 语义：`queryable_parent_aggregate`
- Worker：无成本统计页面派生 worker；`cost-statistics` / `cost-tax` lane 已下线
- Query owner：`CostStatisticsQueryService`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/CostStatisticsPage.tsx` |
| Frontend components | `web/src/components/cost-statistics/*`、`web/src/features/cost-statistics/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Backend service | `cost_statistics_query_service.py`、`cost_statistics_runtime_service.py`、`cost_statistics_service.py` |
| Repository / SQL | 无当前 cost/tax projection；历史 read_model 表仅在迁移/cleanup 中处理 |
| Runtime/cache | `cost_statistics_runtime_service.py`、`cost_statistics_derived_lifecycle_executor.py` |
| Tests | `tests/test_cost_statistics*.py`、`web/src/test/CostStatistics*.test.*`、`web/e2e/cost-statistics-*.spec.ts` |

## 依赖方向

- 允许依赖：workbench relation read boundary、query service。
- 必须通过：CostStatistics API/query service。
- 禁止绕过：页面重新引入旧同步状态 gate；API 直接扫描源表伪装后端 projection 已同步；把税金抵扣状态写入成本统计模块。

## 测试与验证

- `tests/test_cost_statistics_api.py`
- `tests/test_cost_statistics_runtime_service.py`
- `tests/test_cost_statistics_service.py`
- `tests/test_import_processing_service.py`
- `web/e2e/cost-statistics-flow.spec.ts`
- `web/e2e/cost-statistics-relation-fanout.spec.ts`

## 当前缺口和删除条件

- 后续删除历史表/迁移前必须验证 relation/import fan-out、direct API 页面行为和导出合同。
- 成本统计页面无直接写 API；若新增设置或来源修正写入口，必须返回 cost_statistics affected scopes/job diagnostics，不能只依赖页面刷新兜底。
