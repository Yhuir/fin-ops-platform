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
| Tests | `web/src/test/OutputInvoiceCollectionsPage.test.tsx` | Route/sidebar, grouped table, filter/sort/pagination, read-model refreshing, route remount cleanup, all workflow drawers and lifecycle writes. |

## PV-016 Premium Visual Discovery

- Prompt ID: `PV-016-output-invoice-collections-discovery`
- Type: premium visual discovery
- Status: verified
- Scope: `/output-invoice-collections` only.
- Implementation changed: no.
- Tests changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

### Current Implementation Status On `main`

- Page shell, toolbar actions, query controls, summary metrics, loading/error/empty states and drawer wiring already use project/native primitives.
- The main table is a project-owned grouped native table, not a card layout and not MUI DataGrid.
- The filter menu and expandable text controls are project-owned components.
- Right-side workflows already use `AppDrawer`; receipt history keeps internal `AppDialog` confirmation flows for void/reissue.
- Scoped runtime source has no `@mui/*` imports outside the frozen workbench boundary.

### User-visible Entrypoint Matrix

| Area | Preserve exactly |
| --- | --- |
| Route/sidebar | `/output-invoice-collections`, sidebar label `销项发票收款情况`, page heading `销项发票收款情况`. |
| Header actions | `收款状态规则`, admin-only `收据编号设置`, `刷新`; keep button locations and disabled/loading behavior. |
| Query controls | `关键字`, `查询`, `月份`, quick `收款状态`; Enter in keyword submits. |
| Summary metrics | `销项发票数`, `待收款金额`, `已收金额`, `待出收据数`; values remain formatted and tabular. |
| Main table | Table accessible name `销项发票收款情况表`; keep grouped dense table, not cards. |
| Filter menu | `筛选 <field>` triggers, asc/desc sorting, enum/text/money/date operators, clear/apply behavior. |
| Sorting | Header sort buttons such as `发票号码 排序`; preserve backend `sort_field` and `sort_direction`. |
| Expandable cells | Long invoice business, collection status reason, bank counterparty and bank summary text keep expand/collapse controls. |
| Row detail actions | `查看发票 <no> 详情` and `查看流水 <counterparty> 详情` open the detail right drawer. |
| Row workflow actions | `状态/提醒`, `红蓝票`, `已出收据`, `待出收据` remain in their table cells and open the same workflows. |
| Right drawers | `收款状态规则`, `销项发票收款情况详情`, `收款状态和提醒`, `红蓝票关系`, `已出收据历史`, `待出收据预览`, `收据编号设置`. |
| Internal dialogs | Receipt void/reissue confirmations stay dialogs inside the receipt history workflow. |
| States | Loading label `销项发票收款情况加载中`, empty state `当前条件下暂无记录。`, table empty row `当前条件下没有销项发票收款记录。`, backend error text, read-model refreshing/stale behavior and admin permission gating. |

### Table Content Roles

| Group | Columns | Premium layout requirement |
| --- | --- | --- |
| `销项发票` | `发票号码`, `购方`, `价税合计`, `税额/税率`, `业务/货物劳务` | Invoice number and buyer identity stack stay compact; issue date uses a stable tag; amount/tax columns right-align with tabular nums; long business text clamps/expands without changing row rhythm unexpectedly. |
| `收款状态` | `收款状态` | Status tag, status reason, collected/pending amounts and `状态/提醒` action remain vertically aligned; tag height and action placement stay stable across statuses. |
| `收入流水` | `付款方/日期`, `收款金额`, `银行/摘要` | Counterparty/date and bank summary stay readable in dense rows; collected amount right-aligns with tabular nums; detail action remains beside bank identity. |
| `收据` | `收据情况` | Receipt tags and `已出收据` / `待出收据` actions stay in the receipt zone and do not wrap into neighboring columns. |

### PV-017 Premium Opportunities

