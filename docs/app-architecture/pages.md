# 页面架构与页面间影响关系

本文维护当前页面的路由、组件入口、API client、刷新来源和跨页面影响关系。页面自己的筛选、排序、分页、导出 shape 和 UI 状态可以留在页面 service 或组件里；业务规则、read model freshness 和跨页事实必须回到后端 policy/service/read boundary。

## 代码事实源

- 路由入口：`web/src/app/router.tsx`
- 侧边栏：`web/src/components/shell/sidebarItems.ts`
- 页面入口：`web/src/pages/*`
- API client：`web/src/features/*/api.ts`
- 前端 domain event：`web/src/features/domainEvents.ts`
- 后端路由：`backend/src/fin_ops_platform/app/routes_*.py` 与仍在 `server.py` 的 legacy handler

## 页面分组

| 页面域 | 前端入口 | API / 后端 owner | 主要事实来源 | 刷新来源 |
| --- | --- | --- | --- | --- |
| 银企核销 / 关联台 | `web/src/pages/ReconciliationPage.tsx`、workbench 页面组件 | reconciliation/workbench routes、workbench service、read model service | 银行流水、OA 单据、发票、确认关系、active generation | 关系确认/撤回、导入确认、read model refresh、domain event |
| 银行明细 | `web/src/pages/BankDetailsPage.tsx` | bank detail routes、bank detail read model/query service | 银行流水、标签、业务对象关系、no-OA 状态 | 导入、标签规则、关系确认、no-OA 批处理 |
| 往来款管理 | `web/src/pages/TurnoverLedgerPage.tsx` | turnover ledger routes/service、workbench pair relation service | 外部往来候选、人工闭环、利息、项目归因、Workbench pair relation | 银行明细、关联台、人工闭环/撤回 |
| 待找发票 | `web/src/pages/PendingInvoicesPage.tsx` | pending invoice routes/query service | 支出流水、进项发票、规则建议、人工关系 | 进项导入、关系确认/撤回、规则变更 |
| OA 待付款核对 | `web/src/pages/OaPendingPaymentsPage.tsx` | OA pending payments routes/query service | OA 待付款、付款流水、进项发票、SQL read model | OA 导入、银行流水导入、发票关系变化 |
| 税金抵扣 / 发票使用 | tax offset / invoice usage pages | invoice usage/read model routes | 已认证发票、使用状态、销项收款、ETC 发票 | 发票导入、认证状态、收款关系、backfill/refresh |
| ETC 业务批次 | ETC pages/components | ETC business batch routes/service | ETC 票据、OA 自动检测、人工业务批次、导入草稿 | ETC 导入、OA 匹配、人工确认/撤销 |
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
| `pending_invoices` | `/pending-invoices` | `pending_invoice`、`search`、search-pending worker |
| `oa_pending_payments` | `/oa-pending-payments` | `oa_pending_payment`、invoice usage collection worker、OA sync |
| `input_invoice_usage` | `/input-invoice-usage` | `input_invoice_usage`、invoice usage collection worker |
| `output_invoice_collections` | `/output-invoice-collections` | `output_invoice_collection`、invoice usage collection worker |
| `tax_offset` | `/tax-offset` | `tax_offset`、cost-tax worker |
| `cost_statistics` | `/cost-statistics` | `cost_statistics`、cost-tax worker、cache warmup jobs |
| `no_oa_bank_batches` | `/no-oa-bank-batches` | `no_oa_bank_batch`、no-OA worker |
| `batch_accounting` | `/batch-accounting` | workbench relation read model |
| `turnover_ledger` | `/turnover-ledger` | `turnover_ledger`、turnover ledger worker |
| `etc_tickets` | `/etc-tickets` | ETC OA detection worker、ETC import jobs |
| `settings` | `/settings` | OA identity/state store/settings refresh runtime dependencies |
| `app_health_operations` | `/operations/app-health` | runtime health dependencies、workers、queue、state store |

## 页面职责边界

- 页面可以决定筛选、排序、分页、空状态、导出列、drawer/dialog 状态。
- 页面不能重新定义发票生命周期、银行标签、对象 identity/dedup、项目成本归因、往来状态分类等业务口径。
- 多页面共享且需要 freshness/backfill 的结果，必须通过 policy/service + read boundary 暴露。
- 只有一个页面使用且规则简单的派生结果，可以留在页面 service；后续被复用时再上提。

## 前端事件关系

前端 domain event 用于同一浏览器会话内的页面刷新提示，不是事实源，也不负责保证最终一致性。

| 写入动作 | 事件影响 | 典型受影响页面 |
| --- | --- | --- |
| 银行流水导入确认 | 新流水、标签和统计需要刷新 | 银行明细、关联台、往来款、成本统计、App Health |
| OA/发票/ETC 导入确认 | 外部单据和候选关系变化 | 关联台、待找发票、OA 待付款、税金抵扣、ETC 批次 |
| 关系确认 / 撤回 | 对象关系、流水状态、发票使用状态变化 | 关联台、银行明细、待找发票、税金抵扣、往来款 |
| 外部往来手动闭环 | 同一往来组两条银行流水形成 Turnover 手动闭环和 Workbench pair relation | 往来款、关联台、成本统计、搜索 |
| 标签/规则配置保存 | 标签判定和候选建议变化 | 银行明细、关联台、待找发票、成本统计 |
| 数据重置 / backfill | read model 状态和缓存失效 | 所有列表页、App Health |

## 后端间接影响关系

跨页面的稳定影响必须通过后端生命周期表达：

- `DerivedDataLifecycleService` 负责把业务事件转换成 dirty scope、outbox 和 read model refresh 请求。
- `RuntimeQueueRepository.enqueue_read_model_refresh(...)` 是 read model refresh 的标准入队边界。
- `ReadModelQueryGateway` 负责 freshness/status/enqueue 判断，页面不能绕过它读取旧 projection 并显示为 fresh。
- worker registry 定义哪些 read model 可被后台刷新、如何 drain、如何被 App Health 观测。

## 维护要求

新增页面或改页面事实来源时，更新本文件的页面分组和影响关系。新增跨页刷新、domain event、derived lifecycle 事件时，同时检查 `runtime-and-ownership.md`、`docs/dev/api-contracts.md` 和相关产品文档是否需要更新。
