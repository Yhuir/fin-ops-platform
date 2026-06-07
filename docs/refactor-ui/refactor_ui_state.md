# Refactor UI State

本文档是 `refactor-ui` 分支 UI 重构的状态机事实源。每次执行 prompt 或 cumulative MG 后必须更新。

## Current Phase

- Phase: `phase_9_closeout`
- Status: `completed`
- Branch: `refactor-ui`
- Last Updated: `2026-06-07`
- Current Prompt ID: `P115-phase-9-closeout`
- Current MG ID: `MG-P113-phase-7-mui-containment`

## Global Invariants

| Invariant | Status | Evidence |
| --- | --- | --- |
| Backend untouched | yes | 当前 AppHealth discovery 切片只修改重构文档 |
| API contract untouched | yes | 未修改 AppHealth API client contract 或 backend |
| Read model / worker untouched | yes | 未修改 read model、worker 或 queue |
| Reconciliation workbench internals frozen | yes | 当前未改 `ReconciliationWorkbenchPage` 或 `web/src/components/workbench/*` |
| Non-workbench MUI additions | none | InputInvoiceUsage page/table/filter/detail/export/payment-rules/OA-reverse surfaces now have no scoped MUI |
| User-visible actions preserved | documented | `baseline_inventory.md`、`module_inventory.md` 已要求逐页检查 |
| Behavior equivalence | documented | 旧右侧抽屉仍为右侧抽屉，旧弹窗仍为弹窗 |
| HeroUI MCP active | yes | 当前会话已调用 HeroUI MCP quick start、theming、Table/Drawer/Modal docs |
| Module docs on demand | documented | 只有需要跨切片复用的 discovery、旧入口对照、风险或测试策略才新建专项 md |
| Phase prompts generated just-in-time | documented | 每个 phase 可包含多个 prompt；下一条 prompt 由上一条完成情况、验证结果和状态机现场生成 |

## Phase Table

| Phase | Status | Started | Completed | Verification | Notes |
| --- | --- | --- | --- | --- | --- |
| `phase_0_baseline` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | baseline/platform/test/module 文档、文档沉淀规则、完整重构路径和 phase-to-prompt 规则已补齐；MG-P001 已 push |
| `phase_1_docs_and_tokens` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | MG-P004 已 push |
| `phase_2_platform_stack` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | MG-P005 已 push |
| `phase_3_primitives` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | P006-P010 primitives verified，MG-P010 已 push；common 目录已无 MUI import |
| `phase_4_shell` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | P011-P015 verified，MG-P015 已 push；shell 目录已无 MUI import |
| `phase_5_table_system` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | MG-P021 已 push；FinanceTable primitives/session/AppHealth pilot complete |
| `phase_6_page_batches` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | PendingInvoices、InputInvoiceUsage、OaPendingPayments、OutputInvoiceCollections、NoOaBankBatches、BatchAccounting、TurnoverLedger、ETC tickets and Settings MG verified |
| `phase_7_mui_containment` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | MG-P113 verified；non-workbench runtime no-MUI contract passed；frozen workbench legacy isolated |
| `phase_8_full_verification` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | P114 full verification passed: source contract, full Vitest, build, diff check |
| `phase_9_closeout` | `completed` | 2026-06-07 | 2026-06-07 | `passed` | P115 closeout completed; final docs/status/risk register updated |

## Status Values

- `pending`: 未开始。
- `in_progress`: 正在执行。
- `implemented`: prompt 已执行完，等待验证记录。
- `verifying`: 正在验证。
- `verified`: 验证通过，执行者可自行标记。
- `blocked`: 需要用户决策或连续失败。
- `completed`: 阶段完成。
- `deferred`: 明确延期，例如关联台内部工作区。

## Active Checkpoint

