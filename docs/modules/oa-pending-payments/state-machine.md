# OA待付款核对状态机

> 修改 `OA待付款核对` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。OA 待付款状态必须由后端 policy/read model 给出，页面不得自行推断。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 主行 | `oa_application` | OA projection / OA sync | 每个 OA 申请是一行；银行流水和发票只是 relation evidence，不能替代主行。 |
| 流程视图 | `completed` | `oa_application.workflow_status` | 默认视图；只包含已完成 OA，历史未带 workflow status 的 OA 兼容归入此视图。 |
| 流程视图 | `in_progress` | `oa_application.workflow_status` | 进行中 OA 视图；下一次 OA sync/read model refresh 发现 OA 已完成后必须从该视图移除。 |
| 付款状态 | `unpaid` | `InvoiceLifecyclePolicy` / `OaPendingPaymentQueryService` | 没有有效支出流水付款证据时保持未付。 |
| 付款状态 | `paid` | 同上 | 有支出流水且付款合计等于 OA 金额。 |
| 付款状态 | `partially_paid` | 同上 | 支出流水合计小于 OA 金额。 |
| 付款状态 | `pending_review` | 同上 | OA 金额缺失、关联银行事实缺失、收入流水误关联、支出流水合计大于 OA 金额或证据不完整。 |
| OA 写回状态 | `not_written` / `written` | OA MySQL `t_payment_simple` | 仅在支付状态为 `paid` 时读取；实机验证显示 `flow_id` 对应 OA Mongo `form_data._id`。 |
| 银行证据 | `bank_present` / `bank_missing` | bank import facts + Workbench relation | 只有 `outflow` 支出流水计入付款证据；缺失事实不能退化成 `unpaid`。 |
| 发票证据 | `invoice_present` / `invoice_missing` | input invoice import facts + Workbench relation | 发票详情只展示进项发票字段；缺失发票不影响 OA 主行存在。 |
| relation detail | `oa` / `bank` / `invoice` | OA pending payment row payload | 允许 `kind=oa|bank|invoice`；非法 kind 返回业务错误。 |

关键规则：

- 列表以 OA application 为主行，不能因为没有银行流水或发票而隐藏 OA。
- OA 投影统一事实源必须包含 `completed` 和 `in_progress`，页面再用 `view_mode` 分流；设置页手工搜索/导入状态筛选只影响手工导入行为，不能让进行中 OA 从本页面 read model 源头消失。
- `oa.sync` 完成后必须入队 `oa_pending_payment.read_model.refresh` 月份 scope 和 `all` scope；页面不直接 live scan Mongo。
- 当 Workbench active relation 明确包含多条 OA、支出流水或进项发票时，OA 待付款只能按该 relation 生成一条核对行；OA 金额、支出流水已付金额和发票价税合计使用该 relation 下各自事实的合计。
- `paymentStatus` 必须由 lifecycle policy 或 query service 统一判定，页面不按金额字段自行计算。
- 进行中 OA 视图复用同一付款状态判定。`relation_status='candidate'` 只能展示候选 chip 和“确认已支付”动作，不能单独把 OA 判定为 `paid` 或直接写回 OA。
- `paymentStatus` 不再输出 `overpaid` 或 `merged_paid`；多 OA 合并付款通过 relation group 合计后判定为 `paid`，支出流水合计大于 OA 合计时进入 `pending_review`。
- “确认已支付”必须先校验 OA 为 `in_progress`、银行流水为 outflow、支出流水合计等于 OA 金额、可解析 OA Mongo 文档 ID，再确认 Workbench relation 并写回 `t_payment_simple.pay_status=1`。
- 支出流水付款合计使用所有有效 outflow relation 的 decimal total；收入流水、缺失银行事实或无效 relation 进入 `pending_review`。
- OA、支出流水和发票的 `relationCount`/`summaries` 必须完全来自 Workbench relation payload，不得由金额、日期或名称相似度推断。
- completed 与 in-progress 视图使用同一套四分组表格 UI；进行中 OA 没有发票证据时发票列显示 `-`，不影响确认已支付主链路。
- all scope 允许聚合月份 rows/source versions，不要求存在单独 `all` scope row。
- all scope 有实际 rows 时，source version freshness 优先由 rows 表证明；历史空月份 scope 不得把默认视图污染为 stale。
- detail lookup 使用 read model native columns：`oa_id`、`bank_transaction_id`、`invoice_id`、`row_id`。
- pending invoice rules 影响 OA 待付款时，当前执行层通过 workbench invalidation 间接入队 invoice usage collection 三个 read model；该行为由 API 回归保护。

