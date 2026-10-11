# 进项发票使用

入口：`/input-invoice-usage`。

核对进项发票与 OA、流水的使用和支付情况，管理支付规则及 OA 反提申请。

## 边界与 I/O

输入：分页、keyword、日期、filters、sort；反提 preview 使用 page/pageSize/keyword/month/invoiceDateFrom/invoiceDateTo/filters，提交精确 invoiceIds、申请人、预览证明、版本和幂等身份。输出：rows/summary/statistics/pagination/facets/classification、详情、导出、反提批次和草稿状态。

## 当前业务约定

- 头部搜索位于统计右侧，年月按发票日期过滤，默认全部；月份与发票日期列筛选互相替换。导出继承已生效关键词、月份日期边界、完整分类及 OA/列筛选和排序，覆盖全部命中结果。抽屉只显示去重发票张数和一个导出操作，不提供二次筛选或明细预览；数量与下载使用同一查询，先按完整关联组判定条件，再展开去重发票身份并执行导出上限。支付规则在窄头部收进“更多”；OA 预填管理位于反提抽屉。

- OA、流水、发票详情使用公共单条来源抽屉；三种“共 N”分别展开对应实体，N 包含原始成员，点击只新增其余 N−1 行。原始行与展开行复用同一十列渲染，单据字段取各自原件；其它列按正式关系展示上下文，不按数组位置配对。发票/OA 视图的共同流水金额保持业务净额，流水视图显示各笔原始金额。三种入口共用活动父行，使用公共淡蓝灰背景、左侧边线和展开/收起动效，不新增请求；列表替换后清理旧状态。来源详情按原始身份读取，保留同票全部商品行；拆分流水回到父交易。

