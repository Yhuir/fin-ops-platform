# Phase 7 MUI Containment

本文档记录 Phase 7 的 MUI containment 发现结果和后续 Micro-JIT 队列。Phase 7 的目标不是重构关联台内部工作区，而是证明非关联台 runtime 不再依赖 MUI，并把仍需保留的关联台 legacy MUI 隔离清楚。

## P107 Discovery

- Prompt ID: `P107-phase-7-mui-containment-discovery`
- Phase: `phase_7_mui_containment`
- Type: `discovery/planning`
- Scope: MUI containment inventory only.
- Runtime changed: no.
- Tests changed: no.
- CSS changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

## Current MUI Inventory

当前命中命令：

```bash
rg -l "@mui/|Mui[A-Z]|muiTheme|MuiProviders|MuiDatePickerCompatProvider|useMuiDataGrid|@mui/x-date-pickers|@mui/x-data-grid" web/src | sort
```

### Non-workbench Runtime Targets

这些文件仍是非关联台 runtime 或全局 runtime，必须在 Phase 7 处理：

| File | Category | Why It Remains | Target |
| --- | --- | --- | --- |
| `web/src/components/MonthPicker.tsx` | month/date primitive | Still uses MUI Box, MUI X DatePicker and StaticDatePicker. | Replace with native/project month picker while preserving `YYYY-MM`, inline mode, aria labels and `formatMonthLabel`. |
| `web/src/app/MuiDatePickerCompatProvider.tsx` | date compatibility provider | Exists only because `MonthPicker` still needs MUI X LocalizationProvider. | Remove after MonthPicker migration, or prove no MUI X date picker remains. |
| `web/src/app/App.tsx` | app provider boundary | Imports `MuiDatePickerCompatProvider`. | Remove date compat wrapper after MonthPicker migration while preserving provider order and route behavior. |
| `web/src/app/MuiProviders.tsx` | test/legacy provider | Wraps MUI ThemeProvider, LocalizationProvider and CssBaseline. Currently used by tests and legacy workbench-related tests. | Split or replace: non-workbench tests should use project test provider; workbench legacy can keep a named legacy provider if needed. |
| `web/src/app/muiTheme.ts` | MUI theme | Supplies MUI core/DataGrid/date locale and global MUI TableCell overrides. | Delete or move behind explicit workbench legacy boundary after tests/provider cleanup. |
| `web/src/hooks/useMuiDataGridPageSession.ts` | obsolete MUI DataGrid session hook | No migrated page should depend on MUI DataGrid session. | Delete if unused; otherwise replace with `useFinanceTableSession` or a project-native session boundary. |
| `web/src/app/styles.css` | global CSS | Contains MUI DataGrid selectors and workbench legacy `.Mui*` selectors. | Remove non-workbench selectors; retain only documented workbench legacy selectors under a containment section. |
| `web/src/test/renderHelpers.tsx` | test harness | Imports `MuiProviders`, so non-workbench tests still get MUI wrappers. | Replace default app render helper with project provider; use explicit workbench legacy helper only for frozen workbench tests. |

### Allowed Workbench Legacy

These files are inside the frozen reconciliation workbench internal workspace and are allowed to keep MUI during this refactor:

| File | Reason |
| --- | --- |
| `web/src/components/workbench/WorkbenchRecordCard.tsx` | Frozen workbench internal row/card interaction. |
| `web/src/components/workbench/WorkbenchPaneSearch.tsx` | Frozen workbench internal pane search. |
| `web/src/components/workbench/WorkbenchZone.tsx` | Frozen workbench internal three-zone workspace. |

Phase 7 must not visually migrate, restyle or restructure these files. It may only document them and ensure their required providers/styles are isolated.

### Test Harness and Test String Hits

Test files contain three different kinds of MUI hits:

1. **Provider imports that must be replaced for non-workbench tests**
   - `web/src/test/renderHelpers.tsx`
   - `web/src/test/CommonMuiComponents.test.tsx`
   - `web/src/test/MonthPicker.test.tsx`
   - `web/src/test/BankDetailsPage.test.tsx`
   - `web/src/test/BatchAccountingPage.test.tsx`
   - `web/src/test/CostStatisticsPage.test.tsx`
   - `web/src/test/NoOaBankBatchPage.test.tsx`
   - `web/src/test/SettingsOaManualSearchImportTable.test.tsx`
   - `web/src/test/TurnoverLedgerPage.test.tsx`
   - `web/src/test/AutoTagRulesDrawer.test.tsx`

