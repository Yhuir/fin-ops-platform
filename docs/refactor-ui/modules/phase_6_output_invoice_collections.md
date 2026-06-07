# Phase 6 Output Invoice Collections

本文档记录 `/output-invoice-collections` 的 UI 迁移 discovery、旧入口对照、测试策略和后续 Micro-JIT prompt。目标是迁出非关联台 MUI，同时保持用户使用感受不变。

## P065 Discovery

- Prompt ID: `P065-phase-6-output-invoice-collections-discovery`
- Type: discovery/planning
- Status: verified
- Scope: `/output-invoice-collections` only.
- Implementation changed: no.
- Tests changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

## Current Files

| Area | Files | Notes |
| --- | --- | --- |
| Page | `web/src/pages/OutputInvoiceCollectionsPage.tsx` | Page shell, actions, keyword/month/status query controls, summary tiles, loading/error/empty, table and all workflow drawer wiring. |
| Table | `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx` | Grouped dense table, filter menu, sorting, expandable cells, row workflow buttons and server pagination. |
| Filter menu | `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx` | Text/date/money/enum filter popover plus asc/desc sorting. |
| Cell helper | `web/src/components/outputInvoiceCollections/ExpandableCellText.tsx` | Expand/collapse control for long table values. |
| Detail drawer | `OutputInvoiceCollectionDetailDrawer.tsx` | Right drawer for invoice, bank and relation-list details. |
| Rules drawer | `CollectionStatusRulesDrawer.tsx` | Read-only right drawer for Sheet6 collection status rules. |
| Status/reminder drawer | `CollectionStatusReminderDrawer.tsx` | Right drawer for manual collection status and reminder actions. |
| Red relation drawer | `RedInvoiceRelationDrawer.tsx` | Right drawer for red/blue invoice relation confirm/revoke. |
| Receipt history drawer | `ReceiptHistoryDrawer.tsx` | Right drawer for issued receipts plus internal void/reissue confirmation dialogs. |
| Receipt preview drawer | `ReceiptPreviewDrawer.tsx` | Right drawer for receipt preview and formal receipt creation. |
| Receipt settings drawer | `ReceiptSettingsDrawer.tsx` | Admin-only right drawer for receipt number settings. |
| API/types | `web/src/features/outputInvoiceCollections/api.ts`, `types.ts` | Rows, filter options, details, status rules, receipt history/preview/settings and lifecycle write routes. No migration prompt may change these contracts. |
| Tests | `web/src/test/OutputInvoiceCollectionsPage.test.tsx` | Route/sidebar, grouped table, filter/sort/pagination, read-model refreshing, keep-alive activation, all workflow drawers and lifecycle writes. |

## Current MUI Inventory

| File | Current MUI usage | Target |
| --- | --- | --- |
| `OutputInvoiceCollectionsPage.tsx` | `RefreshOutlinedIcon`, `Alert`, `Box`, `Button`, `MenuItem`, `Paper`, `Skeleton`, `Stack`, `TextField`, `Typography` | Project/native page shell controls, summary tiles, loading skeleton/status message and lucide icons. |
| `OutputInvoiceCollectionsTable.tsx` | `SortOutlinedIcon`, `Box`, `Button`, `Chip`, `IconButton`, `Paper`, `Stack`, `Table*`, `TablePagination`, `Tooltip`, `Typography`, `SxProps`, `Theme`, inline `col style` | Project/native grouped dense table, project tags/buttons, native/project pagination, lucide icons and tokenized styles. |
| `OutputInvoiceCollectionFilterMenu.tsx` | MUI icons, `Button`, `Checkbox`, `Divider`, `ListItem*`, `Menu`, `MenuItem`, `Radio`, `Stack`, `TextField`, `Typography`, `.MuiButton-startIcon` selector | Project/native popover/menu controls, checkbox/radio/input/select primitives, lucide icons. |
| `ExpandableCellText.tsx` | MUI expand icons, `Box`, `IconButton`, `Stack`, `Tooltip`, `Typography` | Project text clamp/expand control and lucide icons. |
| `OutputInvoiceCollectionDetailDrawer.tsx` | MUI right `Drawer`, close icon, `Alert`, `CircularProgress`, `Paper`, layout/text components | `AppDrawer`, project loading/alert/sections. |
| `CollectionStatusRulesDrawer.tsx` | MUI right `Drawer`, table, tags, loading and layout components | `AppDrawer`, project read-only table/tags/loading. |
| `CollectionStatusReminderDrawer.tsx` | MUI right `Drawer`, form controls/buttons/dividers/text | `AppDrawer`, native/project form controls and actions. |
| `RedInvoiceRelationDrawer.tsx` | MUI right `Drawer`, radio group, text fields, buttons and alert | `AppDrawer`, native/project radio/search/form/actions. |
| `ReceiptHistoryDrawer.tsx` | MUI right `Drawer` plus internal MUI `Dialog`, form and buttons | `AppDrawer` plus `AppDialog`; keep right drawer and confirmation dialogs. |
| `ReceiptPreviewDrawer.tsx` | MUI right `Drawer`, radio group, tags, preview card/loading/actions | `AppDrawer`, project preview surface and native/project selection. |
| `ReceiptSettingsDrawer.tsx` | MUI right `Drawer`, text fields/select/buttons | `AppDrawer`, native/project form controls. |