- 同一只读快照组合 canonical 发票、active relation、OA 与银行用途。进项查询直接复用已确定的正式关系归属，不再通过发票别名重复反查关系；列表按独立正式关系展示；ETC 展开保留所属关系，共享成员不连接不同关系。单行按关系内实体去重，页面汇总按筛选范围去重，因此共享发票的行数量之和可能大于总数。列表、详情、筛选和导出采用同一范围。
- 银行摘要的 `bankShortName` 只取同一快照内银行全名与字符串尾号精确匹配的唯一账户简称；缺少映射或简称冲突时为空。原始银行名称、尾号、筛选和导出口径不变，列表不额外请求设置。
- 流水金额单元格显示正式关系内业务用途的净额（支出减收入），方向为净支出、净收入或收支相抵；`netOutflow` 为有符号净支出，`netAmount` 为展示绝对金额，`original_amount` 保留原始发生额含义。详情保留逐笔原始金额、方向和银行账户，拆分子项在银行明细的既有入口查看。金额筛选和排序使用有符号净支出。
- 已使用为存在 active OA、流水关系或命中启用支付规则；待使用为三者均不存在。先按完整正式关联组判定规则，再按发票身份汇总使用状态；共享发票只要任一组满足条件就不进入待使用，独立正式关系仍独立展示，不连接成新关系。判定依赖正式关系和规则命中证据，而非详情是否加载成功。`usage_status` 为 used/unused；`oa_relation` 为 linked/unlinked，在 OA 表头下拉筛选，不增加层级。`relation_status` 等既有关系筛选合同保留给当前查询调用。
- 分类表为全部 → 已使用 → 已付款/未付款 → 已配置规则标签，右侧待使用纵跨已使用各层；不另设使用状态选择器。付款父级与标签仅统计已使用范围，存在有效银行流水关联即已付款，否则为未付款；规则命中使发票进入已使用，但不写入或伪造正式 OA/流水关系。未命中“未分类”不算规则命中；禁用、删除或变更规则立即按当前快照重判。`classification` 与列表读取同一快照，数量按去重发票张数统计，保留搜索、日期、OA 及其它列筛选，排除使用状态、付款父级与标签自身筛选，切换分类仍展示完整分类计数；支付状态筛选选项保持原有查询范围。表格分页仍按关联组计数；共享成员可出现在多个独立关系，不能相加子栏数量推算去重总数。关联徽标“共 N”表示总数。
- 支付规则为原生语义表格抽屉，沿用公共财务表格的视觉样式与 HeroUI 表单控件，按 oil-ui 已确认的紧凑表格设计：付款状态、顺序、启用、规则、OA 申请人、是否有流水、发票 VS 流水、发票净额（正数票+负数票）及删除。左侧连续色块按有流水/无流水分为已付款/未付款；启用为 Checkbox，条件下拉不显示箭头，窄屏仅表格横向滚动。顺序列显示拖拽手柄和组内只读序号，支持鼠标及键盘操作；分组标题不参与拖拽。没有复制、数字优先级输入、常驻重新加载、完全匹配或发票/OA 金额匹配条件。加载错误和版本冲突保留重试读取入口，有草稿时先确认放弃。
- `conditions.hasBank` 必须是布尔值，规则分组只由该条件派生；新增在表格底部展开行内表单，先选分组和新标签/既有标签，切换流水条件立即追加到目标分组末尾，禁用仍保留位置。已付款与未付款各自独立排序、分别从 1 编号；同组从上到下采用第一条启用且满足条件的规则，不能跨组拖拽。条件之间为 AND，申请人数组内任一命中；同标签重叠仍取最先命中规则作为证据，匹配顺序不改变正式关系或金额事实。SQL 一次产出命中规则身份，列表 formatter 只读取该证据，不逐行重复匹配；筛选、统计、导出使用相同顺序，分类树按实际流水父级显示规则标签及有数量的未分类。
- OA 匹配支持不限、无 OA、任意申请人、指定姓名；同名账号共同匹配，停用账号可选，历史缺失姓名可移除。净额可选不限、＞0、≥0、＝0、≤0、＜0。无流水清除草稿中的付款比较；无 OA 清除申请人；切回有流水不自动恢复旧比较，还原才恢复已保存条件。
- 多个规则可输出同一标签；规则 `id` 与输出 `statusCode` 保持稳定，`label` 可改名，同一身份名称必须一致。新增标签使用 custom_ 身份，新增时显式选择既有标签可复用其身份并独立配置条件；不同条件的“冲”规则不合并。父级由实际流水关系决定，可出现的位置由显式条件决定，不再从 code 推导隐藏条件。删除最后一条规则移除该标签，禁用保留零数量标签，空规则集保持为空。设置 owner 继续以 CAS、幂等和审计原子保存，不覆盖其它配置 family。
- 发票净额取同一正式关系内去重发票的真实正负价税合计；任一金额缺失则净额未知。付款比较支持 equal/less/less_equal/greater/greater_equal，与关联业务用途净支出比较；净额 nonnegative/nonpositive 分别包含 positive/zero 与 negative/zero，缺失事实不满足任何金额条件。零和负净额同样可以比较，匹配使用当前事实，不修改历史 amount_check。没有命中任何规则时输出 `unclassified`，缺少比较事实时返回具体原因，仍归实际流水父级。摘要 `unclassifiedCount` 按去重发票计数。基础分类也是可编辑、可删除的显式规则，评估器没有隐藏分类分支。
- 表格“进项发票”组标题右侧展示当前完整筛选范围的去重张数、价税合计、税额合计，翻页不改变汇总。金额取带符号原始字段，不补算、不将空值当零。API `summary.taxAmount` 汇总原始数值税额，无可汇总数值时显示 `—`，真实零和负数保留；表头使用“税额合计”，不展示“缺失 N 张”。`missingTaxAmountCount` 继续保留在 API 合同中，表示数值税额为空的票数，不代表发票丢失或支付规则异常。
- 拖拽只修改草稿，保存期间锁定编辑；还原或拖回原顺序不提交。配置以有流水组、无流水组依次保存，组内相对顺序保持。保存规则成功后刷新列表与分类；失败保留草稿，同一提交重试沿用幂等键，版本冲突明确反馈。保存成功但刷新失败单独提示并允许重新刷新。删除当前标签回到对应付款父级，保留已使用范围及其它筛选。分类配置不修改关联关系、OA 数据、附件或原始发票；不包含“对方开错”的专用自动配对和识别。
- 支付规则申请人候选仅从 OA `sys_user` 的全部未删除用户读取，包含启用和停用账号，不扫描历史单据，不复用访问权限设置的账户排除范围；设置抽屉打开时读取，普通列表查询不访问 OA 目录。目录失败明确返回 503，不退回历史姓名。
- 申请人条件为 `applicantNames` 数组，任一姓名命中；姓名去除空白、零宽空格和 BOM 后去重匹配，目录按账号显示姓名、账号及只读状态图标，启用在前、停用在后，支持姓名/账号搜索；同名账号联动选择并合并为一个姓名条件。OA 单据只有姓名，不能据此区分同名账号。新选姓名保存时须仍在完整目录，停用账号可选可保存；目录外历史条件保留并可移除，不自动改成不限制。
- 反提候选复用待使用集合：同一发票无有效 OA 和流水关系，详情缺失不改变正式关系判定。打开抽屉继承主页面关键词、日期及其它筛选，移除使用/付款分类并固定待使用；弹窗搜索独立，关闭重开重新继承。查询按单张票去重并在分页前过滤、统计，同范围同一数据状态下候选与待使用的票数和金额一致。
- 反提占用票仍计入待使用候选但禁选；同批票必须全部有效且同一非空销方。精确选择、创建批次和暂存重试使用同一 canonical 使用状态复核，已关联 OA 或流水的票明确拒绝，不部分提交剩余票。反提 OA 申请人只来自启用、已绑定 OA 身份且完成验证的非敏感凭据选项。草稿创建刷新占用与暂存列表，不把草稿占用伪装成正式使用；正式关系变化后重新查询。成功请求幂等重放保留原结果，既有草稿和提交历史不因候选变化删除。
- 外部 OA 创建前持久化 draft_request 和版本并锁定票身份；相同请求不重复发送。未知结果需要人工核实和原因后释放，不自动删除远端草稿，迟到响应不能覆盖新版本。
- 反提抽屉通过两个按钮打开 HeroUI 原生右侧子抽屉：OA 申请人凭据、OA 草稿预填管理；两者互斥，关闭子抽屉保留父层选票、筛选和分页。配置入口不依赖候选查询成功或已有申请人；凭据管理仅管理员可见。
- 凭据抽屉默认空白表单直接新增，不显示常驻新增按钮；编辑时显示取消编辑，未修改直接重置，有修改复用放弃确认，确认后清空密码、备注和上一条保存错误。已配置账号不能重复新增，编辑固定显示已保存账号，历史未绑定记录按原账号唯一匹配目录并验证；删除当前编辑记录成功后恢复空白表单。账号可选状态由当前目录及凭据摘要计算，搜索、编辑、取消编辑不额外请求 API。
- 凭据表单只有账号、密码和选填备注；新增用 OA 姓名/登录账号组合下拉框，编辑用只读账号。目录仅在打开管理抽屉时读取，按姓名/账号搜索，停用账号禁选；凭据与目录独立并行加载，目录失败明确反馈，不阻止已绑定凭据编辑，不使用历史名单代替目录。备注只影响显示，有值时展示为姓名（备注），不进入 OA 身份或真实申请人姓名。
- 新增或修改密码验证 OA 登录和返回身份后提交；已验证记录仅改备注无需重输密码或访问 OA。失败保留表单和原记录，成功清空密码输入并刷新父层选项。历史记录显示“已保存 · 待验证”，编辑回填原账号和备注，可留空使用存量密码验证，保留原批次引用身份。删除移除整条本地配置；当前选择被删除时清空申请人，不自动换人，不删除历史批次或远端草稿。数据与外部调用合同由 OA 集成 owner 承担。
- OA 预填配置按批次冻结，修改只影响后续新建批次；进项与 ETC 配置独立。获本页权限的用户可以只读，管理员保存；同一非空销方等业务资格以提交前精确 preview 为准。反提候选直接投影主查询的待使用集合，再按单票分页；精确选票使用同一查询，规则命中票以 `already_classified_by_rule` 明确拒绝，创建草稿前重新验证，拒绝不产生 OA 或批次副作用。
- 服务端分页、批量查询，当前页面请求查询预算最多 8 条；详情按需读取，导出上限 20,000 行。进项 canonical 查询缺少 repository 时明确失败，不回退进程内列表；共享原始字段 formatter 仍用于详情和导出。

