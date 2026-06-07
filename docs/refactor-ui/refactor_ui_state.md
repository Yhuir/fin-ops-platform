# Refactor UI State

本文档是 `refactor-ui` 分支 UI 重构的状态机事实源。每次执行 prompt 或 cumulative MG 后必须更新。

## Current Phase

- Phase: `phase_6_page_batches`
- Status: `in_progress`
- Branch: `refactor-ui`
- Last Updated: `2026-06-07`
- Current Prompt ID: `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell`
- Current MG ID: `MG-P052-phase-6-pending-invoices`

## Global Invariants

| Invariant | Status | Evidence |
| --- | --- | --- |
| Backend untouched | yes | 当前 AppHealth discovery 切片只修改重构文档 |
| API contract untouched | yes | 未修改 AppHealth API client contract 或 backend |
| Read model / worker untouched | yes | 未修改 read model、worker 或 queue |
| Reconciliation workbench internals frozen | yes | 当前未改 `ReconciliationWorkbenchPage` 或 `web/src/components/workbench/*` |
| Non-workbench MUI additions | none | InputInvoiceUsage page shell now has no page-level MUI; P056 will clear main table/expandable cell |
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
| `phase_6_page_batches` | `in_progress` | 2026-06-07 |  | `pending` | PendingInvoices MG-P052 verified and pushed；next P053 input invoice usage discovery |
| `phase_7_mui_containment` | `pending` |  |  |  | 非关联台无 MUI，关联台隔离 |
| `phase_8_full_verification` | `pending` |  |  |  | 全量验证 |
| `phase_9_closeout` | `pending` |  |  |  | 文档收口和后续计划 |

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

- Scope: phase 6 input invoice usage main table/expandable cell prompt generated after P055 page shell migration。
- Files touched:
  - `docs/refactor-ui/refactor_ui_prompt.md`
  - `docs/refactor-ui/refactor_ui_state.md`
  - `docs/refactor-ui/modules/phase_6_input_invoice_usage.md`
  - `web/src/pages/InputInvoiceUsagePage.tsx`
  - `web/src/app/styles.css`
- Verification run: P055 focused tests expected-fail, full module tests expected-fail, page grep passed, build passed。
- Failures: expected source-level no-MUI failures remain for unimplemented table/filter/drawer migration。
- Next action: 执行 `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell`。

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
| page batches | `in_progress` | `P056-phase-6-input-invoice-usage-main-table-and-expandable-cell` | InputInvoiceUsage P055 page shell verified as expected-fail；next main table and expandable cell |

## Verification Log

| Date | Prompt / MG | Command | Result | Notes |
| --- | --- | --- | --- | --- |
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
