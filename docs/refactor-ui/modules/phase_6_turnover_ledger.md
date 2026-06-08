# Phase 6 Turnover Ledger

本文档记录 `/turnover-ledger` 的 UI 迁移 discovery、旧入口对照、测试策略和后续 Micro-JIT prompt。目标是迁出非关联台 MUI，同时保持用户使用感受不变。

## P085 Discovery Notes

- Prompt ID: `P085-phase-6-turnover-ledger-discovery`
- Status: verified
- Scope: `/turnover-ledger` only.
- Runtime implementation changed: no.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - `test -f docs/refactor-ui/modules/phase_6_turnover_ledger.md`: passed.
  - `rg -n "P085-phase-6-turnover-ledger-discovery|Current MUI Inventory|User-visible Entrypoints|Recommended Micro-JIT Queue|P086-phase-6-turnover-ledger-characterization-tests" docs/refactor-ui/modules/phase_6_turnover_ledger.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P085/MG docs changed.
- Commit: `5747bf90 docs: verify batch accounting mg and add turnover discovery`, pushed to `origin/refactor-ui`.
- Next prompt generated: `P086-phase-6-turnover-ledger-characterization-tests`.

## Current MUI Inventory

| File | MUI / legacy surface | Notes |
| --- | --- | --- |
| `web/src/pages/TurnoverLedgerPage.tsx` | `DownloadOutlinedIcon`, `CloseIcon`, `Alert`, `Box`, `Button`, `Checkbox`, `Divider`, `Drawer`, `FormControlLabel`, `IconButton`, `Paper`, `Snackbar`, `Stack`, `Tab`, `Tabs`, `Typography` | Page shell actions, family tabs, summary cards, tag settings right drawer, closure right drawer, feedback. |
| `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx` | `Button`, `Checkbox`, `Chip`, `IconButton`, `Paper`, `Stack`, `Table*`, `Typography` | Primary左右双栏 grouped table, sticky group column, flow row selection, edit actions, loading/empty states. |
| `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx` | `Alert`, `Box`, `Button`, `Chip`, `Divider`, `Drawer`, `IconButton`, `MenuItem`, `Stack`, `TextField`, `Typography` | 补充信息右侧抽屉, form fields, tag chips, confirm/withdraw actions. |
| `web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx` | `Alert`, `Button`, `Dialog*`, `MenuItem`, `Stack`, `Table*`, `TextField`, `Typography` | 导出弹窗, family select, export preview table, download action. |

## User-visible Entrypoints

| Entry | Current behavior to preserve |
| --- | --- |
| Page actions | `标签设置` opens right drawer; `下载台账` opens export dialog. |
| Family tabs | `全部`/`待还款`/`已还款`/`待收款`/`已收款` switch table family and clear closure selection. |
| Summary cards | Four metric blocks remain visible above the table with tabular amount formatting. |
| Grouped ledger table | 左侧往来组 sticky summary remains aligned with right-side rows; flow rows, lot rows, amount tones, remarks and actions stay readable at high density. |
| Flow selection | Closure selection remains checkbox-based; selection constraints and error feedback remain unchanged. |
| Closure drawer | Existing right drawer stays a right drawer; selected two-flow preview, delta, cancel and confirm behavior remain unchanged. |
| Extra drawer | Existing right drawer stays a right drawer; relation detail loading, form fields, save, confirm/withdraw actions and close behavior remain unchanged. |
| Export dialog | Existing dialog stays a dialog; family select, preview table, empty/loading states, cancel and download behavior remain unchanged. |
| Feedback | Success/error messages remain user-visible and dismissible/autohide-equivalent. |

## Table And Layout Risks

- 左右双栏台账是本模块最高风险 surface：sticky left group cell, grouped row boundaries, summary rows, flow rows and lot rows must stay aligned.
- 金额列必须保持 `tabular-nums` and right alignment; income/expense/neutral tones must remain visually distinct but restrained.
- Selection checkbox column width must remain stable so closure selection does not shift row content.
- Group row expansion-like density uses many nested text fragments; long counterparty names, category paths and remarks must truncate or wrap predictably.
- Export preview table is a secondary table but still needs the same table layout system: sticky header, readable empty/loading rows and tabular amount cells.

## PV-022 Premium Visual Discovery

- Prompt ID: `PV-022-turnover-ledger-discovery`
- Type: premium visual discovery
- Status: verified
- Scope: `/turnover-ledger` only.
- Runtime implementation changed: no.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

### Current Implementation Status On `main`

- The page and its turnover ledger components already migrated out of MUI in the earlier `P086-P091` sequence.
- Runtime uses `PageScaffold`, `AppDrawer`, `AppDialog`, native controls, native tables and `turnover-ledger-*` project CSS classes.
- Current source-level grep shows no direct MUI/runtime legacy surfaces in `TurnoverLedgerPage.tsx` or `web/src/components/turnoverLedger/*`.
- The premium gap is now visual density, sticky table rhythm, tag sizing, selected-row treatment, drawer/dialog polish and motion-token consistency.

### User-visible Entrypoint Matrix

| Area | Preserve exactly |
| --- | --- |
| Route/sidebar | `/turnover-ledger`, sidebar label `外部往来款管理`, page heading and shell actions remain. |
| Page actions | `外部往来款标签设置` opens the tag right drawer; `下载表格` opens export dialog. |
| Family tabs | `全部`, `个人往来`, `公司往来`, `银行往来`, `业务往来`; selected tab state and closure selection reset remain. |
| Summary metrics | Four metric blocks remain above the table with family breakdown rows and tabular amounts. |
| Grouped table | Table accessible name `往来款左右双栏台账`; sticky left group summary, flow rows, amount tones, remarks, edit actions, loading and empty rows remain. |
| Closure selection | Flow checkbox labels, cross-group selection guard, delta test id `turnover-closure-delta`, cancel and confirm behavior remain. |
| Tag drawer | Right drawer remains right drawer; tag checkbox labels, selected state, inactive warning, `全选`, `清空`, `保存`, disabled rules and save payload remain. |
| Closure drawer | Right drawer remains right drawer; selected two-flow preview, income/expense totals, delta, cancel and confirm disabled rules remain. |
| Extra drawer | Right drawer `编辑流水补充信息`; relation detail loading/error, overview, form labels, dirty/save disabled rule, confirm/withdraw actions remain. |
| Export dialog | Modal dialog `下载往来款台账`; range select, preview table `往来款导出预览`, summary, loading/empty/error, `取消` and `确认下载` remain. |
| Feedback/status | Read-only/stale notices and success/error feedback remain visible and dismissible/autohide-equivalent. |

### Table And Layout Roles

| Surface | Premium layout requirement |
| --- | --- |
| Summary metrics | Compact metric strip, no large dashboard cards; amounts use tabular nums and family breakdown text stays aligned. |
| Grouped table | Preserve left/right alignment. Sticky group column and right rows must keep consistent row rhythm; hover/selected states must not shift layout. |
| Amount cells | Income/expense/neutral amount stacks right-align; direction tags and account/category chips keep stable height. |
| Drawers | Tag, closure and extra drawers remain right drawers with compact sections and tokenized controls. |
| Export dialog | Preview remains dense table with sticky/readable headers, right-aligned money columns and scroll containment. |

### PV-023 Premium Opportunities

- Replace fixed-duration turnover ledger transitions with `--motion-fast` / `--ease-out-quart` where still present.
- Tighten summary cards, tabs, grouped table cells, chip rows, drawer sections, export table and feedback surfaces while preserving the existing information architecture.
- Standardize `turnover-ledger-chip`, direction tags, amount stacks and export money cells on the table layout system.
- Add selected/hover/press feedback for tabs, table rows, checkboxes, edit/expand controls, drawer actions, export dialog actions and feedback close.
- Add CSS contract coverage in `TurnoverLedgerPage.test.tsx` for compact summary/table/drawer/dialog treatment, motion-token usage, amount alignment, stable tags and no layout-shift selected states.

### Non-scope For PV-023

- Do not change turnover ledger API clients, request params, response mapping, domain event names/payloads, closure logic, export download logic, relation detail loading, permission logic, backend/read model/worker or workbench internals.
- Do not change the left/right grouped table architecture, right drawer shapes, export dialog shape, accessible names, checkbox labels or feedback messages.
- Do not convert grouped table rows into cards or dashboard panels.

## Existing Tests

- `web/src/test/TurnoverLedgerPage.test.tsx` covers page rendering, family tabs, table interaction, closure flow, extra drawer, export dialog and feedback at behavior level.
- `web/src/test/TurnoverLedgerApi.test.ts` covers API client contracts; this migration must not change API request/response semantics.

## Characterization Tests Needed

- Source-level contract: no direct `@mui/*` outside frozen workbench surfaces after the full module migration; for P086 this should fail initially.
- Preserve right drawer semantics for tag settings, closure and extra info surfaces.
- Preserve export dialog role/name, family select, preview table and download action.
- Preserve table accessible name `往来款左右双栏台账`, row selection checkboxes, edit actions and loading/empty states.
- Preserve domain events and feedback messages for closure confirmation, relation confirm/withdraw, extra save and tag settings save.

## Recommended Micro-JIT Queue

1. `P085-phase-6-turnover-ledger-discovery`
2. `P086-phase-6-turnover-ledger-characterization-tests`
3. `P087-phase-6-turnover-ledger-page-shell-tabs-summary`
4. `P088-phase-6-turnover-ledger-grouped-table`
5. `P089-phase-6-turnover-ledger-tag-and-closure-drawers`
6. `P090-phase-6-turnover-ledger-extra-drawer`
7. `P091-phase-6-turnover-ledger-export-dialog-feedback-closeout`
7. `P091-phase-6-turnover-ledger-export-dialog-feedback`
8. `MG-P091-phase-6-turnover-ledger`

## P086 Prompt Draft

```text
Prompt ID: P086-phase-6-turnover-ledger-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/turnover-ledger` source-level and behavior guardrails only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/TurnoverLedgerPage.tsx、web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx、web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx、web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx、web/src/test/TurnoverLedgerPage.test.tsx、web/src/test/TurnoverLedgerApi.test.ts、web/src/features/turnoverLedger/api.ts 和 web/src/features/turnoverLedger/types.ts。只修改 `web/src/test/TurnoverLedgerPage.test.tsx`，新增 source-level no-MUI/project primitive contract 和必要的用户可见行为 characterization tests。不得修改 runtime code、API client、backend、read model、worker、domain event semantics 或关联台内部工作区。测试必须覆盖：page shell actions, family tabs, summary cards, grouped table accessible name and row selection, closure right drawer, extra right drawer, export dialog, feedback messages and relevant domain events。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 source-level contract against current MUI runtime is expected-fail while existing/new behavior tests must pass；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P087 page shell/tabs/summary prompt。
```

## P086 Execution Notes

- Status: verified with expected source-level failure.
- Runtime implementation changed: no.
- Test implementation changed: yes, only `web/src/test/TurnoverLedgerPage.test.tsx`.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Added source-level contract for `TurnoverLedgerPage.tsx`, `TurnoverLedgerGroupedTable.tsx`, `TurnoverLedgerExtraDrawer.tsx` and `TurnoverLedgerExportDialog.tsx`.
- Expected current failure lists direct MUI imports and legacy surfaces in all four runtime files, one MUI selector residue in grouped table, and missing project table/drawer/dialog/feedback primitives.
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail; 11 behavior tests passed and 1 source-level contract failed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P086 test file changed before docs.
- Commit: `e8b462a7 test: characterize turnover ledger ui migration`, pushed to `origin/refactor-ui`.

## P087 Prompt Draft

```text
Prompt ID: P087-phase-6-turnover-ledger-page-shell-tabs-summary
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/turnover-ledger` page shell actions, family tabs and summary cards only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/pages/TurnoverLedgerPage.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。只迁移 `TurnoverLedgerPage.tsx` 的 outer `Box`, page action buttons (`外部往来款标签设置`, `下载表格`), family tabs (`全部`/`个人往来`/`公司往来`/`银行往来`/`业务往来`) and summary cards (`当前待还款金额`/`累计已还款金额`/`当前待收款金额`/`累计已收款金额`) 到 native/project controls and `turnover-ledger-*` classes；必要时只补 `web/src/app/styles.css` 中的 turnover ledger shell/tabs/summary classes。不得迁移 grouped table、tag settings drawer、closure drawer、extra drawer、export dialog、feedback/Snackbar、API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：page heading, action button labels and disabled states, family tab accessible roles/selected state, family switch clears closure selection, summary card labels/amounts/family breakdown text, grouped table still renders and existing behavior tests still pass。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|renders grouped|opens tag selection drawer|reloads on category updates"`，预期 source-level contract remains expected-fail but selected behavior tests must pass；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 11 behavior tests pass and source-level contract remains expected-fail until P088-P091；运行 scoped grep `if rg -n 'DownloadOutlinedIcon|<Box|<Tabs|<Tab|label=\"全部\"|label=\"个人往来\"|label=\"公司往来\"|label=\"银行往来\"|label=\"业务往来\"' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P088 grouped table prompt。
```

## P087 Execution Notes

- Status: verified with expected source-level failure.
- Runtime implementation changed: yes, only `web/src/pages/TurnoverLedgerPage.tsx`.
- CSS changed: yes, only `web/src/app/styles.css` `turnover-ledger-*` shell/tabs/summary classes.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Migrated page outer container, page action buttons, family tabs and summary cards to native/project controls.
- Preserved page heading, action labels, disabled states, family tab accessible role/selected state, summary labels/amounts/family breakdown and grouped table rendering.
- Scoped grep was corrected during execution to exclude bare `<Box` because tag/closure drawer internals still legitimately use MUI in later slices.
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|renders grouped|opens tag selection drawer|reloads on category updates"`: expected-fail; selected behavior tests passed and source-level contract failed as expected.
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail; 11 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n 'DownloadOutlinedIcon|<Tabs|<Tab|label="全部"|label="个人往来"|label="公司往来"|label="银行往来"|label="业务往来"' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
- Commit: `e9a464b5 feat: migrate turnover ledger page shell`, pushed to `origin/refactor-ui`.

## P088 Prompt Draft

```text
Prompt ID: P088-phase-6-turnover-ledger-grouped-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/turnover-ledger` grouped ledger table only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。只迁移 `TurnoverLedgerGroupedTable.tsx` 的 MUI table/container/row/cell/checkbox/chip/icon/button/typography/layout surfaces 到 native/project table controls and `turnover-ledger-*`/existing `turnover-*` classes；必要时只补 `web/src/app/styles.css` 中 grouped table classes。不得迁移 `TurnoverLedgerPage.tsx` drawers, `TurnoverLedgerExtraDrawer.tsx`, `TurnoverLedgerExportDialog.tsx`, feedback/Snackbar, API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：table accessible name `往来款左右双栏台账`, sticky left group/header classes, no status column, grouped summary rows, expandable flow rows, real flow rows instead of lot rows, checkbox labels and disabled states, edit button labels, amount tone classes, loading/empty rows and high-density alignment。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|renders grouped|expands Jia Xiaohua|confirms a manual zero-difference|blocks cross-group selection|shows bank-detail tags"`，预期 source-level contract remains expected-fail but selected behavior tests must pass；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 11 behavior tests pass and source-level contract remains expected-fail until P089-P091；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|KeyboardArrowDownIcon|KeyboardArrowRightIcon|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Checkbox|<Chip|<IconButton|<Button|<Paper|<Stack|<Typography' web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P089 tag and closure drawers prompt。
```

## P088 Execution Notes

- Status: verified with expected source-level failure.
- Runtime implementation changed: yes, only `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`.
- CSS changed: yes, only `web/src/app/styles.css` grouped table classes.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Migrated grouped table from MUI table/container/row/cell/checkbox/chip/icon/button/typography/layout surfaces to native table controls and project classes.
- Preserved table accessible name, sticky left classes, group summary rows, flow rows, checkbox labels, edit button labels, amount tone classes, loading/empty text and behavior tests.
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|renders grouped|expands Jia Xiaohua|confirms a manual zero-difference|blocks cross-group selection|shows bank-detail tags"`: expected-fail; selected behavior tests passed and source-level contract failed as expected.
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail; 11 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]|KeyboardArrowDownIcon|KeyboardArrowRightIcon|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Checkbox|<Chip|<IconButton|<Button|<Paper|<Stack|<Typography' web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
- Commit: `db426030 feat: migrate turnover ledger grouped table`, pushed to `origin/refactor-ui`.

## P089 Prompt Draft

```text
Prompt ID: P089-phase-6-turnover-ledger-tag-and-closure-drawers
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/turnover-ledger` page-owned tag settings right drawer and closure right drawer only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/pages/TurnoverLedgerPage.tsx、web/src/components/common/AppDrawer.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。只迁移 `TurnoverLedgerPage.tsx` 内 page-owned drawers：`外部往来款标签设置` right drawer and `确认外部往来闭环` right drawer，以及这些 drawer 内部的 MUI layout/buttons/checkbox chips/close icon/alerts 到 `AppDrawer`、native/project controls and `turnover-ledger-*` classes。不得迁移 `TurnoverLedgerExtraDrawer.tsx`, `TurnoverLedgerExportDialog.tsx`, page feedback/Snackbar, API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：old right drawers remain right drawers, dialog role/name, close buttons, tag checkbox labels and selected state, `全选`/`清空`/`保存` disabled rules and save payload, inactive tag warning text, closure selected rows preview, income/expense totals, delta test id `turnover-closure-delta`, cancel/confirm buttons, confirm disabled when delta is non-zero, closure POST payload and domain events。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|opens tag selection drawer|confirms a manual zero-difference|confirms closure when cash direction crosses|blocks cross-group selection"`，预期 source-level contract remains expected-fail but selected behavior tests must pass；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 11 behavior tests pass and source-level contract remains expected-fail until P090-P091；运行 scoped grep `if rg -n '<Drawer|<IconButton|CloseIcon|FormControlLabel|<Checkbox|<Button|<Alert|<Box|<Stack|<Typography' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P090 extra drawer prompt。
```

## P089 Execution Notes

- Status: verified with expected source-level failure.
- Runtime implementation changed: yes, only `web/src/pages/TurnoverLedgerPage.tsx`.
- CSS changed: yes, only `web/src/app/styles.css` drawer/tag/closure classes.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Migrated page-owned `外部往来款标签设置` and `确认外部往来闭环` right drawers from MUI Drawer/layout/buttons/checkboxes to `AppDrawer` and native/project controls.
- Preserved drawer role/name, close buttons, tag checkbox labels and selected state, save payload, closure preview, totals, `turnover-closure-delta`, confirm disabled rule and closure domain events.
- Scoped grep was corrected during execution to exclude `<Alert` because page status/feedback MUI Alert/Snackbar are reserved for P091 closeout.
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|opens tag selection drawer|confirms a manual zero-difference|confirms closure when cash direction crosses|blocks cross-group selection"`: expected-fail; selected behavior tests passed and source-level contract failed as expected.
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail; 11 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '<Drawer|<IconButton|CloseIcon|FormControlLabel|<Checkbox|<Button|<Box|<Stack|<Typography|<Paper|<Divider' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
- Commit: `3675bed3 feat: migrate turnover ledger drawers`, pushed to `origin/refactor-ui`.

## P090 Prompt Draft

```text
Prompt ID: P090-phase-6-turnover-ledger-extra-drawer
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/turnover-ledger` extra info right drawer component only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx、web/src/components/common/AppDrawer.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。只迁移 `TurnoverLedgerExtraDrawer.tsx` 的 MUI Drawer/layout/buttons/chips/text fields/menu items/alerts 到 `AppDrawer`、native/project controls and `turnover-ledger-*` classes；必要时只补 `web/src/app/styles.css` 中 extra drawer classes。不得迁移 `TurnoverLedgerExportDialog.tsx`, page feedback/Snackbar, API client、mock data、backend、read model、worker 或关联台内部工作区。保留用户可见行为：old extra info drawer remains right drawer, dialog role/name `编辑流水补充信息`, technical relation IDs remain hidden, loading/error states, overview text, form labels (`利率值` 等), dirty/save disabled rule, save payload, relation action buttons (`确认归并`/`撤销归并`) and disabled rules。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|opens the extra drawer|shows a business error|disables turnover write actions"`，预期 source-level contract remains expected-fail but selected behavior tests must pass；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期 11 behavior tests pass and source-level contract remains expected-fail until P091；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|<Drawer|<IconButton|CloseIcon|<Button|<Chip|<TextField|<MenuItem|<Alert|<Box|<Stack|<Typography|<Divider' web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P091 export dialog and feedback closeout prompt。
```

## P090 Execution Notes

- Status: verified with expected source-level failure.
- Runtime implementation changed: yes, only `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx`.
- CSS changed: yes, only `web/src/app/styles.css` extra drawer classes and button/notice variants.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Migrated `编辑流水补充信息` right drawer from MUI Drawer/layout/buttons/chips/text fields/select/menu items/alerts to `AppDrawer`, native form controls and `turnover-ledger-*` classes.
- Preserved dialog role/name, subtitle, technical relation ID hiding, loading/error states, overview text, form labels, dirty/save disabled rule, save payload, `确认归并`/`撤销归并` actions and disabled rules.
- Source-level contract now clears ExtraDrawer MUI import and missing drawer primitive target; remaining expected failures are page Alert/Snackbar, ExportDialog MUI import/dialog target, and over-broad legacy regex matching project primitive names such as `AppDrawer`.
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|opens the extra drawer|shows a business error|disables turnover write actions"`: expected-fail; selected behavior tests passed and source-level contract failed as expected.
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: expected-fail; 11 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]|<Drawer|<IconButton|CloseIcon|<Button|<Chip|<TextField|<MenuItem|<Alert|<Box|<Stack|<Typography|<Divider' web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
- Commit: `30fde5ad feat: migrate turnover ledger extra drawer`, pushed to `origin/refactor-ui`.

## P091 Prompt Draft

```text
Prompt ID: P091-phase-6-turnover-ledger-export-dialog-feedback-closeout
Phase: phase_6_page_batches
Type: extraction/refactor + contract closeout
Scope: `/turnover-ledger` export dialog, page-level feedback/status surfaces, and source-level migration contract false-positive cleanup only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx、web/src/pages/TurnoverLedgerPage.tsx、web/src/components/common/AppDialog.tsx、web/src/test/TurnoverLedgerPage.test.tsx 和 web/src/app/styles.css。迁移 `TurnoverLedgerExportDialog.tsx` 的 MUI Dialog/layout/table/select/alert/buttons 到 `AppDialog`、native/project table/form controls and `turnover-ledger-*` classes；迁移 `TurnoverLedgerPage.tsx` page-level MUI `Alert`/`Snackbar` feedback/status surfaces 到 project/native notice/toast classes。允许只为修正迁移合约 false positive 更新 `web/src/test/TurnoverLedgerPage.test.tsx` 的 source-level no-MUI contract：禁止 `@mui/*` imports、MUI selectors and legacy MUI JSX/import names；不得把 `AppDrawer`/`AppDialog`、文件名中的 `Drawer`/`Dialog` 或项目 primitive class 当成 legacy。不得修改导出 API client、mock response shape、backend、read model、worker、权限语义或关联台内部工作区。保留用户可见行为：旧导出入口仍为 `下载表格` button；旧导出确认仍为 modal dialog `下载往来款台账`；下载范围选项和默认 family behavior 不变；预览 table accessible name `往来款导出预览`、loading/empty/error 文案、summary text、`取消`/`确认下载` buttons and disabled rules 不变；mutation feedback messages and close behavior 不变；只读和 stale read model notices remain visible and semantically announced。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|reloads on category updates and downloads a previewed export|opens the extra drawer|shows a business error|disables turnover write actions"`，预期全部通过；运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx`，预期全部通过；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|<Dialog\\b|<Button|<TextField|<MenuItem|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Stack|<Typography' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 TurnoverLedger cumulative MG prompt。
```

## P091 Execution Notes

- Status: verified.
- Runtime implementation changed: yes, `web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx` and `web/src/pages/TurnoverLedgerPage.tsx`.
- CSS changed: yes, only `web/src/app/styles.css` export dialog/page notice/toast classes.
- Test implementation changed: yes, only source-level no-MUI contract false-positive cleanup in `web/src/test/TurnoverLedgerPage.test.tsx`.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Migrated export dialog from MUI Dialog/layout/table/select/alert/buttons to `AppDialog`, native select/table/buttons and project classes.
- Migrated page-level read-only/stale notices and mutation feedback from MUI Alert/Snackbar to native project notices/toast with 4-second auto close and manual close button.
- Preserved download entry, modal dialog name, download range options, export preview table accessible name, loading/empty/error text, summary text, cancel/download buttons, disabled rules and download request family.
- Source-level migration contract now passes and still forbids MUI imports, MUI selectors and legacy MUI JSX/import names without flagging project primitives.
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives|reloads on category updates and downloads a previewed export|opens the extra drawer|shows a business error|disables turnover write actions"`: passed.
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx`: passed, 12 tests.
  - `if rg -n '@mui/|Mui[A-Z]|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|<Dialog\\b|<Button|<TextField|<MenuItem|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Stack|<Typography' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx; then exit 1; else exit 0; fi`: passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
- Commit: `8a3eb3cb feat: complete turnover ledger ui migration`, pushed to `origin/refactor-ui`.

## MG-P091 Prompt Draft

```text
Prompt ID: MG-P091-phase-6-turnover-ledger
Phase: phase_6_page_batches
Type: cumulative merge gate
Scope: TurnoverLedger P085-P091 only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_turnover_ledger.md、docs/refactor-ui/table_layout_system.md、web/src/pages/TurnoverLedgerPage.tsx、web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx、web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx、web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx、web/src/test/TurnoverLedgerPage.test.tsx、web/src/test/TurnoverLedgerApi.test.ts 和当前 git status/diff。检查当前分支必须是 `refactor-ui`。确认 untracked files、diff scope、测试结果和文档状态；确认 P085-P091 已记录并且 TurnoverLedger runtime no-MUI contract passed。运行 `cd web && npx vitest run TurnoverLedgerPage.test.tsx TurnoverLedgerApi.test.ts`；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 no-MUI grep：`if rg -n '@mui/|Mui[A-Z]|DownloadOutlinedIcon|KeyboardArrowDownIcon|KeyboardArrowRightIcon|CloseIcon|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|<Dialog\\b|<Drawer\\b|<Button|<TextField|<MenuItem|<Table|TableHead|TableBody|TableRow|TableCell|TableContainer|<Checkbox|<Chip|<IconButton|<Stack|<Typography|<Paper|<Divider|FormControlLabel|Tabs|Tab' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。确认 scope 只包含 TurnoverLedger runtime/tests/docs files and `web/src/app/styles.css`；禁止 `git add .` 和 `git add -A`，只允许精确 git add。MG 通过后提交并 push 到 `origin/refactor-ui`，再更新 state/prompt/module docs 的 MG execution notes 和 Push Log，标记 MG verified，并从 `refactor-ui` 分支生成下一条 Micro-JIT prompt。
```

## MG-P091 Execution Notes

- Status: verified.
- Runtime implementation changed during MG: no.
- Test implementation changed during MG: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- MG grep was corrected during execution to use JSX-tag boundaries for `<Tab>`/`<Table>` so project names like `TurnoverLedgerGroupedTable` are not false positives.
- Verification:
  - `cd web && npx vitest run TurnoverLedgerPage.test.tsx TurnoverLedgerApi.test.ts`: passed, 21 tests.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 15 tests.
  - `if rg -n '@mui/|Mui[A-Z]|DownloadOutlinedIcon|KeyboardArrowDownIcon|KeyboardArrowRightIcon|CloseIcon|DialogTitle|DialogContent|DialogActions|Snackbar|<Alert\\b|<Dialog\\b|<Drawer\\b|<Button\\b|<TextField\\b|<MenuItem\\b|<Table\\b|<TableHead\\b|<TableBody\\b|<TableRow\\b|<TableCell\\b|<TableContainer\\b|<Checkbox\\b|<Chip\\b|<IconButton\\b|<Stack\\b|<Typography\\b|<Paper\\b|<Divider\\b|<FormControlLabel\\b|<Tabs\\b|<Tab\\b' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger; then exit 1; else exit 0; fi`: passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
  - `git status --short --branch`: clean before MG docs update.
- Next prompt generated: `P092-phase-6-etc-tickets-discovery`.