- Replace hard-coded output-invoice group/sub-header washes with `DESIGN.md` token-based `color-mix(...)` treatments.
- Keep the table viewport compact and stable; avoid large card treatment and avoid large vertical gaps.
- Add motion-token feedback to output-invoice page buttons, query fields, filter menu trigger/items/apply, expandable controls, sort/table row actions, pagination controls and output-specific drawer buttons where scoped CSS exists.
- Tighten loading skeleton, alert, summary metric and drawer inner surfaces to match the bank details premium sample without changing information hierarchy.
- Add a CSS contract test in `OutputInvoiceCollectionsPage.test.tsx` that locks compact table treatment, token colors and motion-token usage.

### Non-scope For PV-017

- Do not change backend routes, API params, write payloads, read model freshness, permission semantics or worker behavior.
- Do not change route/sidebar labels, action count, row workflow mapping, drawer/dialog type or table column count.
- Do not create a dashboard of big cards; the main experience remains a dense finance table.
- Do not touch the frozen reconciliation workbench internals.

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

## Execution Update: P067 Page Shell

- Status: verified as expected-fail.
- Files changed:
  - `web/src/pages/OutputInvoiceCollectionsPage.tsx`
  - `web/src/app/styles.css`
  - `web/src/test/OutputInvoiceCollectionsPage.test.tsx`
- Runtime changed:
  - Migrated page actions, query toolbar, summary tiles, loading skeleton and error alert from MUI to project/native controls.
  - Replaced the refresh icon with `lucide-react`.
  - Preserved route/sidebar, heading, description, refresh behavior, status rules/settings actions, query labels, Enter submit, quick status options, summary labels, empty/loading/error text, table props and all drawer wiring.
- Table/filter/expandable/drawers changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|Skeleton|TextField|MenuItem|Paper|Typography' web/src/pages/OutputInvoiceCollectionsPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route|uses a standard empty state|pauses read model"`: expected-fail; selected behavior tests passed and the remaining source-level failure lists only table/filter/expandable/drawer files.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail; 5 behavior tests passed and 1 source-level contract failed, limited to table/filter/expandable/drawer residue.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P067 files and docs changed.

## P068 Execution Notes

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx`
  - `web/src/components/outputInvoiceCollections/ExpandableCellText.tsx`
  - `web/src/app/styles.css`
- Behavior preserved:
  - Filter trigger aria-label `筛选 <field label>`.
  - Menu aria-label `<field label>筛选与排序`.
  - Sort actions `升序排序` and `降序排序`.
  - Enum actions `全选`、`清空`、`暂无可选项`.
  - `menuitemcheckbox` / `menuitemradio` roles and labels with counts.
  - Text/money/date labels and `应用筛选`.
  - Enter apply behavior and clear/apply/sort prop contracts.
  - Expand/collapse aria labels and two-line collapsed text behavior.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|FilterListOutlinedIcon|ArrowDownwardOutlinedIcon|ArrowUpwardOutlinedIcon|ExpandLessOutlinedIcon|ExpandMoreOutlinedIcon|TextField|MenuItem|Checkbox|Radio|IconButton|Tooltip|MuiButton-startIcon' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx web/src/components/outputInvoiceCollections/ExpandableCellText.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route"`: expected-fail; main behavior test passed and remaining source-level failure lists only table and drawer files.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail; 5 behavior tests passed and 1 source-level contract failed, limited to table/drawer residue.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P068 implementation files changed before docs.

## Current Expected Failures After P068

- `src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx`: still imports MUI grouped table/tag/button/pagination controls; P069 owns this.
- Output invoice collection drawer files still import MUI right drawer/form/table/dialog controls; P070-P072 own these.
- `src/pages/OutputInvoiceCollectionsPage.tsx`: cleared from source-level no-MUI failure lists.
- `src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx` and `ExpandableCellText.tsx`: cleared from source-level no-MUI failure lists.

## P069 Prompt Draft

