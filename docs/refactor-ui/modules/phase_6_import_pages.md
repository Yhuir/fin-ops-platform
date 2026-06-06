# Phase 6 Import Pages Discovery

本文档记录导入页族迁移 discovery。目标是逐步把 `/imports/*` 的共享导入工作流从 MUI/MUI X DataGrid 迁到 HeroUI/Tailwind/项目 primitives，同时保留上传、预览、确认、错误、进度、详情和 session restore 的用户体感。

Last updated: 2026-06-07

## Boundary

- Scope: `/imports/bank-transactions`、`/imports/invoices`、`/imports/etc-invoices`，`web/src/components/imports/ImportWorkflowPage.tsx`，三个 import route wrapper，相关 import tests。
- Non-scope: 不改后端、API contract、read model、worker、导入业务规则、ETC 对账任务 contract、关联台内部工作区。
- Behavior equivalence:
  - 旧导入页是 standalone route，新 UI 仍是 standalone route，不改弹窗或抽屉。
  - 旧上传区仍是上传区，保留 click upload、drag/drop、文件类型拒绝和 disabled loading 语义。
  - 旧预览/确认/清空/返回关联台按钮位置和信息层级保持等价。
  - 旧预览结果仍是表格，不改成卡片列表。
  - 旧银行账户冲突确认是弹窗，新 UI 仍是弹窗。
  - 旧重复项/未导入项明细 tabs 仍是 tabs。
  - 旧 session restore、导航离开后保留预览、异步预览完成后返回可见结果必须保留。

## Route Wrappers

| Route | Wrapper | Notes |
| --- | --- | --- |
| `/imports/bank-transactions` | `ImportBankTransactionsPage.tsx` | Only renders `<ImportWorkflowPage mode="bank_transaction" />`。 |
| `/imports/invoices` | `ImportInvoicesPage.tsx` | Only renders `<ImportWorkflowPage mode="invoice" />`。 |
| `/imports/etc-invoices` | `ImportEtcInvoicesPage.tsx` | Only renders `<ImportWorkflowPage mode="etc_invoice" />`。 |

Wrappers have no MUI dependency; migration work is concentrated in `ImportWorkflowPage.tsx` and tests.

## Current MUI Inventory

| Usage | Current file | Migration target | Notes |
| --- | --- | --- | --- |
| MUI icons `ArrowBackOutlinedIcon`, `DeleteOutlineOutlinedIcon`, `FileUploadOutlinedIcon` | `ImportWorkflowPage.tsx` | lucide icons | Keep icon button/label semantics。 |
| `Alert` | `ImportWorkflowPage.tsx` | HeroUI `Alert` or project notice primitive | Preserve success/error/info/warning messages。 |
| `Box`, `Paper`, `Stack`, `Typography` | `ImportWorkflowPage.tsx` | Native semantic layout + token classes | Remove `sx` and hard-coded colors。 |
| `Button` | `ImportWorkflowPage.tsx` | HeroUI `Button` | Preserve `返回关联台` link, `清空`, `开始预览`, `确认导入`, `移除`, dialog actions。 |
| `Chip` | `ImportWorkflowPage.tsx` | HeroUI `Chip` or finance tag primitive | Preserve task/version/count/status labels。 |
| `FormControl`, `InputLabel`, `Select` | `ImportWorkflowPage.tsx` | HeroUI `Select` or native select with project classes | Preserve labels `ETC对账任务`、`对应账户 <file>`、`票据方向 <file>` and native options behavior。 |
| `Dialog*` | `ImportWorkflowPage.tsx` | `AppDialog` / HeroUI Modal primitive | Conflict confirmation stays dialog。 |
| `Tabs`, `Tab` | `ImportWorkflowPage.tsx` | HeroUI `Tabs` | Preserve `导入预览明细` tabs and duplicate/unimported counts。 |
| `DataGrid`, `GridColDef`, `useMuiDataGridPageSession`, `useMuiDataGridScrollSession` | `ImportWorkflowPage.tsx` | `FinanceTable` + `useFinanceTableSession` or purpose-built import preview table wrapper | Three grids: main preview, detail preview, ETC preview。 |
| MUI DataGrid CSS in `importGridSx` | `ImportWorkflowPage.tsx` | `.import-workflow-*` + `.finance-table` classes | Remove `.MuiDataGrid-*` selectors from page。 |

## User-visible Entrypoints

- Page headings:
  - `银行流水导入`
  - `发票导入`
  - `ETC发票导入`
- Header actions:
  - `返回关联台`
  - `清空`
  - `开始预览` / `预览中...`
  - `确认导入` / `确认中...`
- Upload labels:
  - `上传银行流水文件`
  - `上传发票文件`
  - `上传ETC zip`
- File selection forms:
  - `对应账户 <fileName>`
  - `票据方向 <fileName>`
  - `ETC对账任务`
- File row actions:
  - `移除`
  - File name and file size display。
- Feedback states:
  - Preview success: `已完成 <n> 个文件的预览识别。`
  - ETC preview success: `已完成 <n> 个 ETC zip 文件预览。`
  - Confirm copy: `将导入 ...`
  - Error messages for stale preview, invalid file type, unavailable bank mapping, missing ETC task, stale ETC task。
