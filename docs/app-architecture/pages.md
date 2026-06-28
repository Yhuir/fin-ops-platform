# 页面架构与页面间影响关系

本文维护当前页面的路由、组件入口、API client、刷新来源和跨页面影响关系。页面自己的筛选、排序、分页、导出 shape 和 UI 状态可以留在页面 service 或组件里；业务规则和跨页事实必须回到后端 policy/service/read boundary。

读架构见 `../architecture/direct-api-read-architecture.md`：所有页面通过 direct API 读取和组装数据，不依赖页面 read model freshness。本文中仍出现的 read model、operation barrier 和 freshness 字段只表示历史迁移对象、负向 guard 或数据库历史表，不是当前设计方向。

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
- 操作闭环 API client：已从前端删除；backend operation barrier endpoint/service 已删除。
- 前端 domain event：`web/src/features/domainEvents.ts`
- 后端路由：`backend/src/fin_ops_platform/app/routes_*.py` 与仍在 `server.py` 的 legacy handler

## 页面分组

| 页面域 | 前端入口 | API / 后端 owner | 主要事实来源 | 刷新来源 |
| --- | --- | --- | --- | --- |
| 银企核销 / 关联台 | `web/src/pages/ReconciliationPage.tsx`、workbench 页面组件 | reconciliation/workbench routes、workbench service | 银行流水、OA 单据、发票、确认关系、direct workbench payload | 关系确认/撤回、导入确认、direct refetch、domain event |
| 银行明细 | `web/src/pages/BankDetailsPage.tsx` | bank detail routes、BankDetailsApplicationService / BankDetailsService | 银行流水事实、直接分类事实、业务对象关系、no-OA 状态 | 导入、标签规则、关系确认、no-OA 批处理后页面 direct API 重读 |
| 往来款管理 | `web/src/pages/TurnoverLedgerPage.tsx` | turnover ledger routes/service、workbench pair relation service | 外部往来候选、人工闭环、利息、项目归因、Workbench pair relation | 银行明细、关联台、人工闭环/撤回 |
| 待找发票 | `web/src/pages/PendingInvoicesPage.tsx` | pending invoice routes/query service | 支出/收入流水、进项发票、规则建议、选择已有发票关系、收入状态覆盖 | 进项导入、选择已有发票确认/撤回、收入状态覆盖、规则变更 |
| OA 待付款核对 | `web/src/pages/OaPendingPaymentsPage.tsx` | OA pending payments routes/query/command service | completed: 普通 OA completed projection；in-progress: OA MySQL `t_payment_simple.flow_id` 准入 + payment-admitted OA projection；OA 待付款 workflow status、付款流水、进项发票、Workbench relation | OA 导入/同步、银行流水导入、发票关系变化、Workbench relation 确认/撤回、进行中 OA 确认已支付 |
| 税金抵扣 / 发票使用 | tax offset / invoice usage pages | invoice usage/tax routes and query services | 已认证发票、使用状态、销项收款、ETC 发票 | 发票导入、认证状态、收款关系、direct refetch/cache warmup |
| ETC 业务批次 | ETC pages/components | ETC business batch routes/service | ETC 票据、人工业务批次、导入草稿、OA 提交确认 | ETC 导入、OA 草稿创建、人工提交确认 |
| 成本统计 | cost statistics page | cost routes/query service | 项目、费用、发票、核销关系 | 项目范围变化、发票/流水关系变化 |
| 设置 / 账户 / 项目 | settings pages | settings/account/project routes | 用户、角色、项目状态、规则配置 | 配置保存、权限变化、数据重置 |
| App Health | shell/status components | app health routes、runtime queue、worker registry | queue、worker 状态、cache 状态、真实后台任务 | worker heartbeat、background jobs、依赖状态 |

## Global Runtime Status Plane 页面域

目标 App Health / Global Runtime Status Plane 不再以页面 read model readiness 作为状态事实源。新增页面不需要新增 read model registry；只在引入真实后台任务、worker 或外部依赖时同步 registry 和测试。

下面表格记录当前页面域与真实后台任务/外部依赖。页面 read model worker 已下线；不得把 read model key 加回 App Status domain registry。

| domain key | route | direct payload / runtime evidence |
| --- | --- | --- |
| `workbench` | `/` | direct workbench payload、workbench matching job |
| `imports_bank_transactions` | `/imports/bank-transactions` | import worker、银行流水导入任务 |
| `imports_invoices` | `/imports/invoices` | import worker、发票导入任务 |
| `imports_etc_invoices` | `/imports/etc-invoices` | import worker、ETC 发票导入任务 |
| `bank_details` | `/bank-details` | direct bank detail APIs；无 active bank_detail / bank_account_balance read-model worker |
| `pending_invoices` | `/pending-invoices` | direct pending invoice payload；Search read-model worker 已删除 |
| `oa_pending_payments` | `/oa-pending-payments` | direct OA pending payload、OA sync |
| `input_invoice_usage` | `/input-invoice-usage` | direct input invoice usage payload |
| `output_invoice_collections` | `/output-invoice-collections` | direct output invoice collection payload；rows 展示 `workbench_relation` 统一关系中的 OA、收入流水和销项发票项 |
| `tax_offset` | `/tax-offset` | direct tax offset payload、tax cache warmup job |
| `cost_statistics` | `/cost-statistics` | direct cost statistics payload、cache warmup jobs |
| `no_oa_bank_batches` | `/no-oa-bank-batches` | direct no-OA batch payload |
| `batch_accounting` | `/batch-accounting` | direct relation query service |
| `turnover_ledger` | `/turnover-ledger` | direct turnover grouped payload |
| `etc_tickets` | `/etc-tickets` | ETC import jobs、ETC business batch manual OA status |
| `settings` | `/settings` | OA identity/state store/settings refresh runtime dependencies |
| `app_health_operations` | `/operations/app-health` | runtime health dependencies、workers、queue、state store |