```text
Prompt ID: P069-phase-6-output-invoice-collections-grouped-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `OutputInvoiceCollectionsTable.tsx` grouped dense table only, plus necessary styles/tests. Do not migrate drawer internals.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、docs/refactor-ui/table_layout_system.md、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx、web/src/components/outputInvoiceCollections/ExpandableCellText.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 grouped table 的 MUI imports/usages，包括 `SortOutlinedIcon`、`Box`、`Button`、`Chip`、`IconButton`、`Paper`、`Stack`、`Table*`、`TablePagination`、`Tooltip`、`Typography`、`SxProps`、`Theme` 和 inline `col style`。使用 project/native grouped dense table, project tags/buttons, native/project pagination, lucide icons and tokenized table styles。必须保留 `aria-label="销项发票收款情况表"`、group headers `销项发票`/`收款状态`/`收入流水`/`收据`、10 leaf columns, filter menu prop contract, sort button labels such as `发票号码 排序`, backend sort/filter behavior, expanded cell controls, status cell class `.output-invoice-collection-status-cell`, row buttons `详情`/`状态/提醒`/`红蓝票`/`已出收据`/`待出收据`, detail/workflow target mapping, empty row `当前条件下没有销项发票收款记录。`, pagination label `每页行数`, options `[20, 50, 100]` and displayed range。不得修改 page shell, filter menu/expandable except import compatibility if required, drawer internals, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route|opens the three right-side workflow drawers"`，P070-P072 drawer source failures 可以继续 expected-fail，但 table file must disappear from source-level failure lists；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` expected-fail only for drawers；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 table MUI grep：`if rg -n '@mui/|Mui[A-Z]|TablePagination|SortOutlinedIcon|TableCell|TableRow|TableHead|TableBody|Chip|IconButton|SxProps|Theme' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P070 simple drawers prompt。
```

## P069 Execution Notes

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx`
  - `web/src/app/styles.css`
- Behavior preserved:
  - Table aria-label `销项发票收款情况表`.
  - Group headers `销项发票`、`收款状态`、`收入流水`、`收据`.
  - 10 leaf columns and filter menu contracts.
  - Sort button labels and backend sort/filter behavior.
  - Expanded cell controls and `.output-invoice-collection-status-cell`.
  - Row buttons `详情`、`状态/提醒`、`红蓝票`、`已出收据`、`待出收据`.
  - Detail/workflow target mapping and pagination label/options/range/actions.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|TablePagination|SortOutlinedIcon|TableCell|TableRow|TableHead|TableBody|Chip|IconButton|SxProps|Theme' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|adds sidebar route|opens the three right-side workflow drawers"`: expected-fail; selected behavior tests passed and remaining source-level failure lists only seven drawer files.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail; 5 behavior tests passed and 1 source-level contract failed, limited to drawer residue.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed; 15 tests passed.
  - `cd web && npm run build`: passed after fixing sort button field narrowing; known HeroUI/Tailwind CSS minifier warnings and chunk size warning remain.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P069 table/style files changed before docs.

## Current Expected Failures After P069

- `src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx`: cleared from source-level no-MUI failure lists.
- `src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx`: still imports MUI right drawer/detail/loading/card controls; P070 owns this.
- `src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx`: still imports MUI right drawer/rules/table/tag controls; P070 owns this.
- `src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx`: still imports MUI right drawer/form controls; P070 owns this.
- `src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx`: workflow drawer remains P071.
- `src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx`: workflow drawer remains P071.
- `src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx`: lifecycle drawer/dialog remains P072.
- `src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx`: receipt preview drawer remains P072.

## P070 Prompt Draft

