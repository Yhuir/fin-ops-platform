# Phase 6 Settings UI Migration

本文档记录 `/settings` 的 UI 平台迁移切片。目标是把设置页迁到 HeroUI/Tailwind/project primitives，同时保持设置导航、配置保存、高风险数据重置、OA 手工搜索导入、权限控制、API contract、后台任务和关联台内部工作区不变。

## P099 Discovery

- Prompt ID: `P099-phase-6-settings-discovery`
- Route: `/settings`
- Page: `web/src/pages/SettingsPage.tsx`
- Components:
  - `web/src/components/settings/SettingsPageContent.tsx`
  - `web/src/components/settings/SettingsTreeNav.tsx`
  - `web/src/components/settings/SettingsProjectsSection.tsx`
  - `web/src/components/settings/SettingsBankAccountsSection.tsx`
  - `web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx`
  - `web/src/components/settings/SettingsOaRetentionSection.tsx`
  - `web/src/components/settings/SettingsOaInvoiceOffsetSection.tsx`
  - `web/src/components/settings/SettingsAccessAccountsSection.tsx`
  - `web/src/components/settings/SettingsDataResetSection.tsx`
  - `web/src/components/settings/OaManualSearchImportTable.tsx`
  - `web/src/components/settings/settingsDesign.ts`
  - `web/src/components/settings/types.ts`
- Tests:
  - `web/src/test/SettingsPage.test.tsx`
  - `web/src/test/SettingsOaManualSearchImportTable.test.tsx`
- API/client facts:
  - `web/src/features/workbench/api.ts`
  - `web/src/features/workbench/types.ts`
- Non-goals:
  - 不修改 settings API client contract、mock response shape、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。
  - 不修改 `ReconciliationWorkbenchPage` 或 `web/src/components/workbench/*`。
  - 不修改 `MonthPicker` 或 frozen workbench legacy MUI；这些属于后续 containment/明确例外。

## Current MUI Inventory

Settings 是当前非关联台剩余 MUI 面最大的页面模块：

- `SettingsPage.tsx`: `Alert`, `Box`, `Stack`.
- `SettingsPageContent.tsx`: `Alert`, `Box`, `Button`, `CircularProgress`, `Dialog`, `DialogActions`, `DialogContent`, `DialogTitle`, `Stack`, `TextField`, `Typography`, `ThemeProvider`.
- `SettingsTreeNav.tsx`: `Box`, `List`, `ListItem`, `ListItemButton`, `ListItemText`, `Stack`, `Typography`.
- `SettingsProjectsSection.tsx`: MUI `DataGrid`, `Button`, `TextField`, `Alert`, `IconButton`, icons and grid column types.
- `SettingsBankAccountsSection.tsx`: MUI `DataGrid`, DataGrid session hooks, `Button`, `TextField`, `Alert`, `IconButton`, icons and grid column types.
- `SettingsAccessAccountsSection.tsx`: MUI `DataGrid`, `Select`, `InputLabel`, `FormControl`, `Button`, `TextField`, `Alert`, `IconButton`, icons and grid column types.
- `SettingsPendingInvoiceTagsSection.tsx`: `List`, `ListItem`, `ListItemButton`, `ListItemText`, `Menu`, `MenuItem`, `Chip`, `Button`, `IconButton`, `TextField`, `Tooltip`, icons.
- `SettingsOaRetentionSection.tsx`: `TextField`, `FormControl`, `FormControlLabel`, `FormGroup`, `FormLabel`, `Checkbox`, `Alert`, layout/typography.
- `SettingsOaInvoiceOffsetSection.tsx`: `TextField`, `Alert`, layout/typography.
- `SettingsDataResetSection.tsx`: `Alert`, `Card`, `LinearProgress`, `Button`, layout/typography.
- `OaManualSearchImportTable.tsx`: MUI native table wrappers, `TablePagination`, `Checkbox`, `Collapse`, `Alert`, `CircularProgress`, `Button`, `TextField`, `FormControl*`, `Chip`, `Tooltip`, icons.
- `settingsDesign.ts`: MUI `createTheme`, `SxProps`, `Theme`, DataGrid theme augmentation and local MUI token bridge.

## User-visible Entrypoints

The migration must preserve these visible entrypoints and accessible names:

- Page test id: `settings-page`.
- No extra legacy page header title `关联台设置`.
- Settings layout:
  - left navigation `设置导航`;
  - tree `设置分类`;
  - content section `设置内容`;
  - primary page heading `设置`;
  - save action `保存设置` / `保存中...`.
- Navigation tree items:
  - `项目状态`;
  - `银行账户`;
  - `待找发票筛选`;
  - `OA导入设置`;
  - `冲账规则` when allowed for `YNSYLP005` / `YNSYKJ001`;
  - `访问账户` for admin;
  - `数据重置` for admin.
- Sections and regions:
  - `项目状态管理`;
  - `银行账户映射`;
  - `待找发票筛选`;
  - `OA导入设置`;
  - `冲账规则`;
  - `访问账户`;
  - `高风险数据重置`.
- Project actions:
  - `从 OA 同步项目`;
  - add local project fields;
  - mark project completed / move back;
  - delete local project or override via `window.confirm`.
- Bank account actions:
  - add mapping fields for bank name, short name and last 4 digits;
  - edit/delete rows.
- Pending invoice tag actions:
  - group list `需要开票`, `流水代替发票`, `无需开票`;
  - `选择现有标签`;
  - menu items for active tags;
  - remove buttons such as `<label> 移除`;
  - invalid historical mappings `标签不存在` / `标签已停用`.
