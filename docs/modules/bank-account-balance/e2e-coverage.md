# Bank Account Balance E2E Coverage

当前不定义独立 Browser E2E coverage；账户余额用户行为归属 Bank Details。

| Spec ID | 状态 | 覆盖 | 说明 |
| --- | --- | --- | --- |
| `BANK-BAL-E2E-001` | `covered-by-bank-details` | `web/e2e/bank-details-initial-state.spec.ts`、`tests/test_bank_details_sql_runtime.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 accounts direct payload 和禁止恢复账户余额 read-model runtime。 |
