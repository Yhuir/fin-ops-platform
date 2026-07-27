# Bank Account Balance 模块维护入口

- Module key：`bank-account-balance`
- 类型：页面专属 canonical query 资源
- Route：`GET /api/bank-details/accounts`
- Page key：`bank-details`

## 修改前必读

- `docs/modules/bank-details/README.md`
- `docs/modules/bank-details/boundary-io.md`
- `docs/modules/imports-bank-transactions/boundary-io.md`
- `docs/architecture/module-boundaries/canonical-facts.md`

## 当前代码入口

- `backend/src/fin_ops_platform/services/bank_details_canonical_query.py`：账户列表、最新余额和流水计数的 direct canonical query。
- `backend/src/fin_ops_platform/services/bank_account_balance_canonical_rows.py`：canonical 账户聚合 SQL。
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`：accounts API application boundary。
- `backend/src/fin_ops_platform/app/routes_bank_details.py`：HTTP 参数和响应映射。
- `web/src/pages/BankDetailsPage.tsx`：账户 loading/empty/error 展示和筛选。

## 当前边界

`/api/bank-details/accounts` 不再读取 `read_model.bank_account_balances`，也不执行 freshness gate、enqueue 或 polling。query repository 在显式 `REPEATABLE READ READ ONLY` snapshot 中：

- 用账户级 SQL从 canonical `app.bank_transactions` 选择每个账户的最新非空余额、币种、账户 identity 和最新流水。
- 用有界聚合计算当前日期范围内的账户流水数量。
- 保留有余额/无余额账户、总余额和按币种汇总语义。
- 不把全量流水搬回 Python 或浏览器聚合。

旧 `bank_account_balance` manifest、worker、readiness、repository/projection、derived lifecycle 和 backfill 已删除。历史 projection migration/表暂留作回滚证据，没有运行时 reader/writer。

## 本目录文件

- `boundary-io.md`：当前 direct accounts I/O 和旧链删除状态。
- `state-machine.md`：历史 read-model 状态记录，不再描述 Bank Details 页面状态。
- `tests.md`：direct query 与删除守卫的测试责任。
- `implementation-notes.md`：历史记录和本次迁移决策。
