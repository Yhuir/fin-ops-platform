# Phase 6 Pending Invoices UI Migration

本文档记录 `/pending-invoices` 待找发票模块的 UI 平台迁移 discovery。它是后续 P047+ Micro-JIT prompt 的模块事实源。

## Scope

- Route: `/pending-invoices`
- Page: `web/src/pages/PendingInvoicesPage.tsx`
- Components:
  - `web/src/components/pendingInvoices/PendingInvoicesTable.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx`
  - `web/src/components/pendingInvoices/ManualInvoiceDialog.tsx`
- API/types:
  - `web/src/features/pendingInvoices/api.ts`
  - `web/src/features/pendingInvoices/types.ts`
- Tests:
  - `web/src/test/PendingInvoicesPage.test.tsx`
  - `web/src/test/PendingInvoicesApi.test.ts`

## Non-Goals

- Do not change backend, API contracts, read models, workers, mocks, permissions or business state machines.
- Do not change reconciliation workbench internals.
- Do not redesign the workflow. Old drawers remain right drawers; old dialogs remain dialogs; the four-zone table remains a table.
- Do not parallelize this module with other page modules.

## Current MUI Inventory

| File | MUI / legacy usage | Migration target |
| --- | --- | --- |
| `PendingInvoicesPage.tsx` | MUI icon `KeyboardArrowDownOutlinedIcon`; `Box`, `Button`, `LinearProgress`, `Menu`, `MenuItem`, `Stack`, `TablePagination`, `TextField`, `ToggleButton`, `ToggleButtonGroup`, `Typography`; `.MuiButton-endIcon`, `.MuiToggleButton-root` sx selectors | Page shell/native or HeroUI controls, project menu/popover, project pagination, project loading bar |
| `PendingInvoicesTable.tsx` | MUI icons `InfoOutlinedIcon`, `MoreVertOutlinedIcon`; `Box`, `Button`, `Chip`, `IconButton`, `Menu`, `MenuItem`, `Stack`, `Table`, `TableBody`, `TableCell`, `TableHead`, `TableRow`, `TableSortLabel`, `Tooltip`, `Typography`, MUI `SxProps/Theme`, `.MuiChip-label` sx selectors | `FinanceTable` or native project table, project sort buttons, project row action menu, `FinanceDirectionTag`/`FinanceStatusTag`/project tags, lucide icons, project tooltip |
| `PendingInvoiceDrawerFrame.tsx` | MUI `Drawer`, `IconButton`, `Divider`, layout primitives, close icon, `SxProps/Theme` | `AppDrawer` with right placement and close label preservation |
| `PendingInvoiceRulesDrawer.tsx` | MUI `Alert`, `Button`, `CircularProgress`, `Checkbox`, `FormControlLabel`, `Paper`, `Stack`, `Typography`, MUI selector in checkbox label sx | `AppDrawer`, project checkbox lists, project alerts/loading, project action buttons |
| `PendingInvoiceRelationDrawer.tsx` | MUI alert/loading/layout/table/button | `AppDrawer`, project metric cards, `FinanceTable`/native table for `历史支付流水` |
| `PendingInvoiceInvoicePickerDrawer.tsx` | MUI alert/button/chip/progress/paper/stack/table/pagination/text fields | `AppDrawer`, project filter inputs, project candidate table and pagination |
| `PendingInvoiceDetailDrawer.tsx` | MUI alert/loading/layout/paper plus MUI `Dialog` for OA print layout | `AppDrawer` for detail, `AppDialog` for `打印选择` dialog |
| `PendingInvoiceExportDrawer.tsx` | MUI alert/button/progress/paper/stack/table/typography | `AppDrawer`, project preview table `导出样例`, project alerts/actions |
| `ManualInvoiceDialog.tsx` | MUI `Dialog`, `DialogActions`, `DialogContent`, `DialogTitle`, `Alert`, `Button`, `Stack`, `TextField`, `Typography` | `AppDialog`, project form grid/inputs, project alerts/actions |
| `PendingInvoicesPage.test.tsx` | Existing wording says “upgraded four-zone MUI table without DataGrid”; no implementation MUI imports but assertions still tolerate current MUI shape | Convert to behavior/project primitive assertions in P047 |

## User-Visible Entrypoints

