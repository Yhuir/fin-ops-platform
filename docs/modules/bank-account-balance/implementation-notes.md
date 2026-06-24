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
