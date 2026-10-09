# 进项发票使用

入口：`/input-invoice-usage`。

核对进项发票与 OA、流水的使用和支付情况，管理支付规则及 OA 反提申请。

## 边界与 I/O

输入：分页、keyword、日期、filters、sort；反提 preview 使用 page/pageSize/keyword/month/invoiceDateFrom/invoiceDateTo/filters，提交精确 invoiceIds、申请人、预览证明、版本和幂等身份。输出：rows/summary/statistics/pagination/facets/classification、详情、导出、反提批次和草稿状态。

## 当前业务约定

- 头部搜索位于统计右侧，年月按发票日期过滤，默认全部；月份与发票日期列筛选互相替换。导出初始范围继承关键词、月份日期边界、分类及 OA 筛选，预览和下载使用同一查询合同；导出抽屉中的日期和支付状态可以继续调整。支付规则在窄头部收进“更多”；OA 预填管理位于反提抽屉。

- OA、流水与发票详情及多项关联详情统一从授权 canonical 快照投影原始字段；关系摘要只定位成员，不能充当原始详情。流水详情按需在同一快照批量读取银行 owner 当前标签，输出 `bank_navigation` 和正文 `bank_labels`，不增加列表查询；切换已加载流水不请求 API。流水和发票导航均自动换行，发票顶部不显示尾号，完整号码保留在正文。