- Preview surfaces:
  - Audit summary cards: `审计汇总 <label> <value>`。
  - Main import preview table: `导入预览结果`。
  - Detail tabs: `导入预览明细` with `重复项 <n>` and `未导入项 <n>`。
  - Detail tables: `重复项明细` and `未导入项明细`。
  - ETC preview table: `ETC导入预览结果`。
  - ETC missing task panel: `ETC对账任务缺失项`。
- Overlay:
  - Dialog `银行账户冲突确认` with cancel and confirm actions。

## Existing Test Coverage

`web/src/test/ImportCenterPage.test.tsx` covers:

- Standalone bank transaction, invoice and ETC routes render headings and are not legacy import dialogs。
- Bank import file upload, account mapping selection and preview request overrides。
- Invoice import file upload, direction selection and preview request overrides。
- Preview audit cards and confirm copy for bank, invoice and ETC。
- Preview stale errors map to user-facing refresh messages。
- Import preview session restore from memory/sessionStorage。
- Navigation away/back while preview is pending or complete preserves preview result。
- ETC rejects non-zip files。
- ETC requires ready reconciliation task, explains unavailable tasks and disables unavailable select。
- ETC preview uses ETC API, skips generic preview and lists missing task items。
- ETC confirm posts session/task ids and shows background job feedback。

Current testing gaps for migration:

- Tests do not yet assert import page shell/cards/notices are non-MUI project primitives。
- Tests still rely on DataGrid columnheader semantics but do not lock `FinanceTable`/project table primitive contract。
- Tests do not lock conflict confirmation dialog away from `.MuiDialog-root`。
- Tests do not lock upload zone project classes or no MUI root classes。
- Tests do not lock detail tabs as HeroUI/project tabs; they only rely on user-visible tab labels indirectly。

## Migration Slices

Recommended Micro-JIT sequence:

1. `P032-phase-6-import-pages-characterization-tests`
   - Update `ImportCenterPage.test.tsx` only。
   - Add primitive-contract assertions for standalone page shell, upload zone, action bar, notices, audit summary cards, preview tables, detail tabs and conflict dialog。
   - Preserve existing API/form/session behavior tests。
   - Expected fail is acceptable before implementation because MUI/DataGrid roots still exist。
2. `P033-phase-6-import-pages-shell-and-forms`
   - Migrate page shell, action buttons, notices, upload zone, selected file cards, select controls and audit cards。
   - Keep existing MUI DataGrid preview surfaces for a smaller first implementation slice if necessary。
   - Preserve all current tests except the table primitive assertions that still target next slice。
3. `P034-phase-6-import-pages-preview-tables`
   - Migrate main preview, detail preview and ETC preview from MUI X DataGrid to `FinanceTable` + `useFinanceTableSession` or an import preview table wrapper。
   - Preserve grid accessible names, headers, row text, loading state and scroll/session restore where user-visible。
4. `P035-phase-6-import-pages-dialog-tabs`
   - Migrate conflict confirmation dialog to `AppDialog` and detail tabs to HeroUI/project tabs if not completed earlier。
5. `MG-phase-6-import-pages`
   - Run import tests, table/common/platform regressions, build, import scope MUI grep, docs update, exact stage, commit and push。

## Risks

- `ImportWorkflowPage.tsx` is a large shared component for three routes; changing it affects bank, invoice and ETC imports simultaneously。
- MUI X DataGrid currently carries column sizing, toolbar, sorting/filter menu and scroll/session state. If old UI does not expose every DataGrid feature as a visible requirement, do not overbuild hidden feature parity。
- Native file input and drag/drop behavior must remain intact; tests use `user.upload` and labels。
- ETC ready-task and stale preview flows depend on API state and draft context; do not change contexts or backend contracts。
- Conflict dialog only appears for bank account conflicts; characterization should lock it before migration。
- The page has many inline `sx` hard-coded colors; CSS migration must use design tokens and avoid affecting frozen workbench CSS。

## P032 Prompt Draft

```text
Prompt ID: P032-phase-6-import-pages-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只调整 ImportCenterPage tests，锁定导入页族 HeroUI/native primitive contract；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_import_pages.md、docs/refactor-ui/test_migration_strategy.md、web/src/test/ImportCenterPage.test.tsx、web/src/components/imports/ImportWorkflowPage.tsx、web/src/components/common/FinanceTable.tsx、web/src/components/common/AppDialog.tsx 和 web/src/app/styles.css。只修改 `web/src/test/ImportCenterPage.test.tsx`，新增或调整断言：standalone import page shell 使用 project class 且不是 MUI root；action bar 按钮位置/名称保留；upload zone 使用 project class 且不是 MUI Box；feedback/error/confirm notices 不是 `.MuiAlert-root`；audit summary cards 使用 project class；preview tables 使用 project/FinanceTable contract 而不是 `.MuiDataGrid-root`；detail tabs 使用 project/HeroUI tabs contract；银行账户冲突确认仍是 dialog 且不是 `.MuiDialog-root`。不得修改实现、后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run ImportCenterPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P033 shell/forms refactor prompt。
```

## Verification For P031

- `test -f docs/refactor-ui/modules/phase_6_import_pages.md`
- `rg -n "P031-phase-6-import-pages-discovery|Current MUI Inventory|User-visible Entrypoints|P032-phase-6-import-pages-characterization-tests|DataGrid|银行账户冲突确认" docs/refactor-ui/modules/phase_6_import_pages.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
- `git diff --check`
- `git status --short --branch`
