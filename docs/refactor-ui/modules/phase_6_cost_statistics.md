# Phase 6 Cost Statistics Discovery

本文档记录成本统计页迁移和 premium visual discovery。当前 `main` 上 `/cost-statistics` 已完成核心表格平台迁移；下一步目标是在保留四种视图、范围筛选、下钻、详情弹窗和导出中心行为的前提下，做 Ledger Calm premium visual polish。

Last updated: 2026-06-08

## Boundary

- Scope: `/cost-statistics`、`web/src/pages/CostStatisticsPage.tsx`、`web/src/components/cost-statistics/*`、`web/src/test/CostStatisticsPage.test.tsx`。
- Non-scope: 不改后端、API contract、read model、worker、成本统计业务规则、导出参数语义、关联台内部工作区。
- Behavior equivalence:
  - 旧页面仍是 standalone 成本统计页面，不改路由、不改 App Shell。
  - 旧四个视图仍是同一页内 tabs/buttons：`按时间`、`按项目`、`按银行`、`按费用类型`。
  - 旧范围切换仍是浮动面板，不改为抽屉或弹窗。
  - 旧详情为 `流水详情` 弹窗，新 UI 仍是弹窗。
  - 旧导出为 `导出中心` 弹窗，新 UI 仍是弹窗。
  - 旧统计结果仍是表格或左中右下钻列表，不改成卡片流。
  - 旧行点击/首列按钮进入流水详情的能力必须保留。

## Current Platform Inventory

| Usage | Current file | Migration target | Notes |
| --- | --- | --- | --- |
| Generic table | `CostStatisticsTable.tsx` | Already `FinanceTable` | Powers time/project/bank/expense transaction grids and keeps first-cell `查看流水 <id>` actions。 |
| Page state | `CostStatisticsPage.tsx` | `usePageSessionState` | Keeps view/scope/date selections; retain it。 |
| View switcher | `CostStatisticsPage.tsx` | Project button tabs | Four view buttons plus project scope toggle。 |
| Scope controls | `CostStatisticsPage.tsx` | Project floating panels + `MonthPicker` | Year/month/custom panels stay floating, not drawer/dialog。 |
| Summary counters | `CostStatisticsSummaryCards.tsx` | Project `stat-card` | Needs premium compact counter treatment, not dashboard cards。 |
| Drilldown lanes | `CostExplorerList.tsx` | Project list lanes | Needs tighter row density and motion-token selection/hover polish。 |
| Detail dialog | `CostTransactionDetailModal.tsx` | Project modal | Already `role="dialog"` with `cost-detail-modal` root。 |
| Export center | `ExportCenterModal.tsx` | Project modal | Already `role="dialog"` with project controls and preview table。 |

Already non-MUI/project-owned:

- `CostExplorerList.tsx` uses native buttons and project classes。
- `CostStatisticsSummaryCards.tsx` uses project stat cards。
- `CostTransactionDetailModal.tsx` is a project modal with `role="dialog"`。
- `CostTransactionDetailPanel.tsx` is project layout plus `BankAccountValue` / `DirectionTag`。
- `ExportCenterModal.tsx` is a project modal with native inputs/buttons and a native preview table。

## User-visible Entrypoints

- Page heading: `成本统计`。
- Header action: `导出中心`。
- Top view switcher:
  - `按时间`
  - `按项目`
  - `按银行`
  - `按费用类型`
  - `项目范围：进行中` / `项目范围：所有项目`
- Summary cards:
  - active row label such as `时间流水`、`项目数`、`银行账户数`、`费用类型数`
  - `支出流水`
  - `支出总额`
- Scope controls:
  - `全部时间`
  - `按年统计`
  - `按月统计`
  - `自定义时间段`
  - Floating panels for year, month and date range。
- Table surfaces:
  - `按时间统计表`
  - `项目对应流水表`
  - `银行对应流水表`
  - `按费用类型流水表`
  - each row keeps `查看流水 <transactionId>` action。
- Drilldown list surfaces:
  - `项目名`
  - `费用类型`
  - `银行账户`
- Dialogs:
  - `流水详情`
  - `导出中心`
- Export center:
  - view switcher `按时间` / `按项目` / `按费用类型`
  - range controls
  - project / expense type multi-select groups
  - `仅预览`
  - `导出`
  - `导出预览表`
  - success/error feedback inside modal。
- States:
  - `正在加载成本统计数据...`
  - `正在加载流水 <id> 的详情...`
  - `成本统计数据加载失败，请稍后重试。`
  - `成本统计数据暂不可用。`
  - empty messages per view。

## Existing Test Coverage

`web/src/test/CostStatisticsPage.test.tsx` covers:

- Default time view loads month-aware transaction rows and changes month。
- Project view drills down project -> expense type -> transaction and opens/closes `流水详情`。
- Project view supports all/year/month/custom scope controls。
- Expense type view shows transaction table and modal drilldown。
- Empty state when selected month has no rows。
- Bank view drilldown bank -> project -> transaction and scope changes。
- Time and expense type scopes stay independent。
- Scope picker floating panel and close behavior。
- Existing content remains visible during background refresh。
- Explorer loading error state。
- Refreshing read model does not display final empty data。
- Export center time/project/expense type preview and export flows。

Current premium gaps:

- Tests already assert page shell/view switcher, `FinanceTable` roots and project dialogs are not MUI roots。
- Tests already cover time/project/bank/expense views, range controls, drilldown, detail modal, loading/error/read-model refreshing states and export center flows。
- Tests do not yet lock premium compact visual treatment for cost summary counters, view toolbar, scope toggles, explorer lanes and cost table shell。
- Tests do not yet lock local interaction smoothness tokens for view tabs、scope buttons、explorer items、row triggers、detail/export modal buttons。
- Current visual style still risks feeling like older dense utility CSS rather than the bank-details premium sample: summary cards, explorer lanes and section shells need better alignment, lower shadow/card emphasis and more consistent table rhythm。

## PV-008 Premium Visual Discovery

Prompt ID: `PV-008-cost-statistics-discovery`

Current source files:

- `web/src/pages/CostStatisticsPage.tsx`
- `web/src/components/cost-statistics/CostStatisticsTable.tsx`
- `web/src/components/cost-statistics/CostExplorerList.tsx`
- `web/src/components/cost-statistics/CostStatisticsSummaryCards.tsx`
- `web/src/components/cost-statistics/CostTransactionDetailModal.tsx`
- `web/src/components/cost-statistics/ExportCenterModal.tsx`
- `web/src/test/CostStatisticsPage.test.tsx`
- `web/src/app/styles.css`

Current implementation status on `main`:

- Runtime table surfaces already use `FinanceTable`, not MUI DataGrid。
- Tests already lock `按时间统计表`、`项目对应流水表`、`银行对应流水表`、`按费用类型流水表` as project/FinanceTable grids。
- `流水详情` and `导出中心` are project dialogs, not MUI dialogs。
- Page still uses `usePageSessionState` for view/scope state, which is intentionally retained by the global plan。

User-visible entrypoint matrix:

| Area | Current UI | Must preserve |
| --- | --- | --- |
| Route | `/cost-statistics` | Standalone route inside App Shell。 |
| Page header | `成本统计`, supporting copy, `导出中心` | Header action remains top-right. |
| Summary | `CostStatisticsSummaryCards`: active row count, `支出流水`, `支出总额` | Keep compact counters; do not convert to large dashboard cards. |
| View switcher | `按时间`, `按项目`, `按银行`, `按费用类型`, project scope toggle | Same view modes and selected state. |
| Scope controls | `全部时间`, `按年统计`, `按月统计`, `自定义时间段` | Floating panel stays floating; not drawer/dialog. |
| Time table | `按时间统计表` | `FinanceTable`, row click and `查看流水 <id>` action remain. |
| Project drilldown | `项目名` lane -> `费用类型` lane -> `项目对应流水表` | Left-to-right drilldown remains. |
| Bank drilldown | `银行账户` lane -> `项目名` lane -> `银行对应流水表` | Left-to-right drilldown remains. |
| Expense drilldown | `费用类型` lane -> `按费用类型流水表` | Same table and detail action. |
| Detail overlay | `流水详情` | Dialog stays dialog; fields and close behavior preserved. |
| Export overlay | `导出中心` | Dialog stays dialog; preview/export flows preserved. |
| States | loading, error, unavailable, empty, refreshing-preserve-content | Same copy and non-blocking behavior. |

Table and layout requirements for PV-009:

- Amount cells remain `money-cell-stack` with amount, direction tag and optional bank account tag.
- Amount columns use `amount` role, right alignment and tabular nums through `FinanceTable`/money-cell styles.
- Time columns use date role; count columns use quantity role; account columns use account role.
- Explorer lane rows keep primary/secondary/meta hierarchy and selected state without changing row height.
- Scope floating panels must not take layout height and must remain anchored under their toggle row.
- Detail and export dialogs keep role/name/focusable controls and do not become drawers.
- Summary counters should be compact ledger counters, not large card metrics.

Premium visual opportunities for PV-009:

- Tighten `stats-row`/`stat-card` usage on this page or add cost-scoped summary classes so counters match import/tax/app-health density.
- Reduce ordinary section/card shadow emphasis in `.cost-content-shell`, `.cost-table-section`, `.cost-explorer-lane` and table shells.
- Add motion-token hover/press/focus treatment for `cost-export-button`, `cost-view-tab`, `cost-project-scope-trigger`, `cost-scope-toggle-btn`, `cost-explorer-item` and `cost-table-row-trigger`.
- Make explorer lanes feel like dense drilldown columns: stable header, compact rows, right-aligned amount/percentage metadata.
- Harmonize table shell spacing and row trigger treatment with bank details/import pages.
- Polish detail/export modal surfaces with existing project classes only where needed; do not rewrite modal behavior.

Non-scope for PV-009:

- Do not change cost APIs, export APIs, read model behavior, cache behavior, worker, route, session state shape, mock data, detail/export payloads or workbench internals.
- Do not change view mode semantics, scope state semantics, row selection semantics, or export query parameters.
- Do not replace `FinanceTable` with another table library.

## Migration Slices

1. `P037-phase-6-cost-statistics-characterization-tests`
   - Update `CostStatisticsPage.test.tsx` only。
   - Add primitive-contract assertions for CostStatistics page shell, summary cards, view switcher, scope panels, table surfaces, detail dialog and export dialog。
   - Assert CostStatistics runtime tables use project/FinanceTable contract and not `.MuiDataGrid-root`。
   - Assert the test render path no longer needs `MuiProviders` after implementation, but allow expected-fail before P038 if wrapper remains。
2. `P038-phase-6-cost-statistics-table-migration`
   - Migrate `CostStatisticsTable.tsx` from MUI X DataGrid to `FinanceTable` while preserving generic column contract, row click and first-cell action button。
   - Remove `DataGrid`, `GridColDef`, `GridRowParams`, `.MuiDataGrid-*` sx and MUI session binding prop。
3. `P039-phase-6-cost-statistics-session-provider-cleanup`
   - Remove `useMuiDataGridPageSession` / `useMuiDataGridScrollSession` from `CostStatisticsPage.tsx`。
   - Remove `MuiProviders` from `CostStatisticsPage.test.tsx` if no longer needed。
   - Verify detail/export dialogs remain project-owned and no runtime MUI remains in cost statistics scope。
4. `MG-P039-phase-6-cost-statistics`
   - Run CostStatistics tests, table/common/platform regressions, build, cost statistics scope MUI grep, docs update, exact stage, commit and push。

## Execution Update

- `P036-phase-6-cost-statistics-discovery`: CostStatistics page、`CostStatisticsTable`、detail/export modals、test coverage and MUI inventory recorded。
- `P037-phase-6-cost-statistics-characterization-tests`: updated `CostStatisticsPage.test.tsx` with project primitive assertions for page shell, summary/view controls, scope controls, cost table surfaces and project dialogs. Targeted test expected-failed with 4 failures, all caused by `CostStatisticsTable` still rendering MUI X DataGrid instead of `FinanceTable`。
- `P038-phase-6-cost-statistics-table-migration`: migrated `CostStatisticsTable` from MUI X DataGrid to `FinanceTable`, removed page-level MUI DataGrid session hook usage and removed cost DataGrid CSS residue. `CostStatisticsPage.test.tsx` now passes all 15 tests. Remaining `MuiProviders` test wrapper is required by shared `MonthPicker`, not by CostStatistics table runtime。

## Risks

- `CostStatisticsTable` is generic and reused across multiple view modes; column rendering must preserve `CostStatisticsAmountCell` behavior, `DirectionTag`, `BankAccountValue`, row action labels and row click semantics。
- MUI X DataGrid currently supplies grid role, column headers, no-row label, row height, sorting and scroll session binding. If sorting/session are not user-visible requirements, do not overbuild hidden feature parity, but keep accessible table/grid names and visible row actions。
- The page uses `usePageSessionState` for view/scope state; do not modify that state shape in table migration。
- Export center is already project-owned; avoid unnecessary rewrite。
- Detail modal is already project-owned; avoid unnecessary rewrite。

## P037 Prompt Draft

```text
Prompt ID: P037-phase-6-cost-statistics-characterization-tests
Phase: phase_6_page_batches
Type: characterization tests
Scope: 只更新 CostStatisticsPage tests，锁定成本统计页非 MUI/project primitive contract；不改实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_cost_statistics.md、docs/refactor-ui/test_migration_strategy.md、docs/refactor-ui/table_layout_system.md、web/src/pages/CostStatisticsPage.tsx、web/src/components/cost-statistics/CostStatisticsTable.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/test/CostStatisticsPage.test.tsx。只修改 `web/src/test/CostStatisticsPage.test.tsx`，新增或调整断言：页面 shell/summary cards/view switcher/scope panels 保留 project classes；`按时间统计表`、`项目对应流水表`、`银行对应流水表`、`按费用类型流水表` 使用 project/FinanceTable contract 且不是 `.MuiDataGrid-root`；`流水详情` 和 `导出中心` 仍是 dialog 且不是 MUI dialog；测试渲染 wrapper 的 MUI provider 依赖作为待迁移缺口记录。不得修改实现、后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run CostStatisticsPage.test.tsx`，实现未迁移前 expected-fail 可接受；运行 `git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，生成 P038 table migration prompt。
```

