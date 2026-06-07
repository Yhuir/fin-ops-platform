# Phase 6 Input Invoice Usage UI Migration

本文档记录 `/input-invoice-usage` 进项发票使用情况模块的 UI 平台迁移 discovery。它是后续 P054+ Micro-JIT prompt 的模块事实源。

## Scope

- Route: `/input-invoice-usage`
- Page: `web/src/pages/InputInvoiceUsagePage.tsx`
- Components:
  - `web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx`
  - `web/src/components/inputInvoiceUsage/ExpandableCellText.tsx`
  - `web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx`
  - `web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx`
  - `web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx`
  - `web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx`
  - `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`
- Shared consumer:
  - `web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx` imports `InputInvoiceUsageFilterMenu`; filter menu migration must remain compatible with this existing caller.
- API/types:
  - `web/src/features/inputInvoiceUsage/api.ts`
  - `web/src/features/inputInvoiceUsage/types.ts`
- Tests:
  - `web/src/test/InputInvoiceUsagePage.test.tsx`
  - `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`

## Non-Goals

- Do not change backend, API contracts, read models, workers, mocks, permissions or business state machines.
- Do not change reconciliation workbench internals.
- Do not redesign the workflow. Existing right drawers remain right drawers; no drawer becomes a dialog, inline panel or route.
- Do not add new user-visible table filters to `/input-invoice-usage` just because `InputInvoiceUsageFilterMenu` exists. It is currently covered as a component and used by `OaPendingPaymentsTable`, not wired into the input invoice usage page table.
- Do not parallelize this module with other page modules.

## Current MUI Inventory

| File | MUI / legacy usage | Migration target |
| --- | --- | --- |
| `InputInvoiceUsagePage.tsx` | MUI icons `FileDownloadOutlinedIcon`, `RefreshOutlinedIcon`; `Alert`, `Box`, `Button`, `Skeleton`, `Stack`, `TextField` | `PageScaffold` remains, toolbar/search/loading/status use project/HeroUI/native controls and lucide icons |
| `InputInvoiceUsageTable.tsx` | MUI icon `InfoOutlinedIcon`; `Box`, `Button`, `Chip`, `IconButton`, `Paper`, `Stack`, `Table`, `TableBody`, `TableCell`, `TableContainer`, `TableHead`, `TablePagination`, `TableRow`, `Tooltip`, `Typography`; `.MuiChip-label`, `.MuiTablePagination-*` selectors | `FinanceTable`/project dense table, project tags/buttons/tooltips, project pagination |
| `ExpandableCellText.tsx` | MUI icons `ExpandLessOutlinedIcon`, `ExpandMoreOutlinedIcon`; `Box`, `IconButton`, `Stack`, `Tooltip`, `Typography` | Shared/project expandable cell text with lucide chevrons and project tooltip/button styling |
| `InputInvoiceUsageFilterMenu.tsx` | MUI icons `ArrowDownwardOutlinedIcon`, `ArrowUpwardOutlinedIcon`, `FilterListOutlinedIcon`; `Button`, `Checkbox`, `Divider`, `ListItemIcon`, `ListItemText`, `Menu`, `MenuItem`, `Radio`, `Stack`, `Typography`; `.MuiButton-startIcon` selector | Project popover/menu preserving `menuitemcheckbox` and `menuitemradio`; must keep prop compatibility for `OaPendingPaymentsTable` |
| `InputInvoiceUsageDetailDrawer.tsx` | MUI icon `CloseOutlinedIcon`; `Alert`, `Box`, `CircularProgress`, `Divider`, `Drawer`, `IconButton`, `Paper`, `Stack`, `Typography` | `AppDrawer`, project section cards/status messages/loading |
| `InputInvoiceUsageExportDrawer.tsx` | MUI icon `CloseOutlinedIcon`; `Alert`, `Box`, `Button`, `CircularProgress`, `Divider`, `Drawer`, `IconButton`, `Paper`, `Stack`, `Table`, `TableBody`, `TableCell`, `TableHead`, `TableRow`, `Typography` | `AppDrawer`, project preview card, project sample table, project actions |
| `PaymentStatusRulesDrawer.tsx` | MUI icon `CloseOutlinedIcon`; `Alert`, `Box`, `Button`, `Chip`, `CircularProgress`, `Divider`, `Drawer`, `IconButton`, `Paper`, `Stack`, `Table`, `TableBody`, `TableCell`, `TableContainer`, `TableHead`, `TableRow`, `TextField`, `Typography` | `AppDrawer`, project rules table, project form inputs/tags/status messages/actions |
| `OaReverseWorkspaceDrawer.tsx` | MUI icon `CloseOutlinedIcon`; `Alert`, `Box`, `Button`, `Checkbox`, `Chip`, `CircularProgress`, `Divider`, `Drawer`, `IconButton`, `MenuItem`, `Paper`, `Stack`, `Table`, `TableBody`, `TableCell`, `TableContainer`, `TableHead`, `TableRow`, `TextField`, `Typography` | `AppDrawer`, project workspace panels, project candidate table, project selection controls/actions |
| `InputInvoiceUsagePage.test.tsx` | Test wording says `dense MUI Table layout without DataGrid`; asserts `.MuiDataGrid-root` absence and `.MuiChip-root` date chips | Convert to behavior/project primitive/source contracts in P054 |
| `InputInvoiceUsageFiltersAndDrawers.test.tsx` | Mostly behavior/aria tests; imports MUI-backed components under test | Add source-level contracts and keep behavior assertions |

