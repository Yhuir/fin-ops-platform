# 关联台与正式关系产品口径

更新日期：2026-08-13

## 用户可见状态

关联台只存在两种关系状态：

1. `paired`：对象属于一条 `app.workbench_pair_relations.status='active'` 的正式关系，该关系当前持久化的 OA/发票要求已经满足，且关系内全部 OA 的流程状态均为 `completed`；同一关系的全部成员显示在同一组。
2. `unpaired`：不属于 active relation 的 canonical fact 独立显示；尚未满足材料完整性要求或仍包含 `in_progress` OA 的 active relation 保持同一 case 分组。材料缺失明确显示缺少的 OA、银行流水或发票，流程阻断返回 `blocking_reasons=['oa_in_progress']`。

不存在第三种“自动候选”“待确认配对”“假配对”或“隐藏但仍存在”的用户关系状态。系统未能安全正式化的计算结果不持久化、不合并行、不隐藏事实，也不进入下游已关联口径。

## 完整性不变量

- 设统一事实源中可见 canonical facts 为 `C`，要求已满足的 active relation members 为 `R_complete`，要求未满足的 active relation members 为 `R_incomplete`，则 `paired = R_complete`、`unpaired = R_incomplete ∪ (C - active relation members)`。
- `paired` 与 `unpaired` 不相交，二者并集必须精确等于 `C`；任何事实不得遗漏、重复显示或同时属于两个 active case。
- 历史 `case_id`、row 上残留的 `case_id`、来源标签和旧 case 前缀都不能决定分组。含银行流水的普通关系只读取 canonical relation 当前持久化的 `requires_oa` / `requires_invoice`；缺失证明 fail closed，不得在读路径临时回查当前规则或按旧 case 前缀放行。规则保存后的增量任务必须先通过正式 relation command 更新 metadata/history，再刷新精确 Workbench 月份。
- 普通 OA 付款关系必须包含银行流水才算完整；OA 与附件发票的 immutable binding 只表达不可拆分 ownership，缺银行时整组保留 active case 但位于 `unpaired`。显式 batch-accounting 与 ETC batch relation 继续按登记豁免处理。
- 进行中 OA 可以与银行流水和发票写入同一正式关系，也可以扩展唯一已存在的银行-发票 active case；不得为进行中 OA 建立第二套 pending relation 或隐藏银行流水。关系满足全部材料要求后仍停留在 `unpaired`，直到所有 OA 完成；OA sync 将同一 OA 迁入 completed canonical projection 后，原 case 不变并在下一次 Workbench normal GET 进入 `paired`。多 OA 关系中任一 OA 进行中即阻断整组。
- `app.oa_pending_payment_admissions` 是进行中 OA 的唯一 canonical 读取源；`app.workbench_pair_relations` 是 completed/in-progress 共用的唯一 active relation owner。历史 `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims` 及事件只读审计，不参与运行时分组、占用、source proof 或 promotion。
- 一条 active relation 可以是任意非空的 OA/银行流水/发票成员组合，包括一对一、一对多、多对一以及 `N:M:K`。关系来源不形成用户可见的业务状态区分。

## 人工正式关系

- 人工确认只要求至少选择 2 个不同的 canonical 成员；每个请求 ID 必须精确解析为 `oa|bank|invoice` canonical row，同栏、跨栏、一对多、多对一和多对多组合均可提交。重复 identity、缺失或已失效成员、未知类型、active owner 冲突、版本冲突和非法 synthetic summary 仍须 fail closed。
- 金额相等、方向已知和材料完整性不再是人工创建 active relation 的门槛。金额不一致或方向不确定时，预览继续通过既有 `amount_check.requires_note` 要求填写 `note`；说明随正式关系与审计历史保存，不新增字段。创建后的关系仍按持久化完成要求与 OA 流程状态决定进入 `paired` 或保持在 `unpaired`，不能因人工确认伪装完整。
- 银行分类不选择人工关系的 mutation owner。选择中部分或全部银行成员为 `internal_transfer` 时，`confirm-link` 仍以 `manual_confirmed` 进入标准 relation command/UoW；不得返回 no-OA batch 专属冲突或转交该批次入口。独立 no-OA batch 功能、其专属入口和登记 relation mode 保持不变。
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
- 单一日常报销父 OA 展开后，父 OA 级银行流水作为整单证据占满摘要与全部付款项高度；只有带明确费用子项 ownership 的发票进入对应付款项同行。该展示不改变正式 relation membership、选择身份或撤回边界。
- OA 附件发票通过显式 `source_expense_item_ids[]` 与付款明细对齐；同一付款项的多张发票、同一发票的多个付款项以及更一般的多对多来源必须按“付款项—发票”连通分量进入同一展示带，每张发票只渲染一次。金额仅用于异常判断，不得把已明确归属但金额有差异的发票拆到残余行。没有任何明确付款项来源的 OA 发票进入独立“待归属”残余带，不得进入父 OA 的“日常报销汇总明细”行。项目名、顺序或 subset-sum 一律不得用来推断 ownership。该视觉同行不创建或修改正式关系。每个付款项的“申请事由”继续显示来源“费用内容”和“费用说明”。
- 已配对区和未配对区的 active 正式关系都可以按关系组撤回；请求成员必须精确等于当前完整 active relation，未配对 singleton 不能撤回。未配对区选择至少 2 个不同 canonical 成员即可发起人工正式配对；旧“撤回候选”概念和入口不存在。
- 未配对工具栏只保留关系确认/撤回等关系动作。系统统一计算金额和 OA 附件异常；右上入口固定为 `未配对异常 n | 已配对异常 m`。
- 关系 provenance、规则版本、证据摘要、actor 和时间只用于审计，不拆分用户可见关系状态。
- `workbench_relation` 下游只输出 `linked` / `unlinked`。只有 active 正式关系能驱动已支付、已关联、成本、待找发票、OA 待付款或银行关系标签。
- direct query 超时或依赖不可用时不得返回部分数据或伪装空结果；页面必须显示明确的读取错误。写入口继续独立服从 session/permission、系统 mutation block、OA sync 安全状态和 canonical preview/CAS，不依赖页面 generation/freshness。