2. **MUI-only tests that should be migrated or deleted with runtime cleanup**
   - `web/src/test/MonthPicker.test.tsx`: currently protects MUI X field structure and must be rewritten to user-visible month picker behavior before replacing MonthPicker.
   - `web/src/test/useMuiDataGridPageSession.test.tsx`: tied to `useMuiDataGridPageSession` and MUI DataGrid types; should move to `useFinanceTableSession` coverage or be deleted if the hook is deleted.

3. **Negative source-contract strings that can remain**
   - Many migrated page tests include strings such as `@mui/`, `.Mui*`, `DataGrid`, or `MuiDialog-root` only to assert absence. These are acceptable if they do not import MUI and do not render MUI providers.

### Global CSS MUI Selectors

`web/src/app/styles.css` still contains:

- MUI DataGrid selectors around the global table/DataGrid section.
- Workbench legacy selectors such as `.zone-title.MuiTypography-root`, `.zone-selection-pill.MuiChip-root`, `.zone-toggle.MuiToggleButton-root`, `.pane-search-field .MuiOutlinedInput-root`.

Phase 7 must split these into:

- **Remove**: MUI DataGrid selectors not owned by frozen workbench.
- **Keep with comment/containment**: workbench-specific selectors required by frozen internal workbench files.
- **Do not broaden**: no new non-workbench `.Mui*` selectors.

## Non-workbench Runtime Targets

The first hard gate for Phase 7 should eventually pass:

```bash
if rg -n "@mui/|Mui[A-Z]|muiTheme|MuiProviders|MuiDatePickerCompatProvider|useMuiDataGrid|@mui/x-date-pickers|@mui/x-data-grid" web/src --glob "!components/workbench/**" --glob "!**/*.test.ts" --glob "!**/*.test.tsx"; then exit 1; else exit 0; fi
```

Expected current blockers:

- `App.tsx`
- `MuiDatePickerCompatProvider.tsx`
- `MuiProviders.tsx`
- `muiTheme.ts`
- `MonthPicker.tsx`
- `useMuiDataGridPageSession.ts`
- non-workbench portions of `styles.css`

## MonthPicker / Date Compat Boundary

Migration requirements:

- Preserve `formatMonthLabel(value: string): string`.
- Preserve external value format `YYYY-MM`.
- Preserve invalid/partial fallback behavior from `parseMonthValue`.
- Preserve default aria label `年月选择` and default caption `月份`.
- Preserve inline and non-inline modes.
- Preserve current user flow in tests: open month picker, choose year, choose month, emit `YYYY-MM`.
- Remove MUI X LocalizationProvider after the new MonthPicker no longer needs it.
- Do not change `MonthProvider` or app default month logic.

## DataGrid Session Boundary

Current `useMuiDataGridPageSession.ts` persists:

- pagination model;
- sort model;
- filter model;
- column visibility;
- row selection;
- column widths;
- column order;
- virtual scroller position.

Discovery expectation: migrated pages no longer use this hook. Phase 7 should verify references. If only the hook and its test remain, delete them and rely on `useFinanceTableSession` coverage. If any page still imports it, generate a targeted migration prompt for that page/hook before deletion.

## Provider / Test Harness Boundary

Current test helpers still import `MuiProviders`. Phase 7 should separate:

- project app test provider for non-workbench tests;
- explicit legacy MUI provider for workbench-only tests if needed;
- no default render helper should wrap non-workbench UI in MUI ThemeProvider/CssBaseline once MonthPicker is migrated.

## Recommended Micro-JIT Queue

1. `P108-phase-7-month-picker-characterization-tests`
   - Rewrite MonthPicker tests from MUI X class/role protection to behavior/ARIA contract.
   - Add source-level no-MUI contract for `MonthPicker.tsx`, `MuiDatePickerCompatProvider.tsx`, and the App provider wrapper.
   - Expected source-level contract fails before implementation; behavior tests must pass.
2. `P109-phase-7-month-picker-and-date-compat`
   - Replace MUI X MonthPicker with native/project month picker.
   - Remove `MuiDatePickerCompatProvider` and its wrapper in `App.tsx`.
   - Preserve `YYYY-MM`, inline mode, labels and `formatMonthLabel`.
3. `P110-phase-7-datagrid-session-cleanup`
   - Verify no runtime references to `useMuiDataGridPageSession`.
   - Delete `useMuiDataGridPageSession.ts` and migrate/delete its test.
   - Ensure `useFinanceTableSession` tests cover remaining project session behavior.
4. `P111-phase-7-test-provider-containment`
   - Replace non-workbench `MuiProviders` test harness usage with project provider helper.
   - Keep an explicit legacy provider only for frozen workbench tests if still required.
5. `P112-phase-7-global-css-containment`
   - Remove non-workbench `.Mui*` and MUI DataGrid selectors from `styles.css`.
   - Keep only documented workbench legacy selectors in a labeled containment block.
