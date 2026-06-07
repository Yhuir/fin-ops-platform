# Phase 6 OA Pending Payments

本文档记录 `/oa-pending-payments` 的 UI 迁移 discovery、旧入口对照、测试策略和后续 Micro-JIT prompt。目标是迁出非关联台 MUI，同时保持用户使用感受不变。

## P061 Discovery

- Prompt ID: `P061-phase-6-oa-pending-payments-discovery`
- Type: discovery/planning
- Status: verified
- Scope: `/oa-pending-payments` only.
- Implementation changed: no.
- Tests changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

## Current Files

| Area | Files | Notes |
| --- | --- | --- |
| Page | `web/src/pages/OaPendingPaymentsPage.tsx` | Page shell, query controls, refresh/rules actions, loading/error/empty, detail drawer and expense pending invoice rules drawer wiring. |
| Table | `web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx` | Grouped dense table, shared filter menu, sorting, pagination, detail buttons and status tags. |
| API/types | `web/src/features/oaPendingPayments/api.ts`, `web/src/features/oaPendingPayments/types.ts` | Rows/filter-options/detail routes. No migration prompt may change these contracts. |
| Tests | `web/src/test/OaPendingPaymentsPage.test.tsx` | Route/sidebar, grouped table, search/filter/sort, detail drawers, rules drawer stability, empty/read-model refreshing states. |
| Shared migrated dependencies | `InputInvoiceUsageFilterMenu`, `InputInvoiceUsageDetailDrawer`, `PendingInvoiceRulesDrawer` | Already migrated project primitives. Future slices must preserve their prop contracts. |

## Current MUI Inventory

| File | Current MUI usage | Target |
| --- | --- | --- |
| `OaPendingPaymentsPage.tsx` | `RefreshOutlinedIcon`, `TuneOutlinedIcon`, `Alert`, `Button`, `MenuItem`, `Skeleton`, `Stack`, `TextField` | Project/native page toolbar controls, native inputs/selects, project loading skeleton/status message, lucide icons. |
| `OaPendingPaymentsTable.tsx` | `InfoOutlinedIcon`, `SortOutlinedIcon`, `Box`, `Button`, `Chip`, `IconButton`, `Paper`, `Stack`, `Table*`, `TablePagination`, `Tooltip`, `Typography`; `.MuiChip-label` selector in `denseChipSx` | `FinanceTable` or native project dense table, project tags/buttons/tooltips, project pagination, lucide icons. |
| `OaPendingPaymentsPage.test.tsx` | Test wording says “compact grouped MUI table”; asserts `.MuiDataGrid-root` absence only | Convert to project primitive/source contracts in P062. Avoid `.Mui*` assertions except explicit no-MUI source residue checks. |

## User-visible Entrypoints

| Entrypoint | Current behavior to preserve |
| --- | --- |
| Route/sidebar | `/oa-pending-payments`, sidebar label `OA待付款核对`, page heading `OA 待付款核对`. |
| Top actions | `支出流水无需开票规则设置` opens the existing expense rules right drawer; `刷新` refreshes rows and disables while refreshing. |
| Query controls | `全页面检索`, `查询`, `月份`, `交易开始`, `交易结束`, `支付状态`. Enter in search submits keyword. |
| Table | Accessible name `OA待付款核对表格`; group headers `OA情况`, `支付状态`, `支出流水`, `发票情况`; 10 leaf columns. |
| Shared filter menu | `筛选 OA申请人` uses API-provided options and the migrated `InputInvoiceUsageFilterMenu` contract. |
| Sorting | `交易时间 排序` toggles `bank_trade_time` with backend query params. |
| Detail buttons | `查看 OA <applicant> 详情`, `查看流水 <applicant> 详情`, `查看发票 <applicant> 详情`, relation-list labels for multiple bank/invoice relations. |
| Detail drawer | Reuses `InputInvoiceUsageDetailDrawer`; remains right drawer and supports unavailable/read-model refreshing state. |
| Rules drawer | Reuses `PendingInvoiceRulesDrawer` with `direction=expense`; remains stable during parent refresh and does not reload rules unnecessarily. |
| Empty/loading/error | Loading label `OA待付款核对加载中`, empty state `当前条件下暂无记录。`, row empty `暂无 OA 待付款核对数据`, error `OA 待付款核对加载失败。`. |

## API / Read Model Boundary

- Rows: `GET /api/oa-pending-payments/rows`.
- Filter options: `GET /api/oa-pending-payments/filter-options`.
- Details:
  - `GET /api/oa-pending-payments/oa/:id/detail`
  - `GET /api/oa-pending-payments/bank-transactions/:id/detail`
  - `GET /api/oa-pending-payments/invoices/:id/detail`
  - `GET /api/oa-pending-payments/rows/:rowId/relation-details?kind=bank|invoice`
