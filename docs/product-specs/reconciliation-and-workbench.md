# 关联台与正式关系产品口径

更新日期：2026-08-11

## 用户可见状态

关联台只存在两种关系状态：

1. `paired`：对象属于一条 `app.workbench_pair_relations.status='active'` 的正式关系，该关系在创建时冻结的 OA/发票要求已经满足，且关系内全部 OA 的流程状态均为 `completed`；同一关系的全部成员显示在同一组。
2. `unpaired`：不属于 active relation 的 canonical fact 独立显示；尚未满足材料完整性要求或仍包含 `in_progress` OA 的 active relation 保持同一 case 分组。材料缺失明确显示缺少的 OA、银行流水或发票，流程阻断返回 `blocking_reasons=['oa_in_progress']`。

不存在第三种“自动候选”“待确认配对”“假配对”或“隐藏但仍存在”的用户关系状态。系统未能安全正式化的计算结果不持久化、不合并行、不隐藏事实，也不进入下游已关联口径。

## 完整性不变量

- 设统一事实源中可见 canonical facts 为 `C`，要求已满足的 active relation members 为 `R_complete`，要求未满足的 active relation members 为 `R_incomplete`，则 `paired = R_complete`、`unpaired = R_incomplete ∪ (C - active relation members)`。
- `paired` 与 `unpaired` 不相交，二者并集必须精确等于 `C`；任何事实不得遗漏、重复显示或同时属于两个 active case。
- 历史 `case_id`、row 上残留的 `case_id`、来源标签和旧 case 前缀都不能决定分组。含银行流水的普通关系只读取关系创建时冻结的 `requires_oa` / `requires_invoice`；缺失快照 fail closed，不得在读路径回查当前规则或按旧 case 前缀放行。
- 普通 OA 付款关系必须包含银行流水才算完整；OA 与附件发票的 immutable binding 只表达不可拆分 ownership，缺银行时整组保留 active case 但位于 `unpaired`。显式 batch-accounting 与 ETC batch relation 继续按登记豁免处理。
- 进行中 OA 可以与银行流水和发票写入同一正式关系，也可以扩展唯一已存在的银行-发票 active case；不得为进行中 OA 建立第二套 pending relation 或隐藏银行流水。关系满足全部材料要求后仍停留在 `unpaired`，直到所有 OA 完成；OA sync 将同一 OA 迁入 completed projection 后，原 case 不变并在下一次 Workbench refresh 进入 `paired`。多 OA 关系中任一 OA 进行中即阻断整组。
- `app.oa_pending_payment_admissions` 是进行中 OA 的唯一 canonical 读取源；`app.workbench_pair_relations` 是 completed/in-progress 共用的唯一 active relation owner。历史 `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims` 及事件只读审计，不参与运行时分组、占用、source proof 或 promotion。
- 一条 active relation 可以是任意非空的 OA/银行流水/发票成员组合，包括一对一、一对多、多对一以及 `N:M:K`。关系来源不形成用户可见的业务状态区分。

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

