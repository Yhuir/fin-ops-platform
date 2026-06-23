# OA待付款核对状态机

> 修改 `OA待付款核对` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。OA 待付款状态必须由后端 policy/read model 给出，页面不得自行推断。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 主行 | `oa_application` | completed: 普通 `app.oa_applications` / OA completed projection；in_progress: OA MySQL `t_payment_simple.flow_id` + payment-admitted OA projection / OA Mongo | completed 每个统一 OA projection 中已完成/历史未知 OA 是一行；in_progress 每个已进入支付状态管理准入表并能匹配 OA Mongo `_id` 的进行中 OA 是一行；银行流水和发票只是 relation evidence，不能替代主行。 |
| 流程视图 | `completed` | `oa_application.workflow_status` | 默认视图；只包含已完成 OA，历史未带 workflow status 的 OA 兼容归入此视图。 |
| 流程视图 | `in_progress` | `oa_application.workflow_status` | 进行中 OA 视图；下一次 OA sync/read model refresh 发现 OA 已完成后必须从该视图移除。 |
| 付款状态 | `unpaid` | `InvoiceLifecyclePolicy` / `OaPendingPaymentQueryService` | 没有有效支出流水付款证据时保持未付。 |
| 付款状态 | `paid` | 同上 | 有支出流水且付款合计等于 OA 金额。 |
| 付款状态 | `partially_paid` | 同上 | 支出流水合计小于 OA 金额。 |
| 付款状态 | `pending_review` | 同上 | OA 金额缺失、关联银行事实缺失、收入流水误关联、支出流水合计大于 OA 金额或证据不完整。 |
| OA 写回状态 | `not_written` / `written` | OA MySQL `t_payment_simple` | 仅在支付状态为 `paid` 时读取；实机验证显示 `flow_id` 对应 OA Mongo `form_data._id`。 |
| 银行证据 | `bank_present` / `bank_missing` | completed: bank import facts + Workbench relation；in_progress: bank import facts + OA pending payment relation | 只有 `outflow` 支出流水计入付款证据；缺失事实不能退化成 `unpaid`。 |
| 支出流水抽屉候选 | `unmatched` / `matched` / `linked_in_progress` | bank import facts + Workbench active relation + `app.bank_transaction_relation_claims` | 从已选 OA 打开抽屉时按 `oa_row_ids` 解析 OA 月份并只读取对应月份支出流水；没有 OA 上下文时才保留全部支出流水语义。只有没有 Workbench active relation、也没有 active pending bank claim 的 `unmatched` 流水可被用户选择并关联到进行中 OA。 |
| 发票证据 | `invoice_present` / `invoice_missing` | input invoice import facts + Workbench relation | 发票详情只展示进项发票字段；缺失发票不影响 OA 主行存在。 |
| relation detail | `oa` / `bank` / `invoice` | OA pending payment row payload | 允许 `kind=oa|bank|invoice`；非法 kind 返回业务错误。 |

关键规则：