- Scope: phase 9 closeout after P114 full verification。
- Files touched in P115:
  - `docs/refactor-ui/README.md`
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`
- Verification run: final non-workbench runtime MUI grep, closeout smoke tests, `cd web && npm run build`, `git diff --check` passed。
- Failures: none.
- Next action: optional PR/review; browser/manual visual QA remains a documented residual risk.

## Prompt Lifecycle

1. `drafted`: 根据状态机生成一条 prompt。
2. `reviewed`: 审查 prompt 的范围、边界、验证、文档更新要求。
3. `approved_for_execution`: prompt 可执行。
4. `implemented`: prompt 已执行。
5. `verified`: 验证通过，状态机和 prompt 文档已更新。
6. `blocked`: prompt 需要用户决策、依赖问题或验证失败。

## Merge Gate Lifecycle

1. `mg_drafted`: 达到可合并边界后生成 MG prompt。
2. `mg_reviewed`: 检查 scope、diff、untracked files、测试和文档状态。
3. `mg_executed`: 精确 staging、必要 commit、push。
4. `mg_verified`: push 完成，远端分支更新。
5. `mg_blocked`: MG 未通过，记录原因。

## Module Queue

按实际执行时的 discovery 结果更新，不预先并行推进。

| Module / Slice | Status | Current Prompt | Notes |
| --- | --- | --- | --- |
| docs bootstrap | `verified` | `P000-docs-bootstrap` | 建立工作流文档 |
| baseline docs gap fill | `verified` | `P001-baseline-doc-gap-fill` | 基线、平台栈、测试策略、模块队列补齐 |
| docs and tokens | `verified` | `P004-phase-1-token-implementation` | Token implementation 和 MG-P004 已完成 |
| platform stack | `verified` | `P005-phase-2-platform-stack-migration` | Build、targeted tests 和 MG-P005 已完成 |
| primitives | `verified` | `P010-phase-3-page-layout-primitives` | P006-P010 verified，MG-P010 已 push，common 目录已无 MUI import |
| app shell | `verified` | `P015-phase-4-status-indicator` | P011-P015 verified，MG-P015 已 push；shell 目录已无 MUI import |
| table system | `verified` | `P021-phase-5-app-health-table-pilot-refactor` | MG-P021 pushed；Phase 5 completed |
| page batches | `verified` | `MG-P106-phase-6-settings` | Phase 6 page modules completed through Settings MG |
| mui containment | `verified` | `MG-P113-phase-7-mui-containment` | Phase 7 completed; MUI limited to frozen workbench internals and test-only legacy provider/helper |
| full verification | `verified` | `P114-phase-8-full-verification` | Source greps, full Vitest, build and diff check passed; residual warnings documented |
| closeout | `verified` | `P115-phase-9-closeout` | Final docs/status/risk register completed |

## Verification Log

| Date | Prompt / MG | Command | Result | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-07 | `P115-phase-9-closeout` | `git status --short --branch` | passed | Clean on `refactor-ui...origin/refactor-ui` before closeout docs update |
| 2026-06-07 | `P115-phase-9-closeout` | final non-workbench runtime MUI grep chain | passed | No non-workbench runtime MUI imports/providers/theme, DataGrid or date-picker residue |
| 2026-06-07 | `P115-phase-9-closeout` | `cd web && npx vitest run MuiContainment.test.ts DesignTokens.test.ts TableLayoutTokens.test.ts TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx SessionGate.test.tsx` | passed | 7 files / 29 tests passed |
| 2026-06-07 | `P115-phase-9-closeout` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P115-phase-9-closeout` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P114-phase-8-full-verification` | final non-workbench runtime MUI grep chain | passed | No non-workbench runtime MUI imports/providers/theme, DataGrid or date-picker residue |
| 2026-06-07 | `P114-phase-8-full-verification` | `cd web && npx vitest run` | passed | 63 files / 613 tests passed after targeted fixes |
| 2026-06-07 | `P114-phase-8-full-verification` | `cd web && npx vitest run WorkbenchSelection.test.tsx -t "workbench settings can manage allowed app accounts\|bank account settings can edit names"` | passed | Verified native Settings inputs and React 19 currentTarget fix |
| 2026-06-07 | `P114-phase-8-full-verification` | `cd web && npx vitest run SettingsPage.test.tsx WorkbenchSelection.test.tsx` | passed | 57 tests passed |
| 2026-06-07 | `P114-phase-8-full-verification` | `cd web && npx vitest run WorkbenchExceptionModal.test.tsx` | passed | 6 tests passed after async preview wait fix |
| 2026-06-07 | `P114-phase-8-full-verification` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx SessionGate.test.tsx` | passed | 24 tests passed after stable keyboard/session assertions |
| 2026-06-07 | `P114-phase-8-full-verification` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P114-phase-8-full-verification` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P114-phase-8-full-verification` | initial full `cd web && npx vitest run` attempts | expected-fail | Exposed stale MUI grid/test timing assertions and React 19 `event.currentTarget` updater bug; fixed before final full pass |
| 2026-06-07 | `MG-P113-phase-7-mui-containment` | `git status --short --branch` | passed | Clean on `refactor-ui...origin/refactor-ui` before MG verification |
| 2026-06-07 | `MG-P113-phase-7-mui-containment` | `cd web && npx vitest run MuiContainment.test.ts MonthPicker.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 23 tests passed |
| 2026-06-07 | `MG-P113-phase-7-mui-containment` | `cd web && npx vitest run WorkbenchExceptionModal.test.tsx WorkbenchColumns.test.tsx WorkbenchPaneFilter.test.ts CandidateGroupGrid.test.tsx WorkbenchColumnLayout.test.tsx` | passed | 64 tests passed |
| 2026-06-07 | `MG-P113-phase-7-mui-containment` | final non-workbench runtime MUI grep excluding frozen workbench, tests and documented styles containment | passed | No non-workbench runtime MUI imports/providers/theme remain |
| 2026-06-07 | `MG-P113-phase-7-mui-containment` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `MG-P113-phase-7-mui-containment` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P113-phase-7-final-no-mui-contract` | `cd web && npx vitest run MuiContainment.test.ts` | passed | 3 source contract tests passed |
| 2026-06-07 | `P113-phase-7-final-no-mui-contract` | `cd web && npx vitest run WorkbenchExceptionModal.test.tsx WorkbenchColumns.test.tsx WorkbenchPaneFilter.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 50 tests passed |
| 2026-06-07 | `P113-phase-7-final-no-mui-contract` | corrected final non-workbench runtime MUI grep excluding workbench, tests and styles.css | passed | `styles.css` frozen workbench selectors are covered by `MuiContainment.test.ts` |
| 2026-06-07 | `P113-phase-7-final-no-mui-contract` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P113-phase-7-final-no-mui-contract` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P112-phase-7-global-css-containment` | `if rg -n "MuiDataGrid\|DataGrid" web/src/app/styles.css; then exit 1; else exit 0; fi` | passed | Non-workbench DataGrid CSS selectors removed |
| 2026-06-07 | `P112-phase-7-global-css-containment` | `rg -n "Mui\|@mui\|Frozen workbench legacy containment" web/src/app/styles.css` | passed | Remaining CSS MUI hits are documented frozen workbench legacy selectors |
| 2026-06-07 | `P112-phase-7-global-css-containment` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx WorkbenchColumns.test.tsx WorkbenchPaneFilter.test.ts` | passed | 46 tests passed |
| 2026-06-07 | `P112-phase-7-global-css-containment` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P112-phase-7-global-css-containment` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P111-phase-7-test-provider-containment` | `cd web && npx vitest run CommonMuiComponents.test.tsx MonthPicker.test.tsx SettingsOaManualSearchImportTable.test.tsx WorkbenchExceptionModal.test.tsx` | passed | 27 tests passed |
| 2026-06-07 | `P111-phase-7-test-provider-containment` | `cd web && npx vitest run BatchAccountingPage.test.tsx NoOaBankBatchPage.test.tsx TurnoverLedgerPage.test.tsx BankDetailsPage.test.tsx CostStatisticsPage.test.tsx AutoTagRulesDrawer.test.tsx` | passed | 112 non-workbench page/drawer regression tests passed |
| 2026-06-07 | `P111-phase-7-test-provider-containment` | `cd web && npx vitest run WorkbenchColumns.test.tsx CandidateGroupGrid.test.tsx WorkbenchPaneFilter.test.ts WorkbenchColumnLayout.test.tsx` | passed | 58 frozen workbench helper regression tests passed |
| 2026-06-07 | `P111-phase-7-test-provider-containment` | `rg -n "import MuiProviders\|<MuiProviders\|MuiProviders" web/src/test` | passed | Only `workbenchRenderHelpers.tsx` and `WorkbenchExceptionModal.test.tsx` remain as explicit workbench legacy hits |
| 2026-06-07 | `P111-phase-7-test-provider-containment` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P111-phase-7-test-provider-containment` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P110-phase-7-datagrid-session-cleanup` | reference grep before deletion | passed | No runtime page references to the obsolete MUI DataGrid session hook |
| 2026-06-07 | `P110-phase-7-datagrid-session-cleanup` | `cd web && npx vitest run useFinanceTableSession.test.tsx TableAlignmentStyles.test.ts` | passed | 7 tests passed |
| 2026-06-07 | `P110-phase-7-datagrid-session-cleanup` | runtime MUI DataGrid session grep excluding tests | passed | No runtime `useMuiDataGridPageSession` / `@mui/x-data-grid` references remain |
| 2026-06-07 | `P110-phase-7-datagrid-session-cleanup` | full reference grep | passed | Only a negative test string remains in `BankDetailsPage.test.tsx` |
| 2026-06-07 | `P110-phase-7-datagrid-session-cleanup` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P110-phase-7-datagrid-session-cleanup` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P109-phase-7-month-picker-and-date-compat` | `cd web && npx vitest run MonthPicker.test.tsx` | passed | 5 tests passed |
| 2026-06-07 | `P109-phase-7-month-picker-and-date-compat` | `cd web && npx vitest run App.test.tsx CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 26 tests passed |
| 2026-06-07 | `P109-phase-7-month-picker-and-date-compat` | scoped MonthPicker/date compat no-MUI grep | passed | `MuiDatePickerCompatProvider.tsx` deleted；`MonthPicker.tsx` and `App.tsx` have no date compat residue |
| 2026-06-07 | `P109-phase-7-month-picker-and-date-compat` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P109-phase-7-month-picker-and-date-compat` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P108-phase-7-month-picker-characterization-tests` | `cd web && npx vitest run MonthPicker.test.tsx` | expected-fail | 4 behavior tests passed；source-level contract failed for `MonthPicker.tsx` and `MuiDatePickerCompatProvider.tsx` |
| 2026-06-07 | `P108-phase-7-month-picker-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P107-phase-7-mui-containment-discovery` | `test -f docs/refactor-ui/modules/phase_7_mui_containment.md` | passed | Phase 7 containment doc exists |
| 2026-06-07 | `P107-phase-7-mui-containment-discovery` | `rg -n "P107-phase-7-mui-containment-discovery\|Current MUI Inventory\|Allowed Workbench Legacy\|Non-workbench Runtime Targets\|Recommended Micro-JIT Queue\|P108-phase-7" docs/refactor-ui/modules/phase_7_mui_containment.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | Containment inventory and next prompt recorded |
| 2026-06-07 | `P107-phase-7-mui-containment-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P106-phase-6-settings` | `git status --short --branch` | passed | Clean before MG docs update |
| 2026-06-07 | `MG-P106-phase-6-settings` | `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx` | passed | 13 tests passed |
| 2026-06-07 | `MG-P106-phase-6-settings` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `MG-P106-phase-6-settings` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `MG-P106-phase-6-settings` | scoped Settings no-MUI grep | passed | `SettingsPage.tsx` and `web/src/components/settings` have no scoped MUI residue |
| 2026-06-07 | `MG-P106-phase-6-settings` | runtime settingsDesign reference grep excluding tests | passed | No runtime Settings MUI bridge references remain |
| 2026-06-07 | `MG-P106-phase-6-settings` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P106-phase-6-settings-closeout` | runtime settingsDesign reference grep excluding tests | passed | No runtime `settingsDesign` / `settingsTokens` / settings MUI bridge references remain |
| 2026-06-07 | `P106-phase-6-settings-closeout` | scoped Settings no-MUI grep | passed | `SettingsPage.tsx` and `web/src/components/settings` have no scoped MUI residue |
| 2026-06-07 | `P106-phase-6-settings-closeout` | `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx` | passed | 13 tests passed |
| 2026-06-07 | `P106-phase-6-settings-closeout` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P106-phase-6-settings-closeout` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P105-phase-6-settings-oa-manual-search-import-table` | scoped OA manual table no-MUI grep | passed | `OaManualSearchImportTable.tsx` has no scoped MUI residue |
| 2026-06-07 | `P105-phase-6-settings-oa-manual-search-import-table` | `cd web && npx vitest run SettingsOaManualSearchImportTable.test.tsx` | passed | 5 tests passed |
| 2026-06-07 | `P105-phase-6-settings-oa-manual-search-import-table` | `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx` | expected-fail | 13 behavior tests passed；source-level contract failed only for `src/components/settings/settingsDesign.ts` |
| 2026-06-07 | `P105-phase-6-settings-oa-manual-search-import-table` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P105-phase-6-settings-oa-manual-search-import-table` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P104-phase-6-settings-oa-rules-and-data-reset` | scoped OA/data reset no-MUI grep | passed | OA retention, OA invoice offset, data reset section and dialogs have no scoped MUI residue |
| 2026-06-07 | `P104-phase-6-settings-oa-rules-and-data-reset` | `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives\|keeps data reset behind impact confirmation\|keeps read-only settings users"` | expected-fail | Selected behavior tests passed；source-level contract failed only for `OaManualSearchImportTable.tsx` and `settingsDesign.ts` |
| 2026-06-07 | `P104-phase-6-settings-oa-rules-and-data-reset` | `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx` | expected-fail | 12 behavior tests passed；1 source-level contract failed for remaining Settings MUI runtime |
| 2026-06-07 | `P104-phase-6-settings-oa-rules-and-data-reset` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P104-phase-6-settings-oa-rules-and-data-reset` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P103-phase-6-settings-access-and-pending-tags` | scoped access/pending no-MUI grep | passed | `SettingsAccessAccountsSection.tsx` and `SettingsPendingInvoiceTagsSection.tsx` have no scoped MUI residue |
| 2026-06-07 | `P103-phase-6-settings-access-and-pending-tags` | `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives\|manages pending invoice tag mappings\|keeps invalid historical pending invoice mappings\|keeps read-only settings users"` | expected-fail | Selected behavior tests passed；source-level contract failed only for OA/data reset/manual table/settingsDesign files |
| 2026-06-07 | `P103-phase-6-settings-access-and-pending-tags` | `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx` | expected-fail | 12 behavior tests passed；1 source-level contract failed for remaining Settings MUI runtime |
| 2026-06-07 | `P103-phase-6-settings-access-and-pending-tags` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P103-phase-6-settings-access-and-pending-tags` | access scoped CSS MUI grep | passed | Obsolete access `.MuiAlert` selectors removed |
| 2026-06-07 | `P103-phase-6-settings-access-and-pending-tags` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P102-phase-6-settings-projects-and-bank-accounts` | scoped projects/bank no-MUI/DataGrid grep | passed | `SettingsProjectsSection.tsx` and `SettingsBankAccountsSection.tsx` have no scoped MUI/DataGrid residue |
| 2026-06-07 | `P102-phase-6-settings-projects-and-bank-accounts` | `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives\|renders as a tree-and-panel page\|switches the content panel\|keeps read-only settings users"` | expected-fail | Selected behavior tests passed；source-level contract failed only for later Settings section/dialog/table/settingsDesign files |
| 2026-06-07 | `P102-phase-6-settings-projects-and-bank-accounts` | `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx` | expected-fail | 12 behavior tests passed；1 source-level contract failed for remaining Settings MUI runtime |
| 2026-06-07 | `P102-phase-6-settings-projects-and-bank-accounts` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P102-phase-6-settings-projects-and-bank-accounts` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P101-phase-6-settings-shell-navigation` | scoped page/content/nav no-MUI grep | passed | `SettingsPage.tsx`, `SettingsPageContent.tsx` and `SettingsTreeNav.tsx` have no scoped MUI shell/navigation residue |
| 2026-06-07 | `P101-phase-6-settings-shell-navigation` | `cd web && npx vitest run SettingsPage.test.tsx -t "targets project primitives\|renders as a tree-and-panel page\|switches the content panel\|keeps workbench-only header actions\|keeps read-only settings users"` | expected-fail | Selected behavior tests passed；source-level contract failed only for remaining Settings section/dialog/table/settingsDesign files |
| 2026-06-07 | `P101-phase-6-settings-shell-navigation` | `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx` | expected-fail | 12 behavior tests passed；1 source-level contract failed for remaining Settings MUI runtime |
| 2026-06-07 | `P101-phase-6-settings-shell-navigation` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P101-phase-6-settings-shell-navigation` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P100-phase-6-settings-characterization-tests` | `cd web && npx vitest run SettingsPage.test.tsx SettingsOaManualSearchImportTable.test.tsx` | expected-fail | 12 behavior tests passed；1 source-level no-MUI/project primitive contract failed as expected against current Settings MUI runtime |
| 2026-06-07 | `P100-phase-6-settings-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P089-phase-6-turnover-ledger-tag-and-closure-drawers` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives\|opens tag selection drawer\|confirms a manual zero-difference\|confirms closure when cash direction crosses\|blocks cross-group selection"` | expected-fail | Selected behavior tests passed; source-level contract failed as expected for remaining ExtraDrawer/ExportDialog targets |
| 2026-06-07 | `P089-phase-6-turnover-ledger-tag-and-closure-drawers` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx` | expected-fail | 11 behavior tests passed; 1 source-level contract failed |
| 2026-06-07 | `P089-phase-6-turnover-ledger-tag-and-closure-drawers` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P089-phase-6-turnover-ledger-tag-and-closure-drawers` | `if rg -n '<Drawer\|<IconButton\|CloseIcon\|FormControlLabel\|<Checkbox\|<Button\|<Box\|<Stack\|<Typography\|<Paper\|<Divider' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi` | passed | Page-owned drawer MUI/layout residues cleared; page Alert/Snackbar intentionally reserved for feedback closeout |
| 2026-06-07 | `P089-phase-6-turnover-ledger-tag-and-closure-drawers` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P090-phase-6-turnover-ledger-extra-drawer` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives\|opens the extra drawer\|shows a business error\|disables turnover write actions"` | expected-fail | Selected behavior tests passed; source-level contract failed as expected for remaining ExportDialog/page feedback targets |
| 2026-06-07 | `P090-phase-6-turnover-ledger-extra-drawer` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx` | expected-fail | 11 behavior tests passed; 1 source-level contract failed |
| 2026-06-07 | `P090-phase-6-turnover-ledger-extra-drawer` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P090-phase-6-turnover-ledger-extra-drawer` | `if rg -n '@mui/\|Mui[A-Z]\|<Drawer\|<IconButton\|CloseIcon\|<Button\|<Chip\|<TextField\|<MenuItem\|<Alert\|<Box\|<Stack\|<Typography\|<Divider' web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx; then exit 1; else exit 0; fi` | passed | Extra drawer MUI residues cleared |
| 2026-06-07 | `P090-phase-6-turnover-ledger-extra-drawer` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P091-phase-6-turnover-ledger-export-dialog-feedback-closeout` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives\|reloads on category updates and downloads a previewed export\|opens the extra drawer\|shows a business error\|disables turnover write actions"` | passed | Selected behavior tests and source-level contract passed |
| 2026-06-07 | `P091-phase-6-turnover-ledger-export-dialog-feedback-closeout` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx` | passed | 12 tests passed |
| 2026-06-07 | `P091-phase-6-turnover-ledger-export-dialog-feedback-closeout` | `if rg -n '@mui/\|Mui[A-Z]\|DialogTitle\|DialogContent\|DialogActions\|Snackbar\|<Alert\\b\|<Dialog\\b\|<Button\|<TextField\|<MenuItem\|<Table\|TableHead\|TableBody\|TableRow\|TableCell\|TableContainer\|<Stack\|<Typography' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx; then exit 1; else exit 0; fi` | passed | Export dialog and page feedback MUI residues cleared |
| 2026-06-07 | `P091-phase-6-turnover-ledger-export-dialog-feedback-closeout` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P091-phase-6-turnover-ledger-export-dialog-feedback-closeout` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P091-phase-6-turnover-ledger` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx TurnoverLedgerApi.test.ts` | passed | 21 tests passed |
| 2026-06-07 | `MG-P091-phase-6-turnover-ledger` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `MG-P091-phase-6-turnover-ledger` | `if rg -n '@mui/\|Mui[A-Z]\|DownloadOutlinedIcon\|KeyboardArrowDownIcon\|KeyboardArrowRightIcon\|CloseIcon\|DialogTitle\|DialogContent\|DialogActions\|Snackbar\|<Alert\\b\|<Dialog\\b\|<Drawer\\b\|<Button\\b\|<TextField\\b\|<MenuItem\\b\|<Table\\b\|<TableHead\\b\|<TableBody\\b\|<TableRow\\b\|<TableCell\\b\|<TableContainer\\b\|<Checkbox\\b\|<Chip\\b\|<IconButton\\b\|<Stack\\b\|<Typography\\b\|<Paper\\b\|<Divider\\b\|<FormControlLabel\\b\|<Tabs\\b\|<Tab\\b' web/src/pages/TurnoverLedgerPage.tsx web/src/components/turnoverLedger; then exit 1; else exit 0; fi` | passed | Corrected JSX-boundary grep avoids project-name false positives |
| 2026-06-07 | `MG-P091-phase-6-turnover-ledger` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `MG-P091-phase-6-turnover-ledger` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P091-phase-6-turnover-ledger` | `git status --short --branch` | passed | Clean before MG docs update |
| 2026-06-07 | `P092-phase-6-etc-tickets-discovery` | `test -f docs/refactor-ui/modules/phase_6_etc_tickets.md` | passed | ETC tickets module discovery doc exists |
| 2026-06-07 | `P092-phase-6-etc-tickets-discovery` | `rg -n "P092-phase-6-etc-tickets-discovery\|Current MUI Inventory\|User-visible Entrypoints\|Recommended Micro-JIT Queue\|P093-phase-6-etc-tickets-characterization-tests" docs/refactor-ui/modules/phase_6_etc_tickets.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | Discovery terms and next prompt recorded |
| 2026-06-07 | `P092-phase-6-etc-tickets-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P092-phase-6-etc-tickets-discovery` | `git status --short --branch` | passed | Only P092 docs changed |
| 2026-06-07 | `P093-phase-6-etc-tickets-characterization-tests` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx` | expected-fail | 41 behavior tests passed; 1 source-level no-MUI/project primitive contract failed against current MUI runtime |
| 2026-06-07 | `P093-phase-6-etc-tickets-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P093-phase-6-etc-tickets-characterization-tests` | `git status --short --branch` | passed | Only P093 test file changed before docs |
| 2026-06-07 | `P094-phase-6-etc-tickets-shell-filters-lists` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives\|unsubmitted mode shows batch list\|submitted mode hides submit action\|creates OA draft through the selected business batch"` | expected-fail | Selected behavior tests passed; source-level contract failed as expected |
| 2026-06-07 | `P094-phase-6-etc-tickets-shell-filters-lists` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx` | expected-fail | 41 behavior tests passed; 1 source-level no-MUI/project primitive contract failed against remaining ETC MUI runtime |
| 2026-06-07 | `P094-phase-6-etc-tickets-shell-filters-lists` | `if rg -n 'AddOutlinedIcon\|ArrowForwardOutlinedIcon\|DeleteOutlineOutlinedIcon\|OpenInNewOutlinedIcon\|RefreshOutlinedIcon\|UndoOutlinedIcon\|UploadFileOutlinedIcon\|<ToggleButton\\b\|<ToggleButtonGroup\\b\|<List\\b\|<ListItem\\b\|<ListItemButton\\b\|<ListItemText\\b\|<Paper\\b\|<TextField[^\\n]*(label="月份"\|label="车牌"\|label="信用卡任务")' web/src/pages/EtcTicketManagementPage.tsx; then exit 1; else exit 0; fi` | passed | P094 shell/filter/list scoped MUI residues cleared |
| 2026-06-07 | `P094-phase-6-etc-tickets-shell-filters-lists` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P094-phase-6-etc-tickets-shell-filters-lists` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P094-phase-6-etc-tickets-shell-filters-lists` | `git status --short --branch` | passed | Only P094 page/style files changed before docs |
| 2026-06-07 | `P095-phase-6-etc-tickets-upload-and-source-panels` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives\|shows the reconciliation workspace with upload blocks\|uploads ticket-root TXT files\|uploads ticket-root TXT files by dropping\|shows source file context\|removes legacy ticket-root mode controls\|disables ticket-root TXT upload"` | expected-fail | Selected upload/source behavior tests passed; source-level contract failed as expected |
| 2026-06-07 | `P095-phase-6-etc-tickets-upload-and-source-panels` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx` | expected-fail | 41 behavior tests passed; 1 source-level no-MUI/project primitive contract failed against remaining ETC MUI runtime |
| 2026-06-07 | `P095-phase-6-etc-tickets-upload-and-source-panels` | `if rg -n 'etc-upload-drop-box[^\\n]*MuiButton\|\\.etc-upload-drop-box\\.Mui\|\\.etc-upload-drop-box[^\\n]*Mui-disabled\|<Stack[^\\n]*etc-upload\|<Typography[^\\n]*etc-upload\|etc-source-file-title[^\\n]*<Chip\|etc-source-issue[^\\n]*<Chip\|etc-source-file-row[^\\n]*<Tooltip\|etc-source-file-row[^\\n]*<IconButton' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi` | passed | Narrowed to upload/source classes because draft grep hit future slices and frozen workbench CSS |
| 2026-06-07 | `P095-phase-6-etc-tickets-upload-and-source-panels` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P095-phase-6-etc-tickets-upload-and-source-panels` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P095-phase-6-etc-tickets-upload-and-source-panels` | `git status --short --branch` | passed | Only P095 page/style files changed before docs |
| 2026-06-07 | `P096-phase-6-etc-tickets-reconciliation-table` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives\|renders paired reconciliation table\|keeps long reconciliation descriptions\|selects reconciliation rows locally\|updates confirmation metrics\|submits the checked card item ids\|manual reconciliation accepts"` | expected-fail | Selected reconciliation/manual behavior tests passed; source-level contract failed as expected |
| 2026-06-07 | `P096-phase-6-etc-tickets-reconciliation-table` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx` | expected-fail | 41 behavior tests passed; 1 source-level no-MUI/project primitive contract failed against remaining ETC MUI runtime |
| 2026-06-07 | `P096-phase-6-etc-tickets-reconciliation-table` | `if rg -n 'etc-reconciliation-description-toggle\\.MuiButton-root\|etc-reconciliation-table .*Mui\|etc-reconciliation-[^\\n]*Mui\|<TextField[^\\n]*(选择票根\|处理说明)\|<Table(Container\|Head\|Body\|Row\|Cell)?\\b[^\\n]*etc-reconciliation\|<Checkbox\\b\|<Tooltip[^\\n]*(重新计算匹配\|上传补充凭证)\|<IconButton[^\\n]*(aria-label=\\{label\\}\|上传补充)\|etc-reconciliation-chip-line[^\\n]*<Chip' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi` | passed | Narrowed to reconciliation/manual classes because draft grep hit P097 future detail/invoice surfaces |
| 2026-06-07 | `P096-phase-6-etc-tickets-reconciliation-table` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P096-phase-6-etc-tickets-reconciliation-table` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P096-phase-6-etc-tickets-reconciliation-table` | `git status --short --branch` | passed | Only P096 page/style files changed before docs |
| 2026-06-07 | `P097-phase-6-etc-tickets-detail-and-invoice-tables` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx -t "targets project primitives\|renders batch invoice details with a native table\|shows imported task invoices\|submitted mode hides submit action\|creates OA draft from the selected imported reconciliation task batch"` | expected-fail | Selected detail/invoice behavior tests passed; source-level contract failed as expected |
| 2026-06-07 | `P097-phase-6-etc-tickets-detail-and-invoice-tables` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx` | expected-fail | 41 behavior tests passed; 1 source-level no-MUI/project primitive contract failed against remaining ETC MUI runtime |
| 2026-06-07 | `P097-phase-6-etc-tickets-detail-and-invoice-tables` | `if rg -n '<Table(Container\|Head\|Body\|Row\|Cell)?\\b\|<Chip\\b\|<Button[^\\n]*(移除发票\|撤销草稿\|未提交OA)\|etc-invoice-[^\\n]*Mui\|etc-import-attempt-row .*Mui\|etc-plate-summary[^\\n]*Mui' web/src/pages/EtcTicketManagementPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi` | passed | Detail/invoice table MUI residues cleared |
| 2026-06-07 | `P097-phase-6-etc-tickets-detail-and-invoice-tables` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P097-phase-6-etc-tickets-detail-and-invoice-tables` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P097-phase-6-etc-tickets-detail-and-invoice-tables` | `git status --short --branch` | passed | Only P097 page/style files changed before docs |
| 2026-06-07 | `P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout` | `if rg -n '@mui/\|Mui[A-Z]\|<(Alert\|Box\|Button\|Checkbox\|Chip\|Collapse\|Divider\|IconButton\|List\|ListItem\|ListItemButton\|ListItemText\|Paper\|Stack\|Table\|TableBody\|TableCell\|TableContainer\|TableHead\|TableRow\|TextField\|ToggleButton\|ToggleButtonGroup\|Tooltip\|Typography)\\b\|AddOutlinedIcon\|ArrowForwardOutlinedIcon\|DeleteOutlineOutlinedIcon\|ExpandLessOutlinedIcon\|ExpandMoreOutlinedIcon\|OpenInNewOutlinedIcon\|RefreshOutlinedIcon\|ReportProblemOutlinedIcon\|UndoOutlinedIcon\|UploadFileOutlinedIcon' web/src/pages/EtcTicketManagementPage.tsx; then exit 1; else exit 0; fi` | passed | Page source no-MUI contract passed |
| 2026-06-07 | `P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout` | `if rg -n 'etc-[^\\n]*Mui\|Mui[^\\n]*etc-' web/src/app/styles.css; then exit 1; else exit 0; fi` | passed | ETC-scoped CSS MUI residues cleared; frozen/global non-ETC MUI selectors intentionally not in scope |
| 2026-06-07 | `P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx` | passed | 42 tests passed |
| 2026-06-07 | `P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout` | `cd web && npx vitest run EtcApi.test.ts EtcOaNavigation.test.ts` | passed | 17 tests passed |
| 2026-06-07 | `P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout` | `git status --short --branch` | passed | Only P098 page/style files changed before docs |
| 2026-06-07 | `MG-P098-phase-6-etc-tickets` | `git status --short --branch` | passed | Clean on `refactor-ui...origin/refactor-ui` before MG verification |
| 2026-06-07 | `MG-P098-phase-6-etc-tickets` | `cd web && npx vitest run EtcTicketManagementPage.test.tsx EtcApi.test.ts EtcOaNavigation.test.ts` | passed | 59 tests passed |
| 2026-06-07 | `MG-P098-phase-6-etc-tickets` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `MG-P098-phase-6-etc-tickets` | `if rg -n '@mui/\|Mui[A-Z]\|<(Alert\|Box\|Button\|Checkbox\|Chip\|Collapse\|Divider\|IconButton\|List\|ListItem\|ListItemButton\|ListItemText\|Paper\|Stack\|Table\|TableBody\|TableCell\|TableContainer\|TableHead\|TableRow\|TextField\|ToggleButton\|ToggleButtonGroup\|Tooltip\|Typography)\\b\|AddOutlinedIcon\|ArrowForwardOutlinedIcon\|DeleteOutlineOutlinedIcon\|ExpandLessOutlinedIcon\|ExpandMoreOutlinedIcon\|OpenInNewOutlinedIcon\|RefreshOutlinedIcon\|ReportProblemOutlinedIcon\|UndoOutlinedIcon\|UploadFileOutlinedIcon' web/src/pages/EtcTicketManagementPage.tsx; then exit 1; else exit 0; fi && if rg -n 'etc-[^\\n]*Mui\|Mui[^\\n]*etc-' web/src/app/styles.css; then exit 1; else exit 0; fi` | passed | ETC page source and ETC-scoped CSS MUI residues cleared |
| 2026-06-07 | `MG-P098-phase-6-etc-tickets` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `MG-P098-phase-6-etc-tickets` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P098-phase-6-etc-tickets` | `git status --short --branch` | passed | Clean before MG docs update |
| 2026-06-07 | `P099-phase-6-settings-discovery` | `test -f docs/refactor-ui/modules/phase_6_settings.md` | passed | Settings module discovery doc exists |
| 2026-06-07 | `P099-phase-6-settings-discovery` | `rg -n "P099-phase-6-settings-discovery\|Current MUI Inventory\|User-visible Entrypoints\|Recommended Micro-JIT Queue\|P100-phase-6-settings-characterization-tests" docs/refactor-ui/modules/phase_6_settings.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | Discovery terms and next prompt recorded |
| 2026-06-07 | `P099-phase-6-settings-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P099-phase-6-settings-discovery` | `git status --short --branch` | passed | Only P099 docs changed |
| 2026-06-07 | `P088-phase-6-turnover-ledger-grouped-table` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives\|renders grouped\|expands Jia Xiaohua\|confirms a manual zero-difference\|blocks cross-group selection\|shows bank-detail tags"` | expected-fail | Selected behavior tests passed; source-level contract failed as expected for remaining drawer/dialog/feedback targets |
| 2026-06-07 | `P088-phase-6-turnover-ledger-grouped-table` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx` | expected-fail | 11 behavior tests passed; 1 source-level contract failed |
| 2026-06-07 | `P088-phase-6-turnover-ledger-grouped-table` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P088-phase-6-turnover-ledger-grouped-table` | `if rg -n '@mui/\|Mui[A-Z]\|KeyboardArrowDownIcon\|KeyboardArrowRightIcon\|<Table\|TableHead\|TableBody\|TableRow\|TableCell\|TableContainer\|<Checkbox\|<Chip\|<IconButton\|<Button\|<Paper\|<Stack\|<Typography' web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx; then exit 1; else exit 0; fi` | passed | Grouped table MUI residues cleared |
| 2026-06-07 | `P088-phase-6-turnover-ledger-grouped-table` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P087-phase-6-turnover-ledger-page-shell-tabs-summary` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx -t "targets project primitives\|renders grouped\|opens tag selection drawer\|reloads on category updates"` | expected-fail | Selected behavior tests passed; source-level contract failed as expected for remaining table/drawer/dialog/feedback targets |
| 2026-06-07 | `P087-phase-6-turnover-ledger-page-shell-tabs-summary` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx` | expected-fail | 11 behavior tests passed; 1 source-level contract failed |
| 2026-06-07 | `P087-phase-6-turnover-ledger-page-shell-tabs-summary` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P087-phase-6-turnover-ledger-page-shell-tabs-summary` | `if rg -n 'DownloadOutlinedIcon\|<Tabs\|<Tab\|label="全部"\|label="个人往来"\|label="公司往来"\|label="银行往来"\|label="业务往来"' web/src/pages/TurnoverLedgerPage.tsx; then exit 1; else exit 0; fi` | passed | Page shell/tabs targeted residues cleared; `<Box` intentionally excluded because drawer internals are later slices |
| 2026-06-07 | `P087-phase-6-turnover-ledger-page-shell-tabs-summary` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P086-phase-6-turnover-ledger-characterization-tests` | `cd web && npx vitest run TurnoverLedgerPage.test.tsx` | expected-fail | 11 behavior tests passed; 1 source-level no-MUI/project primitive contract failed against current MUI runtime |
| 2026-06-07 | `P086-phase-6-turnover-ledger-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P086-phase-6-turnover-ledger-characterization-tests` | `git status --short --branch` | passed | Only P086 test file changed before docs |
| 2026-06-07 | `P085-phase-6-turnover-ledger-discovery` | `test -f docs/refactor-ui/modules/phase_6_turnover_ledger.md` | passed | TurnoverLedger module discovery doc exists |
| 2026-06-07 | `P085-phase-6-turnover-ledger-discovery` | `rg -n "P085-phase-6-turnover-ledger-discovery\|Current MUI Inventory\|User-visible Entrypoints\|Recommended Micro-JIT Queue\|P086-phase-6-turnover-ledger-characterization-tests" docs/refactor-ui/modules/phase_6_turnover_ledger.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | Discovery terms and next prompt recorded |
| 2026-06-07 | `P085-phase-6-turnover-ledger-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P085-phase-6-turnover-ledger-discovery` | `git status --short --branch` | passed | Only P085/MG docs changed |
| 2026-06-07 | `MG-P084-phase-6-batch-accounting` | `git status --short --branch` | passed | Clean worktree on `refactor-ui...origin/refactor-ui` before MG docs |
| 2026-06-07 | `MG-P084-phase-6-batch-accounting` | `cd web && npx vitest run BatchAccountingPage.test.tsx` | passed | 13 tests passed |
| 2026-06-07 | `MG-P084-phase-6-batch-accounting` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `MG-P084-phase-6-batch-accounting` | `if rg -n '@mui/\|Mui[A-Z]\|DialogTitle\|DialogContent\|DialogActions\|Snackbar\|<Alert\\b\|TextField\|<Button\|<Dialog\|<Stack\|<Paper\|<Box\|<Divider' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi` | passed | BatchAccounting final page MUI residues remain cleared |
| 2026-06-07 | `MG-P084-phase-6-batch-accounting` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P084-phase-6-batch-accounting-overlays-feedback` | `cd web && npx vitest run BatchAccountingPage.test.tsx` | passed | 13 tests passed; source-level no-MUI/project primitive contract passed |
| 2026-06-07 | `P084-phase-6-batch-accounting-overlays-feedback` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P084-phase-6-batch-accounting-overlays-feedback` | `if rg -n '@mui/\|Mui[A-Z]\|DialogTitle\|DialogContent\|DialogActions\|Snackbar\|<Alert\\b\|TextField\|<Button\|<Dialog\|<Stack\|<Paper\|<Box\|<Divider' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi` | passed | Final page MUI residues cleared |
| 2026-06-07 | `P084-phase-6-batch-accounting-overlays-feedback` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P083-phase-6-batch-accounting-oa-table` | `cd web && npx vitest run BatchAccountingPage.test.tsx -t "targets project primitives\|renders controls\|filters right side OA rows\|keeps selected bank and OA rows\|renders submitted bucket\|shows loading and empty states"` | expected-fail | Selected behavior tests passed; source-level contract failed as expected for remaining dialog/feedback targets |
| 2026-06-07 | `P083-phase-6-batch-accounting-oa-table` | `cd web && npx vitest run BatchAccountingPage.test.tsx` | expected-fail | 12 behavior tests passed; 1 source-level contract failed |
| 2026-06-07 | `P083-phase-6-batch-accounting-oa-table` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P083-phase-6-batch-accounting-oa-table` | `if rg -n '<Table\|TableHead\|TableBody\|TableRow\|TableCell\|TableContainer\|<Checkbox\|<Chip\|MuiTable\|MuiCheckbox\|MuiChip' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi` | passed | OA table MUI residues cleared |
| 2026-06-07 | `P083-phase-6-batch-accounting-oa-table` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P083-phase-6-batch-accounting-oa-table` | `git status --short --branch` | passed | Only P083 page/style files changed before docs |
| 2026-06-07 | `P082-phase-6-batch-accounting-bank-list-and-summary` | `cd web && npx vitest run BatchAccountingPage.test.tsx -t "targets project primitives\|renders controls\|updates selected totals\|submits mismatched\|clears difference note when switching bank rows\|renders submitted bucket"` | expected-fail | Selected behavior tests passed; source-level contract failed as expected for remaining OA table/dialog/feedback targets |
| 2026-06-07 | `P082-phase-6-batch-accounting-bank-list-and-summary` | `cd web && npx vitest run BatchAccountingPage.test.tsx` | expected-fail | 12 behavior tests passed; 1 source-level contract failed |
| 2026-06-07 | `P082-phase-6-batch-accounting-bank-list-and-summary` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P082-phase-6-batch-accounting-bank-list-and-summary` | `if rg -n 'WarningAmberRoundedIcon\|Tooltip\|IconButton\|<TextField[^\\n]*(label="差额说明")\|银行流水金额.*<Chip\|已选 OA.*<Chip\|差额.*<Chip' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi` | passed | Bank list/summary/mismatch MUI residues cleared |
| 2026-06-07 | `P082-phase-6-batch-accounting-bank-list-and-summary` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P082-phase-6-batch-accounting-bank-list-and-summary` | `git status --short --branch` | passed | Only P082 page/style files changed before docs |
| 2026-06-07 | `P081-phase-6-batch-accounting-page-shell-filters` | `cd web && npx vitest run BatchAccountingPage.test.tsx -t "targets project primitives\|renders controls\|filters right side OA rows\|clears difference note when switching submitted and unsubmitted buckets\|keeps selected bank and OA rows"` | expected-fail | Selected behavior tests passed; source-level contract failed as expected with bank panel/list/region target cleared |
| 2026-06-07 | `P081-phase-6-batch-accounting-page-shell-filters` | `cd web && npx vitest run BatchAccountingPage.test.tsx` | expected-fail | 12 behavior tests passed; 1 source-level contract failed for remaining OA table/dialog/feedback targets |
| 2026-06-07 | `P081-phase-6-batch-accounting-page-shell-filters` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P081-phase-6-batch-accounting-page-shell-filters` | `if rg -n 'RefreshOutlinedIcon\|SearchOutlinedIcon\|ClearOutlinedIcon\|ToggleButton\|ToggleButtonGroup\|InputAdornment\|label="流水年份"\|label="OA年份"\|label="搜索OA内容"' web/src/pages/BatchAccountingPage.tsx; then exit 1; else exit 0; fi` | passed | Page shell/filter MUI/icon/TextField label residues cleared |
| 2026-06-07 | `P081-phase-6-batch-accounting-page-shell-filters` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P081-phase-6-batch-accounting-page-shell-filters` | `git status --short --branch` | passed | Only P081 page/style files changed before docs |
| 2026-06-07 | `P080-phase-6-batch-accounting-characterization-tests` | `cd web && npx vitest run BatchAccountingPage.test.tsx` | expected-fail | 12 behavior tests passed；1 source-level contract failed as expected against current MUI runtime |
| 2026-06-07 | `P080-phase-6-batch-accounting-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P080-phase-6-batch-accounting-characterization-tests` | `git status --short --branch` | passed | Only P080 test file changed before docs |
| 2026-06-07 | `P079-phase-6-batch-accounting-discovery` | `test -f docs/refactor-ui/modules/phase_6_batch_accounting.md` | passed | Module discovery doc exists |
| 2026-06-07 | `P079-phase-6-batch-accounting-discovery` | `rg -n "P079-phase-6-batch-accounting-discovery\|Current MUI Inventory\|User-visible Entrypoints\|P080-phase-6-batch-accounting-characterization-tests" docs/refactor-ui/modules/phase_6_batch_accounting.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | Discovery terms and next prompt recorded |
| 2026-06-07 | `P079-phase-6-batch-accounting-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P079-phase-6-batch-accounting-discovery` | `git status --short --branch` | passed | Only P079 docs changed |
| 2026-06-07 | `MG-P078-phase-6-no-oa-bank-batches` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx NoOaBankBatchApi.test.ts` | passed | 27 tests passed |
| 2026-06-07 | `MG-P078-phase-6-no-oa-bank-batches` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `MG-P078-phase-6-no-oa-bank-batches` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `MG-P078-phase-6-no-oa-bank-batches` | `if rg -n '@mui/\|Mui[A-Z]\|RefreshOutlinedIcon\|CloseIcon\|ToggleButton\|TextField\|TableCell\|TableRow\|TableHead\|TableBody\|Drawer\\b\|DialogTitle\|DialogContent\|DialogActions\|Snackbar\|Chip\|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi` | passed | NoOaBankBatchPage has no direct MUI import/legacy source residue |
| 2026-06-07 | `MG-P078-phase-6-no-oa-bank-batches` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P078-phase-6-no-oa-bank-batches` | `git status --short --branch` | passed | Clean worktree before MG docs update |
| 2026-06-07 | `P078-phase-6-no-oa-bank-batches-overlays-feedback` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx` | passed | 20 tests passed |
| 2026-06-07 | `P078-phase-6-no-oa-bank-batches-overlays-feedback` | `cd web && npx vitest run NoOaBankBatchApi.test.ts` | passed | 7 tests passed |
| 2026-06-07 | `P078-phase-6-no-oa-bank-batches-overlays-feedback` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P078-phase-6-no-oa-bank-batches-overlays-feedback` | `if rg -n '@mui/\|Mui[A-Z]\|RefreshOutlinedIcon\|CloseIcon\|ToggleButton\|TextField\|TableCell\|TableRow\|TableHead\|TableBody\|Drawer\\b\|DialogTitle\|DialogContent\|DialogActions\|Snackbar\|Chip\|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi` | passed | NoOaBankBatchPage has no direct MUI import/legacy source residue |
| 2026-06-07 | `P078-phase-6-no-oa-bank-batches-overlays-feedback` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P078-phase-6-no-oa-bank-batches-overlays-feedback` | `git status --short --branch` | passed | Only P078 implementation files changed before docs |
| 2026-06-07 | `P077-phase-6-no-oa-bank-batches-transaction-region` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives\|renders tag management\|shows batch blocking\|clears hidden selected rows\|selects transactions\|submits selected transaction\|submits internal transfer\|withdraw"` | expected-fail | 6 transaction/withdraw behavior tests passed; source-level contract failed as expected |
| 2026-06-07 | `P077-phase-6-no-oa-bank-batches-transaction-region` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx` | expected-fail | 19 behavior tests passed; 1 source-level contract failed |
| 2026-06-07 | `P077-phase-6-no-oa-bank-batches-transaction-region` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P077-phase-6-no-oa-bank-batches-transaction-region` | `sed -n '930,1096p' web/src/pages/NoOaBankBatchPage.tsx \| if rg -n 'TableContainer\|<Table\\b\|TableHead\|TableBody\|TableRow\|TableCell\|<Checkbox\\b\|<Chip\\b\|BatchStatusChip'; then exit 1; else exit 0; fi` | passed | Transaction-region MUI table/checkbox/tag residues cleared; grep scoped because P078 drawer still owns MUI Checkbox |
| 2026-06-07 | `P077-phase-6-no-oa-bank-batches-transaction-region` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P077-phase-6-no-oa-bank-batches-transaction-region` | `git status --short --branch` | passed | Only P077 implementation files changed before docs |
| 2026-06-07 | `P076-phase-6-no-oa-bank-batches-label-rails` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives\|renders tag management\|shows batch blocking\|clears hidden selected rows\|main and child label rails"` | expected-fail | 4 selected behavior tests passed; source-level contract failed as expected |
| 2026-06-07 | `P076-phase-6-no-oa-bank-batches-label-rails` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx` | expected-fail | 19 behavior tests passed; 1 source-level contract failed |
| 2026-06-07 | `P076-phase-6-no-oa-bank-batches-label-rails` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P076-phase-6-no-oa-bank-batches-label-rails` | `if rg -n 'ListItemButton\|<List\\b\|Mui-selected' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi` | passed | LabelRail MUI list/selected residues cleared |
| 2026-06-07 | `P076-phase-6-no-oa-bank-batches-label-rails` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P076-phase-6-no-oa-bank-batches-label-rails` | `git status --short --branch` | passed | Only P076 implementation files changed before docs |
| 2026-06-07 | `P075-phase-6-no-oa-bank-batches-page-shell-filters` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives\|renders tag management\|shows batch blocking\|clears hidden selected rows\|main and child label rails"` | expected-fail | 4 selected behavior tests passed; source-level contract failed as expected |
| 2026-06-07 | `P075-phase-6-no-oa-bank-batches-page-shell-filters` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx` | expected-fail | 19 behavior tests passed; 1 source-level contract failed |
| 2026-06-07 | `P075-phase-6-no-oa-bank-batches-page-shell-filters` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P075-phase-6-no-oa-bank-batches-page-shell-filters` | `if rg -n 'RefreshOutlinedIcon\|ToggleButton\|ToggleButtonGroup\|<TextField[^\\n]*(label="月份"\|label="银行账户")' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi` | passed | Page shell/filter MUI residues cleared |
| 2026-06-07 | `P075-phase-6-no-oa-bank-batches-page-shell-filters` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P075-phase-6-no-oa-bank-batches-page-shell-filters` | `git status --short --branch` | passed | Only P075 implementation files changed before docs |
| 2026-06-07 | `P074-phase-6-no-oa-bank-batches-characterization-tests` | `cd web && npx vitest run NoOaBankBatchPage.test.tsx` | expected-fail | 19 behavior tests passed; 1 source-level contract failed against current MUI runtime |
| 2026-06-07 | `P074-phase-6-no-oa-bank-batches-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P074-phase-6-no-oa-bank-batches-characterization-tests` | `git status --short --branch` | passed | Only P074 test file changed before docs |
| 2026-06-07 | `P073-phase-6-no-oa-bank-batches-discovery` | `test -f docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md` | passed | Module discovery doc exists |
| 2026-06-07 | `P073-phase-6-no-oa-bank-batches-discovery` | `rg -n "P073-phase-6-no-oa-bank-batches-discovery\|Current MUI Inventory\|User-visible Entrypoints\|P074-phase-6-no-oa-bank-batches-characterization-tests" docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | Discovery terms and next prompt recorded |
| 2026-06-07 | `P073-phase-6-no-oa-bank-batches-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P073-phase-6-no-oa-bank-batches-discovery` | `git status --short --branch` | passed | Only P073 docs changed |
| 2026-06-07 | `MG-P072-phase-6-output-invoice-collections` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` | passed | 6 tests passed |
| 2026-06-07 | `MG-P072-phase-6-output-invoice-collections` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `MG-P072-phase-6-output-invoice-collections` | `if rg -n '@mui/\|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi` | passed | OutputInvoiceCollections runtime scope has no direct MUI import/selector residue |
| 2026-06-07 | `MG-P072-phase-6-output-invoice-collections` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P072-phase-6-output-invoice-collections` | `git status --short --branch` | passed | Only allowed P072 implementation/docs files changed before exact staging |
| 2026-06-07 | `P072-phase-6-output-invoice-collections-receipt-history-and-preview` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives\|opens the three right-side workflow drawers\|closes lifecycle actions"` | passed | Source-level primitive contract and receipt drawer workflows passed |
| 2026-06-07 | `P072-phase-6-output-invoice-collections-receipt-history-and-preview` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` | passed | 6 tests passed |
| 2026-06-07 | `P072-phase-6-output-invoice-collections-receipt-history-and-preview` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P072-phase-6-output-invoice-collections-receipt-history-and-preview` | `if rg -n '@mui/\|Mui[A-Z]\|CloseOutlinedIcon\|CircularProgress\|TextField\|FormControlLabel\|RadioGroup\|IconButton\|DialogTitle\|DialogContent\|DialogActions\|<Dialog\|</Dialog\|<Drawer\|</Drawer\|Chip' web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx; then exit 1; else exit 0; fi` | passed | Corrected from the over-broad draft grep so `AppDialog`/`AppDrawer` are allowed while real MUI surfaces are blocked |
| 2026-06-07 | `P072-phase-6-output-invoice-collections-receipt-history-and-preview` | `if rg -n '@mui/\|Mui[A-Z]' web/src/pages/OutputInvoiceCollectionsPage.tsx web/src/components/outputInvoiceCollections; then exit 1; else exit 0; fi` | passed | OutputInvoiceCollections runtime scope has no direct MUI import/selector residue |
| 2026-06-07 | `P072-phase-6-output-invoice-collections-receipt-history-and-preview` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P072-phase-6-output-invoice-collections-receipt-history-and-preview` | `git status --short --branch` | passed | Only P072 implementation files changed before docs |
| 2026-06-07 | `P071-phase-6-output-invoice-collections-workflow-drawers` | `if rg -n '@mui/\|Mui[A-Z]\|CloseOutlinedIcon\|TextField\|MenuItem\|FormControlLabel\|RadioGroup\|Radio\|IconButton\|DialogTitle\|DialogContent\|DialogActions' web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx; then exit 1; else exit 0; fi` | passed | Status/reminder and red relation workflow drawers have no scoped MUI residue |
| 2026-06-07 | `P071-phase-6-output-invoice-collections-workflow-drawers` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives\|closes lifecycle actions"` | expected-fail | Lifecycle behavior test passed; remaining source-level failure lists only receipt history/preview |
| 2026-06-07 | `P071-phase-6-output-invoice-collections-workflow-drawers` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` | expected-fail | 5 behavior tests passed; 1 source-level contract failed, limited to receipt history/preview |
| 2026-06-07 | `P071-phase-6-output-invoice-collections-workflow-drawers` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P071-phase-6-output-invoice-collections-workflow-drawers` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P071-phase-6-output-invoice-collections-workflow-drawers` | `git status --short --branch` | passed | Only P071 implementation files changed before docs |
| 2026-06-07 | `P070-phase-6-output-invoice-collections-simple-drawers` | `if rg -n '@mui/\|Mui[A-Z]\|CloseOutlinedIcon\|CircularProgress\|TextField\|MenuItem\|TableCell\|TableRow\|TableHead\|TableBody\|Chip\|IconButton\|DialogTitle\|DialogContent\|DialogActions' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx; then exit 1; else exit 0; fi` | passed | Detail, rules and settings drawers have no scoped MUI residue |
| 2026-06-07 | `P070-phase-6-output-invoice-collections-simple-drawers` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives\|opens the three right-side workflow drawers\|closes lifecycle actions"` | expected-fail | Selected behavior tests passed; remaining source-level failure lists only four workflow/lifecycle drawer files |
| 2026-06-07 | `P070-phase-6-output-invoice-collections-simple-drawers` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` | expected-fail | 5 behavior tests passed; 1 source-level contract failed, limited to four drawer files |
| 2026-06-07 | `P070-phase-6-output-invoice-collections-simple-drawers` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P070-phase-6-output-invoice-collections-simple-drawers` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P070-phase-6-output-invoice-collections-simple-drawers` | `git status --short --branch` | passed | Only P070 implementation files changed before docs |
| 2026-06-07 | `P069-phase-6-output-invoice-collections-grouped-table` | `if rg -n '@mui/\|Mui[A-Z]\|TablePagination\|SortOutlinedIcon\|TableCell\|TableRow\|TableHead\|TableBody\|Chip\|IconButton\|SxProps\|Theme' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx; then exit 1; else exit 0; fi` | passed | Grouped table has no scoped MUI/table/tag/action/pagination residue |
| 2026-06-07 | `P069-phase-6-output-invoice-collections-grouped-table` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives\|adds sidebar route\|opens the three right-side workflow drawers"` | expected-fail | Selected behavior tests passed; remaining source-level failure lists only seven drawer files |
| 2026-06-07 | `P069-phase-6-output-invoice-collections-grouped-table` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` | expected-fail | 5 behavior tests passed; 1 source-level contract failed, limited to drawer residue |
| 2026-06-07 | `P069-phase-6-output-invoice-collections-grouped-table` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P069-phase-6-output-invoice-collections-grouped-table` | `cd web && npm run build` | passed | Build passed after fixing sort button field narrowing; known HeroUI/Tailwind CSS minifier warnings and chunk size warning remain |
| 2026-06-07 | `P069-phase-6-output-invoice-collections-grouped-table` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P069-phase-6-output-invoice-collections-grouped-table` | `git status --short --branch` | passed | Only P069 table/style files changed before docs |
| 2026-06-07 | `P068-phase-6-output-invoice-collections-filter-and-expandable` | `if rg -n '@mui/\|Mui[A-Z]\|FilterListOutlinedIcon\|ArrowDownwardOutlinedIcon\|ArrowUpwardOutlinedIcon\|ExpandLessOutlinedIcon\|ExpandMoreOutlinedIcon\|TextField\|MenuItem\|Checkbox\|Radio\|IconButton\|Tooltip\|MuiButton-startIcon' web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx web/src/components/outputInvoiceCollections/ExpandableCellText.tsx; then exit 1; else exit 0; fi` | passed | Filter menu and expandable text have no scoped MUI/icon/input/menu residue |
| 2026-06-07 | `P068-phase-6-output-invoice-collections-filter-and-expandable` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives\|adds sidebar route"` | expected-fail | Main behavior test passed; remaining source-level failure lists only table and drawer files |
| 2026-06-07 | `P068-phase-6-output-invoice-collections-filter-and-expandable` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` | expected-fail | 5 behavior tests passed; 1 source-level contract failed, limited to table/drawer residue |
| 2026-06-07 | `P068-phase-6-output-invoice-collections-filter-and-expandable` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P068-phase-6-output-invoice-collections-filter-and-expandable` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P068-phase-6-output-invoice-collections-filter-and-expandable` | `git status --short --branch` | passed | Only P068 implementation files changed before docs |
| 2026-06-07 | `P067-phase-6-output-invoice-collections-page-shell` | `if rg -n '@mui/\|Mui[A-Z]\|RefreshOutlinedIcon\|Skeleton\|TextField\|MenuItem\|Paper\|Typography' web/src/pages/OutputInvoiceCollectionsPage.tsx; then exit 1; else exit 0; fi` | passed | Page shell has no scoped MUI/icon/input/loading/summary residue |
| 2026-06-07 | `P067-phase-6-output-invoice-collections-page-shell` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx -t "targets project primitives\|adds sidebar route\|uses a standard empty state\|pauses read model"` | expected-fail | Selected behavior tests passed; remaining source-level failure lists only table/filter/expandable/drawer files |
| 2026-06-07 | `P067-phase-6-output-invoice-collections-page-shell` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` | expected-fail | 5 behavior tests passed; 1 source-level contract failed, limited to table/filter/expandable/drawer residue |
| 2026-06-07 | `P067-phase-6-output-invoice-collections-page-shell` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P067-phase-6-output-invoice-collections-page-shell` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P067-phase-6-output-invoice-collections-page-shell` | `git status --short --branch` | passed | Only P067 files and docs changed |
| 2026-06-07 | `P066-phase-6-output-invoice-collections-characterization-tests` | `cd web && npx vitest run OutputInvoiceCollectionsPage.test.tsx` | expected-fail | 5 behavior tests passed; 1 intended source-level failure lists page/table/filter/expandable/drawer MUI residue and missing project primitives |
| 2026-06-07 | `P066-phase-6-output-invoice-collections-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P066-phase-6-output-invoice-collections-characterization-tests` | `git status --short --branch` | passed | Only P066 test file changed before docs |
| 2026-06-07 | `P065-phase-6-output-invoice-collections-discovery` | `test -f docs/refactor-ui/modules/phase_6_output_invoice_collections.md` | passed | OutputInvoiceCollections module discovery doc exists |
| 2026-06-07 | `P065-phase-6-output-invoice-collections-discovery` | `rg -n "P065-phase-6-output-invoice-collections-discovery\|Current MUI Inventory\|User-visible Entrypoints\|P066-phase-6-output-invoice-collections-characterization-tests" docs/refactor-ui/modules/phase_6_output_invoice_collections.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | OutputInvoiceCollections discovery and next prompt recorded |
| 2026-06-07 | `P065-phase-6-output-invoice-collections-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P065-phase-6-output-invoice-collections-discovery` | `git status --short --branch` | passed | Only P065 docs files changed |
| 2026-06-07 | `MG-P064-phase-6-oa-pending-payments` | `git push origin refactor-ui` | passed | Commit `94efb866 feat: complete oa pending payments ui migration` pushed |
| 2026-06-07 | `P064-phase-6-oa-pending-payments-grouped-table` | `if rg -n '@mui/\|Mui[A-Z]\|TablePagination\|InfoOutlinedIcon\|SortOutlinedIcon\|TableCell\|TableRow\|TableHead\|TableBody\|Chip\|IconButton' web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx; then exit 1; else exit 0; fi` | passed | Grouped table has no scoped MUI/table/tag/action residue |
| 2026-06-07 | `P064-phase-6-oa-pending-payments-grouped-table` | `if rg -n '@mui/\|Mui[A-Z]' web/src/pages/OaPendingPaymentsPage.tsx web/src/components/oaPendingPayments; then exit 1; else exit 0; fi` | passed | OaPendingPayments page and components have no scoped MUI residue |
| 2026-06-07 | `P064-phase-6-oa-pending-payments-grouped-table` | `cd web && npx vitest run OaPendingPaymentsPage.test.tsx` | passed | 6 tests passed |
| 2026-06-07 | `P064-phase-6-oa-pending-payments-grouped-table` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P064-phase-6-oa-pending-payments-grouped-table` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P064-phase-6-oa-pending-payments-grouped-table` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P064-phase-6-oa-pending-payments-grouped-table` | `git status --short --branch` | passed | Only P064 table/style files changed before docs |
| 2026-06-07 | `P063-phase-6-oa-pending-payments-page-shell-toolbar` | `if rg -n '@mui/\|Mui[A-Z]\|RefreshOutlinedIcon\|TuneOutlinedIcon\|Skeleton\|TextField\|MenuItem' web/src/pages/OaPendingPaymentsPage.tsx; then exit 1; else exit 0; fi` | passed | Page shell has no scoped MUI/icon/TextField/MenuItem residue |
| 2026-06-07 | `P063-phase-6-oa-pending-payments-page-shell-toolbar` | `cd web && npx vitest run OaPendingPaymentsPage.test.tsx -t "targets project primitives\|adds sidebar route\|keeps pending invoice rules drawer\|uses a standard empty state\|shows neutral unavailable detail"` | expected-fail | 4 behavior tests passed; remaining source-level failure lists only `OaPendingPaymentsTable.tsx` |
| 2026-06-07 | `P063-phase-6-oa-pending-payments-page-shell-toolbar` | `cd web && npx vitest run OaPendingPaymentsPage.test.tsx` | expected-fail | 5 behavior tests passed; 1 source-level contract failed, limited to table residue |
| 2026-06-07 | `P063-phase-6-oa-pending-payments-page-shell-toolbar` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P063-phase-6-oa-pending-payments-page-shell-toolbar` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P063-phase-6-oa-pending-payments-page-shell-toolbar` | `git status --short --branch` | passed | Only P063 implementation/test/docs files changed |
| 2026-06-07 | `P062-phase-6-oa-pending-payments-characterization-tests` | `cd web && npx vitest run OaPendingPaymentsPage.test.tsx` | expected-fail | 5 behavior tests passed; 1 intended source-level failure lists page/table MUI residue |
| 2026-06-07 | `P062-phase-6-oa-pending-payments-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P062-phase-6-oa-pending-payments-characterization-tests` | `git status --short --branch` | passed | Only P062 test and docs files changed |
| 2026-06-07 | `P061-phase-6-oa-pending-payments-discovery` | `test -f docs/refactor-ui/modules/phase_6_oa_pending_payments.md` | passed | OA pending payments module discovery doc exists |
| 2026-06-07 | `P061-phase-6-oa-pending-payments-discovery` | `rg -n "P061-phase-6-oa-pending-payments-discovery\|Current MUI Inventory\|User-visible Entrypoints\|P062-phase-6-oa-pending-payments-characterization-tests" docs/refactor-ui/modules/phase_6_oa_pending_payments.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | OA pending payments discovery and next prompt recorded |
| 2026-06-07 | `P061-phase-6-oa-pending-payments-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P061-phase-6-oa-pending-payments-discovery` | `git status --short --branch` | passed | Only P061/P062 docs files changed |
| 2026-06-07 | `MG-P060-phase-6-input-invoice-usage` | `git push origin refactor-ui` | passed | Commit `21c79cea feat: complete input invoice usage ui migration` pushed |
| 2026-06-07 | `P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer` | `if rg -n '@mui/\|Mui[A-Z]\|CloseOutlinedIcon\|CircularProgress\|@mui/material/Drawer\|TextField\|TableCell\|TableRow\|TableHead\|TableBody\|Checkbox\|Chip\|MenuItem' web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx; then exit 1; else exit 0; fi` | passed | OA reverse drawer has no scoped MUI residue |
| 2026-06-07 | `P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer` | `if rg -n '@mui/\|Mui[A-Z]' web/src/pages/InputInvoiceUsagePage.tsx web/src/components/inputInvoiceUsage; then exit 1; else exit 0; fi` | passed | InputInvoiceUsage page and components have no scoped MUI residue |
| 2026-06-07 | `P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer` | `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "OA reverse drawer\|workflow primitive targets\|parent state can keep\|opening and closing workflow drawers"` | passed | 6 tests passed |
| 2026-06-07 | `P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx` | passed | 21 tests passed |
| 2026-06-07 | `P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer` | `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 12 tests passed |
| 2026-06-07 | `P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P060-phase-6-input-invoice-usage-oa-reverse-workspace-drawer` | `git status --short --branch` | passed | Only P060 OA drawer, AppDrawer persistent mode, styles, and docs files changed |
| 2026-06-07 | `P059-phase-6-input-invoice-usage-payment-rules-drawer` | `if rg -n '@mui/\|Mui[A-Z]\|CloseOutlinedIcon\|CircularProgress\|@mui/material/Drawer\|TextField\|TableCell\|TableRow\|TableHead\|TableBody\|Chip' web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx; then exit 1; else exit 0; fi` | passed | Payment rules drawer has no scoped MUI residue |
| 2026-06-07 | `P059-phase-6-input-invoice-usage-payment-rules-drawer` | `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "payment status rules\|workflow primitive targets"` | expected-fail | Payment rules behavior passed; only intended OA-reverse source-level failure remains |
| 2026-06-07 | `P059-phase-6-input-invoice-usage-payment-rules-drawer` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx` | expected-fail | 19 passed, 2 intended source-level failures; payment rules drawer cleared from failure lists |
| 2026-06-07 | `P059-phase-6-input-invoice-usage-payment-rules-drawer` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P059-phase-6-input-invoice-usage-payment-rules-drawer` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P059-phase-6-input-invoice-usage-payment-rules-drawer` | `git status --short --branch` | passed | Only P059 payment rules drawer, styles, and docs files changed |
| 2026-06-07 | `P058-phase-6-input-invoice-usage-detail-and-export-drawers` | `if rg -n '@mui/\|Mui[A-Z]\|CloseOutlinedIcon\|CircularProgress\|@mui/material/Drawer\|TableCell\|TableRow\|TableHead\|TableBody' web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx; then exit 1; else exit 0; fi` | passed | Detail/export drawers have no scoped MUI residue |
| 2026-06-07 | `P058-phase-6-input-invoice-usage-detail-and-export-drawers` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx -t "detail drawer\|loads export preview\|workflow primitive targets"` | expected-fail | Detail/export selected behavior passed; only intended payment-rules/OA-reverse source-level failure remains |
| 2026-06-07 | `P058-phase-6-input-invoice-usage-detail-and-export-drawers` | `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "lazy-loads full invoice detail\|supports invoice, bank, OA and relation-list detail payloads"` | passed | 2 tests passed |
| 2026-06-07 | `P058-phase-6-input-invoice-usage-detail-and-export-drawers` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx` | expected-fail | 19 passed, 2 intended source-level failures; detail/export drawers cleared from failure lists |
| 2026-06-07 | `P058-phase-6-input-invoice-usage-detail-and-export-drawers` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P058-phase-6-input-invoice-usage-detail-and-export-drawers` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P058-phase-6-input-invoice-usage-detail-and-export-drawers` | `git status --short --branch` | passed | Only P058 detail/export drawer, styles, and docs files changed |
| 2026-06-07 | `P057-phase-6-input-invoice-usage-filter-menu` | `if rg -n '@mui/\|Mui[A-Z]\|FilterListOutlinedIcon\|ArrowDownwardOutlinedIcon\|ArrowUpwardOutlinedIcon\|MenuItem\|ListItemText\|Checkbox\|Radio' web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx; then exit 1; else exit 0; fi` | passed | Filter menu has no scoped MUI residue |
| 2026-06-07 | `P057-phase-6-input-invoice-usage-filter-menu` | `cd web && npx vitest run InputInvoiceUsageFiltersAndDrawers.test.tsx -t "InputInvoiceUsageFilterMenu\|workflow primitive targets"` | expected-fail | Filter menu behavior passed; only intended drawer source-level failure remains |
| 2026-06-07 | `P057-phase-6-input-invoice-usage-filter-menu` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx` | expected-fail | 19 passed, 2 intended source-level failures; filter menu cleared from failure lists |
| 2026-06-07 | `P057-phase-6-input-invoice-usage-filter-menu` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P057-phase-6-input-invoice-usage-filter-menu` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P057-phase-6-input-invoice-usage-filter-menu` | `git status --short --branch` | passed | Only P057 filter-menu/styles/docs files changed |
| 2026-06-07 | `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell` | `if rg -n '@mui/\|Mui[A-Z]\|TablePagination\|InfoOutlinedIcon\|ExpandLessOutlinedIcon\|ExpandMoreOutlinedIcon' web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx web/src/components/inputInvoiceUsage/ExpandableCellText.tsx; then exit 1; else exit 0; fi` | passed | Table and expandable cell have no scoped MUI residue |
| 2026-06-07 | `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives\|adds sidebar route"` | expected-fail | Main table behavior passed; only intended filter/drawer source-level failure remains |
| 2026-06-07 | `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx` | expected-fail | 19 passed, 2 intended source-level failures; table and expandable cell cleared from failure lists |
| 2026-06-07 | `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell` | `git status --short --branch` | passed | Only P056 table/expandable/styles/docs files changed |
| 2026-06-07 | `P055-phase-6-input-invoice-usage-page-shell-toolbar` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx -t "targets project primitives\|uses a standard empty state\|pauses read model retry\|adds sidebar route\|drops legacy column filters\|loads export preview"` | expected-fail | Five behavior tests passed; only intended source-level table/filter/drawer failure remains |
| 2026-06-07 | `P055-phase-6-input-invoice-usage-page-shell-toolbar` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx` | expected-fail | 19 passed, 2 intended source-level failures; `InputInvoiceUsagePage.tsx` cleared from failure lists |
| 2026-06-07 | `P055-phase-6-input-invoice-usage-page-shell-toolbar` | `if rg -n '@mui/\|Mui[A-Z]\|FileDownloadOutlinedIcon\|RefreshOutlinedIcon\|Skeleton\|TextField' web/src/pages/InputInvoiceUsagePage.tsx; then exit 1; else exit 0; fi` | passed | Page shell has no MUI/icon/TextField residue |
| 2026-06-07 | `P055-phase-6-input-invoice-usage-page-shell-toolbar` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P055-phase-6-input-invoice-usage-page-shell-toolbar` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P055-phase-6-input-invoice-usage-page-shell-toolbar` | `git status --short --branch` | passed | Only P055 page/style/docs files changed |
| 2026-06-07 | `P054-phase-6-input-invoice-usage-characterization-tests` | `cd web && npx vitest run InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx` | expected-fail | 19 passed, 2 intended source-level failures listing remaining MUI imports/selectors and missing primitive targets |
| 2026-06-07 | `P054-phase-6-input-invoice-usage-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P054-phase-6-input-invoice-usage-characterization-tests` | `git status --short --branch` | passed | Only P054 tests and docs files changed |
| 2026-06-07 | `P053-phase-6-input-invoice-usage-discovery` | `test -f docs/refactor-ui/modules/phase_6_input_invoice_usage.md` | passed | InputInvoiceUsage module discovery doc exists |
| 2026-06-07 | `P053-phase-6-input-invoice-usage-discovery` | `rg -n "P053-phase-6-input-invoice-usage-discovery\|Current MUI Inventory\|User-visible Entrypoints\|P054-phase-6-input-invoice-usage-characterization-tests" docs/refactor-ui/modules/phase_6_input_invoice_usage.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | InputInvoiceUsage discovery and next prompt recorded |
| 2026-06-07 | `P053-phase-6-input-invoice-usage-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P053-phase-6-input-invoice-usage-discovery` | `git status --short --branch` | passed | Only P053 docs files changed |
| 2026-06-07 | `MG-P052-phase-6-pending-invoices` | `git push origin refactor-ui` | passed | Commit `369e480c feat: complete pending invoices ui migration` pushed |
| 2026-06-07 | `P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog` | `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens invoice picker from status column\|manual invoice action still previews before confirm\|targets project primitives"` | passed | 3 focused tests passed |
| 2026-06-07 | `P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog` | `cd web && npx vitest run PendingInvoicesPage.test.tsx` | passed | 15 tests passed; source-level project primitive contract fully passed |
| 2026-06-07 | `P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog` | `if rg -n '@mui/\|Mui[A-Z]\|DataGrid\|GridColDef\|TablePagination\|TextField' web/src/components/pendingInvoices web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi` | passed | Pending invoices page/components have no scoped MUI/DataGrid residue |
| 2026-06-07 | `P052-phase-6-pending-invoices-invoice-picker-and-manual-dialog` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P051-phase-6-pending-invoices-rules-drawer` | `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks\|keeps pending invoice rule draft\|preserves unsaved rule selections\|shows income rule-group filters\|targets project primitives"` | expected-fail | P051 behavior tests passed; single remaining failure is P052 source contract |
| 2026-06-07 | `P051-phase-6-pending-invoices-rules-drawer` | `cd web && npx vitest run PendingInvoicesPage.test.tsx` | expected-fail | 14 passed, 1 expected source-level failure listing only invoice picker drawer and manual dialog |
| 2026-06-07 | `P051-phase-6-pending-invoices-rules-drawer` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P051-phase-6-pending-invoices-rules-drawer` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P051-phase-6-pending-invoices-rules-drawer` | `if rg -n '@mui/\|Mui[A-Z]\|FormControlLabel\|CircularProgress\|Checkbox' web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx; then exit 1; else exit 0; fi` | passed | Rules drawer source has no MUI imports or old MUI checkbox helpers |
| 2026-06-07 | `P051-phase-6-pending-invoices-rules-drawer` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers` | `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "opens relation, object detail, rules, and export drawers with loading callbacks\|renders project four-zone table contract\|targets project primitives"` | expected-fail | P050 behavior tests passed; single remaining failure is P051-P052 source contract |
| 2026-06-07 | `P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers` | `cd web && npx vitest run PendingInvoicesPage.test.tsx` | expected-fail | 14 passed, 1 expected source-level failure listing only rules drawer, invoice picker drawer and manual dialog |
| 2026-06-07 | `P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers` | `if rg -n '@mui/' web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx; then exit 1; else exit 0; fi` | passed | P050 source has no MUI imports |
| 2026-06-07 | `P050-phase-6-pending-invoices-drawer-frame-and-simple-drawers` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P049-phase-6-pending-invoices-four-zone-table` | `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract\|shows income rule-group filters\|keeps row status actions available\|targets project primitives"` | expected-fail | Main table behavior tests passed; single remaining failure is P050-P052 drawer/dialog source contract |
| 2026-06-07 | `P049-phase-6-pending-invoices-four-zone-table` | `cd web && npx vitest run PendingInvoicesPage.test.tsx` | expected-fail | 14 passed, 1 expected source-level failure listing only 7 drawer/dialog files |
| 2026-06-07 | `P049-phase-6-pending-invoices-four-zone-table` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed after resolving local selector collision with shared FinanceTable CSS contract |
| 2026-06-07 | `P049-phase-6-pending-invoices-four-zone-table` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P049-phase-6-pending-invoices-four-zone-table` | `if rg -n '@mui/\|MuiChip-label\|SxProps\|TableSortLabel\|MoreVertOutlinedIcon\|InfoOutlinedIcon' web/src/components/pendingInvoices/PendingInvoicesTable.tsx; then exit 1; else exit 0; fi` | passed | Main table source has no scoped MUI residue |
| 2026-06-07 | `P049-phase-6-pending-invoices-four-zone-table` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P000-docs-bootstrap` | `find docs/refactor-ui -maxdepth 1 -type f -name '*.md' | sort` | passed | 四份文档存在 |
| 2026-06-07 | `P000-docs-bootstrap` | `rg -n "refactor-ui|HeroUI|Micro-JIT|cumulative MG" docs/refactor-ui docs/index.md DESIGN.md` | passed | 关键规则和入口存在 |
| 2026-06-07 | `P000-docs-bootstrap` | `git status --short --branch` | passed | 仅文档变更和 docs/refactor-ui 新文件 |
| 2026-06-07 | `MG-P000-docs-bootstrap` | `git push -u origin refactor-ui` | passed | `52f4520f` pushed |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `find docs/refactor-ui -maxdepth 1 -type f -name '*.md' | sort` | passed | 八份 refactor-ui 文档存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "baseline_inventory|platform_stack_migration|test_migration_strategy|module_inventory|右侧抽屉|行为等价|Behavioral Equivalence" docs/refactor-ui docs/index.md DESIGN.md PRODUCT.md` | passed | 新事实源和行为等价规则存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "重构理念|文档沉淀规则|按需新建|Module docs on demand|modules/<module>|不为一次性临时分析新建 md" docs/refactor-ui docs/index.md DESIGN.md PRODUCT.md` | passed | 重构理念和按需新建专项 md 规则存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "完整重构路径|MG-P001-baseline-doc-gap-fill|phase_1_docs_and_tokens|phase_9_closeout|不得跳过平台栈" docs/refactor-ui/README.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | 完整重构路径存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "Phase 与 Prompt 关系|Phase-to-Prompt Rules|每个 phase 可以包含多个|上一条 prompt|单独分析生成" docs/refactor-ui/README.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/module_inventory.md docs/refactor-ui/refactor_ui_state.md` | passed | phase-to-prompt 规则存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `rg -n "/goal|完整执行 fin-ops-platform 非关联台 UI 平台迁移计划|最终完成条件|每次最终回复或阶段记录必须包含" docs/refactor-ui/refactor_ui_master_goal_prompt.md` | passed | 主控 goal prompt 存在 |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P001-baseline-doc-gap-fill` | `git status --short --branch` | passed | 仅文档变更 |
| 2026-06-07 | `MG-P001-baseline-doc-gap-fill` | `git push origin refactor-ui` | passed | `8f3daae8` pushed |
| 2026-06-07 | `P002-phase-1-docs-and-tokens-discovery` | `test -f docs/refactor-ui/modules/phase_1_docs_and_tokens.md` | passed | phase 1 token discovery doc exists |
| 2026-06-07 | `P002-phase-1-docs-and-tokens-discovery` | `rg -n "P002-phase-1-docs-and-tokens-discovery|Target Token Boundary|Required Characterization Tests|P003-phase-1-token-characterization-tests" docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/modules/phase_1_docs_and_tokens.md` | passed | token discovery and next prompt recommendation exist |
| 2026-06-07 | `P003-phase-1-token-characterization-tests` | `cd web && npm run test -- DesignTokens.test.ts TableLayoutTokens.test.ts` | expected-fail | Token/import CSS not implemented before P004 |
| 2026-06-07 | `P004-phase-1-token-implementation` | `cd web && npx vitest run DesignTokens.test.ts TableLayoutTokens.test.ts` | passed | CSS token bridge tests pass |
| 2026-06-07 | `MG-P004-phase-1-docs-and-tokens` | `git push origin refactor-ui` | passed | `541cd8d6` pushed |
| 2026-06-07 | `P005-phase-2-platform-stack-migration` | `cd web && npm run build` | passed | Build passed with generated CSS minifier warnings and bundle size warning |
| 2026-06-07 | `P005-phase-2-platform-stack-migration` | `cd web && npx vitest run HeroUIPlatformSmoke.test.tsx DesignTokens.test.ts TableLayoutTokens.test.ts App.test.tsx CommonMuiComponents.test.tsx MonthPicker.test.tsx` | passed | 26 tests passed |
| 2026-06-07 | `P005-phase-2-platform-stack-migration` | `cd web && npm ls react react-dom react-is @types/react @types/react-dom @heroui/react @heroui/styles tailwindcss @tailwindcss/vite --depth=0` | passed | Target versions installed |
| 2026-06-07 | `P005-phase-2-platform-stack-migration` | `rg -U -n '@import "tailwindcss";\n@import "@heroui/styles";' web/src web` | passed | CSS import order exists |
| 2026-06-07 | `MG-P005-phase-2-platform-stack` | `git push origin refactor-ui` | passed | `1eecabb9` pushed |
| 2026-06-07 | `P006-phase-3-state-permission-primitives` | `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 6 tests passed |
| 2026-06-07 | `P006-phase-3-state-permission-primitives` | `cd web && npm run build` | passed | Build passed with known generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P006-phase-3-state-permission-primitives` | `rg -n '@mui/' web/src/components/common/StatePanel.tsx web/src/components/common/PermissionNotice.tsx` | passed | No matches; command exits 1 when no MUI import exists |
| 2026-06-07 | `P006-phase-3-state-permission-primitives` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P006-phase-3-state-permission-primitives` | `git push origin refactor-ui` | passed | `ca962587` pushed |
| 2026-06-07 | `P007-phase-3-dialog-primitives` | `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 9 tests passed |
| 2026-06-07 | `P007-phase-3-dialog-primitives` | `cd web && npm run build` | failed-then-passed | First failed on optional maxWidth type boundary; fixed with NonNullable and build passed |
| 2026-06-07 | `P007-phase-3-dialog-primitives` | `if rg -n '@mui/' web/src/components/common/AppDialog.tsx web/src/components/common/ConfirmActionDialog.tsx; then exit 1; else exit 0; fi` | passed | No MUI imports in dialog primitives |
| 2026-06-07 | `P007-phase-3-dialog-primitives` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P007-phase-3-dialog-primitives` | `git push origin refactor-ui` | passed | `32841902` pushed |
| 2026-06-07 | `P008-phase-3-app-drawer-primitive` | `cd web && npx vitest run CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 10 tests passed |
| 2026-06-07 | `P008-phase-3-app-drawer-primitive` | `cd web && npm run build` | failed-then-passed | First failed because Drawer.Content does not accept style; moved CSS variable to Drawer.Dialog and build passed |
| 2026-06-07 | `P008-phase-3-app-drawer-primitive` | `if rg -n '@mui/' web/src/components/common/AppDrawer.tsx; then exit 1; else exit 0; fi` | passed | No MUI imports in AppDrawer |
| 2026-06-07 | `P008-phase-3-app-drawer-primitive` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P008-phase-3-app-drawer-primitive` | `git push origin refactor-ui` | passed | `1416b69a` pushed |
| 2026-06-07 | `P009-phase-3-file-dropzone-primitive` | `cd web && npx vitest run CommonMuiComponents.test.tsx TaxOffsetPage.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 27 tests passed; after removing custom Button render warning |
| 2026-06-07 | `P009-phase-3-file-dropzone-primitive` | `cd web && npm run build` | passed | Build passed with known generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P009-phase-3-file-dropzone-primitive` | `if rg -n '@mui/|mui-file-dropzone' web/src/components/common/FileDropzone.tsx web/src/test/TaxOffsetPage.test.tsx web/src/app/styles.css; then exit 1; else exit 0; fi` | passed | No MUI import or old class in P009 scope |
| 2026-06-07 | `P009-phase-3-file-dropzone-primitive` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P009-phase-3-file-dropzone-primitive` | `git push origin refactor-ui` | passed | `baba332d` pushed |
| 2026-06-07 | `P010-phase-3-page-layout-primitives` | `cd web && npx vitest run CommonMuiComponents.test.tsx App.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 25 tests passed |
| 2026-06-07 | `P010-phase-3-page-layout-primitives` | `cd web && npm run build` | passed | Build passed with known generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P010-phase-3-page-layout-primitives` | `if rg -n '@mui/' web/src/components/common/PageScaffold.tsx web/src/components/common/PageToolbar.tsx; then exit 1; else exit 0; fi` | passed | No MUI imports in page layout primitives |
| 2026-06-07 | `P010-phase-3-page-layout-primitives` | `if rg -n '@mui/' web/src/components/common --glob '!**/workbench/**'; then exit 1; else exit 0; fi` | passed | common primitives contain no MUI imports |
| 2026-06-07 | `MG-P010-phase-3-page-layout-primitives` | `git push origin refactor-ui` | passed | `d4135cf3` pushed |
| 2026-06-07 | `P011-phase-4-shell-discovery` | `test -f docs/refactor-ui/modules/phase_4_shell.md` | passed | Shell discovery doc exists |
| 2026-06-07 | `P011-phase-4-shell-discovery` | `rg -n "Phase 4 Boundary|Icon Decision|lucide-react|P012-phase-4-shell-icon-dependency|ReconciliationWorkbenchPage|--sidebar-width" docs/refactor-ui/modules/phase_4_shell.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | Key shell constraints recorded |
| 2026-06-07 | `P011-phase-4-shell-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P011-phase-4-shell-discovery` | `git push origin refactor-ui` | passed | `0c0e6b01` pushed |
| 2026-06-07 | `P012-phase-4-shell-icon-dependency` | `cd web && npx vitest run App.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 21 tests passed |
| 2026-06-07 | `P012-phase-4-shell-icon-dependency` | `cd web && npm run build` | passed | Build passed with known generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P012-phase-4-shell-icon-dependency` | `cd web && npm ls lucide-react --depth=0` | passed | lucide-react@1.17.0 |
| 2026-06-07 | `P012-phase-4-shell-icon-dependency` | `if rg -n '@mui/icons-material' web/src/app/pageRegistry.tsx web/src/test/App.test.tsx; then exit 1; else exit 0; fi` | passed | No MUI icon imports in registry/test |
| 2026-06-07 | `P012-phase-4-shell-icon-dependency` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P012-phase-4-shell-icon-dependency` | `git push origin refactor-ui` | passed | `a96087fc` pushed |
| 2026-06-07 | `P013-phase-4-shell-provider-runtime` | `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx` | failed-then-passed | First failed because removing full `MuiProviders` removed MUI X localization context/Chinese localeText; narrow date picker compat provider fixed it; 23 tests passed |
| 2026-06-07 | `P013-phase-4-shell-provider-runtime` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P013-phase-4-shell-provider-runtime` | `if rg -n '@mui/' web/src/app/App.tsx; then exit 1; else exit 0; fi` | passed | `App.tsx` has no direct MUI import; temporary MUI X date picker compat exists in `MuiDatePickerCompatProvider.tsx` |
| 2026-06-07 | `P013-phase-4-shell-provider-runtime` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P013-phase-4-shell-provider-runtime` | `git push origin refactor-ui` | passed | `b26db303` pushed |
| 2026-06-07 | `P014-phase-4-sidebar-topbar` | `cd web && npx vitest run App.test.tsx` | passed | 14 tests passed; includes compact sidebar characterization |
| 2026-06-07 | `P014-phase-4-sidebar-topbar` | `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 24 tests passed |
| 2026-06-07 | `P014-phase-4-sidebar-topbar` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P014-phase-4-sidebar-topbar` | `if rg -n '@mui/' web/src/components/shell/AppSidebar.tsx web/src/components/shell/AppTopBar.tsx; then exit 1; else exit 0; fi` | passed | AppSidebar/AppTopBar have no MUI imports; AppStatusIndicator still contains MUI for P015 |
| 2026-06-07 | `P014-phase-4-sidebar-topbar` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P014-phase-4-sidebar-topbar` | `git push origin refactor-ui` | passed | `3b124246` pushed |
| 2026-06-07 | `P015-phase-4-status-indicator` | `cd web && npx vitest run AppStatusIndicator.test.tsx` | failed-then-passed | HeroUI Popover Trigger changed hover target behavior; replaced with project-owned portal popover preserving old interaction; 2 tests passed |
| 2026-06-07 | `P015-phase-4-status-indicator` | `cd web && npx vitest run App.test.tsx AppStatusIndicator.test.tsx PageKeepAliveHost.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 24 tests passed |
| 2026-06-07 | `P015-phase-4-status-indicator` | `cd web && npm run build` | passed | Build passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P015-phase-4-status-indicator` | `if rg -n '@mui/' web/src/components/shell; then exit 1; else exit 0; fi` | passed | shell components have no MUI imports |
| 2026-06-07 | `P015-phase-4-status-indicator` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P015-phase-4-status-indicator` | `git push origin refactor-ui` | passed | `6f1ac42a` pushed |
| 2026-06-07 | `P016-phase-5-table-system-discovery` | `test -f docs/refactor-ui/modules/phase_5_table_system.md` | passed | Phase 5 table system discovery doc exists |
| 2026-06-07 | `P016-phase-5-table-system-discovery` | `rg -n "P016-phase-5-table-system-discovery|DataGrid-heavy|MUI Table Dense Finance Tables|DirectionTag|AmountCell|useFinanceTableSession|P017-phase-5-table-characterization-tests" docs/refactor-ui/modules/phase_5_table_system.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | Key table migration queue, layout rules and next prompt recorded |
| 2026-06-07 | `P016-phase-5-table-system-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P016-phase-5-table-system-discovery` | `git status --short --branch` | passed | 仅 P016 文档变更 |
| 2026-06-07 | `MG-P016-phase-5-table-system-discovery` | `git push origin refactor-ui` | passed | `599a3d15` pushed |
| 2026-06-07 | `P017-phase-5-table-characterization-tests` | `cd web && npx vitest run TableAlignmentStyles.test.ts` | expected-fail | 3 failures: missing `.finance-table`, missing column role cell block, missing `.finance-amount-cell` |
| 2026-06-07 | `P018-phase-5-finance-table-primitives` | `cd web && npx vitest run TableAlignmentStyles.test.ts` | passed | FinanceTable CSS contract passes |
| 2026-06-07 | `P018-phase-5-finance-table-primitives` | `cd web && npx vitest run TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P018-phase-5-finance-table-primitives` | `cd web && npm run build` | passed | Known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P018-phase-5-finance-table-primitives` | `if rg -n '@mui/' web/src/components/common; then exit 1; else exit 0; fi` | passed | common directory still has no MUI imports |
| 2026-06-07 | `P018-phase-5-finance-table-primitives` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P018-phase-5-finance-table-primitives` | `git push origin refactor-ui` | passed | `aa8cbccb` pushed |
| 2026-06-07 | `P019-phase-5-table-session-primitive` | `cd web && npx vitest run useFinanceTableSession.test.tsx` | passed | 4 tests passed |
| 2026-06-07 | `P019-phase-5-table-session-primitive` | `cd web && npx vitest run useFinanceTableSession.test.tsx useMuiDataGridPageSession.test.tsx TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx` | passed | 23 tests passed |
| 2026-06-07 | `P019-phase-5-table-session-primitive` | `cd web && npm run build` | passed | Known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P019-phase-5-table-session-primitive` | `if rg -n '@mui/' web/src/hooks/useFinanceTableSession.ts web/src/test/useFinanceTableSession.test.tsx web/src/components/common/FinanceTable.tsx; then exit 1; else exit 0; fi` | passed | New table session files have no MUI imports |
| 2026-06-07 | `P019-phase-5-table-session-primitive` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P019-phase-5-table-session-primitive` | `git push origin refactor-ui` | passed | `230ca704` pushed |
| 2026-06-07 | `P020-phase-5-app-health-table-pilot-discovery` | `rg -n "P020-phase-5-app-health-table-pilot-discovery|AppHealth Table Inventory|Inventory sources|Request performance|P021-phase-5-app-health-table-pilot-refactor" docs/refactor-ui/modules/phase_5_table_system.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | AppHealth pilot table inventory and next prompt recorded |
| 2026-06-07 | `P020-phase-5-app-health-table-pilot-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P020-phase-5-app-health-table-pilot-discovery` | `git push origin refactor-ui` | passed | `b9213d67` pushed |
| 2026-06-07 | `P021-phase-5-app-health-table-pilot-refactor` | `cd web && npx vitest run AppHealthOperationsPage.test.tsx` | failed-then-passed | First assertion used role table; HeroUI Table exposes role grid; updated tests to assert accessible grid names |
| 2026-06-07 | `P021-phase-5-app-health-table-pilot-refactor` | `cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx` | passed | 18 tests passed |
| 2026-06-07 | `P021-phase-5-app-health-table-pilot-refactor` | `cd web && npm run build` | passed | Known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P021-phase-5-app-health-table-pilot-refactor` | `if rg -n '@mui/material/(Table|TableBody|TableCell|TableContainer|TableHead|TableRow)' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi` | passed | AppHealth has no MUI table imports |
| 2026-06-07 | `P021-phase-5-app-health-table-pilot-refactor` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P021-phase-5-app-health-table-pilot-refactor` | `git push origin refactor-ui` | passed | `b47f0689` pushed |
| 2026-06-07 | `P022-phase-6-tax-offset-discovery` | `test -f docs/refactor-ui/modules/phase_6_tax_offset.md` | passed | TaxOffset module discovery doc exists |
| 2026-06-07 | `P022-phase-6-tax-offset-discovery` | `rg -n "P022-phase-6-tax-offset-discovery|Current MUI Inventory|User-visible Entrypoints|P023-phase-6-tax-offset-characterization-tests|MuiDialog-root" docs/refactor-ui/modules/phase_6_tax_offset.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | TaxOffset inventory and next prompt recorded |
| 2026-06-07 | `P022-phase-6-tax-offset-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P022-phase-6-tax-offset-discovery` | `git push origin refactor-ui` | passed | `c9b64d4d` pushed |
| 2026-06-07 | `P023-phase-6-tax-offset-characterization-tests` | `cd web && npx vitest run TaxOffsetPage.test.tsx` | expected-fail | 6 failures: TaxOffset still rendered MUI table/dialog surfaces before implementation |
| 2026-06-07 | `P024-P027-phase-6-tax-offset-ui-migration` | `cd web && npx vitest run TaxOffsetPage.test.tsx` | passed | 17 tests passed |
| 2026-06-07 | `P024-P027-phase-6-tax-offset-ui-migration` | `cd web && npx vitest run TaxOffsetPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 32 tests passed |
| 2026-06-07 | `P024-P027-phase-6-tax-offset-ui-migration` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P024-P027-phase-6-tax-offset-ui-migration` | `rg -n '@mui/' web/src/pages/TaxOffsetPage.tsx web/src/components/tax` | passed | No TaxOffset-scope MUI imports |
| 2026-06-07 | `P024-P027-phase-6-tax-offset-ui-migration` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P027-phase-6-tax-offset` | `git push origin refactor-ui` | passed | `4c7a99f5` pushed |
| 2026-06-07 | `P028-phase-6-app-health-discovery` | `test -f docs/refactor-ui/modules/phase_6_app_health.md` | passed | AppHealth discovery doc exists |
| 2026-06-07 | `P028-phase-6-app-health-discovery` | `rg -n "P028-phase-6-app-health-discovery\|Current MUI Inventory\|Already Migrated Surfaces\|User-visible Entrypoints\|P029-phase-6-app-health-characterization-tests\|RefreshIcon" docs/refactor-ui/modules/phase_6_app_health.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | AppHealth inventory and next prompt recorded |
| 2026-06-07 | `P028-phase-6-app-health-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P028-phase-6-app-health-discovery` | `git status --short --branch` | passed | 仅 P028 文档变更 |
| 2026-06-07 | `MG-P028-phase-6-app-health-discovery` | `git push origin refactor-ui` | passed | `1a806eeb` pushed |
| 2026-06-07 | `P029-phase-6-app-health-characterization-tests` | `cd web && npx vitest run AppHealthOperationsPage.test.tsx` | expected-fail | 3 failures: missing `app-health-page`; permission/error notices still `.MuiAlert-root` |
| 2026-06-07 | `P029-phase-6-app-health-characterization-tests` | `git diff --check` | passed | Covered by P030 cumulative diff check |
| 2026-06-07 | `P030-phase-6-app-health-page-shell` | `cd web && npx vitest run AppHealthOperationsPage.test.tsx` | passed | 4 tests passed |
| 2026-06-07 | `P030-phase-6-app-health-page-shell` | `cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 19 tests passed |
| 2026-06-07 | `P030-phase-6-app-health-page-shell` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P030-phase-6-app-health-page-shell` | `if rg -n '@mui/' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi` | passed | AppHealth page has no MUI imports |
| 2026-06-07 | `P030-phase-6-app-health-page-shell` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P030-phase-6-app-health` | `git push origin refactor-ui` | passed | `814ad25c` pushed |
| 2026-06-07 | `P031-phase-6-import-pages-discovery` | `test -f docs/refactor-ui/modules/phase_6_import_pages.md` | passed | Import pages discovery doc exists |
| 2026-06-07 | `P031-phase-6-import-pages-discovery` | `rg -n "P031-phase-6-import-pages-discovery\|Current MUI Inventory\|User-visible Entrypoints\|P032-phase-6-import-pages-characterization-tests\|DataGrid\|银行账户冲突确认" docs/refactor-ui/modules/phase_6_import_pages.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | Import pages inventory and next prompt recorded |
| 2026-06-07 | `P031-phase-6-import-pages-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P031-phase-6-import-pages-discovery` | `git status --short --branch` | passed | 仅 P031 文档变更 |
| 2026-06-07 | `MG-P031-phase-6-import-pages-discovery` | `git push origin refactor-ui` | passed | `adc8ce62` pushed |
| 2026-06-07 | `P032-phase-6-import-pages-characterization-tests` | `cd web && npx vitest run ImportCenterPage.test.tsx` | expected-fail | 7 failures: import shell, audit cards and notice roots still MUI |
| 2026-06-07 | `P033-phase-6-import-pages-shell-forms` | `cd web && npx vitest run ImportCenterPage.test.tsx` | expected-fail | 4 failures remain, all preview tables still MUI DataGrid; shell/forms/cards/notices/dialog failures cleared |
| 2026-06-07 | `P033-phase-6-import-pages-shell-forms` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P034-phase-6-import-pages-preview-tables` | `cd web && npx vitest run ImportCenterPage.test.tsx` | expected-fail | 17 passed, 2 expected failures remain; both failures are detail tabs still MUI Tabs |
| 2026-06-07 | `P035-phase-6-import-pages-detail-tabs` | `cd web && npx vitest run ImportCenterPage.test.tsx` | passed | 19 tests passed; stderr still includes known HeroUI Tooltip focusable warning from existing truncated text trigger behavior |
| 2026-06-07 | `P035-phase-6-import-pages-detail-tabs` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P035-phase-6-import-pages-detail-tabs` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P035-phase-6-import-pages-detail-tabs` | `if rg -n '@mui/|Mui[A-Z]|MuiDataGrid|DataGrid|GridColDef|useMuiDataGrid' web/src/components/imports web/src/pages/imports; then exit 1; else exit 0; fi` | passed | Import pages runtime scope has no MUI/DataGrid/session hook residue |
| 2026-06-07 | `P035-phase-6-import-pages-detail-tabs` | `if rg -n '@mui/' web/src/test/ImportCenterPage.test.tsx; then exit 1; else exit 0; fi` | passed | Import tests have no MUI imports; negative MUI class assertions remain by design |
| 2026-06-07 | `P035-phase-6-import-pages-detail-tabs` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P035-phase-6-import-pages` | `git push origin refactor-ui` | passed | Commit `9e3624a0` pushed |
| 2026-06-07 | `P036-phase-6-cost-statistics-discovery` | `test -f docs/refactor-ui/modules/phase_6_cost_statistics.md` | passed | CostStatistics module discovery doc exists |
| 2026-06-07 | `P036-phase-6-cost-statistics-discovery` | `rg -n "P036-phase-6-cost-statistics-discovery\|Current MUI Inventory\|User-visible Entrypoints\|P037-phase-6-cost-statistics-characterization-tests" docs/refactor-ui/modules/phase_6_cost_statistics.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | CostStatistics inventory and next prompt recorded |
| 2026-06-07 | `P037-phase-6-cost-statistics-characterization-tests` | `cd web && npx vitest run CostStatisticsPage.test.tsx` | expected-fail | 11 passed, 4 expected failures; all failures are project/FinanceTable assertions against current MUI DataGrid tables |
| 2026-06-07 | `P038-phase-6-cost-statistics-table-migration` | `cd web && npx vitest run CostStatisticsPage.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P038-phase-6-cost-statistics-table-migration` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P038-phase-6-cost-statistics-table-migration` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P038-phase-6-cost-statistics-table-migration` | `if rg -n '@mui/|Mui[A-Z]|MuiDataGrid|DataGrid|GridColDef|useMuiDataGrid' web/src/pages/CostStatisticsPage.tsx web/src/components/cost-statistics; then exit 1; else exit 0; fi` | passed | CostStatistics direct runtime scope has no MUI/DataGrid/session residue |
| 2026-06-07 | `P038-phase-6-cost-statistics-table-migration` | `if rg -n 'cost-data-grid-shell|\.cost-data-grid-shell|\.MuiDataGrid' web/src/components/cost-statistics web/src/pages/CostStatisticsPage.tsx web/src/test/CostStatisticsPage.test.tsx; then exit 1; else exit 0; fi` | passed | CostStatistics component/test scope has no cost DataGrid CSS or DataGrid class residue |
| 2026-06-07 | `P038-phase-6-cost-statistics-table-migration` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P038-phase-6-cost-statistics-table-migration` | `git push origin refactor-ui` | passed | Commit `4baffcff` pushed |
| 2026-06-07 | `P040-phase-6-bank-details-discovery` | `test -f docs/refactor-ui/modules/phase_6_bank_details.md` | passed | BankDetails module discovery doc exists |
| 2026-06-07 | `P040-phase-6-bank-details-discovery` | `rg -n "P040-phase-6-bank-details-discovery\|Current MUI Inventory\|User-visible Entrypoints\|P041-phase-6-bank-details-characterization-tests" docs/refactor-ui/modules/phase_6_bank_details.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | BankDetails inventory and next prompt recorded |
| 2026-06-07 | `P040-phase-6-bank-details-discovery` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P040-phase-6-bank-details-discovery` | `git status --short --branch` | passed | 仅 P040 文档变更 |
| 2026-06-07 | `P041-phase-6-bank-details-characterization-tests` | `cd web && npx vitest run BankDetailsPage.test.tsx -t "selecting account and filters request accounts and transactions with the same date range"` | passed | Date input test stabilized through input+blur event path |
| 2026-06-07 | `P041-phase-6-bank-details-characterization-tests` | `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx` | expected-fail | 47 passed, 5 expected failures; all failures are project primitive contracts against current MUI runtime/CSS |
| 2026-06-07 | `P041-phase-6-bank-details-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P041-phase-6-bank-details-characterization-tests` | `git status --short --branch` | passed | P041 tests and docs changed |
| 2026-06-07 | `P042-phase-6-bank-details-shell-toolbar-dates` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P042-phase-6-bank-details-shell-toolbar-dates` | `cd web && npx vitest run BankDetailsPage.test.tsx -t "loads all accounts\|requests the current year\|renders accounts\|uses Chinese labels\|selecting account and filters\|exports all banks"` | passed | 6 passed / 32 skipped |
| 2026-06-07 | `P042-phase-6-bank-details-shell-toolbar-dates` | `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx` | expected-fail | 47 passed, 5 expected failures; remaining failures assigned to P043/P044/P045 |
| 2026-06-07 | `P042-phase-6-bank-details-shell-toolbar-dates` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P042-phase-6-bank-details-shell-toolbar-dates` | `if rg -n '@mui/material/(Popover\|TextField\|ToggleButton\|ToggleButtonGroup)\|@mui/x-date-pickers\|dayjs\|RuleIcon\|exportMenuAnchorEl' web/src/pages/BankDetailsPage.tsx; then exit 1; else exit 0; fi` | passed | Toolbar/date/export/search P042 MUI residues removed; `MenuList` remains for P044 TypeCell |
| 2026-06-07 | `P043-phase-6-bank-details-transaction-table` | `if rg -n '@mui/material/(Table\|TableBody\|TableCell\|TableContainer\|TableHead\|TablePagination\|TableRow)' web/src/pages/BankDetailsPage.tsx; then exit 1; else exit 0; fi` | passed | BankDetails page no longer imports MUI Table/TablePagination primitives |
| 2026-06-07 | `P043-phase-6-bank-details-transaction-table` | `cd web && npx vitest run BankDetailsPage.test.tsx -t "交易流水\|pagination\|searches current account\|loads all accounts\|uses Chinese labels"` | passed | 4 passed / 34 skipped |
| 2026-06-07 | `P043-phase-6-bank-details-transaction-table` | `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx` | expected-fail | 48 passed, 4 expected failures; remaining failures assigned to P044/P045 |
| 2026-06-07 | `P043-phase-6-bank-details-transaction-table` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P043-phase-6-bank-details-transaction-table` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P043-phase-6-bank-details-transaction-table` | `if rg -n '@mui/material/(Table\|TableBody\|TableCell\|TableContainer\|TableHead\|TablePagination\|TableRow)\|bank-transaction-pagination\\.MuiTablePagination\|bank-transaction-table .*MuiTable\|\\.bank-transaction-table .*MuiTable' web/src/pages/BankDetailsPage.tsx web/src/app/styles.css; then exit 1; else exit 0; fi` | passed | Transaction table and pagination MUI table residue removed |
| 2026-06-07 | `P044-phase-6-bank-details-category-popovers` | `if rg -n '@mui/material/(Popper\|MenuList\|Menu\|Tooltip)\|@mui/icons-material/FilterListOutlined\|@mui/material/(ClickAwayListener\|IconButton\|List\|ListItem\|ListItemButton\|ListItemText\|Paper)' web/src/pages/BankDetailsPage.tsx web/src/features/bankDetails/BankCategoryTag.tsx; then exit 1; else exit 0; fi` | passed | Category/tooltip P044 MUI residues removed |
| 2026-06-07 | `P044-phase-6-bank-details-category-popovers` | `cd web && npx vitest run BankDetailsPage.test.tsx -t "category\|internal transfer\|manual classification\|needs-confirmation\|external turnover\|targets project table\|dense three-column"` | expected-fail | P044 category/tag/tooltip/TypeCell behavior passed; only P045 drawer source assertion failed |
| 2026-06-07 | `P044-phase-6-bank-details-category-popovers` | `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx` | expected-fail | 49 passed, 3 expected failures; remaining failures assigned to P045 |
| 2026-06-07 | `P044-phase-6-bank-details-category-popovers` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P044-phase-6-bank-details-category-popovers` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P044-phase-6-bank-details-category-popovers` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P045-phase-6-bank-details-auto-tag-drawer` | `cd web && npx vitest run AutoTagRulesDrawer.test.tsx` | passed | 14 tests passed |
| 2026-06-07 | `P045-phase-6-bank-details-auto-tag-drawer` | `cd web && npx vitest run BankDetailsPage.test.tsx AutoTagRulesDrawer.test.tsx` | passed | 52 tests passed |
| 2026-06-07 | `P045-phase-6-bank-details-auto-tag-drawer` | `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx` | passed | 15 tests passed |
| 2026-06-07 | `P045-phase-6-bank-details-auto-tag-drawer` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P045-phase-6-bank-details-auto-tag-drawer` | `if rg -n '@mui\|Mui\|<Button\|<Chip\|<Stack\|<Typography' web/src/pages/BankDetailsPage.tsx web/src/features/bankDetails/AutoTagRulesDrawer.tsx web/src/features/bankDetails/BankCategoryTag.tsx; then exit 1; else exit 0; fi` | passed | BankDetails runtime scope has no direct MUI imports/usages |
| 2026-06-07 | `P045-phase-6-bank-details-auto-tag-drawer` | `if rg -n 'bank-details-page[^\n]*Mui\|bank-[^\n]*Mui\|Mui[^\n]*bank-\|bank-auto-tag[^\n]*Mui\|Mui[^\n]*bank-auto-tag' web/src/app/styles.css; then exit 1; else exit 0; fi` | passed | BankDetails CSS scope has no MUI selector residue |
| 2026-06-07 | `P045-phase-6-bank-details-auto-tag-drawer` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `MG-P045-phase-6-bank-details` | `git push origin refactor-ui` | passed | Commit `9a0b74ea` pushed |
| 2026-06-07 | `P046-phase-6-pending-invoices-discovery` | `test -f docs/refactor-ui/modules/phase_6_pending_invoices.md` | passed | PendingInvoices module discovery doc exists |
| 2026-06-07 | `P046-phase-6-pending-invoices-discovery` | `rg -n "P046-phase-6-pending-invoices-discovery\|Current MUI Inventory\|User-visible Entrypoints\|P047-phase-6-pending-invoices-characterization-tests" docs/refactor-ui/modules/phase_6_pending_invoices.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md` | passed | PendingInvoices inventory and next prompt recorded |
| 2026-06-07 | `P047-phase-6-pending-invoices-characterization-tests` | `cd web && npx vitest run PendingInvoicesPage.test.tsx` | expected-fail | 14 passed, 1 expected failure. Failure lists 9 pending invoice files still importing `@mui/*` and missing PageScaffold/PageToolbar/FinanceTable/AppDrawer/AppDialog targets |
| 2026-06-07 | `P047-phase-6-pending-invoices-characterization-tests` | `git diff --check` | passed | 无 whitespace error |
| 2026-06-07 | `P047-phase-6-pending-invoices-characterization-tests` | `git status --short --branch` | passed | P047 test and docs changed |
| 2026-06-07 | `P048-phase-6-pending-invoices-page-shell-toolbar` | `cd web && npx vitest run PendingInvoicesPage.test.tsx -t "renders project four-zone table contract\|shows income rule-group filters\|keeps row status actions available\|targets project primitives"` | expected-fail | Page shell/toolbar targets cleared; source contract now lists only 8 table/drawer/dialog files |
| 2026-06-07 | `P048-phase-6-pending-invoices-page-shell-toolbar` | `cd web && npx vitest run PendingInvoicesPage.test.tsx` | expected-fail | 14 passed, 1 expected source-level failure remains for P049-P052 |
| 2026-06-07 | `P048-phase-6-pending-invoices-page-shell-toolbar` | `cd web && npm run build` | passed | Known HeroUI/Tailwind CSS minifier warnings and chunk size warning |
| 2026-06-07 | `P048-phase-6-pending-invoices-page-shell-toolbar` | `if rg -n '@mui/\|MuiButton-endIcon\|MuiToggleButton-root\|KeyboardArrowDownOutlinedIcon\|TablePagination\|ToggleButton\|ToggleButtonGroup' web/src/pages/PendingInvoicesPage.tsx; then exit 1; else exit 0; fi` | passed | PendingInvoices page shell has no P048 MUI residue |
| 2026-06-07 | `P048-phase-6-pending-invoices-page-shell-toolbar` | `git diff --check` | passed | 无 whitespace error |

## Push Log

| Date | MG | Branch | Commit | Result |
| --- | --- | --- | --- | --- |
| 2026-06-07 | `MG-P000-docs-bootstrap` | `refactor-ui` | `52f4520f` | pushed |
| 2026-06-07 | `MG-P001-baseline-doc-gap-fill` | `refactor-ui` | `8f3daae8` | pushed |
| 2026-06-07 | `MG-P004-phase-1-docs-and-tokens` | `refactor-ui` | `541cd8d6` | pushed |
| 2026-06-07 | `MG-P005-phase-2-platform-stack` | `refactor-ui` | `1eecabb9` | pushed |
| 2026-06-07 | `MG-P006-phase-3-state-permission-primitives` | `refactor-ui` | `ca962587` | pushed |
| 2026-06-07 | `MG-P007-phase-3-dialog-primitives` | `refactor-ui` | `32841902` | pushed |
| 2026-06-07 | `MG-P008-phase-3-app-drawer-primitive` | `refactor-ui` | `1416b69a` | pushed |
| 2026-06-07 | `MG-P009-phase-3-file-dropzone-primitive` | `refactor-ui` | `baba332d` | pushed |
| 2026-06-07 | `MG-P010-phase-3-page-layout-primitives` | `refactor-ui` | `d4135cf3` | pushed |
| 2026-06-07 | `MG-P011-phase-4-shell-discovery` | `refactor-ui` | `0c0e6b01` | pushed |
| 2026-06-07 | `MG-P012-phase-4-shell-icon-dependency` | `refactor-ui` | `a96087fc` | pushed |
| 2026-06-07 | `MG-P013-phase-4-shell-provider-runtime` | `refactor-ui` | `b26db303` | pushed |
| 2026-06-07 | `MG-P014-phase-4-sidebar-topbar` | `refactor-ui` | `3b124246` | pushed |
| 2026-06-07 | `MG-P015-phase-4-status-indicator` | `refactor-ui` | `6f1ac42a` | pushed |
| 2026-06-07 | `MG-P016-phase-5-table-system-discovery` | `refactor-ui` | `599a3d15` | pushed |
| 2026-06-07 | `MG-P018-phase-5-finance-table-primitives` | `refactor-ui` | `aa8cbccb` | pushed |
| 2026-06-07 | `MG-P019-phase-5-table-session-primitive` | `refactor-ui` | `230ca704` | pushed |
| 2026-06-07 | `MG-P020-phase-5-app-health-table-pilot-discovery` | `refactor-ui` | `b9213d67` | pushed |
| 2026-06-07 | `MG-P021-phase-5-app-health-table-pilot-refactor` | `refactor-ui` | `b47f0689` | pushed |
| 2026-06-07 | `MG-P022-phase-6-tax-offset-discovery` | `refactor-ui` | `c9b64d4d` | pushed |
| 2026-06-07 | `MG-P027-phase-6-tax-offset` | `refactor-ui` | `4c7a99f5` | pushed |
| 2026-06-07 | `MG-P028-phase-6-app-health-discovery` | `refactor-ui` | `1a806eeb` | pushed |
| 2026-06-07 | `MG-P030-phase-6-app-health` | `refactor-ui` | `814ad25c` | pushed |
| 2026-06-07 | `MG-P031-phase-6-import-pages-discovery` | `refactor-ui` | `adc8ce62` | pushed |
| 2026-06-07 | `MG-P035-phase-6-import-pages` | `refactor-ui` | `9e3624a0` | pushed |
| 2026-06-07 | `MG-P038-phase-6-cost-statistics-table-migration` | `refactor-ui` | `4baffcff` | pushed |
| 2026-06-07 | `P040-phase-6-bank-details-discovery` | `refactor-ui` | `e720504d` | pushed |
| 2026-06-07 | `MG-P045-phase-6-bank-details` | `refactor-ui` | `9a0b74ea` | pushed |
| 2026-06-07 | `MG-P072-phase-6-output-invoice-collections` | `refactor-ui` | `60f9593b` | pushed |
| 2026-06-07 | `P073-phase-6-no-oa-bank-batches-discovery` | `refactor-ui` | `ac9a18ac` | pushed |
| 2026-06-07 | `P089-phase-6-turnover-ledger-tag-and-closure-drawers` | `refactor-ui` | `3675bed3` | pushed |
| 2026-06-07 | `P090-phase-6-turnover-ledger-extra-drawer` | `refactor-ui` | `30fde5ad` | pushed |
| 2026-06-07 | `P091-phase-6-turnover-ledger-export-dialog-feedback-closeout` | `refactor-ui` | `8a3eb3cb` | pushed |
| 2026-06-07 | `MG-P091-phase-6-turnover-ledger` | `refactor-ui` | `392a5d41` | pushed |
| 2026-06-07 | `P092-phase-6-etc-tickets-discovery` | `refactor-ui` | `5267a7a2` | pushed |
| 2026-06-07 | `P093-phase-6-etc-tickets-characterization-tests` | `refactor-ui` | `1d0773cc` | pushed |
| 2026-06-07 | `P094-phase-6-etc-tickets-shell-filters-lists` | `refactor-ui` | `47a2d993` | pushed |
| 2026-06-07 | `P095-phase-6-etc-tickets-upload-and-source-panels` | `refactor-ui` | `a58e74c3` | pushed |
| 2026-06-07 | `P096-phase-6-etc-tickets-reconciliation-table` | `refactor-ui` | `64341c3c` | pushed |
| 2026-06-07 | `P097-phase-6-etc-tickets-detail-and-invoice-tables` | `refactor-ui` | `35d55842` | pushed |
| 2026-06-07 | `P098-phase-6-etc-tickets-dialogs-oa-feedback-closeout` | `refactor-ui` | `071e3f98` | pushed |
| 2026-06-07 | `MG-P098-phase-6-etc-tickets` | `refactor-ui` | `47e93000` | pushed |
| 2026-06-07 | `P099-phase-6-settings-discovery` | `refactor-ui` | `80153649` | pushed |
| 2026-06-07 | `P100-phase-6-settings-characterization-tests` | `refactor-ui` | `6010cad6` | pushed |
| 2026-06-07 | `P101-phase-6-settings-shell-navigation` | `refactor-ui` | `7e615ac6` | pushed |
| 2026-06-07 | `P102-phase-6-settings-projects-and-bank-accounts` | `refactor-ui` | `ea55bc7a` | pushed |
| 2026-06-07 | `P103-phase-6-settings-access-and-pending-tags` | `refactor-ui` | `140ed386` | pushed |
| 2026-06-07 | `P104-phase-6-settings-oa-rules-and-data-reset` | `refactor-ui` | `c43685b9` | pushed |
| 2026-06-07 | `P105-phase-6-settings-oa-manual-search-import-table` | `refactor-ui` | `6648341e` | pushed |
| 2026-06-07 | `P106-phase-6-settings-closeout` | `refactor-ui` | `ad8b3d40` | pushed |
| 2026-06-07 | `MG-P106-phase-6-settings` | `refactor-ui` | `2a30a7b0` | pushed |
| 2026-06-07 | `P107-phase-7-mui-containment-discovery` | `refactor-ui` | `f135e4bd` | pushed |
| 2026-06-07 | `P108-phase-7-month-picker-characterization-tests` | `refactor-ui` | `eb6049ec` | pushed |
| 2026-06-07 | `P109-phase-7-month-picker-and-date-compat` | `refactor-ui` | `f8799863` | pushed |
| 2026-06-07 | `P110-phase-7-datagrid-session-cleanup` | `refactor-ui` | `a3fff0da` | pushed |
| 2026-06-07 | `P111-phase-7-test-provider-containment` | `refactor-ui` | `b63d25ca` | pushed |
| 2026-06-07 | `P112-phase-7-global-css-containment` | `refactor-ui` | `320a8286` | pushed |
| 2026-06-07 | `P113-phase-7-final-no-mui-contract` | `refactor-ui` | `fcdbb7b4` | pushed |
| 2026-06-07 | `MG-P113-phase-7-mui-containment` | `refactor-ui` | `dba7f63d` | pushed |
| 2026-06-07 | `P074-phase-6-no-oa-bank-batches-characterization-tests` | `refactor-ui` | `4a958ce8` | pushed |
| 2026-06-07 | `P075-phase-6-no-oa-bank-batches-page-shell-filters` | `refactor-ui` | `1c872bfe` | pushed |
| 2026-06-07 | `P076-phase-6-no-oa-bank-batches-label-rails` | `refactor-ui` | `379d24cd` | pushed |
| 2026-06-07 | `P077-phase-6-no-oa-bank-batches-transaction-region` | `refactor-ui` | `00e0ca44` | pushed |
| 2026-06-07 | `P078-phase-6-no-oa-bank-batches-overlays-feedback` | `refactor-ui` | `87b92e20` | pushed |
| 2026-06-07 | `MG-P078-phase-6-no-oa-bank-batches` | `refactor-ui` | `f5736c0c` | pushed |
| 2026-06-07 | `P079-phase-6-batch-accounting-discovery` | `refactor-ui` | `e113d6e6` | pushed |
| 2026-06-07 | `P080-phase-6-batch-accounting-characterization-tests` | `refactor-ui` | `cae1d091` | pushed |
| 2026-06-07 | `P081-phase-6-batch-accounting-page-shell-filters` | `refactor-ui` | `64aa7da3` | pushed |
| 2026-06-07 | `P082-phase-6-batch-accounting-bank-list-and-summary` | `refactor-ui` | `7dd51d20` | pushed |
| 2026-06-07 | `P083-phase-6-batch-accounting-oa-table` | `refactor-ui` | `1ae9068d` | pushed |
| 2026-06-07 | `P084-phase-6-batch-accounting-overlays-feedback` | `refactor-ui` | `ef41572f` | pushed |
| 2026-06-07 | `MG-P084-phase-6-batch-accounting` | `refactor-ui` | `5747bf90` | pushed |
| 2026-06-07 | `P085-phase-6-turnover-ledger-discovery` | `refactor-ui` | `5747bf90` | pushed |
| 2026-06-07 | `P086-phase-6-turnover-ledger-characterization-tests` | `refactor-ui` | `e8b462a7` | pushed |
| 2026-06-07 | `P087-phase-6-turnover-ledger-page-shell-tabs-summary` | `refactor-ui` | `e9a464b5` | pushed |
| 2026-06-07 | `P088-phase-6-turnover-ledger-grouped-table` | `refactor-ui` | `db426030` | pushed |
| 2026-06-07 | `P114-phase-8-full-verification` | `refactor-ui` | `48053007` | pushed |