- 进销项共用原件财务字段：金额、税额、价税合计、税率均不补算，缺失显示 `—`。真实零、负数、非数字税额、免税、不征税分别保留；真实明细全部显示，未提供明细时不把整票汇总伪装成一条明细。
- 关联组先用完整成员判定税率，再筛选；一种已知税率与未知成员并存时为 `—`，两个已知不同税率足以判定多税率。原始税率格式统一，不再存在的筛选值保持精确过滤并允许清除，不静默扩大范围。
- 列表原始行和展开行的“价税合计/税率”显示单票原始价税合计与灰色税率，不显示组净额汇总正文行；金额与税率筛选、排序仍按完整关联组执行，表头提示筛选、排序按关联组计算。不含税金额和税额保留在共享详情与 Excel。Excel 金额保持数值，金额来源单独列示。
- 列表使用本页原生语义表格，一级表头按进项发票 4 列、支付状态 1 列、OA 2 列、流水 3 列分组；支付状态纵跨两层表头。colgroup 统一列宽，两层表头整体吸顶、分页在滚动区外，筛选/排序/详情仍使用原有回调。普通正文统一底色，配对展开范围使用公共分组背景和边线，列组边界贯穿表头和正文；完整约定见 [UI 说明](../../ui.md#普通页面的表格与操作层级)。

## 依赖方向

[正式关联关系](../workbench-relations/README.md)、[OA 集成](../oa-integration/README.md)、[设置](../settings/README.md)、[银行明细](../bank-details/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/InputInvoiceUsagePage.tsx](../../../web/src/pages/InputInvoiceUsagePage.tsx)
- [web/src/features/inputInvoiceUsage/api.ts](../../../web/src/features/inputInvoiceUsage/api.ts)
- [web/src/features/inputInvoiceUsage/usePaymentStatusRules.ts](../../../web/src/features/inputInvoiceUsage/usePaymentStatusRules.ts)：规则草稿、版本保存与列表刷新边界。
- [web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx](../../../web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx)：原生表格、组内拖拽与条件编辑。
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
- [web/e2e/input-invoice-payment-rule-order.spec.ts](../../../web/e2e/input-invoice-payment-rule-order.spec.ts)：鼠标、键盘、跨组边界、取消与保存读回。
- [web/src/test/usePaymentStatusRules.test.ts](../../../web/src/test/usePaymentStatusRules.test.ts)：草稿顺序、分组移动、权限与幂等重试。
- [web/e2e/production-payment-rules.spec.ts](../../../web/e2e/production-payment-rules.spec.ts)：生产只读合同与分组三档宽度视觉验证，草稿操作不保存。
- [tests/test_input_invoice_usage_payment_rules_postgres.py](../../../tests/test_input_invoice_usage_payment_rules_postgres.py)：规则迁移、SQL/Python 一致性、CAS、幂等与审计回滚。
- [web/e2e/input-invoice-grouped-header.spec.ts](../../../web/e2e/input-invoice-grouped-header.spec.ts)
- [tests/test_etc_relation_page_reads_postgres.py](../../../tests/test_etc_relation_page_reads_postgres.py)
- [tests/test_bank_split_document_scope_postgres.py](../../../tests/test_bank_split_document_scope_postgres.py)
- [tests/test_oa_reverse_occupancy_postgres.py](../../../tests/test_oa_reverse_occupancy_postgres.py)
- [tests/test_input_invoice_usage_api.py](../../../tests/test_input_invoice_usage_api.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
