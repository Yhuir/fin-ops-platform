# Phase 6 Bank Details Discovery

本文档记录银行明细页迁移 discovery。目标是把 `/bank-details` 中仍依赖 MUI 的页面壳、账户列表、日期筛选、导出菜单、标签筛选 Popper、交易流水表格、行内类型选择 Popper、自动标签规则右侧抽屉和弹窗迁到 HeroUI/Tailwind/project primitives，同时保持用户操作体感不变。

Last updated: 2026-06-07

## Boundary

- Scope: `/bank-details`、`web/src/pages/BankDetailsPage.tsx`、`web/src/features/bankDetails/*`、`web/src/test/BankDetailsPage.test.tsx`、`web/src/test/AutoTagRulesDrawer.test.tsx`。
- Non-scope: 不改后端、API contract、read model、worker、权限语义、银行明细业务状态机、自动标签规则 payload、关联台内部工作区。
- Behavior equivalence:
  - 旧页面仍是左侧账户列表 + 右侧交易面板的大布局，不改成卡片流或分步页。
  - 旧交易流水仍是高密度表格，不改成虚拟列表或卡片列表。
  - 旧分页仍在表格滚动区域外部，不放回表格滚动容器内部。
  - 旧日期快捷筛选仍是顶部 segmented control；旧自定义日期仍是 Popover，不改成抽屉或弹窗。
  - 旧导出入口仍是工具栏按钮 + menu，不改成弹窗或独立页面。
  - 旧标签筛选仍是固定图标触发的 Popper/menu，点击打开、Escape/外部点击关闭，不改成 drawer/dialog。
  - 旧行内 `待确认` / `待分类` 类型选择仍是行内 Popper/menu，保留主标签、子标签、三级业务类型列和 staged save flow。
  - 旧 `自动标签规则` 仍是右侧抽屉，宽度约 `80vw`，不改成全屏页或普通弹窗。
  - 自动标签规则内部旧条件编辑和停用确认仍是 dialogs，不改成 inline-only 操作。
  - 所有现有按钮、菜单项、搜索框、筛选项、抽屉关闭按钮、保存/重新应用入口必须在新 UI 的同等位置和同等交互形态中存在。

## Current MUI Inventory

