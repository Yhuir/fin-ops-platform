# Bank Account Balance 模块维护入口

- Module key：`bank-account-balance`
- 类型：页面专属 canonical query 资源
- Route：`GET /api/bank-details/accounts`
- Page key：`bank-details`

## 同时间顺序与余额

- [同时间流水顺序与账户余额修复](../../dev/bank-same-time-ordering-repair-plan.md)：2026-09-08 本地实现与验证进行中，未发布；本目录描述配套代码合同，实际验收及剩余风险以计划执行记录为准。

## 修改前必读

- `docs/modules/bank-details/README.md`
- `docs/modules/bank-details/boundary-io.md`
- `docs/modules/imports-bank-transactions/boundary-io.md`
- `docs/architecture/module-boundaries/canonical-facts.md`

## 当前代码入口

- `backend/src/fin_ops_platform/services/bank_details_canonical_query.py`：账户列表、最新余额和流水计数的 direct canonical query。
- `backend/src/fin_ops_platform/services/bank_account_balance_canonical_rows.py`：共享 canonical 账户事实输入及账户聚合 SQL。
- `backend/src/fin_ops_platform/services/bank_transaction_ordering_sql.py`：与银行列表/导出共用的请求内顺序和组末余额判定。
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`：accounts API application boundary。
- `backend/src/fin_ops_platform/app/routes_bank_details.py`：HTTP 参数和响应映射。
- `web/src/pages/BankDetailsPage.tsx`：账户 loading/empty/error 展示和筛选。

## 当前边界

`/api/bank-details/accounts` 不再读取 `read_model.bank_account_balances`，也不执行 freshness gate、enqueue 或 polling。query repository 在显式 `REPEATABLE READ READ ONLY` snapshot 中：

- 用账户级 SQL 从 canonical `app.bank_transactions` 判断最新已导入组的可靠末余额；只有最新组全部缺余额时才检查最近有余额的历史组，可靠时标记 `last_known`，不连续越过冲突组寻找可显示数字。
- 最新/最后非空组所属完整日期只用于检测缺时间歧义，复杂余额关系仅判定这两个目标时间组；正常单笔不遍历，闭合组需要锚点时才查紧邻历史证据。
- 用有界聚合计算当前日期范围内的账户流水数量。
- 保留既有账户 identity、metadata 一致性及空币种按 CNY 归一规则。输出 `confirmed`、`last_known`、`unresolved`、`missing`，保留无可用余额的账户；同账户多币种返回 `unresolved` 且展示币种为 null。
- 每币种所有应计账户均 `confirmed` 才返回完整合计；last_known 可展示原值但不纳入完整总额，未确认/缺失余额不补 0。CNY 完整合计通过 `total_balance` 返回，缺失为 null，真实零仍为零值字符串。
- 不把全量流水搬回 Python 或浏览器聚合。

旧 `bank_account_balance` manifest、worker、readiness、repository/projection、derived lifecycle 和 backfill 已删除；migration `0149` 删除遗留 projection schema，没有运行时或物理 projection owner。

旧 `BankDetailsService` 账户列表/末笔 helper、core accounts reader 和 state-store wrapper 已在全仓调用扫描后删除；有效账户业务断言迁入真实 PostgreSQL 顺序测试。metadata 的 label_consistent 选择继续保留。

## 本目录文件

- `boundary-io.md`：当前 direct accounts I/O 和旧链删除状态。
- `state-machine.md`：当前 canonical GET 的页面状态和旧链禁止状态。
- `tests.md`：direct query 与删除守卫的测试责任。
- `implementation-notes.md`：历史记录和本次迁移决策。
