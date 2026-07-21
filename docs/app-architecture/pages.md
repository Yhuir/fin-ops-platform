# 页面架构与页面间影响关系

本文维护当前页面的路由、组件入口、API client、刷新来源和跨页面影响关系。页面自己的筛选、排序、分页、导出 shape 和 UI 状态可以留在页面 service 或组件里；业务规则、read model freshness 和跨页事实必须回到后端 policy/service/read boundary。

## 代码事实源

- 页面注册表：`web/src/app/pageRegistry.tsx`
- 路由入口：`web/src/app/router.tsx`
- 页面路由 host：`web/src/app/PageRouteHost.tsx`
- 页面运行时激活上下文：`web/src/contexts/PageRuntimeContext.tsx`
- 页面会话状态：`web/src/contexts/PageSessionStateContext.tsx`
- 表格会话：`web/src/hooks/useFinanceTableSession.ts`
- 侧边栏：`web/src/components/shell/sidebarItems.ts`（从页面注册表派生）
- 页面入口：`web/src/pages/*`
- API client：`web/src/features/*/api.ts`
- 操作闭环 API client：`web/src/features/operationBarrier/api.ts`
- 前端 domain event：`web/src/features/domainEvents.ts`
- 后端路由：`backend/src/fin_ops_platform/app/routes_*.py` 与仍在 `server.py` 的 legacy handler

## 页面分组

| 页面域 | 前端入口 | API / 后端 owner | 主要事实来源 | 刷新来源 |
| --- | --- | --- | --- | --- |
| 银企核销 / 关联台 | `web/src/pages/ReconciliationPage.tsx`、workbench 页面组件 | reconciliation/workbench routes、workbench service、read model service | 银行流水、OA 单据、发票、确认关系、active generation | 关系确认/撤回、导入确认、read model refresh、domain event |
| 银行明细 | `web/src/pages/BankDetailsPage.tsx` | bank detail routes、bank detail read model/query service | 银行流水、标签、业务对象关系、no-OA 状态 | 导入、标签规则、关系确认、no-OA 批处理 |
| 往来款管理 | `web/src/pages/TurnoverLedgerPage.tsx` | turnover ledger routes/service、workbench pair relation service | 外部往来候选、人工闭环、利息、项目归因、Workbench pair relation | 银行明细、关联台、人工闭环/撤回 |
| 待找发票 | `web/src/pages/PendingInvoicesPage.tsx` | pending invoice routes/query service | 支出/收入流水、进项发票、规则建议、选择已有发票关系、收入状态覆盖 | 进项导入、选择已有发票确认/撤回、收入状态覆盖、规则变更 |
| OA 待付款核对 | `web/src/pages/OaPendingPaymentsPage.tsx` | OA pending payments routes/query/command service | PostgreSQL completed OA、in-progress admission、payment-status snapshot、银行/发票事实、Workbench/pending relation、`oa_pending_payment` read model；页面/worker不直读Mongo/MySQL | OA sync原子snapshot、银行/发票关系变化、Workbench/pending relation、逐行写回；精确月份durable refresh |
| 税金抵扣 / 发票使用 | tax offset / invoice usage pages | invoice usage/read model routes | 已认证发票、使用状态、销项收款、ETC 发票 | 发票导入、认证状态、收款关系、backfill/refresh |
| ETC 业务批次 | ETC pages/components | ETC business batch routes/service、invoice PDF bundle service | ETC 票据、人工业务批次、导入草稿、OA 提交确认、草稿后批次发票合并下载 | ETC 导入、OA 草稿创建、人工提交确认、对象存储 PDF 读取与只读下载审计 |
| 成本统计 | cost statistics page | cost routes/query service | 项目、费用、发票、核销关系 | 项目范围变化、发票/流水关系变化 |
| 设置 / 账户 / 项目 | settings pages | settings/account/project routes | 用户、角色、项目状态、规则配置 | 配置保存、权限变化、数据重置 |
| App Health | shell/status components | app health routes、runtime queue、worker registry | queue、read model freshness、worker 状态、cache 状态 | worker heartbeat、refresh job、后台任务 |

## Global Runtime Status Plane 页面域

所有页面必须通过后端 domain registry 接入全局状态平面。新增页面、read model、worker 或后台任务类型时，需要同步更新 registry、readiness projection 和测试，不能只在前端页面里显示局部状态。

