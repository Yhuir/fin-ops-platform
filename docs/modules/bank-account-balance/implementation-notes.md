# Bank Account Balance 实施记录

## 2026-06-24 - selected as next modular IO read model pilot

- 目标：在 Search local support 进入 `production-evidence-deferred` 后，选择下一个非 Go read model pilot。
- 决策：选择 `bank_account_balance`，下一条边界为 `read-models:bank-account-balance-repository-port-extraction`。
- 理由：它是剩余已知 read model 候选，服务 Bank Details accounts，参与银行导入 write-operation SLO，并且必须与 `bank_detail` rows 保持余额金额/readiness 独立。
- 首切范围：新增窄 `BankAccountBalanceReadModelRepositoryPort`，只暴露 manifest 登记的 `bank_account_balance_scope_summary(...)`、`list_bank_account_balances(...)` 和 `save_bank_account_balances(...)`，并让 projection save 与 accounts SQL read path 使用该 port。
- 非目标：不改余额计算、account identity、API shape、worker event、queue schema、权限、审计、frontend behavior、Go/Fiber 或 Go Worker。
- 状态：`bank_account_balance` 是 `implementation-gap-open`；本记录不是 module closure。

## 2026-06-24 - repository port extraction

- 目标：建立账户余额窄 repository port，避免 projection save 和 accounts SQL read path 继续依赖 broad 或 Bank Detail read port surface。
- 改动：新增 `BankAccountBalanceReadModelRepositoryPort`；`PostgresStateStore.bank_account_balance_sql_read_repository` 返回该 port；`BankAccountBalanceProjectionBuilder` 保存 projection rows 走该 port；`BankDetailsApplicationService.accounts_payload(...)` 优先通过显式 account-balance port 读取；manifest repository owner 更新为 `BankAccountBalanceReadModelRepositoryPort`。
- 保留兼容：`BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` 暂时保留为未注入显式 account-balance port 时的 compatibility fallback，后续 audit 决定删除或加固。
- 保持不变：余额计算、account identity、latest balance 选择、currency normalization、API shape、worker event、queue schema、权限、审计和前端行为。
- 下一步：执行 `read-models:bank-account-balance-refresh-freshness-operation-barrier-audit`，审计 app-owned refresh/derived lifecycle helper、all-only scope contract、operation barrier 和 remaining compat fallback。

## 2026-06-24 - refresh/freshness/operation-barrier audit

- 目标：在实现前审计账户余额 refresh enqueue、derived lifecycle、runtime import-state fan-out、scope policy、operation barrier 和 compat fallback。
- 结论：`Application._enqueue_bank_account_balance_read_model_refresh(...)` 仍是最高优先级本地 implementation gap；它虽然走 `ReadModelRefreshGateway`，但模块 IO 边界仍在 app 层。
- 相关缺口：`Application._derived_lifecycle_bank_account_balance_executor(...)` 仍直接组装 invalidated scope 和 enqueued job；runtime import-state fan-out 仍使用 generic `_enqueue_scopes("bank_account_balance", ["all"])`；scope policy 接受 month/all 但 worker/storage 只接受 `all`；dedicated operation barrier regression 和 Bank Detail fallback quarantine 仍待补齐。
- 决策：下一条边界为 `read-models:bank-account-balance-refresh-producer-extraction`。先抽 `BankAccountBalanceReadModelRefreshProducer`，保持 `bank_account_balance:all` all-only 语义，再处理 derived lifecycle、scope contract、operation barrier 和 fallback。

## 2026-06-24 - refresh producer extraction

- 目标：将 `bank_account_balance` 非事务 refresh enqueue 从 app/runtime generic helper 收敛到显式 producer。
- 改动：新增 `BankAccountBalanceReadModelRefreshProducer`；Application import-state、Bank Details service injection、runtime import-state fan-out、runtime derived lifecycle fan-out 和 backfill enqueue 均改用 producer。
- 边界决策：producer 永远 normalize 为 `["all"]`，保持当前 worker/storage all-only contract，不引入 month/account projection scope。
- 保持不变：余额计算、account identity、latest balance、API shape、worker event、queue schema、权限、审计和前端行为。
- 下一步：`read-models:bank-account-balance-derived-lifecycle-executor-extraction`，把 Application 中的 derived lifecycle response assembly 移入 dedicated executor。

## 2026-06-24 - derived lifecycle executor extraction

- 目标：把账户余额 derived lifecycle response assembly 移出 Application。
- 改动：新增 `BankAccountBalanceDerivedLifecycleExecutor`；derived lifecycle registry 改为 `self._bank_account_balance_derived_lifecycle_executor().execute`；旧 `_derived_lifecycle_bank_account_balance_executor(...)` 删除。
- 保持不变：`deleted_counts={"bank_account_balance_read_models": 0}`、`invalidated_scopes=["all"]`、enqueue 成功时返回 `bank_account_balance.read_model.refresh`。
- 下一步：`read-models:bank-account-balance-all-only-scope-contract`，收敛 gateway scope policy 与 worker/storage all-only contract 的不一致。

## 2026-06-24 - all-only scope contract

- 目标：让账户余额 gateway scope policy 与 worker/storage all-only contract 一致。
- 改动：`DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY["bank_account_balance"]` 改为 all-only policy；`ReadModelRefreshGateway` 现在在 durable enqueue 前拒绝 `2026-03`、`account:*`、`active:*` 等非 `all` scope。
- 保持不变：producer 仍 normalize 为 `["all"]`；不引入 month/account projection shard；API、worker event、queue schema、余额计算、权限、审计和前端行为不变。
- 下一步：`read-models:bank-account-balance-operation-barrier-regression`，补齐 `bank_account_balance:all` operation barrier 回归。
