# Workbench MUI Migration Master Goal Prompt

本文档保存一条可直接交给 Codex 的主控指令，用于在非关联台 UI 迁移完成后，继续把关联台内部工作区从残留 MUI 迁移到 HeroUI v3 + Tailwind CSS v4 + 项目本地 primitives。

这不是单个切片 prompt。执行者必须根据状态机一次只生成、审查、执行一条 Micro-JIT prompt，并在每条 prompt 或 MG 后更新状态文档，直到关联台内部工作区不再依赖 MUI。

```text
/goal 在 /Users/yu/Desktop/fin-ops-platform 的 refactor-ui 分支上，完整执行关联台内部工作区 MUI 迁移计划，直到 ReconciliationWorkbenchPage 和 web/src/components/workbench/* 的运行时代码不再引入 @mui/*，web/src/app/styles.css 不再包含关联台 .Mui* 选择器，测试专用 legacy MUI provider 被移除，MUI/Emotion 依赖在确认无剩余用途后从 web/package.json 和 lockfile 中清理，并且所有必要测试、build、文档状态、MG commit、push 全部闭环。目标栈保持 React 19 + HeroUI v3 + Tailwind CSS v4 + 项目本地 primitives。不得停止在计划、分析或半成品状态。

你必须先执行以下启动步骤：
1. 进入 /Users/yu/Desktop/fin-ops-platform。
2. 确认当前分支是 refactor-ui；如果不是 refactor-ui，停止并说明，不得在 main 上执行迁移。
3. 读取 AGENTS.md、README.md、ARCHITECTURE.md、docs/index.md、PRODUCT.md、DESIGN.md。
4. 读取 docs/refactor-ui/README.md、refactor_ui_state.md、refactor_ui_prompt.md、refactor_ui_master_goal_prompt.md、workbench_migration_master_goal_prompt.md、table_layout_system.md、test_migration_strategy.md、modules/phase_7_mui_containment.md、modules/phase_8_full_verification.md。
5. 如果以下文件不存在，先创建并初始化：docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md、docs/refactor-ui/modules/workbench_mui_migration.md。若文件已存在，先读取并继续，不得覆盖既有记录。
6. 运行 git status --short --branch，识别未提交变更和 untracked files。不得覆盖用户改动；不得使用 git reset --hard、git checkout --、git add . 或 git add -A。
7. 运行以下基线扫描，并把结果写入 docs/refactor-ui/modules/workbench_mui_migration.md：
   - rg -n "^import .*@mui|from \"@mui|from '@mui|@mui/|Mui[A-Z]|\\.Mui" web/src/pages/ReconciliationWorkbenchPage.tsx web/src/components/workbench web/src/test/legacyWorkbenchMuiProvider.tsx web/src/test/workbenchRenderHelpers.tsx web/src/test/WorkbenchExceptionModal.test.tsx web/src/app/styles.css
   - rg -n "from \"@mui|from '@mui|@mui/" web/src --glob "!web/src/components/workbench/**" --glob "!web/src/test/**"
   - rg -n "\\.Mui|Mui[A-Z]" web/src/app/styles.css web/src/components/workbench web/src/test

本专项迁移的核心判断：
1. 这是关联台内部工作区的 UI 平台迁移，不是产品交互再设计。
2. 用户使用起来必须感觉功能上一模一样：旧入口仍在同等位置，旧状态仍可见，旧反馈仍存在，旧右侧抽屉仍是右侧抽屉，旧弹窗仍是弹窗，旧行操作仍是行操作。
3. 不要把关联台三栏工作区重写成 HeroUI Table。ResizableTriPane、CandidateGroupGrid、三栏布局、同步滚动、列拖拽、行分组、候选组选中/高亮/折叠等核心结构必须保留，除非后续用户明确批准重写。
4. HeroUI 只用于替换残留 MUI 控件和 overlay primitive：Button、Tooltip、Input、Chip、Popover/Dialog/Drawer 等；复杂三栏表格继续使用现有 custom DOM/CSS 和项目 primitives。
5. Tailwind/CSS 用于统一 token、spacing、focus、hover、disabled、overflow、tabular nums 和稳定尺寸；不能使用 hard-code 魔法值随意覆盖设计系统。

全局不可违反的边界：
1. 不改后端功能，不改 API contract，不改 read model，不改 worker/queue，不改权限语义，不改业务状态机。
2. 不改变关联台路由、数据获取、URL/search params、权限判断、异常处理、提交/撤回/确认业务语义。
3. 不改变 App Shell 已完成迁移后的大布局；只处理关联台内部工作区残留 MUI。
4. 不引入新的通用表格状态库、虚拟滚动库或业务状态管理库。
5. 不为了迁移组件而删除旧功能入口。现在哪里有按钮、筛选、toggle、搜索、展开、tooltip、行菜单、弹窗或右侧详情，新 UI 就必须保留同等入口和交互形态。
6. 不用旧 MUI class name 作为新测试契约；测试必须转向用户行为、ARIA/语义、project primitive contract、稳定 class 或 design-token contract。

执行方式必须严格遵守 Micro-JIT：
1. 每次只能生成一条 prompt，不允许一次性生成多个 prompt。
2. 每条新 prompt 必须基于上一条 prompt/MG 的完成情况、验证结果、当前 diff、untracked files、状态机、模块文档和相关代码/测试现场单独分析生成。
3. 每条 prompt 执行前必须写入 docs/refactor-ui/workbench_migration_prompt.md，并完成审查：单一范围、非目标、旧入口保护、overlay 形态保护、验证命令、文档更新、是否需要新建专项 md。
4. 同一切片必须按 discovery/planning -> characterization tests -> extraction/refactor -> verification -> cumulative MG 推进。不得跳过 characterization tests，除非该切片是纯文档或纯配置，并且 prompt 中写明理由。
5. 每次 prompt 或 MG 完成后，必须更新 docs/refactor-ui/workbench_migration_state.md、docs/refactor-ui/workbench_migration_prompt.md 和 docs/refactor-ui/modules/workbench_mui_migration.md。若发现会影响后续任务的新事实，可以按需新建 docs/refactor-ui/modules/<workbench-submodule>.md；不需要跨切片复用的一次性分析不要新建 md。
6. 到达可合并边界后必须执行 cumulative MG：检查 scope、untracked files、diff、测试、文档状态；只允许精确 git add <file...>；commit message 必须描述本 MG 范围；push 到 refactor-ui；push 后把 MG 标记为 verified。
7. push 完成后，继续从 refactor-ui 分支读取最新状态，再生成下一条 prompt。

必须按以下完整路径推进，每个 phase 内部仍然只能逐条生成 prompt：

1. wb_phase_0_baseline
   - 创建或读取 docs/refactor-ui/workbench_migration_state.md、workbench_migration_prompt.md、modules/workbench_mui_migration.md。
   - 记录当前 MUI import、.Mui CSS、test provider、package dependency、workbench 测试清单、风险等级。
   - 明确当前直接运行时 MUI 文件：web/src/components/workbench/WorkbenchZone.tsx、WorkbenchPaneSearch.tsx、WorkbenchRecordCard.tsx。
   - 明确测试 MUI helper：web/src/test/legacyWorkbenchMuiProvider.tsx、web/src/test/workbenchRenderHelpers.tsx、web/src/test/WorkbenchExceptionModal.test.tsx。
   - 明确三栏核心非 MUI 文件，例如 ResizableTriPane.tsx、CandidateGroupGrid.tsx，并写明不重写。
   - 完成 baseline MG 并 push。

2. wb_phase_1_characterization
   - 为关联台旧行为补 characterization tests，先保护功能体感再迁移组件。
   - 覆盖 WorkbenchZone：标题、统计、selection toolbar、确认/撤回/批量操作按钮、toggle、展开按钮、disabled/loading/tooltip。
   - 覆盖 WorkbenchPaneSearch：搜索打开/关闭、输入、清空、回车、外部点击、focus、结果摘要、loading/empty。
   - 覆盖 WorkbenchRecordCard：风险/异常 icon、tooltip、行 click、详情入口、按钮冒泡隔离、disabled 状态。
   - 新增或调整 source-level no-MUI expectation，初期可以 expected-fail 或记录为迁移目标，但最终必须变成通过。
   - 完成 characterization MG 并 push。

3. wb_phase_2_zone_header_controls
   - 迁移 WorkbenchZone.tsx 中 Box、Button、Chip、IconButton、Stack、ToggleButton、ToggleButtonGroup、Tooltip、Typography。
   - 使用 HeroUI 或项目 primitives 替代按钮、tooltip、chip 和 toggle；必要时用语义化 button group + Tailwind 实现 pane toggle，确保键盘和 aria 状态明确。
   - 保留旧布局位置、密度、按钮顺序、禁用/加载/提示、上下收支 tag 对齐和 pane expand 行为。
   - 删除该文件中的 MUI sx/class 依赖，改为项目 class/token。
   - 更新测试并完成 MG。

4. wb_phase_3_pane_search
   - 迁移 WorkbenchPaneSearch.tsx 中 ClearIcon、SearchIcon、Grow、IconButton、InputAdornment、TextField。
   - 使用 lucide icons、HeroUI Input/Button/Tooltip 或项目 SearchField primitive；保持旧搜索栏展开方式、focus、清空、快捷操作、结果摘要和 aria label。
   - 移除依赖 MUI input class 的 CSS，改成 stable project selectors。
   - 更新测试并完成 MG。

5. wb_phase_4_record_card_actions
   - 迁移 WorkbenchRecordCard.tsx 中 WarningAmberRoundedIcon、IconButton、Tooltip 和 MUI sx icon selector。
   - 使用 lucide warning/info icons、HeroUI Tooltip/Button 或项目 IconButton primitive。
   - 保留 row click、detail open、action click stopPropagation、tooltip text、aria label、风险视觉语义。
   - 更新测试并完成 MG。

6. wb_phase_5_css_containment_cleanup
   - 清理 web/src/app/styles.css 中关联台 .Mui* 选择器，包括 zone title、selection pill、selection button、toggle、expand icon、pane search field。
   - 迁移为稳定的 project selectors，确保 hover/focus/disabled/selected/loading 视觉状态完整。
   - 扫描 web/src/components/workbench 和 web/src/app/styles.css，不得再出现 .Mui 或 Mui[A-Z] 运行时样式。
   - 完成 MG。

7. wb_phase_6_test_provider_cleanup
   - 移除 web/src/test/legacyWorkbenchMuiProvider.tsx。
   - 更新 web/src/test/workbenchRenderHelpers.tsx、web/src/test/WorkbenchExceptionModal.test.tsx 和相关测试 provider，使其只依赖 HeroUI/project test provider。
   - 迁移或删除旧 MUI theme/locale/date picker 测试依赖；如果关联台内部没有日期选择器，不得保留无用 provider。
   - 所有工作台相关测试通过后完成 MG。

8. wb_phase_7_dependency_cleanup
   - 运行全仓 MUI import/usage 扫描，确认 web/src 中没有 @mui/*、MuiProviders、muiTheme、legacyWorkbenchMuiProvider、.Mui selectors。
   - 审核 web/package.json 和 lockfile。若 @mui/material、@mui/icons-material、@mui/x-data-grid、@mui/x-date-pickers、@emotion/react、@emotion/styled 已无用途，精确移除并更新 lockfile。
   - 运行 npm ls 或等价命令确认依赖树健康。
   - 完成 dependency cleanup MG 并 push。

9. wb_phase_8_full_verification
   - 运行工作台专项测试、非关联台回归测试、MUI containment 测试、build。
   - 若本地 dev server 可用，做关联台浏览器 smoke：三栏可见、pane resize、搜索、toggle、展开、行点击、右侧详情、弹窗、关键按钮状态无重叠。
   - 如果浏览器 smoke 因环境限制无法完成，必须记录原因和剩余风险，不得假称完成。
   - 完成 full verification MG。

10. wb_phase_9_closeout
    - 收口 docs/refactor-ui/README.md、workbench_migration_state.md、workbench_migration_prompt.md、modules/workbench_mui_migration.md。
    - 记录最终 no-MUI contract、验证命令、push log、剩余风险、后续 QA 建议。
    - 确认最终 commit 已 push 到 refactor-ui。

建议验证命令池：
1. git status --short --branch
2. cd web && npx vitest run WorkbenchSelection.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx
3. cd web && npx vitest run MuiContainment.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx App.test.tsx
4. cd web && npm run build
5. if rg -n "@mui/|Mui[A-Z]|@mui/x-date-pickers|@mui/x-data-grid|legacyWorkbenchMuiProvider|MuiProviders|muiTheme" web/src; then exit 1; else exit 0; fi
6. if rg -n "\\.Mui|Mui[A-Z]" web/src/app/styles.css web/src/components/workbench; then exit 1; else exit 0; fi
7. npm --prefix web ls @mui/material @mui/icons-material @mui/x-data-grid @mui/x-date-pickers @emotion/react @emotion/styled

每个实现切片必须遵守测试纪律：
1. 先判断七类测试是否适用：业务核心、service、API contract、read model/cache/job、前端组件交互、E2E business flow、既有功能回归。
2. 本专项通常不触及业务核心、service、API contract、read model/cache/job；若误触这些范围，必须停止并说明 scope drift。
3. UI 切片通常至少需要第 5 类前端组件/交互测试和第 7 类既有功能回归测试；涉及完整关联台路径时可以追加第 6 类 E2E/smoke。
4. 测试必须保护用户可见行为、ARIA/语义、primitive contract 和设计 token，不保护旧 MUI class name。
5. 若某类测试不适用，最终回复必须写明原因。

每个阶段的完成标准：
1. 当前 phase 的所有必要 prompt 均 verified。
2. 当前 phase 的 MG 已 verified 并 push 到 refactor-ui。
3. docs/refactor-ui/workbench_migration_state.md 的 Phase Table、Prompt Queue、Verification Log、Push Log 已更新。
4. docs/refactor-ui/workbench_migration_prompt.md 记录了已执行 prompt、review、execution notes、verification 和下一条 prompt slot。
5. docs/refactor-ui/modules/workbench_mui_migration.md 已更新当前事实，或明确说明无需新增专项 md。
6. git status 已检查；没有无意进入仓库的临时文件、截图、导出物或 unrelated changes。

如果遇到失败或不确定：
1. 先按 systematic debugging 调查，读取相关代码、测试、文档和错误输出。
2. 不要绕过失败测试，不要放宽断言掩盖问题，不要用 skip/ignore_errors 隐藏问题。
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
1. wb_phase_0_baseline 到 wb_phase_9_closeout 全部 completed/verified。
2. web/src 运行时和测试代码无 @mui/* import、MuiProviders、muiTheme、legacyWorkbenchMuiProvider。
3. web/src/app/styles.css 和 web/src/components/workbench 无 .Mui* 或 Mui[A-Z] 选择器。
4. web/package.json 和 lockfile 不再保留无用途 MUI/Emotion 依赖。
5. 关联台三栏结构、行交互、右侧详情、内部弹窗、搜索、toggle、展开、批量操作、权限/disabled/loading/empty/error 状态均保持用户体感等价。
6. 工作台专项测试、非关联台回归测试、MUI containment 测试、build 和必要 smoke 通过，或明确记录无法完成的验证及风险。
7. 文档、状态机、prompt registry、push log 全部闭环。
8. 最终 commit 已 push 到 refactor-ui。
```
