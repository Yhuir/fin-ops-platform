# Bank Account Balance 状态机

## Read Model 状态

| 状态 | 含义 | 合法来源 |
| --- | --- | --- |
| `fresh` | `read_model.bank_account_balances` 与 `bank_account_balance:all` scope summary 当前可用。 | Bank Details accounts SQL read path。 |
| `refreshing` | scope missing、dirty/outbox active、migration missing 或 worker 正在刷新。 | Bank Details accounts fresh gate、runtime queue、App Status。 |
| `stale` | scope/source/schema 不匹配，或已有 payload 不能证明当前 freshness。 | API fresh gate / App Status。 |
| `failed` | worker/runtime queue 对 `bank_account_balance.read_model.refresh` 记录失败。 | Runtime worker / App Status。 |
| `unavailable` | SQL repository、table 或 storage contract 不可用。 | API fresh gate / App Status。 |

## Worker 状态

- `bank-account-balance` 是 `bank_account_balance.read_model.refresh` 的 required worker。
- 当前 worker handler 只接受 `scope_type=bank_account_balance` 且 `scope_key=all`。
- `bank_account_balance:all` 当前是唯一 projection publish scope；不要在没有设计的情况下把它机械改成 month/account shard。

## 非法状态

- Bank Details accounts API 用 `bank_detail` rows 推导余额金额或余额 freshness。
- 页面/API 返回 `read_model_status=fresh`，但账户余额 table/scope summary missing、dirty、failed 或 schema/source 不匹配。
- `bank_account_balance` refresh 绕过 `ReadModelRefreshGateway` / scope policy / durable queue。
- `BankDetailReadModelRepositoryPort` 长期作为账户余额 read model 的正式 owner。

## 变更记录

| 日期 | 变更 | 状态机影响 | 测试/验证 |
| --- | --- | --- | --- |
| 2026-06-24 | 建立模块维护骨架，并选择为 Search 后的下一 read model pilot | 不改变运行时状态定义；记录当前 all-only worker/storage contract 和 repository port gap | `bash scripts/verify.sh docs` |
| 2026-06-24 | Repository port extraction | 不改变运行时状态定义；账户余额 projection save 和 Bank Details accounts SQL read path 收敛到 `BankAccountBalanceReadModelRepositoryPort` | `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry -v` |
| 2026-06-24 | Refresh/freshness/operation-barrier audit | 不改变运行时状态定义；确认 `bank_account_balance:all` 仍是唯一 publish scope，并把 refresh producer extraction 作为下一条实现边界 | `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry -v` |
| 2026-06-24 | Refresh producer extraction | 不改变运行时状态定义；`BankAccountBalanceReadModelRefreshProducer` 成为 all-only refresh enqueue 边界 | `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_runtime_worker_read_model_refresh_scopes tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_refresh_producer_helpers_stay_out_of_application tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli -v` |
| 2026-06-24 | Derived lifecycle executor extraction | 不改变运行时状态定义；derived lifecycle response assembly 移入 `BankAccountBalanceDerivedLifecycleExecutor` | `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_derived_lifecycle_executor tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_derived_lifecycle_uses_explicit_executor_boundary tests.test_bank_account_balance_read_model tests.test_runtime_worker_read_model_refresh_scopes tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli -v` |