- 列表以 OA application 为主行，不能因为没有银行流水或发票而隐藏 OA。
- OA 待付款核对只有 `in_progress` 视图使用 `t_payment_simple.flow_id` 作为主行准入事实源；该字段必须匹配 OA Mongo `form_data._id`。未进入 `t_payment_simple` 的进行中 OA，即使 OA 系统显示为进行中，也不进入本页面进行中表格。
- `in_progress` 主行不得用 completed projection 的业务字段指纹排除。不同 `flow_id` 代表不同付款申请，即使项目、对方、金额、申请人、事由和收款信息完全相同，也必须作为独立 OA 保留；自动匹配遇到同一流水命中多张 OA 时应按歧义处理或留给人工关联。
- 普通 `app.oa_applications` 投影承载已完成/历史未知 OA，并作为 `completed` 视图的统一事实源；OA 待付款 read model 同时接入普通 completed projection 和专用 payment-admitted projection。设置页手工搜索/导入状态筛选只影响手工导入行为，不能把已准入的进行中 OA 从本页面 read model 源头过滤掉。
- `t_payment_simple.id` 不得当作 OA ID；页面可以携带它作为支付状态记录诊断字段，但 OA 匹配和写回只使用 `flow_id`。
- `oa.sync` 完成后必须入队 `oa_pending_payment.read_model.refresh` 月份 scope 和 `all` scope；页面不直接 live scan Mongo。
- 当 Workbench active relation 明确包含多条 OA、支出流水或进项发票时，OA 待付款只能按该 relation 生成一条核对行；OA 金额、支出流水已付金额和发票价税合计使用该 relation 下各自事实的合计。
- `paymentStatus` 必须由 lifecycle policy 或 query service 统一判定，页面不按金额字段自行计算。
- 进行中 OA 视图复用同一付款状态判定。`relation_status='candidate'` 只能展示候选 chip，不能单独把 OA 判定为 `paid` 或直接写回 OA；completed 视图只有 Workbench active relation 能作为写回证据，in-progress 视图只有 OA 待付款独立 active pending relation 或自动匹配命令刚确认的 pending relation 能作为写回证据。
- `paymentStatus` 不再输出 `overpaid` 或 `merged_paid`；多 OA 合并付款通过 relation group 合计后判定为 `paid`，支出流水合计大于 OA 合计时进入 `pending_review`。
- 页面进入后调用自动匹配/写回命令。该命令复用关联台 OA-bank 精确金额/精确合计规则，只自动确认无冲突的 in-progress OA 与没有 Workbench active relation、也没有 pending bank claim 的支出流水；同时扫描 completed 中已有 Workbench active 支出流水 relation 的 OA、in-progress 中已有 active pending relation 的 OA。写回前必须校验银行流水为 outflow、支出流水合计等于 OA 金额、可解析 OA Mongo 文档 ID；校验通过后写回 `t_payment_simple.pay_status=1`。
- “关联支出流水”抽屉作为自动匹配失败后的人工兜底，创建 OA 待付款独立 active pending relation，并写入 `app.bank_transaction_relation_claims` 独占对应支出流水，不写 `app.workbench_pair_relations`。关联成功后沿用同一写回校验，金额/方向/`flow_id` 通过时自动写回 `t_payment_simple.pay_status=1`，不再需要用户二次点击确认写回。
- OA sync 发现 active pending relation 的所有 OA row 都变成 completed 时，promotion service 复用 Workbench relation command 创建普通 `manual_confirmed`/`normal_match` active relation，再把 pending relation 标记为 `promoted` 并释放 bank claim。promotion metadata 使用 `origin=oa_pending_payment_promotion`；不得继续写 `origin=oa_pending_payment_in_progress` 的 Workbench active relation。
- 支出流水付款合计使用所有有效 outflow relation 的 decimal total；收入流水、缺失银行事实或无效 relation 进入 `pending_review`。
- completed 视图 OA、支出流水和发票的 `relationCount`/`summaries` 必须完全来自 Workbench relation payload；in-progress 视图 OA、支出流水 relation summary 必须来自 OA 待付款独立 pending relation payload。任何视图都不得由金额、日期或名称相似度推断已关联。
- completed 与 in-progress 视图使用同一套四分组表格 UI；进行中 OA 没有发票证据时发票列显示 `-`，不影响支出流水匹配和自动写回主链路。
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
- 禁止只因为出现候选流水、自动决策或未确认 relation 就写回 OA 支付状态；写回必须基于 completed Workbench active relation、in-progress active pending relation 或自动匹配命令刚确认的 pending relation，并通过 outflow、金额相等和 `flow_id` 校验。
- 禁止前端暴露人工 `confirm-paid` 写回入口；写回必须由自动匹配/写回命令或支出流水关联成功后的自动写回路径触发。
- 禁止把 Flowable 流程实例 ID、流程请求 ID 或 relation case id 当 `t_payment_simple.flow_id`；写回 key 必须来自 OA Mongo `form_data._id`（投影中的 `Mongo文档ID` 或 `oa-pay-/oa-exp-` 行 ID 后缀）。
- 禁止用销项发票字段渲染进项发票详情。
- 禁止把 App Status / domain event 当成付款事实源。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | rows + filter-options 初始请求 | 展示页面加载骨架；abort 后清理 loading。 |
| refreshing | rows/filter-options API 返回 `read_model_status=refreshing` 或 202 | 页面展示中性刷新诊断，不得把空 rows 当成真实空态，也不得展示 stale reason 给业务用户。 |
| empty | fresh payload 且 total 为 0 | 表示当前筛选下真实没有记录。 |
| error | rows/filter-options 请求失败 | 展示业务错误，不暴露 SQL、worker 或 OA adapter internals。 |
| detail loading | OA/bank/invoice/relation detail 请求中 | drawer 内展示加载态。 |
| detail unavailable | detail API 返回 202 / `detailAvailable=false` | drawer 展示“详情暂不可用”和后端业务原因。 |
| rules drawer | 用户打开“支出流水无需开票规则设置” | 复用 pending invoice rules endpoint，保存后不重挂载父页面。 |
| view toggle | 用户切换“已完成 OA / 进行中 OA” | rows/filter-options 带 `view_mode`，切换时 page reset 为 1；按钮数量来自 rows `summary.viewCounts.completed/in_progress`。 |
| invoice display | row payload 含发票证据 | completed 与 in-progress 表格都显示发票列；发票号、发票方、日期 chip 和金额纵向展示，支持单发票详情和多发票 relation 明细。 |
| missing invoice display | row payload 缺少发票证据 | 发票列显示 `-`；候选流水确认前不把发票证据作为进行中 OA 主操作。 |
| auto reconcile | 页面具备写权限、rows/filter-options 已完成加载且 `oa_pending_payment` read model 为 fresh | 调用 `POST /api/oa-pending-payments/auto-reconcile-bank-transactions`；自动匹配 in-progress OA 与未配对支出流水，并对 completed/in-progress 中已匹配流水的 OA 自动写回 `t_payment_simple.pay_status=1`。read model 仍 refreshing/stale/unavailable 或 rows 加载失败时不得触发自动写命令；成功后等待 `oa_pending_payment` operation barrier fresh，再刷新 rows。 |
| bank link drawer | 用户在进行中 OA 视图勾选未写回 OA 后打开 | 调用 `GET /api/oa-pending-payments/bank-transaction-candidates` 并携带已选 OA 的 repeated `oa_row_ids`，后端按 OA 月份限定候选支出流水；支持全部、未配对、已配对、已关联进行中 OA 筛选；只有未配对流水可勾选。无 OA 上下文的旧调用才查询全部支出流水。提交后调用 `POST /api/oa-pending-payments/link-bank-transactions` 创建 OA 待付款独立 pending relation 和 bank claim；若支出合计等于 OA 金额且 `flow_id` 可解析，响应同时携带自动写回结果。 |
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
| `stale` / `source_mismatch` / `schema_mismatch` | payment-admitted OA projection、bank import、input invoice import、workbench relation 或 lifecycle source version 落后 | 入队重建；API 不返回 stale rows。 |
| `failed` | projection/worker refresh 失败 | App Status busy/blocked，页面等待运维恢复。 |
| `unavailable` | repository、queue、worker、OA dependency 不可用 | API 返回 unavailable/refreshing；不得伪造 fresh。 |