| Entrypoint | Current label / accessible hook | Must preserve |
| --- | --- | --- |
| Route/sidebar | link `待找发票`, href `/pending-invoices` | Same route and sidebar link |
| Page root | `data-testid="pending-invoices-page"` | Keep or replace only if tests are updated to equivalent root contract |
| Direction segmented control | `待找发票流水范围`; buttons `全部 <n>`, `支出 <n>`, `收入 <n>` | Same labels, counts, state reset behavior |
| Status filter menu | button `筛选发票获取状态：<label>`; menu items depend on direction | Same trigger text, menu semantics and options |
| Rules buttons | `支出待找发票规则设置`, `收入待找发票规则设置` | Same positions in toolbar and same right drawer |
| Export | `筛选内容导出`; disabled when read model not fresh | Same disabled behavior and export drawer |
| Search | input label `搜索流水`, placeholder `搜索流水` | Same query/page reset behavior |
| Refresh | `刷新` | Same manual reload behavior |
| Loading | progress `待找发票加载中` | Same loading status |
| Pagination | `每页行数`, displayed rows `<from>-<to> / <count>`, page size `[25, 50, 100]` | Same server page/pageSize behavior |

## Tables

### Main Four-Zone Table

- Accessible name: `待找发票四区表`
- Shell test id: `pending-invoices-table-shell`
- Current table groups:
  - Bank group: `支出流水` / `收入流水` / `流水`
  - Status group: `发票获取状态`
  - Invoice group: `进项发票` / `销项发票` / `发票`
  - OA group: `OA`
- Column headers:
  - `对方 / 时间`
  - `金额 / 银行账户`
  - `摘要 / 凭证`
  - status filter control column
  - `发票号码 / 开票日期`
  - `销方 / 识别号`
  - `金额 / 支付差额`
  - `申请人 / 类型`
  - `项目 / 详情`
- Must preserve:
  - Sticky group/header behavior.
  - Dense four-zone information layout.
  - Row names including counterparty text.
  - Status chip labels such as `已支付待开票`, `无需开票`, `未支付完已开票`.
  - Suppressed long reason text in rows; tests currently assert reason text is not shown in main table.
  - Row action menu button label `<counterparty> 发票获取操作` and menu label `<counterparty> 发票获取操作菜单`.
  - Menu items `选择发票`, `补票`, `查看支付明细`, income status items `无需开票`, `现金收入`.
  - Object detail buttons such as `发票详情 DIG-001` and `OA详情 李四`.

### Drawer / Dialog Tables

| Surface | Accessible name | Notes |
| --- | --- | --- |
| Relation drawer | `历史支付流水` | Preserve empty text `暂无历史支付。`, payment metrics and `选择发票` action |
| Invoice picker drawer | `发票候选` | Preserve filters, candidate rows, preview and confirm flow |
| Export drawer | `导出样例` | Preserve empty text `暂无样例。`, preview columns and sample rows |

## Drawers And Dialogs

All existing right drawers must remain right drawers after migration.

| Surface | Current title / label | Shape | Must preserve |
| --- | --- | --- | --- |
| Shared drawer frame | `PendingInvoiceDrawerFrame` with MUI Drawer | right drawer | Close labels, title/subtitle/action/body regions |
| Rules drawer | `支出待找发票规则设置`, `收入待找发票规则设置`; close `关闭规则抽屉` | right drawer | Version subtitle, `保存规则`, readonly permission alert, stale conflict message, unsaved selection merge on tag refresh |
| Relation drawer | `关系与支付明细`; close `关闭关系明细抽屉` | right drawer | Metrics `已付合计`/`发票合计`/`待付金额`/`支付差额`, `选择发票`, history table |
| Invoice picker drawer | `选择已有进项发票`; close via frame | right drawer | Filters `关键词`/`销方`/date range/amount range, `搜索`, `预览关联 <invoice>`, `确认建立关系` |
| Detail drawer | detail heading e.g. `DIG-001`; close `关闭详情抽屉` | right drawer | Field sections like `发票字段`, OA unavailable detail behavior |
| OA print detail | `打印选择` | dialog | `打印下载`, field sections such as `申请人`, `项目负责人审核`, close button currently named `关闭详情抽屉` |
| Export drawer | `导出预览` | right drawer | `预计导出 <n> 行`, `下载导出`, success `已生成 pending-invoices.xlsx` |
| Manual invoice | `手工补录发票` | dialog | Form labels, `预览`, `确认写入`, duplicate/preview feedback |

## Loading / Empty / Error / Stale / Permission

- Page read model:
  - `readModelStatus === "refreshing"` displays `数据刷新中` and disables export.
  - Non-fresh/non-refreshing status displays `读模型 <status>，写入和导出已暂停`.
  - Error displays the error text in compact status area.