- Product/API docs require rows, filter-options and detail interfaces to represent read model status and not fabricate options or stale details.
- UI migration must not change request params: `page`, `page_size`, `keyword`, `month`, `trade_date_from`, `trade_date_to`, `filters`, `sort_field`, `sort_direction`.

## Existing Test Coverage

| Test | Current coverage | Migration implication |
| --- | --- | --- |
| `adds sidebar route and renders compact grouped MUI table from OA perspective` | Route/sidebar, heading, no DataGrid, grouped table headers, search, API-provided filter, sort query. | P062 should rename MUI wording and add source/project primitive contract. |
| `opens OA, bank, invoice, relation drawers and reuses pending invoice rules endpoint` | Detail drawer targets and rules endpoint direction `expense`. | Must keep `InputInvoiceUsageDetailDrawer` and `PendingInvoiceRulesDrawer` wiring. |
| `keeps pending invoice rules drawer stable during parent refresh` | Rules drawer does not reload during parent refresh; refresh button re-enables. | Page shell refactor must preserve parent refresh state and rules drawer state. |
| `uses a standard empty state while read model refresh details stay hidden` | Empty state hides read model internals. | Keep user-facing empty state; do not surface stale reason text in table view. |
| `shows neutral unavailable detail state while detail read model is refreshing` | Detail drawer shows `详情暂不可用` and backend unavailable reason. | Detail drawer is shared and already migrated; keep target mapping unchanged. |

## Migration Slice Plan

1. `P062-phase-6-oa-pending-payments-characterization-tests`
   - Convert MUI wording/class assertions to behavior/project primitive assertions.
   - Add source-level contracts for page shell and table.
2. `P063-phase-6-oa-pending-payments-page-shell-toolbar`
   - Migrate page actions, query controls, loading/error shell.
   - Do not migrate table.
3. `P064-phase-6-oa-pending-payments-grouped-table`
   - Migrate table, status tags, detail buttons, sorting and pagination.
   - Preserve shared `InputInvoiceUsageFilterMenu` prop contract.
4. `MG-P064-phase-6-oa-pending-payments`
   - Verify module no-MUI residue, tests, build and exact push.

## Risks

- `InputInvoiceUsageFilterMenu` is a shared already-migrated primitive; changes to its props would regress input invoice usage and OA pending payments together. Do not change its contract in this module.
- `PendingInvoiceRulesDrawer` is shared with pending invoices; keep `direction=expense` and avoid reloading rules during parent refresh.
- `InputInvoiceUsageDetailDrawer` is shared; detail targets must remain `oa`, `bank`, `invoice`, `relationList`.
- The old table is a grouped dense table with fixed-width columns. New table must remain a table, not cards.
- Read model refreshing/stale details are intentionally hidden in the list empty state but visible in detail unavailable state.

## P062 Prompt Draft

