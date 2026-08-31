# 成本统计边界与 I/O

日期：2026-08-31

## 模块状态

- 状态：closed
- 页面职责：对同一项目成本集合提供项目、费用类型、银行账户三个观察维度。
- 不负责：浏览原始银行流水、按标签/时间分析银行收支、维护银行标签规则、构建 Cost read model。
- 旧路径：`time`、`bank`、`bank_tag` view、`time-tag-rules` API/设置/前端抽屉已经删除，禁止兼容回退。

## 分层边界

| 层 | 输入 | 输出 | 禁止 |
| --- | --- | --- | --- |
| Route | HTTP query/body、权限 session | HTTP 状态、JSON 或导出文件 | SQL、业务聚合、队列写入 |
| Canonical repository | scope、一个 PostgreSQL connection | 单个一致性 snapshot | read model、Redis、RabbitMQ、HTTP、逐行查询 |
| Policy | canonical snapshot、无 OA/人工分配事实 | 唯一成本事件集合、聚合、详情 | 数据库、网络、全局状态、fallback |
| Query service | repository、policy、view/filter/cursor | 稳定 API DTO | freshness gate、worker、旧 view 兼容 |
| Manual allocation service | relation case、逐 OA 单元金额、`X`、version/fingerprint、actor | versioned allocation 与 audit | HTTP、页面状态、比例建议、半写入 |
| Frontend | API DTO、用户选择 | 三视图、详情、导出、错误/重试 | 业务金额重算、跨页面 I/O、旧页签 |

## Canonical 输入

单个 `REPEATABLE READ READ ONLY` snapshot 按请求范围批量读取：

- `app.bank_transactions`
- `app.oa_applications.normalized_payload` 的成本字段和 canonical `expense_items`
- `app.workbench_pair_relations` 中 `status='active'` 的正式关系
- `app.bank_transaction_categories` 与 confirmations（用于退款与无 OA 资格，不用于提供按标签视图）
- `app.app_settings` 中银行账户映射和 `cost_statistics_no_oa_projects`
- `app.cost_statistics_manual_allocations`

成本模块不读取银行明细页面的 payload/read model。银行有效分类通过银行分类 owner 的批量 projection port 取得；不得复制分类算法或增加 SQL/Python fallback。

## 请求闭环

```text
GET explorer/detail/export
  -> CostStatisticsApiRoutes
  -> CostStatisticsQueryService
  -> PostgresCostStatisticsCanonicalRepository.load_snapshot()
  -> CostStatisticsPolicy
  -> 200 JSON / export file

PUT manual allocation
  -> CostStatisticsManualAllocationService
  -> lock relation facts + validate version/fingerprint/C+X=N
  -> allocation + audit.events in one transaction
```

### Explorer 合同

- `view` 仅接受 `project|expense_type|bank_account`。
- 共用 `scope`、`query`、`cursor`、`page_size` 和 `include_statistics`。
- `project` 下钻参数：可选 `project_name`，选中项目后可选 `expense_type`。
- `expense_type` 下钻参数：可选 `expense_type`。
- `bank_account` 下钻参数：可选 `bank_account_label`，选中账户后可选 `project_name`。
- 旧 `payment_account_label`、`tag_code`、`primary_tag`、`sub_tag`、时间栏参数不是 explorer 合同。
- 响应固定包含 `summary`、可选 `statistics`、`facets`、`rows`、`row_count`、`next_cursor`；不包含旧 `time_rows`、`bank_flow_rows`、方向汇总或 read-model 状态。
- `summary.total_amount` 与 `transaction_count` 在三个根视图上必须相等；分面只改变分组，不改变成本人口。
- `statistics` 只包含项目数、费用类型数、已确定银行账户数和成本明细数；`银行账户未确定`不计入已确定账户数，但其成本仍计入总额。

### 银行账户归属合同

- OA 成本关系仅收集 `direction=支出` 且账户非空的不同账户。
- 集合大小为 1：使用该账户；为 0 或大于 1：`银行账户未确定`。
- 收入/退款账户不参与归属。
- 无 OA 成本事件使用来源支出流水账户；空账户归入`银行账户未确定`。
- 归属只发生一次并写入成本事件 `bank_account_label`；project、expense_type、bank_account 聚合和导出必须复用该字段。

### 详情与导出

- OA 成本行打开 `/allocations/{id}`，展示 OA 单元成本和关系层付款证据；银行账户归属不等于 OA 单元到某条流水的分配。
- 无 OA 成本行可打开 `/bank-transactions/{id}`；该 endpoint 不等于恢复原始银行统计页。
- preview 与 download 复用 explorer 的成本事件和三个 view；旧 view 明确返回 400。
- 预览最多 8 行，下载受行数上限保护。

## 设置边界

- 成本统计只保留 `cost_statistics_no_oa_projects` 设置 family。
- `AppSettingsService.get_cost_statistics_source_settings_payload()` 只向 canonical repository 提供银行账户映射和银行标签字典等读取事实。
- 已删除的 `cost_statistics_time_tag_selection` 不读取、不归一化、不持久化、不审计；历史持久化字段不得作为运行时 fallback。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/CostStatisticsPage.tsx`、`web/src/components/cost-statistics/*`、`web/src/features/cost-statistics/*` |
| Route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Query / policy | `cost_statistics_query_service.py`、`cost_statistics_policy.py`、`cost_statistics_bank_tags.py`、`cost_statistics_manual_allocation_service.py` |
| Canonical repository | `cost_statistics_canonical_repository.py` |
| Manual allocation repository | `postgres_repositories/cost_statistics_manual_allocation.py` |
| Settings owner | `app_settings_service.py` |
| Tests | `tests/test_cost_statistics_*.py`、`web/src/test/CostStatistics*.test.*`、`web/e2e/cost-statistics-*.spec.ts` |

## 已删除旧链路

- Cost read model、refresh service、runtime worker、source version、SQL projection与缓存链。
- 页面 `按时间`、`按标签`、原始 `按银行` 视图及其前端状态、类型和请求参数。
- `/api/cost-statistics/time-tag-rules` 的 GET/PUT 路由及 App Settings family。
- `time_rows`、`bank_flow_rows`、`bank_flow_time_rows` 响应兼容读取。

历史 migration 和明确验证“旧合同被拒绝”的负面测试可以保留；生产 runtime 和 UI 不得保留并行旧路径。

## 跨模块影响

- 银行明细：功能不变，仍是原始流水唯一浏览入口。
- Workbench/OA：关系确认、撤回或 OA 状态改变后，下一次 Cost GET 读取新事实；不新增 fan-out。
- 设置：只删除成本统计旧 time/tag family，不影响银行明细自己的自动标签设置。
- 权限/审计：无 OA 与人工分配写入口保持现有权限和审计合同。
- 数据库：forward-only migration `0165` 只从 `app.app_settings` 的 canonical/formal-raw JSON 删除退役设置键；无表结构变化、无备份工件、无主库删除 I/O。旧 release 会重新补入该键，因此迁移后禁止自动回滚旧 binary。