| Usage | Current file | Migration target | Notes |
| --- | --- | --- | --- |
| Page/layout primitives: `Box`, `Stack`, `Paper`, `Typography`, `Divider`, `List`, `ListItem`, `ListItemButton`, `ListItemText` | `BankDetailsPage.tsx` | project layout classes, native semantic elements, HeroUI where useful | Preserve left account list and right transaction panel geometry. |
| Account chips and transaction chips | `BankDetailsPage.tsx` | project tag/chip primitive or HeroUI `Chip` with token classes | Counts, balances, `余额为空`, trade time, relation tags and source bank/account chips must keep compact alignment. |
| Category filter trigger and panel: `ClickAwayListener`, `IconButton`, `Popper`, `Paper`, `List`, `ListItemButton`, `ListItemText`, `Divider`, `FilterListOutlinedIcon` | `BankDetailsPage.tsx` | project popover/menu primitive + lucide filter icon or HeroUI popover if it preserves click-only behavior | Must keep `aria-label="银行明细标签筛选"`, `role="menu"`, `role="menuitem"`, `aria-current`, `data-level`, three-column dense hierarchy and open-on-click-only behavior. |
| Toolbar export/search: MUI `Button`, `Menu`, `MenuItem`, `TextField` | `BankDetailsPage.tsx` | HeroUI `Button`, project menu/popover, HeroUI/native input | Keep `导出`, `导出中`, menu label `导出银行明细`, `导出全部银行`, `导出当前账户`, and search placeholder/label `搜索流水`. |
| Date presets and date range controls: `ToggleButtonGroup`, `ToggleButton`, `Button`, `Popover`, `TextField`, MUI X `DatePicker`, `dayjs` | `BankDetailsPage.tsx` | HeroUI/Tailwind segmented control plus native month/date fields or project date primitive | Keep presets `本月`、`上月`、`近7天`、`近30天`、`今年`; keep labels `年月筛选`、`开始日期`、`结束日期`. |
| Transaction table: `Table`, `TableContainer`, `TableHead`, `TableBody`, `TableRow`, `TableCell`, `TablePagination` | `BankDetailsPage.tsx` | `FinanceTable` plus project pagination primitive | Keep table name `交易流水`, headers, sticky/dense layout, server pagination labels `每页行数` and `1-100 / 299`, page size options `[25, 50, 100]`. |
| Transaction row loading/empty | `BankDetailsPage.tsx` | `StatePanel` or table empty row primitive | Keep `正在加载流水。` and `当前时间范围内没有流水。`. |
| `TypeCell` row category confirmation/assignment: MUI `Button`, `Popper`, `ClickAwayListener`, `Paper`, `MenuList`, `ListItemButton`, `ListItemText`, `Divider`, `Stack`, `Typography` | `BankDetailsPage.tsx` | project popover/menu columns + HeroUI/project buttons | Preserve `待确认`/`待分类` triggers, staged choice label, `取消`, `保存`, `保存中`, all menu names and third-level business type flow. |
| Internal transfer tooltip: MUI `Tooltip`, `Box`, `Typography` | `BankDetailsPage.tsx` | HeroUI/project tooltip | Preserve tooltip role/name and structured rows for `对应内部往来流水`. |
| `BankCategoryTag`: MUI `Chip`, `Tooltip`, `Box`, `Typography` | `BankCategoryTag.tsx` | project category tag/tooltip primitive or HeroUI chip + project tooltip | Used by transaction rows and filters; keep compact two-line label and hierarchy tooltip. |
| Auto tag rules right drawer: MUI icons, `Drawer`, `Button`, `IconButton`, `ToggleButtonGroup`, `Alert`, `CircularProgress`, `Table`, `TextField`, `Select`, `Checkbox`, `Tooltip`, `Dialog` | `AutoTagRulesDrawer.tsx` | `AppDrawer`, `AppDialog`, HeroUI form controls/table or project primitives, lucide icons | Must remain right drawer, keep active/archived tabs, table-based rule editor, condition editor dialog, archive confirmation dialog. |
| Test providers | `BankDetailsPage.test.tsx`, `AutoTagRulesDrawer.test.tsx` | remove `MuiProviders` after runtime MUI is removed from this module | Current tests rely on MUI providers for MUI X DatePicker, Drawer/Dialog/Menu/Select. |
| CSS selectors with MUI classes | `web/src/app/styles.css`, tests | project class selectors | Known examples: `.MuiTablePagination-root`, `.MuiIconButton-root`, `.MuiListItemButton-root`, `.MuiTableCell-root`, `.MuiButton-root`, `.MuiInput-root`. |

## User-visible Entrypoints

- Page root: `data-testid="bank-details-page"`。
- State panels:
  - `正在加载银行明细。`
  - error message from caught API errors。
  - `规则已保存，银行明细正在刷新。` / `规则已保存，银行明细已刷新。`
  - `暂无银行流水，请先在银行流水导入页面导入。`
- Account sidebar:
  - list label `银行账户`。
  - all-account button `全部流水 <n> 条` with `aria-current` when selected。
  - account buttons like `工商银行 6386 余额 130,500.50 299 条`。
  - total balance, account count chip, missing balance chip, per-account transaction count and `余额为空` chip。
- Header / controls:
  - current title such as `全部流水`。
  - `自动标签规则` button opens a right drawer named `自动标签规则`。
  - date presets `本月`、`上月`、`近7天`、`近30天`、`今年` under label `日期快捷筛选`。
  - date range button text like `2026-01-01 - 2026-12-31` opens a date Popover。
  - custom date fields `年月筛选`、`开始日期`、`结束日期`。
- Category filter:
  - icon trigger label `标签筛选：<selected label>`。
  - menu name `银行明细标签筛选`。
  - menu items `全部 <n>`、`未分类 <n>` and hierarchical category rows such as `费用 1`、`工资 1`、`内部往来款 2`。
  - click selection keeps the menu open, updates `aria-current`, resets server page to 1 and sends category query params。
