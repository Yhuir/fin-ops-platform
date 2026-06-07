# Phase 6 Batch Accounting UI Migration

本文档记录 `/batch-accounting` 的 UI 迁移 discovery、旧入口对照、测试策略和后续 Micro-JIT prompt。目标是迁出非关联台 MUI，同时保持用户使用感受不变。

## P079 Discovery

- Prompt ID: `P079-phase-6-batch-accounting-discovery`
- Status: verified
- Scope: `/batch-accounting` only.
- Runtime implementation changed: no.
- Test implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Commit: `e113d6e6 docs: add batch accounting migration discovery`, pushed to `origin/refactor-ui`.

## Current MUI Inventory

| File | Current MUI / MUI icon usage | Migration target |
| --- | --- | --- |
| `web/src/pages/BatchAccountingPage.tsx` | `ClearOutlinedIcon`, `RefreshOutlinedIcon`, `SearchOutlinedIcon`, `WarningAmberRoundedIcon`, `Alert`, `Box`, `Button`, `Checkbox`, `Chip`, `Dialog*`, `Divider`, `IconButton`, `InputAdornment`, `Paper`, `Snackbar`, `Stack`, `Table*`, `TextField`, `ToggleButton*`, `Tooltip`, `Typography` | lucide icons, project/native toolbar/filter controls, project segmented buttons, native year/search/textarea fields, native right/left panels, dense project table, native checkboxes, project tags/notices/toast, `AppDialog` or native dialog equivalent. |
| `web/src/test/BatchAccountingPage.test.tsx` | wraps runtime in `MuiProviders`; behavior tests otherwise mostly user-visible | P080 should add source-level no-MUI/project primitive contract and preserve behavior assertions. |

## User-visible Entrypoints

| Entry | Existing behavior to preserve |
| --- | --- |
| Route/sidebar | Route `/batch-accounting`, sidebar label `批量账务`, page heading `日常报销批量账务管理`. |
| Header action | `刷新` button reloads current bucket/year data and is disabled while loading. |
| Status switch | `批量账务状态` segmented control with `未提交 <count>` and `已提交 <count>`, exclusive selection, switching clears selected bank/OA rows and difference note. |
| Bank region | Region `批量账务流水`; copy `对方户名精确匹配批量账务集中处理`; field `流水年份`; selected bank row is button-like with `aria-pressed`; row accessible name includes counterparty, amount, trade time, direction and account. |
| OA/relation region | Table aria-label switches between `可关联OA项` and `已关联OA项`; field `OA年份`; search field `搜索OA内容`; clear search button `清空搜索`. |
| OA selection | Unsubmitted bucket shows OA row checkboxes with label `选择 <申请人> <申请时间>`; submitted bucket is read-only and hides selection column. |
| Amount summary | Shows `银行流水金额 ...`, `已选 OA <n> 项`, `已选 OA 金额 ...`, `差额 ...`; mismatch requires `差额说明`; submitted mismatch shows `金额不一致` and tooltip action `查看金额不一致差额说明`. |
| Submit | Button `关联OA项与流水` is disabled until a bank row, OA rows and valid years exist; if amount mismatch, non-empty trimmed note is required. |
| Withdraw | Submitted bucket shows `撤回关联`; opens modal dialog `撤回关联`; field `撤回原因`; buttons `取消` and `确认撤回`; confirm disabled without trimmed reason. |
| Feedback | Success/error messages appear via Snackbar today: `已关联批量账务流水与 2 项 OA。`, `已撤回批量账务关联。`, API error fallbacks. New UI should keep feedback text and close/autohide behavior. |
| Empty/loading/error | `正在加载流水`, `当前年份暂无批量账务流水`, `暂无可关联 OA`, `暂无已关联 OA`, and page error `批量账务数据加载失败` remain visible in equivalent positions. |

## API / Read Model Boundary

- `GET /api/batch-accounting`: query params `bank_year`, `oa_year`, `bucket`; returns summary, bank rows, OA rows and submitted relation buckets.
- `POST /api/batch-accounting/submit`: payload `{ bank_year, oa_year, bank_row_id, oa_row_ids, expected_version, note }`.
- `POST /api/batch-accounting/{relation_id}/withdraw`: payload `{ expected_version, reason }`.
- UI emits `FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated` with `source: "batch_accounting_mutation"` after submit/withdraw.
- This UI migration must not change API client mapping, request payloads, response shapes, read model freshness semantics, backend routes, worker behavior or workbench internals.

