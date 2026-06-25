# Bank Account Balance E2E Spec

`bank_account_balance` 是 Bank Details accounts 视图使用的资源/API read model，不是独立页面。当前 Spec-first 合同以 API/read model/worker freshness 为主，用户可见页面行为归属 `docs/modules/bank-details/e2e-spec.md` 和银行导入相关 E2E spec。

| Spec ID | 用户目标 | 优先级 | 验收合同 |
| --- | --- | --- | --- |
| `BANK-BAL-E2E-001` | 银行明细账户余额读取使用独立账户余额 read model | P1 | `/api/bank-details/accounts` 必须通过 `bank_account_balance:all` freshness/status contract 读取余额；不能回退到 bank detail rows 伪造 fresh 余额；银行导入或 settings/data lifecycle fan-out 后必须入队/刷新该 read model。 |

若后续新增独立账户余额页面或新的用户交互入口，必须先在本文件补新的 Spec ID，再补 Browser/Vitest/API 覆盖映射。