```text
Prompt ID: P070-phase-6-output-invoice-collections-simple-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `OutputInvoiceCollectionDetailDrawer.tsx`, `CollectionStatusRulesDrawer.tsx` and `ReceiptSettingsDrawer.tsx` only, plus necessary styles/tests. Do not migrate status reminder, red relation, receipt history or receipt preview drawers.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、web/src/components/common/AppDrawer.tsx、web/src/components/common/StatePanel.tsx、web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx、web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx、web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除这三个简单抽屉的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Box`、`Button`、`Chip`、`CircularProgress`、`Divider`、`Drawer`、`IconButton`、`MenuItem`、`Paper`、`Stack`、`Table*`、`TextField` 和 `Typography`。使用 `AppDrawer` 保持右侧抽屉形态，使用 project/native loading/error panels, native buttons, native inputs/selects, native table/card layouts and lucide close icon。必须保留 `aria-label`：详情抽屉 `销项发票收款情况详情`、规则抽屉 `收款状态规则`、设置抽屉 `收据编号设置`；保留关闭按钮 labels `关闭详情抽屉`、`关闭收款状态规则`、`关闭收据编号设置`；保留 loading labels `正在加载详情`、`正在加载收款状态规则`；保留详情 unavailable/empty 文案、规则表 `Sheet6 销项发票收款情况规则` 与 columns `收款状态`/`识别方式`/`规则`/`必要事实`/`优先级`、版本/只读 tag、后续服务边界；保留设置表单 labels `编号前缀`/`重置周期`、options `每月重置`/`每年重置`/`不按日期重置`、buttons `取消`/`保存收据编号设置`、loading/submitting disabled behavior and uppercase prefix transform。不得修改 page shell/table/filter/expandable, status reminder/red relation/receipt history/receipt preview drawers, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|opens the three right-side workflow drawers|closes lifecycle actions"`，P071-P072 drawer source failures 可以继续 expected-fail，但 these three simple drawer files must disappear from source-level failure lists；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` expected-fail only for status reminder/red relation/receipt history/receipt preview drawers；运行 `cd web && npm run build`；运行 simple drawer MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|TextField|MenuItem|TableCell|TableRow|TableHead|TableBody|Chip|IconButton|DialogTitle|DialogContent|DialogActions' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P071 workflow drawers prompt。
```

## P070 Execution Notes

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx`
  - `web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx`
  - `web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx`
  - `web/src/app/styles.css`
- Behavior preserved:
  - Detail, rules and receipt settings remain right-side drawers.
  - Close labels, loading labels, detail unavailable/empty text, rules columns, version/read-only tags and settings form labels/options/buttons are preserved.
  - Receipt settings still uppercases prefix and keeps loading/submitting disabled behavior.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|TextField|MenuItem|TableCell|TableRow|TableHead|TableBody|Chip|IconButton|DialogTitle|DialogContent|DialogActions' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|opens the three right-side workflow drawers|closes lifecycle actions"`: expected-fail; selected behavior tests passed and remaining source-level failure lists only four workflow/lifecycle drawer files.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail; 5 behavior tests passed and 1 source-level contract failed, limited to four drawer files.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P070 implementation files changed before docs.

## Current Expected Failures After P070

- `src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx`: cleared from source-level no-MUI failure lists.
- `src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx`: cleared from source-level no-MUI failure lists.
- `src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx`: cleared from source-level no-MUI failure lists.
- `src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx`: workflow drawer remains P071.
- `src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx`: workflow drawer remains P071.
- `src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx`: lifecycle drawer/dialog remains P072.
- `src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx`: receipt preview drawer remains P072.

## P071 Prompt Draft

