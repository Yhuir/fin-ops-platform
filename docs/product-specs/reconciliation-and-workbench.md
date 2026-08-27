# 关联台与正式关系产品口径

更新日期：2026-08-26

## 用户可见状态

关联台只存在两种关系状态：

1. `paired`：对象属于一条 `app.workbench_pair_relations.status='active'` 的正式关系，该关系当前持久化的 OA/发票要求已经满足，且关系内全部 OA 的流程状态均为 `completed`；同一关系的全部成员显示在同一组。
2. `unpaired`：不属于 active relation 的 canonical fact 独立显示；尚未满足材料完整性要求或仍包含 `in_progress` OA 的 active relation 保持同一 case 分组。材料缺失明确显示缺少的 OA、银行流水或发票，流程阻断返回 `blocking_reasons=['oa_in_progress']`。

不存在第三种“自动候选”“待确认配对”“假配对”或“隐藏但仍存在”的用户关系状态。系统未能安全正式化的计算结果不持久化、不合并行、不隐藏事实，也不进入下游已关联口径。

## 完整性不变量

- 设统一事实源中可见 canonical facts 为 `C`，要求已满足的 active relation members 为 `R_complete`，要求未满足的 active relation members 为 `R_incomplete`，则 `paired = R_complete`、`unpaired = R_incomplete ∪ (C - active relation members)`。
- `paired` 与 `unpaired` 不相交，二者并集必须精确等于 `C`；任何事实不得遗漏、重复显示或同时属于两个 active case。
- 发票数量以统一发票池 canonical row ID 为唯一统计身份。ETC 批次即使折叠为一个 summary 展示对象，也必须按明确 canonical row id / `etc_invoice_id` 展开到批次内每张 canonical 发票后再计数；不得把 summary 当成一张发票，也不得按金额、名称或顺序推断成员。同一 canonical 发票若存在 paired owner 只计入 paired，否则只计入 unpaired，因此 `已配对 canonical 发票数 + 未配对 canonical 发票数 = 当前 scope 统一发票池 canonical 发票总数`。
- 历史 `case_id`、row 上残留的 `case_id`、来源标签和旧 case 前缀都不能决定分组。含银行流水的普通关系只读取 canonical relation 当前持久化的 `requires_oa` / `requires_invoice`；缺失证明 fail closed，不得在读路径临时回查当前规则或按旧 case 前缀放行。规则保存后的增量任务必须先通过正式 relation command 更新 metadata/history，再刷新精确 Workbench 月份。
- 普通 OA 付款关系必须包含银行流水才算完整；OA 与附件发票的 immutable binding 只表达不可拆分 ownership，缺银行时整组保留 active case 但位于 `unpaired`。显式 batch-accounting 与 ETC batch relation 继续按登记豁免处理。
- 进行中 OA 可以与银行流水和发票写入同一正式关系，也可以扩展唯一已存在的银行-发票 active case；不得为进行中 OA 建立第二套 pending relation 或隐藏银行流水。关系满足全部材料要求后仍停留在 `unpaired`，直到所有 OA 完成；OA sync 将同一 OA 迁入 completed canonical projection 后，原 case 不变并在下一次 Workbench normal GET 进入 `paired`。多 OA 关系中任一 OA 进行中即阻断整组。
- `app.oa_pending_payment_admissions` 是进行中 OA 的唯一 canonical 读取源；`app.workbench_pair_relations` 是 completed/in-progress 共用的唯一 active relation owner。历史 `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims` 及事件只读审计，不参与运行时分组、占用、source proof 或 promotion。
- 一条 active relation 可以是任意非空的 OA/银行流水/发票成员组合，包括一对一、一对多、多对一以及 `N:M:K`。关系来源不形成用户可见的业务状态区分。

## 人工正式关系

