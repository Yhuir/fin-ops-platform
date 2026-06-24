# Bank Account Balance E2E Spec

当前不定义独立 Browser E2E spec。

原因：

- `bank_account_balance` 是 Bank Details accounts 视图使用的资源/API read model，不是独立页面。
- 用户可见验收入口属于 `docs/modules/bank-details/e2e-spec.md` 和银行导入相关 E2E spec。
- 若后续新增独立账户余额页面或独立交互入口，必须先在本文件补 Spec ID，再补 Browser/Vitest/API 覆盖映射。
