# Bank Account Balance 模块维护入口

- Module key: `bank-account-balance`
- 类型: 已下线 legacy read model 记录
- 当前页面入口: `/api/bank-details/accounts`
- 当前 owner: `bank-details`

## 当前边界

`bank_account_balance` 独立 read model runtime 已删除。Bank Details accounts API 现在直接通过 `BankDetailsService.list_accounts(...)` 从银行流水事实/银行明细 direct query 组装账户列表、余额和交易数，不读取 `read_model.bank_account_balances`，也不返回 `read_model_status`、`balance_read_model_status`、`read_model_scope_keys` 或 `refresh_enqueued`。

已删除的当前运行面：

- `bank_account_balance.read_model.refresh`
- `bank-account-balance` worker / RabbitMQ env / systemd deploy env
- `BankAccountBalanceProjectionBuilder`
- `BankAccountBalanceReadModelRefreshService`
- `BankAccountBalanceReadModelRefreshProducer`
- `BankAccountBalanceReadModelRepositoryPort`
- `BankAccountBalanceDerivedLifecycleExecutor`
- `app/bank_account_balance_backfill.py`
- read-model manifest、App Status read-model/job registration、runtime worker registry entry

历史 `read_model.bank_account_balances` migration 只作为数据库迁移历史存在，不是当前页面读取、freshness proof、worker refresh 或运维必启 worker。

## 修改前必读

- `docs/modules/bank-details/README.md`
- `docs/modules/bank-details/boundary-io.md`
- `docs/modules/bank-details/state-machine.md`
- `docs/architecture/direct-api-read-architecture.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`

## 当前守卫

- `tests/test_read_model_manifest.py::ReadModelManifestTests.test_bank_account_balance_manifest_is_removed`
- `tests/test_runtime_worker_registry.py::RuntimeWorkerRegistryTests.test_bank_account_balance_worker_registration_is_removed`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_refresh_path_is_removed`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`

## 后续规则

不得恢复独立账户余额 read model、freshness gate、dirty scope、refresh worker 或 backfill CLI。若账户余额 direct query 性能不足，优先在 Bank Details direct repository 上加 SQL 索引/查询优化；只有明确证明 direct SQL 无法满足 SLO 时，先更新 direct API 架构决策，再设计可删除短 TTL response cache。
