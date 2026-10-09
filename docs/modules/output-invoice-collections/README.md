# 销项发票收款

入口：`/output-invoice-collections`。

按销项发票核对收入流水及红蓝票关系，提供详情、筛选、统计和导出。

## 边界与 I/O

输入：page/page_size/keyword/日期/filters/sort，原始销项票、active relations 和收入用途。输出：每个 canonical 发票 ID 一行、summary/statistics/pagination/facets、详情及导出。

## 当前业务约定

- 搜索与发票月份位于页面头部，搜索在统计右侧，月份在右侧导出操作之前；不额外占查询工具行。查询、日期、排序及导出口径不变，失败保留重试。

- 分类切换采用连续三层区域：全部销项发票 → 蓝字/红字 → 六类既有状态。父分类使用子状态并集，不新增业务状态；区域无外围框或嵌套卡片，窄屏整体纵向排列，无横向滚动。恢复会话保留完整多状态条件，筛选、分页和导出使用同一查询。

- 红蓝票及正式关系成员在行内展开，成员 icon 打开公共单条详情。列表 `relationSources` 包含同快照发票、OA、原始流水成员，独立关系保留标识；不改变收款状态和金额计算。详情按原始身份定向读取，保留同票全部商品行。

- 正负票各自保留，正式关系不能把发票行折叠，共享 OA 或发票也不能递归连接独立正式关系。只统计可唯一归属于正票的收入流水，支出不计已收。
- 银行摘要的 `bankShortName` 只取同一快照内银行全名与字符串尾号精确匹配的唯一账户简称；缺少映射或简称冲突时为空。原始银行名称、尾号、筛选和导出口径不变，列表不额外请求设置。
- 红票的目标只从原始备注精确的“被红冲蓝字数电发票号码”标记提取，并唯一匹配正票，不用金额猜测。
- 六类状态为 pending_collection、partial_collected、collected、reversed_by_red、reverses_blue、unmatched_red。`pending_collection` 统一展示为“待收款”，表示系统尚未确认相应收款；不代表客户现实中一定尚未付款。表头仍为“收款状态”，行内保留已收、待收金额。
- 收款状态候选排除自身条件并补齐合法零数量状态；rows 与统计在同一快照，分页不影响发票张数。
- 列表金额列展示价税合计及灰色税率，税额可在详情和 Excel 查看。四个财务字段只读取原件，不补算；原件未提供时为空。Excel 保留数字和原始税额文本，不附推算来源列。
- 税率只来自原始字段或真实明细，缺少证据时显示 `—`，明确不同税率时显示“多税率”；不以金额比率推算。来源冲突在共享详情列明。原始 `0.13` 与 `13%` 统一，`0%`、免税、不征税分别保留。
- 税率勾选为 OR，与其他条件为 AND；候选排除自身筛选，保留搜索、日期及其他条件。不再存在的筛选值保持精确过滤，弹窗提示失效并提供清除入口，不静默扩大结果。
- 分组表头显示当前完整筛选范围的含税、不含税金额及收入用途合计，红票金额带负号，不按当前页求和。收入合计只使用可唯一归属的收入用途，按业务身份去重，不能将同额不同流水合并。加载或刷新失败时不展示旧合计为新结果。
- `unmatched_red` 展示名为“未关联蓝字”。导出继承当前红蓝票/收款分类、税率、已生效搜索、日期、其他筛选和排序，覆盖完整命中范围，不受分页影响。抽屉只显示发票张数和一个导出操作，不提供二次筛选或明细预览；数量和文件使用同一查询。
- 父流水原始金额与用途收款金额分别表达，红蓝票不能重复占用收款。
- 导出使用同一业务筛选、排序和口径，20,000 行上限；原始详情有界读取，不暴露内部关系或 raw payload。

## 依赖方向

[正式关联关系](../workbench-relations/README.md)、[银行明细](../bank-details/README.md)、[发票导入](../imports-invoices/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/OutputInvoiceCollectionsPage.tsx](../../../web/src/pages/OutputInvoiceCollectionsPage.tsx)
- [web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx](../../../web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx)
- [web/src/features/SourceDetailDrawer.tsx](../../../web/src/features/SourceDetailDrawer.tsx)
- [web/src/features/outputInvoiceCollections/api.ts](../../../web/src/features/outputInvoiceCollections/api.ts)
- [backend/src/fin_ops_platform/app/routes_output_invoice_collections.py](../../../backend/src/fin_ops_platform/app/routes_output_invoice_collections.py)
- [backend/src/fin_ops_platform/services/output_invoice_collection_canonical_query_service.py](../../../backend/src/fin_ops_platform/services/output_invoice_collection_canonical_query_service.py)
- [backend/src/fin_ops_platform/services/output_invoice_collection_service.py](../../../backend/src/fin_ops_platform/services/output_invoice_collection_service.py)
- [backend/src/fin_ops_platform/services/output_invoice_reversal.py](../../../backend/src/fin_ops_platform/services/output_invoice_reversal.py)
- [backend/src/fin_ops_platform/services/output_invoice_tax_rate.py](../../../backend/src/fin_ops_platform/services/output_invoice_tax_rate.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py)
- [backend/src/fin_ops_platform/services/workbench_free_matching_engine.py](../../../backend/src/fin_ops_platform/services/workbench_free_matching_engine.py)
- [tests/test_invoice_usage_collection_canonical_query.py](../../../tests/test_invoice_usage_collection_canonical_query.py)
- [tests/test_workbench_free_matching_engine.py](../../../tests/test_workbench_free_matching_engine.py)
- [web/src/test/OutputInvoiceCollectionsPage.test.tsx](../../../web/src/test/OutputInvoiceCollectionsPage.test.tsx)
- [tests/test_bank_split_document_scope_postgres.py](../../../tests/test_bank_split_document_scope_postgres.py)
- [web/src/test/OutputInvoiceCollectionApi.test.ts](../../../web/src/test/OutputInvoiceCollectionApi.test.ts)
- [web/e2e/output-invoice-status-tabs.spec.ts](../../../web/e2e/output-invoice-status-tabs.spec.ts)
- [web/e2e/production-output-invoice-summary.spec.ts](../../../web/e2e/production-output-invoice-summary.spec.ts)：显式生产只读模式下核验筛选、合计、导出和详情。

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