```text
Prompt ID: P062-phase-6-oa-pending-payments-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/oa-pending-payments` tests only. Do not modify runtime implementation.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_oa_pending_payments.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/OaPendingPaymentsPage.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx 和 web/src/test/OaPendingPaymentsPage.test.tsx。只修改 `web/src/test/OaPendingPaymentsPage.test.tsx`：把 “compact grouped MUI table” wording 和 MUI/DataGrid/class-based expectations 改成 behavior/project primitive assertions；新增 source-level contracts，锁定 `OaPendingPaymentsPage.tsx` 和 `OaPendingPaymentsTable.tsx` 未来不再依赖 `@mui/*`、`Mui[A-Z]`、`TablePagination`、`TextField`、`Skeleton`、`Chip`、`IconButton`、`TableCell`、`TableRow`、`TableHead`、`TableBody`；新增或保留行为断言确保 route/sidebar、page heading、query controls、refresh/rules buttons、group headers、10 leaf columns、shared `InputInvoiceUsageFilterMenu` trigger `筛选 OA申请人`、sort button `交易时间 排序`、detail right drawer labels、rules drawer endpoint `direction=expense`、empty state and refreshing detail unavailable state保留。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P063 page shell toolbar prompt。
```

## Execution Update: P062 Characterization Tests

- Status: verified as expected-fail.
- Files changed:
  - `web/src/test/OaPendingPaymentsPage.test.tsx`
- Runtime implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - Renamed the main behavior test away from MUI wording.
  - Replaced `.MuiDataGrid-root` absence check with the user-observable table role `OA待付款核对表格`.
  - Added source-level contracts for `OaPendingPaymentsPage.tsx` and `OaPendingPaymentsTable.tsx`.
- Verification:
  - `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`: expected-fail, 5 behavior tests passed and 1 source-level contract failed. Current failure lists page/table MUI imports, table `.MuiChip-label`, legacy table/form surfaces, and missing project table primitive/class.
  - `git diff --check`: passed.

## Current Expected Failures After P062

- `src/pages/OaPendingPaymentsPage.tsx`: still imports MUI icons/layout/buttons/inputs/loading controls; P063 owns this.
- `src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`: still imports MUI table/tag/button/tooltip/pagination controls and `.MuiChip-label`; P064 owns this.

## P063 Prompt Draft

```text
Prompt ID: P063-phase-6-oa-pending-payments-page-shell-toolbar
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/oa-pending-payments` page shell/actions/query/loading/error only. Do not migrate `OaPendingPaymentsTable.tsx`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_oa_pending_payments.md、web/src/pages/OaPendingPaymentsPage.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/components/common/StatePanel.tsx、web/src/test/OaPendingPaymentsPage.test.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/OaPendingPaymentsPage.tsx`、必要 `web/src/app/styles.css` 和必要测试 expectation：移除 page shell/actions/query/loading/error scope 的 MUI imports/usages，包括 `RefreshOutlinedIcon`、`TuneOutlinedIcon`、`Alert`、`Button`、`MenuItem`、`Skeleton`、`Stack`、`TextField`。使用 project/native toolbar controls、native text/month/date/select inputs、project loading skeleton/status message and lucide icons。必须保留 `data-testid="oa-pending-payments-page"`、heading `OA 待付款核对`、buttons `支出流水无需开票规则设置` and `刷新`、search label `全页面检索`、`查询` button、Enter submit、date labels `月份`/`交易开始`/`交易结束`、payment status label `支付状态` and old options `全部`/`未支付`/`已支付`/`合并支付`/`支付少了`/`支付多了`/`待核对`、refresh disabled while refreshing、error text `OA 待付款核对加载失败。`、loading label `OA待付款核对加载中`、empty state `当前条件下暂无记录。`、detail/rules drawer wiring and API query behavior。不得修改 `OaPendingPaymentsTable.tsx`、shared filter/detail/rules drawers、mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OaPendingPaymentsPage.test.tsx -t "targets project primitives|adds sidebar route|keeps pending invoice rules drawer|uses a standard empty state|shows neutral unavailable detail"`；运行完整 `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`，P064 table source contract failure 可以继续 expected-fail，但 `src/pages/OaPendingPaymentsPage.tsx` must disappear from source-level failure lists；运行 `cd web && npm run build`；运行 page shell MUI grep：`if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|TuneOutlinedIcon|Skeleton|TextField|MenuItem' web/src/pages/OaPendingPaymentsPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P064 grouped table prompt。
```

## Execution Update: P063 Page Shell / Toolbar

- Status: verified as expected-fail.
- Files changed:
  - `web/src/pages/OaPendingPaymentsPage.tsx`
  - `web/src/app/styles.css`
  - `web/src/test/OaPendingPaymentsPage.test.tsx`
- Runtime changed:
  - Migrated page actions, query toolbar, loading skeleton and error alert from MUI to project/native controls.
  - Replaced page action icons with `lucide-react` icons.
  - Preserved route/sidebar, heading, refresh behavior, rules drawer trigger, query labels, Enter submit, status options, empty state, detail drawer wiring and rules drawer wiring.
- Table changed: no. `OaPendingPaymentsTable.tsx` remains the only OA pending payments MUI implementation surface.
- Shared filter/detail/rules drawers changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|TuneOutlinedIcon|Skeleton|TextField|MenuItem' web/src/pages/OaPendingPaymentsPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run OaPendingPaymentsPage.test.tsx -t "targets project primitives|adds sidebar route|keeps pending invoice rules drawer|uses a standard empty state|shows neutral unavailable detail"`: expected-fail; 4 behavior tests passed and the remaining source-level failure lists only `src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`.
  - `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`: expected-fail; 5 behavior tests passed and 1 source-level contract failed, limited to table residue.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P063 files and docs changed.

## Current Expected Failures After P063

- `src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`: still imports MUI table/tag/button/tooltip/pagination controls and contains `.MuiChip-label`; P064 owns this.
- `src/pages/OaPendingPaymentsPage.tsx`: cleared from source-level no-MUI failure lists.

## P064 Prompt Draft