6. `P113-phase-7-final-no-mui-contract`
   - Add a repository-level source contract proving non-workbench runtime has no MUI imports/selectors/providers.
   - Allowed list must be restricted to `web/src/components/workbench/*` and explicitly documented legacy helpers if any.
7. `MG-P113-phase-7-mui-containment`
   - Run the final no-MUI contract, MonthPicker tests, table/common/HeroUI smoke, workbench smoke tests, build, diff/status and docs checks.

## P108 Prompt Draft

```text
Prompt ID: P108-phase-7-month-picker-characterization-tests
Phase: phase_7_mui_containment
Type: characterization tests
Scope: MonthPicker/date compat characterization tests only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_7_mui_containment.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/MonthPicker.tsx、web/src/test/MonthPicker.test.tsx、web/src/app/App.tsx、web/src/app/MuiDatePickerCompatProvider.tsx 和 web/src/app/styles.css。只修改 MonthPicker/date compat 相关测试，不改 runtime code、CSS、依赖、backend、API、read model、worker 或关联台内部工作区。把 `MonthPicker.test.tsx` 中保护 MUI X field/class 的断言改成用户可见行为和 ARIA 合约：普通模式显示当前 `YYYY-MM` 对应年月、点击 `年月选择` 后可选择年份和月份并 emit `YYYY-MM`、inline 模式可直接选择月份、`formatMonthLabel` 保持中文年月、invalid month fallback 保持可预测。添加 source-level no-MUI/date-compat contract，覆盖 `MonthPicker.tsx`、`MuiDatePickerCompatProvider.tsx` 和 `App.tsx` date compat wrapper，预期 contract 失败但行为测试通过。运行 `cd web && npx vitest run MonthPicker.test.tsx`，预期 behavior tests pass and source-level contract fails against current MUI X runtime；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P109 month picker/date compat implementation prompt。
```

## P107 Push

- Commit: `f135e4bd docs: add mui containment discovery`, pushed to `origin/refactor-ui`.

## P108 Execution Notes

- Prompt ID: `P108-phase-7-month-picker-characterization-tests`
- Status: `verified`
- Runtime implementation changed: no.
- Test implementation changed:
  - `MonthPicker.test.tsx` now reads source files for `MonthPicker.tsx`, `MuiDatePickerCompatProvider.tsx` and `App.tsx`.
  - Replaced the old `.MuiFormControl-root` assertion with user-visible month field semantics.
  - Added inline month selection coverage.
  - Added `formatMonthLabel` coverage for normal and invalid values.
  - Added a source-level no-MUI/date-compat contract that currently fails against the MUI X MonthPicker runtime.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - `cd web && npx vitest run MonthPicker.test.tsx`: expected-fail; 4 behavior tests passed, 1 source-level contract failed.
  - Expected failure files: `src/components/MonthPicker.tsx`, `src/app/MuiDatePickerCompatProvider.tsx`.
  - `git diff --check`: passed.

## P109 Prompt Draft

```text
Prompt ID: P109-phase-7-month-picker-and-date-compat
Phase: phase_7_mui_containment
Type: extraction/refactor
Scope: MonthPicker/date compat implementation only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_7_mui_containment.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/MonthPicker.tsx、web/src/test/MonthPicker.test.tsx、web/src/app/App.tsx、web/src/app/MuiDatePickerCompatProvider.tsx 和 web/src/app/styles.css。只迁移 MonthPicker/date compat：把 `MonthPicker.tsx` 从 MUI Box、MUI X DatePicker、StaticDatePicker、SxProps/Theme 改为 native/project month picker；移除 `MuiDatePickerCompatProvider` 文件和 `App.tsx` 中的 wrapper/import；保留 `formatMonthLabel`、`YYYY-MM` external contract、invalid fallback、默认 aria label `年月选择`、caption `月份`、inline 和 non-inline modes、用户选择年份/月后 emit `YYYY-MM`。不得修改 MonthProvider、路由、业务 providers 顺序、backend、API、read model、worker 或关联台内部工作区。运行 `cd web && npx vitest run MonthPicker.test.tsx`，必须通过；运行 `cd web && npx vitest run App.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`，必须通过；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|MuiDatePickerCompatProvider|LocalizationProvider|DatePicker|StaticDatePicker|MuiInputBase|MuiFormControl' web/src/components/MonthPicker.tsx web/src/app/App.tsx web/src/app/MuiDatePickerCompatProvider.tsx; then exit 1; else exit 0; fi`，必须通过（若 `MuiDatePickerCompatProvider.tsx` 被删除，用 `test ! -f web/src/app/MuiDatePickerCompatProvider.tsx` 记录）；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P110 DataGrid session cleanup prompt。
```
