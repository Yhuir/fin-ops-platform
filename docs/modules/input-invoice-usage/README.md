# 进项发票使用

入口：`/input-invoice-usage`。

核对进项发票与 OA、流水的使用和支付情况，管理支付规则及 OA 反提申请。

## 边界与 I/O

输入：分页、keyword、日期、filters、sort；反提 preview 使用独立 page/pageSize/keyword/bankRelation，提交精确 invoiceIds、申请人、预览证明、版本和幂等身份。输出：rows/summary/statistics/pagination/facets/classification、详情、导出、反提批次和草稿状态。

## 当前业务约定

- OA、流水与发票详情及多项关联详情统一从授权 canonical 快照投影原始字段；关系摘要只定位成员，不能充当原始详情。

- 同一只读快照组合 canonical 发票、active relation、OA 与银行用途。列表按关系组件展示，数量按去重发票张数统计，金额按实体去重。
- 银行摘要的 `bankShortName` 只取同一快照内银行全名与字符串尾号精确匹配的唯一账户简称；缺少映射或简称冲突时为空。原始银行名称、尾号、筛选和导出口径不变，列表不额外请求设置。
- 流水金额单元格统一显示原始流水金额、收支方向和银行账户标识，不显示用途分类或拆分子项标签；拆分数据及业务计算不变，子项在银行明细的现有拆分入口查看。
- 已使用为存在 active OA 或流水关系；待使用为两者都没有，判定依赖正式关系而非详情是否加载成功。`usage_status` 为 used/unused；`oa_relation` 为 linked/unlinked，在 OA 表头下拉筛选，不增加层级。原 `relation_status` 合同供反提等既有调用继续使用。
- 分类层级为全部 → 已使用/待使用；已使用 → 已付款/未付款/待核对。`classification` 与列表读取同一个快照，数量按去重发票张数统计，保留搜索、日期及 OA 等筛选，排除使用/付款分类自身筛选。表格分页仍按关联组计数。分类面板按父级配色，子分类自动换行，不横向滚动。
- 支付规则按优先级匹配，多个规则可输出同一分类；规则输出 `statusCode` 为稳定分类身份，`label` 可改名，`parentStatus` 指定 paid/unpaid。内置分类父级固定；自定义分类使用 custom_ 前缀，必须明确父级，同一分类的名称和父级必须一致。移除最后一条规则后自定义分类消失；禁用规则保留其零数量分类。配置、版本冲突、幂等与审计仍由 Settings owner CAS 原子保存。
- 已付款的金额分类为发票＝付款、发票＜付款、发票＞付款；规则可通过 `paymentComparison` 选择 equal/less/greater。比较使用正式关联组中去重发票价税合计与支出用途金额，正数且用途可确定时才成立；收入、混合方向、负数、未知金额或未能唯一确定用途的拆分流水保留待核对，不用绝对值强行算作付款。不新增全部/部分付款层级。规则优先，未命中规则时按明确的金额分类，无法判定则待核对。
- 修改规则后列表和分类一起刷新；删除当前分类后返回已使用并保留其它筛选。刷新失败明确反馈，不用旧分类伪装刷新成功。分类展示不修改关联关系、OA 数据、附件或发票原件。
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
- [web/e2e/input-invoice-hierarchy.spec.ts](../../../web/e2e/input-invoice-hierarchy.spec.ts)
- [web/e2e/input-invoice-grouped-header.spec.ts](../../../web/e2e/input-invoice-grouped-header.spec.ts)
- [tests/test_etc_relation_page_reads_postgres.py](../../../tests/test_etc_relation_page_reads_postgres.py)
- [tests/test_bank_split_document_scope_postgres.py](../../../tests/test_bank_split_document_scope_postgres.py)
- [tests/test_oa_reverse_occupancy_postgres.py](../../../tests/test_oa_reverse_occupancy_postgres.py)
- [tests/test_input_invoice_usage_api.py](../../../tests/test_input_invoice_usage_api.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
