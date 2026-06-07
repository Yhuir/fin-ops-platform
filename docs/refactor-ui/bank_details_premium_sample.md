# Bank Details Premium Sample

本文档定义 `/bank-details` 作为 HeroUI/Tailwind premium visual sample 的设计规格。它不是新的业务需求，也不是后端改造计划。目标是在保留所有现有功能和交互形态的前提下，把银行明细页面做成高级浅色金融产品样板。

Last updated: 2026-06-07

## Decision Summary

- Visual direction: **Light Banking Console**。
- Scope: 银行明细页面内部 + App Shell 局部视觉升级。
- Density: 保持当前银行流水表格高密度。
- No large cards: 不新增大摘要区，不做 dashboard metric cards，不把表格改成交易卡片流。
- Function preservation: 所有按钮、筛选、导出、分页、分类确认、右侧抽屉、弹窗、菜单和 API 行为必须保留。
- Backend untouched: 不改后端、API contract、read model、worker、权限语义或银行明细业务状态机。

## Product Intent

银行明细是财务人员核对银行流水、确认标签、搜索交易、导出明细和维护自动标签规则的高频工作页。视觉升级必须让页面更像一个成熟金融产品，但不能牺牲扫描效率。

样板页的成功标准不是“更像营销 dashboard”，而是：

- 页面第一眼更干净、更高级。
- 左侧账户列表、顶部工具栏和右侧交易表格更像同一套产品系统。
- 表格仍然一屏显示足够多行。
- 收入/支出、金额、余额、账户来源、交易时间、标签和分类动作更容易扫描。
- 用户不需要重新学习银行明细的操作路径。

## Non-negotiable Functional Inventory

以下入口和行为必须保留。实现时不得删除、隐藏或换成交互形态不同的控件。

### Account Rail

- `银行账户` 列表。
- `全部流水 <n> 条` 入口。
- 每个银行账户的银行名、尾号、余额、流水条数。
- `余额为空` 状态。
- 选中账户通过 `aria-current` 表达。
- 切换账户后继续按当前日期范围、搜索和分页规则请求数据。

### Header And Toolbar

- 当前视图标题，例如 `全部流水`。
- `自动标签规则` 按钮，打开右侧抽屉。
- 日期快捷筛选：`本月`、`上月`、`近7天`、`近30天`、`今年`。
- 日期范围按钮和日期 Popover。
- 日期字段：`年月筛选`、`开始日期`、`结束日期`。
- `导出` / `导出中` 按钮。
- 导出菜单：`导出全部银行`、`导出当前账户`。
- 搜索框：`搜索流水`。
- 标签筛选按钮和菜单：`银行明细标签筛选`。

### Transaction Table

- Accessible name: `交易流水`。
- 表头保持：
  - `对方户名`
  - `类型`
  - `金额`
  - `余额`
  - `用途/交易用途`
  - `摘要`
  - `备注/附言/客户附言`
- 不新增可见 `交易时间` 列或 `操作` 列。
- 交易时间继续在对方户名单元格中展示。
- 金额列继续展示方向 tag、金额和来源银行/账户 tag。
- 分页保持在表格区域外部：
  - `每页行数`
  - `1-100 / 299` 这类 range text
  - page size options `[25, 50, 100]`
  - `下一页` 等可访问标签。

### Row Type Cell

- 已分类行显示已有标签，例如 `费用 / 工资`。
- 未分类行显示 `待分类`。
- 待确认行显示 `待确认`。
- 主标签、子标签、三级业务类型菜单保持行内 Popover/Menu，不改成 drawer/dialog。
- staged choice 不立即调用 API。
- 只有点击 `保存` 才提交。
- `取消`、`保存`、`保存中` 保留。
- 手动确认后 `撤销` 保留。

### Category Filter

- 触发按钮 label 仍以 `标签筛选：` 开头。
- 菜单 accessible name 仍为 `银行明细标签筛选`。
- 点击打开，Escape/外部点击关闭。
- 点击选项后菜单保持旧有交互语义。
- 三列层级结构保留。
- 分类计数、`全部`、`未分类` 和业务标签行保留。

### Auto Tag Rules Drawer