domain registry 是页面域入口；`AppStatusReadModelRegistry` 是 read model readiness 事实入口。表中的 read model 必须能从 `read_model.app_status_readiness` 或等价 active generation readiness 读取到 `fresh/missing/refreshing/stale/failed/unavailable` 等状态。没有 readiness 记录时，该 read model 进入 `missing`，对应 domain 不能显示 ready。

| domain key | route | read model / worker / task 来源 |
| --- | --- | --- |
| `workbench` | `/` | `workbench`、`workbench_relation`、workbench workers、workbench matching/rebuild jobs |
| `imports_bank_transactions` | `/imports/bank-transactions` | import worker、银行流水导入任务 |
| `imports_invoices` | `/imports/invoices` | import worker、发票导入任务 |
| `imports_etc_invoices` | `/imports/etc-invoices` | import worker、ETC 发票导入任务 |
| `bank_details` | `/bank-details` | `bank_detail`、`bank_account_balance`、bank detail workers |
| `pending_invoices` | `/pending-invoices` | `pending_invoice`、`search`、`pending-invoice` / `search` workers，旧 `search-pending` 兼容 worker |
| `oa_pending_payments` | `/oa-pending-payments` | `oa_pending_payment`、`oa-pending-payment`专属worker、OA sync |
| `input_invoice_usage` | `/input-invoice-usage` | `input_invoice_usage`、invoice usage collection worker |
| `output_invoice_collections` | `/output-invoice-collections` | `output_invoice_collection`、invoice usage collection worker；rows 展示 `workbench_relation` 统一关系中的 OA、收入流水和销项发票项 |
| `tax_offset` | `/tax-offset` | `tax_offset`、`tax-offset` worker，旧 `cost-tax` 兼容 worker |
| `cost_statistics` | `/cost-statistics` | `cost_statistics`、`cost-statistics` worker、`cost_statistics.read_model.refresh` durable queue |
| `bank_flow_rule_batches` | `/bank-flow-rule-batches` | `bank_flow_rule_batch`、bank-flow-rule-batch worker |
| `batch_accounting` | `/batch-accounting` | workbench relation read model |
| `turnover_ledger` | `/turnover-ledger` | `turnover_ledger`、turnover ledger worker |
| `etc_tickets` | `/etc-tickets` | ETC import jobs、ETC business batch manual OA status |
| `settings` | `/settings` | OA identity/state store/settings refresh runtime dependencies |
| `app_health_operations` | `/operations/app-health` | runtime health dependencies、workers、queue、state store |

