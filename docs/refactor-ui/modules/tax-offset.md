# Tax Offset Premium Visual Discovery

本文档记录 `/tax-offset` 的 premium visual slice discovery。目标是后续把税金抵扣页打磨成银行明细 premium sample 同级的 HeroUI/Tailwind 视觉与交互质感，同时保留所有原始功能、信息结构和业务语义。

Last updated: 2026-06-08

## PV-002 Discovery

- Prompt ID: `PV-002-tax-offset-discovery`
- Type: discovery/planning
- Status: verified
- Runtime changed: no.
- Tests changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

## Boundary

### In Scope For Future Visual Slice

- Route: `/tax-offset`
- Page: `web/src/pages/TaxOffsetPage.tsx`
- Components:
  - `web/src/components/tax/TaxSummaryCards.tsx`
  - `web/src/components/tax/TaxResultPanel.tsx`
  - `web/src/components/tax/TaxTable.tsx`
  - `web/src/components/tax/CertifiedResultsDrawer.tsx`
  - `web/src/components/tax/CertifiedInvoiceImportModal.tsx`
- Related shared primitives:
  - `PageScaffold`
  - `MonthPicker`
  - `StatePanel`
  - `AppDialog`
  - `FileDropzone`
  - `FinanceTable`
  - `FinanceStatusTag`
  - `AmountCell`
  - `WorkbenchColumnFilterMenu`
- Tests: `web/src/test/TaxOffsetPage.test.tsx`

### Out Of Scope

- Backend/API contracts:
  - `GET /api/tax-offset?month=...`
  - `POST /api/tax-offset/calculate`
  - `POST /api/tax-offset/plans`
  - `POST /api/tax-offset/certified-import/preview`
  - `POST /api/tax-offset/certified-import/confirm`
  - `GET /api/tax-offset/certified-import/jobs/:jobId`
- Read model status and freshness semantics.
- Import job polling semantics.
- Permission semantics from `canMutateData`.
- Reconciliation workbench internals.
- App Shell navigation or route code splitting.

## Current User-Visible Entrypoints

| Entrypoint | Current behavior | Must preserve |
| --- | --- | --- |
| Route/sidebar | `/tax-offset`, sidebar label `税金抵扣` | Same route and menu item. |
| Page title | `税金抵扣计划与试算` | Same title and information hierarchy. |
| Page description | Explains plan, certified results, calculation and read model status | Can be visually tightened, but must not disappear unless equivalent context remains. |
| Header status note | Success/info note after import or plan save | Same feedback messages and status role. |
| Import action | `已认证发票导入` visible only when `canMutateData` | Same permission gating and same modal behavior. |
| Month picker | `MonthPicker` controls current month session state | Same `YYYY-MM` state and reload behavior. |
| Summary metrics | `销项税额`, `已认证结果进项税额`, `计划进项税额`, `本月抵扣额`, result label | Keep all five metrics; avoid oversized big-card treatment. |
| Result panel | `税金抵扣试算`, result amount, `保存计划` | Keep save button and disabled/loading behavior. |
| Output table | `销项票开票情况` read-only table | Remains table; no checkbox column. |
| Input plan table | `进项票认证计划` editable/selectable table | Remains table with checkboxes, `全选`, `清空`. |
| Shared horizontal scrollbar | `税金抵扣表格横向滚动` syncs both tables | Must remain because both tables share horizontal scanning. |
| Certified results area | `已认证结果` complementary right workspace, collapsible | Preserve right-side workspace/collapse; do not convert to route, large card, or modal. |
| Certified result item | Click matched row to highlight related input plan row | Preserve `data-certified-highlighted` behavior. |
| Import modal | `已认证发票导入` dialog | Remains dialog, not drawer or route. |
| Dropzone | `选择已认证发票文件`, accepts `.xls/.xlsx`, drag/drop | Same accepted types, invalid-file message and disabled states. |
| Preview table | `已认证发票预览结果` and per-file row table | Remains dense table with same columns. |
| Confirm import | `确认导入`, queued job progress, auto-refresh | Same polling feedback and close-on-success behavior. |
| Loading/error/empty | Loading panel, error panel, empty month panel | Keep user-visible messages and avoid exposing stale read model internals. |

## State And Data Contracts