## User-Visible Entrypoints

| Entrypoint | Current label / accessible hook | Must preserve |
| --- | --- | --- |
| Route/sidebar | link `进项发票使用情况`, href `/input-invoice-usage` | Same route and sidebar link |
| Page root | `data-testid="input-invoice-usage-page"` | Keep root contract |
| Page title | heading `进项发票使用情况` | Same heading and page purpose |
| Description | `以进项发票为主对象反查支付状态、OA 和银行流水。` | Preserve unless copy docs are explicitly updated |
| OA reverse workflow | button `以发票反提 OA` | Same toolbar position and right drawer |
| Rules workflow | button `发票与支付状态规则设置` | Same toolbar position and right drawer |
| Export workflow | button `筛选内容导出` | Same toolbar position and right drawer |
| Refresh | button `刷新`; disabled while refreshing | Same manual reload behavior |
| Search | input label `关键字`; submit button `查询`; Enter submits | Same page reset and keyword trim behavior |
| Loading | region label `进项发票使用情况加载中` | Same loading semantic contract |
| Empty | page empty state `当前条件下暂无记录。`; table empty row `当前条件下没有进项发票使用记录。` | Same copy and placement intent |
| Error | API error text in page status area | Same visible failure feedback |
| Pagination | table pagination labels `每页行数`, displayed rows `<from>-<to> / <count>`, page size `[20, 50, 100]` | Same server page/pageSize behavior |

## Tables

### Main Dense Table

- Accessible name: `进项发票使用情况表`
- Current table groups:
  - `进项发票`
  - `支付状态`
  - `OA`
  - `流水`
- Column headers:
  - `发票号码`
  - `销方`
  - `价税合计` / `不含税/税率税额`
  - `货物或应税劳务名称`
  - `支付状态`
  - `OA申请人`
  - `项目名称`
  - `对方户名`
  - `金额`
  - `摘要/备注`
- Must preserve:
  - 10-column fixed dense layout and group boundaries.
  - Amount columns right aligned with tabular numbers.
  - Payment status column visual emphasis and class contract `input-invoice-usage-payment-cell` unless P054 replaces it with an equivalent project class contract.
  - Invoice number detail icon button label `查看发票 <invoice> 详情`.
  - OA detail text button label `查看OA <applicant/id> 详情` when `detailAvailable` is true.
  - Bank detail text button label `查看流水 <counterparty/id> 详情` when `detailAvailable` is true.
  - Date/status/application type/bank direction tags with stable height and no row jump.
  - Expand/collapse labels such as `展开 <preview>` and `收起 <preview>`.
  - Empty row copy `当前条件下没有进项发票使用记录。`
  - No DataGrid.

### Drawer / Workspace Tables

| Surface | Accessible name | Notes |
| --- | --- | --- |
| Export drawer | `进项发票使用情况导出样例` | Preserve preview columns, sample rows, empty text `暂无样例。` |
| Payment rules drawer | `Sheet4 支付状态规则` | Preserve editable/read-only table modes and versioned save |
| OA reverse workspace | `反提 OA 候选发票清单` | Preserve candidate checkbox labels, selected count, backend-driven rows and batch creation |

## Filter Menu

`InputInvoiceUsageFilterMenu` is a shared component under `components/inputInvoiceUsage`, but `/input-invoice-usage` does not currently mount it in `InputInvoiceUsagePage` or `InputInvoiceUsageTable`.

Current consumer:

- `web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`

Current behavior covered by tests:

- Trigger button label `筛选 <field label>`.
- Menu accessible name `<field label>筛选与排序`.
- Sort menu items `升序排序` and `降序排序`.
- Multi-select mode with `menuitemcheckbox`, `全选`, `清空`, API-provided labels/counts and no fabricated options.
- Single-select mode with `menuitemradio`.
- Empty options text `暂无可选项`.
- Non-enum fields show `该字段的输入控件由页面查询区提供`.

Migration rule:

- Preserve prop contract for existing consumers.
- Do not add this menu to input invoice usage table unless a separate product/UI prompt explicitly requires restoring column filters.

## Drawers And Workflows

All existing overlays are right drawers after migration.

| Surface | Current title / label | Shape | Must preserve |
| --- | --- | --- | --- |
| Detail drawer | `发票详情`, `银行流水详情`, `OA详情`, `关联明细`; close `关闭详情抽屉` | right drawer | Lazy load on open, loading `正在加载完整详情`, progress label `正在加载详情`, error text, `详情暂不可用`, `后端未提供 OA 完整详情`, field sections |
| Export drawer | `筛选内容导出`; drawer label `进项发票使用情况导出`; close `关闭进项发票使用情况导出` | right drawer | Preview load, `正在计算导出范围`, `导出数据准备中，请稍后再试。`, `预计导出 <n> 行`, sample table, `下载导出`, success `已生成 <file>` |
| Payment status rules drawer | `发票与支付状态规则设置`; close `关闭支付状态规则抽屉` | right drawer | Loading `正在读取规则`, progress label `正在加载支付状态规则`, read-only/no-save mode, editable table inputs, version chip, `还原`, `保存规则`, version conflict text |
| OA reverse workspace drawer | `以发票反提 OA`; drawer label `以发票反提 OA 工作流`; close `关闭以发票反提 OA 工作流` | right drawer | Preview load, target applicant select, backend warnings, backend unavailable reason, target groups, rejected reasons, candidate table, candidate selection, selected count, local batch, OA draft, refresh status, revoke, manual fallback |

## Loading / Empty / Error / Stale / Permission

- Page read model:
  - `readModelStatus === "refreshing"` schedules retry only while keep-alive page is active.
  - Current page intentionally hides old refresh detail copy `进项发票使用情况读模型正在刷新，完成后页面会自动重新加载。`
- Page loading:
  - `aria-label="进项发票使用情况加载中"` with three skeleton blocks today.
- Page empty:
  - Standard `StatePanel` copy `当前条件下暂无记录。`
- Detail drawer:
  - Loading label `正在加载详情`; text `正在加载完整详情`.
  - Unavailable OA detail must not fabricate fake OA detail.
- Export drawer:
  - `readModelStatus === "refreshing"` disables download through `refreshing` state and shows `导出数据准备中，请稍后再试。`
- Payment rules:
  - Read-only payload must show content without textboxes or save button.
  - Editable payload must send `expectedVersion` and `idempotencyKey`.
  - Conflict text: `规则已被其他人更新，请重新加载后再编辑。`
- OA reverse:
  - Preview, batch, draft, refresh, revoke and manual status all depend on backend payload flags and permissions.
  - Do not fabricate draft success or hidden unavailable states.

## Existing Test Coverage

`web/src/test/InputInvoiceUsagePage.test.tsx` currently covers:

- Empty state while read model refresh details stay hidden.
- Keep-alive inactive page pauses read model retry reload.
- Sidebar route and main dense table layout without DataGrid.
- Group and column headers.
- Amount formatting.
- Date chips via `.MuiChip-root` class assertions.
- Detail buttons and detail drawer opening.
- Expand/collapse long text.
- Pagination next page server request.
- Restored legacy filters/sort are dropped.
- Export preview and download flow.

`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` currently covers:

- Filter menu multi-select, select all, clear, sort asc/desc.
- Filter menu single-select radio behavior.
- Detail drawer lazy loading and invoice/bank/OA/relation payloads.
- OA reverse API mapper backend contract.
- OA reverse drawer preview, backend-provided totals/groups/rejections and no fabricated actions.
- OA reverse preview to batch to draft to refresh status.
- OA reverse target applicant selection.
- OA reverse manual fallback after backend detection exception.
- Payment status rules read-only mode.
- Payment status rules editable versioned save.
- Payment status rules version conflict.
- Parent state keeps OA reverse and payment rules drawers mutually exclusive.
- Opening/closing workflow drawers does not invoke parent rows loader.

## API / Contract Boundaries

Do not change:

- `fetchInputInvoiceUsageRows` query shape: `page`, `page_size`, `keyword`, `invoice_date_from`, `invoice_date_to`, `month`, encoded `filters`, `sort_field`, `sort_direction`.
- Row response mapping for invoice/payment status/OA/bank relation summaries.
- Detail endpoints for invoice, bank, OA and relation list.
- Payment status rules load/save shape, version conflict handling and idempotency key.
- OA reverse preview, batch creation, draft creation, refresh status, revoke and manual status request semantics.
- Export preview/download current filter request semantics.
- Page session state key `input-invoice-usage` and table scroll key `usage-table`.

## Migration Slices

