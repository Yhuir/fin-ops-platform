# Workbench MUI Migration

本文档记录关联台内部工作区从残留 MUI 迁移到 HeroUI v3 + Tailwind CSS v4 + 项目本地 primitives 的专项发现、切片队列和验证事实。

## Scope

- 目标分支：`refactor-ui`。
- 目标栈：React 19 + HeroUI v3 + Tailwind CSS v4 + project primitives。
- 范围：`web/src/pages/ReconciliationWorkbenchPage.tsx` 和 `web/src/components/workbench/*` 中的残留 MUI 控件、workbench `.Mui*` CSS、workbench test-only legacy MUI provider、最终 MUI/Emotion dependency cleanup。
- 非目标：不重写后端、API contract、read model、worker、权限语义、业务状态机；不把三栏工作区改成 HeroUI Table；不改变 App Shell 已完成的大布局。

## Behavioral Equivalence Rules

- 旧入口必须保留：按钮、筛选、toggle、搜索、展开、行操作、详情抽屉、异常弹窗、确认/撤回/批量操作。
- 旧右侧抽屉仍必须是右侧抽屉；旧弹窗仍必须是弹窗。
- `ResizableTriPane`、`CandidateGroupGrid`、三栏布局、同步滚动、列拖拽、候选组折叠/展开、行选中/高亮是核心工作台结构，不在本专项中重写。
- HeroUI 仅替换残留 MUI 表层控件；复杂三栏行列结构继续使用 custom DOM/CSS 和 project primitives。

## P-WB001 Baseline

- Prompt ID: `P-WB001-baseline-discovery`
- Phase: `wb_phase_0_baseline`
- Type: `discovery/planning`
- Runtime changed: no.
- CSS changed: no.
- Tests changed: no.
- Dependencies changed: no.
- Backend/API/read model/worker changed: no.

## Current MUI Inventory

Baseline command:

```bash
rg -n "^import .*@mui|from \"@mui|from '@mui|@mui/|Mui[A-Z]|\\.Mui" web/src/pages/ReconciliationWorkbenchPage.tsx web/src/components/workbench web/src/test/legacyWorkbenchMuiProvider.tsx web/src/test/workbenchRenderHelpers.tsx web/src/test/WorkbenchExceptionModal.test.tsx web/src/app/styles.css
```

### Runtime MUI Files

| File | MUI dependency | Migration target | Risk |
| --- | --- | --- | --- |
| `web/src/components/workbench/WorkbenchZone.tsx` | migrated in `P-WB003` | Semantic `div`/`span`/`button` with existing project class hooks | resolved |
| `web/src/components/workbench/WorkbenchPaneSearch.tsx` | migrated in `P-WB004` | Native search input/button with existing project class hooks | resolved |
| `web/src/components/workbench/WorkbenchRecordCard.tsx` | migrated in `P-WB005` | Native warning icon buttons + project tooltip classes | resolved |

`web/src/pages/ReconciliationWorkbenchPage.tsx` 当前没有直接 MUI import。

### Workbench CSS MUI Selectors

`web/src/app/styles.css` workbench `.Mui*` selectors were removed in `P-WB006`. Current migration status:

- Zone title, selection pills/buttons, pane toggles and expand icon buttons now use stable project selectors.
- Pane search field now uses native `.pane-search-input-wrap`、`.pane-search-input-icon`、`.pane-search-field`、`.pane-search-clear-btn` styles.
- Record warning tooltip/icon buttons now use `.record-warning-tooltip-wrap`、`.record-warning-icon-btn`、`.record-warning-icon`、`.bank-amount-mismatch-tooltip`.
- CSS grep `rg -n "\\.Mui|Mui[A-Z]" web/src/app/styles.css web/src/components/workbench` is expected to have no output.

### Test-only MUI Boundary

| File | Current role | Migration target |
| --- | --- | --- |
| `web/src/test/legacyWorkbenchMuiProvider.tsx` | MUI ThemeProvider, CssBaseline, date picker LocalizationProvider for legacy workbench tests | Delete after workbench runtime no longer needs MUI |
| `web/src/test/workbenchRenderHelpers.tsx` | Wraps workbench tests with `LegacyWorkbenchMuiProvider` | Switch to project/HeroUI test provider |
| `web/src/test/WorkbenchExceptionModal.test.tsx` | Uses `LegacyWorkbenchMuiProvider` for modal render helper path | Remove legacy provider wrapping |

### Non-workbench Runtime MUI Scan

Command:

```bash
rg -n "from \"@mui|from '@mui|@mui/" web/src --glob "!web/src/components/workbench/**" --glob "!web/src/test/**"
```

