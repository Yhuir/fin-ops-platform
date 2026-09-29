# OA 待付款核对

入口：`/oa-pending-payments`。

展示准入的进行中/已完成 OA，核对支付与正式关系，支持选择银行流水建立或扩展关系。

## 边界与 I/O

输入：分页、日期、搜索、状态与排序，以及 OA/银行精确身份和命令版本。输出：canonical OA rows、summary/statistics、关系与来源详情、候选及导出。

## 当前业务约定

- 原始 OA、银行、发票及多项关系详情复用公共来源投影，完整保留 OA 费用行和发票商品行，不以关联摘要补齐字段。

- 页面只读 PostgreSQL OA、准入与支付状态快照；请求热路径不访问外部财务源。
- 关系创建/扩展调用正式关系 owner，唯一 active case 可扩展并保留原发票；多个 owner 或版本冲突明确失败。
- OA source 的权威同步负责准入变化、源删除及关系成员清理；页面不猜外部删除。
- 支付状态由 OA worker 根据当前 active outflow 关系收敛，有支出为已支付、无支出为待支付；失败状态不被自动覆盖。
- OA 财务事实变化按实际月份通知匹配；仅支付状态变化不重新匹配。
- 展示行按正式关系与审批状态分组，跨归属月份合并；无正式关系的 OA 单独展示。已完成和进行中不混组，行身份不依赖月份。
- 筛选命中组后保留该组当前审批状态的全部 OA。OA 文本条件由同一成员满足；月份匹配任一 OA 归属月份，流水日期匹配任一关联支出成员。月份筛选后的组金额不是单月成本金额。
- 分段数量按真实 OA 身份计算，分页按展示行；关联支出合计按有效银行用途单元身份去重，原始流水数量与用途金额分别遵循银行 owner 合同。相同金额的不同单据不能去重。
- 列表按页批量读取、详情按需读取，分页与金额统计同快照。抽屉按稳定行身份读取完整组，不再从代表 OA 月份裁剪成员。选择合并行传递实际 OA 成员，来源导出仍逐单据输出。

## 依赖方向

[OA 集成](../oa-integration/README.md)、[正式关联关系](../workbench-relations/README.md)、[银行明细](../bank-details/README.md)、[后台任务](../runtime-workers/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/OaPendingPaymentsPage.tsx](../../../web/src/pages/OaPendingPaymentsPage.tsx)
- [backend/src/fin_ops_platform/app/routes_oa_pending_payments.py](../../../backend/src/fin_ops_platform/app/routes_oa_pending_payments.py)
- [backend/src/fin_ops_platform/services/oa_pending_payment_query_service.py](../../../backend/src/fin_ops_platform/services/oa_pending_payment_query_service.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/oa_pending_payment_query.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/oa_pending_payment_query.py)
- [tests/test_etc_relation_page_reads_postgres.py](../../../tests/test_etc_relation_page_reads_postgres.py)
- [tests/test_bank_split_document_scope_postgres.py](../../../tests/test_bank_split_document_scope_postgres.py)
- [tests/test_mongo_oa_adapter.py](../../../tests/test_mongo_oa_adapter.py)
- [tests/test_oa_projection_sql_runtime.py](../../../tests/test_oa_projection_sql_runtime.py)
- [tests/test_oa_pending_payment_source_snapshot_repository.py](../../../tests/test_oa_pending_payment_source_snapshot_repository.py)
- [tests/test_oa_payment_status_reconcile_service.py](../../../tests/test_oa_payment_status_reconcile_service.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