Scope 形态：

- `all`
- 月份 shard：`YYYY-MM`

Refresh 触发来源：

- OA sync / OA rebuild。
- 银行流水导入确认。
- 发票导入确认。
- Workbench 关系确认/撤回、OA 待付款自动匹配/写回、进行中 OA 抽屉关联支出流水、pending relation promotion、batch accounting relation change、turnover relation change。
- 待找发票规则保存和人工发票相关事件。
- invoice lifecycle refresh、App Health/readiness backfill。
- `startup_stale_scan` 默认关闭，且不直接刷新 OA 待付款 read model；只有后续 matching 结果真实变化并触发业务 lifecycle 时才间接影响。

Worker 流程：

1. 生产 API 发现 read model missing/stale/source mismatch，调用 `ReadModelRefreshGateway` 入队 `oa_pending_payment.read_model.refresh`。
2. `invoice-usage-collection` worker 消费事件。
3. refresh handler 先通过 durable queue 检查 event source_version 是否仍为当前 dirty scope；旧 event 返回 `skipped/stale_source_version`，不 rebuild、不 fan-out、不 complete dirty scope。
4. `scope_key=all` 先由 `InvoiceUsageCollectionSqlProjectionBuilder.list_oa_pending_payment_scope_shards` 展开月份 shard。
5. 月份 shard 调 `rebuild_oa_pending_payment_read_model_scope`，基于普通 completed OA projection、`t_payment_simple.flow_id` 准入后的进行中 OA Mongo 当前记录、bank/import facts、input invoices、Workbench relation 和 OA 待付款独立 pending relation 构建 rows。
6. projection 保存 `read_model.oa_pending_payment_rows` 和 `read_model.oa_pending_payment_scopes`，写入 source versions 和 row count。
7. App Status 读取 readiness/dirty/outbox/worker heartbeat，展示 `oa_pending_payments` domain 状态。

失败恢复：