- Toolbar:
  - `导出` / `导出中` button。
  - export menu name `导出银行明细`。
  - menu items `导出全部银行` and `导出当前账户`。
  - search field placeholder and label `搜索流水`。
- Transaction table:
  - accessible name `交易流水`。
  - headers exactly: `对方户名`、`类型`、`金额`、`余额`、`用途/交易用途`、`摘要`、`备注/附言/客户附言`。
  - no visible `交易时间` or `操作` column; trade time remains inside the counterparty cell。
  - amount column keeps direction tag + amount on one aligned line and source bank/account chip below。
  - `收入` / `支出` tags, amounts and balances use tabular numeric alignment。
  - pagination text `每页行数`, range text like `1-100 / 299`, next page control label `下一页`, options `25`, `50`, `100`。
- Row type/category cell:
  - read-only auto category displays labels such as `费用 / 工资`。
  - unmatched rows can show `待分类`; needs-confirmation rows can show `待确认`。
  - primary menus: `待确认主标签` / `待分类主标签`。
  - child menus: `<主标签>候选标签` / `<主标签>可选标签`。
  - third-level menus: `<子标签>候选业务类型` / `<子标签>可选业务类型`。
  - staged selection changes the trigger label but does not call API until `保存`。
  - footer buttons `取消` and `保存`; mutation state label `保存中`。
  - manually confirmed rows show category tag plus `撤销`。
- Internal transfer tooltip:
  - tooltip named with `对应内部往来流水`。
  - rows: `时间`、`账户`、`金额`、`对方户名`。
- Auto tag rules drawer:
  - dialog name `自动标签规则`。
  - close button `关闭自动标签规则抽屉`。
  - version text `版本 <n>` and read-only suffix when applicable。
  - status switcher label `自动标签规则状态` with `可用` and `停用`。
  - toolbar actions `新增标签`, `重新应用规则`, `保存`。
  - loading text `正在读取规则`。
  - active rule table name `自动标签规则表格`。
  - active rule table headers exactly: `主标签`、`子标签`、`流水类型`、`查询项`、`包含`、`必须同时包含`、`精准命中`、`不包含字样`、`优先级`、`操作`。
  - system row remains first with priority `1` and non-editable operation `-`/dash。
  - editable fields keep accessible labels such as `<rule> 主标签`, `<rule> 子标签`, `<rule> 流水类型`, `<rule> 查询项`, `<rule> 优先级`。
  - match-field menu keeps `全选` and `清空` actions and excludes hidden `全部文本` option。
  - condition buttons keep labels like `编辑费用 / 手续费包含` and open a condition editor dialog with `取消` / `确定`。
  - archive action remains `停用 <rule>` and opens `确认停用标签` dialog with `取消` / `确认停用`。
  - archived tab displays `暂无停用标签。`, `已停用`, and `重新启用`。

## Existing Test Coverage

`web/src/test/BankDetailsPage.test.tsx` covers:

- All accounts load by default, request current-year date range, and no duplicate marketing/header title is rendered。
- Account list, total balance, selected account state, positive balance formatting and missing-balance display。
- Transaction table accessible name, column headers and lack of `交易时间` / `操作` columns。
- Chinese server pagination labels, search input, server page reset, server total and default page size。
- Pagination outside the table scroll area through CSS contract。
- Dense three-column category filter panel structure, click-only open behavior, Escape close, selected `aria-current`, category counts and server query params。
- Read-only auto category display, hierarchy labels, internal transfer tooltip and structured tooltip rows。
- Automatic tag rule drawer opens from page toolbar and triggers rule fetch。
- Saving/reapplying rules refreshes bank details, dispatches `bankAutoTagRulesUpdated`, and preserves fresh/stale/schema-mismatch row visibility behavior。
- Keep-alive inactive page pauses read-model retry。
- Manual classification, needs-confirmation classification and external turnover third-level selection flows stage choices before API calls。
- Account/date/search/category/export flows keep query params consistent。
- Workbench relation and bank detail tag setting events refetch the correct resources。

