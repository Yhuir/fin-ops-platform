# OA待付款核对状态机

> 修改 `OA待付款核对` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。OA 待付款状态必须由后端 policy/read model 给出，页面不得自行推断。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 主行 | `oa_application` | OA projection / OA sync | 每个 OA 申请是一行；银行流水和发票只是 relation evidence，不能替代主行。 |
| 付款状态 | `unpaid` | `InvoiceLifecyclePolicy` / `OaPendingPaymentQueryService` | 没有有效支出流水付款证据时保持未付。 |
| 付款状态 | `paid` | 同上 | 有支出流水且付款合计等于 OA 金额。 |
| 付款状态 | `partially_paid` | 同上 | 支出流水合计小于 OA 金额。 |
| 付款状态 | `overpaid` | 同上 | 支出流水合计大于 OA 金额。 |
| 付款状态 | `merged_paid` | 同上 | 多个 OA 申请共享一组付款关系，且 relation 语义表示合并支付。 |
| 付款状态 | `pending_review` | 同上 | OA 金额缺失、关联银行事实缺失、收入流水误关联或证据不完整。 |
| 银行证据 | `bank_present` / `bank_missing` | bank import facts + Workbench relation | 只有 `outflow` 支出流水计入付款证据；缺失事实不能退化成 `unpaid`。 |
| 发票证据 | `invoice_present` / `invoice_missing` | input invoice import facts + Workbench relation | 发票详情只展示进项发票字段；缺失发票不影响 OA 主行存在。 |
| relation detail | `bank` / `invoice` | OA pending payment row payload | 只允许 `kind=bank|invoice`；非法 kind 返回业务错误。 |

关键规则：

- 列表以 OA application 为主行，不能因为没有银行流水或发票而隐藏 OA。
- `paymentStatus` 必须由 lifecycle policy 或 query service 统一判定，页面不按金额字段自行计算。
- 支出流水付款合计使用所有有效 outflow relation 的 decimal total；收入流水、缺失银行事实或无效 relation 进入 `pending_review`。
- all scope 允许聚合月份 rows/source versions，不要求存在单独 `all` scope row。
- detail lookup 使用 read model native columns：`oa_id`、`bank_transaction_id`、`invoice_id`、`row_id`。
- pending invoice rules 影响 OA 待付款时，当前执行层通过 workbench invalidation 间接入队 invoice usage collection 三个 read model；该行为由 API 回归保护。

禁止流转：

- 禁止生产 rows/filter-options/detail 在 read model miss/stale/source mismatch 时 live scan。
- 禁止把 refreshing payload 的空 rows 当作真实“暂无 OA 待付款”。
- 禁止前端自造 filter-options 枚举或 payment status 枚举。
- 禁止把 relation case id 当 OA id、bank transaction id 或 invoice id 请求详情。
- 禁止用销项发票字段渲染进项发票详情。
- 禁止把 App Status / domain event 当成付款事实源。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | rows + filter-options 初始请求 | 展示页面加载骨架；abort 后清理 loading。 |
| refreshing | rows/filter-options API 返回 `read_model_status=refreshing` 或 202 | 页面当前采用标准空状态隐藏底层刷新细节；不得展示 stale reason 给业务用户。 |
| empty | fresh payload 且 total 为 0 | 表示当前筛选下真实没有记录。 |
| error | rows/filter-options 请求失败 | 展示业务错误，不暴露 SQL、worker 或 OA adapter internals。 |
| detail loading | OA/bank/invoice/relation detail 请求中 | drawer 内展示加载态。 |
| detail unavailable | detail API 返回 202 / `detailAvailable=false` | drawer 展示“详情暂不可用”和后端业务原因。 |
| rules drawer | 用户打开“支出流水无需开票规则设置” | 复用 pending invoice rules endpoint，保存后不重挂载父页面。 |
| filters/sort | 表头筛选菜单和排序按钮 | 参数必须映射到后端支持字段；多筛选为 AND 语义。 |
| missing bank/invoice display | row payload 缺少银行或发票详情 | 表格显示 `-`，不显示 `0.00`、方向 chip、空日期提示或详情按钮。 |
| permission denied | API 403 | 页面显示错误；后端必须强制权限，前端隐藏不是权限事实。 |

