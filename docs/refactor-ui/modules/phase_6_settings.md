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
