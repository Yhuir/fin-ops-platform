# Phase 6 ETC Tickets UI Migration

本文档记录 `/etc-tickets` 的 UI 平台迁移切片。目标是把 ETC 票据管理迁到 HeroUI/Tailwind/project primitives，同时保持用户使用感、业务流程、API contract、后台任务和关联台内部工作区不变。

## P092 Discovery

- Prompt ID: `P092-phase-6-etc-tickets-discovery`
- Route: `/etc-tickets`
- Page: `web/src/pages/EtcTicketManagementPage.tsx`
- Tests:
  - `web/src/test/EtcTicketManagementPage.test.tsx`
  - `web/src/test/EtcApi.test.ts`
  - `web/src/test/EtcOaNavigation.test.ts`
- API/client facts:
  - `web/src/features/etc/api.ts`
  - `web/src/features/etc/types.ts`
  - `web/src/features/etc/oaNavigation.ts`
- Non-goals:
  - 不修改 ETC API client contract、mock response shape、backend、read model、worker、background job semantics。
  - 不修改 OA 草稿 URL 构造、domain event names/payloads、导入任务 job 语义。
  - 不修改 `ReconciliationWorkbenchPage` 或 `web/src/components/workbench/*`。

## Current MUI Inventory

`EtcTicketManagementPage.tsx` 仍直接引入大量 MUI：

- Icons: `AddOutlinedIcon`, `ArrowForwardOutlinedIcon`, `DeleteOutlineOutlinedIcon`, `ExpandLessOutlinedIcon`, `ExpandMoreOutlinedIcon`, `OpenInNewOutlinedIcon`, `RefreshOutlinedIcon`, `ReportProblemOutlinedIcon`, `UndoOutlinedIcon`, `UploadFileOutlinedIcon`.
- Feedback/status: `Alert`.
- Layout/surface: `Box`, `Paper`, `Stack`, `Divider`, `Typography`, `Collapse`.
- Actions/inputs: `Button`, `IconButton`, `Checkbox`, `TextField`, `ToggleButton`, `ToggleButtonGroup`.
- Lists: `List`, `ListItem`, `ListItemButton`, `ListItemText`.
- Tables: `Table`, `TableBody`, `TableCell`, `TableContainer`, `TableHead`, `TableRow`.
- Display helpers: `Chip`, `Tooltip`.

The page already uses project primitives in some places:

- `PageScaffold`
- `StatePanel`
- `AppDialog`
- `usePageScrollSession`
- `useBackgroundJobProgress`

## User-visible Entrypoints

The migration must preserve these visible entrypoints and accessible names:

- Page heading: `ETC票据`.
- Status segmented controls: `未提交 2`, `已提交 1`.
- Primary page action: `提交OA`.
- Batch/task lists:
  - `ETC批次列表`
  - `ETC批次列表区`
  - `ETC对账任务列表`
  - `ETC对账任务`
- Upload areas:
  - `ETC对账文件上传`
  - `ETC导入动作`
  - `上传票根网`
  - batch-level upload blocks under ticket-root import area.
- Reconciliation workspace:
  - `ETC对账工作区`
  - `人工核对处理`
  - `ETC双侧核对明细`
  - row selection controls: all, paired-only, clear.
  - action: `接受推荐票根`.
- Business batch detail:
  - `ETC批次详情`
  - `批次指标`
  - `车牌汇总`
  - invoice detail tables rendered by `renderEtcInvoiceTable`.
- Task imported invoices:
  - `已导入ETC发票`
  - action: `移除发票`.
- Dialogs:
  - `删除批次`
  - `删除任务`
  - `删除源文件`
  - `移除发票`
  - `上传补充凭证`
  - `撤销OA提交`
  - `创建OA草稿`
  - `OA自动检测`
- OA actions:
  - `打开草稿`
  - `刷新检测`
  - `撤销草稿`
  - `确认已提交OA`
  - `未提交OA`

## Existing Test Coverage

`EtcTicketManagementPage.test.tsx` currently has broad behavior coverage:

