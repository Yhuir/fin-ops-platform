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

关联台是 canonical OA、银行流水和发票事实与 active 正式关系的读写工作台。页面只有 `paired` 和 `unpaired` 两个关系区：满足冻结 OA/发票要求的 active relation 进入 `paired`；未满足要求的 active relation 保持同 case 分组进入 `unpaired` 并显示缺失类型；无 active owner 的 canonical facts 各自作为单行进入 `unpaired`。人工确认允许至少 2 个不同 canonical 成员，不以跨栏、金额相等或材料完整为创建门槛；只有既有 `amount_check.requires_note=true` 时才要求 `note`，创建后仍按页面完成合同分区。银行分类不选择人工写入链：选择中的银行成员部分或全部为 `internal_transfer` 时，`confirm-link` 仍以 `manual_confirmed` 进入标准 relation command/UoW，不得转交 no-OA batch；独立 no-OA batch 功能及其业务入口保持不变。

页面不拥有自动候选、matching decision 或第三种关系状态。确定性引擎满足安全规则时直接通过正式关系命令边界创建 active relation；不满足时不写关系，事实仍保持可见的未配对单行。

已配对区和未配对区三栏的表头下拉不再从浏览器已加载页推导。菜单打开后通过 direct canonical `/api/workbench/filter-options` 读取完整候选域；主表按 10 组的 opaque keyset cursor 分页并在接近底部时自动续读，候选菜单独立按 100 项 keyset 分页并支持搜索。目标列自己的筛选条件不限制其候选，其余区域搜索、列筛选和时间筛选保持生效。

银行“金额”是收支方向、银行账户、流水标签的分组复合菜单；OA“申请人”是 OA 类型、流程状态、申请人的分组复合菜单；OA“项目名称”是 OA 费用类型、项目名称的分组复合菜单。同组多值 OR、跨组 AND，且条件必须由同一 canonical member（项目/费用类型为同一费用明细）满足。项目菜单使用加宽、可换行且随内容增高的选项，不允许恢复固定行高造成的文字重叠。

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

## 代码入口

- 前端：`web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/RelationGroupGrid.tsx`、`RelationGroupCell.tsx`、`WorkbenchExceptionDrawer.tsx`
- API：`web/src/features/workbench/api.ts`、`backend/src/fin_ops_platform/app/routes_workbench.py`
- Direct page SQL：`backend/src/fin_ops_platform/services/postgres_repositories/workbench_page_query.py`、`workbench_page_hydration.py`
- 分组：`backend/src/fin_ops_platform/services/workbench_relation_grouping.py`
- 统一异常判断/审阅：`backend/src/fin_ops_platform/services/workbench_amount_check_service.py`、`workbench_anomaly_review_service.py`
- 匹配：`backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`、`workbench_matching_orchestrator.py`
- Matching I/O：`backend/src/fin_ops_platform/services/postgres_repositories/workbench_formal_relation.py`
- 正式关系写入：`backend/src/fin_ops_platform/services/workbench_relation_command_service.py`、`workbench_uow.py`
- 保留的独立 Worker：`backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_worker.py`、`workbench_relation_read_model_worker.py`

## 关联台异常合同

- 系统按当前方向分别比较 OA—流水、OA—发票、流水—发票；付款关系的银行侧使用同一 relation 内支出减退款收入的净额。日常报销的 OA—发票按归一后的 `source_expense_item_ids[]` 连通分量去重计算；历史附件 ID 只有在 OA parent + row index 唯一时才映射到当前 canonical 子付款项。金额完整且不等时只输出三种具体差异之一或多项；附件异常继续区分缺失、解析失败和待归属。
- 任何当前异常默认把完整 active relation 留在 `unpaired`。金额异常必须先在多选下拉中人工选择三种具体差异或互斥的“无异常”，再选择 `accept_paired` 或 `keep_unpaired`；附件异常继续逐项审阅。只有无其他完整性 blocker 时前者才允许进入 `paired`。决定后的 chip 使用人工分类，“撤回”写入 `keep_unpaired` 并同步把主表关系移回未配对；系统检测证据仍保留用于审计。
- 决定复用既有 exception case repository 的独立 `workbench_anomaly_review` scenario，按 bundle fingerprint 失效。旧金额 ignore/restore API、service 和前端动作已删除；历史记录、WEX/row-ignore 仅保留审计。
- 页面只保留统一 `WorkbenchExceptionDrawer`，两个 bucket 固定为“未配对异常 / 已配对异常”；每次只读取当前 bucket。入口文案固定为 `未配对异常 n | 已配对异常 m`。
- 异常抽屉宽度固定为 `min(1740px, 96vw)`。折叠态只显示 OA、流水、发票三栏金额/数量摘要和异常数量；展开后先复用只读 `RelationGroupGrid` 展示完整三栏证据，再在独立审阅区显示全部 chip、HeroUI 审阅复选框、人工金额判断和决定按钮。窄视口只允许三栏明细区局部横向滚动，抽屉和审阅控件不得溢出视口；不得恢复折叠行右侧的并排操作栏或原生 HTML 表单控件。
- 未配对选择工具栏不提供人工“异常处理”；删除该按钮不删除异常系统、主表异常 chip、右上统计入口、统一异常抽屉或自动异常计算。

