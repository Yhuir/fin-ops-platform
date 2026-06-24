# Bank Account Balance 模块维护入口

- Module key: `bank-account-balance`
- 类型: 资源/API 模块
- Route: `/api/bank-details/accounts`
- Page key: `bank-details`

## 修改前必读

- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/bank-details/README.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`：账户余额 projection builder。
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`：账户余额 read model repository port。
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`：`bank_account_balance.read_model.refresh` worker handler。
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`：Bank Details accounts API 的 query/freshness 映射。
- `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`：当前过渡期仍暴露 `list_bank_account_balances(...)`。
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`：当前 SQL table owner，包含 scope summary、list 和 save 方法。
- `backend/src/fin_ops_platform/app/bank_account_balance_backfill.py`：backfill/enqueue/worker-drain CLI。
- `backend/src/fin_ops_platform/services/read_model_manifest.py`：`bank_account_balance` read model manifest contract。
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`：`bank-account-balance` worker registration。

## 当前边界

`bank_account_balance` 是 Bank Details accounts 视图使用的独立 read model。余额金额、余额 freshness 和 balance read model status 不能由 `bank_detail` rows 替代；交易数量可以在页面筛选范围内参考 bank detail rows。

当前 worker 和 storage 只支持 `bank_account_balance:all`。虽然 scope policy 目前允许 month/all，后续不能直接引入 month/account scope，除非先完成 scope contract 设计、worker/storage/operation-barrier/test 更新。

## 当前缺口

- Projection save path 已通过 `BankAccountBalanceReadModelRepositoryPort.save_bank_account_balances(...)` 写入。
- Bank Details accounts SQL read path 已优先通过显式 `BankAccountBalanceReadModelRepositoryPort` 读取；`BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` 仍作为过渡兼容 fallback，后续必须审计移除或加固为 compat-only。
- Refresh producer 已通过 `BankAccountBalanceReadModelRefreshProducer` 收敛；Application、Bank Details service injection、runtime import-state fan-out、runtime derived lifecycle fan-out 和 backfill enqueue 均走该 producer。
- `_derived_lifecycle_bank_account_balance_executor(...)` 仍在 Application 中组装 response payload；下一条边界是 dedicated derived lifecycle executor extraction。
- `bank_account_balance:all` 是当前唯一 publish scope；scope policy 的 month/all 允许范围需要在 producer 后续 scope-contract slice 中收敛或明确拒绝。
- dedicated `bank_account_balance:all` operation barrier regression 尚未补齐。
- 真实 PostgreSQL/worker/App Status/high-row/browser evidence 尚未闭环。

## 本目录文件

- `state-machine.md`：账户余额 read model、worker 和非法状态。
- `tests.md`：七类测试适用性、现有测试入口和验证命令。
- `implementation-notes.md`：实施记录、边界决策、风险和后续事项。