- 人工确认只要求至少选择 2 个不同的 canonical 成员；每个请求 ID 必须精确解析为 `oa|bank|invoice` canonical row，同栏、跨栏、一对多、多对一和多对多组合均可提交。重复 identity、缺失或已失效成员、未知类型、active owner 冲突、版本冲突和非法 synthetic summary 仍须 fail closed。
- 金额相等、方向已知和材料完整性不再是人工创建 active relation 的门槛。金额不一致或方向不确定时，预览继续通过既有 `amount_check.requires_note` 要求填写 `note`；说明随正式关系与审计历史保存，不新增字段。创建后的关系仍按持久化完成要求与 OA 流程状态决定进入 `paired` 或保持在 `unpaired`，不能因人工确认伪装完整。
- 银行分类不选择人工关系的 mutation owner。选择中部分或全部银行成员为 `internal_transfer` 时，`confirm-link` 仍以 `manual_confirmed` 进入标准 relation command/UoW；不得返回 no-OA batch 专属冲突或转交该批次入口。独立 no-OA batch 功能、其专属入口和登记 relation mode 保持不变。
- 外部往来款是上述通用人工关系中的唯一窄特例：当选择同时含 OA 与至少两条银行流水，且全部银行流水的 canonical 分类明确给出 `turnover_role=external_turnover`、action、family、counterparty，既有 Turnover 校验器又证明它们属于同一业务语义、同时包含本金与结算两侧且收支差额为 `0.00` 时，关联台直接写 `relation_mode=turnover_manual_closure`。付款 OA 的金额只与支出本金侧比较；收款 OA 对称地只与收入本金侧比较。普通付款、单边流水、非零差额选择和非外部往来款仍使用 `manual_confirmed` 与既有净额规则；结构化往来语义缺失或冲突必须明确失败，禁止根据摘要、备注、显示标签或金额形态猜测。
- 未配对区中已经属于 active relation 的整组可执行关系级撤回。preview 与 submit 必须提交和当前完整 active relation 精确相等的 canonical 成员集合，不能用子集触发后端隐式扩张，也不能混入其它 case 成员。撤回以 case、expected versions 和拓扑 preview fingerprint 为并发合同；fingerprint 锁定 current/after relations 的 case/version/status/完整 typed members 以及最近 confirm history identity。在同一关系命令事务中先计算 current 与 predecessor 的完整 case/member 锁集合、一次全局稳定排序取得锁；重载并重算拓扑，且重验 canonical member、restored case 未被复用和唯一 active owner 后，才撤销当前拓扑并从 `before_relations` 恢复上一稳定拓扑。没有可恢复关系的成员才回到独立 `unpaired` singleton，任一冲突整笔 fail closed。不得按 row `case_id`、展示 metadata 或非稳定历史猜测恢复。
- 上述放宽只适用于人工确认。确定性自动正式化继续执行下节全部精确金额、币种/方向、强证据、唯一性、资源上限和撤回指纹规则，不得复用人工入口绕过自动匹配门禁。

## 确定性自动正式化

自动匹配引擎只输出可直接提交到正式关系命令边界的 `FormalRelationPlan`，不输出候选或 decision 状态。计划必须在同一个 UoW 中通过 `WorkbenchRelationCommandService` 写入 active relation、history、幂等记录和 durable refresh outbox；部分失败必须整体回滚。

安全规则如下：

- 允许显式 canonical source/reference 跨全部保留历史查找；显式引用必须唯一指向 typed canonical identity。
- 组合证据最多跨 365 天，不限制为同月。窗口边界按真实日期计算，366 天必须拒绝。
- 金额按最小货币单位精确比较；关系中每个已出现 pane 的合计必须相等，币种和收支方向必须一致。
- 每个成员必须通过税号、规范化对方名称、发票号/数电票号、项目号、流水号、source link 等允许的强证据边接入同一个连通证据图。
- 金额相同本身不是证据；模糊文本、日期接近、通用词或仅项目描述不得单独建立关系。
- 同一 component 存在多个竞争闭合、共享引用不唯一、成员冲突或证据图不连通时 fail closed，未形成 active relation 的事实继续作为 `unpaired` 单行显示。
- 搜索状态数、内存和工作量有硬上限；达到上限只记录阻断原因，不创建部分关系。
- 红冲、退款和反向流水只有存在对原始业务事实的唯一显式引用时才允许自动正式化。
- 已在 active relation 中的成员保持稳定；系统只能在唯一且安全时扩展原 case，不能重建第二条关系。
- 用户撤回的精确 typed member set 形成阻断指纹，自动引擎不得再次创建同一关系。

## 页面与下游

