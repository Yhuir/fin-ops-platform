# 模块与页面

这是当前 App 的模块索引。每个模块只有一份说明，集中记录职责、输入输出、业务不变量、依赖和代码/测试入口。系统共性见[架构](../../ARCHITECTURE.md)。浏览器路径以 `/fin-ops` 为部署前缀，表中使用应用内路径。

| 模块 | 页面或入口 |
| --- | --- |
| [银行明细](bank-details/README.md) | `/bank-details` |
| [银行账户余额](bank-account-balance/README.md) | `/api/bank-details/accounts` |
| [流水规则批量处理](bank-flow-rule-batches/README.md) | `/bank-flow-rule-batches` |
| [批量账务](batch-accounting/README.md) | `/settings?section=batch-accounting` |
| [关联台](reconciliation-workbench/README.md) | `/` |
| [正式关联关系](workbench-relations/README.md) | `公共命令与读取边界` |
| [流水待找发票](pending-invoices/README.md) | `/pending-invoices` |
| [进项发票使用](input-invoice-usage/README.md) | `/input-invoice-usage` |
| [销项发票收款](output-invoice-collections/README.md) | `/output-invoice-collections` |
| [OA付款情况](oa-pending-payments/README.md) | `/oa-pending-payments` |
| [专票认证情况](tax-offset/README.md) | `/tax-offset` |
| [外部往来款](turnover-ledger/README.md) | `/turnover-ledger` |
| [成本](cost-statistics/README.md) | `/cost-statistics` |
| [ETC 票据](etc-tickets/README.md) | `/etc-tickets` |
| [银行流水导入](imports-bank-transactions/README.md) | `/imports/bank-transactions` |
| [发票导入](imports-invoices/README.md) | `/imports/invoices` |
| [ETC 发票导入](imports-etc-invoices/README.md) | `/imports/etc-invoices` |
| [现金账](cash/README.md) | `/cash` |
| [设置](settings/README.md) | `/settings` |
| [权限与审计](permissions-and-audit/README.md) | `公共请求边界` |
| [操作历史](operation-history/README.md) | `/operations/history` |
| [系统状态](app-health-operations/README.md) | `/operations/app-health` |
| [后台任务](runtime-workers/README.md) | `独立 worker 进程` |
| [领域任务通知](domain-events-lifecycle/README.md) | `跨模块任务边界` |
| [数据安全与重置](data-safety-reset/README.md) | `设置控制面` |
| [OA 集成](oa-integration/README.md) | `外部系统适配边界` |
| [应用壳与导航](app-shell-navigation/README.md) | `全局前端入口` |
| [公共财务表格](finance-table-system/README.md) | `共享前端组件` |
| [免 OA 批次 API](no-oa-bank-batches/README.md) | `/api/no-oa-bank-batches/*` |