## 三栏纵向展示合同

- 页面只使用紧凑三栏：已配对/未配对各自只渲染一套 `WorkbenchZone`，标题、区域搜索、选择汇总与区域动作保持同一工具栏；银行流水的“全部 + 年月”筛选固定在区域标题栏最右侧、栏显示菜单之前，已配对与未配对分别保存筛选状态。栏显示菜单只允许切换 OA、银行流水、进销项发票，至少保留一栏。经典布局、紧凑/经典切换、区域放大/恢复及对应状态和样式已删除，不得恢复并行布局路径。紧凑三栏隐藏横向滚动与还借款日期列，长文本在单元格内直接换行显示，不创建行单元格 hover Popover；银行流水和发票的合法行级动作收进 `···`，OA 仍无行级操作列。
- OA、银行流水、发票栏默认各自跨越完整关联组高度；同栏有 `N` 条可见记录时由 CSS Flex 等分可用高度，单条记录占满整栏。
- 单一日常报销父 OA 展开为多个付款项时，只有父 OA 归属、没有费用子项归属的银行流水继续作为整单证据跨越摘要与全部付款项高度，不得被压进父 OA 摘要行。
- 单条银行流水/非 OA 来源发票与 OA 或费用子项金额按分精确相等且双方唯一时共享行轨，不再要求整栏完整覆盖。普通父 OA 下有两条或以上银行流水时，只有所有流水都带 canonical `sourceOaId`、当前显示包含完整组成且流水按分合计等于该 OA，才共享一个复合行轨；OA 只渲染一次，流水在轨内等分。显式 `sourceOaId` / `sourceExpenseItemIds[]` 优先；API 映射必须优先 canonical `source_oa_id` / `source_oa_row_id`，历史 `derived_from_oa_id` 只作兜底，不能覆盖 canonical ownership。OA 附件发票的同行只消费顶层 canonical `source_expense_item_ids[]`，原始 `source_links[]` 只作审计证据；OA 附件缺少 canonical 子付款项来源时进入独立待归属残余带，禁止按金额兜底。显式费用子项 ownership 不以金额相等为前提。其他来源缺少显式 ownership 时，只允许在同一完整 source group、方向已知且金额双方都唯一时做展示级精确金额兜底。
- 同一费用子项下的所有显式绑定附件发票共享一个复合行轨；费用子项占满该轨高度，发票在轨内等分。即使合计金额不等，也保持同行并由异常 chip 表达差异。筛选后缺少任一组成发票时不建立部分复合同行。
- 缺少 canonical ownership、合计不等、显示组成不完整的父 OA 级一对多，以及多对一、重复来源、重复金额、零/非法金额、方向未知或冲突，都不建立同行；无显式来源的 2～6 条金额即使合计相等也不做组合推断。已分段栏中的这些记录进入独立残余展示带，完全没有精确配对的栏继续按 group-level 占满整组高度。金额兜底不写 relation、不改变 membership、selection 或 action identity。
- 多项目报销继续显示父 OA 摘要和费用子项；显式来源形成的付款项/发票连通分量同行，每张发票只渲染一次，未归属附件发票留在独立残余展示带且不得进入父摘要。缺失附件发票的展示位只显示原因明确的异常 chip，不得再叠加历史 `未识别附件` 来源标签。发票比较金额统一使用价税合计，银行流水使用当前方向金额。
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
