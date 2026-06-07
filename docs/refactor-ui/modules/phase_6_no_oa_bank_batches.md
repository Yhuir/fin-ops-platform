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
| Page tests | `web/src/test/NoOaBankBatchPage.test.tsx` | Route/sidebar, three-column layout, tag drawer, selection boundaries, submit/withdraw flows, stale read model retry and keep-alive behavior. |
| API tests | `web/src/test/NoOaBankBatchApi.test.ts` | API client mapping, request payloads, HTML/error handling and mutation contracts. |
| Related docs | `docs/dev/api-contracts.md`, `docs/app-architecture/pages.md` | API contract and page/read-model ownership references. |

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
| Read model stale handling | Stale/read-model-refresh detail text stays hidden; page keeps current rows visible while background polling runs; polling pauses while keep-alive page is inactive. |

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
| Read model tests | Stale retry, keep-alive inactive pause, background refresh keeps rows visible. | Loading/status replacement must preserve hidden stale copy and background refresh behavior. |
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
- The transaction detail table is loaded lazily per selected batch and cached in `details`; table refactor must not refetch unnecessarily or lose `usePageScrollSession`.
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

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md、docs/refactor-ui/table_layout_system.md、web/src/pages/NoOaBankBatchPage.tsx、web/src/features/noOaBankBatches/api.ts、web/src/features/noOaBankBatches/types.ts、web/src/test/NoOaBankBatchPage.test.tsx 和 web/src/test/NoOaBankBatchApi.test.ts。只修改 `web/src/test/NoOaBankBatchPage.test.tsx`：新增或调整 characterization tests，锁定 `/no-oa-bank-batches` 的 project primitive 目标和旧行为。新增 source-level contract，未来 runtime 不得依赖 `@mui/*`、`Mui[A-Z]`、`RefreshOutlinedIcon`、`CloseIcon`、`ToggleButton`、`TextField`、`TableCell`、`TableRow`、`TableHead`、`TableBody`、`Drawer`、`DialogTitle`、`DialogContent`、`DialogActions`、`Snackbar`、`Chip`、`IconButton`；要求页面继续使用 `PageScaffold`、`StatePanel`，后续 drawer/dialog 使用 project primitives 或 native equivalents。行为断言必须继续覆盖 route/sidebar、heading、description/top actions、status buttons `未提交`/`已提交`/`历史`、fields `月份`/`银行账户`、main/sub rail region names and keyboard activation、transaction region/table labels, selection guard, selected-row submit payload, internal-transfer submit payload, tag drawer open/refetch/save payload/live update, withdraw dialog reason payload, snackbar messages, read model stale retry and keep-alive pause。不得修改页面实现、API client、mock data shape、backend、read model、worker 或关联台内部工作区。运行 `cd web && npx vitest run NoOaBankBatchPage.test.tsx`，实现未迁移前 source-level contract expected-fail 可接受，但 existing behavior tests must pass；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P075 page shell filters prompt。
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