```text
Prompt ID: P071-phase-6-output-invoice-collections-workflow-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `CollectionStatusReminderDrawer.tsx` and `RedInvoiceRelationDrawer.tsx` only, plus necessary styles/tests. Do not migrate receipt history or receipt preview drawers.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、web/src/components/common/AppDrawer.tsx、web/src/components/common/StatePanel.tsx、web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx、web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除这两个 workflow 抽屉的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Button`、`Divider`、`Drawer`、`FormControlLabel`、`IconButton`、`MenuItem`、`Radio`、`RadioGroup`、`Stack`、`TextField` 和 `Typography`。使用 `AppDrawer` 保持右侧抽屉形态，使用 project/native fields, selects, textarea, radio inputs, buttons and StatePanel error。必须保留 `aria-label`/accessible name：`收款状态和提醒`、`红蓝票关系`；保留关闭 labels `关闭收款状态抽屉`、`关闭红蓝票关系抽屉`；保留字段 labels `手动状态`、`预计收款日期`、`状态备注`、`提醒时间`、`提醒备注`、`搜索关联发票`、`关联发票候选`、`关系类型`、`确认依据`；保留 buttons `撤销手动状态`、`取消提醒`、`取消`、`保存`、`撤销人工关系 <invoiceNo>`、`确认关系`；保留 status submit payload、reminder submit payload、clear/cancel reminder calls、candidate search/filter, radio candidate labels, relation type options `红字发票`/`蓝字发票`, evidence validation, confirm/revoke payloads and disabled/submitting behavior。不得修改 page shell/table/filter/expandable, simple drawers, receipt history/receipt preview drawers, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|closes lifecycle actions"`，P072 receipt source failures 可以继续 expected-fail，但 these two workflow drawer files must disappear from source-level failure lists；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` expected-fail only for receipt history/receipt preview drawers；运行 `cd web && npm run build`；运行 workflow drawer MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|TextField|MenuItem|FormControlLabel|RadioGroup|Radio|IconButton|DialogTitle|DialogContent|DialogActions' web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P072 receipt history and preview prompt。
```

## P071 Execution Notes

- Status: verified as expected-fail.
- Files changed:
  - `web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx`
  - `web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx`
  - `web/src/app/styles.css`
- Behavior preserved:
  - Status/reminder and red/blue relation remain right-side drawers.
  - Field labels, close labels, action buttons, status/reminder payloads, clear/cancel calls, candidate search/filter, radio candidate labels, relation type options and confirm/revoke payloads are preserved.
- Verification:
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|TextField|MenuItem|FormControlLabel|RadioGroup|Radio|IconButton|DialogTitle|DialogContent|DialogActions' web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|closes lifecycle actions"`: expected-fail; lifecycle behavior test passed and remaining source-level failure lists only receipt history/preview.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: expected-fail; 5 behavior tests passed and 1 source-level contract failed, limited to receipt history/preview.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P071 implementation files changed before docs.

## Current Expected Failures After P071

- `src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx`: cleared from source-level no-MUI failure lists.
- `src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx`: cleared from source-level no-MUI failure lists.
- `src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx`: lifecycle drawer/dialog remains P072.
- `src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx`: receipt preview drawer remains P072.

## P072 Prompt Draft

```text
Prompt ID: P072-phase-6-output-invoice-collections-receipt-history-and-preview
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `ReceiptHistoryDrawer.tsx` and `ReceiptPreviewDrawer.tsx` only, plus necessary styles/tests. Do not migrate unrelated modules.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/StatePanel.tsx、web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx、web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：移除 receipt history/preview 的 MUI imports/usages，包括 `CloseOutlinedIcon`、`Alert`、`Box`、`Button`、`Chip`、`CircularProgress`、`Divider`、`Dialog*`、`Drawer`、`FormControl`、`FormControlLabel`、`IconButton`、`Paper`、`Radio`、`RadioGroup`、`Stack`、`TextField` 和 `Typography`。使用 `AppDrawer` 保持右侧抽屉形态，使用 `AppDialog` 保持作废/重开确认弹窗形态，使用 project/native cards, receipt preview grid/table, native radio inputs, native buttons and StatePanel。必须保留 accessible names：`已出收据历史`、`待出收据预览`、dialog labels `作废收据原因`/`重开收据原因`；保留关闭 labels `关闭已出收据历史`、`关闭待出收据预览`；保留 loading labels `正在加载已出收据历史`、`正在加载待出收据预览`；保留 history source unavailable/empty messages, receipt cards, buttons `作废收据 <no>`、`重开收据 <no>`、dialog fields `作废原因`/`重开原因`、buttons `取消`/`确认作废`/`确认重开`, reason validation, void/reissue calls, reload/onChanged behavior；保留 preview bank selection required warning, candidate radio list, receipt preview title `收 据`, company/date/payer/summary/amount/remark/uppercase/lowercase display, `创建正式收据` button disabled/submitting behavior and createReceipt call。不得修改 page shell/table/filter/expandable, previous drawers, mock/API/read model/worker/backend/关联台。运行 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|opens the three right-side workflow drawers|closes lifecycle actions"`，source-level project primitive contract must fully pass；运行完整 `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`，must pass；运行 `cd web && npm run build`；运行 receipt drawer MUI grep：`if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|TextField|FormControlLabel|RadioGroup|Radio|IconButton|DialogTitle|DialogContent|DialogActions|Dialog\\b|Drawer\\b|Chip' web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx; then exit 1; else exit 0; fi`；运行 full module no-MUI grep：`if rg -n '@mui/|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 `MG-P072-phase-6-output-invoice-collections` cumulative MG prompt。
```