Current test migration gaps after P041:

- Tests still import and render through `MuiProviders` so the legacy runtime can render until P042-P045 remove the module MUI dependencies。
- Source-level tests now require `FinanceTable`, project menu/date primitives, `AppDrawer`, `AppDialog` and non-MUI `BankCategoryTag` implementation。
- CSS tests now require project selectors instead of `.MuiTablePagination-root`, `.MuiIconButton-root`, `.MuiListItemButton-root`, `.MuiTableCell-root`, `.MuiButton-root` and `.MuiInput-root`。
- Transaction and auto tag rule table helpers now accept either native `table` or HeroUI `grid` role while preserving accessible names and headers。
- Date custom input test now fires `input` before `blur` to exercise the same `YYYY-MM-DD` path for legacy MUI DatePicker and future native/date primitive。

`web/src/test/AutoTagRulesDrawer.test.tsx` covers:

- Drawer loads active rules as a wide table with fixed system priority first。
- Archive confirmation dialog `确认停用标签` and cancel/confirm behavior。
- Priority editing and active rule save payload。
- External turnover third labels are read-only while action type is saved。
- Match fields select-all/clear actions and hidden option exclusion。
- Label editing, condition editing, validation, unsaved draft discard, new rule save and reapply flow。
- Reapply disabled when dirty。
- CSS contract for wide, table-based, non-truncating drawer layout。

Current drawer test migration gaps after P041:

- Tests still import `MuiProviders` until P045 removes MUI Drawer/Dialog/Select/TextField/Table dependencies。
- Source-level tests now require `AutoTagRulesDrawer` to use `AppDrawer`, `AppDialog`, non-MUI table/form controls and non-MUI icons。
- Styling test now targets `.finance-table__cell` and project button classes instead of MUI table/button/input selectors。

## Migration Slices

1. `P041-phase-6-bank-details-characterization-tests`
   - Update only `BankDetailsPage.test.tsx` and `AutoTagRulesDrawer.test.tsx`。
   - Replace MUI class/source assertions with behavior/project primitive assertions for page shell, account list, table, pagination, date Popover, export menu, category filter Popper, row type Popper, right drawer and dialogs。
   - Expected-fail is acceptable before implementation because runtime still renders MUI roots。
2. `P042-phase-6-bank-details-shell-toolbar-dates`
   - Migrate page layout, account list, header controls, date presets/date Popover, export menu and search field to HeroUI/Tailwind/project primitives。
   - Preserve layout geometry, labels, server query behavior and export payloads。
3. `P043-phase-6-bank-details-transaction-table`
   - Migrate transaction table and pagination to `FinanceTable` plus project pagination。
   - Preserve table headers, dense row layout, loading/empty rows, amount alignment, direction/source chip vertical alignment, row scroll and server pagination behavior。
4. `P044-phase-6-bank-details-category-popovers`
   - Migrate `BankCategoryFilterControl`, `BankCategoryTag`, internal transfer tooltip and `TypeCell` Popper/menu surfaces。
   - Preserve click-only category filter, three-column hierarchy, staged row category save, third-level external turnover selection and tooltip structure。
5. `P045-phase-6-bank-details-auto-tag-drawer`
   - Migrate `AutoTagRulesDrawer` to `AppDrawer`, `AppDialog`, HeroUI/Tailwind/project controls and lucide icons。
   - Preserve right drawer, active/archived tabs, wide table editor, selects, condition editor dialog, archive confirmation dialog, validation and save/reapply payloads。
6. `MG-P045-phase-6-bank-details`
   - Run BankDetails and AutoTagRulesDrawer tests, table/common/platform regressions, build, BankDetails-scope MUI grep, CSS MUI selector residue grep, docs update, exact stage, commit and push。

## Execution Update

