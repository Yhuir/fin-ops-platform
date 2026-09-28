# 外部往来款

入口：`/turnover-ledger`。

管理外部往来本金、结算、借款天数、关系确认及补充字段，提供分组明细和导出。

## 边界与 I/O

输入：family、筛选、分页、精确 bank_row_ids/selection_version、命令版本与 actor。输出：groups/summary/statistics、summary_row/flow_rows、关系详情、补充字段和导出；页面每页 50 条。

## 当前业务约定

- 流水用途、有效分类、规则、active relations 与 extras 来自同一个只读快照，分类算法复用银行 owner。
- 现金配对不等于业务结清；只有成员完整唯一、现金差额和本金结算余额都为零才认定闭环。
- 手工闭环使用当前银行事实和往来语义的 selection_version，在同一 UoW 重检并提交；不能仅以 relation mode 判断结清。
- 本金借款天数按该笔日期至上海今天，FIFO 计息天数按未结/结清日计算，二者分别展示。
- 详情一次返回关系、流水、审计和 extra；动态建议可由当前事实重建，不要求先持久化草稿。
- 导出保留归属明细，页面只返回实际消费字段。写成功后当前页 GET 失败应说明写已成功、重载失败，不能重新发送业务写。

## 依赖方向

[银行明细](../bank-details/README.md)、[正式关联关系](../workbench-relations/README.md)、[设置](../settings/README.md)、[成本统计](../cost-statistics/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/TurnoverLedgerPage.tsx](../../../web/src/pages/TurnoverLedgerPage.tsx)
- [backend/src/fin_ops_platform/app/routes_turnover_ledger.py](../../../backend/src/fin_ops_platform/app/routes_turnover_ledger.py)
- [backend/src/fin_ops_platform/services/turnover_ledger_query_service.py](../../../backend/src/fin_ops_platform/services/turnover_ledger_query_service.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/turnover_ledger_snapshot.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/turnover_ledger_snapshot.py)
- [backend/src/fin_ops_platform/services/turnover_ledger_service.py](../../../backend/src/fin_ops_platform/services/turnover_ledger_service.py)
- [backend/src/fin_ops_platform/services/turnover_ledger_relation_context.py](../../../backend/src/fin_ops_platform/services/turnover_ledger_relation_context.py)
- [tests/test_turnover_ledger_service.py](../../../tests/test_turnover_ledger_service.py)
- [tests/test_turnover_ledger_query_service.py](../../../tests/test_turnover_ledger_query_service.py)
- [tests/test_turnover_ledger_postgres_integration.py](../../../tests/test_turnover_ledger_postgres_integration.py)
- [tests/test_bank_details_canonical_query.py](../../../tests/test_bank_details_canonical_query.py)
- [tests/test_turnover_ledger_api.py](../../../tests/test_turnover_ledger_api.py)
- [tests/test_turnover_ledger_uow_contract.py](../../../tests/test_turnover_ledger_uow_contract.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