- 前端只消费 active generation 发布的 `paired.groups` 与 `unpaired.groups`，不得本地拼关系或按旧 `case_id` 合并未配对事实。
- 页面只保留紧凑三栏，已配对与未配对始终同时可见，不提供经典布局或区域放大。每个区域标题栏最右侧提供独立的银行流水“全部 + 年月”筛选，紧邻只包含 OA、银行流水、进销项发票的栏显示菜单；栏显示至少保留一栏。时间筛选只使用既有银行交易日期服务端筛选合同，不改变关系成员、分区、选择或 mutation。
- 日常报销仍以外层 OA 作为唯一 canonical relation member。其付款明细只作为该 OA 的嵌套展示事实，不得独立选择、配对或撤回；点击任一付款明细等价于选择父 OA。
- 多付款明细日常报销在 OA 栏显示为一个复合行：申请人栏显示申请人、申请类型和日期；项目名称栏先显示“多个项目 · N”及父 OA 金额，再逐项显示真实项目名称；金额栏只显示逐项金额。不得显示按项目聚合金额，不得增加“付款明细”列，也不得在项目名称栏显示关系或附件解析状态 chip。
- 单一日常报销父 OA 展开后，父 OA 级银行流水作为整单证据占满摘要与全部付款项高度；只有带明确费用子项 ownership 的发票进入对应付款项同行。该展示不改变正式 relation membership、选择身份或撤回边界。
- OA 附件发票优先通过显式 `source_expense_item_id` 与付款明细对齐；同一付款项下所有显式绑定该 item 的发票始终进入该 item 的同一展示带，一对一、一对多、多对一和多对多关系均不再用金额相等决定 ownership。金额仅用于异常判断，不得把已明确归属但金额有差异的发票拆到残余行。缺少显式来源时，只允许在同一完整关联组、方向已知且金额双方唯一时做纯视觉单条精确金额兜底；父 OA 级重复来源、重复金额、无显式费用子项归属的金额组合、项目名或顺序推断一律保留在残余展示带。该视觉同行不创建或修改正式关系。每个付款项的“申请事由”继续显示来源“费用内容”和“费用说明”。
- 已配对区可以撤回正式关系；未配对区可以选择多行发起人工正式配对，但没有“撤回候选”动作。
- 关系 provenance、规则版本、证据摘要、actor 和时间只用于审计，不拆分用户可见关系状态。
- `workbench_relation` 下游只输出 `linked` / `unlinked`。只有 active 正式关系能驱动已支付、已关联、成本、待找发票、OA 待付款或银行关系标签。
- stale/refreshing/failed read model 不得伪装 fresh；页面必须显示诊断并按写安全合同禁用相关写入口。

## OA 与发票异常

- 日常报销以 OA 子付款项为比较单元：该 item 金额与所有显式绑定到同一 `source_expense_item_id` 的发票价税合计按分精确比较。`290=145+145`、`405=350+55` 均为正常；一对一、一对多、多对一、多对多使用同一规则，不做 subset-sum 或顺序推断。支付申请没有子付款项时，才按关系组 OA 总金额与发票总金额比较。
- 两侧金额完整且不相等时产生 `oa_invoice_amount_mismatch`，不设置容差，也不判断“真异常/假异常”。一个比较单元只显示一个 `金额不一致` chip，不把同一异常复制到每张发票；任一参与比较的金额缺失时不误报。
- 日常报销子付款项声明已上传附件，但该 item 没有任何已解析且显式绑定的发票时，产生 `oa_invoice_attachment_missing`。发票栏在对应 item 行只显示一个不可选择、不可写入 canonical 数据的 `OA发票附件缺失` 占位 chip，不再显示历史 `未识别附件` 来源标签；它只属于展示和异常处理，不是发票事实。
- active 异常持续进入统一“异常处理”右侧抽屉的“进行中的异常”。入口固定显示 `异常 n | 已忽略 m`；抽屉默认按关系组折叠为一行，只显示 OA、银行流水和发票各自的成员数与总金额，展开后才显示完整三栏，同一时间最多展开一组。
- full-access/admin 可以按关系组忽略 active 异常；忽略不修改正式关系、canonical 金额或附件事实，chip 改为 `已忽略：金额不一致` 或 `已忽略：OA发票附件缺失`，并进入“已忽略的异常”。用户可通过“撤回忽略”恢复；read-export 只可查看，不显示写按钮。
- 忽略决定绑定 relation、比较单元、成员集合、金额/附件状态和当前 active generation。任一输入变化导致 fingerprint 变化时旧决定不再命中；写入时 generation 或 fingerprint 已变化必须返回冲突。

## 固定验收样例

- 云南立孚科技 520 元：发票 `inv_imported_0369`（发票号 `26532000000716859331`）与 OA `oa-pay-2169` 必须存在于 canonical facts；历史 case `case:decision:2026-05:oa_invoice_exact_amount:oa-pay-2169:inv_imported_0369` 只作为 identity 保留。缺银行流水时 active case 必须完整保留但显示在 `unpaired`；补齐银行并满足冻结要求后才进入 `paired`。
- 13 张合计 1709.49 元的省略发票样例在没有唯一强证据闭合时必须是 13 个 `unpaired` 单行，不能因合计金额形成伪关系，也不能被隐藏。
