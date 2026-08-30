# 关联台模块维护入口

- Module key：`reconciliation-workbench`
- 类型：页面模块
- Route：`/`
- Page key：`reconciliation-workbench`

## 修改前必读

- `docs/product-specs/reconciliation-and-workbench.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/operations/runtime-worker-governance.md`

## 当前业务边界

关联台是 canonical OA、银行流水和发票事实与 active 正式关系的读写工作台。页面只有 `paired` 和 `unpaired` 两个关系区：满足冻结 OA/发票要求的 active relation 进入 `paired`；未满足要求的 active relation 保持同 case 分组进入 `unpaired` 并显示缺失类型；无 active owner 的 canonical facts 各自作为单行进入 `unpaired`。人工确认允许至少 2 个不同 canonical 成员，不以跨栏、金额相等或材料完整为创建门槛；只有既有 `amount_check.requires_note=true` 时才要求 `note`，创建后仍按页面完成合同分区。银行分类不选择人工写入链：选择中的银行成员部分或全部为 `internal_transfer` 时，`confirm-link` 仍以 `manual_confirmed` 进入标准 relation command/UoW，不得转交 no-OA batch；独立 no-OA batch 功能及其业务入口保持不变。唯一窄例外是 OA 与完整 canonical 外部往来收支闭环同时确认：关联台复用既有 Turnover 校验器写 `turnover_manual_closure`，金额按 OA 同方向本金侧比较；结构化语义不完整时明确失败，不做文本或金额形态兜底。

页面不拥有自动候选、matching decision 或第三种关系状态。确定性引擎满足安全规则时直接通过正式关系命令边界创建 active relation；不满足时不写关系，事实仍保持可见的未配对单行。

已配对区和未配对区三栏的表头下拉不再从浏览器已加载页推导。菜单打开后通过 direct canonical `/api/workbench/filter-options` 读取完整候选域；主表按 10 组的 opaque keyset cursor 分页并在接近底部时自动续读，候选菜单独立按 100 项 keyset 分页并支持搜索。目标列自己的筛选条件不限制其候选，其余区域搜索、列筛选和时间筛选保持生效。

银行“金额”是收支方向、银行账户、流水标签的分组复合菜单；OA“申请人”是 OA 类型、流程状态、申请人的分组复合菜单；OA“项目名称”是 OA 费用类型、项目名称的分组复合菜单。同组多值 OR、跨组 AND，且条件必须由同一 canonical member（项目/费用类型为同一费用明细）满足。项目菜单使用加宽、可换行且随内容增高的选项，不允许恢复固定行高造成的文字重叠。

OA 附件状态固定为“发票附件缺失 / 发票附件未解析 / 发票待归属”。只有“未解析”显示“录入发票”，打开单一右侧抽屉并默认复用多张发票编辑器的上传识别/人工校正；补充凭证是次级模式且不进入发票池。active relation 含 OA 费用明细时，每张缺少有效费用明细来源边的 relation invoice 各生成一次行级“发票待归属”，默认让完整关系留在 `unpaired`；没有 OA 费用明细的关系不生成该异常。`batch_accounting` 且正式发票成员为 canonical `etc_invoice_summary` 的 ETC 批次不属于 OA 附件归属流程，不生成上述三类资料异常，但仍执行三栏金额检查。“发票待归属”通过感叹号内的“选择 OA 明细”打开独立抽屉，默认零选择并允许用户显式选择同关系内一项或多项，禁止按金额、名称或顺序推荐。显式 `oa_expense_item_invoice` 是有效展示归属，旧附件来源只保留审计。金额异常只在唯一来源证明具体单票时落该发票，否则落 OA 子项或 OA/流水组级位置。

补充凭证资源同时向发票导入页提供全局只读 gallery：每页最多九条 active 元数据，按上传时间和 ID 倒序游标分页；图片和 PDF 首页缩略图按需生成，完整内容仍走既有鉴权 content API。统一入口不改变本模块按 OA 子付款项上传、列表和软删除的上下文边界。