## Existing Test Coverage

`web/src/test/BatchAccountingPage.test.tsx` currently covers:

- Rendering heading, status buttons, years, refresh button, bank region and selectable OA table.
- Selected totals, mismatch note requirement, successful submit payload and affected-month event.
- Trimmed difference note behavior.
- Clearing difference note when bank row, bucket or OA selection changes.
- Preserving selected bank/OA rows when changing only OA year.
- OA search across applicant, project, amount and reason.
- Submitted bucket read-only associated OA rows and withdraw payload.
- Sidebar entry placement near no-OA bank batches.

## Migration Slice Plan

1. `P080-phase-6-batch-accounting-characterization-tests`
   - Add source-level no-MUI/project primitive contract.
   - Keep existing behavior assertions user-visible rather than MUI provider/class based.
2. `P081-phase-6-batch-accounting-page-shell-filters`
   - Migrate header refresh, status segmented control and year/search filter controls.
   - Do not migrate bank list, OA table, tooltip, dialog or snackbar yet.
3. `P082-phase-6-batch-accounting-bank-list-and-summary`
   - Migrate bank region/list, amount summary chips, mismatch note field and mismatch tooltip trigger.
4. `P083-phase-6-batch-accounting-oa-table`
   - Migrate OA table, checkboxes, expandable text and empty states.
5. `P084-phase-6-batch-accounting-overlays-feedback`
   - Migrate withdraw dialog and snackbar/feedback; clear remaining page MUI imports.
6. `MG-P084-phase-6-batch-accounting`
   - Verify page tests, table/common/HeroUI smoke, build, no-MUI scope grep, exact staging and push.

## Risks

- The page keeps selection caches in `bankRowsById` and `oaRowsById`; UI refactor must not drop cached selected rows after year changes.
- Mismatch note is intentionally cleared by bank row, bucket and OA selection changes; field extraction must preserve these resets.
- Submitted bucket table is read-only but still uses relation bucket OA rows; table refactor must keep submitted relation display and withdraw behavior.
- `AmountMismatchWarning` uses controlled tooltip open/close today; replacing it must preserve hover/focus/click access to bank amount, OA amount, delta and note.
- Search normalizes whitespace and case across multiple fields; visual refactor must not alter filtering logic.
- Mutation completion emits workbench relation update events; UI migration must not move or suppress this side effect.

## P080 Prompt Draft

```text
Prompt ID: P080-phase-6-batch-accounting-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/batch-accounting` tests only. Do not modify runtime implementation.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_batch_accounting.md、docs/refactor-ui/table_layout_system.md、web/src/pages/BatchAccountingPage.tsx、web/src/features/batchAccounting/api.ts、web/src/features/batchAccounting/types.ts 和 web/src/test/BatchAccountingPage.test.tsx。只修改 `web/src/test/BatchAccountingPage.test.tsx`：新增 source-level contract，未来 `BatchAccountingPage.tsx` 不得依赖 `@mui/*`、`Mui[A-Z]`、MUI icons (`ClearOutlinedIcon`/`RefreshOutlinedIcon`/`SearchOutlinedIcon`/`WarningAmberRoundedIcon`)、`ToggleButton`、`TextField`、`TableCell`、`TableRow`、`TableHead`、`TableBody`、`DialogTitle`、`DialogContent`、`DialogActions`、`Snackbar`、`Chip`、`IconButton`、`Tooltip`；要求页面继续使用 `PageScaffold`、`StatePanel` and project/native table/panel/dialog/feedback classes or primitives。保留并必要补强行为断言：route/sidebar label `批量账务`、heading `日常报销批量账务管理`、refresh、status buttons `未提交`/`已提交`、fields `流水年份`/`OA年份`/`搜索OA内容`/`差额说明`、region `批量账务流水`、bank row accessible names and `aria-pressed`, table aria-label `可关联OA项`/`已关联OA项`, OA checkbox labels, search clear button, amount summary and mismatch tooltip, submit payload/event, withdraw dialog payload, feedback messages, loading/empty/error states, and selection/note reset behavior。不得修改页面实现、API client、mock data shape、backend、read model、worker 或关联台内部工作区。运行 `cd web && npx vitest run BatchAccountingPage.test.tsx`，实现未迁移前 source-level contract expected-fail 可接受，但 existing behavior tests must pass；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P081 page shell filters prompt。
```