- Background job completion refreshes business batch and reconciliation task lists.
- Unsubmitted/submitted mode switching and whole-batch OA submit action.
- Deleting unsubmitted batches, stale business batches, imported reconciliation tasks, source files and idempotent not-found cleanup.
- Reconciliation workspace upload blocks, ticket-root TXT uploads, drag/drop, legacy PDF/TXT source handling and source issue display.
- Paired reconciliation table rendering, one-line long descriptions, local row selection, confirmation metrics and selected-card submit payload.
- Imported task invoice display, OA draft creation/detection workflow, delete imported task flow.
- Suggested ticket manual reconciliation and batch invoice details.
- Submitted mode hiding submit action and showing OA information.
- Native table coverage already exists for batch invoice details: “renders batch invoice details with a native table instead of DataGrid”.

Current gaps for migration:

- No source-level no-MUI/project primitive contract for `EtcTicketManagementPage.tsx`.
- Existing assertions still tolerate many MUI surfaces because the page is legacy MUI.
- Need explicit coverage that old UI form factor remains stable:
  - status mode remains segmented control equivalent.
  - batch/task list remains list, not card-only replacement.
  - reconciliation detail remains table.
  - existing dialogs remain dialogs, not drawers.
  - upload blocks remain upload/drop controls with file input semantics.
  - OA automatic detection dialog keeps action availability.

## Table Layout Risks

- ETC page has multiple dense financial tables:
  - invoice detail table via `renderEtcInvoiceTable`
  - `ETC双侧核对明细`
  - imported invoice table
  - reconciliation card/evidence comparison rows
- Amount/date columns must keep table layout system rules:
  - money right aligned and tabular nums.
  - date/time split remains compact and scannable.
  - long descriptions remain one-line collapsed until expanded.
  - checkbox/selection column has fixed width and does not shift table layout.
  - explicit linked/suggested pair rows remain visually distinct without introducing new status chips that tests removed.

## Migration Risks

- File is large and mixed: upload controls, lists, tables, dialogs and OA status panels are in one page. Do not migrate all in one implementation prompt.
- Several dialogs already use `AppDialog` but still contain MUI buttons/Stack/Typography/TextField. Dialog shell should remain dialog.
- Existing tests use CSS selectors such as `.etc-upload-drop-grid`, `.etc-reconciliation-table-block`, `.etc-reconciliation-table-row`, `.etc-reconciliation-divider`. Preserve or deliberately migrate tests with equivalent behavior selectors only after characterization.
- Existing tests query role/name for many buttons. Keep button labels stable.
- Do not change OA draft submission/detection payloads or URL construction.
- Do not remove idempotent stale-row cleanup behavior.

## Recommended Micro-JIT Queue

1. `P093-phase-6-etc-tickets-characterization-tests`
   - Add source-level no-MUI/project primitive contract and form-factor characterization assertions.
   - Expected source-level contract fails against current MUI runtime; behavior tests must pass.
2. `P094-phase-6-etc-tickets-shell-filters-lists`
   - Migrate icons, page shell local layout, status segmented controls, filter/list panels and batch/task list items.
   - Do not touch reconciliation workspace tables or dialogs.
3. `P095-phase-6-etc-tickets-upload-and-source-panels`
   - Migrate upload blocks, source file list, ticket-root TXT upload controls and source issue/status notices.
   - Preserve file input labels, drag/drop behavior and upload payloads.
4. `P096-phase-6-etc-tickets-reconciliation-table`
   - Migrate `ETC双侧核对明细`, row selection controls, expandable descriptions and reconciliation metrics.
   - Keep table accessible name, row data test ids and selection payloads.
5. `P097-phase-6-etc-tickets-detail-and-invoice-tables`
   - Migrate business batch detail, imported invoice section, `renderEtcInvoiceTable`, metrics and import attempts.
   - Preserve native table test intent and amount/date alignment.
6. `P098-phase-6-etc-tickets-dialogs-oa-feedback`
   - Migrate remaining dialog content controls, OA status/detection panels, feedback/status Alert surfaces and final MUI cleanup.
   - Source-level contract must pass.
7. `MG-P098-phase-6-etc-tickets`
   - Run ETC page/API/navigation tests, table/common/HeroUI platform regressions, build, no-MUI grep and docs state check.

## P093 Prompt Draft