`batch_accounting` 页面依赖 Workbench active payload 和 `workbench_relation` read model 判定已提交/未提交。`GET /api/batch-accounting` 必须透出 relation read model 的 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys` 和 `refresh_enqueued`；页面不能在 relation read model 非 fresh 时把空关系结果当作真实“全部未提交”。未提交 bucket 的 relation lookup 输入必须先收窄到批量账务银行候选和日常报销 OA 候选，`summary.submitted_count` 只能走年份级 count I/O；已提交 bucket 才读取完整 submitted relation DTO。

`bank_flow_rule_batches` 列表只通过 bank-flow 专属 paged read port 读取当前页和完整筛选范围聚合，默认 page size 50，不能先加载全部批次再由前端或 application 分页。未提交 rail 和批次只接纳 active 且 OA/发票双 false 的标签；submitted/history rail 使用实际历史聚合，不受当前规则隐藏。详情按成员 ID 一次 bulk 读取 canonical 银行流水。规则保存把 settings CAS 与精确受影响月份 dirty/outbox 原子提交；submit/withdraw/reset 以 command 原子提交为前台完成边界，页面立即更新本地 committed state；`bank_flow_rule_batch` freshness wait 与 reload 只在后台 reconcile，完整跨页 targets 仍通过既有 domain event 传递，不能把关联台或其它页面 freshness 重新变成当前页操作的同步依赖。

## 页面职责边界

- 页面可以决定筛选、排序、分页、空状态、导出列、drawer/dialog 状态。
- 页面写操作可以接入 `GlobalOperationOverlayProvider`，在 operation 完成前显示全屏阻塞层，防止用户在同一事实链路尚未收敛时继续操作。overlay 只包裹会改变后端事实或跨页面 read model 的操作；普通页面初始读取、筛选、分页、详情打开不使用全屏阻塞。
- 页面切换时 `PageRouteHost` 只挂载当前匹配 route；离开页面会卸载页面 React tree，不保留隐藏 DOM frame、mounted cache、TTL/LRU 策略或页面数据 snapshot。返回页面时页面重新 mount，并通过现有 API/read boundary 重新加载数据。
- 页面注册表不声明保活策略；`AppPageRoute` 只维护 `path`、`pageKey`、`component`、`preload()` 和 `end`。侧栏分组继续从页面注册表派生，不能在侧栏里维护第二份路由事实。
- `PageRuntimeContext` 仍为当前页面提供 active runtime context，供页面 hook 统一读取当前页面身份；因为旧页面会卸载，inactive 页面不再接收或延迟 replay finance domain event。
- 页面入口使用 lazy route chunks；`AppPageRoute.preload()` 和 `SidebarItem.preload()` 是 route chunk 预加载入口。侧边栏可以在 hover/focus/touch start 时预加载目标页，但点击导航仍由 React Router `Link` 负责。
- 页面会话状态只保存当前浏览器标签页内的轻量可恢复 UI，例如查询、筛选、分页、排序、tab、选中行、展开行和详情 drawer target；不保存滚动位置、列表 rows、read model payload、loading、一次性 toast、失败中的提交、权限事实或业务事实。
- 财务表格继续使用 `FinanceTable` 和 `useFinanceTableSession` 保存分页、排序、过滤、列和选择状态。表格滚动位置不写入页面 session，返回页面后由浏览器和组件默认布局决定。
- 页面不能重新定义发票生命周期、银行标签、对象 identity/dedup、项目成本归因、往来状态分类等业务口径。
- 多页面共享且需要 freshness/backfill 的结果，必须通过 policy/service + read boundary 暴露。
- 只有一个页面使用且规则简单的派生结果，可以留在页面 service；后续被复用时再上提。

## 前端事件关系

前端 domain event 用于同一浏览器会话内的页面刷新提示，不是事实源，也不负责保证最终一致性。

| 写入动作 | 事件影响 | 典型受影响页面 |
| --- | --- | --- |
| 银行流水导入确认 | 新流水、标签和统计需要刷新 | 银行明细、关联台、往来款、成本统计、App Health |
| OA/发票/ETC 导入确认 | 外部单据进入 canonical facts；确定性匹配若唯一安全则直接创建正式关系，并刷新相关 read model | 关联台、待找发票、OA 待付款、税金抵扣、ETC 批次 |
| 关系确认 / 撤回 | 对象关系、流水状态、发票使用状态变化 | 关联台、银行明细、待找发票、税金抵扣、往来款 |
| 外部往来手动闭环 | 同一往来组多笔银行流水形成 Turnover 手动闭环和 Workbench active relation；既有正式关系可原子扩展进同一 `turnover_manual_closure` case。active relation 继续驱动跨页面 linked ownership；关联台展示区由 relation 自身的显式完成合同决定 | 往来款、关联台、成本统计、搜索 |
| 标签/规则配置保存 | 标签判定和候选建议变化 | 银行明细、关联台、待找发票、成本统计 |
| 数据重置 / backfill | read model 状态和缓存失效 | 所有列表页、App Health |

## 后端间接影响关系

跨页面的稳定影响必须通过后端生命周期表达：

- `DerivedDataLifecycleService` 负责把业务事件转换成 dirty scope、outbox 和 read model refresh 请求。
- `RuntimeQueueRepository.enqueue_read_model_refresh(...)` 是 read model refresh 的标准入队边界。
- `ReadModelQueryGateway` 负责 freshness/status/enqueue 判断，页面不能绕过它读取旧 projection 并显示为 fresh。
- `/api/operation-barrier/status` 只读取 runtime snapshot 判定写操作后的目标 read model/scope 是否 fresh；它不写 queue、不重建 read model、不把状态改成 green。前端只有在 barrier fresh 且页面自身重新读取到 fresh payload 后，才能释放写操作 overlay。
- worker registry 定义哪些 read model 可被后台刷新、如何 drain、如何被 App Health 观测。

## 维护要求

新增页面或改页面事实来源时，更新本文件的页面分组和影响关系。新增跨页刷新、domain event、derived lifecycle 事件时，同时检查 `runtime-and-ownership.md`、`docs/dev/api-contracts.md` 和相关产品文档是否需要更新。