- 仍为右侧抽屉，不改成页面、全屏、卡片区或普通弹窗。
- 名称：`自动标签规则`。
- 关闭按钮：`关闭自动标签规则抽屉`。
- `可用` / `停用` 状态切换保留。
- `新增标签`、`重新应用规则`、`保存` 保留。
- 宽表格编辑器保留。
- 条件编辑 dialog 和停用确认 dialog 保留。
- save/reapply/archive/restore payload 语义不变。

## Visual Direction

### Light Banking Console

采用高级浅色金融产品风格，参考用户截图的浅色 sidebar、简洁主内容、轻边框、明确 action group 和高质量表格节奏，但不照搬 crypto dashboard 的资产卡片和大图表。

### Color Strategy

- Page background: 继续使用冷浅灰，不使用米色、奶油色或大面积深色。
- Sidebar: 浅灰白层，细边界，active item 使用浅灰或浅蓝灰。
- Main surface: 白色或接近白色，不做大卡片阴影。
- Primary action: Ledger Blue，不使用黄色作为主按钮，避免和 warning 混淆。
- Warning: 琥珀色只用于 `待确认`、stale、warning，不用于装饰。
- Income: 绿色。
- Expense: 红/棕红。
- Neutral tags: 用浅灰底和深灰文本承载账户、来源、数量、版本。

### Typography

- 使用现有 Inter/system sans 栈。
- 不使用 display font 或大 hero heading。
- 页面标题、表头、账户名、金额、标签分别用清晰层级。
- 金额、余额、数量继续使用 tabular nums。
- 不使用 viewport-scaled font size。

### Shape And Elevation

- 卡片半径上限 `10px`，表格/账户面板通常 `6-8px`。
- 普通面板以边框和背景层次表达，不用大阴影。
- Popover、Menu、Drawer 可以使用轻量 shadow 以表达浮层。
- 不使用 glassmorphism、gradient text、大装饰阴影。

## Layout Specification

### App Shell Local Visual Upgrade

只做局部视觉升级，不改变路由、菜单入口、权限或导航结构。

- 左侧菜单保留所有现有入口和顺序。
- Sidebar 背景改为更接近截图的浅灰白 surface。
- Active nav item 使用更清晰的圆角浅底和深色文字。
- Icon、label、group spacing 更统一。
- Page body 背景与银行明细页面背景衔接。
- 不新增 global dashboard header，不改其他页面业务结构。

### Bank Details Page

保留当前两栏布局：

- 左：账户 rail。
- 右：交易面板。

优化方向：

- 页面整体更接近一个连续的 banking console，而不是多个旧后台 box。
- 账户 rail 更像截图中的 sidebar list，选中态明确但克制。
- 交易面板头部压缩为一个清晰工具栏区：
  - 左侧当前视图标题。
  - 右侧 `自动标签规则`、日期、导出、搜索等控件。
- 日期快捷筛选视觉改成轻量 segmented control。
- 日期范围按钮、导出按钮、搜索框高度统一。
- 不新增顶部 summary metrics。

### Transaction Table Premium Treatment

保持高密度，重点优化细节：

- Header background 使用浅冷灰。
- Row divider 更轻，hover 更细腻。
- 金额列右对齐，direction tag 固定宽度。
- `收入` / `支出` tag 等宽等高，上下对齐。
- 交易时间 chip 降低视觉重量。
- 来源银行/账户 tag 固定风格，不抢金额主视觉。
- 文本列保持 truncation 和 overflow 规则。
- 空态和 loading 保留表格 frame。

### Category Filter And Type Popovers

- 保留 Popover/Menu 交互形态。
- 视觉上从旧后台菜单提升为清晰浮层：
  - 白色 surface。
  - 轻边框。
  - 小阴影。
  - 三列层级保留。
  - active/hover/focus 状态清晰。
- 不把分类筛选改成 drawer。

### Auto Tag Rules Drawer

右侧抽屉是本页最复杂的工作区，视觉升级原则：

- 保留 `80vw` 左右的大宽度。
- Header 更清楚，title、version、status switcher、actions 分区明确。
- Rule table 保持高密度，不变成表单卡片列表。
- 表头和 editable cell style 更统一。
- 系统行、active row、archived row 的状态更清晰。
- Dialog 继续使用 `AppDialog`，不改变语义。

## HeroUI / Tailwind Usage

允许使用 HeroUI 作为底座，但必须通过项目语义和测试保护功能。

Preferred:

- HeroUI Button for primary/secondary toolbar actions when it does not break existing roles.
- HeroUI Chip or project `FinanceTag` for status/direction/source/count.
- HeroUI Input or project/native input for search/date fields.
- HeroUI Popover/Menu only if it preserves current click/Escape/outside-click behavior.
- Existing `AppDrawer` and `AppDialog` remain the overlay boundary.
- Existing `FinanceTable` remains table boundary.

Avoid:

- Replacing `FinanceTable` with a new table implementation.
- Replacing row popovers with drawers.
- Adding large dashboard cards.
- Adding decorative charts.
- Adding new dependencies.
- Changing backend data shape to feed visual components.

## Implementation Slices

每个 slice 必须先跑目标测试，再改样式/组件，再 rerun 目标测试。不得并行推进多个模块。

### P117 Bank Details Premium Spec

- Write this spec.
- Update `refactor_ui_prompt.md` and `refactor_ui_state.md`.
- No runtime UI changes.

### P118 App Shell Local Surface

- Scope: `web/src/app/styles.css` and, only if necessary, shell class structure.
- Upgrade sidebar/page body visual treatment.
- Preserve all route labels, groups and active state semantics.
- Run App shell tests and smoke.
- Status: verified.
- Execution: App Shell CSS was updated to a flatter light-gray banking workspace, calmer sidebar, clearer active nav, larger brand mark, collapsed sidebar spacing and cleaner page-body rhythm. No routes, sidebar item order, permissions or BankDetails internals changed.
- Verification:
  - `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx`: passed.
  - `cd web && npx vitest run BankDetailsPage.test.tsx -t "loads all accounts by default and its transactions|renders accounts as a list and transactions in the bank transaction table"`: passed.
  - runtime no-MUI grep: passed.
  - `cd web && npm run build`: passed with known warnings.
  - Headless Chrome smoke for `/bank-details`: rendered shell, nav, account rail, toolbar and transaction table; one resource 404 remained.

### P119 Bank Details Layout And Toolbar

- Scope: page layout, account rail, title toolbar, date controls, export/search controls.
- No table row behavior changes.
- Keep no summary metrics and no large cards.
- Run BankDetails targeted tests.
- Status: verified.
- Execution: BankDetails tokens, account rail, transaction panel header, title hierarchy, date segmented control, date range button, export trigger/menu, search field and category-filter button surroundings were visually upgraded toward the Light Banking Console direction. The implementation stayed in `web/src/app/styles.css`; table headers, row rendering, pagination behavior, TypeCell, category filter menu behavior and AutoTagRulesDrawer were not changed.
- Verification:
  - `cd web && npx vitest run BankDetailsPage.test.tsx -t "loads all accounts by default and its transactions|renders accounts as a list and transactions in the bank transaction table|selecting account and filters request accounts and transactions with the same date range|exports all banks or the selected account with the current filters"`: passed.
  - `cd web && npx vitest run App.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed.
  - runtime no-MUI grep: passed.
  - `cd web && npm run build`: passed with known warnings.
  - `git diff --check`: passed.
  - Headless Chrome smoke for `/bank-details`: shell, sidebar, BankDetails page, account rail, transaction panel, toolbar, search and table rendered with no JS runtime errors captured.

### P120 Bank Details Table Premium Treatment

- Scope: table header, row density, amount cell, direction tags, source tags, empty/loading rows, pagination surface.
- Preserve high density and all headers.
- Run BankDetails table/pagination/category tests.
- Status: verified.
- Prompt ID: `P120-bank-details-table-premium-treatment`.
- Execution: transaction table header, row dividers, hover state, amount grid, fixed-width direction tags, source tags, trade-time chips and relation chips were visually refined for the Light Banking Console sample. P120 also removed the two top error bars from the BankDetails visual flow: the global background-progress stack is not rendered on `/bank-details`, and the page-level fetch error is preserved only as a visually hidden live region. Collapsed sidebar icon targets are centered in the 72px rail.
- Verification:
  - `cd web && npx vitest run BankDetailsPage.test.tsx -t "uses Chinese labels for table pagination and exposes keyword search|keeps pagination outside the table scroll area|uses a dense three-column grouped category filter layout|shows read-only auto category and keeps manual category controls out of bank details|renders accounts as a list and transactions in the bank transaction table"`: passed.
  - `cd web && npx vitest run BankDetailsPage.test.tsx -t "loads all accounts by default and its transactions|selecting account and filters request accounts and transactions with the same date range|exports all banks or the selected account with the current filters"`: passed.
  - `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed.
  - runtime no-MUI grep: passed.
  - `cd web && npm run build`: passed with known warnings.
  - `git diff --check`: passed.
  - Headless Chrome smoke for `/bank-details`: top error bars absent, page top is `0`, collapsed sidebar icon center aligns with sidebar center, transaction table rendered with no JS runtime errors captured.