1. 先看 `/api/app-health.app_status` 中 `oa_pending_payments` domain、`oa_pending_payment` read model scopes、dirty scopes、outbox 和 `invoice-usage-collection` worker。
2. 如果 OA sync 失败，先恢复 OA dependency / `oa.sync`，再重跑 `oa_pending_payment:all`。
3. 如果 source version mismatch，确认 payment-admitted OA projection、bank import fact、input invoice fact、workbench relation 和 invoice lifecycle 是否已经收敛。
4. 如果 detail 202/refreshing，先确认对应 row 所在月份 scope 是否 fresh，不手工查 live facts 补页面。
5. 如果 all scope 卡住，检查月份 shard readiness；all scope 不应同步重建历史全量。
6. 如果手工 rebuild 后又回退到旧 source version，先确认服务器 `invoice-usage-collection` worker 是否已经发布到当前 release；不要仅靠本地源码或一次性手工 rebuild 判定生产已闭环。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-17 | 补 OA pending read model stale event guard 和 all scope rows source-version 聚合 | 防止旧 worker/event 覆盖新 v3 投影，防止历史空 scope 污染默认 `all` 视图 freshness | `tests.test_invoice_usage_collection_sql_runtime`、HTTP smoke、Playwright 页面 smoke |
| 2026-06-17 | 新增 `completed/in_progress` OA 流程视图和进行中 OA 确认写回 | OA workflow status 投影、`view_mode` rows/filter-options、`confirm-paid` command、OA MySQL `t_payment_simple` 写回、前端三列表格与确认按钮 | `tests.test_oa_payment_status_service`、`tests.test_mongo_oa_adapter`、`tests.test_oa_pending_payment_service`、`tests.test_oa_pending_payment_command_service`、`tests.test_oa_pending_payment_api`、`web/src/test/OaPendingPaymentsPage.test.tsx` |
| 2026-06-22 | OA 待付款改为自动匹配和自动写回 | 页面进入后调用自动匹配/写回命令；in-progress OA 复用关联台 OA-bank 精确金额/精确合计规则匹配未配对支出流水；completed/in-progress 已有 active 支出流水 relation 时自动写回 `t_payment_simple.pay_status=1`；移除前端人工 confirm-paid 按钮，保留支出流水关联抽屉作为人工兜底 | `tests.test_oa_pending_payment_command_service`、`tests.test_oa_pending_payment_api`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts`、`web/e2e/oa-pending-payments-bank-link-flow.spec.ts` |
| 2026-06-22 | 自动匹配增加 read model fresh gate 与 API HTML fallback 防护 | rows/filter-options 仍 refreshing 或加载失败时不触发自动匹配/写回；前端 API 遇到根 `/api/*` 或 `/fin-ops/api/*` HTML fallback 时重试 canonical `/fin-ops-api/*`，避免路径错配把后台自动命令错误暴露给用户 | `web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/apiClient.test.ts` |
| 2026-06-23 | 右侧抽屉候选流水按已选 OA 月份收敛 | 进行中 OA 勾选后打开“关联支出流水”抽屉时，前端传 `oa_row_ids`；候选接口按 OA 月份读取支出流水，避免生产全量历史流水和 relation status 扫描导致抽屉长期加载。有 OA id 但无法解析月份时返回空候选，不退回 `all`。 | `tests.test_oa_pending_payment_command_service`、`tests.test_oa_pending_payment_api`、`web/src/test/OaPendingPaymentsPage.test.tsx` |
| 2026-06-22 | OA 待付款表格 OA 区域五列压缩 | OA 单元格按申请人/项目/申请事由/对方户名/金额五栏展示；申请人内部列和发票大列收窄，表格字号/间距压缩，继续保护真实 Chromium 无横向滚动 | `cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`、`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts --project=chromium` |
| 2026-06-22 | 进行中 OA 配对关系改为 OA 待付款独立事实源 | in-progress OA 自动匹配和抽屉关联写入 `app.oa_pending_payment_bank_relations` 与 `app.bank_transaction_relation_claims`，不进入关联台；Workbench projection 排除 active pending bank claim；OA sync 在 OA completed 后 promotion 为普通 Workbench relation 并释放 claim；migration 0073 撤回历史 `origin=oa_pending_payment_in_progress` Workbench active relation | `tests.test_oa_pending_payment_command_service`、`tests.test_oa_pending_payment_api`、`tests.test_oa_pending_payment_service`、`tests.test_workbench_relation_sql_projection`、`tests.test_oa_pending_payment_relation_promotion_service`、`tests.test_oa_projection_sync_service`、`tests.test_postgres_migrations` |
| 2026-06-17 | 补充 OA 待付款 Browser e2e，覆盖 rows 首屏、搜索、支付状态筛选、交易时间排序、OA/流水/发票详情抽屉和支出流水无需开票规则抽屉 | OA 待付款 UI 状态、rows/filter/detail/rules endpoint、Playwright smoke | `cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts` |
| 2026-06-18 | `oa.sync` 增加 OA 待付款 read model fan-out | 进行中 OA 当前记录进入 payment-admitted projection 后，`oa_pending_payment` 月份和 all scope 必须自动刷新，避免页面空数据 | `PYTHONPATH=backend/src python3 -m unittest tests.test_oa_projection_sync_service -v` |
| 2026-06-18 | completed 视图恢复发票证据列，in-progress 继续隐藏发票列 | 真实浏览器首屏必须看到发票号并可打开发票详情；进行中 OA 仍只展示候选流水确认主链路 | `cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`、`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts` |
| 2026-06-18 | OA/状态/流水主体表格改为内部三栏布局 | OA 单元格按申请人/项目/金额三栏展示，流水单元格按对方户名/金额/摘要三栏展示，支付状态列收窄并只显示未写回/已写回 | `cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx` |
| 2026-06-18 | completed/in-progress 统一四分组表格 UI | 两种流程视图都显示 OA、支付状态、流水、发票四个大分组；发票列纵向展示并移除价税合计 chip | `cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx` |
| 2026-06-18 | OA pending 四分组表格取消横向滚动 | 表格改为 100% 自适应百分比列宽，局部缩小字号/chip/按钮并允许换行 | `cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts` |
| 2026-06-18 | OA 待付款拆分 completed 统一 OA projection 与 in-progress `t_payment_simple.flow_id` 准入源 | completed/read model 读取普通 completed projection；in-progress 先按支付状态管理表 flow_id 准入再读取 OA Mongo 当前记录；未进入 `t_payment_simple` 的进行中 OA 不展示；已进入 `t_payment_simple` 的不同 flow id 不因 completed 中存在相似业务字段而排除；tab 数量来自 `summary.viewCounts` | `tests.test_oa_payment_status_service`、`tests.test_oa_pending_payment_service`、`tests.test_invoice_usage_collection_sql_runtime`、`web/src/test/OaPendingPaymentsPage.test.tsx` |
| 2026-06-18 | 拆分普通 completed OA projection 与 OA 待付款专用准入 projection | `app.oa_applications` 和其他页面只消费 completed/legacy OA；OA 待付款 read model 使用 `PaymentAdmittedOAProjectionAdapter` 根据 `t_payment_simple.flow_id` 精确读取 OA Mongo，`oa.sync` 只写 completed projection 并清理旧 in-progress 投影残留 | `tests.test_oa_payment_status_service`、`tests.test_oa_projection_sync_service`、`tests.test_oa_projection_sql_runtime`、`tests.test_invoice_usage_collection_sql_runtime`、`tests.test_workbench_relation_sql_projection` |
| 2026-06-18 | 进行中 OA 增加人工写回与右侧支出流水关联抽屉 | 历史记录：当时自动候选、自动决策和已有 active relation 只能点击确认后写回；抽屉默认展示全部支出流水但只允许选择未配对流水，提交只创建 Workbench relation、不写 MySQL。该口径已由 2026-06-22 自动匹配和自动写回替代 | `tests.test_oa_pending_payment_command_service`、`tests.test_oa_pending_payment_api`、`tests.test_workbench_sql_runtime.WorkbenchSqlProjectionRelationPayloadTests`、`web/src/test/OaPendingPaymentsPage.test.tsx` |
| 2026-06-11 | 关联台分组关系收敛 | 移除 `overpaid`/`merged_paid` 展示口径；多 OA/流水/发票 relation 合并为一条核对行；详情支持 `kind=oa` | `tests.test_oa_pending_payment_service`、`tests.test_invoice_lifecycle_policy`、`tests.test_oa_pending_payment_api`、`tests.test_invoice_usage_collection_sql_runtime`、`web/src/test/OaPendingPaymentsPage.test.tsx` 通过 |
| 2026-06-11 | 补齐测试闭环状态机 | OA 主行、付款状态、详情、UI、read model 和 worker 状态边界 | `tests.test_oa_pending_payment_service`、`tests.test_oa_pending_payment_api`、`tests.test_invoice_lifecycle_page_integration`、`tests.test_invoice_usage_collection_sql_runtime`、`tests.test_derived_data_lifecycle_service`、`tests.test_app_status_overview_service`、`tests.test_runtime_worker_registry`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts` 通过 |
