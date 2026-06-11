# Business Flows Workflow State

## 当前阶段

阶段 6 已完成：预检、文档生成、一致性审查和最终验证均已完成。

## 已确认页面清单

以 `web/src/app/pageRegistry.tsx` 为页面事实源，本目录覆盖以下非操作系统页面：

| Route | Page key | 文档 |
| --- | --- | --- |
| `/` | `reconciliation-workbench` | `reconciliation-workbench.md` |
| `/tax-offset` | `tax-offset` | `tax-offset.md` |
| `/cost-statistics` | `cost-statistics` | `cost-statistics.md` |
| `/bank-details` | `bank-details` | `bank-details.md` |
| `/pending-invoices` | `pending-invoices` | `pending-invoices.md` |
| `/input-invoice-usage` | `input-invoice-usage` | `input-invoice-usage.md` |
| `/oa-pending-payments` | `oa-pending-payments` | `oa-pending-payments.md` |
| `/output-invoice-collections` | `output-invoice-collections` | `output-invoice-collections.md` |
| `/no-oa-bank-batches` | `no-oa-bank-batches` | `no-oa-bank-batches.md` |
| `/batch-accounting` | `batch-accounting` | `batch-accounting.md` |
| `/turnover-ledger` | `turnover-ledger` | `turnover-ledger.md` |
| `/etc-tickets` | `etc-tickets` | `etc-tickets.md` |
| `/settings` | `settings` | `settings.md` |
| `/imports/bank-transactions` | `imports.bank-transactions` | `imports-bank-transactions.md` |
| `/imports/invoices` | `imports.invoices` | `imports-invoices.md` |
| `/imports/etc-invoices` | `imports.etc-invoices` | `imports-etc-invoices.md` |

## 排除页面

| Route | Page key | 原因 |
| --- | --- | --- |
| `/operations/app-health` | `app-health-operations` | 系统状态和运维页面，不属于业务页面；只在总览中说明它接收后台健康状态，不单独展开业务流程。 |

## 已生成文档清单

- `_workflow-state.md`
- `README.md`
- `reconciliation-workbench.md`
- `tax-offset.md`
- `cost-statistics.md`
- `bank-details.md`
- `pending-invoices.md`
- `input-invoice-usage.md`
- `oa-pending-payments.md`
- `output-invoice-collections.md`
- `no-oa-bank-batches.md`
- `batch-accounting.md`
- `turnover-ledger.md`
- `etc-tickets.md`
- `settings.md`
- `imports-bank-transactions.md`
- `imports-invoices.md`
- `imports-etc-invoices.md`

## 待处理页面清单

无。下一步只做一致性审查、补洞和验证。

## 发现的页面/模块命名差异

- 导入页在 `pageRegistry.tsx` 中使用点号 page key：`imports.bank-transactions`、`imports.invoices`、`imports.etc-invoices`；模块文档使用连字符 module key：`imports-bank-transactions`、`imports-invoices`、`imports-etc-invoices`。业务文档文件名采用模块文档的连字符命名。
- `docs/app-architecture/pages.md` 的银企核销入口描述包含旧名 `ReconciliationPage.tsx`，当前页面注册表的实际入口是 `ReconciliationWorkbenchPage.tsx`；业务文档以 route `/` 和 page key `reconciliation-workbench` 为准。

## 校验结果

- 当前分支：`main`。
- 页面清单已与 `docs/modules/README.md` 和 `docs/app-architecture/pages.md` 对照。
- 当前 worktree 存在大量既有未提交改动；本工作只新增 `docs/business-flows/` 并在后续必要时修改 `docs/index.md`。
- `docs/index.md` 已登记 `business-flows/`。
- 所有非操作系统页面已生成对应业务文档；`/operations/app-health` 已按排除规则仅在总览说明。
- 16 个业务页面文档均包含“页面目的、主要数据、页面流程、状态和异常、输出和影响、相关页面”六个章节。
- 未发现未完成标记。
- 未发现指定开发细节词命中。
- 页面注册表共有 17 个路由，其中 `/operations/app-health` 按规则排除；业务页面文档共 16 篇，覆盖数匹配。
- `git diff --check` 通过。
- 尾随空白检查通过。

## 下一轮 Prompt

无需下一轮 prompt；主控流程已闭环完成。