| State | Source | Behavior to preserve |
| --- | --- | --- |
| Current month | `usePageSessionState({ pageKey: "tax-offset", stateKey: "currentMonth" })` | Session restore for selected month only; no data snapshot restore. |
| Selected input IDs | `usePageSessionState({ stateKey: "selectedInputIds" })` | Survives route remount within TTL, filtered against current selectable rows. |
| Certified results collapsed | `usePageSessionState({ stateKey: "certifiedDrawerCollapsed" })` | Collapsed state persists without keeping page mounted. |
| Initial load | `fetchTaxOffsetMonth(currentMonth)` | Shows loading while no visible data exists. |
| Refresh | window focus, visibility change, domain events, read model refreshing/stale polling | Refreshes data without showing internal read model metadata. |
| Recalculate | `POST /api/tax-offset/calculate` when selection differs from server defaults | Updates summary; first load must not duplicate calculate if server summary already matches. |
| Save plan | `POST /api/tax-offset/plans` with `expectedReadModelScopeKey`, `expectedSourceVersions`, idempotency key | Shows save feedback, handles 409 as stale-data error, refreshes after save. |
| Import preview | `POST /api/tax-offset/certified-import/preview` | Shows summary and file row preview. |
| Import confirm | `POST /api/tax-offset/certified-import/confirm` plus optional job polling | Keeps modal processing until queued job completes. |

## Tables

### Output Invoice Table

- Accessible name: `销项票开票情况`
- Current primitive: `FinanceTable`
- Column roles:
  - `identity`: `发票编号`
  - `amount`: `税额`
  - `account`: `对方名称`
  - `amount`: `金额（税率）`
- No selection column.
- Row identity cell includes:
  - invoice number
  - flow tag `销`
  - issue date tag
- Must preserve:
  - Tax amount and amount/rate right aligned.
  - Amounts use tabular nums.
  - Date/status/flow tags have stable height.
  - Table remains dense and horizontally scannable.

### Input Plan Table

- Accessible name: `进项票认证计划`
- Current primitive: `FinanceTable`
- Column roles:
  - `selection`: `选择`
  - `identity`: `发票编号`
  - `amount`: `税额`
  - `account`: `对方名称`
  - `amount`: `金额（税率）`
- Header actions:
  - `时间↓` / `时间↑` sort button.
  - `搜索 进项票认证计划` popover.
  - `筛选 对方名称` filter dialog from `WorkbenchColumnFilterMenu`.
  - `全选`, `清空`.
- Row identity cell includes:
  - invoice number
  - flow tag `进`
  - status tag such as `待认证` / `已认证`
  - issue date tag
- Must preserve:
  - Locked/certified rows have disabled checkbox.
  - Selected row and highlighted matched row remain visually distinguishable.
  - Search/filter/sort do not change row height.
  - Flow/status/date/tax-rate tags stay aligned across rows.

### Certified Import Preview Table

- Lives inside `CertifiedInvoiceImportModal`.
- Accessible name pattern: `<fileName> 行级预览结果`.
- Column roles:
  - `quantity`: `行号`
  - `identity`: `发票号码`
  - `account`: `销方`
  - `amount`: `税额`
  - `status`: `状态`
  - `status`: `重复`
  - `description`: `原因`
- Must preserve:
  - Status tags for `匹配计划`, `未进入计划`, `无效`.
  - Empty invoice/seller/tax/reason cells use shared empty value primitive.
  - Preview remains dense and readable inside dialog without large whitespace.

## Dialog / Right-Side Workspace Matrix

| UI surface | Current component | Shape to preserve | Notes |
| --- | --- | --- | --- |
| Certified import | `AppDialog` | Dialog | Do not convert to drawer. Keep title, description, close behavior, disabled Escape while confirming. |
| Certified results | `aside.tax-certified-drawer` | Right-side complementary workspace, collapsible | Despite name, this is not an overlay drawer. Keep it attached to the page's right side. |
| Counterparty filter | `WorkbenchColumnFilterMenu` | Dialog/menu-like filter surface | Preserve options, selected values, clear, Escape behavior from existing primitive. |
| Search | Custom `pane-search-popover` | Small popover anchored to table header action | Preserve searchbox labels and clear button. |

## Existing Test Coverage

| Test area | Current coverage | PV-003 implication |
| --- | --- | --- |
| Loading abort | Initial loading state clears when active request aborts | Visual slice must keep loading message and abort cleanup. |
| Main render | Summary, output table, input table, certified right workspace, no legacy back link | Keep table roles and entrypoints. |
| No snapshot restore | Route remount reloads page and shows fresh loading | Do not reintroduce keepalive or data snapshot. |
| Read-only permission | Read/export-only users cannot import or save | Preserve `canMutateData` gating. |
| Import preview/confirm | In-page dialog, dropzone, preview table, confirm, refresh, locked rows | Preserve dialog workflow and table columns. |
| Drag/drop invalid file | Dropzone accepts Excel and rejects non-Excel | Keep FileDropzone behavior. |
| Recalculate | Selection changes call calculate and update metrics | Preserve selection state and summary updates. |
| Save plan | Save payload includes read model versions and idempotency key | UI slice must not touch payload. |
| Select all / clear | Input plan header actions update checkboxes | Preserve buttons and disabled states. |
| Search/sort/filter | Both tables support inline search, time sort and counterparty filter | Preserve action names and visible filtering. |
| Flow tags | Output rows use `销` even when invoice type text lacks `销` | Do not infer display solely from invoice type. |
| Matched click highlight | Certified row click highlights related input plan row | Preserve right workspace item buttons and highlight attr. |
| Empty month | Empty message for no tax invoices | Do not show final empty while read model is refreshing. |
| Focus refresh | Regains focus refreshes summary, locks and drawer rows | Preserve refresh trigger behavior. |
| Read model refreshing | Hides internal stale metadata and avoids false empty state | Preserve user-facing stale handling. |
| Queued import job | Modal remains processing until queued import job succeeds | Preserve progress messaging and polling. |