```text
Prompt ID: P064-phase-6-oa-pending-payments-grouped-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/oa-pending-payments` grouped dense table only: `OaPendingPaymentsTable.tsx`, necessary `web/src/app/styles.css` and necessary `OaPendingPaymentsPage.test.tsx` expectation updates. Do not modify page shell, shared drawers or shared `InputInvoiceUsageFilterMenu`.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_oa_pending_payments.md、docs/refactor-ui/table_layout_system.md、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx、web/src/components/common/FinanceTable.tsx、web/src/test/OaPendingPaymentsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 `OaPendingPaymentsTable.tsx` 的 MUI imports/usages，包括 `InfoOutlinedIcon`、`SortOutlinedIcon`、`Box`、`Button`、`Chip`、`IconButton`、`Paper`、`Stack`、`Table*`、`TablePagination`、`Tooltip`、`Typography` 和 `.MuiChip-label` selector。使用 `FinanceTable`/project dense table primitives or native project table shell、project tags/buttons/tooltips、lucide icons and project pagination。必须保留 `aria-label="OA待付款核对表格"`、group headers `OA情况`/`支付状态`/`支出流水`/`发票情况`、10 leaf columns、shared `InputInvoiceUsageFilterMenu` trigger `筛选 OA申请人` and prop contract、sort button `交易时间 排序` and `bank_trade_time` query behavior、status cell project class or equivalent contract, amount right alignment/tabular nums, date/status/direction/account tags stable height, detail button labels `查看 OA <applicant> 详情` / `查看流水 <applicant> 详情` / `查看发票 <applicant> 详情` / relation-list labels, empty row `暂无 OA 待付款核对数据`, server pagination labels/options `每页`, `[20, 50, 100]` and total behavior。不得修改 page shell, shared filter/detail/rules drawers, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`，now all OA pending payments source-level no-MUI contracts must pass；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 table MUI grep：`if rg -n '@mui/|Mui[A-Z]|TablePagination|InfoOutlinedIcon|SortOutlinedIcon|TableCell|TableRow|TableHead|TableBody|Chip|IconButton' web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx; then exit 1; else exit 0; fi`；运行 full OA pending payments residue grep：`if rg -n '@mui/|Mui[A-Z]' web/src/pages/OaPendingPaymentsPage.tsx web/src/components/oaPendingPayments; then exit 1; else exit 0; fi`。运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 OA pending payments cumulative MG prompt。
```

## Execution Update: P064 Grouped Table

- Status: verified.
- Files changed:
  - `web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`
  - `web/src/app/styles.css`
- Runtime changed:
  - Migrated grouped dense table from MUI `Table*`, MUI tags/buttons/tooltips and MUI pagination to a project-owned native table shell.
  - Preserved accessible table name `OA待付款核对表格`, 4 group headers, 10 leaf columns, shared `InputInvoiceUsageFilterMenu`, `交易时间 排序`, status cell class, detail button labels, relation-list targets, empty row text, server pagination labels/options and total range.
  - Kept amounts right-aligned with tabular nums and normalized table tags/buttons to stable dimensions.
- Page shell changed: no.
- Shared filter/detail/rules drawers changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|TablePagination|InfoOutlinedIcon|SortOutlinedIcon|TableCell|TableRow|TableHead|TableBody|Chip|IconButton' web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx; then exit 1; else exit 0; fi`: passed.
  - `if rg -n '@mui/|Mui[A-Z]' web/src/pages/OaPendingPaymentsPage.tsx web/src/components/oaPendingPayments; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run OaPendingPaymentsPage.test.tsx`: passed, 6 tests.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P064 table/style files changed before docs.

## Current Expected Failures After P064

- None in `/oa-pending-payments` scoped no-MUI contracts.
- MUI dependencies remain allowed only for frozen reconciliation workbench internals and still-unmigrated non-workbench modules outside this completed module scope.

## MG-P064 Prompt Draft

```text
Prompt ID: MG-P064-phase-6-oa-pending-payments
Scope: completed `/oa-pending-payments` page batch P061-P064.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_oa_pending_payments.md、web/src/pages/OaPendingPaymentsPage.tsx、web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx、web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx、web/src/app/styles.css 和当前 git status。检查当前分支必须是 `refactor-ui`。检查 untracked files、diff scope、测试结果和文档状态。确认已通过：`if rg -n '@mui/|Mui[A-Z]' web/src/pages/OaPendingPaymentsPage.tsx web/src/components/oaPendingPayments; then exit 1; else exit 0; fi`、`cd web && npx vitest run OaPendingPaymentsPage.test.tsx`、`cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`、`cd web && npm run build`、`git diff --check`。只允许精确 `git add docs/refactor-ui/refactor_ui_state.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/modules/phase_6_oa_pending_payments.md web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx web/src/app/styles.css`；禁止 `git add .` 或 `git add -A`。commit message 使用 `feat: complete oa pending payments ui migration`。push 到 `origin refactor-ui`。完成后更新 state/prompt/module docs 的 MG execution notes、verification、Push Log，标记 MG verified，并从 `refactor-ui` 分支继续生成下一条 Micro-JIT prompt。
```
