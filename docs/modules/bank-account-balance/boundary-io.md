# Bank Account Balance 模块边界与 I/O

日期：2026-09-08（同时间顺序修复本地实施中，未发布）

## 模块化状态

- Bank Details 页面状态：direct canonical read completed
- 页面 query owner：`BankDetailsCanonicalQueryService`
- 页面 repository owner：`PostgresBankDetailsCanonicalQueryRepository`
- 旧 `bank_account_balance` read model：运行时已删除，不再是 `/api/bank-details/accounts` 的事实源

## 职责边界

### 负责

- 为银行明细页面返回账户 identity、展示名、最新余额、最新流水、币种和流水数量。
- 在 SQL 中完成账户级末余额判定与 count 聚合；共享顺序证据，不用银行流水号或 UUID 选择真实末笔。
- 完整账号存在时，账户 identity 和尾号必须以规范化真实账号为准；选择银行 metadata 与真实尾号不一致的历史行不得覆盖同一账户的展示基准，优先采用 metadata 一致的最新行。
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
| canonical 流水 | `app.bank_transactions` | 使用有效状态、账户号/名称、银行映射、numeric balance/amount/signed_amount、direction、currency、实际 trade/txn time 和 stable identity。沿用既有空币种/RMB/人民币按 CNY 归一，不新增账户 key。 |
| 账户映射 | canonical app settings | 决定银行名称、展示名和 identity metadata；不创建平行账户事实。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `accounts` | Bank Details 页面 | 每个账户一行；包含 `account_identity`、`account_key`、`balance_status`、nullable 最新余额/来源时间/来源流水 ID、nullable 币种、当前范围笔数和全量笔数。 |
| 余额状态 | Bank Details 页面 | `confirmed` 为最新已导入组可靠末余额；`last_known` 为最近有余额历史组的可靠末余额；`unresolved` 为末余额待核实或账户多币种；`missing` 为单币种账户全历史无余额。后两者金额、来源时间和 ID 为 null。 |
| 来源 | 页面/导出 snapshot | 末余额已确认但末笔身份无法证明时，返回金额与来源组时间，`latest_balance_transaction_id=null`；不能以稳定展示 ID 补齐。 |
| 汇总 | Bank Details 页面 | 每币种所有应计账户均 `confirmed` 才进入 `total_balances_by_currency`；CNY 完整合计才进入 `total_balance`，否则为 null。真实 0 保留零值字符串。多币种账户按底层全部币种集合标记合计不完整，不能只依据展示币种 null。所有汇总与账户 rows 同一 snapshot。 |
| 余额数量 | Bank Details 页面 | `has_balance` 及 `balance_account_count` 按 `confirmed/last_known` 的可显示原值计数；`missing_balance_account_count` 为无可显示值数量。数量不代表完整当前余额的账户数量。 |
| 退役状态字段 | 无 | 不输出 `balance_read_model_status`、`read_model_status`、source version、refresh job 或 barrier；余额证据状态不是 freshness。 |

同账户多币种时优先返回 `unresolved`，保留 account key、metadata 和笔数，`currency=null`。单币种账户全历史无余额返回 `missing`；最新日多笔且有缺具体时间记录时返回 `unresolved`，不把日期补成午夜挑末笔。最新组部分缺余额而无法确定终点时不回退历史；仅最新组全部缺余额，且最近有余额的历史组终点可靠时返回 `last_known`。

## 查询与性能合同

- 显式 `REPEATABLE READ READ ONLY` snapshot。
- 一次账户 latest-balance SQL，一次日期范围账户 count SQL，加一次 canonical settings 读取；查询次数固定。
- canonical aggregate SQL 由 `BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL` 提供；账户事实由 `BANK_ACCOUNT_CANONICAL_SOURCE_CTES` 提供，顺序/末余额由 `BANK_TRANSACTION_ORDERING_CTES` 共享。`ordering_target_groups` 仅包括最新组和最后非空组；它们所属完整日期先检测缺时间歧义，随后只对目标时间组做余额关系判定。闭合组需要锚点时才访问完整历史并取紧邻前一时点的单笔证据。
- 银行列表排序输入复用 classifier base 已有 account_key，币种归一与账户聚合共用 `BANK_NORMALIZED_CURRENCY_SQL`；不为排序增加账户 hash 计算，分类 mapper 与 Workbench 消费边界保持原样。
- 多笔组要求有效金额方向、numeric 余额关系以及进入/离开次数和连通性同时成立。完整逐笔顺序仅确认无分支组；有分支时可以只确认终点，末笔身份不足返回 null。正常单笔不参与复杂遍历。
- 固定查询数用于防止 N+1，不等于性能通过；尾延迟、扫描量和 EXPLAIN 结果由修复计划的实测记录验收。
- 不增加 cache、materialized view 或页面 worker；索引只在 EXPLAIN/性能证据显示需要时由主控统一 migration 编号。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Query | `backend/src/fin_ops_platform/services/bank_details_canonical_query.py` |
| Canonical SQL | `backend/src/fin_ops_platform/services/bank_account_balance_canonical_rows.py`、`bank_transaction_ordering_sql.py` |
| Application/route | `bank_details_application_service.py`、`routes_bank_details.py` |
| Frontend | `web/src/pages/BankDetailsPage.tsx`、`web/src/features/bankDetails/*` |
| Tests | `tests/test_bank_same_time_ordering_postgres.py`、`tests/test_bank_details_canonical_query.py`、`tests/test_bank_details_routes.py`、Bank Details frontend/E2E tests |

## 旧链删除结果

- 全仓扫描后删除 `BankDetailsService.list_accounts/_latest_balance_transaction`、`PostgresCoreRepository.list_bank_transaction_accounts`、`PostgresStateStore` 对应 wrapper 和独占测试 fake；有效余额来源、范围笔数、无余额账户及 metadata 断言迁入 `tests/test_bank_same_time_ordering_postgres.py`，正式/本地不再维护两套余额选择算法。
- `bank_account_balance_read_model_repository.py`、refresh/producer、derived lifecycle、backfill 和旧 projection 已删除。
- manifest、scope policy、worker registry/handler、App Status、deploy env 和 RabbitMQ 条目已删除。
- `BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL` 位于 `bank_account_balance_canonical_rows.py`，正式 direct accounts query 统一消费共享组末余额判定；metadata 的一致性选择继续保留，不能把其 serial/ID 稳定选择误认为余额算法。
- 历史 migration 文件保留为不可变迁移记录；migration `0149` 删除遗留 projection schema，没有运行时或物理 projection owner。
