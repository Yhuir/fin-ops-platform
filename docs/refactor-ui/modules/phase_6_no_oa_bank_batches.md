# Phase 6 No OA Bank Batches

本文档记录 `/no-oa-bank-batches` 的 UI 迁移 discovery、旧入口对照、测试策略和后续 Micro-JIT prompt。目标是迁出非关联台 MUI，同时保持用户使用感受不变。

## P073 Discovery

- Prompt ID: `P073-phase-6-no-oa-bank-batches-discovery`
- Type: discovery/planning
- Status: verified
- Scope: `/no-oa-bank-batches` only.
- Implementation changed: no.
- Tests changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Commit: `ac9a18ac docs: add no oa bank batches migration discovery`, pushed to `origin/refactor-ui`.

## Current Files

| Area | Files | Notes |
| --- | --- | --- |
| Page | `web/src/pages/NoOaBankBatchPage.tsx` | Page shell, status/month/account filters, main/sub label rails, batch cards, detail transaction table, tag-management right drawer, withdraw dialog and snackbar feedback. |
| API/types | `web/src/features/noOaBankBatches/api.ts`, `types.ts` | List/detail/tag-selection/submit/withdraw API client and response normalization. No UI prompt may change these contracts. |
| Page tests | `web/src/test/NoOaBankBatchPage.test.tsx` | Route/sidebar, three-column layout, tag drawer, selection boundaries, submit/withdraw flows, stale read model retry and route remount behavior. |
| API tests | `web/src/test/NoOaBankBatchApi.test.ts` | API client mapping, request payloads, HTML/error handling and mutation contracts. |
| Related docs | `docs/dev/api-contracts.md`, `docs/app-architecture/pages.md` | API contract and page/read-model ownership references. |

## PV-018 Premium Visual Discovery

- Prompt ID: `PV-018-no-oa-bank-batches-discovery`
- Type: premium visual discovery
- Status: verified
- Scope: `/no-oa-bank-batches` only.
- Implementation changed: no.
- Tests changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.

### Current Implementation Status On `main`

- Page shell, filter region, status segmented controls, label rails, transaction region, batch rows, detail table, tag drawer shell, withdraw dialog and toast feedback already use project/native primitives.
- The page is a dense three-zone operational layout: filter controls on top, main/sub rails on the left/middle, transaction batches and detail table on the right.
- The tag-management workflow is a right-side project drawer surface implemented with `no-oa-bank-batches-drawer*` classes; withdraw remains an `AppDialog`.
- Source-level tests already require no direct runtime MUI imports/selectors and require `PageScaffold`, `StatePanel`, project rail/table/drawer/dialog classes.

### User-visible Entrypoint Matrix

| Area | Preserve exactly |
| --- | --- |
| Route/sidebar | `/no-oa-bank-batches`, sidebar label `免OA流水批量处理`, page heading `免OA流水批量处理`. |
| Header actions | `免OA流水标签管理`, `刷新`; keep location, disabled/loading behavior and tag selection refetch on drawer open. |
| Filter region | Region `批次筛选`; status segmented buttons `未提交 <count>`, `已提交 <count>`, `历史 <count>`; fields `月份` and `银行账户`. |
| Selected feedback | Unsubmitted bucket shows `提交批次` and `已选 <n> 条`; cross-bank selection warning remains visible. |
| Main rail | Region `主标签`; empty title `请先在标签管理中选择免OA标签`; buttons expose `<label> <批数/条数>` and Enter/Space activation. |
| Sub rail | Region `子标签`; empty title `暂无子标签`; subtitle follows selected main label; buttons expose `<label> <批数/条数>` and Enter/Space activation. |
| Transaction region | Region `流水`; selected title `<主标签> / <子标签>`; bucket hint copy, selected account copy and stale/loading/empty states remain. |
| Batch list | Account label, status tag, row count, total amount, blocking reason and audit metadata remain in the batch item. |
| Batch actions | `查看<account>流水`, `全选`, `清空`, `提交内部往来批次`, `撤回批次` remain in the transaction region with existing disabled/mutating semantics. |
| Detail table | Accessible name `<account>流水`; columns `交易时间`, `对方户名`, `金额`, `摘要/用途/备注`, `分类来源`; row checkboxes and account select-all remain. |
| Tag drawer | Right drawer/dialog name `免OA流水标签管理`; close label `关闭免OA流水标签管理`; version caption; actions `全选`, `清空`, `保存`; inactive warning and main/child checkboxes remain. |
| Withdraw dialog | Dialog title `撤回批次`; warning copy, `撤回原因`, `取消`, `确认撤回`; disabled without reason. |
| Feedback/status | Snackbar/status feedback for save, submit, withdraw, selection warnings and API errors remains user visible. |
| Read model | Stale/read-model-refresh details stay hidden while current rows remain visible and retry timers clean up on route unmount. |

### Table And List Content Roles