- Main table empty row: `当前条件下没有待找发票流水。`
- Rules drawer:
  - Loading: `正在加载待找发票规则`
  - Save success: `规则已保存，相关数据正在刷新。` or `规则已保存。`
  - Stale conflict: `规则已被其他人更新。请刷新规则后再保存，当前勾选内容已保留。`
  - Tag refresh with unsaved draft: `银行明细自动标签已更新，已刷新标签名称并保留未保存选择。`
  - Permission info: `当前账号只能查看规则，不能保存。`
- Relation/detail/picker/export drawers have loading and error states using MUI alert/progress today; P047 should lock semantic equivalents before implementation.

## Existing Test Coverage

`web/src/test/PendingInvoicesPage.test.tsx` currently covers:

- Route/sidebar link and root render.
- Main four-zone table, column headers, no DataGrid, table shell scroll behavior.
- Direction toggle and direction-specific status filters.
- Row action menu collapse behavior: actions are under menu, not inline.
- Relation drawer open/close and metrics.
- Invoice detail drawer and OA print dialog.
- Rules drawer save, stale conflict, mutual exclusion, tag refresh preserving unsaved selections.
- Export drawer preview/download.
- Candidate OA detail unavailable behavior.
- Full business flow: rule closure filtering, attach existing invoice, manual invoice preview/confirm.
- Read model refreshing disables export but does not disable row action menu.

## API / Contract Boundaries

Do not change:

- `fetchPendingInvoiceRows` query shape: direction, filter, keyword, page, pageSize, sortField, sortDirection.
- `savePendingInvoiceRules` payload semantics, version conflict behavior and read model status.
- `fetchPendingInvoiceRelationDetail`, `fetchPendingInvoiceObjectDetail`, `fetchPendingInvoiceCandidates`, attach preview/confirm and manual invoice preview/confirm contracts.
- Domain events emitted after manual invoice and existing invoice attach.
- Page activation/tag refresh behavior and scroll session key `pending-invoices-table`.

## Migration Slices

1. `P047-phase-6-pending-invoices-characterization-tests`
   - Update only pending invoices tests.
   - Convert current “MUI table without DataGrid” assertions to project primitive contracts.
   - Add source-level no-MUI expectations for each future slice without requiring implementation yet.
   - Expected-fail acceptable before implementation.
2. `P048-phase-6-pending-invoices-page-shell-toolbar`
   - Migrate page shell, direction segmented control, status filter menu, toolbar buttons/search/loading and pagination.
   - Do not migrate table internals or drawers/dialogs.
3. `P049-phase-6-pending-invoices-four-zone-table`
   - Migrate `PendingInvoicesTable` to `FinanceTable`/project native table, row action menu, tags, tooltip/sort controls.
   - Preserve table headers, row action menu, object detail buttons and dense row layout.
4. `P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers`
   - Migrate shared drawer frame, relation drawer, detail drawer and export drawer.
   - Preserve right drawer shape and OA print dialog.
5. `P051-phase-6-pending-invoices-rules-drawer`
   - Migrate rules drawer and checkbox tree.
   - Preserve conflict handling, mutual exclusion and tag refresh merge behavior.
6. `P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog`
   - Migrate invoice picker drawer and manual invoice dialog.
   - Preserve candidate search/preview/confirm and manual invoice preview/confirm flows.
7. `MG-P052-phase-6-pending-invoices`
   - Run PendingInvoices tests, common/table/platform regressions, build, pending-invoices MUI grep, CSS residue grep, docs update, exact stage, commit and push.

## Risks

- `PendingInvoicesTable` is information dense and currently hand-built with sticky MUI table groups. Preserve the four-zone table geometry before changing visual density.
- Row action menu must remain collapsed; tests require no inline `选择发票` / `补票` buttons in rows.
- Rules drawer has business-sensitive mutual exclusion and stale merge behavior. Do not migrate it in the same slice as the table.
- Shared `PendingInvoiceDrawerFrame` is used by multiple drawers; migrate it only when tests for every dependent drawer are already characterizing right-drawer behavior.
- OA print `打印选择` is a dialog inside the detail flow. Do not convert it into a drawer.
- Manual invoice dialog has many form labels and preview/confirm API semantics. Keep it as a dialog and preserve labels exactly.

## P047 Prompt Draft

