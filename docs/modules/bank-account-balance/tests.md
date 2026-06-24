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

## 2026-06-24 - refresh/freshness/operation-barrier audit

- 新增测试：无。本轮是 analysis/accounting slice，不改运行时代码或测试 contract。
- 复用覆盖：account-balance projection/repository port、Bank Details SQL runtime、backfill CLI、manifest 和 runtime worker registry tests。
- 审计结论：下一条实现边界需要新增 `BankAccountBalanceReadModelRefreshProducer`；后续还需补 dedicated `bank_account_balance:all` operation barrier regression、all-only scope contract guard 和兼容 fallback 处理。

## 2026-06-24 - refresh producer extraction

- 新增：`tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests::test_refresh_producer_enqueues_all_scope_through_gateway`。
- 新增：`tests/test_bank_account_balance_read_model.py::BankAccountBalanceProjectionTests::test_refresh_producer_returns_false_when_gateway_unavailable`。
- 新增：`tests/test_runtime_worker_read_model_refresh_scopes.py::RuntimeWorkerReadModelRefreshScopeTests::test_import_state_bank_account_balance_refresh_uses_producer_boundary`。
- 新增：`tests/test_runtime_worker_read_model_refresh_scopes.py::RuntimeWorkerReadModelRefreshScopeTests::test_lifecycle_bank_account_balance_refresh_uses_all_only_producer_boundary`。
- 新增：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_account_balance_refresh_producer_helpers_stay_out_of_application`。
- 覆盖：Application、Bank Details service injection、runtime import-state、runtime derived lifecycle 和 backfill enqueue 均走 `BankAccountBalanceReadModelRefreshProducer`，且 producer 保持 `bank_account_balance:all` all-only contract。

## 2026-06-24 - derived lifecycle executor extraction

- 新增：`tests/test_bank_account_balance_derived_lifecycle_executor.py`。
- 新增：`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_account_balance_derived_lifecycle_uses_explicit_executor_boundary`。
- 覆盖：`BankAccountBalanceDerivedLifecycleExecutor` 保持 `deleted_counts`、`invalidated_scopes=["all"]` 和 enqueue 成功/失败的 `enqueued_jobs` payload shape，且 Application 不再拥有旧 helper。

## 2026-06-24 - all-only scope contract

- 新增：`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_account_balance_policy_accepts_only_all_scope`。
- 覆盖：`ReadModelRefreshGateway` 对 `bank_account_balance` 只接受 `all`，拒绝 month/account/active scope，且拒绝发生在 durable enqueue 前。

## 2026-06-24 - operation barrier regression

- 新增：`tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests::test_bank_account_balance_all_dirty_scope_keeps_accounts_target_refreshing`。
- 新增：`tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests::test_bank_account_balance_all_outbox_pending_keeps_accounts_target_refreshing`。
- 新增：`tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests::test_other_read_model_outbox_pending_does_not_block_bank_account_balance_all_target`。
- 覆盖：`bank_account_balance:all` dirty/readiness 和 outbox pending 都会阻止 accounts freshness target 被误判为 fresh，且无关 read model outbox 不影响账户余额目标。

## 下一 slice 必跑建议

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## 未测风险

- 当前没有本地 `PGSQL_URL` 或 staging DB，真实 PostgreSQL worker drain、App Status readiness、high-row performance 和 Browser smoke evidence 仍需后续生产/环境验证。
- 当前 worker/storage/gateway 只支持 `bank_account_balance:all`；dedicated operation barrier regression 已补齐，但 Bank Detail fallback quarantine 仍需后续闭环。