无 OA、全部为收入流水和销项发票、币种为人民币、付款方唯一且必要字段完整的 active relation，无论当前位于 `paired` 还是 `unpaired`，都在 OA 栏显示唯一的“编辑并打印收据”动作；无 active relation 的 singleton 不显示。一个 relation 固定生成一张收据，多条收入以全部流水合计为金额、以最新交易日期为默认日期；付款方不一致时不显示动作且 draft fail closed，不按发票购买方或日期猜测拆分。动作先读取当前 canonical 草稿并打开单一右侧编辑抽屉，用户核对付款单位、日期、摘要、金额、备注、主管和经手人后再请求生成一联 A5 横向 PDF。服务端以收入流水金额为固定合计，提交时重验关系版本、来源指纹和明细合计；关系或来源变化、金额不平或红蓝票异常未确认时 fail closed。收据快照不改变 relation、发票、统计或页面分区。

候选菜单使用紧凑的 HeroUI Popover/SearchField/Checkbox 布局并允许长标签自然换行。OA 申请事由直接显示完整文本，不再创建 hover 浮层，避免浮层测量导致表格滚动条抖动。

OA 栏在已配对和未配对区域都只承担行选择与详情查看，不存在逐行“确认关联”“异常处理”或撤回按钮，也不显示操作列。确认从未配对区域表头选择动作进入；已配对和未配对 active relation 的撤回都从关系级选择动作进入，并恢复上一可证明的稳定拓扑。未配对工具栏“异常处理”及其人工 drawer 触发链已删除；自动识别的 OA/发票异常仍只走右上统一异常抽屉。银行流水和发票保留各自独立的行级能力合同。

关系来源（人工、历史或系统）只进入审计 provenance，不参与页面分区。历史 case id 的字符串前缀不能覆盖当前 active relation 状态。

## 运行链

```text
canonical fact repositories
  + app.workbench_pair_relations/history
  -> PostgresWorkbenchPageQueryRepository (RR/RO, scope-first SQL)
  -> WorkbenchQueryFacade
  -> paired / unpaired direct API
  -> ReconciliationWorkbenchPage
```

页面为 direct-only：不读 projection/Redis，不比较 generation/freshness，不投递 page refresh，也不从旧 snapshot、旧 candidate/decision 表或 row metadata 恢复关系。自动匹配仍由 `workbench-matching` 通过 relation UoW 写 active relations；共享 `workbench_relation` read model 只为其它明确消费者服务，不参与 Workbench page read path。

ETC 批次在折叠态只显示 canonical `summaryRow`，不显示任何真实发票成员；“展开全部 N 张发票”通过既有 group detail I/O 一次加载该批次完整 `collapsedRows`，展开态只显示真实成员，收起后恢复 `summaryRow`。首屏只携带汇总行和总数，避免 68 张等大批次放大初始 payload；缺少汇总行时明确显示空态，禁止拿第一张真实发票兜底。ETC 折叠资格只认 submitted/closed 批次；搜索可命中 ETC 批次标识、成员发票号和精确批次金额。两区发票栏标题按 canonical ID 统计：summary 必须通过明确 row id / `etc_invoice_id` 展开到真实 canonical 成员，paired 优先且两区互斥，合计等于统一发票池总数；展示对象数继续只服务分页和布局。

## 代码入口

- 前端：`web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/RelationGroupGrid.tsx`、`RelationGroupCell.tsx`、`WorkbenchExceptionDrawer.tsx`、`WorkbenchInvoiceAssignmentDrawer.tsx`、`WorkbenchReceiptDrawer.tsx`
- API：`web/src/features/workbench/api.ts`、`backend/src/fin_ops_platform/app/routes_workbench.py`、`routes_workbench_actions.py`
- Direct page SQL：`backend/src/fin_ops_platform/services/postgres_repositories/workbench_page_query.py`、`workbench_page_hydration.py`
- 分组：`backend/src/fin_ops_platform/services/workbench_relation_grouping.py`
- 统一异常合同/判断/审阅：`backend/src/fin_ops_platform/services/workbench_anomaly_contract.py`、`workbench_amount_check_service.py`、`workbench_anomaly_review_service.py`
- 匹配：`backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`、`workbench_matching_orchestrator.py`
- Matching I/O：`backend/src/fin_ops_platform/services/postgres_repositories/workbench_formal_relation.py`
- 正式关系与发票明细归属写入：`backend/src/fin_ops_platform/services/workbench_relation_command_service.py`、`workbench_invoice_expense_item_assignment_service.py`、`invoice_expense_item_links.py`、`workbench_uow.py`
- 保留的独立 Worker：`backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_worker.py`、`workbench_relation_read_model_worker.py`

## 关联台异常合同

