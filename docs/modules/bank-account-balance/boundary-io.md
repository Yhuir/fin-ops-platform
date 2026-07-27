# Bank Account Balance 模块边界与 I/O

日期：2026-07-27

## 模块化状态

- Bank Details 页面状态：direct canonical read completed
- 页面 query owner：`BankDetailsCanonicalQueryService`
- 页面 repository owner：`PostgresBankDetailsCanonicalQueryRepository`
- 旧 `bank_account_balance` read model：运行时已删除，不再是 `/api/bank-details/accounts` 的事实源

## 职责边界

### 负责

- 为银行明细页面返回账户 identity、展示名、最新余额、最新流水、币种和流水数量。
- 在 SQL 中完成账户级 latest-row 与 count 聚合。
- 保持日期筛选只影响 `transaction_count`，不影响 latest balance。

### 不负责

- 不拥有银行流水导入或 canonical transaction 写入。
- 不在 Python/浏览器全量聚合。
- 不维护页面 freshness、dirty scope、outbox、readiness、worker 或 cache。
- 不把无余额账户误删，也不把不同完整账号仅按尾号合并。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| `date_from` / `date_to` | `/api/bank-details/accounts` | ISO 日期且范围有序；只收窄账户流水计数。 |
| canonical 流水 | `app.bank_transactions` | 使用有效状态、账户号/名称、银行映射、balance、currency、trade/txn time 和 stable identity。 |
| 账户映射 | canonical app settings | 决定银行名称、展示名和 identity metadata；不创建平行账户事实。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `accounts` | Bank Details 页面 | 每个账户一行；包含 `account_identity`、`account_key`、最新余额/时间/流水 ID、币种、当前范围笔数和全量笔数。 |
| 汇总 | Bank Details 页面 | `total_balance`、`total_balances_by_currency`、`balance_account_count`、`missing_balance_account_count` 与账户 rows 同一 snapshot。 |
| 状态字段 | 无 | 不输出 `balance_read_model_status`、`read_model_status`、source version、refresh job 或 barrier。 |

## 查询与性能合同

- 显式 `REPEATABLE READ READ ONLY` snapshot。
- 一次账户 latest-balance SQL，一次日期范围账户 count SQL，加一次 canonical settings 读取；查询次数固定。
- canonical aggregate SQL 由 `BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL` 提供；只保留这一份余额算法。
- 不增加 cache、materialized view 或页面 worker；索引只在 EXPLAIN/性能证据显示需要时由主控统一 migration 编号。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Query | `backend/src/fin_ops_platform/services/bank_details_canonical_query.py` |
| Canonical SQL | `backend/src/fin_ops_platform/services/bank_account_balance_canonical_rows.py` |
| Application/route | `bank_details_application_service.py`、`routes_bank_details.py` |
| Frontend | `web/src/pages/BankDetailsPage.tsx`、`web/src/features/bankDetails/*` |
| Tests | `tests/test_bank_details_canonical_query.py`、`tests/test_bank_details_routes.py`、Bank Details frontend/E2E tests |

## 旧链删除结果

- `bank_account_balance_read_model_repository.py`、refresh/producer、derived lifecycle、backfill 和旧 projection 已删除。
- manifest、scope policy、worker registry/handler、App Status、deploy env 和 RabbitMQ 条目已删除。
- `BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL` 位于 `bank_account_balance_canonical_rows.py`，是 direct query 的唯一余额算法。
- 历史 projection migration/表暂留作回滚证据，没有运行时 reader/writer。