## User-visible Entrypoints

| Entrypoint | Current behavior to preserve |
| --- | --- |
| Route/sidebar | `/output-invoice-collections`, sidebar label `销项发票收款情况`, page heading `销项发票收款情况`. |
| Top actions | `收款状态规则` opens read-only rules right drawer; admin-only `收据编号设置` opens settings right drawer; `刷新` reloads rows and disables while refreshing. |
| Query controls | `关键字`, `查询`, `月份`, quick `收款状态` select. Enter in keyword submits. |
| Summary tiles | `销项发票数`, `待收款金额`, `已收金额`, `待出收据数`; numeric values stay tabular and formatted. |
| Table | Accessible name `销项发票收款情况表`; group headers `销项发票`, `收款状态`, `收入流水`, `收据`; 10 leaf columns. |
| Filter menu | `筛选 <field>` buttons; supports asc/desc sort, enum multi/single, text contains/equals, money/date between and clear/apply. |
| Sorting | Header sort buttons such as `发票号码 排序` preserve backend query params `sort_field` and `sort_direction`. |
| Expandable cells | Expand/collapse labels for long invoice business, collection status reason, bank counterparty and bank summary text. |
| Row detail actions | `查看发票 <no> 详情`, `查看流水 <counterparty> 详情` open the detail right drawer. |
| Row workflow actions | `状态/提醒`, `红蓝票`, `已出收据`, `待出收据` stay in the same table cells and open the same right drawers. |
| Rules drawer | Right drawer `收款状态规则`; read-only, no save/submit action. |
| Detail drawer | Right drawer `销项发票收款情况详情`; unavailable state remains neutral and backend-driven. |
| Status/reminder drawer | Right drawer `收款状态和提醒`; preserves `撤销手动状态`, `取消提醒`, `保存`, notes and expected date fields. |
| Red relation drawer | Right drawer `红蓝票关系`; preserves candidate search/radio, relation type, evidence, `确认关系`, and revoke artificial relation action. |
| Receipt history drawer | Right drawer `已出收据历史`; preserves issued receipt list and internal `作废收据原因` / `重开收据原因` confirmation dialogs. |
| Receipt preview drawer | Right drawer `待出收据预览`; preserves backend preview, bank transaction choice, disabled create behavior when unavailable, and formal receipt creation action. |
| Receipt settings drawer | Right drawer `收据编号设置`; admin-only, preserves prefix, next sequence, reset policy and save. |
| Empty/loading/error | Loading label `销项发票收款情况加载中`, empty state `当前条件下暂无记录。`, table empty row `当前条件下没有销项发票收款记录。`, error text from rows fetch. |

## API / Read Model Boundary

- Rows: `GET /api/output-invoice-collections/rows`.
- Filter options: `GET /api/output-invoice-collections/filter-options`.
- Details:
  - `GET /api/output-invoice-collections/invoices/:id/detail`
  - `GET /api/output-invoice-collections/bank-transactions/:id/detail`
  - `GET /api/output-invoice-collections/rows/:rowId/relation-details?kind=bank|red_invoice|receipt`
- Rules/history/preview/settings:
  - `GET /api/output-invoice-collections/status-rules`
  - `GET /api/output-invoice-collections/receipts/history?invoice_id=...`
  - `GET|PUT /api/output-invoice-collections/receipt-settings`
  - `POST /api/output-invoice-collections/receipt-preview`
