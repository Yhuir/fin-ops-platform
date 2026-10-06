# 待找发票

入口：`/pending-invoices`。

按银行收支用途核对发票取得状态，提供候选选择、已有发票关联、收入状态维护和规则设置。

## 边界与 I/O

输入：direction/filter/date/keyword/field filters/sort/page/include_statistics；写操作输入精确流水/发票集合、版本与受信 actor。输出：rows、summary、statistics、acquisition_summary、候选、详情和导出。

## 当前业务约定

- 单项与关系详情使用同一来源字段投影；发票按真实票身份读取全部商品行，OA 保留全部费用明细，拆分流水归并原始父交易。

- 银行分类复用银行 owner；关系读取 active typed members，跨月关系不按当前月份截断，排除 turnover_manual_closure。
- OA completed/in-progress 与 ETC 正式发票成员都来自 PostgreSQL 当前事实；银行用途与父流水金额区分，原始流水计数按父身份去重。
- 分类切换采用连续三层区域：全部流水 → 支出/收入 → 各自发票状态，无外框和嵌套卡片。`acquisition_summary.scope_status_counts` 排除方向与状态自身条件，保留其他筛选，供两个方向同时展示；原 `status_counts` 保留当前方向口径。统计按原始流水身份去重，包含真实零值，不从当前页推导。
- 分类点击与列多选使用同一查询状态；子分类只命中部分底层状态时明确显示部分选中。导出抽屉继承方向、状态、搜索、列条件、日期与排序，抽屉修改方向/状态/日期后预览和下载使用相同查询。
- 发票价税合计只读取原字段。关联发票缺少价税合计时，整组金额及待付金额显示缺失，已付流水金额保留；状态为“已开票·金额缺失”，归入“金额待核对”。候选票仍显示，但不能执行依赖价税合计的关联确认。有价税合计而缺不含税金额的票不受此限制。
- 首屏不聚合高基数候选，filter-options 后续有界读取，每字段最多 50 项；发票候选使用服务端过滤排序分页。
- 关联命令由正式关系 owner 提交；失败保留用户选择，成功才回读。合法空集、加载和错误分开显示。
- 详情只返回公开来源字段；导出复用业务查询，最大 20,000 行，超限明确报错。

## 依赖方向

[银行明细](../bank-details/README.md)、[正式关联关系](../workbench-relations/README.md)、[发票导入](../imports-invoices/README.md)、[OA 待付款核对](../oa-pending-payments/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/PendingInvoicesPage.tsx](../../../web/src/pages/PendingInvoicesPage.tsx)
- [web/src/features/pendingInvoices/api.ts](../../../web/src/features/pendingInvoices/api.ts)
- [backend/src/fin_ops_platform/app/routes_pending_invoices.py](../../../backend/src/fin_ops_platform/app/routes_pending_invoices.py)
- [backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py](../../../backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py)
- [backend/src/fin_ops_platform/services/pending_invoice_service.py](../../../backend/src/fin_ops_platform/services/pending_invoice_service.py)
- [backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py](../../../backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [tests/test_pending_invoice_canonical_query.py](../../../tests/test_pending_invoice_canonical_query.py)
- [tests/test_pending_invoice_api.py](../../../tests/test_pending_invoice_api.py)
- [tests/test_etc_relation_page_reads_postgres.py](../../../tests/test_etc_relation_page_reads_postgres.py)
- [tests/test_bank_split_consumers_postgres.py](../../../tests/test_bank_split_consumers_postgres.py)
- [tests/test_pending_invoice_service.py](../../../tests/test_pending_invoice_service.py)
- [tests/test_pending_invoice_relation_identity.py](../../../tests/test_pending_invoice_relation_identity.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
