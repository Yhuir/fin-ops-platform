# Bank Account Balance 实施记录

## 2026-06-24 - selected as next modular IO read model pilot

- 目标：在 Search local support 进入 `production-evidence-deferred` 后，选择下一个非 Go read model pilot。
- 决策：选择 `bank_account_balance`，下一条边界为 `read-models:bank-account-balance-repository-port-extraction`。
- 理由：它是剩余已知 read model 候选，服务 Bank Details accounts，参与银行导入 write-operation SLO，并且必须与 `bank_detail` rows 保持余额金额/readiness 独立。
- 首切范围：新增窄 `BankAccountBalanceReadModelRepositoryPort`，只暴露 manifest 登记的 `bank_account_balance_scope_summary(...)`、`list_bank_account_balances(...)` 和 `save_bank_account_balances(...)`，并让 projection save 与 accounts SQL read path 使用该 port。
- 非目标：不改余额计算、account identity、API shape、worker event、queue schema、权限、审计、frontend behavior、Go/Fiber 或 Go Worker。
- 状态：`bank_account_balance` 是 `implementation-gap-open`；本记录不是 module closure。
