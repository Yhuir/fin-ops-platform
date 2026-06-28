# Bank Account Balance E2E Spec

该模块已从独立 read model 转为 Bank Details accounts direct API 的历史记录，不再定义独立 E2E spec。

| Spec ID | 用户目标 | 优先级 | 验收合同 |
| --- | --- | --- | --- |
| `BANK-BAL-E2E-001` | 银行明细账户余额通过 direct accounts payload 可见 | P1 | 覆盖归属 `docs/modules/bank-details/e2e-spec.md`；不得要求 `bank_account_balance` read model freshness、worker drain 或 operation barrier。 |

新增账户余额用户交互时，应在 `bank-details` 模块补 Spec ID，而不是恢复本模块 read model。