| Surface | Premium layout requirement |
| --- | --- |
| Status segmented controls | Keep compact segmented controls with stable button height, no page-transition delay and clear active state. |
| Main/sub rails | Keep rail items dense and scan-friendly; active rail state must not shift layout; counts align at the right edge where possible. |
| Batch list | Avoid big card treatment; batch rows should read like compact operational list items with stable status tag, amount and action alignment. |
| Detail table | Amount column right-aligns with tabular nums; direction/bank/source tags keep stable height; long counterparty/summary/purpose/remark text wraps or truncates without breaking row rhythm. |
| Drawer | Tag management drawer remains right-side and compact; checkbox rows align consistently with labels and nested child tags. |
| Dialog/toast | Withdraw dialog and feedback surfaces stay small, focused and non-blocking beyond their original workflow semantics. |

### PV-019 Premium Opportunities

- Replace any no-OA hard-coded hover/focus/table/surface colors with Ledger Calm token-based `color-mix(...)` treatments.
- Add motion-token feedback to no-OA page buttons, segmented controls, filter inputs, rail items, batch actions, table row/checkbox affordances, drawer close/actions and dialog actions.
- Tighten rail, batch-list, table-wrap, drawer and toast surfaces while preserving the existing three-zone layout.
- Add CSS contract coverage in `NoOaBankBatchPage.test.tsx` for compact rails/list/table treatment, motion-token usage, amount alignment and token colors.

### Non-scope For PV-019

- Do not change API client/types, request params, mutation payloads, domain events, read-model freshness handling, retry behavior or workbench rebuild behavior.
- Do not change the three-zone page structure, row selection guard, internal-transfer submit endpoint, withdraw dialog shape or tag drawer shape.
- Do not convert the batch list into large cards or a dashboard.
- Do not touch the frozen reconciliation workbench internals.

## Current MUI Inventory

| File | Current MUI usage | Target |
| --- | --- | --- |
| `NoOaBankBatchPage.tsx` | `RefreshOutlinedIcon`, `CloseIcon`, `Alert`, `Box`, `Button`, `Checkbox`, `Chip`, `Dialog*`, `Divider`, `Drawer`, `FormControlLabel`, `IconButton`, `List`, `ListItemButton`, `Paper`, `Snackbar`, `Stack`, `Table*`, `TextField`, `ToggleButton*`, `Typography` | Project/native page toolbar, segmented controls, native inputs, project rail/cards/table, `AppDrawer`, `AppDialog`, `StatePanel`, native snackbar/status surface and lucide icons. |
| `NoOaBankBatchPage.test.tsx` | Imports `MuiProviders` to render current page | Characterization tests may keep compatibility while runtime migrates; final module tests should not require MUI provider for this page unless global compat still exists for unrelated components. |

## User-visible Entrypoints

| Entrypoint | Current behavior to preserve |
| --- | --- |
| Route/sidebar | `/no-oa-bank-batches`, sidebar label `免OA流水批量处理`, page heading `免OA流水批量处理`. |
| Page description | `按月份、主子标签和银行账户确认免 OA 银行流水批次。` |
| Top actions | `免OA流水标签管理` opens a right drawer and refetches tag selection; `刷新` reloads tag selection and batch list while disabled during loading. |
| Filter region | Region `批次筛选`; status segmented buttons `未提交 <count>`、`已提交 <count>`、`历史 <count>`; fields `月份` and `银行账户`; unsubmitted bucket shows `提交批次`. |
| Selection feedback | Shows `已选 <n> 条`; selecting rows from another account without clearing shows `请先清空已选银行区域，再选择其他银行流水。`. |
| Main label rail | Region `主标签`; empty title `请先在标签管理中选择免OA标签`; button labels include `<主标签> <批数/条数>` and support Enter/Space activation. |
| Sub label rail | Region `子标签`; empty title `暂无子标签`; subtitle follows selected main label; button labels include `<子标签> <批数/条数>` and support Enter/Space activation. |
| Transaction region | Region `流水`; selected title is `<主标签> / <子标签>`; hints depend on bucket: unsubmitted selection rule, submitted withdraw hint, withdrawn readonly hint. |
| Batch cards | Account label such as `建设银行8106`, status tags `待提交`/`已提交`/`已撤回`/`冲突`/`需复核`, row count and total amount, blocking reason, audit metadata `版本`/`提交人`/`提交时间`/`撤回人`/`撤回时间`. |
| Batch actions | `查看<account>流水`, selected batch `全选`/`清空`, internal transfer `提交内部往来批次`, submitted batch `撤回批次`. |
| Detail table | Accessible table name `<account>流水`; columns `交易时间`、`对方户名`、`金额`、`摘要/用途/备注`、`分类来源`; draft non-internal-transfer rows include account select-all and row checkboxes. |
| Row content | Direction tag (`收`/`支` or backend label), right-aligned tabular amount, bank/account tag, summary/purpose/remark, category source label `自动`/`人工`. |
| Tag drawer | Right drawer/dialog name `免OA流水标签管理`; close label `关闭免OA流水标签管理`; version caption; actions `全选`/`清空`/`保存`; inactive selected warning; main and child tag checkboxes including `主标签本身`. |
| Withdraw dialog | Dialog title `撤回批次`; warning copy `撤回后会取消关联台闭环关系，相关流水回到未配对区域。`; field `撤回原因`; buttons `取消` and `确认撤回`; submit disabled without reason. |
| Snackbar/status feedback | Success/warning/error feedback remains user visible: `免OA流水标签范围已保存`, `选中流水已提交`, `内部往来批次已提交`, `批次已撤回`, selection warning and API error messages. |
| Read model stale handling | Stale/read-model-refresh detail text stays hidden; page keeps current rows visible while background polling runs; retry timers are cleaned up when the route unmounts. |