前端事件：

- OA 待付款页面主要靠重新请求 API/read boundary 收敛，不把同浏览器 domain event 当事实源。
- rules drawer 使用 pending invoice rules API；保存后的真实 fan-out 由后端 lifecycle/dirty scope/outbox/readiness 证明。
- 页面卸载后不 replay 事件；返回页面重新加载 rows/filter-options。

## Read Model / Worker 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `fresh` | scope row/readiness、source versions、schema 与当前事实一致 | rows/filter-options/detail 可返回当前 payload。 |
| `missing` | repository 无 rows/scope 或 readiness 记录缺失 | 入队 `oa_pending_payment.read_model.refresh`，API 返回 refreshing。 |
| `refreshing` | dirty scope pending/processing，或 all scope 正 fan-out month shards | worker 继续处理；页面展示同步中的中性状态。 |
| `stale` / `source_mismatch` / `schema_mismatch` | OA projection、bank import、input invoice import、workbench relation 或 lifecycle source version 落后 | 入队重建；API 不返回 stale rows。 |
| `failed` | projection/worker refresh 失败 | App Status busy/blocked，页面等待运维恢复。 |
| `unavailable` | repository、queue、worker、OA dependency 不可用 | API 返回 unavailable/refreshing；不得伪造 fresh。 |

Scope 形态：

- `all`
- 月份 shard：`YYYY-MM`

Refresh 触发来源：

- OA sync / OA rebuild。
- 银行流水导入确认。
- 发票导入确认。
- Workbench 关系确认/撤回、batch accounting relation change、turnover relation change。
- 待找发票规则保存和人工发票相关事件。
- invoice lifecycle refresh、startup stale scan、App Health/readiness backfill。

Worker 流程：

1. 生产 API 发现 read model missing/stale/source mismatch，调用 `ReadModelRefreshGateway` 入队 `oa_pending_payment.read_model.refresh`。
2. `invoice-usage-collection` worker 消费事件。
3. `scope_key=all` 先由 `InvoiceUsageCollectionSqlProjectionBuilder.list_oa_pending_payment_scope_shards` 展开月份 shard。
4. 月份 shard 调 `rebuild_oa_pending_payment_read_model_scope`，基于 OA projection、bank/import facts、input invoices 和 Workbench relation 构建 rows。
5. projection 保存 `read_model.oa_pending_payment_rows` 和 `read_model.oa_pending_payment_scopes`，写入 source versions 和 row count。
6. App Status 读取 readiness/dirty/outbox/worker heartbeat，展示 `oa_pending_payments` domain 状态。

失败恢复：

1. 先看 `/api/app-health.app_status` 中 `oa_pending_payments` domain、`oa_pending_payment` read model scopes、dirty scopes、outbox 和 `invoice-usage-collection` worker。
2. 如果 OA sync 失败，先恢复 OA dependency / `oa.sync`，再重跑 `oa_pending_payment:all`。
3. 如果 source version mismatch，确认 OA projection、bank import fact、input invoice fact、workbench relation 和 invoice lifecycle 是否已经收敛。
4. 如果 detail 202/refreshing，先确认对应 row 所在月份 scope 是否 fresh，不手工查 live facts 补页面。
5. 如果 all scope 卡住，检查月份 shard readiness；all scope 不应同步重建历史全量。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐测试闭环状态机 | OA 主行、付款状态、详情、UI、read model 和 worker 状态边界 | `tests.test_oa_pending_payment_service`、`tests.test_oa_pending_payment_api`、`tests.test_invoice_lifecycle_page_integration`、`tests.test_invoice_usage_collection_sql_runtime`、`tests.test_derived_data_lifecycle_service`、`tests.test_app_status_overview_service`、`tests.test_runtime_worker_registry`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts` 通过 |