## Premium Visual Requirements For PV-003

- Keep the overall large layout: summary/result on top, two synchronized tables left, certified results workspace right.
- Avoid big card redesign. Use compact surfaces, subtle section bands, dense headers and tight table controls.
- Summary metrics should feel premium but not become oversized marketing cards.
- Use existing shared tokens from `DESIGN.md` and `interaction_smoothness.md`.
- Prefer HeroUI primitives already in use:
  - HeroUI `Button`, `Alert`, `Chip`, `Checkbox`, `ProgressBar`.
  - Shared `AppDialog`, `FileDropzone`, `FinanceTable`, `FinanceStatusTag`, `AmountCell`, `StatePanel`.
- Do not introduce new dependencies.
- Do not touch API or data mapping.
- Improve interaction smoothness locally:
  - table header controls get immediate hover/press feedback,
  - selected/highlighted rows have stable affordance,
  - right workspace collapse feels immediate,
  - dialog/dropzone/progress states preserve layout.
- Do not add route transition or page-level animation delay.

## Known Visual Opportunities

- `stats-row` / `stat-card` can be tightened into a compact metric strip aligned with bank details premium sample.
- `tax-result-panel` can become a denser decision/status band with right-aligned result amount and save action.
- `tax-panel-header` can be aligned to the shared toolbar rhythm; search/filter/sort/actions should have consistent button sizing.
- `tax-certified-drawer` can be polished as a right-side working rail with clear group headers, stable counts and compact list rows.
- `certified-import` preview can use a tighter table/summary hierarchy inside the existing dialog.
- Tags (`销`, `进`, `待认证`, date, tax rate) should use stable heights and widths so rows align vertically.

## PV-003 Acceptance Checklist

- No backend/API/read model/worker diff.
- No workbench internal diff.
- No new `@mui/*` runtime imports.
- Existing `TaxOffsetPage.test.tsx` passes.
- Source-level or DOM tests still prove:
  - output/input table column roles,
  - import dialog remains `finance-dialog`,
  - certified results remains `role="complementary"`,
  - read-only permission hides import/save,
  - no data snapshot restore.
- `git diff --check`, forbidden keepalive grep and non-workbench MUI grep pass.

## PV-003 Premium Visual Implementation

- Prompt ID: `PV-003-tax-offset-premium-visual`
- Type: implementation
- Status: verified
- Runtime changed: CSS-only visual/interaction polish plus tax summary class names.
- Tests changed: yes, source/style contract in `TaxOffsetPage.test.tsx`.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

### Changes

- Added scoped `tax-summary-strip` and `tax-summary-card` classes so Tax Offset metrics can be polished without affecting Cost Statistics `stat-card` usage.
- Tightened the metrics into a compact five-column strip with tabular numeric values and tokenized success/warning treatments.
- Converted `tax-result-panel` from a large rounded gradient card into a compact decision band with a Ledger Blue left rule and right-aligned result amount.
- Lightened `tax-panel-header` and table tool buttons to match the premium finance surface while preserving search/sort/filter button names.
- Stabilized tax tags with `--fp-tag-height-table`, tokenized radii, stable min widths and fast motion-token transitions.
- Polished selected, locked and certified-highlighted table rows without changing row height.
- Polished the right-side `已认证结果` complementary workspace as a compact working rail; it remains an attached right workspace, not an overlay drawer.
- Tightened certified import modal file-list spacing without changing dropzone, preview table or queued job behavior.

### Verification

Passed:

- `cd web && npx vitest run TaxOffsetPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- Forbidden legacy page-cache/snapshot grep over runtime and module docs.
- `if rg -n "(@mui/material|@mui/icons-material|@mui/x-|from ['\"]@mui/)" web/src --glob '!components/workbench/**' --glob '!**/test/**'; then exit 1; else exit 0; fi`
- Browser smoke with system Chrome and mocked `/api/*` at `http://127.0.0.1:4173/tax-offset`.

Browser smoke evidence:

- Grids: 2.
- Metrics: 5.
- `role="complementary"` / `已认证结果`: 1.
- `已认证发票导入` button: 1.
- Top-level horizontal overflow: 0.
- Screenshot: `/tmp/tax-offset-premium-smoke.png`.

Notes:

- `npm run build` still emits existing HeroUI/Tailwind CSS minify warnings; build exits successfully.