- OA import settings:
  - cutoff date;
  - form type checkboxes;
  - status checkboxes;
  - `OA全量搜索导入` surface.
- OA manual search/import table:
  - heading `OA全量搜索导入`;
  - search filters `搜索关键字`, `开始日期`, `结束日期`;
  - form type/status filter groups;
  - `搜索`, `导入已选OA项`, `清空选择`;
  - table `OA全量搜索导入结果`;
  - row selection `选择 OA <row_id>`;
  - current page selection `选择当前页可导入OA`;
  - detail toggle `展开 OA <row_id> 明细`;
  - refresh action `刷新 OA <row_id> 附件解析`;
  - pagination.
- Access account actions:
  - add username;
  - role select `新增账户权限`;
  - edit/delete access rows;
  - admin account notice.
- Data reset actions:
  - `清除所有银行流水数据`;
  - `清除所有发票（进销）数据`;
  - `清除所有 OA 数据并重新写入`;
  - dialog `确认数据重置`;
  - dialog `OA 密码复核`;
  - password field `当前 OA 用户密码`;
  - `继续`, `确认清理`, `取消`;
  - job progress text such as `正在清理 app 内部状态。 25%`.

## Existing Test Coverage

`SettingsPage.test.tsx` currently covers:

- Settings renders as tree-and-panel page without an extra page header title.
- Section switching from project status to bank account mapping.
- Workbench-only header actions stay out of standalone Settings.
- Read-only users cannot save settings.
- Data reset requires impact confirmation, OA password review and job progress.
- Pending invoice tag mappings can be changed through an existing-tag menu.
- Invalid historical pending invoice mappings stay visible and block save until removed.

Current test issue:

- The first Settings test asserts `tree` has class `MuiList-root`; P100 must replace this with user-visible semantics and a source-level no-MUI/project primitive contract.

`SettingsOaManualSearchImportTable.test.tsx` currently covers:

- OA search filters and request query.
- Native MUI table semantics and no DataGrid surface.
- Selectable/importable rows, disabled non-importable rows, expanded detail rows, attachment refresh, import payload and clear selection.
- Staged OA import progress must not leak to the global shell status mark.

Current test issue:

- The first OA manual import table test name says "MUI table semantics"; P100 must rename/adjust this to native table/user-observable table semantics without protecting MUI implementation.

## API / Contract Risks

- Settings main API is `/api/workbench/settings`.
- Project sync/create/delete use:
  - `/api/workbench/settings/projects/sync`;
  - `/api/workbench/settings/projects`;
  - `/api/workbench/settings/projects/{projectId}`.
- Data reset uses:
  - `/api/workbench/settings/data-reset/jobs`;
  - `/api/workbench/settings/data-reset/jobs/active`;
  - `/api/workbench/settings/data-reset/jobs/{jobId}`.
- OA manual search/import uses:
  - `/api/workbench/settings/oa/manual-search`;
  - `/api/workbench/settings/oa/manual-search/refresh-attachments`;
  - `/api/workbench/settings/oa/manual-imports`.
- Save payload includes completed projects, bank account mappings, access control, workbench column layouts, OA retention/import, OA invoice offset, bank transaction tags and pending invoice tag groups.
- P100+ must not change payload keys, endpoint paths, actor ids, polling semantics or data reset confirmation flow.

## Table Layout Risks

- Settings has three editable MUI DataGrid surfaces:
  - active/completed projects;
  - bank account mappings;
  - access accounts.
- OA manual search has a dense 15-column table and nested detail table.
- Migration must keep table form factor:
  - do not turn tables into card lists;
  - keep row edit/delete actions in-row;
  - keep numeric amount/count columns right aligned and tabular;
  - preserve table accessible names;
  - preserve loading/empty/error states;
  - preserve pagination on OA manual search.
- DataGrid session hooks (`useMuiDataGridPageSession`, `useMuiDataGridScrollSession`) are used in bank accounts. Migration should either move to project table/session primitives or explicitly document no session requirement for that slice.

## Overlay / Menu Risks

- Data reset uses two modal dialogs and must stay modal dialogs.
- Pending invoice tags uses a Menu anchored to `选择现有标签`; must remain a menu/popover-like selection surface from the same trigger.
- Project deletion uses `window.confirm`; do not silently change this to a new custom flow unless the prompt explicitly scopes it and tests the same confirmation behavior.

## Recommended Micro-JIT Queue

1. `P100-phase-6-settings-characterization-tests`
   - Add source-level no-MUI/project primitive contract for `SettingsPage.tsx` and `web/src/components/settings`.
   - Replace MUI class/name expectations in existing tests with user-observable semantics.
   - Add explicit form-factor assertions for left nav tree, regions, tables, menu and dialogs.
   - Expected source-level contract fails against current MUI runtime; behavior tests must pass.
2. `P101-phase-6-settings-shell-navigation`
   - Migrate `SettingsPage`, `SettingsPageContent` layout/header/save feedback and `SettingsTreeNav`.
   - Do not migrate section bodies, data reset dialogs or OA manual import table yet.
3. `P102-phase-6-settings-projects-and-bank-accounts`
   - Migrate project status and bank account DataGrid surfaces to native/project table primitives.
   - Preserve project sync/add/delete/complete actions, bank mapping add/edit/delete and table form factor.
4. `P103-phase-6-settings-access-and-pending-tags`
   - Migrate access account table/role select and pending invoice tag group/menu/chip surfaces.
   - Preserve invalid mapping visibility and save-block behavior.