- `P040-phase-6-bank-details-discovery`: BankDetails page、BankCategoryTag、AutoTagRulesDrawer、tests、MUI inventory、user-visible entrypoints and migration slices recorded。
- `P041-phase-6-bank-details-characterization-tests`: updated `BankDetailsPage.test.tsx` and `AutoTagRulesDrawer.test.tsx` with project primitive source/CSS contracts and table/grid role-compatible helpers. Targeted test expected-failed with 47 passed and 5 failures. All 5 failures are intended red lights caused by current runtime/CSS still using MUI instead of `FinanceTable`, project pagination/category filter selectors, `AppDrawer`, `AppDialog`, non-MUI rule table styles and non-MUI BankDetails primitives。

## Risks

- This page has several overlay types; migrating everything to a single HeroUI overlay can break interaction shape. Use right drawer for the drawer, dialog for dialogs, popover/menu for old popovers/menus。
- HeroUI Table exposes different roles than native MUI Table in some contexts. Tests should assert user-observable table/grid name and headers, not MUI internals。
- MUI Select and HeroUI/native select have different portal/listbox behavior; preserve accessible labels and test with user interactions before refactor is considered done。
- MUI X DatePicker currently depends on `dayjs`; replacing it with native date/month inputs must preserve exact `YYYY-MM-DD` request values and blur/input behavior。
- `TypeCell` has staged local choice state. Do not call assignment/confirmation APIs on menu item click; only call after `保存`。
- `AutoTagRulesDrawer` payload semantics are high risk: do not alter `active_rules`, `archived_rules`, `expected_version`, `refresh_scope` or reapply endpoint behavior。
- Shared CSS currently mixes page classes with MUI selectors. Replace selectors surgically; do not remove bank layout classes that tests and users rely on。

## P041 Prompt Draft

```text
Prompt ID: P041-phase-6-bank-details-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只更新 BankDetails 和 AutoTagRulesDrawer tests，锁定银行明细页非 MUI/project primitive contract；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_bank_details.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BankDetailsPage.tsx、web/src/features/bankDetails/AutoTagRulesDrawer.tsx、web/src/features/bankDetails/BankCategoryTag.tsx、web/src/components/common/FinanceTable.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/test/BankDetailsPage.test.tsx 和 web/src/test/AutoTagRulesDrawer.test.tsx。只修改 `web/src/test/BankDetailsPage.test.tsx` 和 `web/src/test/AutoTagRulesDrawer.test.tsx`：把 source/CSS 中 MUI class assertions 改成 project primitive assertions；新增断言锁定 bank details root/account sidebar/transaction table/pagination/date Popover/export menu/category filter Popper/row type Popper/internal transfer tooltip/auto tag rules right drawer/condition dialog/archive dialog 均保留旧 accessible labels 和旧交互形态，且 migrated root 不再是 `.Mui*`。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P042 shell-toolbar-dates prompt。
```

## P042 Prompt Draft

```text
Prompt ID: P042-phase-6-bank-details-shell-toolbar-dates
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: 迁移 BankDetails 页面壳、账户列表、顶部工具栏、日期筛选、导出菜单和搜索输入；不迁移交易表格、TypeCell、BankCategoryTag 或 AutoTagRulesDrawer。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_bank_details.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BankDetailsPage.tsx、web/src/test/BankDetailsPage.test.tsx、web/src/components/common/StatePanel.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx 和 web/src/app/styles.css。只修改 `BankDetailsPage.tsx`、必要的 `styles.css` 和必要的 BankDetails test expectations：移除页面壳、账户 sidebar、header controls、date presets/date Popover、export menu/search toolbar 的 MUI layout/input/button/menu/date imports；使用 HeroUI/Tailwind/project primitives 或 native `input[type=month/date]` 保留旧布局、旧 labels、旧 query params、旧 export payload、旧 search behavior、旧 loading/empty/error feedback。不得迁移交易 table/TablePagination、TypeCell category Popper、BankCategoryTag、internal transfer tooltip、AutoTagRulesDrawer；不得修改后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run BankDetailsPage.test.tsx -t "loads all accounts|requests the current year|renders accounts|uses Chinese labels|selecting account and filters|exports all banks"`；运行完整 `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx`，P041 中与 table/category/drawer 相关 failures 可以继续 expected-fail，但 shell/toolbar/date/export failures 必须清除；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P043 transaction table prompt。
```
