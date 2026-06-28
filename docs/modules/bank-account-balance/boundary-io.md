# Bank Account Balance 模块边界与 I/O

日期：2026-06-28

## 模块化状态

- 状态：retired
- 当前边界可信度：high
- 当前 owner：`bank-details`
- 删除条件：已满足；当前运行代码不再注册、读取或写入独立账户余额 read model。

## 当前 I/O

| I/O | 当前合同 |
| --- | --- |
| 页面读取 | `/api/bank-details/accounts` 通过 Bank Details direct service 返回账户列表和余额。 |
| 写入/导入影响 | 银行导入继续返回 bank details / downstream direct payload 的 affected scope/job diagnostics；不再产生 `bank_account_balance` scope。 |
| 运维/worker | 无 `bank-account-balance` worker、env、manifest、App Status job 或 backfill CLI。 |
| 数据库历史 | 历史 migrations 中的 `read_model.bank_account_balances` 不作为当前运行面。 |

## 禁止边界

- 不新增 `bank_account_balance.read_model.refresh`。
- 不新增 `bank_account_balance` dirty scope、scope policy 或 manifest entry。
- 不恢复 `BankAccountBalanceReadModelRepositoryPort`、projection builder、refresh service、producer、derived lifecycle executor 或 backfill CLI。

## 当前测试与验证

- `tests/test_bank_details_sql_runtime.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
