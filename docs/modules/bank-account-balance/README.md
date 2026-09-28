# 银行账户余额

入口：`/api/bank-details/accounts`。

为银行明细提供账户身份、末余额及按币种合计。余额来源是原始银行事实，不使用用途子项累计。

## 边界与 I/O

输入：有序 ISO 日期范围、canonical 流水与账户映射。日期只收窄范围笔数；余额按账户全历史证据计算。输出：accounts、account_key、balance_status、可空金额与来源、范围和全量笔数、按币种合计。

## 当前业务约定

- confirmed 表示最新导入组可靠末余额；last_known 表示最近历史可靠余额；unresolved 表示无法证明末余额或账户多币种；missing 表示没有余额证据。
- unresolved/missing 的金额和来源为空，不显示为零。真实零余额保留。
- 只有某币种全部应计账户都 confirmed 才返回该币种完整合计；CNY 不完整时 total_balance 为空。
- 顺序、余额、账户 rows 和合计来自同一快照，集合式计算，不逐账户查询。

## 依赖方向

[银行明细](../bank-details/README.md)、[设置](../settings/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [backend/src/fin_ops_platform/services/bank_details_canonical_query.py](../../../backend/src/fin_ops_platform/services/bank_details_canonical_query.py)
- [backend/src/fin_ops_platform/services/bank_account_balance_canonical_rows.py](../../../backend/src/fin_ops_platform/services/bank_account_balance_canonical_rows.py)
- [backend/src/fin_ops_platform/services/bank_transaction_ordering_sql.py](../../../backend/src/fin_ops_platform/services/bank_transaction_ordering_sql.py)
- [backend/src/fin_ops_platform/services/bank_details_application_service.py](../../../backend/src/fin_ops_platform/services/bank_details_application_service.py)
- [backend/src/fin_ops_platform/app/routes_bank_details.py](../../../backend/src/fin_ops_platform/app/routes_bank_details.py)
- [web/src/pages/BankDetailsPage.tsx](../../../web/src/pages/BankDetailsPage.tsx)
- [tests/test_bank_same_time_ordering_postgres.py](../../../tests/test_bank_same_time_ordering_postgres.py)
- [tests/test_bank_details_canonical_query.py](../../../tests/test_bank_details_canonical_query.py)
- [tests/test_bank_details_routes.py](../../../tests/test_bank_details_routes.py)
- [web/src/test/BankDetailsApi.test.ts](../../../web/src/test/BankDetailsApi.test.ts)
- [tests/test_read_model_runtime_removal.py](../../../tests/test_read_model_runtime_removal.py)
- [tests/test_runtime_worker_registry.py](../../../tests/test_runtime_worker_registry.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
