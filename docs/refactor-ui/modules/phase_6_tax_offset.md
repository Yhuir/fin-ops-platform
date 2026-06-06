# Phase 6 Tax Offset Discovery

本文档记录 TaxOffsetPage 页面模块迁移 discovery。目标是逐步把税金抵扣页面从 MUI 迁到 HeroUI/Tailwind/项目 primitives，同时保持现有用户体感和业务行为。

Last updated: 2026-06-07

## Boundary

- Scope: `/tax-offset` 页面、`web/src/pages/TaxOffsetPage.tsx`、`web/src/components/tax/*`、相关测试。
- Non-scope: 不改后端、API contract、read model、worker、税金抵扣业务计算、权限语义、关联台内部工作区。
- Behavior equivalence:
  - 旧页面表格仍是表格。
  - 旧已认证导入是页面内弹窗，新 UI 仍是页面内弹窗。
  - 旧已认证结果是右侧/旁侧结果区，新 UI 不改为新路由或弹窗。
  - 旧月份选择、全选、清空、保存计划、横向同步滚动、筛选弹窗、排序按钮、导入预览/确认入口都必须保留。

## Current MUI Inventory

| File | MUI usage | Notes |
| --- | --- | --- |
| `TaxOffsetPage.tsx` | `Alert`, `Box`, `Button`, `Stack` | Page-level layout/actions; common `PageScaffold` and `StatePanel` already migrated. |
| `TaxTable.tsx` | `Box`, `Button`, `Checkbox`, `Paper`, `Stack`, `Table*`, `Typography` | Main output/input invoice tables, filters, sort, selection, horizontal scroll. |
| `CertifiedInvoiceImportModal.tsx` | `Alert`, `Box`, `Button`, `Chip`, `Dialog*`, `LinearProgress`, `Paper`, `Stack`, `Table*`, `Typography` | Page modal, FileDropzone already migrated, preview table still MUI. |
| `CertifiedResultsDrawer.tsx` | `Button`, `ButtonBase`, `Chip`, `Paper`, `Stack`, `Typography` | Complementary result panel, not currently using shared AppDrawer. |
| `TaxResultPanel.tsx` | `Button`, `Paper`, `Stack`, `Typography` | Save plan action and computed tax result. |
| `TaxSummaryCards.tsx` | `Paper`, `Stack`, `Typography` | Summary cards. |
| `MonthPicker` | MUI X DatePicker compat | Temporary compat from Phase 4; date/month migration still pending. |

## User-visible Entrypoints

- Page heading: `税金抵扣计划与试算`。
- Month picker: current month, `YYYY-MM` behavior from `MonthPicker`。
- Header action: `已认证发票导入` shown only when `canMutateData`。
- Output table: `销项票开票情况` read-only table。
- Input plan table: `进项票认证计划` selectable table。
- Input table actions: `全选` and `清空`。
- Tax table filters: inline search/filter dialog for counterparty。
- Tax table sorting: time sort button with accessible action label。
- Tax layout shared horizontal scrollbar: `税金抵扣表格横向滚动`。
- Save plan action: `保存计划` shown only when mutable, disabled during refresh/calculation/loading。
- Certified import modal: upload, preview, confirm, immediate invalid file feedback。
- Certified preview row table: `<fileName> 行级预览结果`。
- Certified results panel: `role="complementary"` / `已认证结果`，collapse/expand button。

## Existing Test Coverage

`web/src/test/TaxOffsetPage.test.tsx` already covers:

- Aborted initial load clears loading state。
- Read-only output table, editable input plan table, certified result panel。
- Read-export users cannot import or save。
- Certified invoice import preview/confirm refreshes summary and locks matched row。
- File drop upload and invalid file rejection。
- Recalculate with selected rows。
- Select all / clear。
- Inline search, time sorting, counterparty filters。
- Missing tax amount and empty statuses。
- MUI-specific assertion still present: import modal expects `modal.closest(".MuiDialog-root")`。

## Migration Slices

Recommended Micro-JIT sequence:

1. `P023-phase-6-tax-offset-characterization-tests`
   - Convert MUI-specific dialog assertion from `.MuiDialog-root` to project dialog primitive contract。
   - Add/adjust assertions for TaxTable column roles and preview table semantics without changing implementation。
   - Expected fail is acceptable if new primitive classes are not yet present。
2. `P024-phase-6-tax-offset-import-modal`
   - Migrate `CertifiedInvoiceImportModal` from MUI Dialog/Table/Chip/LinearProgress to AppDialog/FinanceTable/HeroUI primitives。
   - Keep FileDropzone and all upload/preview/confirm behavior。
3. `P025-phase-6-tax-offset-tax-table`
   - Migrate `TaxTable` tables, checkboxes, filter buttons/dialog surfaces carefully。
   - Preserve table role/name, selection, filters, sorting, horizontal scroll and column content。
4. `P026-phase-6-tax-offset-result-panel`
   - Migrate `TaxResultPanel` and `TaxSummaryCards` cards/buttons/typography。
5. `P027-phase-6-tax-offset-certified-results`
   - Migrate `CertifiedResultsDrawer` side/complementary panel while preserving collapse/expand and row selection。
6. `MG-phase-6-tax-offset`
   - Full TaxOffset tests, build, non-workbench MUI import grep for TaxOffset scope, docs update, push。

## Execution Update

- `P023-phase-6-tax-offset-characterization-tests`: updated `TaxOffsetPage.test.tsx` from MUI class/table assertions to project dialog and FinanceTable grid contracts. Initial targeted run expected-failed with 6 failures because the page still rendered MUI tables.
- `P024-phase-6-tax-offset-import-modal`: migrated `CertifiedInvoiceImportModal` to `AppDialog`, HeroUI feedback/buttons/chips/progress, and `FinanceTable` preview rows.
- `P025-phase-6-tax-offset-tax-table`: migrated `TaxTable` to `FinanceTable`, HeroUI `Checkbox`/`Button`, and local non-MUI search while preserving filter, sort, selection, highlighted row and horizontal scrollbar behavior.
- `P026-phase-6-tax-offset-result-panel`: migrated `TaxResultPanel` and `TaxSummaryCards` to HeroUI/native token classes.
- `P027-phase-6-tax-offset-certified-results`: migrated `CertifiedResultsDrawer` to HeroUI/native controls while preserving the complementary side panel and collapse/expand behavior.
- Page-level cleanup: migrated `TaxOffsetPage.tsx` header actions, feedback note, workspace containers and select/clear buttons away from MUI.
- Current TaxOffset scope has no `@mui/*` imports in `web/src/pages/TaxOffsetPage.tsx` or `web/src/components/tax/*`.

## Verification

- `cd web && npx vitest run TaxOffsetPage.test.tsx`: passed, 17 tests.
- `cd web && npx vitest run TaxOffsetPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed, 32 tests.
- `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning.
- `rg -n '@mui/' web/src/pages/TaxOffsetPage.tsx web/src/components/tax`: passed with no matches.
- `git diff --check`: passed.

## P023 Prompt Draft

```text
Prompt ID: P023-phase-6-tax-offset-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只调整 TaxOffsetPage tests，锁定新 primitives 的行为契约；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_tax_offset.md、docs/refactor-ui/test_migration_strategy.md、web/src/test/TaxOffsetPage.test.tsx、web/src/components/common/AppDialog.tsx、web/src/components/common/FinanceTable.tsx、web/src/components/tax/CertifiedInvoiceImportModal.tsx、web/src/components/tax/TaxTable.tsx。将 TaxOffsetPage.test.tsx 中 `.MuiDialog-root` 断言改为项目 dialog primitive 语义；为认证导入预览表和 TaxTable 增加稳定的列/role/入口断言，避免 MUI class 断言。不得修改实现、后端、API、read model、worker 或关联台。运行 `cd web && npx vitest run TaxOffsetPage.test.tsx`，预期在实现未迁移前可 expected-fail；运行 git diff --check、git status。更新 state/prompt/module docs，生成 P024 import modal refactor prompt。
```