禁止流转：

- 禁止生产 rows/filter-options/detail 在 read model miss/stale/source mismatch 时 live scan。
- 禁止把 refreshing payload 的空 rows 当作真实“暂无 OA 待付款”。
- 禁止旧 `oa_pending_payment.read_model.refresh` event 在 dirty scope 已有更新 source version 时继续 rebuild 或 fan-out 覆盖新 read model。
- 禁止前端自造 filter-options 枚举或 payment status 枚举。
- 禁止把 relation case id 当 OA id、bank transaction id 或 invoice id 请求详情。
- 禁止用单条 OA 金额和同一 relation 下多条支出流水/发票逐行交叉展开，造成“支付多了”或重复显示同一发票。
- 禁止只因为出现候选流水就自动写回 OA 支付状态；候选关系必须经用户确认或已是 active relation。
- 禁止对非 `in_progress` OA 调用 `confirm-paid` 写回。
- 禁止把 Flowable 流程实例 ID、流程请求 ID 或 relation case id 当 `t_payment_simple.flow_id`；写回 key 必须来自 OA Mongo `form_data._id`（投影中的 `Mongo文档ID` 或 `oa-pay-/oa-exp-` 行 ID 后缀）。
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
| view toggle | 用户切换“已完成 OA / 进行中 OA” | rows/filter-options 带 `view_mode`，切换时 page reset 为 1。 |
| invoice display | row payload 含发票证据 | completed 与 in-progress 表格都显示发票列；发票号、发票方、日期 chip 和金额纵向展示，支持单发票详情和多发票 relation 明细。 |
| missing invoice display | row payload 缺少发票证据 | 发票列显示 `-`；候选流水确认前不把发票证据作为进行中 OA 主操作。 |
| confirm paid | 进行中 OA 有候选或可确认支出流水 | 点击后调用 `POST /api/oa-pending-payments/confirm-paid`；成功提示“已确认支付并写回 OA”或等待写回状态刷新。 |
| OA writeback display | rows payload 的 `oaPaymentWriteback` | 展示“未写回 / 已写回”；外部依赖不可用只展示同步状态异常，不暴露数据库错误。 |
| filters/sort | 表头筛选菜单和排序按钮 | 参数必须映射到后端支持字段；多筛选为 AND 语义。 |
| grouped relation display | row payload 的 `relationCount` / `summaries` | 多 OA、流水或发票只显示合计金额和 `+N`，点击 `+N` 打开对应 `kind=oa|bank|invoice` 的关联明细。 |
| missing bank/invoice display | row payload 缺少银行或发票详情 | 表格显示 `-`，不显示 `0.00`、方向 chip、空日期提示或详情按钮。 |
| compact table fit | 页面表格容器 | 四分组表格应在常见桌面宽度内完整显示；优先换行和紧凑控件，不用横向滚动承载核心信息。 |
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
- Workbench 关系确认/撤回、进行中 OA 确认已支付、batch accounting relation change、turnover relation change。
- 待找发票规则保存和人工发票相关事件。
- invoice lifecycle refresh、App Health/readiness backfill。
- `startup_stale_scan` 默认关闭，且不直接刷新 OA 待付款 read model；只有后续 matching 结果真实变化并触发业务 lifecycle 时才间接影响。

Worker 流程：

1. 生产 API 发现 read model missing/stale/source mismatch，调用 `ReadModelRefreshGateway` 入队 `oa_pending_payment.read_model.refresh`。
2. `invoice-usage-collection` worker 消费事件。
3. refresh handler 先通过 durable queue 检查 event source_version 是否仍为当前 dirty scope；旧 event 返回 `skipped/stale_source_version`，不 rebuild、不 fan-out、不 complete dirty scope。
4. `scope_key=all` 先由 `InvoiceUsageCollectionSqlProjectionBuilder.list_oa_pending_payment_scope_shards` 展开月份 shard。
5. 月份 shard 调 `rebuild_oa_pending_payment_read_model_scope`，基于 OA projection、bank/import facts、input invoices 和 Workbench relation 构建 rows。
6. projection 保存 `read_model.oa_pending_payment_rows` 和 `read_model.oa_pending_payment_scopes`，写入 source versions 和 row count。
7. App Status 读取 readiness/dirty/outbox/worker heartbeat，展示 `oa_pending_payments` domain 状态。

