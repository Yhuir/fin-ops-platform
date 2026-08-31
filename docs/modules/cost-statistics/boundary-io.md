# 成本统计边界与 I/O

日期：2026-08-31

## 模块状态

- 状态：closed
- 页面职责：对同一项目成本集合提供项目、费用类型、银行账户三个观察维度，并对同一 canonical 银行流水集合提供时间、标签两个收支观察维度。
- 不负责：银行账户余额、银行流水维护、成本专属标签规则、构建 Cost read model。
- 旧路径：原始 `bank` view、`time-tag-rules` API/设置/前端抽屉已经删除，禁止兼容回退；`time|bank_tag` 是当前正式只读 view。

## 分层边界

| 层 | 输入 | 输出 | 禁止 |
| --- | --- | --- | --- |
| Route | HTTP query/body、权限 session | HTTP 状态、JSON 或导出文件 | SQL、业务聚合、队列写入 |
| Canonical repository | scope、一个 PostgreSQL connection | 单个一致性 snapshot | read model、Redis、RabbitMQ、HTTP、逐行查询 |
| Policy | canonical snapshot、无 OA/人工分配事实 | 唯一成本事件集合或真实流水集合、聚合、详情 | 数据库、网络、全局状态、fallback |
| Query service | repository、policy、view/filter/cursor | 稳定 API DTO | freshness gate、worker、旧 view 兼容 |
| Manual allocation service | relation case、逐 OA 单元金额、`X`、version/fingerprint、actor | versioned allocation 与 audit | HTTP、页面状态、比例建议、半写入 |
| Frontend | API DTO、用户选择 | 五视图、详情、导出、错误/重试 | 业务金额重算、跨页面 I/O、旧规则 UI |

## Canonical 输入

单个 `REPEATABLE READ READ ONLY` snapshot 按请求范围批量读取。两个流水 view 只读取银行流水和批量有效分类投影并立即返回；三个项目成本 view 再按需读取其余事实：

- `app.bank_transactions`
- `app.oa_applications.normalized_payload` 的成本字段和 canonical `expense_items`
- `app.workbench_pair_relations` 中 `status='active'` 的正式关系
- `app.bank_transaction_categories` 与 confirmations 的批量有效分类投影
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

### 人工分配展示合同

- relation-only snapshot 对关系内全部银行流水 ID 去重后执行一次批量有效分类投影；支出与付错退款都消费同一银行分类 owner，不逐行读取。
- `bank_events.tags` 是 canonical 银行标签层级路径；流水 DTO 不再输出旧 `summary`，前端不得用摘要、备注或 OA 费用类型补写标签。
- OA 单元以 Chip 展示 `oa_apply_type` 与 `expense_type`；流水以 Chip 展示顺序号/退款类型、交易时间和 `tags`，两组分类 I/O 不互相推导。
- 前端只在金额输入后按当前差额展示简短校验；初始空白和已平衡状态不显示常驻说明。多项目关系才在 OA 单元旁保留项目名用于消歧。

### Explorer 合同

- `view` 接受 `time|bank_tag|project|expense_type|bank_account`；原始 `bank` 明确拒绝。
- 共用 `scope`、`query`、`cursor`、`page_size` 和 `include_statistics`。
- `project` 下钻参数：可选 `project_name`，选中项目后可选 `expense_type`。
- `expense_type` 下钻参数：可选 `expense_type`。
- `bank_account` 下钻参数：可选 `bank_account_label`，选中账户后可选 `project_name`。
- `time` 无额外下钻参数，直接分页返回当前 scope/query 的流水；`bank_tag` 可接受 `bank_tag_primary_label`，选中主标签后可接受 `bank_tag_sub_label`。
- 旧 `payment_account_label`、`tag_code`、`primary_tag`、`sub_tag` 和客户端时间栏私有参数不是 explorer 合同。
- 响应固定包含 `summary`、可选 `statistics`、`facets`、`rows`、`row_count`、`next_cursor`；不包含旧 `time_rows`、`bank_flow_rows` 或 read-model 状态。
- `summary.total_amount` 与 `transaction_count` 在三个根视图上必须相等；分面只改变分组，不改变成本人口。
- 项目与银行账户分面不再返回无消费方的 `percentage_label` 和明细数；费用类型分面保留下钻所需的明细数与项目数。
- 三个项目成本 view 的 `statistics` 在既有项目数、费用类型数、已确定银行账户数和成本明细数之外，返回同一 snapshot 已加载银行流水的总数、支出数和收入数；不新增查询或跨页统计 I/O。`银行账户未确定`不计入已确定账户数，但其成本仍计入总额。
- 两个流水 view 的 `summary.total_amount` 表示净支出，并同时返回 `expense_amount`、`income_amount` 和两个方向的交易数。`bank_tag` 分面同样返回支出、收入、净支出，禁止使用绝对值总和替代净额。
- 两个流水 view 的 `statistics` 返回流水数、支出数、收入数、未标记数和标签数；不触发项目成本构建。

### 银行账户归属合同

- OA 成本关系仅收集 `direction=支出` 且账户非空的不同账户。
- 集合大小为 1：使用该账户；为 0 或大于 1：`银行账户未确定`。
- 收入/退款账户不参与归属。
- 无 OA 成本事件使用来源支出流水账户；空账户归入`银行账户未确定`。
- 归属只发生一次并写入成本事件 `bank_account_label`；project、expense_type、bank_account 聚合和导出必须复用该字段。

### 详情与导出

- OA 成本行打开 `/allocations/{id}`，展示 OA 单元成本和关系层付款证据；银行账户归属不等于 OA 单元到某条流水的分配。
- 两个流水 view 和无 OA 成本行可打开 `/bank-transactions/{id}`；OA 成本行打开 `/allocations/{id}`。
- preview 与 download 接受五个正式 view。项目成本导出复用成本事件；流水导出复用真实银行集合和方向净额。
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
- 原始 `按银行` view 及其前端状态、类型和请求参数。
- `/api/cost-statistics/time-tag-rules` 的 GET/PUT 路由及 App Settings family。
- `time_rows`、`bank_flow_rows`、`bank_flow_time_rows` 响应兼容读取。
- 人工分配银行流水的旧 `summary` DTO、前端 mapper、展示与测试 fixture。

历史 migration 和明确验证“旧合同被拒绝”的负面测试可以保留；生产 runtime 和 UI 不得保留并行旧路径。

## 跨模块影响

- 银行明细：功能不变，继续拥有账户余额、账户维度筛选和流水维护；成本统计只读同一 canonical 流水做时间/标签收支分析。
- Workbench/OA：关系确认、撤回或 OA 状态改变后，下一次 Cost GET 读取新事实；不新增 fan-out。
- 设置：只删除成本统计旧 time/tag family，不影响银行明细自己的自动标签设置。
- 权限/审计：无 OA 与人工分配写入口保持现有权限和审计合同。
- 数据库：无 schema migration、无设置写入、无备份工件、无主库删除 I/O。