## API / Read Model Boundary

- `GET /api/no-oa-bank-batches/tag-selection`: tag drawer selection source.
- `PUT /api/no-oa-bank-batches/tag-selection`: payload `{ expected_version, selected_tag_codes }`; success returns the same selection shape and refreshes the list.
- `GET /api/no-oa-bank-batches`: query params `month`, `type`, `status`, `bucket`, `account_key`; UI currently sends `month`, `bucket`, `account_key`.
- `GET /api/no-oa-bank-batches/{batch_id}`: detail rows for the selected batch.
- `POST /api/no-oa-bank-batches/submit-selection`: payload `{ transaction_ids, note }`; used for selected non-internal-transfer rows.
- `POST /api/no-oa-bank-batches/{batch_id}/submit`: payload `{ expected_version, note }`; used for internal transfer draft batches.
- `POST /api/no-oa-bank-batches/{batch_id}/withdraw`: payload `{ expected_version, reason }`.
- Mutation results return `affected_months` and `workbench_rebuild_queued`; UI emits `workbenchRelationUpdated` with affected months after submit/withdraw.
- Read model status is `fresh` / `refreshing` / `stale` / `schema_mismatch` / `missing`; non-fresh status triggers background retry through `NO_OA_READ_MODEL_REFRESH_RETRY_MS`.
- UI migration must not change request params, mutation payloads, version semantics, freshness handling, domain events or workbench rebuild behavior.

## Existing Test Coverage

| Test | Current coverage | Migration implication |
| --- | --- | --- |
| `renders tag management and the three-column main/sub/transaction layout` | Heading, tag drawer button, status buttons, month/account fields, rails, transaction region, detail table, checkboxes and source label. | Characterization should add no-MUI/project primitive source contract while preserving this behavior. |
| `shows batch blocking reasons and audit metadata` | Conflict/blocking text and submitted/withdrawn audit metadata. | New card/table layout must keep these texts visible. |
| `clears hidden selected rows when changing label scope` | Selection clears when main/sub scope changes and submit disables. | Refactor must keep selection clearing bound to label changes. |
| `main and child label rails support keyboard activation` | Enter and Space activation on rails. | Native/project rail buttons must preserve keyboard semantics. |
| `saves drawer tag selection with main and child tag toggles` | Right drawer, clear/all/select child behavior and PUT payload. | Drawer migration must preserve checkbox labels and payload ordering. |
| `opening tag drawer refetches the latest no OA tag selection` | Drawer open triggers fresh tag-selection fetch. | Do not move drawer open into stale cached state. |
| `updates open tag drawer labels after bank auto tag rules change` | Domain event refreshes open drawer labels. | Event hooks and open drawer refresh must survive. |
| `drawer shows only bank auto rule main and child labels for external turnover tags` | Tag drawer hides third/family labels. | Do not expose unrelated label levels during visual refactor. |
| `submits only the selected transaction rows and dispatches affected months` | Selected row POST and domain event. | Table checkbox migration must keep row IDs and affected month event. |
| `prevents selecting rows from another bank before clearing the current bank region` | Cross-account selection warning and original selection retained. | Selection guard must remain before table/card split. |
| `switches to submitted bucket and withdraws a submitted batch` | Submitted bucket, withdraw dialog, reason payload and domain event. | Dialog migration must keep field label and disabled semantics. |
| `shows withdrawn history as read-only` | History bucket hides submit/withdraw controls. | Do not accidentally render actions in withdrawn bucket. |
| `submits internal transfer draft batches through the batch endpoint` | Internal transfer uses batch submit endpoint, not selected-row endpoint. | Keep special-case action path distinct. |
| Category/tag update tests | `bankTransactionCategoryUpdated`, `bankAutoTagRulesUpdated`, BroadcastChannel sync refresh list/detail/tag selection. | UI refactor must not rewrite event wiring. |
| Read model tests | Stale retry, route unmount retry cleanup, background refresh keeps rows visible. | Loading/status replacement must preserve hidden stale copy and background refresh behavior. |
| Sidebar test | Sidebar route entry. | App shell already migrated; keep route label unchanged. |

## Migration Slice Plan