1. `P054-phase-6-input-invoice-usage-characterization-tests`
   - Update only `InputInvoiceUsagePage.test.tsx` and `InputInvoiceUsageFiltersAndDrawers.test.tsx`.
   - Remove MUI wording and class assertions.
   - Add project primitive/source-level no-MUI contracts with expected failures before implementation.
2. `P055-phase-6-input-invoice-usage-page-shell-toolbar`
   - Migrate page shell actions/search/loading/error while keeping the main table and drawers untouched.
   - Preserve `关键字`, `查询`, toolbar buttons and refresh behavior.
3. `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell`
   - Migrate `InputInvoiceUsageTable.tsx` and `ExpandableCellText.tsx`.
   - Preserve 10-column grouped table, tags, detail buttons, long-text expansion and pagination.
4. `P057-phase-6-input-invoice-usage-filter-menu`
   - Migrate shared `InputInvoiceUsageFilterMenu.tsx`.
   - Preserve `OaPendingPaymentsTable` prop compatibility and menu aria semantics.
5. `P058-phase-6-input-invoice-usage-detail-and-export-drawers`
   - Migrate detail and export right drawers.
   - Preserve loading/error/unavailable/export-preview/download behavior.
6. `P059-phase-6-input-invoice-usage-payment-rules-drawer`
   - Migrate payment status rules right drawer.
   - Preserve read-only/edit/versioned save/conflict behavior.
7. `P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer`
   - Migrate OA reverse right drawer.
   - Preserve preview, candidate selection, batch, draft, status refresh, revoke and manual fallback.
   - If implementation scope proves too large during prompt review, split into P060 workspace shell/candidate table and P061 batch/draft/actions.
8. `MG-P060-or-P061-phase-6-input-invoice-usage`
   - Run module tests, common/table/platform regressions, build, scoped MUI grep, docs update, exact stage, commit and push.

## Risks

- Main table is dense and fixed-width. Preserve scanability, column group boundaries and right-aligned financial amounts before changing visual polish.
- Payment status column is deliberately emphasized today. Keep a consistent project class/token contract rather than a one-off yellow hard-code.
- `InputInvoiceUsageFilterMenu` has an external consumer in `OaPendingPaymentsTable`; migration must not break that page.
- OA reverse workspace is business-sensitive and action-heavy. It must not migrate in the same slice as the main table or ordinary drawers.
- Payment rules drawer has versioned save and permission behavior. Keep read-only mode free of editable controls.
- Existing tests include MUI class assertions. P054 must replace those with behavior and source contracts before implementation.

## P054 Prompt Draft