- 前端只消费 direct canonical API 在同一只读 snapshot 返回的 `paired.groups` 与 `unpaired.groups`，不得本地拼关系或按旧 `case_id` 合并未配对事实。后续分页使用与查询条件绑定的 opaque cursor；cursor 只表达读取位置，不是写 CAS 或 read-model version。
- 页面只保留紧凑三栏，已配对与未配对始终同时可见，不提供经典布局或区域放大。每个区域标题栏最右侧提供独立的银行流水“全部 + 年月”筛选，紧邻只包含 OA、银行流水、进销项发票的栏显示菜单；栏显示至少保留一栏。时间筛选只使用既有银行交易日期服务端筛选合同，不改变关系成员、分区、选择或 mutation。
- 三个复合表头菜单按现有列承载相关事实：银行“金额”菜单依次提供收支方向、银行账户和流水标签；OA“申请人”菜单依次提供 OA 类型、流程状态和申请人，其中“支付申请 / 日常报销”和“已完成 / 进行中”四项在每个区域固定可选，不因当前区域恰好没有对应行而消失；OA“项目名称”菜单依次提供 OA 费用类型和项目名称。同一子组多选按 OR，不同子组按 AND；银行条件必须由同一条流水满足，项目与费用类型必须由同一条 OA 费用明细满足。银行账户展示只使用设置中的银行账户映射与账号后四位，流水标签复用银行明细 canonical 分类结果，不在关联台复制分类逻辑。
- 项目筛选菜单允许项目名换行并按内容高度展开，长项目名不得与相邻选项重叠；筛选选项仍由服务端完整候选域提供，不从当前已加载页面推导。
- 日常报销仍以外层 OA 作为唯一 canonical relation member。其付款明细只作为该 OA 的嵌套展示事实，不得独立选择、配对或撤回；点击任一付款明细等价于选择父 OA。
- 多付款明细日常报销在 OA 栏显示为一个复合行：申请人栏显示申请人、申请类型和日期；项目名称栏先显示“多个项目 · N”及父 OA 金额，再逐项显示真实项目名称；金额栏只显示逐项金额。不得显示按项目聚合金额，不得增加“付款明细”列，也不得在项目名称栏显示关系或附件解析状态 chip。
- ETC `collapsed_summary` 在折叠态只显示服务端提供的 canonical 汇总行和真实发票总数，不显示任何真实发票成员；用户显式展开后只显示完整真实发票成员，收起恢复同一汇总行。汇总行缺失时显示明确空态，禁止拿首张发票、`rows[0]` 或详情子集兜底；搜索命中隐藏成员只保留该组，不自动展开或预取明细。
- 两区发票栏标题显示 canonical 发票数，不显示 ETC summary 等展示对象数；展开/收起批次只改变展示行，不改变统计。区域搜索/筛选时该数字按命中的关系组所拥有的 canonical ID 去重计算，无筛选时两区数字必须满足统一发票池全量守恒式。
- 单一日常报销父 OA 展开后，父 OA 级银行流水作为整单证据占满摘要与全部付款项高度；只有带明确费用子项 ownership 的发票进入对应付款项同行。该展示不改变正式 relation membership、选择身份或撤回边界。
- OA 附件发票通过显式 `source_expense_item_ids[]` 与付款明细对齐；同一付款项的多张发票、同一发票的多个付款项以及更一般的多对多来源必须按“付款项—发票”连通分量进入同一展示带，每张发票只渲染一次。金额仅用于异常判断，不得把已明确归属但金额有差异的发票拆到残余行。没有任何明确付款项来源的 OA 发票进入独立“待归属”残余带，不得进入父 OA 的“日常报销汇总明细”行。项目名、顺序或 subset-sum 一律不得用来推断 ownership。该视觉同行不创建或修改正式关系。每个付款项的“申请事由”继续显示来源“费用内容”和“费用说明”。
- 发票来源与发票归属是两个独立合同。`source_kinds[]` 保留同一 canonical 发票的全部来源证据，`source_kind` 继续作为单值结构兼容字段，不能覆盖复数来源；页面只显示一个主来源 Chip：存在 `oa_attachment_invoice` 时显示“OA附件”，否则存在 `manual_invoice_import` 时显示“人工导入”，不再显示“导入记录”。`oa_expense_item_invoice` 仍作为独立的“明细归属”Chip。只有 `source_expense_item_ids[]` 决定发票与 OA 子付款项同行；OA 附件来源必须能通过当前 OA 显式身份、owned item/attachment parent identity 或 active OA source alias 精确恢复到当前子付款项，否则保持待归属异常，禁止按金额或顺序猜测。OA 附件来源和显式明细归属必须在后续 Excel 导入中保留；未知来源不得默认伪装为“人工导入”。
- 已配对区和未配对区的 active 正式关系都可以按关系组撤回；请求成员必须精确等于当前完整 active relation，未配对 singleton 不能撤回。未配对区选择至少 2 个不同 canonical 成员即可发起人工正式配对；旧“撤回候选”概念和入口不存在。
- 未配对工具栏只保留关系确认/撤回等关系动作。系统统一计算金额和 OA 附件异常；右上入口固定为 `未配对异常 n | 已配对异常 m`。
- 关系 provenance、规则版本、证据摘要、actor 和时间只用于审计，不拆分用户可见关系状态。
- `workbench_relation` 下游只输出 `linked` / `unlinked`。只有 active 正式关系能驱动已支付、已关联、成本、待找发票、OA 待付款或银行关系标签。
- direct query 超时或依赖不可用时不得返回部分数据或伪装空结果；页面必须显示明确的读取错误。写入口继续独立服从 session/permission、系统 mutation block、OA sync 安全状态和 canonical preview/CAS，不依赖页面 generation/freshness。