1. `P074-phase-6-no-oa-bank-batches-characterization-tests`
   - Add source-level project primitive/no-MUI contracts.
   - Rename any MUI wording/provider assumptions where needed.
   - Lock page shell, rails, transaction table, tag drawer, withdraw dialog, snackbar/status and stale retry behavior.
2. `P075-phase-6-no-oa-bank-batches-page-shell-filters`
   - Migrate page actions, filter region, status segmented controls, month/account fields, selected count and high-level error/loading status.
   - Do not migrate rails/table/drawer/dialog.
3. `P076-phase-6-no-oa-bank-batches-label-rails`
   - Migrate `LabelRail` and the main/sub rail surfaces from MUI `Paper/List/ListItemButton/Typography/Divider` to project/native controls.
   - Preserve region names, labels, counts, `aria-pressed` and keyboard activation.
4. `P077-phase-6-no-oa-bank-batches-transaction-region`
   - Migrate transaction region batch cards, detail table, checkboxes, tags, amount alignment and batch actions.
   - Preserve submit-selection/internal-transfer/selection guard behavior.
5. `P078-phase-6-no-oa-bank-batches-overlays-feedback`
   - Migrate tag-management right drawer, withdraw dialog and snackbar/status feedback.
   - Preserve drawer right-side shape, dialog shape, labels, warnings and payloads.
6. `MG-P078-phase-6-no-oa-bank-batches`
   - Verify page tests, API tests, build, no-MUI scope grep, exact staging and push.

## Risks

- The page is a single large component with UI and workflow state interleaved. Refactor slices must stay narrow to avoid changing batch/selection semantics.
- The transaction detail table is loaded lazily per selected batch and cached in `details`; table refactor must not refetch unnecessarily or lose lightweight table/session state.
- Selected-row submit must only allow one bank account region at a time; visual grouping must not hide this boundary.
- Internal-transfer drafts submit by `batchId` and must not be mixed into selected-row submit.
- Tag drawer open/refetch and live updates from bank tag events are easy to break if drawer state is extracted too aggressively.
- Stale read model copy is intentionally hidden from users while polling continues; replacing loading/status surfaces must not reintroduce the hidden stale message.
- Reconciliation workbench imports the no-OA API for its frozen internal workspace; UI migration must not change API client/types or workbench behavior.

## P074 Prompt Draft

