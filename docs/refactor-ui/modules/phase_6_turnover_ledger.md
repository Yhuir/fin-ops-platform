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