- 系统只在 OA、流水、发票三栏金额完整且方向明确时自动输出七种互斥金额分类；方向未知、方向冲突、任一栏缺失或三栏总额完全一致时不得猜测。普通付款关系的银行侧使用同一 relation 内支出减退款收入的净额；`turnover_manual_closure` 继续只按 canonical mode 使用付款本金侧。日常报销的 OA—发票按 `source_expense_item_ids[]` 连通分量去重计算，局部差异只用于定位已成立的七分类，不创建第八种金额 Chip。附件状态只区分“发票附件缺失 / 发票附件未解析 / 发票待归属”；后一种按无有效 item edge 的 relation invoice 逐票、逐行生成，不按费用明细重复，也不按金额推断 owner。
- 任何当前异常默认把完整 active relation 留在 `unpaired`。服务端从当前 canonical bundle 推导分类与 evidence fingerprints，客户端只提交 fingerprint 和 `accept_paired|keep_unpaired`，不提交 actor、人工分类或逐项审阅结果。只有无其他完整性 blocker 时 `accept_paired` 才允许进入 `paired`；接受后保留感叹号与原异常 Chip，审阅审计在 Popover 单独展示。“撤回到未配对”写入 `keep_unpaired` 并同步移动主表关系。
- 决定复用既有 exception case repository 的独立 `workbench_anomaly_review` scenario，按 bundle fingerprint 失效。旧人工异常分类器、金额 ignore/restore API、人工分类/复选 UI 和前端请求字段均已删除；历史记录、WEX/row-ignore 仅保留审计。
- 页面只保留统一 `WorkbenchExceptionDrawer`，两个 bucket 固定为“未配对异常 / 已配对异常”，并作为最外层切换放在抽屉标题右侧；每次只读取当前 bucket。入口文案固定为 `未配对异常 n | 已配对异常 m`。审阅动作完成后只让目标关系迁移，抽屉继续停留在用户当前 bucket，不自动跟随关系跳转。
- 每个 bucket 内再提供“金额异常 / 仅资料异常”两个互斥视图。金额视图下才显示七个服务端分类，并按 `OA = 流水`、`OA = 发票`、`流水 = 发票`、`三项互异` 四个父组组织；这四组及其中七项都不属于“仅资料异常”。默认选中首个非零分类；仅资料视图只收纳没有金额分类的附件异常关系。金额与资料并存时关系只进入唯一金额分类，资料 Chip 仍在该关系 Popover 中显示；多个资料 item 不得把同一关系重复计数或重复返回。分类筛选只组织审阅队列，不自动触发付款、退款、补票或 OA 草稿。
- 异常抽屉宽度固定为 `min(1740px, 96vw)`。折叠态只显示 OA、流水、发票三栏金额/数量摘要，并在展开箭头前显示一个感叹号；hover/focus 临时打开 HeroUI Popover，显示时点击感叹号立即关闭且在当前鼠标停留期间禁止自动重开，再次点击改为持续打开，鼠标真正离开后下一次 hover 恢复。展开态直接复用只读 `RelationGroupGrid`，所以感叹号与主表定位和交互完全一致；动作区只保留决定按钮。不得新增关系汇总栏、第四栏、重复 Chip、逐项复选框、人工金额下拉或原生 HTML 表单控件。
- 未配对选择工具栏不提供人工“异常处理”；删除该按钮不删除异常系统、主表异常 chip、右上统计入口、统一异常抽屉或自动异常计算。
- “发票待归属”只允许在异常 Popover 中发起显式归属；提交重验 active case、invoice/OA 成员、费用明细、行级 anomaly fingerprint、幂等和 source-links CAS。既有不同或不完整的显式归属 fail closed，不允许静默覆盖。写成功后页面恰好一次 canonical 回读，不能本地删除异常、移动分区或拼装同行；关系成员与金额保持不变。

## 三栏纵向展示合同