- Lifecycle writes:
  - `PUT /api/output-invoice-collections/rows/{row_id}/collection-status`
  - `PUT /api/output-invoice-collections/rows/{row_id}/collection-reminder`
  - `DELETE /api/output-invoice-collections/rows/{row_id}/collection-reminder/{reminder_id}`
  - `POST /api/output-invoice-collections/rows/{row_id}/red-invoice-relations`
  - `DELETE /api/output-invoice-collections/red-invoice-relations/{relation_id}`
  - `POST /api/output-invoice-collections/rows/{row_id}/receipts`
  - `POST /api/output-invoice-collections/receipts/{receipt_id}/void`
  - `POST /api/output-invoice-collections/receipts/{receipt_id}/reissue`
- UI migration must not change request params: `page`, `page_size`, `keyword`, `month`, `filters`, `sort_field`, `sort_direction`.
- Write payloads, idempotency keys, versions, permissions and read model refreshing/stale behavior must remain backend-driven.

## Existing Test Coverage

| Test | Current coverage | Migration implication |
| --- | --- | --- |
| read-model refreshing tests | Hides read-model internals, reloads after activation/refreshing. | Page shell refactor must preserve retry/activation behavior and user-facing empty/loading text. |
| `adds sidebar route and renders grouped MUI Table layout without fake export` | Route/sidebar, no DataGrid, no fake export, grouped headers, row cells, expanders, sort, filters, pagination. | P066 should rename MUI wording and add source-level project primitive contracts. |
| `opens the three right-side workflow drawers without reloading the main rows` | Rules, receipt history, receipt preview right drawers and row fetch stability. | Drawer slices must not reload rows just by opening read-only/history/preview drawers. |
| `closes lifecycle actions from drawers and exposes receipt settings only to admins` | Status/reminder, red relation, receipt void/reissue dialogs and settings writes. | Must keep right drawer/dialog shapes, button labels and write payloads. |

## Migration Slice Plan

1. `P066-phase-6-output-invoice-collections-characterization-tests`
   - Convert MUI wording/class assertions to behavior/project primitive assertions.
   - Add source-level contracts for page, table, filter menu, expandable text and drawer files.
2. `P067-phase-6-output-invoice-collections-page-shell`
   - Migrate page actions, query controls, summary tiles, loading/error shell.
   - Do not migrate table/filter/drawers.
3. `P068-phase-6-output-invoice-collections-filter-and-expandable`
   - Migrate `OutputInvoiceCollectionFilterMenu` and `ExpandableCellText`.
   - Preserve filter/sort labels and query behavior.
4. `P069-phase-6-output-invoice-collections-grouped-table`
   - Migrate grouped table, row actions, tags, pagination and table styles.
   - Preserve workflow/detail target mapping.
5. `P070-phase-6-output-invoice-collections-simple-drawers`
   - Migrate detail and rules right drawers.
6. `P071-phase-6-output-invoice-collections-workflow-drawers`
   - Migrate status/reminder, red relation, receipt preview and receipt settings right drawers.
7. `P072-phase-6-output-invoice-collections-receipt-history`
   - Migrate receipt history right drawer and internal void/reissue dialogs.
8. `MG-P072-phase-6-output-invoice-collections`
   - Verify module no-MUI residue, tests, build and exact push.

## Risks

- This module contains lifecycle write actions; UI refactor must not invent success states, mutate payload shapes or hide backend permission semantics.
- Receipt history has nested dialogs inside a right drawer; old drawer/dialog shapes must remain distinct.
- The filter menu is not shared with input invoice usage; do not accidentally change `InputInvoiceUsageFilterMenu`.
- The table is a 4-zone dense financial table; new UI must stay a table and not become cards.
- Receipt preview uses backend-rendered facts; do not generate fake receipt content.
- Admin-only `收据编号设置` must remain permission-gated.

## P066 Prompt Draft