- Guardrails:
  - Keep accessible table name `交易流水`.
  - Keep visible headers exactly as current 7-column table.
  - Do not add visible `交易时间` or `操作` columns.
  - Keep pagination outside the scroll area.
  - Keep TypeCell and category popover behavior unchanged.

### P121 Bank Details Popovers And Drawer Polish

- Scope: category filter popover, row type popover, internal transfer tooltip, auto tag drawer visual polish.
- Preserve overlay shapes and payload behavior.
- Run BankDetailsPage and AutoTagRulesDrawer tests.
- Status: verified.
- Prompt ID: `P121-bank-details-popovers-drawer-polish`.
- Execution: category filter popover, row type confirmation popover, internal transfer tooltip, BankCategoryTag hierarchy tooltip and AutoTagRulesDrawer visuals were refined to the Light Banking Console language. Overlay shapes stayed the same: category filter remains a popover/menu, row classification remains an inline popover/menu, automatic tag rules remains a right drawer, and condition/archive controls remain dialogs.
- Verification:
  - `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`: passed.
  - `cd web && npx vitest run App.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed.
  - runtime no-MUI grep: passed.
  - `cd web && npm run build`: passed with known warnings.
  - `git diff --check`: passed.
  - Headless Chrome smoke for `/bank-details`: page/table rendered, top error bars absent, AutoTagRulesDrawer opened with the new light surface and no JS runtime errors captured.

### MG-P121 Bank Details Premium Sample

- Run:
  - `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`
  - `cd web && npx vitest run App.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx TableAlignmentStyles.test.ts`
  - `cd web && npm run build`
  - runtime no-MUI grep
  - browser smoke for `/bank-details`
  - `git diff --check`
- Exact stage only.
- Commit and push only after scope and verification pass.
- Status: verified.
- Prompt ID: `MG-P121-bank-details-premium-sample`.
- Scope files:
  - `web/src/app/App.tsx`
  - `web/src/pages/BankDetailsPage.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/bank_details_premium_sample.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`
- Execution:
  - Scope check passed; no backend/API/read model/worker/permission/business state machine/workbench files changed.
  - Exact staging was used for the scope files only.
  - Commit message: `style: polish bank details premium sample`.
  - Push target: `origin/refactor-ui`.
- Verification:
  - `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`: passed, 52 tests.
  - `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx TableAlignmentStyles.test.ts`: passed, 31 tests.
  - runtime no-MUI grep: passed.
  - `cd web && npm run build`: passed with known warnings.
  - headless Chrome `/bank-details` smoke: page/table rendered, top error bars absent, AutoTagRulesDrawer opened, no JS runtime errors.
  - `git diff --check`: passed.

## Acceptance Criteria

- `/bank-details` visibly matches Light Banking Console direction.
- No large card dashboard or metrics summary added.
- All user-visible BankDetails functions from `phase_6_bank_details.md` remain available.
- Bank transaction table remains high-density and keeps existing headers.
- App Shell visual change is local and does not remove or reorder navigation entries.
- All BankDetails and AutoTagRulesDrawer tests pass.
- Full no-MUI runtime contract remains true.
- Build passes.
- Browser smoke confirms `/bank-details` renders without blank page or obvious overlap at desktop viewport.

## Residual Risks

- App Shell local visual changes may affect other routes because shell CSS is shared. P118 must run App tests and at least one smoke route outside BankDetails.
- BankDetails tests currently include several CSS source assertions. Visual changes must update assertions only when behavior and functional geometry remain equivalent.
- HeroUI components can alter roles/portals. If a HeroUI replacement changes accessible roles, prefer project/native controls unless tests prove equivalence.
- Browser smoke may require backend/mock availability. If full API-backed route cannot run locally, record limitation and use component tests plus local shell smoke.
