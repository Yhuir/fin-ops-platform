# Bank Account Balance E2E Spec

`bank_account_balance` 是 Bank Details accounts 视图使用的 canonical query 资源，不是独立页面。用户可见页面行为归属 `docs/modules/bank-details/e2e-spec.md` 和银行导入相关 E2E spec。

| Spec ID | 用户目标 | 优先级 | 验收合同 |
| --- | --- | --- | --- |
| `BANK-BAL-E2E-001` | 银行明细账户余额从 canonical 流水高性能聚合 | P1 | `/api/bank-details/accounts` 在同一只读 snapshot 返回最新余额、账户和范围计数；不读取 projection、不 enqueue、不等待 worker，银行导入提交后下次 GET 直接可见。 |

若后续新增独立账户余额页面或新的用户交互入口，必须先在本文件补新的 Spec ID，再补 Browser/Vitest/API 覆盖映射。
