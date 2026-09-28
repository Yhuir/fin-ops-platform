# 销项发票收款

入口：`/output-invoice-collections`。

按销项发票核对收入流水及红蓝票关系，提供详情、筛选、统计和导出。

## 边界与 I/O

输入：page/page_size/keyword/日期/filters/sort，原始销项票、active relations 和收入用途。输出：每个 canonical 发票 ID 一行、summary/statistics/pagination/facets、详情及导出。

## 当前业务约定

- 正负票各自保留，正式关系不能把发票行折叠。只统计可唯一归属于正票的收入流水，支出不计已收。
- 红票的目标只从原始备注精确的“被红冲蓝字数电发票号码”标记提取，并唯一匹配正票，不用金额猜测。
- 六类状态为 pending_collection、partial_collected、collected、reversed_by_red、reverses_blue、unmatched_red。
- 收款状态候选排除自身条件并补齐合法零数量状态；rows 与统计在同一快照，分页不影响发票张数。
- 父流水原始金额与用途收款金额分别表达，红蓝票不能重复占用收款。
- 导出使用同一业务筛选、排序和口径，20,000 行上限；原始详情有界读取，不暴露内部关系或 raw payload。

## 依赖方向

[正式关联关系](../workbench-relations/README.md)、[银行明细](../bank-details/README.md)、[发票导入](../imports-invoices/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/OutputInvoiceCollectionsPage.tsx](../../../web/src/pages/OutputInvoiceCollectionsPage.tsx)
- [web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx](../../../web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx)
- [web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx](../../../web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx)
- [web/src/features/outputInvoiceCollections/api.ts](../../../web/src/features/outputInvoiceCollections/api.ts)
- [backend/src/fin_ops_platform/app/routes_output_invoice_collections.py](../../../backend/src/fin_ops_platform/app/routes_output_invoice_collections.py)
- [backend/src/fin_ops_platform/services/output_invoice_collection_canonical_query_service.py](../../../backend/src/fin_ops_platform/services/output_invoice_collection_canonical_query_service.py)
- [backend/src/fin_ops_platform/services/output_invoice_collection_service.py](../../../backend/src/fin_ops_platform/services/output_invoice_collection_service.py)
- [backend/src/fin_ops_platform/services/output_invoice_reversal.py](../../../backend/src/fin_ops_platform/services/output_invoice_reversal.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py)
- [backend/src/fin_ops_platform/services/workbench_free_matching_engine.py](../../../backend/src/fin_ops_platform/services/workbench_free_matching_engine.py)
- [tests/test_invoice_usage_collection_canonical_query.py](../../../tests/test_invoice_usage_collection_canonical_query.py)
- [tests/test_workbench_free_matching_engine.py](../../../tests/test_workbench_free_matching_engine.py)
- [web/src/test/OutputInvoiceCollectionsPage.test.tsx](../../../web/src/test/OutputInvoiceCollectionsPage.test.tsx)
- [tests/test_bank_split_document_scope_postgres.py](../../../tests/test_bank_split_document_scope_postgres.py)
- [web/src/test/OutputInvoiceCollectionApi.test.ts](../../../web/src/test/OutputInvoiceCollectionApi.test.ts)
- [web/e2e/output-invoice-status-tabs.spec.ts](../../../web/e2e/output-invoice-status-tabs.spec.ts)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