- 同一只读快照组合 canonical 发票、active relation、OA 与银行用途。列表按独立正式关系展示；ETC 展开保留所属关系，共享成员不连接不同关系。单行按关系内实体去重，页面汇总按筛选范围去重，因此共享发票的行数量之和可能大于总数。列表、详情、筛选和导出采用同一范围。
- 银行摘要的 `bankShortName` 只取同一快照内银行全名与字符串尾号精确匹配的唯一账户简称；缺少映射或简称冲突时为空。原始银行名称、尾号、筛选和导出口径不变，列表不额外请求设置。
- 流水金额单元格显示正式关系内业务用途的净额（支出减收入），方向为净支出、净收入或收支相抵；`netOutflow` 为有符号净支出，`netAmount` 为展示绝对金额，`original_amount` 保留原始发生额含义。详情保留逐笔原始金额、方向和银行账户，拆分子项在银行明细的既有入口查看。金额筛选和排序使用有符号净支出。
- 已使用为存在 active OA 或流水关系；待使用为两者都没有，判定依赖正式关系而非详情是否加载成功。`usage_status` 为 used/unused；`oa_relation` 为 linked/unlinked，在 OA 表头下拉筛选，不增加层级。`relation_status` 等既有关系筛选合同保留给当前查询调用。
- 分类表为全部 → 已使用 → 已付款/未付款 → 已配置规则标签，右侧待使用纵跨已使用各层；不另设使用状态选择器。付款父级与标签仅统计已使用范围，存在有效银行流水关联即已付款，否则为未付款；规则命中不改变正式使用状态。`classification` 与列表读取同一快照，数量按去重发票张数统计，保留搜索、日期、OA 及其它列筛选，排除使用状态、付款父级与标签自身筛选，切换分类仍展示完整分类计数；支付状态筛选选项保持原有查询范围。表格分页仍按关联组计数；共享成员可出现在多个独立关系，不能相加子栏数量推算去重总数。关联徽标 `+N` 表示总数。
- 支付规则为 HeroUI 原生单元格表格抽屉：启用、顺序、规则、OA 申请人、流水、发票与付款比较、发票净额、完全匹配、发票/OA 金额匹配及操作。行内使用原生下拉，窄屏在表格内横向滚动，底部保留新增、还原与保存。上下移动交换相邻优先级，保持规则和标签身份。条件之间为 AND，申请人数组内为任一匹配，按优先级首条命中。OA 匹配方式与指定姓名多选在同一单元格，支持不限制、无 OA、任意申请人、指定姓名；目录同名账号共同匹配，停用账号可选，历史缺失姓名可移除。流水可选不限、✓、✕；净额可选不限、＞0、≥0、＝0、≤0、＜0。选择无流水会清除草稿中的付款比较；选择无 OA 会清除申请人与 OA 金额匹配，还原恢复已保存条件。
- 多个规则可输出同一标签；规则 `id` 与输出 `statusCode` 保持稳定，`label` 可改名，同一身份名称必须一致。新增标签使用 custom_ 身份，复制规则复用标签身份并独立配置条件；不同条件的“冲”规则不合并。父级由实际流水关系决定，可出现的位置由显式条件决定，不再从 code 推导隐藏条件。删除最后一条规则移除该标签，禁用保留零数量标签，空规则集保持为空。设置 owner 继续以 CAS、幂等和审计原子保存，不覆盖其它配置 family。
- 发票净额取同一正式关系内去重发票的真实正负价税合计；任一金额缺失则净额未知。付款比较支持 equal/less/less_equal/greater/greater_equal，与关联业务用途净支出比较；净额 nonnegative/nonpositive 分别包含 positive/zero 与 negative/zero，缺失事实不满足任何金额条件。零和负净额同样可以比较，匹配使用当前事实，不修改历史 amount_check。没有命中任何规则时输出 `unclassified`，缺少比较事实时返回具体原因，仍归实际流水父级。摘要 `unclassifiedCount` 按去重发票计数。基础分类也是可编辑、可删除的显式规则，评估器没有隐藏分类分支。
- 表格“进项发票”组标题右侧展示当前完整筛选范围的去重张数、价税合计、税额合计，翻页不改变汇总。金额取带符号原始字段，不补算、不将缺失当零。API `summary.taxAmount` 为已知税额之和，`missingTaxAmountCount` 表示缺失数量，界面不能把部分数展示为完整税额合计。
- 保存规则成功后刷新列表与分类；失败保留草稿，版本冲突明确反馈。保存成功但刷新失败单独提示并允许重新刷新。删除当前标签回到对应付款父级，保留已使用范围及其它筛选。分类配置不修改关联关系、OA 数据、附件或原始发票；不包含“对方开错”的专用自动配对和识别。
- 支付规则申请人候选仅从 OA `sys_user` 的全部未删除用户读取，包含启用和停用账号，不扫描历史单据，不复用访问权限设置的账户排除范围；设置抽屉打开时读取，普通列表查询不访问 OA 目录。目录失败明确返回 503，不退回历史姓名。
- 申请人条件为 `applicantNames` 数组，任一姓名命中；姓名去除空白、零宽空格和 BOM 后去重匹配，目录按账号显示姓名、账号及只读状态图标，启用在前、停用在后，支持姓名/账号搜索；同名账号联动选择并合并为一个姓名条件。OA 单据只有姓名，不能据此区分同名账号。新选姓名保存时须仍在完整目录，停用账号可选可保存；目录外历史条件保留并可移除，不自动改成不限制。
- 反提候选复用待使用集合：同一发票无有效 OA 和流水关系，详情缺失不改变正式关系判定。打开抽屉继承主页面关键词、日期及其它筛选，移除使用/付款分类并固定待使用；弹窗搜索独立，关闭重开重新继承。查询按单张票去重并在分页前过滤、统计，同范围同一数据状态下候选与待使用的票数和金额一致。
- 反提占用票仍计入待使用候选但禁选；同批票必须全部有效且同一非空销方。精确选择、创建批次和暂存重试使用同一 canonical 使用状态复核，已关联 OA 或流水的票明确拒绝，不部分提交剩余票。反提 OA 申请人只来自启用、已绑定 OA 身份且完成验证的非敏感凭据选项。草稿创建刷新占用与暂存列表，不把草稿占用伪装成正式使用；正式关系变化后重新查询。成功请求幂等重放保留原结果，既有草稿和提交历史不因候选变化删除。
- 外部 OA 创建前持久化 draft_request 和版本并锁定票身份；相同请求不重复发送。未知结果需要人工核实和原因后释放，不自动删除远端草稿，迟到响应不能覆盖新版本。
- 反提抽屉通过两个按钮打开 HeroUI 原生右侧子抽屉：OA 申请人凭据、OA 草稿预填管理；两者互斥，关闭子抽屉保留父层选票、筛选和分页。配置入口不依赖候选查询成功或已有申请人；凭据管理仅管理员可见。
- 凭据抽屉默认空白表单直接新增，不显示常驻新增按钮；编辑时显示取消编辑，未修改直接重置，有修改复用放弃确认，确认后清空密码、备注和上一条保存错误。已配置账号不能重复新增，已绑定记录编辑时锁定账号，历史未绑定记录只能选择原登录账号并验证；删除当前编辑记录成功后恢复空白表单。账号可选状态由当前目录及凭据摘要计算，搜索、编辑、取消编辑不额外请求 API。
- 凭据表单只有 OA 姓名/登录账号组合下拉框、密码和选填备注。目录仅在打开管理抽屉时读取，按姓名/账号搜索，停用账号禁选；目录失败明确反馈，不使用历史名单代替。备注只影响显示，有值时展示为姓名（备注），不进入 OA 身份或真实申请人姓名。
- 每次保存均验证 OA 登录和返回身份，再提交凭据；失败保留表单和原记录，成功清空密码输入并刷新父层选项。历史未验证记录显示待验证，重新验证时保留原批次引用身份。删除移除整条本地配置；当前选择被删除时清空申请人，不自动换人，不删除历史批次或远端草稿。数据与外部调用合同由 OA 集成 owner 承担。
- OA 预填配置按批次冻结，修改只影响后续新建批次；进项与 ETC 配置独立。获本页权限的用户可以只读，管理员保存；同一非空销方等业务资格以提交前精确 preview 为准。
- 服务端分页、批量查询，当前页面请求查询预算最多 8 条；详情按需读取，导出上限 20,000 行。进项 canonical 查询缺少 repository 时明确失败，不回退进程内列表；共享原始字段 formatter 仍用于详情和导出。