## OA 与发票异常

- 日常报销以“子付款项—发票”二部图的连通分量为比较单元：分量内所有子付款项金额之和与去重后的所有发票价税合计按分精确比较。`290=145+145`、`405=350+55`、`18+18=36` 均为正常；一对一、一对多、多对一、多对多使用同一规则，不做 subset-sum 或顺序推断。支付申请没有子付款项时，才按关系组 OA 总金额与发票总金额比较。
- 关系按当前业务方向分别比较 OA—流水、OA—发票、流水—发票，产生具体的 `oa_bank_amount_mismatch`、`oa_invoice_amount_mismatch`、`bank_invoice_amount_mismatch`；chip 分别显示“OA流水金额不一致”“OA发票金额不一致”“流水发票金额不一致”，可同时存在。金额缺失或方向冲突不得猜测。
- 普通付款关系的银行比较金额是支出减退款收入；但已由外部往来款管理确认且 `relation_mode=turnover_manual_closure`、同一关系收支等额闭环时，OA 只与付款本金侧比较。不能把同额归还收入再次抵减为零后误报 `OA流水金额不一致`，也不能仅凭备注、标签文本或金额形态把普通关系当作外部往来闭环。
- 日常报销子付款项的 OA 附件状态只有三种用户口径：附件数为零显示 `无OA附件`（`oa_invoice_attachment_absent`，无操作）；有附件但没有解析出可用正式发票显示 `OA发票附件未解析`（`oa_invoice_attachment_unparsed`，提供“录入发票”）；同一父 OA 已解析出正式发票但缺少子付款项归属显示 `OA发票待归属`（`oa_invoice_attachment_unassigned`，走已有发票归属）。不得再显示或计算旧“OA发票附件缺失/解析失败”状态。
- “录入发票”只打开一个右侧抽屉，内部切换 `JPG/PDF上传` 与 `手工录入`。前者保存为当前 OA 子付款项的补充凭证，可预览/删除且不进入统一发票池；后者复用发票导入页的多张发票编辑器，整批进入统一发票池，并在同一提交边界与当前 OA 子付款项关系配对。禁止抽屉套抽屉、第二发票池和先入池后关系失败的半成品。
- 金额异常只有在 canonical 来源边能唯一证明“具体发票 ↔ 具体 OA 子付款项”时才显示在该发票行；一项多票但无法定位到单票时显示在 OA 子付款项，关系组级或流水—发票总额差异显示在 OA/流水组级位置。禁止把组级 `流水发票金额不一致` 复制到任意一张（例如最后一张 55 元）发票上。
- 任一异常默认阻断关系进入已配对区，并进入抽屉“未配对异常”。用户必须逐项勾选确认已审阅，再选择“进入已配对”或“留在未配对”；分类由服务器客观计算，不允许用下拉菜单把 OA—流水差异改标为另一类型。
- “进入已配对”只在 relation 其余完整性条件满足时成功；异常 chip 保留并进入“已配对异常”，统一显示 `已接受：<原异常>`。该前缀表示用户已审阅并接受风险，不表示异常消失、被忽略或事实已修正；tooltip 保留审阅人、时间和说明。“撤回”写入留在未配对决定，并让主表完整关系同步回到未配对区。两种动作均不修改正式关系、成员、canonical 金额或附件事实。
- 决定绑定 relation、完整 typed 成员集合、金额/附件状态和 anomaly fingerprint。任一输入变化后旧决定自动失效；写入时 topology 或 fingerprint 已变化返回冲突。read-export 可查看但没有写按钮。

## 固定验收样例

- 云南立孚科技 520 元：发票 `inv_imported_0369`（发票号 `26532000000716859331`）与 OA `oa-pay-2169` 必须存在于 canonical facts；历史 case `case:decision:2026-05:oa_invoice_exact_amount:oa-pay-2169:inv_imported_0369` 只作为 identity 保留。缺银行流水时 active case 必须完整保留但显示在 `unpaired`；补齐银行并满足冻结要求后才进入 `paired`。
- 13 张合计 1709.49 元的省略发票样例在没有唯一强证据闭合时必须是 13 个 `unpaired` 单行，不能因合计金额形成伪关系，也不能被隐藏。
