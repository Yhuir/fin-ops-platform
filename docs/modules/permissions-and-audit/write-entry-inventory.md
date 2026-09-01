# 页面访问路由清单

账户权限只决定“能否进入页面”，不再逐按钮维护账号级写入口矩阵。页面内写入能力由各业务模块、系统健康状态和后端业务规则负责。

## 可分配页面

`reconciliation-workbench`、`cost-statistics`、`bank-details`、`oa-pending-payments`、`bank-flow-rule-batches`、`batch-accounting`、`turnover-ledger`、`etc-tickets`、`tax-offset`、`pending-invoices`、`input-invoice-usage`、`output-invoice-collections`、`settings`、`app-health-operations`、`imports.bank-transactions`、`imports.invoices`、`imports.etc-invoices`。

## 管理员专属页面与接口

- `operation-history`
- `/api/workbench/settings/access-control*`
- `/api/workbench/settings/oa-applicant-credentials*`
- `/api/workbench/settings/data-reset*`

## 维护规则

- 页面 registry 事实源：`web/src/app/pageRegistry.tsx` 与 `backend/.../access_control_service.py`。
- API→页面映射事实源：`backend/src/fin_ops_platform/app/route_access_policy.py`。
- 新增页面或 protected API 时同步两处 registry、路由映射和 `tests/test_permissions_write_entry_inventory.py`。
- 未知 protected route fail closed；不得通过通配 fallback、OA role 或前端隐藏绕过。
- `/api/background-jobs` 是跨页面共享状态；拥有任一可分配页面即可读取，但具体业务 job 创建仍由其页面 API 权限约束。
