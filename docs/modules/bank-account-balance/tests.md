# Bank Account Balance 测试矩阵

## 七类测试适用性

| 类别 | 适用性 | 当前入口 / 要求 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | 改账户 identity、latest balance、currency、排序或过滤规则时必须覆盖。 |
| 2. Service-layer tests | 适用 | projection builder、repository port、Bank Details accounts query/freshness wiring、refresh producer/worker 变化必须覆盖。 |
| 3. API contract tests | 条件适用 | `/api/bank-details/accounts` response shape、fresh/refreshing/unavailable、migration missing 或 permission 行为变化时必须覆盖。 |
| 4. Read model/cache/background job tests | 适用 | `bank_account_balance.read_model.refresh`、`bank_account_balance:all` dirty/outbox/readiness、worker completion 和 backfill CLI 必须覆盖。 |
| 5. Frontend component and interaction tests | 条件适用 | Bank Details accounts UI 或 loading/stale/error 展示变化时必须补前端测试。 |
| 6. End-to-end business-flow integration tests | 条件适用 | 银行导入 -> durable refresh -> account balance fresh -> Bank Details accounts 展示需要 staging/production 或 Browser smoke 证据。 |
| 7. Existing feature regression tests | 适用 | 保持 bank_detail 与 bank_account_balance 独立 manifest、scope/event/repository/test owner 和 Bank Details response shape。 |

## 当前测试入口

- `tests/test_bank_account_balance_read_model.py`
- `tests/test_bank_details_sql_runtime.py`
- `tests/test_bankdetail_backfill_cli.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_read_model_slo_smoke.py`
- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes`

## 2026-06-24 - repository port extraction

- 新增：`tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests::test_port_excludes_unrelated_read_model_methods`。
- 新增：`tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests::test_application_accounts_uses_account_balance_repository_port`。
- 覆盖：账户余额 repository port 只暴露 manifest-listed 方法；Bank Details accounts SQL read path 优先使用显式 account-balance port，不再把 Bank Detail read port 当作正常 owner。
- 保持不变：余额计算、account identity、API shape、worker event、scope、queue、权限、审计和前端行为。

## 下一 slice 必跑建议

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_read_model_slo_smoke -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## 未测风险

- 当前没有本地 `PGSQL_URL` 或 staging DB，真实 PostgreSQL worker drain、App Status readiness、high-row performance 和 Browser smoke evidence 仍需后续生产/环境验证。
- 当前 worker/storage 只支持 `bank_account_balance:all`；scope policy 的 month/all 允许范围需要在后续边界中收敛或明确兼容解释。
