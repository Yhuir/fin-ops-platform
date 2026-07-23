# Canonical Facts E2E 规格

本模块没有独立页面或用户可直接操作的 E2E 流程。它的 E2E 验收通过 owner 模块业务流程间接覆盖。

## 规格映射

| Spec ID | 业务流程 | Owner 模块 |
| --- | --- | --- |
| `CF-E2E-001` | 导入预览确认后写入 canonical facts，并触发受影响 read model 收敛 | `imports-invoices`、`imports-bank-transactions`、`imports-etc-invoices` |
| `CF-E2E-002` | 关联确认/撤回只写 relation facts/version/audit；写时零页面 fan-out，关联台和下游页面各自在访问时收敛 | `workbench-relations`、`reconciliation-workbench` |
| `CF-E2E-003` | 银行流水分类确认只写分类事实/version/audit；银行明细、搜索和相关 downstream 各自在访问时收敛 | `bank-details` |
| `CF-E2E-004` | 发票/收款/待付款生命周期写入后，下游页面通过 fresh read model 展示 | `pending-invoices`、`output-invoice-collections`、`oa-pending-payments` |

## 不适用原因

`canonical-facts` 是资源治理模块，不新增路由、页面、按钮、表单或浏览器交互。因此不维护独立 Playwright spec；新增或修改 E2E 时必须落到具体 owner 页面/功能模块。