失败恢复：

1. 先看 `/api/app-health.app_status` 中 `oa_pending_payments` domain、`oa_pending_payment` read model scopes、dirty scopes、outbox 和 `invoice-usage-collection` worker。
2. 如果 OA sync 失败，先恢复 OA dependency / `oa.sync`，再重跑 `oa_pending_payment:all`。
3. 如果 source version mismatch，确认 OA projection、bank import fact、input invoice fact、workbench relation 和 invoice lifecycle 是否已经收敛。
4. 如果 detail 202/refreshing，先确认对应 row 所在月份 scope 是否 fresh，不手工查 live facts 补页面。
5. 如果 all scope 卡住，检查月份 shard readiness；all scope 不应同步重建历史全量。
6. 如果手工 rebuild 后又回退到旧 source version，先确认服务器 `invoice-usage-collection` worker 是否已经发布到当前 release；不要仅靠本地源码或一次性手工 rebuild 判定生产已闭环。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-17 | 补 OA pending read model stale event guard 和 all scope rows source-version 聚合 | 防止旧 worker/event 覆盖新 v3 投影，防止历史空 scope 污染默认 `all` 视图 freshness | `tests.test_invoice_usage_collection_sql_runtime`、HTTP smoke、Playwright 页面 smoke |
| 2026-06-17 | 新增 `completed/in_progress` OA 流程视图和进行中 OA 确认写回 | OA workflow status 投影、`view_mode` rows/filter-options、`confirm-paid` command、OA MySQL `t_payment_simple` 写回、前端三列表格与确认按钮 | `tests.test_oa_payment_status_service`、`tests.test_mongo_oa_adapter`、`tests.test_oa_pending_payment_service`、`tests.test_oa_pending_payment_command_service`、`tests.test_oa_pending_payment_api`、`web/src/test/OaPendingPaymentsPage.test.tsx` |
| 2026-06-17 | 补充 OA 待付款 Browser e2e，覆盖 rows 首屏、搜索、支付状态筛选、交易时间排序、OA/流水/发票详情抽屉和支出流水无需开票规则抽屉 | OA 待付款 UI 状态、rows/filter/detail/rules endpoint、Playwright smoke | `cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts` |
| 2026-06-18 | `oa.sync` 增加 OA 待付款 read model fan-out | 进行中 OA 进入 OA projection 后，`oa_pending_payment` 月份和 all scope 必须自动刷新，避免页面空数据 | `PYTHONPATH=backend/src python3 -m unittest tests.test_oa_projection_sync_service -v` |
| 2026-06-18 | completed 视图恢复发票证据列，in-progress 继续隐藏发票列 | 真实浏览器首屏必须看到发票号并可打开发票详情；进行中 OA 仍只展示候选流水确认主链路 | `cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`、`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts` |
| 2026-06-18 | OA/状态/流水主体表格改为内部三栏布局 | OA 单元格按申请人/项目/金额三栏展示，流水单元格按对方户名/金额/摘要三栏展示，支付状态列收窄并只显示未写回/已写回 | `cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx` |
| 2026-06-18 | completed/in-progress 统一四分组表格 UI | 两种流程视图都显示 OA、支付状态、流水、发票四个大分组；发票列纵向展示并移除价税合计 chip | `cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx` |
| 2026-06-18 | OA pending 四分组表格取消横向滚动 | 表格改为 100% 自适应百分比列宽，局部缩小字号/chip/按钮并允许换行 | `cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts` |
| 2026-06-11 | 关联台分组关系收敛 | 移除 `overpaid`/`merged_paid` 展示口径；多 OA/流水/发票 relation 合并为一条核对行；详情支持 `kind=oa` | `tests.test_oa_pending_payment_service`、`tests.test_invoice_lifecycle_policy`、`tests.test_oa_pending_payment_api`、`tests.test_invoice_usage_collection_sql_runtime`、`web/src/test/OaPendingPaymentsPage.test.tsx` 通过 |
| 2026-06-11 | 补齐测试闭环状态机 | OA 主行、付款状态、详情、UI、read model 和 worker 状态边界 | `tests.test_oa_pending_payment_service`、`tests.test_oa_pending_payment_api`、`tests.test_invoice_lifecycle_page_integration`、`tests.test_invoice_usage_collection_sql_runtime`、`tests.test_derived_data_lifecycle_service`、`tests.test_app_status_overview_service`、`tests.test_runtime_worker_registry`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts` 通过 |
