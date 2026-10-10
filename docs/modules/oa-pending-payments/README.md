# OA付款情况

入口：`/oa-pending-payments`。

展示准入的进行中/已完成 OA，核对支付与正式关系，支持选择银行流水建立或扩展关系。

## 边界与 I/O

输入：分页、日期、搜索、状态与排序，以及 OA/银行精确身份和命令版本。输出：canonical OA rows、summary/statistics、关系与来源详情、候选及导出。

## 当前业务约定

- 搜索、OA 月份与操作位于页面头部，搜索在统计右侧、月份在右侧操作最前；规则入口在窄头部收进“更多”。导出继承当前已生效的流程分类、关联状态、搜索、月份、日期、列筛选和排序，覆盖完整命中范围，不受分页影响；读取失败保留重试，关联和拆分成功后继续重读。

- OA、流水、发票数量入口分别在原表格展开成员，数量包含原始成员，仅追加 N−1 行，复用原四列及列内布局；其它来源仅按正式关系提供上下文，不按数组位置配对。逐条 icon 使用与关联台相同的公共来源详情抽屉。退款流水也属于展示成员，支付统计继续只按原业务口径。原件保留全部费用行和商品行，不以关联摘要补齐字段。原始行和展开行复用[公共分组提示](../../ui.md#oa流水与发票来源详情)，使用同一淡蓝灰背景与左侧边线；每个列表仅一个活动父行，列表替换后清理展开状态，不新增请求。

- 页面只读 PostgreSQL OA、准入与支付状态快照；请求热路径不访问外部财务源。
- 查询、空结果和失败保留表头及滚动容器；切换查询清除旧结果与选择并回到纵向起点，横向位置保持。相同条件刷新保留当前结果与位置，读取失败清除结果并明确提示。加载时禁止建立关联，反馈使用固定状态区域，不推动表格。
- 银行摘要的 `bankShortName` 只取同一快照内银行全名与字符串尾号精确匹配的唯一账户简称；缺少映射或简称冲突时为空。原始银行名称、尾号、筛选和导出口径不变，列表不额外请求设置。
- 关系创建/扩展调用正式关系 owner，唯一 active case 可扩展并保留原发票；多个 owner 或版本冲突明确失败。
- OA source 的权威同步负责准入变化、源删除及关系成员清理；页面不猜外部删除。
- 支付状态由 OA worker 根据当前 active outflow 关系收敛，有支出为已支付、无支出为待支付；失败状态不被自动覆盖。
- OA 财务事实变化按实际月份通知匹配；仅支付状态变化不重新匹配。
- 展示行按正式关系与审批状态分组，跨归属月份合并；无正式关系的 OA 单独展示。已完成和进行中不混组，行身份不依赖月份。
- 筛选命中组后保留该组当前审批状态的全部 OA。OA 文本条件由同一成员满足；月份匹配任一 OA 归属月份，流水日期匹配任一关联支出成员。月份筛选后的组金额不是单月成本金额。
- 表格 OA、支付状态、流水、发票标题在各自区域居中；流水金额与摘要的表头和正文共用 24px 列间距。
- 分类切换为静态 OA 核对范围 → 已完成/进行中 → 已关联/未关联流水，父子区域直接相连，不增加混合流程视图。`summary.classificationCounts` 同时返回两个流程状态的关联计数，排除流程与关联状态自身筛选，保留其他查询条件；原 `statusCounts` 保留当前流程口径。
- 分段数量按真实 OA 身份计算，分页按展示行；关联支出合计按有效银行用途单元身份去重，原始流水数量与用途金额分别遵循银行 owner 合同。相同金额的不同单据不能去重。
- 列表按页批量读取、详情按需读取，分页与金额统计同快照。行内按稳定组身份展开完整关系，详情按单条身份读取。选择合并行传递实际 OA 成员，导出逐单据输出，数量按去重 OA 身份计算；筛选命中组后保留同组当前流程成员，与列表一致。导出抽屉只显示数量和一个导出操作，不再选择来源。数量查询与文件查询复用组筛选，下载保留原字段、权限和审计。

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
