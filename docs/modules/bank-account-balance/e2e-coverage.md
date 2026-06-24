# Bank Account Balance E2E Coverage

当前不定义独立 Browser E2E coverage。

覆盖归属：

- Bank Details accounts UI 行为归属 `docs/modules/bank-details/e2e-coverage.md`。
- 银行导入后账户余额刷新链路归属 `docs/modules/imports-bank-transactions/e2e-coverage.md`。
- 本模块当前主要由 API/service/read model/worker 测试保护，详见 `tests.md`。

缺口：

- 真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍需 staging/production smoke。
- 若新增独立账户余额页面或新的用户交互入口，需要在本文件补 Spec ID 到测试的映射。