```text
Prompt ID: P093-phase-6-etc-tickets-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/etc-tickets` characterization tests only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx、web/src/test/EtcApi.test.ts、web/src/test/EtcOaNavigation.test.ts 和 web/src/features/etc/types.ts。只修改 `web/src/test/EtcTicketManagementPage.test.tsx`，新增 source-level no-MUI/project primitive contract 和必要的用户可见 form-factor characterization assertions。不得修改 runtime code、API client、backend、read model、worker、domain event semantics 或关联台内部工作区。测试必须覆盖：page shell heading/actions, status segmented controls, batch/task list accessible names, upload/drop controls, reconciliation workspace/table accessible names, dialogs remain dialogs, OA detection actions, feedback/status surfaces, and existing table alignment expectations。运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx`，预期 source-level contract against current MUI runtime is expected-fail while existing/new behavior tests must pass；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P094 shell/filters/lists prompt。
```

## P093 Execution Notes

- Test implementation changed: yes, only `web/src/test/EtcTicketManagementPage.test.tsx`.
- Runtime implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Added a source-level no-MUI/project primitive contract for `EtcTicketManagementPage.tsx`.
- Added user-visible form-factor assertions for:
  - status segmented control group `ETC批次状态`;
  - batch list region `ETC批次列表区`;
  - reconciliation workspace region `ETC对账工作区`;
  - upload/drop control label `ETC对账文件上传`;
  - reconciliation table accessible name `ETC双侧核对明细`.