Result: no output. Non-workbench runtime remains no-MUI at the start of this专项.

### Package Dependency Baseline

`web/package.json` still lists:

- `@emotion/react`
- `@emotion/styled`
- `@mui/icons-material`
- `@mui/material`
- `@mui/x-data-grid`
- `@mui/x-date-pickers`

These must remain until runtime/test references are removed, then be audited in `wb_phase_7_dependency_cleanup`. `@mui/x-data-grid` appears unused at runtime but remains in dependency baseline and lockfile until final dependency cleanup.

## Workbench Component Inventory

### Direct MUI-hit Counts

| Hits | File |
| --- | --- |
| 0 | `web/src/components/workbench/WorkbenchZone.tsx` after `P-WB003` |
| 0 | `web/src/components/workbench/WorkbenchPaneSearch.tsx` after `P-WB004` |
| 0 | `web/src/components/workbench/WorkbenchRecordCard.tsx` after `P-WB005` |
| 0 | all other `web/src/components/workbench/*.tsx` files in the baseline count |

### Core Workbench Files to Preserve

- `web/src/components/workbench/ResizableTriPane.tsx`
- `web/src/components/workbench/CandidateGroupGrid.tsx`
- `web/src/components/workbench/CandidateGroupCell.tsx`
- `web/src/components/workbench/PaneTable.tsx`
- `web/src/components/workbench/RelationPreviewTriPane.tsx`
- `web/src/components/workbench/RowActions.tsx`
- `web/src/components/workbench/DetailDrawer.tsx`
- `web/src/components/workbench/WorkbenchExceptionModal.tsx`
- `web/src/components/workbench/ProcessedExceptionsModal.tsx`
- `web/src/components/workbench/OaBankExceptionModal.tsx`
- `web/src/components/workbench/WorkbenchColumnFilterMenu.tsx`
- `web/src/components/workbench/WorkbenchPaneTimeFilter.tsx`
- `web/src/components/workbench/WorkbenchSettingsModal.tsx`

These files currently have no direct MUI hit in the baseline scan. They may need regression tests but should not be structurally rewritten for this migration.

## Test Inventory

Workbench-related tests at baseline:

- `web/src/test/WorkbenchZone.test.tsx`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/WorkbenchColumns.test.tsx`
- `web/src/test/CandidateGroupGrid.test.tsx`
- `web/src/test/WorkbenchPaneFilter.test.ts`
- `web/src/test/WorkbenchColumnLayout.test.tsx`
- `web/src/test/WorkbenchExceptionModal.test.tsx`
- `web/src/test/ProcessedExceptionsModal.test.tsx`
- `web/src/test/OaBankExceptionModal.test.tsx`
- `web/src/test/WorkbenchApi.test.ts`
- `web/src/test/WorkbenchApiRuntimePath.test.ts`

`wb_phase_1_characterization` should add or extend tests around:

- `WorkbenchZone`: title, counts, toolbar buttons, selection pill, toggle, expand, disabled/loading/tooltip.
- `WorkbenchPaneSearch`: open/close, typing, clear, focus, result summary, keyboard behavior.
- `WorkbenchRecordCard`: warning icon, tooltip, row click, detail entry, action bubbling isolation.
- Source contract: current MUI runtime files are expected-fail targets until phases 2-4 migrate them.

## P-WB002 Characterization

- Prompt ID: `P-WB002-characterization-tests`
- Phase: `wb_phase_1_characterization`
- Type: `characterization tests`
- Runtime changed: no.
- CSS changed: no.
- Dependencies changed: no.
- Backend/API/read model/worker changed: no.

### Tests Added

`web/src/test/WorkbenchZone.test.tsx` now covers:

- Selection toolbar counts, actions and disabled primary action.
- Pane toggle `aria-pressed`, last-visible-pane disabled state and expand callback.
- `WorkbenchPaneSearch` focus, typing, clear action, outside close and applied summary state.
- Source-level current target contract: direct residual MUI runtime targets are exactly `WorkbenchZone.tsx`, `WorkbenchPaneSearch.tsx`, `WorkbenchRecordCard.tsx`; `ResizableTriPane.tsx` and `CandidateGroupGrid.tsx` remain no-MUI core files.

`web/src/test/WorkbenchColumns.test.tsx` now covers:

- Bank amount mismatch warning icon click opens the warning detail without selecting the row or opening detail.
- Invoice row action column `详情` and `忽略` do not bubble into row selection.

### Verification

```bash
cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx
cd web && npx vitest run WorkbenchSelection.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx
if rg -n "from \"@mui|from '@mui|@mui/" web/src --glob "!web/src/components/workbench/**" --glob "!web/src/test/**"; then exit 1; else exit 0; fi
git diff --check
```

Results: targeted tests passed; 2 files / 36 tests and 8 files / 118 tests. Non-workbench runtime MUI scan and diff check passed.

## P-WB003 Zone Header Controls

- Prompt ID: `P-WB003-zone-header-controls`
- Phase: `wb_phase_2_zone_header_controls`
- Type: `extraction/refactor`
- Runtime changed:
  - `web/src/components/workbench/WorkbenchZone.tsx`
- Test changed:
  - `web/src/test/WorkbenchZone.test.tsx` source target contract now expects remaining MUI targets to be `WorkbenchPaneSearch.tsx` and `WorkbenchRecordCard.tsx`.
- CSS changed: no.
- Dependencies changed: no.
- Backend/API/read model/worker changed: no.

### Result

`WorkbenchZone.tsx` no longer imports or renders MUI components. It preserves existing class hooks and behavior for:

- zone title/meta;
- selection summary/action toolbar;
- auxiliary header actions;
- pane toggle group;
- expand icon button;
- page footer load-more button;
- `ResizableTriPane` props and tri-pane behavior.

Remaining direct runtime MUI targets are now:

- `web/src/components/workbench/WorkbenchPaneSearch.tsx`
- `web/src/components/workbench/WorkbenchRecordCard.tsx`

### Verification

```bash
if rg -n '@mui/|Mui[A-Z]|<Box\b|<Stack\b|<Typography\b|<Chip\b|<ToggleButton\b|<ToggleButtonGroup\b|<IconButton\b|<Button\b|<Tooltip\b' web/src/components/workbench/WorkbenchZone.tsx; then exit 1; else exit 0; fi
cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx
cd web && npx vitest run WorkbenchSelection.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx WorkbenchExceptionModal.test.tsx ProcessedExceptionsModal.test.tsx OaBankExceptionModal.test.tsx
cd web && npm run build
git diff --check
```

Results: all passed. Build still reports known HeroUI/Tailwind CSS minifier warnings and chunk size warning.

## P-WB004 Pane Search

- Prompt ID: `P-WB004-pane-search`
- Phase: `wb_phase_3_pane_search`
- Type: `extraction/refactor`
- Runtime changed:
  - `web/src/components/workbench/WorkbenchPaneSearch.tsx`
- Test changed:
  - `web/src/test/WorkbenchZone.test.tsx` source target contract now expects only `WorkbenchRecordCard.tsx` to remain as a direct runtime MUI target.
- CSS changed: no.
- Dependencies changed: no.
- Backend/API/read model/worker changed: no.

### Result

`WorkbenchPaneSearch.tsx` no longer imports or renders MUI components. It preserves:

- open/focus/select behavior;
- outside mousedown close;
- `onChange`, `onClear`, `onToggle`, `onClose`;
- searchbox and clear button accessible labels;
- applied summary button text/label;
- existing `pane-search*` class hooks.

Remaining direct runtime MUI target:

- none in `web/src/components/workbench/*.tsx`

### Verification

```bash
if rg -n '@mui/|Mui[A-Z]|<Grow\b|<TextField\b|<InputAdornment\b|<IconButton\b|ClearIcon|SearchIcon' web/src/components/workbench/WorkbenchPaneSearch.tsx; then exit 1; else exit 0; fi
cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchPaneFilter.test.ts WorkbenchSelection.test.tsx
cd web && npm run build
git diff --check
```

Results: all passed. Build still reports known HeroUI/Tailwind CSS minifier warnings and chunk size warning.

## P-WB005 Record Card Actions

- Prompt ID: `P-WB005-record-card-actions`
- Phase: `wb_phase_4_record_card_actions`
- Type: `extraction/refactor`
- Runtime changed:
  - `web/src/components/workbench/WorkbenchRecordCard.tsx`
- Test changed:
  - `web/src/test/WorkbenchZone.test.tsx` source target contract now expects zero direct runtime MUI targets in workbench component files.
- CSS changed: no.
- Dependencies changed: no.
- Backend/API/read model/worker changed: no.

### Result

`WorkbenchRecordCard.tsx` no longer imports or renders MUI components. It preserves:

- amount mismatch and reconciliation warning accessible labels;
- hover/focus/click/touch tooltip open behavior;
- `stopPropagation` so warning/action clicks do not trigger row selection or detail opening;
- tooltip text, warning titles and amount formatting;
- record card layout and existing row/action behavior.

Direct runtime MUI targets in `web/src/components/workbench/*.tsx` are now zero. Remaining workbench MUI cleanup is limited to:

- test-only `legacyWorkbenchMuiProvider` and related render helpers;
- package dependencies after no references remain.

### Verification

```bash
if rg -n '@mui/|Mui[A-Z]|WarningAmberRoundedIcon|<IconButton\b|<Tooltip\b|sx=|MuiSvgIcon' web/src/components/workbench/WorkbenchRecordCard.tsx; then exit 1; else exit 0; fi
cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx
cd web && npm run build
```

Results: all passed. Build still reports known HeroUI/Tailwind CSS minifier warnings and chunk size warning.

## P-WB006 CSS Containment Cleanup

- Prompt ID: `P-WB006-css-containment-cleanup`
- Phase: `wb_phase_5_css_containment_cleanup`
- Type: `extraction/refactor`
- Runtime changed: no.
- CSS changed:
  - `web/src/app/styles.css`
- Test changed:
  - `web/src/test/WorkbenchZone.test.tsx` source contract now asserts no `.Mui`/`Mui[A-Z]` hooks remain in `styles.css`.
- Dependencies changed: no.
- Backend/API/read model/worker changed: no.

### Result

Workbench CSS no longer depends on MUI-generated classes. The migrated styles preserve:

- zone title, selection pill/button density and hover/focus/disabled states;
- pane toggle active/disabled/hover states;
- expand icon button size and state colors;
- native pane search input sizing, icon, clear button and focus ring;
- record warning icon button and tooltip positioning.

Remaining workbench MUI cleanup is limited to:

- test-only `legacyWorkbenchMuiProvider` and related render helpers;
- package dependencies after no references remain.

### Verification

```bash
if rg -n '\.Mui|Mui[A-Z]' web/src/app/styles.css web/src/components/workbench; then exit 1; else exit 0; fi
cd web && npx vitest run WorkbenchZone.test.tsx WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx
cd web && npm run build
git diff --check
```

Results: all passed. Build still reports known HeroUI/Tailwind CSS minifier warnings and chunk size warning.

## Recommended Micro-JIT Queue

1. `P-WB002-characterization-tests`
   - Add behavior tests and source contract for the three residual MUI runtime files.
   - Runtime/CSS/dependency unchanged.
2. `P-WB003-zone-header-controls`
   - Migrate `WorkbenchZone.tsx`.
3. `P-WB004-pane-search`
   - Migrate `WorkbenchPaneSearch.tsx`.
4. `P-WB005-record-card-actions`
   - Migrate `WorkbenchRecordCard.tsx`. Completed.
5. `P-WB006-css-containment-cleanup`
   - Remove workbench `.Mui*` selectors from `styles.css`. Completed.
6. `P-WB007-test-provider-cleanup`
   - Remove `legacyWorkbenchMuiProvider` and update render helpers/tests.
7. `P-WB008-dependency-cleanup`
   - Remove MUI/Emotion deps after no references remain.
8. `P-WB009-full-verification`
   - Run workbench tests, non-workbench regressions, no-MUI scans, build and smoke.
9. `P-WB010-closeout`
   - Final docs/state/prompt closeout and push log.

## Risks

| Risk | Level | Mitigation |
| --- | --- | --- |
| WorkbenchZone selection toolbar/toggle behavior changes | high | Add characterization tests before implementation |
| Pane search focus and outside-click behavior regresses | medium | Test search open/input/clear/focus/summary before migration |
| Record card icon button click bubbles into row selection/detail | medium | Test action click propagation before migration |
| `.Mui*` CSS cleanup changes density or alignment | medium | Stable project selectors and targeted visual/DOM assertions |
| Removing legacy MUI provider breaks workbench tests indirectly | medium | Provider cleanup after all runtime MUI is gone |
| Removing MUI dependencies while hidden references remain | high | Full source scans and `npm ls` before dependency cleanup |

## Verification Notes

Baseline verification already run:

```bash
git status --short --branch
rg -n "^import .*@mui|from \"@mui|from '@mui|@mui/|Mui[A-Z]|\\.Mui" web/src/pages/ReconciliationWorkbenchPage.tsx web/src/components/workbench web/src/test/legacyWorkbenchMuiProvider.tsx web/src/test/workbenchRenderHelpers.tsx web/src/test/WorkbenchExceptionModal.test.tsx web/src/app/styles.css
rg -n "from \"@mui|from '@mui|@mui/" web/src --glob "!web/src/components/workbench/**" --glob "!web/src/test/**"
rg -n "\\.Mui|Mui[A-Z]" web/src/app/styles.css web/src/components/workbench web/src/test
rg -n "@mui|emotion" web/package.json web/package-lock.json | head -120
```
