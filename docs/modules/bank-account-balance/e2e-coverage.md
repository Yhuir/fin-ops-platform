# Bank Account Balance E2E Coverage

当前不定义独立 Browser E2E coverage；本模块是 canonical query 资源。

| Spec ID | 状态 | 覆盖 | 说明 |
| --- | --- | --- | --- |
| `BANK-BAL-E2E-001` | `covered-api` | `tests/test_bank_account_balance_canonical_rows.py`、Bank Details route/frontend tests、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 canonical aggregate SQL、accounts DTO、零 projection/worker/barrier 和旧链删除守卫。 |

覆盖归属：

- Bank Details accounts UI 行为归属 `docs/modules/bank-details/e2e-coverage.md`。
- 银行导入后账户余额刷新链路归属 `docs/modules/imports-bank-transactions/e2e-coverage.md`。
- 本模块当前主要由 API/service/repository 与旧链负向测试保护，详见 `tests.md`。

缺口：

- 真实 PostgreSQL high-row/browser evidence 仍需 staging/production smoke。
- 若新增独立账户余额页面或新的用户交互入口，需要在本文件补 Spec ID 到测试的映射。