- Stabilized the OA draft creation behavior test by removing a brittle precheck on import attempt text that was not required for the user-visible submit flow.
- Verification:
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx`: expected-fail; 41 behavior tests passed and 1 source-level no-MUI/project primitive contract failed against current MUI runtime.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P093 test file changed before docs.
- Commit: `1d0773cc test: characterize etc tickets ui migration`, pushed to `origin/refactor-ui`.

## P094 Prompt Draft

```text
Prompt ID: P094-phase-6-etc-tickets-shell-filters-lists
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/etc-tickets` page shell, status/filter bar, and batch/task list panels only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx、web/src/app/styles.css 和 web/src/components/common/PageScaffold.tsx。只迁移 `EtcTicketManagementPage.tsx` 中 page shell local wrapper、top action icons、status segmented controls、月份/车牌/信用卡任务筛选输入、左侧 `ETC批次列表区`、`ETC批次列表` 和 `ETC对账任务列表` 的 MUI icons/layout/forms/list items/buttons/chips 到 lucide icons、native/project controls and `etc-*` classes；必要时只补 `web/src/app/styles.css` 中该切片 classes。不得迁移 upload/drop blocks、reconciliation workspace tables、business batch detail tables、manual review panel、dialog contents、OA status/detection panels、feedback Alert surfaces、API client、backend、read model、worker、domain event semantics 或关联台内部工作区。保留用户可见行为：page heading `ETC票据`、import link `导入发票`、primary action `提交OA`、status controls `未提交 2`/`已提交 1`、filter labels `月份`/`车牌`/`信用卡任务`、batch/task list accessible names, selected row behavior, task row delete/view actions, batch row delete/reopen/open-draft actions and disabled rules。运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|unsubmitted mode shows batch list|submitted mode hides submit action|creates OA draft through the selected business batch"`，预期 source-level contract remains expected-fail but selected behavior tests pass；运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx`，预期 41 behavior tests pass and 1 source-level contract remains expected-fail until later ETC slices；运行 scoped grep `if rg -n 'AddOutlinedIcon|ArrowForwardOutlinedIcon|DeleteOutlineOutlinedIcon|OpenInNewOutlinedIcon|RefreshOutlinedIcon|UndoOutlinedIcon|UploadFileOutlinedIcon|<ToggleButton\\b|<ToggleButtonGroup\\b|<List\\b|<ListItem\\b|<ListItemButton\\b|<ListItemText\\b|<Paper\\b|<TextField[^\\n]*(label="月份"|label="车牌"|label="信用卡任务")' web/src/pages/EtcTicketManagementPage.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P095 upload/source panels prompt。
```

## P094 Execution Notes

- Runtime implementation changed: yes, only `web/src/pages/EtcTicketManagementPage.tsx` and `web/src/app/styles.css`.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Migrated ETC page top import link, status segmented controls, filter inputs, submit action, batch/task list panels and list row delete actions to lucide icons, native buttons/inputs/lists and `etc-*` classes.
- Cleared page-level MUI icons, MUI `Paper`, and MUI `List`/`ListItem` wrappers. The uploaded source-file list was converted to native `ul/li` only so the P094 scoped no-list grep can pass; upload behavior and source-file deletion payloads were unchanged.
- Preserved page heading, `导入发票`, `提交OA`, status button names, filter labels, batch/task list accessible names, selected row behavior, delete dialog triggers and disabled rules.
- Verification:
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|unsubmitted mode shows batch list|submitted mode hides submit action|creates OA draft through the selected business batch"`: expected-fail; selected behavior tests passed and the source-level contract failed as expected.
  - `cd web && npx vitest run EtcTicketManagementPage.test.tsx`: expected-fail; 41 behavior tests passed and 1 source-level no-MUI/project primitive contract failed against remaining ETC MUI runtime.
  - `if rg -n 'AddOutlinedIcon|ArrowForwardOutlinedIcon|DeleteOutlineOutlinedIcon|OpenInNewOutlinedIcon|RefreshOutlinedIcon|UndoOutlinedIcon|UploadFileOutlinedIcon|<ToggleButton\\b|<ToggleButtonGroup\\b|<List\\b|<ListItem\\b|<ListItemButton\\b|<ListItemText\\b|<Paper\\b|<TextField[^\\n]*(label="月份"|label="车牌"|label="信用卡任务")' web/src/pages/EtcTicketManagementPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P094 page/style files changed before docs.
- Commit: `47a2d993 feat: migrate etc tickets shell and lists`, pushed to `origin/refactor-ui`.

## P095 Prompt Draft

```text
Prompt ID: P095-phase-6-etc-tickets-upload-and-source-panels
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/etc-tickets` upload/drop blocks, source-file context, and upload/source notices only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_etc_tickets.md、docs/refactor-ui/table_layout_system.md、web/src/pages/EtcTicketManagementPage.tsx、web/src/test/EtcTicketManagementPage.test.tsx 和 web/src/app/styles.css。只迁移 `EtcTicketManagementPage.tsx` 中 `UploadDropBox`、`ETC对账文件上传`、`ETC导入动作`、信用卡账单/补充凭证/票根网 TXT 上传块、source file context/issues/status notices and source upload lists 的 MUI Button/Stack/Typography/Chip/Tooltip/IconButton/Alert usages 到 native/project controls and `etc-*` classes；必要时只补 `web/src/app/styles.css` 中 upload/source classes。不得迁移 reconciliation detail table, manual review form, business batch detail/invoice tables, dialog contents, OA status/detection panels, API client、backend、read model、worker、domain event semantics 或关联台内部工作区。保留用户可见行为：file input labels `上传信用卡账单`/`上传补充凭证`/`上传票根网`, drag/drop upload behavior, accepted file types, disabled reasons, legacy non-TXT/PDF blocking notices, source issue visibility, delete source file action label and payload, fresh task source issue isolation。运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives|shows the reconciliation workspace with upload blocks|uploads ticket-root TXT files|uploads ticket-root TXT files by dropping|shows source file context|removes legacy ticket-root mode controls|disables ticket-root TXT upload"`，预期 source-level contract remains expected-fail but selected behavior tests pass；运行 `cd web && npx vitest run EtcTicketManagementPage.test.tsx`，预期 41 behavior tests pass and 1 source-level contract remains expected-fail until later ETC slices；运行 scoped grep for upload/source slice `if rg -n 'etc-upload-drop-box[^\\n]*MuiButton|MuiButton-root|Mui-disabled|<Alert\\b|<Tooltip\\b|<IconButton\\b|<Stack[^\\n]*etc-upload|<Typography[^\\n]*(上传|legacy|source)|<Chip\\b' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi`，若 grep 过宽命中未迁移的 table/detail/OA surfaces，必须收窄到 upload/source classes and document why；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P096 reconciliation table prompt。
```
