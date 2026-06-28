# Bank Account Balance 测试矩阵

## 七类测试适用性

| 类别 | 适用性 | 当前入口 / 要求 |
| --- | --- | --- |
| 1. Business core unit tests | 不单独适用 | 账户余额业务规则归属 `bank-details` direct query/service。 |
| 2. Service-layer tests | 适用为负向守卫 | 确认 producer/worker/projection/repository/manifest 不存在。 |
| 3. API contract tests | 归属 Bank Details | `/api/bank-details/accounts` response shape 在 Bank Details 测试中覆盖。 |
| 4. Read model/cache/background job tests | 适用为负向守卫 | 不得出现 `bank_account_balance.read_model.refresh`、worker、scope policy 或 App Status registration。 |
| 5. Frontend component and interaction tests | 归属 Bank Details | 账户余额 UI 在 Bank Details 页面测试中覆盖。 |
| 6. End-to-end business-flow integration tests | 归属 Bank Details/imports | 银行导入后账户余额 direct payload 在 Bank Details/import flow 覆盖。 |
| 7. Existing feature regression tests | 适用 | 防止恢复 legacy read model path，保持 direct API。 |

## 当前测试入口

- `tests/test_bank_details_sql_runtime.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_write_operation_slo_audit.py`

## 2026-06-28 - legacy read model runtime 删除

- 删除：`tests/test_bank_account_balance_read_model.py`
- 删除：`tests/test_bank_account_balance_derived_lifecycle_executor.py`
- 删除：`tests/test_bankdetail_backfill_cli.py`
- 更新：runtime worker registry、manifest、runtime lifecycle、SLO audit、deploy/RabbitMQ/monitoring guard 测试。
- 覆盖：当前代码不再有账户余额 read-model worker/projection/repository/backfill/manifest/App Status/deploy env。