`batch_accounting` 通过 direct relation query service 判定已提交/未提交；`GET /api/batch-accounting` 不透出 relation read model freshness 字段。

## 页面职责边界

- 页面可以决定筛选、排序、分页、空状态、导出列、drawer/dialog 状态。
- 页面写操作可以接入 `GlobalOperationOverlayProvider`，在 operation 完成前显示全屏阻塞层，防止用户在同一事实链路尚未完成时继续操作。目标 direct API 下，overlay 等待写 API 和随后的 direct GET；页面不得重新等待跨页面 read model operation barrier。普通页面初始读取、筛选、分页、详情打开不使用全屏阻塞。
- 页面切换时 `PageRouteHost` 只挂载当前匹配 route；离开页面会卸载页面 React tree，不保留隐藏 DOM frame、mounted cache、TTL/LRU 策略或页面数据 snapshot。返回页面时页面重新 mount，并通过 direct API 重新加载数据。
- 页面注册表不声明保活策略；`AppPageRoute` 只维护 `path`、`pageKey`、`component`、`preload()` 和 `end`。侧栏分组继续从页面注册表派生，不能在侧栏里维护第二份路由事实。
- `PageRuntimeContext` 仍为当前页面提供 active runtime context，供页面 hook 统一读取当前页面身份；因为旧页面会卸载，inactive 页面不再接收或延迟 replay finance domain event。
- 页面入口使用 lazy route chunks；`AppPageRoute.preload()` 和 `SidebarItem.preload()` 是 route chunk 预加载入口。侧边栏可以在 hover/focus/touch start 时预加载目标页，但点击导航仍由 React Router `Link` 负责。
- 页面会话状态只保存当前浏览器标签页内的轻量可恢复 UI，例如查询、筛选、分页、排序、tab、选中行、展开行和详情 drawer target；不保存滚动位置、列表 rows、read model payload、loading、一次性 toast、失败中的提交、权限事实或业务事实。
- 财务表格继续使用 `FinanceTable` 和 `useFinanceTableSession` 保存分页、排序、过滤、列和选择状态。表格滚动位置不写入页面 session，返回页面后由浏览器和组件默认布局决定。
- 页面不能重新定义发票生命周期、银行标签、对象 identity/dedup、项目成本归因、往来状态分类等业务口径。
- 多页面共享结果必须通过 policy/service + direct read boundary 暴露；legacy freshness/backfill 结果只作为历史对象或负向 guard 保留。
- 只有一个页面使用且规则简单的派生结果，可以留在页面 service；后续被复用时再上提。

## 前端事件关系

前端 domain event 用于同一浏览器会话内的页面刷新提示，不是事实源，也不负责保证最终一致性。

| 写入动作 | 事件影响 | 典型受影响页面 |
| --- | --- | --- |
| 银行流水导入确认 | 新流水、标签和统计需要刷新 | 银行明细、关联台、往来款、成本统计、App Health |
| OA/发票/ETC 导入确认 | 外部单据和候选关系变化 | 关联台、待找发票、OA 待付款、税金抵扣、ETC 批次 |
| 关系确认 / 撤回 | 对象关系、流水状态、发票使用状态变化 | 关联台、银行明细、待找发票、税金抵扣、往来款 |
| 外部往来手动闭环 | 同一往来组多笔银行流水形成 Turnover 手动闭环和 Workbench pair relation；既有 OA-bank relation 可合并进同一 `turnover_manual_closure` active case；确认后外部往来台账显示“收支闭环”，关联台保留同一个 canonical case/evidence，未补齐 OA + 银行 + 发票三栏前留在 open/candidate，三栏完整后才进入 paired | 往来款、关联台、成本统计、搜索 |
| 标签/规则配置保存 | 标签判定和候选建议变化 | 银行明细、关联台、待找发票、成本统计 |
| 数据重置 / backfill | direct API 重新读取，cache/历史投影清理 | 所有列表页、App Health |

## 后端间接影响关系

跨页面的稳定影响必须通过后端 lifecycle、direct query service 或真实后台任务表达：

- 目标 direct API 下，业务事件影响由下次 GET 的 direct repository 查询体现；真实异步任务通过 background job 状态体现。
- Legacy `RuntimeQueueRepository.enqueue_read_model_refresh(...)`、`ReadModelQueryGateway` 和 backend operation barrier endpoint/service 已删除；前端页面不再调用 operation barrier。
- worker registry 只应保留真实后台任务 worker；页面 read model refresh worker 是删除对象。

## 维护要求

新增页面或改页面事实来源时，更新本文件的页面分组和影响关系。新增跨页刷新、domain event、derived lifecycle 事件时，同时检查 `runtime-and-ownership.md`、`docs/dev/api-contracts.md` 和相关产品文档是否需要更新。
