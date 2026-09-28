# 银行明细

入口：`/bank-details`。

负责原始银行流水、有效分类、分类规则、人工标签与持久化用途拆分。原始金额、余额和导入身份由银行事实保留；其他模块通过用途视图消费拆分子项。

## 边界与 I/O

输入：账户、日期、搜索、分类、排序、分页；分类或拆分命令携带精确流水身份、版本与服务端 actor。输出：账户、流水、完整筛选统计、详情、导出及写入结果。rows 与统计在同一只读快照查询。

## 当前业务约定

- 分类优先级和自动规则复用同一 canonical SQL classifier，消费者不复制算法。
- 拆分必须金额守恒，稳定子项身份与完整 category_payload 在银行 owner 事务保存；原流水只显示一次，业务金额与原始金额不得混算。
- 拆分会通过所属 owner 同事务处理受影响的正式关系、往来补充及成本决定；仅顺序变化不等同业务用途改变。
- 同时间组的顺序由余额衔接证据判断，分页与导出一致；不能用稳定展示 ID 伪造末笔证明。
- 详情通过原始父交易 ID 定向读取来源字段，公共抽屉不从列表拼凑来源。
- 写入成功回读当前页；旧请求不得覆盖新账户、筛选或分页。

## 依赖方向

[银行账户余额](../bank-account-balance/README.md)、[正式关联关系](../workbench-relations/README.md)、[外部往来款](../turnover-ledger/README.md)、[成本统计](../cost-statistics/README.md)、[银行流水导入](../imports-bank-transactions/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/BankDetailsPage.tsx](../../../web/src/pages/BankDetailsPage.tsx)
- [backend/src/fin_ops_platform/app/routes_bank_details.py](../../../backend/src/fin_ops_platform/app/routes_bank_details.py)
- [backend/src/fin_ops_platform/services/bank_details_application_service.py](../../../backend/src/fin_ops_platform/services/bank_details_application_service.py)
- [backend/src/fin_ops_platform/services/bank_details_canonical_query.py](../../../backend/src/fin_ops_platform/services/bank_details_canonical_query.py)
- [backend/src/fin_ops_platform/services/bank_transaction_ordering_sql.py](../../../backend/src/fin_ops_platform/services/bank_transaction_ordering_sql.py)
- [backend/src/fin_ops_platform/services/bank_account_balance_canonical_rows.py](../../../backend/src/fin_ops_platform/services/bank_account_balance_canonical_rows.py)
- [backend/src/fin_ops_platform/services/bank_details_service.py](../../../backend/src/fin_ops_platform/services/bank_details_service.py)
- [backend/src/fin_ops_platform/services/bank_transaction_category_mutation_writer.py](../../../backend/src/fin_ops_platform/services/bank_transaction_category_mutation_writer.py)
- [backend/src/fin_ops_platform/services/bank_details_export_service.py](../../../backend/src/fin_ops_platform/services/bank_details_export_service.py)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [tests/test_bank_details_canonical_query.py](../../../tests/test_bank_details_canonical_query.py)
- [tests/test_bank_same_time_ordering_postgres.py](../../../tests/test_bank_same_time_ordering_postgres.py)
- [tests/test_bank_details_routes.py](../../../tests/test_bank_details_routes.py)
- [tests/test_bank_details_export_service.py](../../../tests/test_bank_details_export_service.py)
- [tests/test_bank_auto_tag_rules_api.py](../../../tests/test_bank_auto_tag_rules_api.py)
- [tests/test_bank_split_consumers_postgres.py](../../../tests/test_bank_split_consumers_postgres.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