- 进销项共用原件财务字段：金额、税额、价税合计、税率均不补算，缺失显示 `—`。真实零、负数、非数字税额、免税、不征税分别保留；真实明细全部显示，未提供明细时不把整票汇总伪装成一条明细。
- 关联组先用完整成员判定税率，再筛选；一种已知税率与未知成员并存时为 `—`，两个已知不同税率足以判定多税率。原始税率格式统一，不再存在的筛选值保持精确过滤并允许清除，不静默扩大范围。
- 列表“价税合计/税率”列第一行显示价税合计，第二行只显示灰色税率；不含税金额和税额保留在共享详情与 Excel。Excel 金额保持数值，金额来源单独列示。
- 列表使用本页原生语义表格，一级表头按进项发票 4 列、支付状态 1 列、OA 2 列、流水 3 列分组；支付状态纵跨两层表头。colgroup 统一列宽，两层表头整体吸顶、分页在滚动区外，筛选/排序/详情仍使用原有回调。正文统一底色，组边界贯穿表头和正文；完整约定见 [UI 说明](../../ui.md#普通页面的表格与操作层级)。

## 依赖方向

[正式关联关系](../workbench-relations/README.md)、[OA 集成](../oa-integration/README.md)、[设置](../settings/README.md)、[银行明细](../bank-details/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/InputInvoiceUsagePage.tsx](../../../web/src/pages/InputInvoiceUsagePage.tsx)
- [web/src/features/inputInvoiceUsage/api.ts](../../../web/src/features/inputInvoiceUsage/api.ts)
- [web/src/features/inputInvoiceUsage/usePaymentStatusRules.ts](../../../web/src/features/inputInvoiceUsage/usePaymentStatusRules.ts)：规则草稿、版本保存与列表刷新边界。
- [web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx](../../../web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx)：原生表格与条件编辑。
- [backend/src/fin_ops_platform/app/routes_input_invoice_usage.py](../../../backend/src/fin_ops_platform/app/routes_input_invoice_usage.py)
- [backend/src/fin_ops_platform/services/input_invoice_usage_canonical_query_service.py](../../../backend/src/fin_ops_platform/services/input_invoice_usage_canonical_query_service.py)
- [backend/src/fin_ops_platform/services/input_invoice_usage_service.py](../../../backend/src/fin_ops_platform/services/input_invoice_usage_service.py)
- [backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py](../../../backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py)
- [backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py](../../../backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py)
- [web/src/components/inputInvoiceUsage/OaApplicantCredentialsDrawer.tsx](../../../web/src/components/inputInvoiceUsage/OaApplicantCredentialsDrawer.tsx)
- [web/src/features/oaDraftPrefill.ts](../../../web/src/features/oaDraftPrefill.ts)
- [web/src/components/common/OaDraftPrefillDrawer.tsx](../../../web/src/components/common/OaDraftPrefillDrawer.tsx)
- [tests/test_invoice_usage_collection_canonical_query.py](../../../tests/test_invoice_usage_collection_canonical_query.py)
- [web/e2e/input-invoice-usage-flow.spec.ts](../../../web/e2e/input-invoice-usage-flow.spec.ts)
- [web/e2e/production-input-invoice-oa-reverse.spec.ts](../../../web/e2e/production-input-invoice-oa-reverse.spec.ts)：显式开启生产验证后，只读比对候选与待使用集合，并检查已使用票的精确预览拒绝。
- [web/e2e/input-invoice-hierarchy.spec.ts](../../../web/e2e/input-invoice-hierarchy.spec.ts)
- [web/e2e/production-input-invoice-hierarchy.spec.ts](../../../web/e2e/production-input-invoice-hierarchy.spec.ts)：显式开启的生产只读分类、搜索、汇总和三种宽度视觉验证。
- [web/e2e/input-invoice-payment-rules.spec.ts](../../../web/e2e/input-invoice-payment-rules.spec.ts)
- [tests/test_input_invoice_usage_payment_rules_postgres.py](../../../tests/test_input_invoice_usage_payment_rules_postgres.py)：规则迁移、SQL/Python 一致性、CAS、幂等与审计回滚。
- [web/e2e/input-invoice-grouped-header.spec.ts](../../../web/e2e/input-invoice-grouped-header.spec.ts)
- [tests/test_etc_relation_page_reads_postgres.py](../../../tests/test_etc_relation_page_reads_postgres.py)
- [tests/test_bank_split_document_scope_postgres.py](../../../tests/test_bank_split_document_scope_postgres.py)
- [tests/test_oa_reverse_occupancy_postgres.py](../../../tests/test_oa_reverse_occupancy_postgres.py)
- [tests/test_input_invoice_usage_api.py](../../../tests/test_input_invoice_usage_api.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