## P072 Execution Notes

- Status: verified.
- Files changed:
  - `web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx`
  - `web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx`
  - `web/src/app/styles.css`
- Behavior preserved:
  - Receipt history and receipt preview remain right-side drawers.
  - Accessible names `已出收据历史` and `待出收据预览` are preserved through `AppDrawer` titles.
  - Close labels `关闭已出收据历史` and `关闭待出收据预览` are preserved.
  - Loading labels `正在加载已出收据历史` and `正在加载待出收据预览` are preserved.
  - Receipt history source unavailable/empty messages, receipt cards, `作废收据 <no>` / `重开收据 <no>` buttons, void/reissue confirmation dialog labels, reason fields, submit buttons, reload/onChanged behavior and lifecycle calls are preserved.
  - Receipt preview bank selection warning, candidate radio list, receipt title/content/amount display, `创建正式收据` disabled/submitting behavior and createReceipt call are preserved.
- Implementation:
  - Replaced MUI drawer/dialog/layout/form components with `AppDrawer`, `AppDialog`, `StatePanel`, native controls and project styles.
  - Added receipt history card and receipt preview grid/card styles in `web/src/app/styles.css`.
  - Corrected the P072 grep during review because `Dialog\b|Drawer\b` would incorrectly match approved `AppDialog` and `AppDrawer` project primitives; the executed grep blocks real MUI imports/usages and JSX `<Dialog>/<Drawer>` surfaces.
- Non-goals honored:
  - Did not modify page shell, table, filter, expandable text, previous drawers, mock/API/read model/worker/backend or reconciliation workbench internals.