```text
Prompt ID: P074-phase-6-no-oa-bank-batches-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: `/no-oa-bank-batches` tests only. Do not modify runtime implementation.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/features/noOaBankBatches/api.ts、web/src/features/noOaBankBatches/types.ts、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/test/NoOaBankBatchApi.test.ts。只修改 `web/src/test/NoOaBankBatchPage.test.tsx`：新增或调整 characterization tests，锁定 `/no-oa-bank-batches` 的 project primitive 目标和旧行为。新增 source-level contract，未来 runtime 不得依赖 `@mui/*`、`Mui[A-Z]`、`RefreshOutlinedIcon`、`CloseIcon`、`ToggleButton`、`TextField`、`TableCell`、`TableRow`、`TableHead`、`TableBody`、`Drawer`、`DialogTitle`、`DialogContent`、`DialogActions`、`Snackbar`、`Chip`、`IconButton`；要求页面继续使用 `PageScaffold`、`StatePanel`，后续 drawer/dialog 使用 project primitives 或 native equivalents。行为断言必须继续覆盖 route/sidebar、heading、description/top actions、status buttons `未提交`/`已提交`/`历史`、fields `月份`/`银行账户`、main/sub rail region names and keyboard activation、transaction region/table labels, selection guard, selected-row submit payload, internal-transfer submit payload, tag drawer open/refetch/save payload/live update, withdraw dialog reason payload, snackbar messages, read model stale retry和 route unmount cleanup。不得修改页面实现、API client、mock data shape、backend、read model、worker 或关联台内部工作区。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx`，实现未迁移前 source-level contract expected-fail 可接受，但 existing behavior tests must pass；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P075 page shell filters prompt。
```

## P074 Execution Notes

- Status: verified as expected-fail.
- Files changed:
  - `web/src/test/NoOaBankBatchPage.test.tsx`
- Runtime implementation changed: no.
- Backend/API/read model/worker changed: no.
- Workbench internals changed: no.
- Implementation:
  - Added a source-level contract for `NoOaBankBatchPage.tsx`.
  - The contract forbids direct MUI imports/selectors and legacy MUI surfaces such as `RefreshOutlinedIcon`, `ToggleButton`, `TextField`, MUI table cells, `Drawer`, `DialogTitle`, `Snackbar`, `Chip` and `IconButton`.
  - The contract requires `PageScaffold`, `StatePanel`, project drawer/dialog/table/rail classes or primitives.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: expected-fail; 19 existing behavior tests passed and 1 source-level contract failed against current MUI runtime.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P074 test file changed before docs.
- Commit: `4a958ce8 test: characterize no oa bank batch ui migration`, pushed to `origin/refactor-ui`.

## Current Expected Failures After P074

- `src/pages/NoOaBankBatchPage.tsx` still imports MUI and MUI icons.
- Page shell/filter still uses `RefreshOutlinedIcon`, MUI `Button`, `ToggleButtonGroup`, `ToggleButton`, `TextField`, `Box`, `Stack` and `Typography`; P075 owns this slice.
- `LabelRail` still uses MUI `Paper`, `List`, `ListItemButton`, `Divider`, `Box`, `Stack`, `Typography` and `.Mui-selected` selectors; P076 owns this slice.
- Transaction region still uses MUI `Paper`, `Stack`, `Alert`, `Button`, `Table*`, `Checkbox`, `Chip`, `Typography`; P077 owns this slice.
- Tag drawer, withdraw dialog and snackbar still use MUI `Drawer`, `Dialog*`, `Snackbar`, `FormControlLabel`, `Checkbox`, `IconButton`, `CloseIcon`, `Alert`, `Button`, `TextField`; P078 owns this slice.

## P075 Prompt Draft

```text
Prompt ID: P075-phase-6-no-oa-bank-batches-page-shell-filters
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `/no-oa-bank-batches` page shell actions and filter region only. Do not migrate label rails, transaction region, tag drawer, withdraw dialog or snackbar.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/app/styles.css。只修改 `web/src/pages/NoOaBankBatchPage.tsx`、必要 `web/src/app/styles.css` 和必要测试 expectation：迁移 page shell actions and filter region，包括 top actions `免OA流水标签管理`/`刷新`、region `批次筛选`、status segmented buttons `未提交 <count>`/`已提交 <count>`/`历史 <count>`、fields `月份`/`银行账户`、unsubmitted `提交批次` and selected count `已选 <n> 条`。移除本 slice 的 `RefreshOutlinedIcon`、MUI `ToggleButtonGroup`、`ToggleButton` and filter `TextField` usages，使用 lucide refresh icon, project/native buttons, native segmented controls and native month/text inputs with project classes。必须保留 PageScaffold title/description/actions, tag drawer open/refetch trigger, refresh loading disabled behavior, status bucket state reset/clearSelection behavior, labels and aria pressed/current selected semantics, month/account query behavior, selected-row submit button disabled/mutating behavior and selected count text。不得修改 `LabelRail` implementation, transaction region/table/cards, tag drawer, withdraw dialog, snackbar, API client, mock data shape, backend, read model, worker or reconciliation workbench internals。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|main and child label rails"`，source-level contract expected-fail can remain but selected behavior tests must pass；运行完整 `cd web && npx vitest run NoOaBankBatchPage.test.tsx` expected-fail only for remaining source-level contract；运行 `cd web && npm run build`；运行 page-shell/filter grep：`if rg -n 'RefreshOutlinedIcon|ToggleButton|ToggleButtonGroup|<TextField[^\\n]*(label=\"月份\"|label=\"银行账户\")' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P076 label rails prompt。
```

## P075 Execution Notes

- Status: verified as expected-fail.
- Files changed:
  - `web/src/pages/NoOaBankBatchPage.tsx`
  - `web/src/app/styles.css`
- Behavior preserved:
  - PageScaffold title/description/actions remain unchanged.
  - Top actions `免OA流水标签管理` and `刷新` remain in the same header action area.
  - Tag drawer open still calls `loadTagSelection()` before opening.
  - Refresh still clears details, reloads tag selection and increments refresh token while disabled during loading.
  - Filter region `批次筛选`, status buttons `未提交` / `已提交` / `历史`, fields `月份` / `银行账户`, `提交批次` disabled logic and `已选 <n> 条` text are preserved.
  - Status bucket change still clears selection and resets selected main/sub/batch state.
- Implementation:
  - Replaced page actions and filter region MUI `Stack`, `ToggleButtonGroup`, `ToggleButton`, filter `TextField` and refresh icon usage with native controls, `lucide-react` `RefreshCw` and project CSS classes.
  - Did not modify `LabelRail`, transaction region/table/cards, tag drawer, withdraw dialog, snackbar, API client, backend, read model, worker or workbench internals.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|main and child label rails"`: expected-fail; 4 selected behavior tests passed and 1 source-level contract failed.
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: expected-fail; 19 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n 'RefreshOutlinedIcon|ToggleButton|ToggleButtonGroup|<TextField[^\\n]*(label="月份"|label="银行账户")' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P075 implementation files changed before docs.
- Commit: `1c872bfe feat: migrate no oa bank batch filters`, pushed to `origin/refactor-ui`.

## Current Expected Failures After P075

- `src/pages/NoOaBankBatchPage.tsx` still imports MUI because rails, transaction region, tag drawer, withdraw dialog and snackbar remain MUI.
- Source-level contract still fails on forbidden MUI imports/legacy surfaces and missing project rail/table/drawer/dialog targets.
- Page shell/filter-specific residues `RefreshOutlinedIcon`, `ToggleButton`, `ToggleButtonGroup`, and filter `TextField` usages for `月份`/`银行账户` are cleared.
- `LabelRail` remains P076.
- Transaction region remains P077.
- Tag drawer, withdraw dialog and snackbar remain P078.

## P076 Prompt Draft

```text
Prompt ID: P076-phase-6-no-oa-bank-batches-label-rails
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: `LabelRail` and main/sub rail surfaces in `NoOaBankBatchPage.tsx` only, plus necessary styles/tests. Do not migrate transaction region, tag drawer, withdraw dialog or snackbar.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：迁移 `LabelRail` 以及 `主标签`/`子标签` rail surfaces，移除该 slice 的 MUI `Paper`、`List`、`ListItemButton`、`Divider`、`Box`、`Stack`、`Typography` and `.Mui-selected` rail selector usage，使用 native/project region, header, button list, count meta and project rail classes。必须保留 regions `主标签`/`子标签`、empty titles `请先在标签管理中选择免OA标签`/`暂无子标签`、titles/subtitles、button accessible names `<label> <countMeta>`、`aria-pressed` selected state, Enter/Space keyboard activation, selected main/sub state behavior and clearSelection behavior on rail selection。不得修改 page shell/filter controls, transaction region/table/cards, tag drawer, withdraw dialog, snackbar, API client, mock data shape, backend, read model, worker or reconciliation workbench internals。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|main and child label rails"`，source-level contract expected-fail can remain for table/overlays but selected behavior tests must pass；运行完整 `cd web && npx vitest run NoOaBankBatchPage.test.tsx` expected-fail only for remaining source-level contract；运行 `cd web && npm run build`；运行 rail grep：`if rg -n 'ListItemButton|<List\\b|Mui-selected' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P077 transaction region prompt。
```

## P076 Execution Notes

- Status: verified as expected-fail.
- Files changed:
  - `web/src/pages/NoOaBankBatchPage.tsx`
  - `web/src/app/styles.css`
- Behavior preserved:
  - Regions `主标签` and `子标签` keep the same accessible names.
  - Empty states `请先在标签管理中选择免OA标签` and `暂无子标签` are unchanged.
  - Label buttons keep accessible names `<label> <countMeta>`, `aria-pressed`, click selection and Enter/Space activation.
  - Selecting a main/sub rail still clears row selection and preserves the existing selected label state flow.
- Implementation:
  - Replaced `LabelRail` MUI `Paper`, `List`, `ListItemButton`, rail `Stack`/`Typography`/`Divider`/`Box` and `.Mui-selected` styling with native section/header/button list markup and project rail classes.
  - Did not modify page shell/filter controls, transaction region/table/cards, tag drawer, withdraw dialog, snackbar, API client, backend, read model, worker or workbench internals.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|main and child label rails"`: expected-fail; 4 selected behavior tests passed and 1 source-level contract failed.
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: expected-fail; 19 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n 'ListItemButton|<List\\b|Mui-selected' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P076 implementation files changed before docs.
- Commit: `379d24cd feat: migrate no oa bank batch label rails`, pushed to `origin/refactor-ui`.

## Current Expected Failures After P076

- `src/pages/NoOaBankBatchPage.tsx` still imports MUI because transaction region, tag drawer, withdraw dialog and snackbar remain MUI.
- Source-level contract still fails on forbidden MUI imports/legacy surfaces and missing project table/drawer/dialog targets.
- Rail-specific residues `ListItemButton`, `<List` and `.Mui-selected` are cleared.
- Transaction region remains P077.
- Tag drawer, withdraw dialog and snackbar remain P078.

## P077 Prompt Draft

```text
Prompt ID: P077-phase-6-no-oa-bank-batches-transaction-region
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: transaction region in `NoOaBankBatchPage.tsx` only: region `流水`, batch cards, batch actions, blocking/detail/audit states, detail dense table, row checkboxes, direction/bank/source tags and amount alignment. Do not migrate tag drawer, withdraw dialog or snackbar.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：迁移 `流水` region、batch cards and detail table，移除该 slice 的 MUI `Paper`、`Stack`、`Divider`、`Alert`、`Button`、`Box`、`TableContainer`、`Table`、`TableHead`、`TableBody`、`TableRow`、`TableCell`、`Checkbox`、`Chip`、`Typography` 用法，使用 native/project section, card, alert/status, buttons, dense table classes, native checkboxes and project tags。必须保留 region `流水`、标题 fallback `流水`、selected label title `<主标签> / <子标签>`、bucket hint copy、`当前选择账户：...`、loading/empty/detail loading/detail empty/error states、batch account/status/row count/total amount/audit items/blocking reason、按钮 `查看流水`/`全选`/`清空`/`提交内部往来批次`/`撤回批次` 的位置、accessible labels and disabled/mutating behavior、selected batch highlighting、detail table aria-label `<账户>流水`、headers `交易时间`/`对方户名`/`金额`/`摘要/用途/备注`/`分类来源`、select-all aria label `<账户>全选`、row checkbox aria label `选择流水 <transactionId>`、single-account selection guard, `setRegionSelection`, `toggleTransaction`, `handleSubmitBatch`, `setWithdrawTarget`, amount right alignment, direction/bank tags and source labels。不得修改 page shell/filter controls, `LabelRail`, tag drawer, withdraw dialog, snackbar, API client, mock data shape, backend, read model, worker or reconciliation workbench internals。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|selects transactions|submits selected transaction|submits internal transfer|withdraw"`，source-level contract expected-fail can remain for overlays but transaction behavior tests must pass；运行完整 `cd web && npx vitest run NoOaBankBatchPage.test.tsx` expected-fail only for remaining overlay/source-level contract；运行 `cd web && npm run build`；运行 transaction grep：`if rg -n 'TableContainer|<Table\\b|TableHead|TableBody|TableRow|TableCell|<Checkbox\\b|<Chip\\b|BatchStatusChip' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P078 overlays feedback prompt。
```

## P077 Execution Notes

- Status: verified as expected-fail.
- Files changed:
  - `web/src/pages/NoOaBankBatchPage.tsx`
  - `web/src/app/styles.css`
- Behavior preserved:
  - Region `流水`, label title fallback, bucket hint, selected account copy and selected batch highlighting are unchanged.
  - Loading/empty/detail loading/detail empty/error states remain visible in the same workflow positions.
  - Batch actions `查看流水`/`全选`/`清空`/`提交内部往来批次`/`撤回批次` keep their accessible labels, disabled/mutating behavior and handlers.
  - Detail table keeps aria-label `<账户>流水`, headers, row and region checkbox accessible labels, single-account selection guard, amount right alignment, direction/bank tags and source labels.
- Implementation:
  - Replaced transaction-region MUI `Paper`, `Stack`, `Divider`, `Alert`, `Button`, batch `Box`, `Table*`, row `Checkbox`, `Chip` and `Typography` usage with native/project section, card, notice, button, dense table, native checkbox and project tag classes.
  - Did not modify page shell/filter controls, `LabelRail`, tag drawer, withdraw dialog, snackbar, API client, backend, read model, worker or workbench internals.
  - Corrected the P077 residue grep to scope only the transaction region because P078 still owns drawer `<Checkbox>` usage.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx -t "targets project primitives|renders tag management|shows batch blocking|clears hidden selected rows|selects transactions|submits selected transaction|submits internal transfer|withdraw"`: expected-fail; 6 transaction/withdraw behavior tests passed and 1 source-level contract failed.
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: expected-fail; 19 behavior tests passed and 1 source-level contract failed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `sed -n '930,1096p' web/src/pages/NoOaBankBatchPage.tsx | if rg -n 'TableContainer|<Table\\b|TableHead|TableBody|TableRow|TableCell|<Checkbox\\b|<Chip\\b|BatchStatusChip'; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P077 implementation files changed before docs.
- Commit: `00e0ca44 feat: migrate no oa bank batch transactions`, pushed to `origin/refactor-ui`.

## Current Expected Failures After P077

- `src/pages/NoOaBankBatchPage.tsx` still imports MUI because tag drawer, withdraw dialog, snackbar and remaining page layout wrapper remain MUI.
- Source-level contract still fails on forbidden MUI imports/legacy surfaces and missing project drawer/dialog targets.
- Transaction table target is satisfied by `no-oa-bank-batches-table`.
- Tag drawer, withdraw dialog and snackbar remain P078.

## P078 Prompt Draft

```text
Prompt ID: P078-phase-6-no-oa-bank-batches-overlays-feedback
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: final `/no-oa-bank-batches` UI migration slice: tag-management right drawer, withdraw dialog, snackbar/feedback, remaining MUI page wrapper/layout imports in `NoOaBankBatchPage.tsx`, plus necessary styles/tests. This is the final runtime cleanup before MG-P078.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx、web/src/components/common/AppDrawer.tsx、web/src/components/common/AppDialog.tsx 和 web/src/app/styles.css。只修改本 prompt scope 内文件：迁移标签管理右侧抽屉、撤回确认弹窗、snackbar/feedback 和剩余页面 MUI wrapper/layout，移除 `NoOaBankBatchPage.tsx` 所有 `@mui/*` imports and MUI legacy surfaces (`Alert`, `Box`, `Button`, `Checkbox`, `Dialog*`, `Divider`, `Drawer`, `FormControlLabel`, `IconButton`, `Paper`, `Snackbar`, `Stack`, `TextField`, `Typography`, `CloseIcon`)。使用 `AppDrawer`/`AppDialog` 或 project/native equivalents、native form controls、project buttons/notices/classes and lucide close icon as needed。必须保留 tag drawer 右侧抽屉形态、dialog accessible shape、labels `免OA流水标签管理`/`关闭免OA流水标签管理`/`全选`/`清空`/`保存`、版本显示、inactive selected warning、group checkbox indeterminate semantics、child checkbox labels, tag drawer open/refetch/save payload/live update behavior, withdraw warning copy、撤回原因 field、取消/确认撤回 disabled/mutating behavior and payload, snackbar messages and close behavior, top-level page error/loading/empty behavior, current page shell/filter/rail/transaction behavior。不得修改 API client、mock data shape、backend、read model、worker or reconciliation workbench internals。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx` 必须全部通过；运行 `cd web && npx vitest run NoOaBankBatchApi.test.ts`；运行 `cd web && npm run build`；运行 no-MUI grep：`if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|Drawer\\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 MG-P078 cumulative merge gate prompt。
```

## P078 Execution Notes

- Status: verified.
- Files changed:
  - `web/src/pages/NoOaBankBatchPage.tsx`
  - `web/src/app/styles.css`
- Behavior preserved:
  - Tag management remains a right-side dialog surface with title `免OA流水标签管理`, close label `关闭免OA流水标签管理`, version display, `全选`/`清空`/`保存`, inactive selected warning, group indeterminate semantics and child checkbox labels.
  - Tag drawer open/refetch/save payload and live update behavior remain covered by tests.
  - Withdraw confirmation keeps title `撤回批次`, warning copy, `撤回原因`, `取消`, `确认撤回`, disabled/mutating behavior and withdraw payload.
  - Feedback messages keep success/warning/error text, close behavior and 3s auto-hide behavior.
  - Page shell/filter/rail/transaction behavior remains covered by the full page test.
- Implementation:
  - Removed all direct `@mui/*` imports and legacy MUI source surfaces from `NoOaBankBatchPage.tsx`.
  - Replaced the final MUI wrapper/layout, tag drawer, withdraw dialog and snackbar surfaces with native/project markup, `AppDialog`, native checkboxes/textarea and project CSS classes.
  - Renamed `snackbar` state to `feedback` so source-level no-MUI contract does not treat business feedback state as a MUI `Snackbar` residue.
  - Did not modify API client, mock data shape, backend, read model, worker or workbench internals.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx`: passed; 20 tests passed.
  - `cd web && npx vitest run NoOaBankBatchApi.test.ts`: passed; 7 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|Drawer\\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; only P078 implementation files changed before docs.
- Commit: `87b92e20 feat: complete no oa bank batch ui migration`, pushed to `origin/refactor-ui`.

## MG-P078 Prompt Draft

```text
Prompt ID: MG-P078-phase-6-no-oa-bank-batches
Phase: phase_6_page_batches
Type: cumulative merge gate
Scope: completed `/no-oa-bank-batches` UI migration slices P073-P078 only.

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/test/NoOaBankBatchPage.test.tsx、web/src/test/NoOaBankBatchApi.test.ts 和当前 git status/diff。检查当前分支必须是 `refactor-ui`。确认 untracked files、diff scope、测试结果和文档状态；确认 P073-P078 已记录且 P078 后 `NoOaBankBatchPage.tsx` 无 direct MUI import/source residue。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx NoOaBankBatchApi.test.ts`；运行 `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`；运行 `cd web && npm run build`；运行 no-MUI grep：`if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|Drawer\\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`；运行 `git diff --check`、`git status --short --branch`。确认 scope 只包含 `docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`、`docs/refactor-ui/refactor_ui_prompt.md`、`docs/refactor-ui/refactor_ui_state.md`、`web/src/app/styles.css`、`web/src/pages/NoOaBankBatchPage.tsx` 及必要 test docs；禁止 `git add .` 和 `git add -A`，只允许精确 git add。MG 通过后提交并 push 到 `origin/refactor-ui`，再更新 state/prompt/module docs 的 MG execution notes 和 Push Log，标记 MG verified，并从 `refactor-ui` 分支生成下一条 Micro-JIT prompt。
```

## MG-P078 Execution Notes

- Status: mg_verified.
- Scope checked: P073-P078 `/no-oa-bank-batches` only.
- Worktree before MG docs update: clean on `refactor-ui`.
- Runtime result:
  - `NoOaBankBatchPage.tsx` has no direct MUI import or legacy MUI source residue.
  - Backend/API/read model/worker unchanged.
  - Reconciliation workbench internals unchanged.
- Verification:
  - `cd web && npx vitest run NoOaBankBatchPage.test.tsx NoOaBankBatchApi.test.ts`: passed; 27 tests passed.
  - `cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx`: passed; 15 tests passed.
  - `cd web && npm run build`: passed with known HeroUI/Tailwind CSS minifier warnings and chunk size warning.
  - `if rg -n '@mui/|Mui[A-Z]|RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|Drawer\\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton' web/src/pages/NoOaBankBatchPage.tsx; then exit 1; else exit 0; fi`: passed.
  - `git diff --check`: passed.
  - `git status --short --branch`: passed; clean before MG docs update.
- Commit: `f5736c0c docs: record no oa bank batch merge gate`, pushed to `origin/refactor-ui`.
- Next prompt: `P079-phase-6-batch-accounting-discovery`.
