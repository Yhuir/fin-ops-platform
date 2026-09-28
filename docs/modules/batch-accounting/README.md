# 批量账务

入口：`/batch-accounting`。

把批量账务集中处理支出与已完成日常报销 OA 及附件发票建立正式关系。

## 边界与 I/O

输入：GET bank_year=具体年份或 all、bucket、银行/OA 分页和 oa_search；提交携带具体年份、bank_row_id、oa_row_ids、tag_selection_version、稳定 idempotency_key。输出：同快照 summary、bank_rows、oa_rows、relations_by_bank_row_id 和 pagination。

## 当前业务约定

- 银行候选为有效正金额支出、指定对方户名且未被 active relation 占用；有效分类复用银行 owner。
- OA 候选不限银行年份，必须已完成且没有银行成员占用；附件只按当前候选 IDs 批量读取。
- 规则由 Settings owner 保存 stable tag codes/version，CAS 与审计同事务；新标签不自动扩大已保存选择。
- 提交/撤回调用正式关系命令，持久幂等键随同一用户意图重试复用。
- 双方分页在服务端完成，page_size 最大 200；submitted 不再返回候选 OA 列表。

## 依赖方向

[银行明细](../bank-details/README.md)、[设置](../settings/README.md)、[正式关联关系](../workbench-relations/README.md)、[OA 集成](../oa-integration/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/BatchAccountingPage.tsx](../../../web/src/pages/BatchAccountingPage.tsx)
- [web/src/components/batchAccounting/BatchAccountingTagRulesDrawer.tsx](../../../web/src/components/batchAccounting/BatchAccountingTagRulesDrawer.tsx)
- [web/src/features/batchAccounting/api.ts](../../../web/src/features/batchAccounting/api.ts)
- [web/src/features/batchAccounting/types.ts](../../../web/src/features/batchAccounting/types.ts)
- [backend/src/fin_ops_platform/app/routes_batch_accounting.py](../../../backend/src/fin_ops_platform/app/routes_batch_accounting.py)
- [backend/src/fin_ops_platform/services/batch_accounting_service.py](../../../backend/src/fin_ops_platform/services/batch_accounting_service.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/batch_accounting.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/batch_accounting.py)
- [backend/src/fin_ops_platform/services/workbench_relation_command_service.py](../../../backend/src/fin_ops_platform/services/workbench_relation_command_service.py)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [backend/src/fin_ops_platform/postgres/migrations/0135_batch_accounting_tag_selection.sql](../../../backend/src/fin_ops_platform/postgres/migrations/0135_batch_accounting_tag_selection.sql)
- [tests/test_batch_accounting_api.py](../../../tests/test_batch_accounting_api.py)
- [tests/test_batch_accounting_postgres_integration.py](../../../tests/test_batch_accounting_postgres_integration.py)
- [tests/test_audit_page_canonical_data_tool.py](../../../tests/test_audit_page_canonical_data_tool.py)
- [tests/test_platform_runtime_boundary_guards.py](../../../tests/test_platform_runtime_boundary_guards.py)
- [web/src/test/BatchAccountingApi.test.ts](../../../web/src/test/BatchAccountingApi.test.ts)
- [web/src/test/BatchAccountingPage.test.tsx](../../../web/src/test/BatchAccountingPage.test.tsx)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