- Verification:
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives|opens the three right-side workflow drawers|closes lifecycle actions"`: passed.
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: passed, 6 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]|CloseOutlinedIcon|CircularProgress|TextField|FormControlLabel|RadioGroup|IconButton|DialogTitle|DialogContent|DialogActions|<Dialog|</Dialog|<Drawer|</Drawer|Chip' web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx; then exit 1; else exit 0; fi`: passed.
  - `if rg -n '@mui/|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P072 implementation files changed before docs.

## Current Expected Failures After P072

- None in the OutputInvoiceCollections runtime scope.
- `web/src/pages/OutputInvoiceCollectionsPage.tsx` and `web/src/components/outputInvoiceCollections/*` have no direct `@mui/*` imports or `.Mui*` selector residue.
- Full `OutputInvoiceCollectionsPage.test.tsx` passes.

## MG-P072 Prompt Draft

```text
Prompt ID: MG-P072-phase-6-output-invoice-collections
Phase: phase_6_page_batches
Type: cumulative MG
Scope: OutputInvoiceCollections P066-P072 completed migration only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_output_invoice_collections.md、docs/refactor-ui/table_layout_system.md、web/src/test/OutputInvoiceCollectionsPage.test.tsx 和 `git status --short --branch`。确认当前分支必须是 `refactor-ui` 且 tracking `origin/refactor-ui`。检查 untracked files、diff、测试结果和文档状态。Scope 只允许本 MG 的 P072 implementation/docs 文件以及此前已提交的 P066-P071 历史；当前未提交 diff 应仅包含 `web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx`、`web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx`、`web/src/app/styles.css`、`docs/refactor-ui/refactor_ui_state.md`、`docs/refactor-ui/refactor_ui_prompt.md`、`docs/refactor-ui/modules/phase_6_output_invoice_collections.md`。禁止 `git add .` 和 `git add -A`；只允许精确 `git add <file...>`。

执行验证：`cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`；`cd web && npm run build`；`if rg -n '@mui/|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi`；`git diff --check`；`git status --short --branch`。如验证通过，精确 stage 上述文件，commit message 使用 `feat: migrate output invoice collection receipt drawers`，push 到 `origin refactor-ui`。push 完成后更新 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md 和 docs/refactor-ui/modules/phase_6_output_invoice_collections.md，标记 MG verified、记录 commit/push、并从最新 `refactor-ui` 状态单独生成下一条 prompt。下一条 prompt 必须基于当前状态机分析，不得预生成多个模块 prompt。
```

## MG-P072 Execution Notes

- Status: verified.
- Scope checked:
  - `web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx`
  - `web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx`
  - `web/src/app/styles.css`
  - `docs/refactor-ui/refactor_ui_state.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/modules/phase_6_output_invoice_collections.md`
- Verification:
  - `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx`: passed, 6 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed before exact staging.
- Result:
  - OutputInvoiceCollections runtime scope has no direct `@mui/*` imports or `.Mui*` selector residue.
  - Commit `60f9593b feat: migrate output invoice collection receipt drawers` was pushed to `origin/refactor-ui`.
  - The next module prompt is `P073-phase-6-no-oa-bank-batches-discovery`.

## PV-017 Premium Visual Execution Notes

- Prompt ID: `PV-017-output-invoice-collections-premium-visual`
- Type: premium visual implementation
- Status: verified
- Runtime files changed:
  - `web/src/app/styles.css`
- Tests changed:
  - `web/src/test/OutputInvoiceCollectionsPage.test.tsx`
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

### Implementation

- Replaced output-invoice table group and sub-header hard-coded washes with Ledger Calm token-based `color-mix(...)` treatments.
- Tightened table viewport from the older tall layout to `min-height: 320px` and `max-height: calc(100vh - 214px)`.
- Tightened summary, alert, loading, detail, receipt-history and receipt-preview surfaces without changing their information hierarchy.
- Added motion-token hover/press/focus feedback for page actions, query controls, filter menu trigger/items/fields/apply, expandable text controls, table actions, sort buttons, pagination controls and drawer controls.
- Preserved the route, header actions, query controls, summary metrics, grouped table, filter/sort/expand controls, row details/workflows, all right drawers, receipt dialogs, loading/empty/error/read-model/permission states and all API behavior.

### Verification

Passed:

- `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`
- `cd web && npx tsc -b --pretty false`
- `cd web && npm run build`
- `git diff --check`
- keepalive/snapshot forbidden grep for runtime and module docs.
- non-workbench runtime MUI import grep.
- Browser smoke for `/output-invoice-collections` with system Chrome and mocked API at `http://127.0.0.1:4181/output-invoice-collections`.

Browser smoke result:

- Main table rendered with 1 data row.
- Group headers rendered: `销项发票`, `收款状态`, `收入流水`, `收据`.
- Filter menu trigger opened and rendered `待收款，已收部分款`.
- Detail right drawer opened for `销项发票收款情况详情`.
- Rules right drawer opened with `收款状态规则`.
- Receipt history right drawer opened with `已出收据历史`.
- Top-level body overflow: `0`; page root overflow: `0`.
- Screenshot: `/tmp/output-invoice-collections-premium-smoke.png`.

Notes:

- `npm run build` passed with existing HeroUI/Tailwind CSS minify warnings.
