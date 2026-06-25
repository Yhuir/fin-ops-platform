# Bank Account Balance E2E Coverage

当前不定义独立 Browser E2E coverage；本模块是资源/API read model。

| Spec ID | 状态 | 覆盖 | 说明 |
| --- | --- | --- | --- |
| `BANK-BAL-E2E-001` | `covered-api` | `tests/test_bank_account_balance_api.py`、`tests/test_bank_account_balance_read_model.py`、`tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 `/api/bank-details/accounts` 账户余额 read model contract、`bank_account_balance:all` scope policy、worker registry、operation barrier 和禁止回退到 bank detail repository port。 |

覆盖归属：

- Bank Details accounts UI 行为归属 `docs/modules/bank-details/e2e-coverage.md`。
- 银行导入后账户余额刷新链路归属 `docs/modules/imports-bank-transactions/e2e-coverage.md`。
- 本模块当前主要由 API/service/read model/worker 测试保护，详见 `tests.md`。

缺口：

- 真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍需 staging/production smoke。
- 若新增独立账户余额页面或新的用户交互入口，需要在本文件补 Spec ID 到测试的映射。