## OA 与发票异常

- 日常报销以“子付款项—发票”二部图的连通分量为比较单元：分量内所有子付款项金额之和与去重后的所有发票价税合计按分精确比较。`290=145+145`、`405=350+55`、`18+18=36` 均为正常；一对一、一对多、多对一、多对多使用同一规则，不做 subset-sum 或顺序推断。支付申请没有子付款项时，才按关系组 OA 总金额与发票总金额比较。
- 关系只在 OA、流水、发票三栏金额与方向都可比较时自动归为七种互斥结果：`OA 流水一致，票多`、`OA 流水一致，票少`、`OA 发票一致，付多`、`OA 发票一致，付少`、`发票流水一致，OA 提少了`、`发票流水一致，OA 提多了`、`三项不一致`。金额缺失、任一方向未知、方向冲突或三栏总额完全一致时不得猜测金额异常；日常报销子付款项的局部 OA—发票差异只用于把已成立的七分类定位到可证明的明细，不额外创建第八种金额 Chip。
- 普通付款关系的银行比较金额是支出减退款收入；但已由外部往来款管理确认且 `relation_mode=turnover_manual_closure`、同一关系收支等额闭环时，OA 只与付款本金侧比较。不能把同额归还收入再次抵减为零后误报 `OA流水金额不一致`，也不能仅凭备注、标签文本或金额形态把普通关系当作外部往来闭环。
- 日常报销子付款项的附件状态只有三种用户口径：只有“附件数为零且没有通过 canonical `oa_expense_item_invoice` 来源边精确绑定正式发票”时才显示“发票附件缺失”（`oa_invoice_attachment_absent`，无额外处理）；有附件但没有解析出可用正式发票显示“发票附件未解析”（`oa_invoice_attachment_unparsed`，保留“录入发票”）；active relation 内存在 OA 费用明细时，每张没有任何有效费用明细来源边的 relation invoice 各显示一次行级“发票待归属”（`oa_invoice_attachment_unassigned`，走已有发票归属），不得按 OA 明细数重复生成，也不得把没有 OA 费用明细的普通关系误判为待归属。APP 内手工录入或选择并精确关联到该子付款项的正式发票满足发票来源证明，但不改写 OA 原始 `attachment_file_count`。
- “录入发票”只打开一个右侧抽屉，默认直接显示复用发票导入页的多张发票编辑器；编辑器同时支持 `JPG/PNG/PDF` 上传识别和人工校正。提交只以发票强身份创建新 canonical invoice，或把已存在的唯一 canonical invoice 显式关联到当前 OA 子付款项；疑似重复、多个候选或身份不足必须整批拒绝，禁止按金额猜测。`补充凭证` 是次级模式，仅保存当前 OA 子付款项的报销证明材料，可预览/删除且不进入统一发票池、不参与配对。发票确认、`oa_expense_item_invoice` 来源边和正式关系扩展必须在同一事务成败；显式来源边是当前展示归属，旧附件来源继续保留为审计证据。禁止抽屉套抽屉、第二发票池和先入池后关系失败的半成品。
- 补充凭证的统一只读查看入口位于发票导入页。资源 owner 仍是关联台；全局列表只返回 active 元数据，按 `(created_at,id)` 倒序游标分页，每页最多九条，并按需返回图片或 PDF 首页缩略图。原文件格式不转换，完整预览继续走鉴权 content API；列表入口不开放 mutation，也不复制表、文件对象、service 或 repository。
- “发票待归属”的感叹号 Popover 只提供“选择 OA 明细”：先关闭当前异常抽屉，再打开一个独立右侧抽屉，默认不勾选任何候选，并列出同一 active relation 内全部可用 OA 费用明细；用户可以显式选择一项或多项。提交必须携带当前 relation case、发票 identity、精确 `(oa_row_id, expense_item_id)` targets、该行待归属 anomaly fingerprint 和幂等键；服务端在同一 UoW 内锁定并重验关系成员、OA 明细、既有来源边、fingerprint 与 source-links CAS。金额相等、项目顺序或名称都不能产生默认选择或自动归属；既有不同或不完整的显式归属必须冲突且不得被覆盖。成功只追加显式 `oa_expense_item_invoice` 来源边并保留全部旧来源审计证据，不修改关系成员或金额；页面不本地挪行，只执行一次 canonical Workbench 回读。回读后该发票与所选 OA 明细按显式 ownership 同行，行级“发票待归属”消失；其它仍成立的金额或资料异常继续保留，并按当前服务端事实决定关系所在分区。
- 页面不直接平铺异常 tag；只显示一个可聚合多项异常的圆形感叹号，hover、键盘 focus 或点击后通过 HeroUI Popover 展示具体异常 Chip、三栏金额、审阅审计，以及人工确认关系时因异常门禁填写的非空备注。异常能由 canonical 来源唯一证明属于某条 OA、流水、发票或 OA 子付款项时，感叹号落在对应明细；无法精确定位或目标明细当前不可见时，感叹号落在既有三栏关联组边界右上角。不得新增关系汇总栏、第四栏、流水金额旁三角形或把组级异常复制到任意明细。
- 主表与异常抽屉展开态必须复用同一 `RelationGroupGrid` 定位逻辑；抽屉折叠态仅在既有三栏摘要的展开箭头前显示同一感叹号。所有异常 Chip 只存在于 Popover，抽屉不得重复平铺 Chip、逐项复选框或人工金额判断下拉菜单。
- 异常抽屉在“未配对异常 / 已配对异常”分区内再提供“金额异常 / 仅资料异常”两个互斥视图。金额异常视图按上述七种金额分类显示唯一关系数，默认选中固定顺序中的首个非零分类；仅资料异常只包含“没有金额异常、但至少存在一种附件异常”的关系。一个关系同时存在金额与资料异常时只归入其唯一金额分类，资料异常继续作为该关系的附属 Chip 展示，不得再次出现在“仅资料异常”或其它金额分类中；每个数量都按唯一关系计数，而不是按异常 item 数计数。
- 七分类是服务端事实筛选，不是付款、退款、补票或 OA 草稿的自动执行指令。当前抽屉继续只负责异常审阅与分区；“发票附件未解析”可复用既有“录入发票”闭环，“发票附件缺失”不新增复杂处置。不得因为分类名称自动创建 OA、付款或退款。
- 任一异常默认阻断关系进入已配对区，并进入抽屉“未配对异常”。分类与当前证据指纹完全由服务器计算；用户只选择“接受异常并进入已配对”或“留在未配对”，不得提交或覆盖分类、证据项或 actor。
- “接受异常并进入已配对”只在 relation 其余完整性条件满足时成功；感叹号和原异常 Chip 保留并进入“已配对异常”，Popover 另行显示审阅人、时间和说明，不给 Chip 添加伪状态前缀。“撤回到未配对”写入留在未配对决定，并让主表完整关系同步回到未配对区。两种动作均不修改正式关系、成员、canonical 金额或附件事实。
- 决定绑定 relation、完整 typed 成员集合、金额/附件状态和 anomaly fingerprint。任一输入变化后旧决定自动失效；写入时 topology 或 fingerprint 已变化返回冲突。read-export 可查看但没有写按钮。

## 固定验收样例

- 云南立孚科技 520 元：发票 `inv_imported_0369`（发票号 `26532000000716859331`）与 OA `oa-pay-2169` 必须存在于 canonical facts；历史 case `case:decision:2026-05:oa_invoice_exact_amount:oa-pay-2169:inv_imported_0369` 只作为 identity 保留。缺银行流水时 active case 必须完整保留但显示在 `unpaired`；补齐银行并满足冻结要求后才进入 `paired`。
- 13 张合计 1709.49 元的省略发票样例在没有唯一强证据闭合时必须是 13 个 `unpaired` 单行，不能因合计金额形成伪关系，也不能被隐藏。
