# 成本统计边界与 I/O

## 责任边界

| 层 | 输入 | 输出 | 禁止 |
| --- | --- | --- | --- |
| Route | HTTP query/body、权限 session | HTTP 状态、JSON 或文件 | SQL、业务聚合、队列写入 |
| Canonical repository | PostgreSQL connection | 单个一致性快照 | read model、Redis、RabbitMQ、HTTP |
| Policy | canonical snapshot、筛选参数 | 视图、统计、详情、导出行 | 数据库、网络、全局状态 |
| Query service | repository、policy、分页/游标 | 稳定 API DTO | freshness gate、worker、隐式 fallback |
| Frontend | API DTO、用户筛选 | 页面、下载、错误/重试状态 | read-model polling、版本推断、跨页面 I/O |

## 统一事实源

一次请求在同一个 `REPEATABLE READ READ ONLY` 快照内读取：

- `app.bank_transactions`
- `app.oa_applications`（经 `PostgresOAProjectionRepository`）
- `app.workbench_pair_relations`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_confirmations`
- `app.app_settings`

正式配对关系只认 `app.workbench_pair_relations.status = 'active'`。成本页面不复制关联关系，也不读取 Workbench 或银行明细页面的 read model。

## 请求闭环

```text
HTTP GET
  -> CostStatisticsApiRoutes
  -> CostStatisticsQueryService
  -> PostgresCostStatisticsCanonicalRepository.load_snapshot()
  -> CostStatisticsPolicy
  -> 200 JSON / export file
```

- 页面首次访问和浏览器刷新走同一条链。
- API 失败时明确返回错误；用户再次刷新会重新打开数据库快照并完整重试。
- 标签规则保存只修改 App Settings；保存成功后的页面 reload 重新应用最新规则。
- 不产生 `cost_statistics.read_model.refresh`、dirty scope、readiness 或 Cost worker I/O。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/CostStatisticsPage.tsx`、`web/src/features/cost-statistics/*` |
| Route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Query / policy | `cost_statistics_query_service.py`、`cost_statistics_policy.py`、`cost_statistics_bank_tags.py` |
| Canonical repository | `cost_statistics_canonical_repository.py` |
| Settings owner | `app_settings_service.py` |
| Audit | `postgres_repositories/cost_statistics_page_audit.py` |
| Migration | `postgres/migrations/0126_cost_statistics_direct_canonical_read.sql` |

## 已删除旧链路

以下模块及其 worker/registry/manifest/scope/status 入口不得恢复：

- `cost_statistics_read_model_refresh.py`
- `cost_statistics_read_model_repository.py`
- `cost_statistics_runtime_service.py`
- `cost_statistics_source_versions.py`
- `cost_statistics_sql_projection.py`
- `cost_statistics_derived_lifecycle_executor.py`
- Cost worker env、Cost read-model 表与 Cost refresh event

migration `0126` 负责停止遗留运行时事件并删除旧表。除该迁移的清理语句与回归门禁外，生产 runtime 不得再出现旧 Cost read-model 符号。

## 性能边界

- 一次 API 请求只建立一个数据库快照，不轮询、不等待后台任务。
- 分页、详情和导出保持现有上限；导出仍受 `COST_STATISTICS_EXPORT_ROW_LIMIT` 保护。
- 本次不承诺 3 秒硬 SLO，但候选发布必须记录各视图多次请求的 p50/p95，并确认无 Cost queue/worker I/O。
- 若生产数据量使全量 canonical snapshot 成为已测瓶颈，下一步只允许在 repository 内下推等价筛选/聚合；不得恢复 Cost read model 或页面间依赖。
