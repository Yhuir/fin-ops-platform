# Refactor UI Master Goal Prompt

本文档保存一条可直接交给 Codex 的主控指令。它不是切片 prompt；它是持续执行整个 UI 平台迁移计划的入口。执行者必须根据状态机逐条生成、审查、执行 Micro-JIT 切片 prompt，直到 `phase_9_closeout` verified 并 push。

```text
/goal 在 /Users/yu/Desktop/fin-ops-platform 的 refactor-ui 分支上，完整执行 fin-ops-platform 非关联台 UI 平台迁移计划，直到 docs/refactor-ui/refactor_ui_state.md 中 phase_0_baseline 到 phase_9_closeout 全部 verified/completed，所有必要 MG 均已精确提交并 push 到 refactor-ui。目标栈是 React 19 + HeroUI v3 + Tailwind CSS v4。迁移必须形成闭环：设计事实源、平台栈、primitives、App Shell、表格系统、页面模块、MUI containment、全量验证和 closeout 文档全部完成。不得停止在计划、分析或半成品状态。

你必须先执行以下启动步骤：
1. 进入 /Users/yu/Desktop/fin-ops-platform。
2. 确认当前分支是 refactor-ui；如果不是 refactor-ui，停止并说明，不得在 main 上执行 UI 重构。
3. 读取 AGENTS.md、README.md、ARCHITECTURE.md、docs/index.md、PRODUCT.md、DESIGN.md。
4. 读取 docs/refactor-ui/README.md、refactor_ui_state.md、refactor_ui_prompt.md、refactor_ui_master_goal_prompt.md、baseline_inventory.md、platform_stack_migration.md、test_migration_strategy.md、module_inventory.md、table_layout_system.md。
5. 运行 git status --short --branch，识别未提交变更和 untracked files。不得覆盖用户改动；不得使用 git reset --hard、git checkout --、git add . 或 git add -A。
6. 若 MG-P001-baseline-doc-gap-fill 仍是 reviewed-not-executed，先执行该 MG：检查 scope、diff、验证记录，精确 git add PRODUCT.md DESIGN.md docs/index.md docs/refactor-ui/README.md docs/refactor-ui/baseline_inventory.md docs/refactor-ui/platform_stack_migration.md docs/refactor-ui/test_migration_strategy.md docs/refactor-ui/module_inventory.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md docs/refactor-ui/refactor_ui_master_goal_prompt.md docs/refactor-ui/table_layout_system.md，commit message 使用 docs: complete ui refactor baseline，push 到 refactor-ui，并把 MG 标记为 verified。

全局不可违反的边界：
1. 不改后端功能，不改 API contract，不改 read model，不改 worker/queue，不改权限语义，不改业务状态机。
2. 非关联台 UI 必须迁出 MUI，迁到 HeroUI + Tailwind + 项目本地 primitives。
3. 关联台内部工作区冻结：ReconciliationWorkbenchPage 和 web/src/components/workbench/* 的三栏工作台、行交互、内部弹窗和专用 CSS 不作为本次迁移目标。新的 App Shell 可以包住关联台，但不得重构其内部工作区。
4. MUI 短期只允许冻结的关联台内部工作区继续使用。非关联台新增 UI 不得引入 @mui/*。
5. 用户操作体感必须一致：旧按钮仍在同等位置，旧筛选/导入/导出/确认/权限反馈仍保留；旧右侧抽屉必须仍是右侧抽屉，旧弹窗必须仍是弹窗，旧菜单/Popover/表格行操作/工具栏入口必须保持同类交互形态和同等信息层级。
6. 不引入 TanStack Table/TanStack Virtual 或新的通用表格状态库，除非用户后续明确批准。
7. 不用 HeroUI/Tailwind 默认外观替代项目设计系统；必须落实 DESIGN.md 的 Ledger Calm 和 table_layout_system.md 的表格排版系统。

执行方式必须严格遵守 Micro-JIT：
1. phase_0 到 phase_9 是阶段容器，不是单条任务。每个 phase 可以包含多个 prompt 和多个 MG。
2. 不允许一次性生成一个 phase 的全部 prompt。每次只能生成一条 prompt。
3. 每条新 prompt 必须基于上一条 prompt/MG 的完成情况、验证结果、当前 diff、untracked files、状态机、模块文档和相关代码/测试现场单独分析生成。
4. 每条 prompt 执行前必须先写入 docs/refactor-ui/refactor_ui_prompt.md，并审查：单一范围、非目标、验证命令、文档更新、是否需要新建专项 md、是否保护旧入口和 overlay 形态。
5. 同一模块必须按 discovery/planning -> characterization tests -> extraction/refactor -> verification -> cumulative MG 推进。不得跳过 characterization tests，除非该切片是纯文档或纯配置，并且 prompt 中写明理由。
6. 每次 prompt 或 MG 完成后，必须更新 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md 和相关模块文档。需要跨切片复用的 discovery、旧入口对照、风险、测试策略或组件迁移规则，按需新建 docs/refactor-ui/modules/<module>.md；一次性临时分析不要新建 md。
7. 到达可合并边界后必须执行 cumulative MG：检查 scope、untracked files、diff、测试、文档状态；只允许精确 git add；commit message 必须描述本 MG 范围；push 到 refactor-ui；push 后把 MG 标记为 verified。

必须按以下完整路径推进，不得跳过平台栈、primitives 或表格系统直接迁页面：
1. 完成并 push MG-P001-baseline-doc-gap-fill。
2. phase_1_docs_and_tokens：收口 PRODUCT/DESIGN、Ledger Calm token、Tailwind token bridge、HeroUI 使用规则，确保设计事实源可执行。
3. phase_2_platform_stack：升级 React 19，接入 HeroUI v3、Tailwind CSS v4、Vite 插件和 CSS import；完成 build 与基础 shell smoke。
4. phase_3_primitives：建立本地 UI primitives，包括 Button、Tag、StatePanel、Dialog、右侧 Drawer、Toolbar、Tooltip、Icon、MonthPicker、AmountCell、FinanceTag、基础 session/format helpers。
5. phase_4_shell：迁移 App Shell，保留左侧菜单、顶部栏、页面容器、路由、权限入口、全局状态和关联台外层 wrapper。
6. phase_5_table_system：落地 FinanceTable、表格 cell primitives、分页、loading/empty/error、列角色、金额对齐、上下 tag 对齐、tooltip/overflow、表格测试策略。
7. phase_6_page_batches：按 docs/refactor-ui/module_inventory.md 的页面队列逐模块迁移非关联台页面。每个页面必须先 discovery，再 characterization tests，再实现迁移，再 verification，再 MG。
8. phase_7_mui_containment：清理非关联台 @mui/*，只允许冻结的关联台内部工作区继续使用 MUI，并记录隔离边界。
9. phase_8_full_verification：运行全量前端测试、build、关键页面 smoke、桌面/紧凑屏/OA embedded/关联台 wrapper 验证。必要时用浏览器截图或 smoke 验证 UI 非空、布局无重叠、抽屉/弹窗形态正确。
10. phase_9_closeout：收口文档、剩余风险、关联台后续计划、最终 MUI containment 说明、测试结果、push log 和可交接状态。

每个实现切片必须遵守测试纪律：
1. 先判断七类测试是否适用：业务核心、service、API contract、read model/cache/job、前端组件交互、E2E business flow、既有功能回归。
2. UI 切片通常至少需要第 5 类前端组件/交互测试和第 7 类既有功能回归测试；跨模块流程需要第 6 类 E2E。
3. 测试必须保护用户可见行为、ARIA/语义、primitive contract 和设计 token，不保护旧 MUI class name。
4. 旧右侧抽屉必须有右侧形态测试；旧弹窗必须有 dialog 语义测试；旧表格必须有列角色、金额对齐、tag 对齐、loading/empty/error/permission 状态测试。
5. 若某类测试不适用，最终回复必须写明原因。

每个阶段的完成标准：
1. 当前 phase 的所有必要 prompt 均 verified。
2. 当前 phase 的 MG 已 verified 并 push 到 refactor-ui。
3. docs/refactor-ui/refactor_ui_state.md 的 Phase Table、Module Queue、Verification Log、Push Log 已更新。
4. docs/refactor-ui/refactor_ui_prompt.md 记录了已执行 prompt、review、execution notes、verification 和下一条 prompt slot。
5. 相关模块文档已更新，或明确说明无需新建专项 md。
6. git status 已检查；没有无意进入仓库的临时文件、截图、导出物或 unrelated changes。

如果遇到失败或不确定：
1. 先按 systematic debugging 调查，读取相关代码、测试、文档和错误输出。
2. 不要绕过失败测试，不要放宽断言掩盖问题，不要用 skip/ignore_errors 隐藏清理或 background job 问题。
3. 如果同一个阻塞条件连续三轮仍无法推进，记录 blocked 原因、已尝试命令、剩余风险和需要用户决策的问题。
4. 除非被明确阻塞，否则继续按状态机推进下一条 prompt，不要停在分析阶段。

每次最终回复或阶段记录必须包含：
1. 完成了什么。
2. 修改了哪些文件或模块。
3. 新增/修改了哪些测试，以及覆盖七类测试中的哪些类别。
4. 运行了哪些验证命令和结果。
5. 是否 commit/push，push 到哪个分支和 commit。
6. 当前 phase/prompt/MG 状态。
7. 下一步是什么。

最终完成条件：
1. phase_0_baseline 到 phase_9_closeout 全部 completed/verified。
2. 非关联台无 @mui/* import；冻结关联台内部工作区除外。
3. React 19 + HeroUI v3 + Tailwind CSS v4 平台栈构建通过。
4. App Shell、表格系统、所有非关联台页面、抽屉、弹窗、表单、按钮、状态提示、权限状态均完成迁移并验证。
5. 用户可见功能入口和操作体感与旧 UI 等价。
6. 全量测试/build/smoke 通过或明确记录无法完成的验证及风险。
7. 文档、状态机、prompt registry、push log 全部闭环。
8. 最终 commit 已 push 到 refactor-ui。
```
