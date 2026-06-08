# Phase 8 Full Verification

本文档记录 `P114-phase-8-full-verification` 的最终验证事实。它不替代 `refactor_ui_state.md`，只保留后续 closeout 和复盘需要查阅的验证细节。

## Scope

- 分支：`refactor-ui`
- 栈目标：React 19 + HeroUI v3 + Tailwind CSS v4。
- 边界：
  - 不改 backend、API contract、read model、worker、权限语义或业务状态机。
  - 不迁移冻结关联台内部工作区：`web/src/pages/ReconciliationWorkbenchPage.tsx` 和 `web/src/components/workbench/*`。
  - 非关联台 runtime 不允许再引入 MUI、MUI X DataGrid、MUI X date picker、app-level MUI provider/theme。

## Final Verification Matrix

| Check | Command | Result | Notes |
| --- | --- | --- | --- |
| Non-workbench MUI containment | final `rg` chain for `@mui/`, `Mui*`, DataGrid/date-picker/provider/theme excluding frozen workbench, tests and documented `styles.css` containment | passed | No non-workbench runtime MUI residue found |
| Full frontend tests | `cd web && npx vitest run` | passed | 63 test files / 613 tests |
| Build | `cd web && npm run build` | passed | `tsc -b` and Vite build passed |
| Whitespace | `git diff --check` | passed | No whitespace errors |
| Settings + workbench targeted regression | `cd web && npx vitest run SettingsPage.test.tsx WorkbenchSelection.test.tsx` | passed | 57 tests |
| Workbench exception modal regression | `cd web && npx vitest run WorkbenchExceptionModal.test.tsx` | passed | 6 tests |
| No-OA/session regression | `cd web && npx vitest run NoOaBankBatchPage.test.tsx SessionGate.test.tsx` | passed | 24 tests |

## Issues Found During P114

P114 intentionally ran broad verification after phase 7 containment. The first full-test attempts exposed stale test contracts and one real React 19 runtime issue:

1. `SettingsBankAccountsSection` and `SettingsAccessAccountsSection` read `event.currentTarget.value` inside deferred updater callbacks. Under React 19, `currentTarget` can become `null` by the time the updater runs. The value is now captured before the updater is passed.
2. `WorkbenchSelection.test.tsx` still expected old MUI/DataGrid edit semantics for settings tables. The test now verifies the native table/input contract.
3. `WorkbenchExceptionModal.test.tsx` asserted data-anomaly preview content before async preview loading completed. The test now waits for the preview text.
4. `NoOaBankBatchPage.test.tsx` used an `人工成本/工资` path that is not present in the current unsubmitted bucket. The keyboard test now uses the visible `福利/过节费` path.
5. `SessionGate.test.tsx` asserted a workbench row/person text after session bootstrap. The test now asserts the user-visible app shell/navigation is rendered after `/api/session/me`.

## Known Warnings

These warnings were observed during verification and are not introduced as phase 8 blockers:

- React Router v7 future-flag warnings from tests using React Router v6.
- Node `--localstorage-file` warning emitted by the test environment.
- HeroUI/Tailwind CSS minifier warnings around generated `:is()` / `:not(:is())` selectors in `npm run build`.
- Vite chunk size warning for the current single-bundle app.
- React Aria `<Focusable> child must be focusable` warnings in import page tests; tests still pass and the warning should be handled as a future accessibility cleanup slice, not as a MUI migration blocker.

## Remaining Risk

- Browser/manual visual smoke was not run in P114. The automated suite covers major routes and interactions, but phase 9 should record this as a residual risk unless a browser smoke is added before closeout.
- Bundle splitting remains outside the UI migration scope. The current build passes but reports chunk-size warning.
- Workbench internal MUI was removed by the subsequent workbench-specific migration and P116 post-closeout audit. Historical phase 8 notes remain useful for understanding why P114 did not treat workbench MUI as a blocker at that moment.

## Next Prompt

Generate and execute one closeout prompt only:

- `P115-phase-9-closeout`

## PV-028 App-wide Smoothness Audit

- Prompt ID: `PV-028-app-wide-smoothness-audit`
- Status: `verified`
- Runtime implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

### Completed Premium Visual Scope

The premium visual pass now has verified module records for:

- Bank Details premium sample.
- Tax Offset.
- App Health / System Status.
- Import pages family.
- Cost Statistics.
- Pending Invoices.
- Input Invoice Usage.
- OA Pending Payments.
- Output Invoice Collections.
- No-OA Bank Batches.
- Batch Accounting.
- Turnover Ledger.
- ETC Tickets.
- Settings.

### Audit Results

- Non-workbench runtime MUI/Emotion scan: passed.
- Removed page-cache/snapshot architecture guard: passed.
- App-wide premium CSS contract coverage exists for the major page families, including motion tokens, table row rhythm, stable tags, tabular amounts and key drawer/dialog/table controls.
- Build/test warnings known from earlier phases remain non-blocking:
  - React Router v7 future-flag test warnings.
  - Node localstorage-file warning in the test environment.
  - HeroUI/Tailwind CSS minifier warnings for generated selectors.
  - Current Vite CSS/JS chunk size warnings.

### Motion And Smoothness Findings

- Remaining raw animation declarations are mostly expected loading/spinner/status animations. They are not route transitions and do not block navigation.
- Remaining fixed-duration transition declarations fall into three groups:
  - Shell/status tooltip and status indicators that predate the premium visual pass.
  - Frozen or historical workbench/zone styling that is outside this non-workbench premium scope.
  - Older ETC/Settings declarations that are covered by later premium override rules using motion tokens.
- No route-level decorative page transition was found in the scan.
- No `transition: all` risk was found in current scan output.

### Final MG Requirements

The final merge gate should not expand into another visual redesign. It should verify and close:

- Full frontend targeted tests for all premium-touched pages.
- Type check and production build.
- Non-workbench runtime MUI/Emotion guard.
- Removed page-cache/snapshot guard.
- Diff/scope/untracked-file check.
- Browser smoke coverage for the representative premium surfaces already used in this run:
  - Bank Details sample.
  - ETC Tickets.
  - Settings.
- Documentation state consistency:
  - `premium_visual_master_state.md` current slice and push log.
  - `premium_visual_prompt.md` completed prompt and final MG prompt.
  - Module docs for the latest slices.

### Backlog, Not MG Blockers

- Global shell/status tooltip colors and timings can be folded into a future shell-specific polish slice.
- Workbench/zone historical CSS should stay outside this premium closeout unless a separate workbench visual pass is requested.
- Bundle splitting and HeroUI/Tailwind minifier warnings remain technical debt but are not blockers for this UI polish closeout.

## MG-PV-final-premium-visual-closeout Prompt Draft

Next unique prompt: `MG-PV-final-premium-visual-closeout`.
