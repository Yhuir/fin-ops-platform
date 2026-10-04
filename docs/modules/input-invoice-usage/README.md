# 进项发票使用

入口：`/input-invoice-usage`。

核对进项发票与 OA、流水的使用和支付情况，管理支付规则及 OA 反提申请。

## 边界与 I/O

输入：分页、keyword、日期、filters、sort；反提 preview 使用独立 page/pageSize/keyword/bankRelation，提交精确 invoiceIds、申请人、预览证明、版本和幂等身份。输出：rows/summary/statistics/pagination/facets、详情、导出、反提批次和草稿状态。

## 当前业务约定

- OA、流水与发票详情及多项关联详情统一从授权 canonical 快照投影原始字段；关系摘要只定位成员，不能充当原始详情。

- 同一只读快照组合 canonical 发票、active relation、OA 与银行用途。列表按关系组件展示，数量按去重发票张数统计，金额按实体去重。
- 银行摘要的 `bankShortName` 只取同一快照内银行全名与字符串尾号精确匹配的唯一账户简称；缺少映射或简称冲突时为空。原始银行名称、尾号、筛选和导出口径不变，列表不额外请求设置。
- relation_status 为 no_oa/oa_no_bank/oa_bank；facet 排除自身筛选，不把缺失详情误判为无关系。
- 支付规则支持新增、删除和修改；输出 paid/cash_turnover/offset/waiting_payment，未命中为显式待核对。配置与审计由 Settings owner CAS 保存，读取不补造规则。
- 支付规则申请人候选仅从 OA `sys_user` 的全部未删除用户读取，包含启用和停用账号，不扫描历史单据，不复用访问权限设置的账户排除范围；设置抽屉打开时读取，普通列表查询不访问 OA 目录。目录失败明确返回 503，不退回历史姓名。
- 申请人条件为 `applicantNames` 数组，任一姓名命中；姓名去除空白、零宽空格和 BOM 后去重匹配，目录按账号显示姓名、账号及只读状态图标，启用在前、停用在后，支持姓名/账号搜索；同名账号联动选择并合并为一个姓名条件。OA 单据只有姓名，不能据此区分同名账号。新选姓名保存时须仍在完整目录，停用账号可选可保存；目录外历史条件保留并可移除，不自动改成不限制。
- 反提默认候选为未关联 OA 的单张进项票；占用票仍可见但禁选，精确选择必须全部有效。申请人只来自启用且有凭据的非敏感选项。
- 外部 OA 创建前持久化 draft_request 和版本并锁定票身份；相同请求不重复发送。未知结果需要人工核实和原因后释放，不自动删除远端草稿，迟到响应不能覆盖新版本。
- OA 预填配置按批次冻结；同一非空销方等业务资格以提交前精确 preview 为准。
- 服务端分页、批量查询，当前页面请求查询预算最多 8 条；详情按需读取，导出上限 20,000 行。

- 进销项共用原件财务字段：金额、税额、价税合计、税率均不补算，缺失显示 `—`。真实零、负数、非数字税额、免税、不征税分别保留；真实明细全部显示，未提供明细时不把整票汇总伪装成一条明细。
- 关联组先用完整成员判定税率，再筛选；一种已知税率与未知成员并存时为 `—`，两个已知不同税率足以判定多税率。原始税率格式统一，不再存在的筛选值保持精确过滤并允许清除，不静默扩大范围。
- 列表“价税合计/税率”列第一行显示价税合计，第二行只显示灰色税率；不含税金额和税额保留在共享详情与 Excel。Excel 金额保持数值，金额来源单独列示。
- 列表使用本页原生语义表格，一级表头按进项发票 4 列、支付状态 1 列、OA 2 列、流水 3 列分组；支付状态纵跨两层表头。colgroup 统一列宽，两层表头整体吸顶、分页在滚动区外，筛选/排序/详情仍使用原有回调。正文统一底色，组边界贯穿表头和正文；完整约定见 [UI 说明](../../ui.md#普通页面的表格与操作层级)。

## 依赖方向

[正式关联关系](../workbench-relations/README.md)、[OA 集成](../oa-integration/README.md)、[设置](../settings/README.md)、[银行明细](../bank-details/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/InputInvoiceUsagePage.tsx](../../../web/src/pages/InputInvoiceUsagePage.tsx)
- [web/src/features/inputInvoiceUsage/api.ts](../../../web/src/features/inputInvoiceUsage/api.ts)
- [backend/src/fin_ops_platform/app/routes_input_invoice_usage.py](../../../backend/src/fin_ops_platform/app/routes_input_invoice_usage.py)
- [backend/src/fin_ops_platform/services/input_invoice_usage_canonical_query_service.py](../../../backend/src/fin_ops_platform/services/input_invoice_usage_canonical_query_service.py)
- [backend/src/fin_ops_platform/services/input_invoice_usage_service.py](../../../backend/src/fin_ops_platform/services/input_invoice_usage_service.py)
- [backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py](../../../backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py)
- [backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py](../../../backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py)
- [web/src/features/oaDraftPrefill.ts](../../../web/src/features/oaDraftPrefill.ts)
- [web/src/components/common/OaDraftPrefillDrawer.tsx](../../../web/src/components/common/OaDraftPrefillDrawer.tsx)
- [tests/test_invoice_usage_collection_canonical_query.py](../../../tests/test_invoice_usage_collection_canonical_query.py)
- [web/e2e/input-invoice-usage-flow.spec.ts](../../../web/e2e/input-invoice-usage-flow.spec.ts)
- [web/e2e/input-invoice-grouped-header.spec.ts](../../../web/e2e/input-invoice-grouped-header.spec.ts)
- [tests/test_etc_relation_page_reads_postgres.py](../../../tests/test_etc_relation_page_reads_postgres.py)
- [tests/test_bank_split_document_scope_postgres.py](../../../tests/test_bank_split_document_scope_postgres.py)
- [tests/test_oa_reverse_occupancy_postgres.py](../../../tests/test_oa_reverse_occupancy_postgres.py)
- [tests/test_input_invoice_usage_api.py](../../../tests/test_input_invoice_usage_api.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