```text
Prompt ID: P047-phase-6-pending-invoices-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只更新 pending invoices tests，锁定 `/pending-invoices` 非 MUI/project primitive contract；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/PendingInvoicesPage.tsx、web/src/components/pendingInvoices/*.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/test/PendingInvoicesPage.test.tsx。只修改 `web/src/test/PendingInvoicesPage.test.tsx`：把当前 “upgraded four-zone MUI table without DataGrid” 等 MUI wording/class assertions 改成 project primitive assertions；新增 source-level contracts 锁定 page shell/toolbar/status menu/pagination、main four-zone table、row action menu、shared right drawer frame、rules/relation/detail/export/invoice-picker drawers、OA print dialog 和 manual invoice dialog 未来均不再依赖 `@mui/*`；新增行为断言确保旧右侧抽屉仍是右侧抽屉、旧 dialog 仍是 dialog、主表仍是 `待找发票四区表` table、`发票候选`/`历史支付流水`/`导出样例` 表格语义保留、`打印选择` 和 `手工补录发票` dialog 名称保留。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P048 page shell toolbar prompt。
```

## Execution Update: P047 Characterization Tests

- Status: verified as expected-fail.
- Files changed: `web/src/test/PendingInvoicesPage.test.tsx`.
- Runtime implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Test changes:
  - Added a source-level project primitive contract for all pending invoice page/table/drawer/dialog files.
  - Reworded the main table test away from old MUI terminology.
  - Added behavior assertions for `历史支付流水`, `发票候选` and `导出样例` table semantics.
  - Existing tests continue to cover `打印选择` and `手工补录发票` as dialogs.
- Verification:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail, 14 passed and 1 failed.
  - Expected failure: `targets project primitives for page shell, tables, drawers, and dialogs`.
  - Failure lists all 9 pending invoice runtime files still importing `@mui/*` and missing required project primitive targets.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed.

## Current Expected Failures After P047

The single source-level failure is expected until P048-P052 complete:

- `src/pages/PendingInvoicesPage.tsx`: still imports MUI shell/toolbar/menu/pagination/search controls; P048 owns this.
- `src/components/pendingInvoices/PendingInvoicesTable.tsx`: still imports MUI table/menu/tag/tooltip controls; P049 owns this.
- `src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx`: still imports MUI Drawer; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx`: still imports MUI alert/loading/table/button/layout controls; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx`: still imports MUI alert/loading/dialog/button/layout controls; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx`: still imports MUI alert/loading/table/button/layout controls; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`: still imports MUI alert/loading/checkbox/button/layout controls; P051 owns this.
- `src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`: still imports MUI alert/loading/table/pagination/button/input controls; P052 owns this.
- `src/components/pendingInvoices/ManualInvoiceDialog.tsx`: still imports MUI Dialog/form controls; P052 owns this.

## P048 Prompt Draft

```text
Prompt ID: P048-phase-6-pending-invoices-page-shell-toolbar
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/pending-invoices` page shell/toolbar/pagination only. Do not migrate `PendingInvoicesTable` internals or any pending invoice drawer/dialog component.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/PendingInvoicesPage.tsx、web/src/test/PendingInvoicesPage.test.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/components/common/StatePanel.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/PendingInvoicesPage.tsx`、必要 `web/src/app/styles.css` 和必要的 `web/src/test/PendingInvoicesPage.test.tsx` expectation：移除 page shell/toolbar/status menu/pagination/search/loading 的 MUI imports/usages，包括 `KeyboardArrowDownOutlinedIcon`、`Box`、`Button`、`LinearProgress`、`Menu`、`MenuItem`、`Stack`、`TablePagination`、`TextField`、`ToggleButton`、`ToggleButtonGroup`、`Typography` 以及 `.MuiButton-endIcon`、`.MuiToggleButton-root` sx selector。使用 PageScaffold/PageToolbar、native/project buttons、project menu/listbox/popover、native search input、project pagination/loading/status markup 或 HeroUI primitives，保留旧 `data-testid="pending-invoices-page"`、route/sidebar link、direction counts/buttons `全部 <n>`/`支出 <n>`/`收入 <n>`、status menu trigger `筛选发票获取状态：<label>` 和 options、search `搜索流水`、refresh `刷新`、rules/export buttons、non-fresh read model disables export、loading `待找发票加载中`、server page/pageSize/total behavior and pagination labels。不得修改 pending invoices API/mock/read model/worker/backend/关联台；不得改 `web/src/components/pendingInvoices/*`，除非测试证明 page-only migration needs a prop-compatible no-op adjustment and the prompt must record why。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract|shows income rule-group filters|keeps row status actions available|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，P049-P052 table/drawer/dialog source contract failures 可以继续 expected-fail，但 P048 page shell/toolbar/pagination targets and page-level MUI import failure must clear；运行 `cd web && npm run build`；运行 page shell MUI grep：`if rg -n '@mui/|MuiButton-endIcon|MuiToggleButton-root|KeyboardArrowDownOutlinedIcon|TablePagination|ToggleButton|ToggleButtonGroup' web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P049 four-zone table prompt。
```

## Execution Update: P048 Page Shell / Toolbar

- Status: verified as expected-fail.
- Files changed:
  - `web/src/pages/PendingInvoicesPage.tsx`
  - `web/src/app/styles.css`
- Runtime implementation changed: page shell/toolbar/pagination only.
- Pending invoice table/drawer/dialog components changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - `PendingInvoicesPage.tsx` now uses `PageScaffold` and `PageToolbar`.
  - Direction controls are native segmented buttons with `aria-label="待找发票流水范围"`.
  - Status filter trigger/menu are native project controls with the old accessible trigger name `筛选发票获取状态：<label>`.
  - Toolbar rules/export/search/refresh controls and pagination no longer use MUI.
  - Page loading indicator keeps `aria-label="待找发票加载中"`.
- Verification:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract|shows income rule-group filters|keeps row status actions available|targets project primitives"`: expected-fail. Page shell/toolbar source target cleared.
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail, 14 passed and 1 failed.
  - Remaining failure: `targets project primitives for page shell, tables, drawers, and dialogs`.
  - The failure now lists only 8 pending invoice table/drawer/dialog files; `src/pages/PendingInvoicesPage.tsx` no longer appears.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|MuiButton-endIcon|MuiToggleButton-root|KeyboardArrowDownOutlinedIcon|TablePagination|ToggleButton|ToggleButtonGroup' web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.

## Current Expected Failures After P048

The single source-level failure is expected until P049-P052 complete:

- `src/components/pendingInvoices/PendingInvoicesTable.tsx`: still imports MUI table/menu/tag/tooltip controls; P049 owns this.
- `src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx`: still imports MUI Drawer; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx`: still imports MUI alert/loading/table/button/layout controls; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx`: still imports MUI alert/loading/dialog/button/layout controls; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx`: still imports MUI alert/loading/table/button/layout controls; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`: still imports MUI alert/loading/checkbox/button/layout controls; P051 owns this.
- `src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`: still imports MUI alert/loading/table/pagination/button/input controls; P052 owns this.
- `src/components/pendingInvoices/ManualInvoiceDialog.tsx`: still imports MUI Dialog/form controls; P052 owns this.

## P049 Prompt Draft

```text
Prompt ID: P049-phase-6-pending-invoices-four-zone-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: PendingInvoices main four-zone table only. Do not migrate drawer frame, drawers, rules drawer, invoice picker drawer or manual invoice dialog.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、web/src/components/pendingInvoices/PendingInvoicesTable.tsx、web/src/pages/PendingInvoicesPage.tsx、web/src/components/common/FinanceTable.tsx、web/src/test/PendingInvoicesPage.test.tsx 和 web/src/app/styles.css。只修改 `PendingInvoicesTable.tsx`、必要 `styles.css` 和必要的 `PendingInvoicesPage.test.tsx` expectations：移除主四区表的 MUI imports/usages，包括 `InfoOutlinedIcon`、`MoreVertOutlinedIcon`、`Box`、`Button`、`Chip`、`IconButton`、`Menu`、`MenuItem`、`Stack`、`Table`、`TableBody`、`TableCell`、`TableHead`、`TableRow`、`TableSortLabel`、`Tooltip`、`Typography`、`SxProps`、`Theme` 和 `.MuiChip-label` selector。使用 FinanceTable/project native table markup、project buttons/menu/tooltip/tag classes 或 HeroUI primitives，保留 accessible table name `待找发票四区表`、`pending-invoices-table-shell` scroll container、group headers `支出流水/收入流水/流水`、`发票获取状态`、`进项发票/销项发票/发票`、`OA`、所有 subheaders、sticky header behavior、dense four-zone row layout、loading row `正在加载待找发票。`、empty row `当前条件下没有待找发票流水。`、row action button `<counterparty> 发票获取操作`、menu items `选择发票`/`补票`/`查看支付明细`/income status actions、object detail buttons such as `发票详情 DIG-001` and `OA详情 李四`、direction/status tags、amount/payment difference tabular numeric alignment and server sorting behavior。不得修改 page shell、pending invoice API/mock/read model/worker/backend/关联台；不得改 any drawer/dialog component。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract|shows income rule-group filters|keeps row status actions available|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，P050-P052 drawer/dialog source contract failures 可以继续 expected-fail，但 `PendingInvoicesTable.tsx` must disappear from the source-level failure list；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 table MUI grep：`if rg -n '@mui/|MuiChip-label|SxProps|TableSortLabel|MoreVertOutlinedIcon|InfoOutlinedIcon' web/src/components/pendingInvoices/PendingInvoicesTable.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P050 drawer frame/simple drawers prompt。
```

## Execution Update: P049 Four-Zone Table

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/pendingInvoices/PendingInvoicesTable.tsx`
  - `web/src/app/styles.css`
  - `web/src/test/PendingInvoicesPage.test.tsx`
- Runtime implementation changed: main four-zone table only.
- Drawer/dialog components changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - `PendingInvoicesTable.tsx` no longer imports MUI table, sort, menu, tag, tooltip, icon or layout primitives.
  - The main table is now native/project markup with accessible table name `待找发票四区表` and `pending-invoices-table-shell`.
  - Row content uses `AmountCell`, `FinanceDirectionTag`, `FinanceStatusTag`, `EmptyValue`, lucide icons and pending invoice CSS classes.
  - Row action menu remains collapsed under `<counterparty> 发票获取操作` and preserves `选择发票`/`补票`/`查看支付明细`/income status actions.
  - Object detail actions preserve labels such as `发票详情 DIG-001` and `OA详情 李四`.
  - Table shell overflow/sticky header assertions were moved to CSS contract checks to avoid inline style requirements.
- Verification:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract|shows income rule-group filters|keeps row status actions available|targets project primitives"`: expected-fail. Main table behavior tests passed; only P050-P052 source-level failure remains.
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail, 14 passed and 1 failed.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|MuiChip-label|SxProps|TableSortLabel|MoreVertOutlinedIcon|InfoOutlinedIcon' web/src/components/pendingInvoices/PendingInvoicesTable.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.

## Current Expected Failures After P049

The single source-level failure is expected until P050-P052 complete:

- `src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx`: still imports MUI Drawer; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx`: still imports MUI alert/loading/table/button/layout controls; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx`: still imports MUI alert/loading/dialog/button/layout controls; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx`: still imports MUI alert/loading/table/button/layout controls; P050 owns this.
- `src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`: still imports MUI alert/loading/checkbox/button/layout controls; P051 owns this.
- `src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`: still imports MUI alert/loading/table/pagination/button/input controls; P052 owns this.
- `src/components/pendingInvoices/ManualInvoiceDialog.tsx`: still imports MUI Dialog/form controls; P052 owns this.

## P050 Prompt Draft

```text
Prompt ID: P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: PendingInvoices shared drawer frame plus simple drawers only: `PendingInvoiceDrawerFrame.tsx`, `PendingInvoiceRelationDrawer.tsx`, `PendingInvoiceDetailDrawer.tsx`, `PendingInvoiceExportDrawer.tsx`, necessary `web/src/app/styles.css` and necessary `PendingInvoicesPage.test.tsx` expectations. Do not migrate `PendingInvoiceRulesDrawer.tsx`, `PendingInvoiceInvoicePickerDrawer.tsx` or `ManualInvoiceDialog.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/FinanceTable.tsx、web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx、web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx、web/src/test/PendingInvoicesPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：用 `AppDrawer` 替换 shared MUI Drawer frame，保留右侧抽屉形态、title/subtitle/action/body 区域和 close labels；迁移 relation drawer，保留 `关系与支付明细`、metrics `已付合计`/`发票合计`/`待付金额`/`支付差额`、`选择发票` 和 `历史支付流水` table；迁移 detail drawer，保留 detail heading 如 `DIG-001`、发票字段、OA unavailable detail behavior，并用 `AppDialog` 保留 `打印选择` dialog 和 `打印下载`；迁移 export drawer，保留 `导出预览`、`预计导出 <n> 行`、`下载导出`、`已生成 pending-invoices.xlsx` 和 `导出样例` table。移除本 scope 内 MUI imports/usages，包括 MUI Drawer/Dialog/Alert/Button/CircularProgress/Paper/Stack/Table/Typography/Divider/IconButton 等。不得修改 pending invoice API/mock/read model/worker/backend/关联台；不得修改 rules drawer、invoice picker drawer 或 manual invoice dialog。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks|renders project four-zone table contract|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，P051-P052 rules/invoice-picker/manual-dialog source contract failures 可以继续 expected-fail，但 P050 scope files must disappear from the source-level failure list；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 P050 MUI grep：`if rg -n '@mui/' web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P051 rules drawer prompt。
```

## Execution Update: P050 Drawer Frame And Simple Drawers

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/common/AppDrawer.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx`
  - `web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx`
  - `web/src/app/styles.css`
- Runtime implementation changed: shared drawer frame, relation drawer, detail drawer, export drawer and OA print dialog only.
- Rules drawer/invoice picker/manual dialog changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - `AppDrawer` now supports optional `subtitle`.
  - `PendingInvoiceDrawerFrame` now wraps `AppDrawer` and keeps the old frame props for pending invoice drawers.
  - Relation drawer uses project metrics, status messages and native `历史支付流水` table.
  - Detail drawer uses project field panels and `AppDialog` for OA `打印选择`.
  - Export drawer uses project status messages and native `导出样例` table.
- Verification:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks|renders project four-zone table contract|targets project primitives"`: expected-fail. P050 behavior tests passed; only P051-P052 source-level failure remains.
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail, 14 passed and 1 failed.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/' web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.

## Current Expected Failures After P050

The single source-level failure is expected until P051-P052 complete:

- `src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`: still imports MUI alert/loading/checkbox/button/layout controls; P051 owns this.
- `src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`: still imports MUI alert/loading/table/pagination/button/input controls; P052 owns this.
- `src/components/pendingInvoices/ManualInvoiceDialog.tsx`: still imports MUI Dialog/form controls and lacks `AppDialog`; P052 owns this.

## P051 Prompt Draft

```text
Prompt ID: P051-phase-6-pending-invoices-rules-drawer
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: PendingInvoices rules drawer only: `web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`, necessary `web/src/app/styles.css` and necessary `web/src/test/PendingInvoicesPage.test.tsx` expectations. Do not migrate `PendingInvoiceInvoicePickerDrawer.tsx` or `ManualInvoiceDialog.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx、web/src/test/PendingInvoicesPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 rules drawer 的 MUI imports/usages，包括 `Alert`、`Button`、`CircularProgress`、`Checkbox`、`FormControlLabel`、`Paper`、`Stack`、`Typography`、`Box` 和 checkbox label sx selectors。使用 existing `PendingInvoiceDrawerFrame` right drawer、native/project buttons、native checkboxes、project status messages 和 project rule block CSS。必须保留 `支出待找发票规则设置`/`收入待找发票规则设置` heading、`关闭规则抽屉`、subtitle `版本 <n>`、`保存规则`、loading label `正在加载待找发票规则`、readonly permission alert `当前账号只能查看规则，不能保存。`、save success `规则已保存，相关数据正在刷新。`/`规则已保存。`、stale conflict `规则已被其他人更新。请刷新规则后再保存，当前勾选内容已保留。`、tag refresh notices、checkbox group names such as `需要开票`/`无需开票`/`现金收入`、mutual exclusion behavior and tag refresh merge behavior。不得修改 pending invoice API/mock/read model/worker/backend/关联台；不得修改 invoice picker drawer 或 manual invoice dialog。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks|keeps pending invoice rule draft|preserves unsaved rule selections|shows income rule-group filters|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，P052 invoice-picker/manual-dialog source contract failures 可以继续 expected-fail，但 `PendingInvoiceRulesDrawer.tsx` must disappear from the source-level failure list；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 rules MUI grep：`if rg -n '@mui/|Mui[A-Z]|FormControlLabel|CircularProgress|Checkbox' web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P052 invoice picker/manual dialog prompt。
```

## Execution Update: P051 Rules Drawer

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`
  - `web/src/app/styles.css`
- Runtime implementation changed: rules drawer only.
- Invoice picker/manual dialog changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - Rules drawer now uses existing `PendingInvoiceDrawerFrame`, native/project buttons, native checkboxes, project status messages and rule block CSS.
  - Preserved headings, `关闭规则抽屉`, `保存规则`, version subtitle, loading label, readonly permission notice, save success/stale conflict/tag refresh notices and mutual exclusion logic.
  - Added rules grid, rule block, checkbox and readonly tag styles.
- Verification:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks|keeps pending invoice rule draft|preserves unsaved rule selections|shows income rule-group filters|targets project primitives"`: expected-fail. P051 behavior tests passed; only P052 source-level failure remains.
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: expected-fail, 14 passed and 1 failed.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]|FormControlLabel|CircularProgress|Checkbox' web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.

## Current Expected Failures After P051

The single source-level failure is expected until P052 completes:

- `src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`: still imports MUI alert/loading/table/pagination/button/input controls; P052 owns this.
- `src/components/pendingInvoices/ManualInvoiceDialog.tsx`: still imports MUI Dialog/form controls and lacks `AppDialog`; P052 owns this.

## P052 Prompt Draft

```text
Prompt ID: P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: Final pending invoices UI migration slice: `web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`, `web/src/components/pendingInvoices/ManualInvoiceDialog.tsx`, necessary `web/src/app/styles.css` and necessary `web/src/test/PendingInvoicesPage.test.tsx` expectations. Do not modify backend, API contracts, read models, workers, mocks or reconciliation workbench internals.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、web/src/components/common/AppDialog.tsx、web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx、web/src/components/pendingInvoices/ManualInvoiceDialog.tsx、web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx、web/src/test/PendingInvoicesPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：迁移 invoice picker right drawer，移除 MUI Alert/Button/Chip/CircularProgress/Paper/Stack/Table/TablePagination/TextField/Typography，使用 existing `PendingInvoiceDrawerFrame`、native/project form controls、project status messages、native `发票候选` table、project pagination/buttons/status tags；必须保留 filters `关键词`/`销方`/`开票开始`/`开票结束`/`最小金额`/`最大金额`、`搜索`、candidate rows、status labels `可关联`/`已关联本流水`/`存在冲突`、`预览关联 <invoice>`、preview message、`确认建立关系` 和 server page/pageSize behavior。迁移 `ManualInvoiceDialog.tsx` 到 `AppDialog` 和 native/project inputs/buttons/status messages，保留 dialog name `手工补录发票`、row context text、所有 form labels、`预览`、`确认写入`、duplicate/preview feedback、disabled/busy behavior and confirm flow。不得修改 pending invoice API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens invoice picker from status column|manual invoice action still previews before confirm|targets project primitives"`；运行完整 `cd web && npx vitest run PendingInvoicesPage.test.tsx`，source-level project primitive contract must pass fully；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 pending invoices MUI grep：`if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|TablePagination|TextField|Dialog' web/src/components/pendingInvoices web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 `MG-P052-phase-6-pending-invoices` cumulative MG prompt。
```

## Execution Update: P052 Invoice Picker And Manual Dialog

- Status: verified.
- Files changed:
  - `web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx`
  - `web/src/components/pendingInvoices/ManualInvoiceDialog.tsx`
  - `web/src/app/styles.css`
- Runtime implementation changed: invoice picker drawer and manual invoice dialog only.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - Invoice picker now uses existing `PendingInvoiceDrawerFrame`, native/project form controls, project status messages, native `发票候选` table, project pagination/buttons/status tags.
  - Manual invoice now uses `AppDialog`, native/project inputs, project buttons and status messages.
  - Preserved candidate search/preview/confirm and manual invoice preview/confirm flows.
- Verification:
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens invoice picker from status column|manual invoice action still previews before confirm|targets project primitives"`: passed, 3 focused tests passed.
  - `cd web && npx vitest run PendingInvoicesPage.test.tsx`: passed, 15 tests passed.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|TablePagination|TextField' web/src/components/pendingInvoices web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.

## Current Expected Failures After P052

- None for `PendingInvoicesPage.test.tsx`.
- Pending invoices page/components scoped source-level project primitive contract now passes fully.

## MG-P052 Prompt Draft

```text
Prompt ID: MG-P052-phase-6-pending-invoices
Phase: phase_6_page_batches
Type: cumulative MG
Scope: PendingInvoices module P046-P052 only. Confirm all pending invoice migration slices are implemented and verified; commit/push only the exact PendingInvoices MG files.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_pending_invoices.md、docs/refactor-ui/table_layout_system.md、当前 git status 和当前 diff。检查当前分支必须是 `refactor-ui`。确认 untracked files、diff scope、测试结果和文档状态；确认 `cd web && npx vitest run PendingInvoicesPage.test.tsx`、`cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`、`cd web && npm run build` 已通过；确认 pending invoices MUI/DataGrid residue grep 已通过：`if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|TablePagination|TextField' web/src/components/pendingInvoices web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi`。只允许精确 `git add docs/refactor-ui/refactor_ui_state.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/modules/phase_6_pending_invoices.md web/src/app/styles.css web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx web/src/components/pendingInvoices/ManualInvoiceDialog.tsx`；如果当前 diff 还包含本模块此前未提交的 P052 scope 文件，必须逐个精确列出；禁止 `git add .` 或 `git add -A`。commit message 使用 `feat: complete pending invoices ui migration` 或更准确的 PendingInvoices module message。push 到 `origin refactor-ui`。完成后更新 state/prompt/module docs 的 MG execution notes、verification、Push Log，标记 MG verified，并从 `refactor-ui` 分支继续生成下一条 Micro-JIT prompt。
```