```text
Prompt ID: P054-phase-6-input-invoice-usage-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只更新 input invoice usage tests，锁定 `/input-invoice-usage` 非 MUI/project primitive contract；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/InputInvoiceUsagePage.tsx、web/src/components/inputInvoiceUsage/*.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/FinanceTable.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx。只修改 `web/src/test/InputInvoiceUsagePage.test.tsx` 和 `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`：把当前 `dense MUI Table layout without DataGrid`、`.MuiDataGrid-root`、`.MuiChip-root` 等 MUI wording/class assertions 改成行为和 project primitive assertions；新增 source-level contracts，锁定 page shell/toolbar/search/loading、main dense table、ExpandableCellText、shared filter menu、detail/export/payment-rules/OA-reverse right drawers 未来均不再依赖 `@mui/*`、`Mui[A-Z]`、`TablePagination`、`TextField`、`Drawer`、`Dialog`、`Menu`、`Chip` 等旧 MUI surface；新增或保留行为断言确保旧右侧抽屉仍是右侧抽屉，`进项发票使用情况表`、`进项发票使用情况导出样例`、`Sheet4 支付状态规则`、`反提 OA 候选发票清单` 表格语义保留，`筛选 支付状态` menu、`关闭详情抽屉`、`关闭进项发票使用情况导出`、`关闭支付状态规则抽屉`、`关闭以发票反提 OA 工作流` 标签保留。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P055 page shell toolbar prompt。
```

## Execution Update: P054 Characterization Tests

- Status: verified as expected-fail.
- Files changed:
  - `web/src/test/InputInvoiceUsagePage.test.tsx`
  - `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`
- Runtime implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Test changes:
  - Added source-level project primitive contracts for page shell, dense table, expandable cell, shared filter menu and workflow drawers.
  - Reworded the main table test away from old MUI terminology.
  - Replaced `.MuiDataGrid-root` and `.MuiChip-root` assertions with behavior/table/text assertions.
  - Preserved behavior coverage for table semantics, pagination, detail drawer, export drawer, filter menu, payment rules and OA reverse workflows.
- Verification:
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures.
  - Expected failures:
    - `InputInvoiceUsagePage.test.tsx` source contract lists remaining MUI imports/selectors and missing page/table/drawer primitive targets.
    - `InputInvoiceUsageFiltersAndDrawers.test.tsx` source contract lists remaining MUI overlay imports/selectors and missing AppDrawer targets.

## Current Expected Failures After P054

The two source-level failures are expected until P055-P060/P061 complete:

- `src/pages/InputInvoiceUsagePage.tsx`: still imports MUI page shell controls/icons/search/loading; P055 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx`: still imports MUI table/tag/pagination/tooltip/button controls and `.MuiChip-label`/`.MuiTablePagination-*` selectors; P056 owns this.
- `src/components/inputInvoiceUsage/ExpandableCellText.tsx`: still imports MUI icons/tooltip/button/text layout; P056 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx`: still imports MUI menu/check/radio/button/icons and `.MuiButton-startIcon`; P057 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx`: still imports MUI Drawer and status/layout components; P058 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx`: still imports MUI Drawer/table/status/action components; P058 owns this.
- `src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx`: still imports MUI Drawer/table/form/tag/status/action components; P059 owns this.
- `src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`: still imports MUI Drawer/table/form/selection/tag/status/action components; P060 owns this.

## P055 Prompt Draft

```text
Prompt ID: P055-phase-6-input-invoice-usage-page-shell-toolbar
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/input-invoice-usage` page shell/actions/search/loading/error only. Do not migrate `InputInvoiceUsageTable`, `ExpandableCellText`, `InputInvoiceUsageFilterMenu` or any input invoice usage drawer/workflow component.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/InputInvoiceUsagePage.tsx、web/src/test/InputInvoiceUsagePage.test.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/components/common/StatePanel.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/InputInvoiceUsagePage.tsx`、必要 `web/src/app/styles.css` 和必要的 `web/src/test/InputInvoiceUsagePage.test.tsx` expectation：移除 page shell/actions/search/loading/error scope 的 MUI imports/usages，包括 `FileDownloadOutlinedIcon`、`RefreshOutlinedIcon`、`Alert`、`Box`、`Button`、`Skeleton`、`Stack`、`TextField`。使用 existing `PageScaffold`、`PageToolbar` 或等价 project toolbar、native/project buttons、native/project search input、project loading skeleton/status message 和 lucide icons。必须保留 `data-testid="input-invoice-usage-page"`、heading `进项发票使用情况`、description `以进项发票为主对象反查支付状态、OA 和银行流水。`、toolbar buttons `以发票反提 OA`、`发票与支付状态规则设置`、`筛选内容导出`、`刷新`、search input label `关键字`、submit button `查询`、Enter submit、refresh disabled while refreshing、error feedback、loading label `进项发票使用情况加载中`、empty state `当前条件下暂无记录。`、query/page reset and read model retry behavior。不得修改 input invoice usage API/mock/read model/worker/backend/关联台；不得修改 `web/src/components/inputInvoiceUsage/*`。运行 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives|uses a standard empty state|pauses read model retry|adds sidebar route|drops legacy column filters|loads export preview"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P056-P060/P061 table/filter/drawer source contract failures 可以继续 expected-fail，但 `src/pages/InputInvoiceUsagePage.tsx` must disappear from the source-level failure list；运行 `cd web && npm run build`；运行 page shell MUI grep：`if rg -n '@mui/|Mui[A-Z]|FileDownloadOutlinedIcon|RefreshOutlinedIcon|Skeleton|TextField' web/src/pages/InputInvoiceUsagePage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P056 main table and expandable cell prompt。
```

## Execution Update: P055 Page Shell / Toolbar

- Status: verified as expected-fail.
- Files changed:
  - `web/src/pages/InputInvoiceUsagePage.tsx`
  - `web/src/app/styles.css`
- Runtime implementation changed: page shell/actions/search/loading/error only.
- Input invoice usage table/filter/drawer components changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - `InputInvoiceUsagePage.tsx` now uses `PageToolbar` plus native/project buttons and search input.
  - MUI page-level imports were removed: icons, Alert, Box, Button, Skeleton, Stack and TextField.
  - Loading state now uses project skeleton markup under `aria-label="进项发票使用情况加载中"`.
  - Error state now uses `StatePanel tone="error"`.
  - Toolbar labels, search label, Enter submit, refresh disabled state, empty state and page/session behavior are preserved.
- Verification:
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives|uses a standard empty state|pauses read model retry|adds sidebar route|drops legacy column filters|loads export preview"`: expected-fail. Five behavior tests passed; the only failure is the source-level contract for P056-P060/P061.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures. `src/pages/InputInvoiceUsagePage.tsx` no longer appears in the failure lists.
  - `if rg -n '@mui/|Mui[A-Z]|FileDownloadOutlinedIcon|RefreshOutlinedIcon|Skeleton|TextField' web/src/pages/InputInvoiceUsagePage.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.

## Current Expected Failures After P055

The two source-level failures are expected until P056-P060/P061 complete:

- `src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx`: still imports MUI table/tag/pagination/tooltip/button controls and `.MuiChip-label`/`.MuiTablePagination-*` selectors; P056 owns this.
- `src/components/inputInvoiceUsage/ExpandableCellText.tsx`: still imports MUI icons/tooltip/button/text layout; P056 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx`: still imports MUI menu/check/radio/button/icons and `.MuiButton-startIcon`; P057 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx`: still imports MUI Drawer and status/layout components; P058 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx`: still imports MUI Drawer/table/status/action components; P058 owns this.
- `src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx`: still imports MUI Drawer/table/form/tag/status/action components; P059 owns this.
- `src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`: still imports MUI Drawer/table/form/selection/tag/status/action components; P060 owns this.

## P056 Prompt Draft

```text
Prompt ID: P056-phase-6-input-invoice-usage-main-table-and-expandable-cell
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/input-invoice-usage` main dense table and expandable cell only: `InputInvoiceUsageTable.tsx`, `ExpandableCellText.tsx`, necessary `web/src/app/styles.css` and necessary `InputInvoiceUsagePage.test.tsx` expectations. Do not migrate `InputInvoiceUsageFilterMenu` or any input invoice usage drawer/workflow component.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、docs/refactor-ui/table_layout_system.md、web/src/components/common/FinanceTable.tsx、web/src/pages/InputInvoiceUsagePage.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx、web/src/components/inputInvoiceUsage/ExpandableCellText.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 `InputInvoiceUsageTable.tsx` 和 `ExpandableCellText.tsx` 的 MUI imports/usages，包括 `InfoOutlinedIcon`、`ExpandLessOutlinedIcon`、`ExpandMoreOutlinedIcon`、`Box`、`Button`、`Chip`、`IconButton`、`Paper`、`Stack`、`Table*`、`TablePagination`、`Tooltip`、`Typography` 和 `.MuiChip-label`/`.MuiTablePagination-*` selectors。使用 `FinanceTable`/project dense table primitives 或 native project table shell、project tags/buttons/tooltips、lucide icons 和 project pagination。必须保留 `aria-label="进项发票使用情况表"`、四个列组 `进项发票`/`支付状态`/`OA`/`流水`、10 列 header、amount right alignment/tabular nums、payment status class or equivalent project class contract、date/status/application/bank direction tags with stable height、detail button labels `查看发票 <invoice> 详情` / `查看OA <applicant/id> 详情` / `查看流水 <counterparty/id> 详情`、long-text expand/collapse labels、empty row `当前条件下没有进项发票使用记录。`、server page/pageSize/total pagination labels `每页行数` and `<from>-<to> / <count>`。不得修改 page shell、filter menu、detail/export/payment-rules/OA-reverse drawers、input invoice usage API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives|adds sidebar route"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P057-P060/P061 filter/drawer source contract failures 可以继续 expected-fail，但 `InputInvoiceUsageTable.tsx` and `ExpandableCellText.tsx` must disappear from the source-level failure list；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 table MUI grep：`if rg -n '@mui/|Mui[A-Z]|TablePagination|InfoOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon' web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx web/src/components/inputInvoiceUsage/ExpandableCellText.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P057 filter menu prompt。
```

## Execution Update: P056 Main Table And Expandable Cell

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx`
  - `web/src/components/inputInvoiceUsage/ExpandableCellText.tsx`
  - `web/src/app/styles.css`
- Runtime implementation changed: main dense table, pagination and expandable cell only.
- Page shell/filter menu/drawer components changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - Replaced MUI table/chip/button/tooltip/pagination stack with a native project dense table shell.
  - Preserved table accessible name `进项发票使用情况表`, four column groups, 10-column header, detail buttons, payment status class contract, empty row and pagination labels.
  - Replaced MUI expandable text controls with `lucide-react` chevrons and project/native buttons.
  - Added input invoice usage table, tag, action, expandable text and pagination styles in `web/src/app/styles.css`.
  - Corrected P055 page shell CSS to use existing `--fp-primary` tokens instead of undefined accent aliases.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|TablePagination|InfoOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon' web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx web/src/components/inputInvoiceUsage/ExpandableCellText.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives|adds sidebar route"`: expected-fail. Main table behavior passed; source failure now lists only filter menu and drawers.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures. `InputInvoiceUsageTable.tsx` and `ExpandableCellText.tsx` no longer appear in failure lists.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.

## Current Expected Failures After P056

The two source-level failures are expected until P057-P060/P061 complete:

- `src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx`: still imports MUI menu/check/radio/button/icons and `.MuiButton-startIcon`; P057 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx`: still imports MUI Drawer and status/layout components; P058 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx`: still imports MUI Drawer/table/status/action components; P058 owns this.
- `src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx`: still imports MUI Drawer/table/form/tag/status/action components; P059 owns this.
- `src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`: still imports MUI Drawer/table/form/selection/tag/status/action components; P060 owns this.

## P057 Prompt Draft

```text
Prompt ID: P057-phase-6-input-invoice-usage-filter-menu
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: Shared `InputInvoiceUsageFilterMenu.tsx` only, plus necessary styles/tests. Preserve its external consumer `OaPendingPaymentsTable`; do not add new `/input-invoice-usage` table filter entrypoints.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/app/styles.css。只修改 `InputInvoiceUsageFilterMenu.tsx`、必要 `web/src/app/styles.css` 和必要测试 expectation：移除 filter menu 的 MUI imports/usages，包括 `ArrowDownwardOutlinedIcon`、`ArrowUpwardOutlinedIcon`、`FilterListOutlinedIcon`、`Button`、`Checkbox`、`Divider`、`ListItemIcon`、`ListItemText`、`Menu`、`MenuItem`、`Radio`、`Stack`、`Typography` 和 `.MuiButton-startIcon` selector。使用 project/native popover/menu、native checkbox/radio semantics and lucide icons。必须保持 prop contract for `OaPendingPaymentsTable`，保留 trigger label `筛选 <field label>`、menu accessible name `<field label>筛选与排序`、heading/subtitle text、`升序排序`、`降序排序`、`全选`、`清空`、`暂无可选项`、`该字段的输入控件由页面查询区提供`、`menuitemcheckbox` checked state、`menuitemradio` checked state、API-provided option labels/counts and no fabricated options。不得修改 page shell、main table、detail/export/payment-rules/OA-reverse drawers、input invoice usage API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "InputInvoiceUsageFilterMenu|workflow primitive targets"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P058-P060/P061 drawer source contract failures 可以继续 expected-fail，但 `InputInvoiceUsageFilterMenu.tsx` must disappear from the source-level failure lists；运行 `cd web && npm run build`；运行 filter menu MUI grep：`if rg -n '@mui/|Mui[A-Z]|FilterListOutlinedIcon|ArrowDownwardOutlinedIcon|ArrowUpwardOutlinedIcon|MenuItem|ListItemText|Checkbox|Radio' web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P058 detail/export drawers prompt。
```

## Execution Update: P057 Filter Menu

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx`
  - `web/src/app/styles.css`
- Runtime implementation changed: shared filter menu only.
- External consumer changed: no. `OaPendingPaymentsTable` keeps the same props/callback contract.
- Page shell/main table/drawers changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - Replaced MUI `Button`, `Menu`, `MenuItem`, checkbox/radio/list item/icon stack with project/native trigger and popover menu.
  - Preserved trigger label, menu accessible name, sort actions, `全选`, `清空`, empty option text, non-enum placeholder and checked `menuitemcheckbox`/`menuitemradio` semantics.
  - Added filter menu styles in `web/src/app/styles.css`.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|FilterListOutlinedIcon|ArrowDownwardOutlinedIcon|ArrowUpwardOutlinedIcon|MenuItem|ListItemText|Checkbox|Radio' web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "InputInvoiceUsageFilterMenu|workflow primitive targets"`: expected-fail. Filter menu behavior tests passed; source failure now lists only drawers.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures. `InputInvoiceUsageFilterMenu.tsx` no longer appears in failure lists.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.

## Current Expected Failures After P057

The two source-level failures are expected until P058-P060/P061 complete:

- `src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx`: still imports MUI Drawer and status/layout components; P058 owns this.
- `src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx`: still imports MUI Drawer/table/status/action components; P058 owns this.
- `src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx`: still imports MUI Drawer/table/form/tag/status/action components; P059 owns this.
- `src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`: still imports MUI Drawer/table/form/selection/tag/status/action components; P060 owns this.

## P058 Prompt Draft

```text
Prompt ID: P058-phase-6-input-invoice-usage-detail-and-export-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: Input invoice usage detail drawer and export drawer only: `InputInvoiceUsageDetailDrawer.tsx`, `InputInvoiceUsageExportDrawer.tsx`, necessary styles/tests. Do not migrate `PaymentStatusRulesDrawer.tsx` or `OaReverseWorkspaceDrawer.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、web/src/components/common/AppDrawer.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx、web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 detail/export drawers 的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Box`、`Button`、`CircularProgress`、`Divider`、`Drawer`、`IconButton`、`Paper`、`Stack`、`Table*`、`Typography`。使用 `AppDrawer`、project/native status messages/loading、project detail section cards、project sample table and project action buttons。必须保留 detail drawer right placement、`aria-label="详情"` 或 equivalent drawer accessible label、close button `关闭详情抽屉`、lazy load on open、progress label `正在加载详情`、text `正在加载完整详情`、error text、`详情暂不可用` and unavailable reason behavior、empty detail `暂无更多详情。`、field section labels and values。必须保留 export drawer right placement、drawer label `进项发票使用情况导出`、close `关闭进项发票使用情况导出`、title `筛选内容导出`、preview loading `正在加载导出预览` / `正在计算导出范围`、refreshing notice `导出数据准备中，请稍后再试。`、success `已生成 <file>`、`预计导出 <n> 行`、sample table `进项发票使用情况导出样例`、empty sample `暂无样例。`、`关闭` and `下载导出` buttons and actual download trigger behavior。不得修改 page shell、main table、filter menu、payment-rules/OA-reverse drawers、input invoice usage API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx -t "detail drawer|loads export preview|workflow primitive targets"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P059-P060/P061 payment-rules/OA-reverse source contract failures 可以继续 expected-fail，但 detail/export drawer files must disappear from source-level failure lists；运行 `cd web && npm run build`；运行 detail/export drawer MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|Drawer|TableCell|TableRow|TableHead|TableBody' web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P059 payment status rules drawer prompt。
```

## Execution Update: P058 Detail And Export Drawers

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx`
  - `web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx`
  - `web/src/app/styles.css`
- Runtime implementation changed: detail and export right drawers only.
- Payment rules and OA reverse drawers changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - Replaced detail/export MUI Drawer implementations with `AppDrawer`.
  - Replaced MUI alert/loading/paper/table/button/layout usage with project/native status blocks, sections, sample table and action buttons.
  - Preserved lazy loading, unavailable OA detail behavior, detail sections, export preview, sample table, refreshing notice, success message and download trigger.
  - Added detail/export drawer styles in `web/src/app/styles.css`.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|@mui/material/Drawer|TableCell|TableRow|TableHead|TableBody' web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx -t "detail drawer|loads export preview|workflow primitive targets"`: expected-fail. Detail/export behavior passed where selected; source failure now lists only payment rules and OA reverse drawers.
  - `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "lazy-loads full invoice detail|supports invoice, bank, OA and relation-list detail payloads"`: passed, 2 tests passed.
  - `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`: expected-fail, 19 passed and 2 source-level failures. Detail/export drawer files no longer appear in failure lists.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.

## Current Expected Failures After P058

The two source-level failures are expected until P059-P060/P061 complete:

- `src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx`: still imports MUI Drawer/table/form/tag/status/action components; P059 owns this.
- `src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`: still imports MUI Drawer/table/form/selection/tag/status/action components; P060 owns this.

## P059 Prompt Draft

```text
Prompt ID: P059-phase-6-input-invoice-usage-payment-rules-drawer
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `PaymentStatusRulesDrawer.tsx` only, plus necessary styles/tests. Do not migrate `OaReverseWorkspaceDrawer.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_input_invoice_usage.md、web/src/components/common/AppDrawer.tsx、web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx、web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx、web/src/test/InputInvoiceUsagePage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 payment rules drawer 的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Box`、`Button`、`Chip`、`CircularProgress`、`Divider`、`Drawer`、`IconButton`、`Paper`、`Stack`、`Table*`、`TextField`、`Typography`。使用 `AppDrawer`、project/native status messages/loading/tags/table/inputs/buttons。必须保留 drawer title `发票与支付状态规则设置`、close label `关闭支付状态规则抽屉`、loading progress label `正在加载支付状态规则` and text `正在读取规则`、error text、success `规则已保存，读模型会按后端返回的刷新状态更新。`、version chip `版本 <n>`、read-only/no-save mode、editable `支付状态`/`规则`/`优先级` inputs、pending direction inputs/chips、`还原`、`保存规则`、dirty disabled behavior、versioned save payload with idempotency key and conflict text `规则已被其他人更新，请重新加载后再编辑。`。不得修改 page shell、main table、filter menu、detail/export drawers、OA-reverse drawer、input invoice usage API/mock/read model/worker/backend/关联台。运行 `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "payment status rules|workflow primitive targets"`；运行完整 `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx`，P060/P061 OA-reverse source contract failure 可以继续 expected-fail，但 `PaymentStatusRulesDrawer.tsx` must disappear from source-level failure lists；运行 `cd web && npm run build`；运行 payment rules MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|@mui/material/Drawer|TextField|TableCell|TableRow|TableHead|TableBody|Chip' web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P060 OA reverse workspace drawer prompt。
```