```text
Prompt ID: P066-phase-6-output-invoice-collections-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/output-invoice-collections` tests only. Do not modify runtime implementation.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/OutputInvoiceCollectionsPage.tsx、web/src/components/outputInvoiceCollections/*、web/src/features/outputInvoiceCollections/* 和 web/src/test/OutputInvoiceCollectionsPage.test.tsx。只修改 `web/src/test/OutputInvoiceCollectionsPage.test.tsx`：把 “grouped MUI Table” wording 和 MUI/DataGrid/class-based expectations 改成 behavior/project primitive assertions；新增 source-level contracts，锁定 page/table/filter/expandable/drawer files 未来不再依赖 `@mui/*`、`Mui[A-Z]`、`TablePagination`、`TextField`、`Skeleton`、`Chip`、`IconButton`、`TableCell`、`TableRow`、`TableHead`、`TableBody`、`Drawer`、`Dialog`；新增或保留行为断言确保 route/sidebar、page heading、query controls、summary tiles、refresh/status-rules/settings buttons、group headers、10 leaf columns、filter menu labels and operators、sort query, expand/collapse controls, detail right drawer labels, status/reminder/red relation/receipt history/receipt preview/receipt settings right drawers, receipt void/reissue dialogs, empty/loading/error/read-model refreshing behavior and lifecycle write payloads保留。不得修改实现、mock、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P067 page shell prompt。
```

## Execution Update: P066 Characterization Tests

- Status: verified as expected-fail.
- Files changed:
  - `web/src/test/OutputInvoiceCollectionsPage.test.tsx`
- Runtime implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - Renamed the main behavior test away from MUI wording.
  - Replaced the `.MuiDataGrid-root` absence check with the user-observable table role `销项发票收款情况表`.
  - Added source-level contracts for page shell, grouped table, filter menu, expandable text and all output invoice collection drawers.
  - Source-level drawer contracts intentionally allow future `AppDrawer`/`AppDialog` project primitives while forbidding MUI imports and legacy MUI surface names.
- Verification:
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail, 5 behavior tests passed and 1 source-level contract failed. Current failure lists page/table/filter/expandable/drawer MUI imports, `.MuiButton-startIcon`, legacy MUI surfaces, missing project table class, missing `AppDrawer` and missing `AppDialog`.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P066 test file changed before docs.

## Current Expected Failures After P066

- `src/pages/OutputInvoiceCollectionsPage.tsx`: still imports MUI page shell/query/summary/loading controls; P067 owns this.
- `src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx` and `ExpandableCellText.tsx`: still import MUI menu/filter/expand controls and `.MuiButton-startIcon`; P068 owns this.
- `src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx`: still imports MUI grouped table/tag/button/pagination controls; P069 owns this.
- Output invoice collection drawer files still import MUI right drawer/form/table/dialog controls; P070-P072 own these.

## P067 Prompt Draft

```text
Prompt ID: P067-phase-6-output-invoice-collections-page-shell
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/output-invoice-collections` page shell/actions/query/summary/loading/error only. Do not migrate table, filter menu, expandable text or drawer internals.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、web/src/pages/OutputInvoiceCollectionsPage.tsx、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx、web/src/components/common/PageScaffold.tsx、web/src/components/common/PageToolbar.tsx、web/src/components/common/StatePanel.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/OutputInvoiceCollectionsPage.tsx`、必要 `web/src/app/styles.css` 和必要测试 expectation：移除 page shell/actions/query/summary/loading/error scope 的 MUI imports/usages，包括 `RefreshOutlinedIcon`、`Alert`、`Box`、`Button`、`MenuItem`、`Paper`、`Skeleton`、`Stack`、`TextField`、`Typography`。使用 project/native toolbar controls、native text/month/select inputs、project summary tiles/loading skeleton/status message and lucide icons。必须保留 `data-testid="output-invoice-collections-page"`、heading `销项发票收款情况`、description、buttons `收款状态规则`/admin-only `收据编号设置`/`刷新`、refresh disabled while refreshing、query labels `关键字`/`查询`/`月份`/`收款状态`、Enter submit、quick status options from backend rules/options, summary labels `销项发票数`/`待收款金额`/`已收金额`/`待出收据数`、loading label `销项发票收款情况加载中`、empty state `当前条件下暂无记录。`、error text, table props and all drawer wiring。不得修改 `OutputInvoiceCollectionsTable.tsx`、filter menu、expandable text、drawer internals、mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route|uses a standard empty state|pauses read model"`；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`，P068-P072 source contract failures 可以继续 expected-fail，但 `src/pages/OutputInvoiceCollectionsPage.tsx` must disappear from source-level failure lists；运行 `cd web && npm run build`；运行 page shell MUI grep：`if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|Skeleton|TextField|MenuItem|Paper|Typography' web/src/pages/OutputInvoiceCollectionsPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P068 filter and expandable prompt。
```