- 页面只使用紧凑三栏：已配对/未配对各自只渲染一套 `WorkbenchZone`，标题、区域搜索、选择汇总与区域动作保持同一工具栏；银行流水的“全部 + 年月”筛选固定在区域标题栏最右侧、栏显示菜单之前，已配对与未配对分别保存筛选状态。栏显示菜单只允许切换 OA、银行流水、进销项发票，至少保留一栏。经典布局、紧凑/经典切换、区域放大/恢复及对应状态和样式已删除，不得恢复并行布局路径。紧凑三栏隐藏横向滚动与还借款日期列，长文本在单元格内直接换行显示，不创建行单元格 hover Popover；银行流水和发票的合法行级动作收进 `···`，OA 仍无行级操作列。
- OA、银行流水、发票栏默认各自跨越完整关联组高度；同栏有 `N` 条可见记录时由 CSS Flex 等分可用高度，单条记录占满整栏。
- 单一日常报销父 OA 展开为多个付款项时，只有父 OA 归属、没有费用子项归属的银行流水继续作为整单证据跨越摘要与全部付款项高度，不得被压进父 OA 摘要行。
- 单条银行流水/非 OA 来源发票与 OA 或费用子项金额按分精确相等且双方唯一时共享行轨，不再要求整栏完整覆盖。普通父 OA 下有两条或以上银行流水时，只有所有流水都带 canonical `sourceOaId`、当前显示包含完整组成且流水按分合计等于该 OA，才共享一个复合行轨；OA 只渲染一次，流水在轨内等分。显式 `sourceOaId` / `sourceExpenseItemIds[]` 优先；API 映射必须优先 canonical `source_oa_id` / `source_oa_row_id`，历史 `derived_from_oa_id` 只作兜底，不能覆盖 canonical ownership。OA 附件发票的同行只消费顶层 canonical `source_expense_item_ids[]`，原始 `source_links[]` 只作审计证据；OA 附件缺少 canonical 子付款项来源时进入独立待归属残余带，禁止按金额兜底。显式费用子项 ownership 不以金额相等为前提。其他来源缺少显式 ownership 时，只允许在同一完整 source group、方向已知且金额双方都唯一时做展示级精确金额兜底。
- 同一费用子项下的所有显式绑定附件发票共享一个复合行轨；费用子项占满该轨高度，发票在轨内等分。即使合计金额不等，也保持同行并由异常 chip 表达差异。筛选后缺少任一组成发票时不建立部分复合同行。
- 缺少 canonical ownership、合计不等、显示组成不完整的父 OA 级一对多，以及多对一、重复来源、重复金额、零/非法金额、方向未知或冲突，都不建立同行；无显式来源的 2～6 条金额即使合计相等也不做组合推断。已分段栏中的这些记录进入独立残余展示带，完全没有精确配对的栏继续按 group-level 占满整组高度。金额兜底不写 relation、不改变 membership、selection 或 action identity。
- 多项目报销继续显示父 OA 摘要和费用子项；显式来源形成的付款项/发票连通分量同行，每张发票只渲染一次，未归属 relation invoice 留在独立残余展示带且不得进入父摘要。待归属发票在自身行只显示一个原因明确的感叹号，Popover 提供“选择 OA 明细”，不得同时显示“录入发票”；归属成功并完成 canonical 回读后，发票进入所选 OA 明细的同行带且待归属感叹号消失。缺失附件发票的展示位仍只显示一个原因明确的感叹号，不得叠加历史 `未识别附件` 来源标签或直接平铺 Chip；空发票栏中的“感叹号 + 录入发票”只属于“发票附件未解析”，使用一个跨整栏的 HeroUI 状态操作区，不渲染或保留占位横杠。按钮权限不足时保持禁用并解释原因。发票比较金额统一使用价税合计，银行流水使用当前方向金额。
- 布局判断只消费已加载 DTO，是 `O(OA + bank + invoice)` 的 Map/Set 纯计算，不增加 HTTP、数据库、cache、worker、React state/effect、DOM 测量或依赖。

## 不变量

- `paired = complete active relation members`。
- `unpaired = incomplete active relation members + unowned canonical facts`。
- 两区不相交且完整覆盖 canonical facts。
- 无 active owner 的未配对事实永远是 singleton；未闭环 active relation 只能按其 canonical case 分组，旧 `case_id` 和候选 metadata 不能合并无 owner 事实。
- 一个 canonical member 最多属于一个 active relation。
- 未知 zone、group type、relation mode、重复 identity、缺失 active member 或跨 case 占用冲突均 fail fast。
- 人工确认至少包含 2 个不同 canonical identity；金额/方向差异只触发既有备注门禁，不阻止创建。自动匹配的 exact-sum、强证据与唯一性门禁不随之放宽。

## 维护文档

- `boundary-io.md`：模块边界、I/O、依赖方向、迁移与删除条件。
- `state-machine.md`：页面 direct query 与正式关系状态。
- `tests.md`：七类测试、命令和生产核验。
- `implementation-notes.md`：历史实施记录，不是当前业务事实源。