## P038 Prompt Draft

```text
Prompt ID: P038-phase-6-cost-statistics-table-migration
Phase: phase_6_page_batches
Type: extraction/refactor
Scope: 迁移 CostStatisticsTable 从 MUI X DataGrid 到 FinanceTable，保留 CostStatisticsPage 业务 flow。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_cost_statistics.md、docs/refactor-ui/table_layout_system.md、web/src/components/cost-statistics/CostStatisticsTable.tsx、web/src/pages/CostStatisticsPage.tsx、web/src/test/CostStatisticsPage.test.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/app/styles.css。只迁移 `CostStatisticsTable.tsx` 的表格实现和必要样式：移除 MUI X `DataGrid`、`GridColDef`、`GridRowParams`、`.MuiDataGrid-*` sx 和 `MuiDataGridScrollSessionBinding` prop；使用 `FinanceTable` primitives 保留 `ariaLabel`、column headers、empty label、row click、首列 `查看流水 <id>` action、amount/direction/account stack、row text 和 visible height/scroll behavior。暂不改 CostStatisticsPage 的 `useMuiDataGridPageSession` 调用，除非类型必须同步去除；如去除，必须不改变 view/scope page session state。不得改后端、API、read model、worker、mock 或关联台。运行 `cd web && npx vitest run CostStatisticsPage.test.tsx`，本切片结束后 P037 table primitive assertions 必须通过；如果只剩 test wrapper 的 `MuiProviders`/page session hook cleanup，记录为 P039。运行 focused table/common/platform tests、build、cost statistics runtime MUI grep、git diff --check、git status。更新 state/prompt/module docs，生成 P039 cleanup/MG prompt。
```

## P039 Prompt Draft

```text
Prompt ID: MG-P038-phase-6-cost-statistics-table-migration
Phase: phase_6_page_batches
Type: cumulative MG
Scope: 提交已验证的 CostStatistics table migration；记录共享 MonthPicker 间接 MUI 依赖留待 shared MonthPicker/global containment。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_6_cost_statistics.md 和 git status。检查当前分支必须是 refactor-ui。检查 untracked files、diff、测试结果和文档状态。确认 scope 只包含 P037/P038 文件：web/src/components/common/FinanceTable.tsx、web/src/components/cost-statistics/CostStatisticsTable.tsx、web/src/pages/CostStatisticsPage.tsx、web/src/app/styles.css、web/src/test/CostStatisticsPage.test.tsx、docs/refactor-ui/modules/phase_6_cost_statistics.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/refactor_ui_state.md。禁止 git add . 和 git add -A。只允许精确 git add 这些文件。验证命令：cd web && npx vitest run CostStatisticsPage.test.tsx；cd web && npx vitest run TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx HeroUIPlatformSmoke.test.tsx；cd web && npm run build；if rg -n '@mui/|Mui[A-Z]|MuiDataGrid|DataGrid|GridColDef|useMuiDataGrid' web/src/pages/CostStatisticsPage.tsx web/src/components/cost-statistics; then exit 1; else exit 0; fi；if rg -n 'cost-data-grid-shell|\\.cost-data-grid-shell|\\.MuiDataGrid' web/src/components/cost-statistics web/src/pages/CostStatisticsPage.tsx web/src/test/CostStatisticsPage.test.tsx; then exit 1; else exit 0; fi；git diff --check；git status --short --branch。提交信息使用 feat: migrate cost statistics table ui。push 到 refactor-ui 分支。完成后更新 docs 状态和 Push Log，标记 MG verified，并生成下一条 Phase 6 module prompt。
```

## Verification For P036

- `test -f docs/refactor-ui/modules/phase_6_cost_statistics.md`
- `rg -n "P036-phase-6-cost-statistics-discovery|Current MUI Inventory|User-visible Entrypoints|P037-phase-6-cost-statistics-characterization-tests" docs/refactor-ui/modules/phase_6_cost_statistics.md docs/refactor-ui/refactor_ui_prompt.md docs/refactor-ui/refactor_ui_state.md`
- `git diff --check`
- `git status --short --branch`