5. `P104-phase-6-settings-oa-rules-and-data-reset`
   - Migrate OA retention/import settings, OA invoice offset section and data reset cards/progress/dialogs.
   - Preserve high-risk confirmation and OA password review.
6. `P105-phase-6-settings-oa-manual-search-import-table`
   - Migrate OA manual search/import table, filters, row selection, detail expansion, attachment refresh, import actions and pagination.
   - Preserve table accessible name, nested detail table and no global shell status leak.
7. `P106-phase-6-settings-closeout`
   - Remove `settingsDesign.ts` MUI theme bridge if unused, clear settings MUI imports/selectors, run Settings page/table tests and build.
8. `MG-P106-phase-6-settings`
   - Run Settings page/table tests, common/table/HeroUI smoke tests, build, no-MUI grep for `SettingsPage.tsx` and `web/src/components/settings`, diff/status and docs state check.

## P100 Prompt Draft

```text
Prompt ID: P100-phase-6-settings-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/settings` characterization tests only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/SettingsPage.tsx、web/src/components/settings/*、web/src/test/SettingsPage.test.tsx、web/src/test/SettingsOaManualSearchImportTable.test.tsx 和 web/src/features/workbench/types.ts。只修改 Settings 相关测试，不改 runtime code、API client、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。添加 source-level no-MUI/project primitive contract，覆盖 `SettingsPage.tsx` 和 `web/src/components/settings`；更新现有 MUI class/theme 断言为用户可观察语义、ARIA、table/dialog/menu form-factor 断言，不得保护旧 MUI class。测试必须覆盖：left settings nav remains tree, content sections remain regions, Settings page does not show extra legacy title/dialog, read-only save disabled, data reset remains two modal dialogs, pending invoice tag menu remains menu, DataGrid/table surfaces remain table form factor, OA manual search/import keeps table, nested detail table, selection, refresh/import payload and shell-status isolation。运行 `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level no-MUI contract fails against current MUI runtime；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P101 settings shell/navigation prompt。
```

## P100 Execution Notes

- Prompt ID: `P100-phase-6-settings-characterization-tests`
- Status: `verified`
- Runtime implementation changed: no.
- Test implementation changed:
  - Added a source-level no-MUI/project primitive contract covering `SettingsPage.tsx` and all `web/src/components/settings` migration targets.
  - Replaced the legacy `MuiList-root` tree assertion with user-visible tree/region/ARIA assertions.
  - Renamed the OA manual search/import table test from MUI table semantics to native table semantics.
  - Stabilized Settings tests by waiting for the asynchronously rendered settings tree and read-only notice.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail; 12 behavior tests passed, 1 source-level no-MUI/project primitive contract failed against current Settings MUI runtime.
  - `git diff --check`: passed.
- Expected failure:
  - `SettingsPage.test.tsx > targets project primitives for settings navigation, tables, dialogs, menus, and feedback` fails because the current Settings runtime still imports MUI in the page and section components. This is the intended characterization target for P101-P106.

## P101 Prompt Draft

```text
Prompt ID: P101-phase-6-settings-shell-navigation
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` page shell, save feedback, loading/error wrappers and left settings navigation only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/SettingsPage.tsx、web/src/components/settings/SettingsPageContent.tsx、web/src/components/settings/SettingsTreeNav.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移 Settings page shell、loading/error/read-only/save feedback、primary save button、left settings nav/tree 和 content wrapper classes；不得迁移 section bodies、DataGrid/native table bodies、pending tag menu、data reset dialogs、OA manual search/import table 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留用户可见行为：`settings-page` test id, no extra legacy `关联台设置` page title/dialog, left nav remains `设置导航`, tree remains `role="tree"` with `设置分类`, treeitems keep names/selection/aria-controls, content region remains `设置内容`, section regions keep the same accessible names, read-only notice and `保存设置` disabled state stay visible, loading/error/save status messages stay equivalent. 运行 `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|renders as a tree-and-panel page|switches the content panel|keeps workbench-only header actions|keeps read-only settings users"`，预期 selected behavior tests pass and source-level contract still fails for remaining section bodies；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails for remaining Settings MUI runtime；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|ThemeProvider|settingsTheme|settingsButtonSx|settingsSectionSx|<(Alert|Box|Button|CircularProgress|List|ListItem|ListItemButton|ListItemText|Stack|Typography)\\b' web/src/pages/SettingsPage.tsx web/src/components/settings/SettingsPageContent.tsx web/src/components/settings/SettingsTreeNav.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P102 projects/bank accounts prompt。
```

## P101 Execution Notes

- Prompt ID: `P101-phase-6-settings-shell-navigation`
- Status: `verified`
- Runtime implementation changed:
  - `SettingsPage.tsx` no longer imports MUI; page loading/error/success feedback uses the project `StatePanel`.
  - `SettingsTreeNav.tsx` no longer imports MUI; the left nav is a native `aside` + `ul role="tree"` + button `role="treeitem"` structure with preserved names, counts, selection and `aria-controls`.
  - `SettingsPageContent.tsx` no longer imports MUI for shell/header/save/read-only feedback and no longer wraps the page in `ThemeProvider`.
  - Existing data reset dialogs were moved unchanged into `SettingsDataResetDialogs.tsx` so P101 does not migrate the destructive dialog flow prematurely; the file is tracked by the source-level contract for P104.
  - `web/src/app/styles.css` adds Settings shell/nav/header/save/inline status classes using existing `--fp-*` tokens.
- Test implementation changed:
  - `SettingsPage.test.tsx` now includes `SettingsDataResetDialogs.tsx` in the source-level contract and checks the two data-reset dialog labels there.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - Scoped grep for page/content/nav MUI shell residues: passed.
  - `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|renders as a tree-and-panel page|switches the content panel|keeps workbench-only header actions|keeps read-only settings users"`: expected-fail; selected behavior tests passed, source-level contract failed only for remaining section/dialog/table/settingsDesign files.
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail; 12 behavior tests passed, 1 source-level contract failed for remaining Settings MUI runtime.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
- Expected remaining source-level failure files:
  - `SettingsProjectsSection.tsx`
  - `SettingsBankAccountsSection.tsx`
  - `SettingsPendingInvoiceTagsSection.tsx`
  - `SettingsOaRetentionSection.tsx`
  - `SettingsOaInvoiceOffsetSection.tsx`
  - `SettingsAccessAccountsSection.tsx`
  - `SettingsDataResetSection.tsx`
  - `SettingsDataResetDialogs.tsx`
  - `OaManualSearchImportTable.tsx`
  - `settingsDesign.ts`

## P102 Prompt Draft

```text
Prompt ID: P102-phase-6-settings-projects-and-bank-accounts
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` project status and bank account mapping sections only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/SettingsProjectsSection.tsx、web/src/components/settings/SettingsBankAccountsSection.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移项目状态 section 和银行账户映射 section：移除 MUI DataGrid、MUI Buttons/TextFields/Alerts/IconButtons/icons、settingsDataGridSx/settingsButtonSx 在这两个 section 的使用，改为原生/project table/form/button/status classes，并保持表格 form factor。不得迁移 pending invoice tags、access accounts、OA retention/import、OA invoice offset、data reset section/dialogs、OA manual search/import table 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留用户可见行为：`项目状态管理` region、`银行账户映射` region、从 OA 同步项目、新增本地项目、进行中/已完成项目双表格、完成/恢复/删除行操作、银行名称/简称/尾号输入、新增账户映射、行内编辑/删除、disabled/loading/status/error states、表格内容高密度对齐、金额/数字列若出现必须 tabular/right align。运行 selected tests `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|renders as a tree-and-panel page|switches the content panel|keeps read-only settings users"`，预期 behavior tests pass and source-level contract still fails for later Settings sections；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails only for remaining later sections/dialogs/table/settingsDesign；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|settingsDataGridSx|settingsButtonSx|DeleteOutlined|CheckCircleOutlineIcon|UndoIcon|<(Alert|Box|Button|IconButton|TextField|Typography)\\b' web/src/components/settings/SettingsProjectsSection.tsx web/src/components/settings/SettingsBankAccountsSection.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P103 access/pending tags prompt。
```

## P102 Execution Notes

- Prompt ID: `P102-phase-6-settings-projects-and-bank-accounts`
- Status: `verified`
- Runtime implementation changed:
  - `SettingsProjectsSection.tsx` migrated from MUI DataGrid/TextField/Button/IconButton/Alert/icons to native form controls, native tables and lucide row action icons.
  - `SettingsBankAccountsSection.tsx` migrated from MUI DataGrid/session hooks/TextField/Button/IconButton/Alert to a native editable table with row inputs and preserved delete action.
  - `web/src/app/styles.css` adds project/bank section form, native table, row action, source tag and status classes using existing `--fp-*` tokens.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - Scoped grep for projects/bank MUI/DataGrid residues: passed.
  - `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|renders as a tree-and-panel page|switches the content panel|keeps read-only settings users"`: expected-fail; selected behavior tests passed, source-level contract failed only for later Settings section/dialog/table/settingsDesign files.
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail; 12 behavior tests passed, 1 source-level contract failed for remaining Settings MUI runtime.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
- Expected remaining source-level failure files:
  - `SettingsPendingInvoiceTagsSection.tsx`
  - `SettingsOaRetentionSection.tsx`
  - `SettingsOaInvoiceOffsetSection.tsx`
  - `SettingsAccessAccountsSection.tsx`
  - `SettingsDataResetSection.tsx`
  - `SettingsDataResetDialogs.tsx`
  - `OaManualSearchImportTable.tsx`
  - `settingsDesign.ts`

## P103 Prompt Draft

```text
Prompt ID: P103-phase-6-settings-access-and-pending-tags
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` access accounts and pending invoice tag sections only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/SettingsAccessAccountsSection.tsx、web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移访问账户 section 和待找发票筛选 section：移除 MUI DataGrid、Select/Menu/MenuItem/List/ListItem/Button/TextField/Alert/Chip/Tooltip/IconButton/icons、settingsDataGridSx/settingsButtonSx/settingsSectionSx/settingsTokens 在这两个 section 的使用，改为原生/project table、select、menu/popover-like surface、tag、button、status classes。不得迁移 OA retention/import、OA invoice offset、data reset section/dialogs、OA manual search/import table 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留用户可见行为：`访问账户` region、管理员账号提示、新增账户用户名和 `新增账户权限` select、访问账户行内编辑/删除、`待找发票筛选` region、分组列表 `需要开票`/`流水代替发票`/`无需开票`、`选择现有标签` menu/popover trigger、active tags 可选、移除按钮、invalid historical mappings `标签不存在` / `标签已停用` 保持可见且继续阻止保存。运行 selected tests `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|manages pending invoice tag mappings|keeps invalid historical pending invoice mappings|keeps read-only settings users"`，预期 behavior tests pass and source-level contract still fails for later Settings sections；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails only for OA/data reset/manual table/settingsDesign；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|DataGrid|GridColDef|settingsDataGridSx|settingsButtonSx|settingsSectionSx|settingsTokens|DeleteOutlined|<(Alert|Box|Button|Chip|FormControl|IconButton|InputLabel|List|ListItem|ListItemButton|ListItemText|Menu|MenuItem|Select|Stack|TextField|Tooltip|Typography)\\b' web/src/components/settings/SettingsAccessAccountsSection.tsx web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P104 OA rules and data reset prompt。
```

## P103 Execution Notes

- Prompt ID: `P103-phase-6-settings-access-and-pending-tags`
- Status: `verified`
- Runtime implementation changed:
  - `SettingsAccessAccountsSection.tsx` migrated from MUI DataGrid/FormControl/Select/TextField/Button/IconButton/Alert/icons to native table, native select, native inputs and lucide delete action.
  - `SettingsPendingInvoiceTagsSection.tsx` migrated from MUI List/Menu/MenuItem/Chip/Button/TextField/Tooltip/IconButton/icons to native group buttons, native select, trigger-driven `role="menu"`/`role="menuitem"` surface, project tags and row actions.
  - `web/src/app/styles.css` adds access account, pending invoice tag, menu, select and tag classes and removes obsolete access `.MuiAlert` selectors.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - Scoped grep for access/pending MUI residues: passed.
  - `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|manages pending invoice tag mappings|keeps invalid historical pending invoice mappings|keeps read-only settings users"`: expected-fail; selected behavior tests passed, source-level contract failed only for OA/data reset/manual table/settingsDesign files.
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail; 12 behavior tests passed, 1 source-level contract failed for remaining Settings MUI runtime.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - Access scoped CSS MUI grep: passed.
  - `git diff --check`: passed.
- Expected remaining source-level failure files:
  - `SettingsOaRetentionSection.tsx`
  - `SettingsOaInvoiceOffsetSection.tsx`
  - `SettingsDataResetSection.tsx`
  - `SettingsDataResetDialogs.tsx`
  - `OaManualSearchImportTable.tsx`
  - `settingsDesign.ts`

## P104 Prompt Draft

```text
Prompt ID: P104-phase-6-settings-oa-rules-and-data-reset
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` OA retention/import, OA invoice offset, data reset section and data reset dialogs only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/SettingsOaRetentionSection.tsx、web/src/components/settings/SettingsOaInvoiceOffsetSection.tsx、web/src/components/settings/SettingsDataResetSection.tsx、web/src/components/settings/SettingsDataResetDialogs.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移 OA 导入设置、冲账规则、高风险数据重置 section 和两个数据重置 modal dialogs：移除 MUI TextField/FormControl/FormGroup/FormLabel/FormControlLabel/Checkbox/Alert/Card/LinearProgress/Button/Dialog/DialogTitle/DialogContent/DialogActions/CircularProgress/Typography/Stack/Box 以及 settingsSectionSx/settingsTokens 在这些文件的使用，改为原生/project fieldset/checkbox/input/status/progress/dialog classes。不得迁移 OA manual search/import table、settingsDesign.ts closeout 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留用户可见行为：`OA导入设置` region、cutoff date、form type/status checkboxes、`冲账规则` region/applicant textarea、`高风险数据重置` region、三个数据重置 actions、progress text such as `正在清理 app 内部状态。 25%`、modal dialog `确认数据重置`、modal dialog `OA 密码复核`、password field `当前 OA 用户密码`、`继续`/`确认清理`/`取消` labels and disabled/loading states。运行 selected tests `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|keeps data reset behind impact confirmation|keeps read-only settings users"`，预期 behavior tests pass and source-level contract still fails for OA manual table/settingsDesign；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails only for OA manual table/settingsDesign；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|settingsSectionSx|settingsTokens|<(Alert|Box|Button|Card|Checkbox|CircularProgress|Dialog|DialogActions|DialogContent|DialogTitle|FormControl|FormControlLabel|FormGroup|FormLabel|LinearProgress|Stack|TextField|Typography)\\b' web/src/components/settings/SettingsOaRetentionSection.tsx web/src/components/settings/SettingsOaInvoiceOffsetSection.tsx web/src/components/settings/SettingsDataResetSection.tsx web/src/components/settings/SettingsDataResetDialogs.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P105 OA manual search/import table prompt。
```

## P104 Execution Notes

- Prompt ID: `P104-phase-6-settings-oa-rules-and-data-reset`
- Status: `verified`
- Runtime implementation changed:
  - `SettingsOaRetentionSection.tsx` migrated from MUI TextField/FormControl/Checkbox/Alert/layout primitives to native fieldsets, checkboxes, date input and status panel; OA manual import table remains embedded for P105.
  - `SettingsOaInvoiceOffsetSection.tsx` migrated from MUI TextField/Alert/layout primitives to native input and status panel.
  - `SettingsDataResetSection.tsx` migrated from MUI Alert/Card/LinearProgress/Button/layout primitives to native risk/status panels, native cards, native progress and danger buttons.
  - `SettingsDataResetDialogs.tsx` migrated from MUI Dialog/TextField/Button/layout primitives to project `AppDialog` with native password field and action buttons.
  - `web/src/app/styles.css` adds OA import, checkbox, data reset, danger button and dialog content classes.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - Scoped grep for OA/data reset MUI residues: passed.
  - `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives|keeps data reset behind impact confirmation|keeps read-only settings users"`: expected-fail; selected behavior tests passed, source-level contract failed only for `OaManualSearchImportTable.tsx` and `settingsDesign.ts`.
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail; 12 behavior tests passed, 1 source-level contract failed for remaining Settings MUI runtime.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
- Expected remaining source-level failure files:
  - `OaManualSearchImportTable.tsx`
  - `settingsDesign.ts`

## P105 Prompt Draft

```text
Prompt ID: P105-phase-6-settings-oa-manual-search-import-table
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` OA manual search/import table only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/OaManualSearchImportTable.tsx、web/src/components/settings/settingsDesign.ts、web/src/test/SettingsOaManualSearchImportTable.test.tsx、web/src/test/SettingsPage.test.tsx 和 web/src/app/styles.css。只迁移 OA manual search/import table：移除 MUI Table/TableContainer/TableHead/TableBody/TableRow/TableCell/TablePagination/Checkbox/Collapse/Alert/CircularProgress/Button/TextField/FormControl/FormLabel/FormGroup/FormControlLabel/Chip/Tooltip/IconButton/icons、settingsButtonSx/settingsTokens 在该文件的使用，改为原生/project filters、checkboxes、table、pagination、detail expansion、status、buttons and tags。不得迁移 settingsDesign.ts closeout 或 settings API/data logic。不得修改 API client、mock response shape、backend、read model、worker、权限语义、OA 手工导入语义、附件刷新语义、导入 payload 或关联台内部工作区。保留用户可见行为：heading `OA全量搜索导入`、filters `搜索关键字`/`开始日期`/`结束日期`、form type/status filter groups、`搜索`、`导入已选OA项`、`清空选择`、table `OA全量搜索导入结果`、row selection `选择 OA <row_id>`、current page selection `选择当前页可导入OA`、detail toggle `展开 OA <row_id> 明细`、refresh action `刷新 OA <row_id> 附件解析`、pagination、nested detail table、disabled non-importable rows、selected import payload and global shell status isolation。运行 `cd web && npx vitest run SettingsOaManualSearchImportTable.test.tsx`，必须通过；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，预期 behavior tests pass and source-level contract fails only for settingsDesign.ts；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|settingsButtonSx|settingsTokens|<(Alert|Box|Button|Checkbox|Chip|CircularProgress|Collapse|FormControl|FormControlLabel|FormGroup|FormLabel|IconButton|Table|TableBody|TableCell|TableContainer|TableHead|TablePagination|TableRow|TextField|Tooltip|Typography)\\b|ExpandMoreIcon|ExpandLessIcon|RefreshIcon' web/src/components/settings/OaManualSearchImportTable.tsx; then exit 1; else exit 0; fi`；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P106 settings closeout prompt。
```

## P105 Execution Notes

- Prompt ID: `P105-phase-6-settings-oa-manual-search-import-table`
- Status: `verified`
- Runtime implementation changed:
  - `OaManualSearchImportTable.tsx` moved from MUI table, pagination, checkbox, collapse, alert, text field, form control, chip, tooltip, icon button and MUI icons to native/project filters, checkboxes, dense tables, pagination controls, expansion rows, status panels, buttons and tags.
  - The table keeps the accessible name `OA全量搜索导入结果`, current-page selection, per-row selection, detail expansion, attachment refresh, import action and clear-selection action.
  - Nested OA detail rows remain a nested table and use stable dense table/amount/date/tag classes from `web/src/app/styles.css`.
  - `web/src/app/styles.css` adds OA manual import filter, toolbar, pagination, selected-row and table alignment classes using existing `--fp-*` tokens.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - scoped OA manual table no-MUI grep: passed.
  - `cd web && npx vitest run SettingsOaManualSearchImportTable.test.tsx`: passed; 5 tests passed.
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: expected-fail; 13 behavior tests passed, source-level contract failed only for `src/components/settings/settingsDesign.ts`.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
- Commit: `6648341e feat: migrate settings oa manual table`, pushed to `origin/refactor-ui`.
- Expected remaining source-level failure files:
  - `settingsDesign.ts`

## P106 Prompt Draft

```text
Prompt ID: P106-phase-6-settings-closeout
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/settings` closeout for `settingsDesign.ts` only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/components/settings/settingsDesign.ts、web/src/pages/SettingsPage.tsx、web/src/components/settings/*、web/src/test/SettingsPage.test.tsx、web/src/test/SettingsOaManualSearchImportTable.test.tsx 和 web/src/app/styles.css。只处理 Settings closeout：检查 `settingsDesign.ts` 是否仍有 runtime 使用；如果未使用则删除该 MUI theme bridge；如果仍有使用则转换为纯 project token module，必须移除 MUI `createTheme`、`SxProps`、`Theme`、DataGrid theme augmentation、`settingsTheme`、`settingsDataGridSx`、`settingsButtonSx`、`settingsSectionSx` 等 MUI bridge。不得迁移 `MonthPicker`、不得修改 frozen workbench legacy MUI、不得修改 Settings API/client/mock response/backend/read model/worker、权限语义、数据重置语义、OA 手工导入语义或关联台内部工作区。保留 Settings 用户可见行为和 P100-P105 已锁定的 tree, regions, tables, menu, dialogs, OA manual import table form factor。运行 `rg -n "settingsDesign|settingsTokens|settingsTheme|settingsButtonSx|settingsDataGridSx|settingsPageSx|settingsHeaderSx|settingsLayoutSx|settingsNavShellSx|settingsContentSx|settingsSectionSx" web/src` 确认引用边界；运行 full `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`，必须通过；运行 scoped grep `if rg -n '@mui/|Mui[A-Z]|settingsTheme|settingsButtonSx|settingsDataGridSx|settingsSectionSx|<(Alert|Box|Button|Checkbox|Chip|CircularProgress|Collapse|Dialog|FormControl|IconButton|List|Menu|Select|Table|TextField|Tooltip|Typography)\\b' web/src/pages/SettingsPage.tsx web/src/components/settings; then exit 1; else exit 0; fi`，必须通过；运行 `cd web && npm run build`、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 `MG-P106-phase-6-settings` prompt。
```

## P106 Execution Notes

- Prompt ID: `P106-phase-6-settings-closeout`
- Status: `verified`
- Runtime implementation changed:
  - Deleted unused `web/src/components/settings/settingsDesign.ts`; Settings no longer carries a MUI theme/DataGrid/Sx bridge.
  - Removed the deleted file from the Settings source-level no-MUI contract file list in `SettingsPage.test.tsx`.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- MonthPicker/frozen legacy MUI changed: no.
- Verification:
  - Runtime settingsDesign/settingsTokens/settingsTheme/settingsButtonSx/settingsDataGridSx/settingsSectionSx reference grep excluding tests: passed; no runtime references remain.
  - Scoped Settings no-MUI grep for `SettingsPage.tsx` and `web/src/components/settings`: passed.
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: passed; 13 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `git diff --check`: passed.
- Commit: `ad8b3d40 feat: close settings mui bridge`, pushed to `origin/refactor-ui`.

## MG-P106 Prompt Draft

```text
Prompt ID: MG-P106-phase-6-settings
Phase: phase_6_page_batches
Type: cumulative merge gate
Scope: `/settings` P099-P106 migration only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_settings.md、docs/refactor-ui/table_layout_system.md、web/src/pages/SettingsPage.tsx、web/src/components/settings/*、web/src/test/SettingsPage.test.tsx、web/src/test/SettingsOaManualSearchImportTable.test.tsx 和当前 git status/diff。检查当前分支必须是 `refactor-ui`。确认 untracked files、diff scope、测试结果和文档状态；确认 P099-P106 已记录并且 Settings source-level no-MUI contract passed。运行 `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 no-MUI grep：`if rg -n '@mui/|Mui[A-Z]|settingsTheme|settingsButtonSx|settingsDataGridSx|settingsSectionSx|<(Alert|Box|Button|Checkbox|Chip|CircularProgress|Collapse|Dialog|FormControl|IconButton|List|Menu|Select|Table|TextField|Tooltip|Typography)\\b' web/src/pages/SettingsPage.tsx web/src/components/settings; then exit 1; else exit 0; fi`；运行 runtime settingsDesign reference grep：`if rg -n "settingsDesign|settingsTokens|settingsTheme|settingsButtonSx|settingsDataGridSx|settingsPageSx|settingsHeaderSx|settingsLayoutSx|settingsNavShellSx|settingsContentSx|settingsSectionSx" web/src --glob '!**/*.test.tsx' --glob '!**/*.test.ts'; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。确认 scope 只包含 Settings P106 closeout files and docs files：`web/src/components/settings/settingsDesign.ts` deletion, `web/src/test/SettingsPage.test.tsx`, `docs/refactor-ui/modules/phase_6_settings.md`, `docs/refactor-ui/refactor_ui_prompt.md`, `docs/refactor-ui/refactor_ui_state.md`。禁止 `git add .` 和 `git add -A`，只允许精确 git add。MG 通过后提交并 push 到 `origin/refactor-ui`，再更新 state/prompt/module docs 的 MG execution notes 和 Push Log，标记 MG verified，并从 `refactor-ui` 分支生成下一条 Micro-JIT prompt。
```

## MG-P106 Execution Notes

- Prompt ID: `MG-P106-phase-6-settings`
- Status: `verified`
- Scope:
  - Settings P099 discovery through P106 closeout.
  - No backend/API/read model/worker changes.
  - No workbench internals changes.
- Verification:
  - `git status --short --branch`: clean before MG docs update.
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx`: passed; 13 tests passed.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed; 15 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - Scoped Settings no-MUI grep: passed.
  - Runtime settingsDesign/settingsTokens/settingsTheme/settingsButtonSx/settingsDataGridSx/settingsSectionSx reference grep excluding tests: passed.
  - `git diff --check`: passed.
- Result:
  - Settings module is ready to leave Phase 6.
  - Next Micro-JIT prompt moves to Phase 7 MUI containment discovery.
- Commit: `2a30a7b0 docs: verify settings mg and add mui containment discovery`, pushed to `origin/refactor-ui`.

## PV-026 Premium Visual Discovery

- Prompt ID: `PV-026-settings-discovery`
- Status: `verified`
- Scope:
  - `/settings` route, Settings tree navigation, Settings content panel, project status settings, bank account mappings, pending invoice tag mapping, OA import/retention settings, OA invoice offset rules, access accounts, data reset dialogs, OA manual search/import table and related feedback states.
- Runtime implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

### Current Code Facts

- Current non-workbench Settings runtime has already migrated out of MUI:
  - `SettingsPage.tsx` and `web/src/components/settings/*` have no `@mui/*` or Emotion imports.
  - Source-level Settings tests already guard project primitive usage, tree semantics, native table semantics and data reset dialog names.
- Previous `P099-P106` entries in this file are platform migration history. They prove Settings left the MUI platform, but they do not prove this new premium visual pass is complete.
- The Settings page uses:
  - `SettingsPageContent` as the route content container.
  - `SettingsTreeNav` for the left Settings tree.
  - Native/project buttons, inputs, checkboxes, menus, tables, dialogs and tags.
  - `OaManualSearchImportTable` for the largest dense table surface.

### Functional Equivalence Boundaries

PV-027 must preserve all user-visible entrypoints and workflows:

- Existing Settings tree remains a tree navigation, not a tab strip or card list.
- Existing Settings sections remain in the same positions and keep their current labels and affordances.
- Existing setting forms remain forms; field labels, validation, disabled/read-only behavior and save flow must not change.
- Existing tables remain dense tables, including OA manual search import and nested OA detail rows.
- Existing menus remain menus, including pending invoice tag selection.
- Existing data reset flow remains modal dialogs with impact confirmation, OA password review and job progress.
- Existing OA manual import workflow, staged shell status updates, attachment refresh, selection, pagination and import behavior must not change.

### Premium Visual Gaps

- `web/src/app/styles.css` contains two generations of Settings styling:
  - newer tokenized `.settings-*` rules around the route/tree/table/dialog system;
  - older hard-coded Settings project/bank/checkbox/data-reset rules that still use values such as `#102a43`, `#486581`, `#e7edf5`, `#fbfdff`, `#ffffff`, `#f0fff4`, `#fff5f5`, `#9f1d1d` and `#0f4c81`.
- Several controls lack the motion-token treatment used by the premium sample:
  - tree item hover/selected;
  - save/primary/secondary/danger/icon buttons;
  - menu items;
  - table row hover/selected;
  - form input focus;
  - data reset action cards;
  - OA manual import pagination/actions.
- Some Settings regions still feel like migration-era surfaces rather than the bank-details premium direction:
  - project columns and rows;
  - bank mapping rows;
  - data reset cards;
  - pending invoice tag selector;
  - OA manual import filters/metrics/table.
- Layout should stay compact and operational. PV-027 must avoid large card redesigns or dashboard-style metrics.

### Table And List Treatment Required

- Settings table cells must keep `13px` dense rhythm, compact padding and no top-level horizontal overflow.
- Amount/count/date columns must remain right-aligned or tabular where applicable.
- OA manual import table must preserve its wide scroll containment and nested detail table.
- Tags for role/status/source/import status must keep stable table tag height and radius.
- Project names, bank names, project codes, usernames, OA numbers, reasons, tag paths and descriptions must truncate or wrap predictably without changing row height unexpectedly.
- Selected/expanded/active states must not change table/list dimensions.

### Interaction Smoothness Required

- PV-027 should use `docs/refactor-ui/interaction_smoothness.md` tokens:
  - `--motion-fast`;
  - `--ease-out-quart`;
  - compositor-friendly hover/press feedback.
- Do not add route transition animations.
- Do not block Settings tree switching, OA manual table search, pagination, dialog open/close or menu open/close with decorative animations.
- Use reduced-motion-safe CSS only.

### Test And Smoke Implications

- Existing `SettingsPage.test.tsx` covers no-MUI source contract, tree/panel behavior, read-only save disabling, data reset dialogs and pending invoice tag behavior.
- Existing `SettingsOaManualSearchImportTable.test.tsx` covers search, selection, expansion, refresh, import, shell status staging and pagination/filter behavior.
- PV-027 should add a CSS contract to `SettingsPage.test.tsx` for:
  - compact tree/content/table/dialog treatment;
  - motion-token usage;
  - tokenized old hard-coded Settings colors;
  - stable table/tag sizing;
  - OA manual import table scroll containment;
  - no layout-shift hover/selected states.
- Browser smoke should cover `/settings`: tree navigation, save action visibility, one section switch, OA manual import table or data reset dialog, and no top-level horizontal overflow.

### Next Prompt

Next unique prompt: `PV-027-settings-premium-visual`.

## PV-027 Premium Visual Execution

- Prompt ID: `PV-027-settings-premium-visual`
- Status: `verified`
- Runtime implementation changed:
  - `web/src/app/styles.css` adds a Settings-scoped premium override layer for the Settings route, tree navigation, content panel, save/actions, forms, project/bank rows, pending invoice tag selector, menus, data reset cards/dialogs, native tables and OA manual import table.
  - The implementation keeps existing Settings JSX and all behavior intact. No API calls, payloads, save/data-reset/OA manual import workflows, route/session behavior, backend, read model, worker or workbench internals changed.
  - Older hard-coded Settings colors and fixed local transitions are covered by Ledger Calm tokens, `color-mix(...)`, `--motion-fast`, `--motion-base` and `--ease-out-quart` where this slice touched them.
  - Settings tables keep dense row rhythm; amount/count/code fields remain tabular; tree/list/table selected/hover states avoid dimension changes.
- Test implementation changed:
  - `web/src/test/SettingsPage.test.tsx` adds a CSS contract test for compact tree/content/table/dialog treatment, motion-token usage, tokenized Settings colors, amount/count alignment, stable tags, OA manual table containment and no layout-shift rules.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Verification:
  - `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx TableAlignmentStyles.test.ts DesignTokens.test.ts`: passed; 23 tests passed.
  - `cd web && npx tsc -b --pretty false`: passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings.
  - `git diff --check`: passed.
  - Forbidden page-cache/snapshot guard grep: passed.
  - Non-workbench runtime MUI/emotion grep: passed.
  - Browser smoke at `/settings`: passed; verified Settings tree, one section switch, data reset confirmation dialog and no top-level horizontal overflow.
  - Browser table smoke at `/settings`: passed; verified `OA全量搜索导入结果` table and no top-level horizontal overflow.
  - Screenshots:
    - `/tmp/settings-premium-smoke.png`
    - `/tmp/settings-premium-table-smoke.png`
