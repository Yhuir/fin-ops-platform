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
