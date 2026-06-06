# Phase 5 Table System Discovery

本文档记录 Phase 5 表格系统迁移的现场 discovery。它不替代 `docs/refactor-ui/table_layout_system.md`，而是把当前代码、测试、风险和后续 prompt 顺序落到可执行队列。

Last updated: 2026-06-07

## Boundary

- Scope: 非关联台表格系统、表格内容排版规则、表格测试迁移策略和后续切片队列。
- Non-scope: 不迁移任何业务页面实现，不改后端、API contract、read model、worker、权限语义或业务状态机。
- Frozen area: `ReconciliationWorkbenchPage` 和 `web/src/components/workbench/*` 仍冻结。关联台内部的 `grid-table`、三栏工作区、行交互、内部弹窗和专用 CSS 不纳入 Phase 5。
- User equivalence: 旧 UI 是表格时，新 UI 仍是表格；旧右侧抽屉仍是右侧抽屉；旧行点击、按钮、分页、筛选、导入、导出、确认、选择入口不得丢失。
- Library target: HeroUI Table + Tailwind token classes。不要引入 TanStack Table、TanStack Virtual 或其它表格库。

## Current Inventory Buckets

### DataGrid-heavy

这些模块依赖 `@mui/x-data-grid` 或 `useMuiDataGridPageSession`，迁移前必须先建立 session 替代策略，不能直接逐文件替换。

| Area | Files | Notes |
| --- | --- | --- |
| 成本统计 | `web/src/pages/CostStatisticsPage.tsx`, `web/src/components/cost-statistics/CostStatisticsTable.tsx` | `CostStatisticsTable` 使用 DataGrid、排序、行点击、scroll session、金额复合单元格。 |
| 导入页族 | `web/src/components/imports/ImportWorkflowPage.tsx` | 多个 preview/detail DataGrid session，涉及上传、预览、确认、错误详情。 |
| 设置项目 | `web/src/components/settings/SettingsProjectsSection.tsx` | DataGrid editable row 或表格式设置入口。 |
| 设置接入账号 | `web/src/components/settings/SettingsAccessAccountsSection.tsx` | DataGrid row model、编辑、保存、权限提示。 |
| Session hook | `web/src/hooks/useMuiDataGridPageSession.ts`, `web/src/test/useMuiDataGridPageSession.test.tsx` | 绑定 MUI DataGrid apiRef、initialState、pagination/sort/filter/selection/column/scroll state。 |

### MUI Table Dense Finance Tables

这些页面已经是 MUI Table，适合在 FinanceTable primitives 和 characterization tests 后逐个迁移。

| Area | Files | Notes |
| --- | --- | --- |
| 银行明细 | `web/src/pages/BankDetailsPage.tsx` | 交易流水表、分页、日期筛选、导出菜单、自动标签规则右侧抽屉；测试目前断言 MUI Table/source。 |
| 进项发票使用 | `web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx`, `web/src/pages/InputInvoiceUsagePage.tsx` | 分组表头、分页、可展开长文本、详情右侧抽屉、筛选菜单；高密度排版。 |
| 销项发票收款 | `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx`, `web/src/pages/OutputInvoiceCollectionsPage.tsx` | 分组表头、排序、分页、详情/规则/历史右侧抽屉。 |
| 免 OA 批量 | `web/src/pages/NoOaBankBatchPage.tsx` | 批量选择、确认、状态反馈。 |
| 批量账务 | `web/src/pages/BatchAccountingPage.tsx` | 双 bucket 表格、选择、搜索、撤回弹窗、Snackbar。 |
| ETC 票据 | `web/src/pages/EtcTicketManagementPage.tsx` | 导入、对账、确认、空/错误状态。 |
| 设置 OA 手工反查 | `web/src/components/settings/OaManualSearchImportTable.tsx` | 设置页内导入/搜索表格，测试已存在。 |
| 输出发票规则抽屉 | `web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx` | 右侧抽屉内部规则表；迁移时抽屉形态必须保持。 |

### Operational Tables

这些不是核心财务明细表，但仍应复用 FinanceTable 或轻量 table primitives，避免继续写 MUI Table。

| Area | Files | Notes |
| --- | --- | --- |
| 系统状态 | `web/src/pages/AppHealthOperationsPage.tsx` | 多个小型状态表，适合低风险迁移。 |
| 税金抵扣 | `web/src/pages/TaxOffsetPage.tsx`, `web/src/components/tax/*` | 上传、认证导入弹窗、结果右侧抽屉和表格状态。 |
| 待找发票 / OA 待付款 / 外部往来款 | `web/src/pages/PendingInvoicesPage.tsx`, `web/src/pages/OaPendingPaymentsPage.tsx`, `web/src/pages/TurnoverLedgerPage.tsx` | 含表格、右侧抽屉、筛选、关系/规则动作；需要页面级 discovery 后迁移。 |

### Frozen Or Out Of Phase

- `web/src/components/workbench/*`: 关联台内部工作区冻结，本次不迁 HeroUI。
- 现有 MUI X date picker compat provider: Phase 4 后保留的临时兼容层，不属于 Table system；必须在后续 date/session 或页面迁移切片里收口。

## HeroUI Table Facts

HeroUI v3 Table 使用 compound API：

- `Table`
- `Table.ScrollContainer`
- `Table.Content`
- `Table.Header`
- `Table.Column`
- `Table.Body`
- `Table.Row`
- `Table.Cell`
- `Table.Footer`

可用能力：

- `Table.Column allowsSorting` + `Table.Content sortDescriptor/onSortChange`。
- `Table.Content selectionMode/selectedKeys/onSelectionChange`，选择框用 `Checkbox slot="selection"`。
- `Table.Footer` 可放 HeroUI `Pagination`。
- 横向滚动由 `Table.ScrollContainer` 和 `Table.Content className="min-w-[...]"` 承载。

执行原则：

- 只迁移旧 UI 用户可见能力。旧页面没有可见 DataGrid filter panel 时，不为 HeroUI Table 复刻隐藏 filter model。
- 旧页面分页位置和文案保持等价；HeroUI Pagination 只替换表现和可访问交互，不改变业务 page/pageSize 语义。
- 旧页面有行点击详情时，`Table.Row` 或第一列按钮必须保留同等入口和可访问名称。

## Table Content Layout Contract

### Column Role Alignment

- `identity`、`account`、`description`: left。
- `amount`、`quantity`: right，强制 tabular nums。
- `date`、`status`、`direction`、`selection`: center。
- `action`: center 或 right，按旧页面位置保持。

不要再延续旧的“全局居中所有 MUI/DataGrid cell”策略。`web/src/test/TableAlignmentStyles.test.ts` 当前仍断言 MUI/DataGrid/grid-table 全局居中，P017 必须改为按 finance table column role 断言。

### Amount And Direction

- 金额主值使用 `font-variant-numeric: tabular-nums`，右对齐，稳定行高。
- 金额展示统一千分位，两位小数；无法解析时显示 `EmptyValue` 或原始业务文案，不在页面内临时 invent 文案。
- 收入/支出 `DirectionTag` 固定高度 `22px`，固定最小宽度，文字必须存在，不能只靠颜色。
- 复合金额单元格使用固定槽位：
  - amount row: 右对齐金额。
  - meta row: `DirectionTag` + account/source tag。
  - 当同一表格上下行出现收入/支出时，方向 tag 的宽度和起点必须一致。
  - 当一个复合单元格需要同时展示上下收支或借贷对照时，使用两行固定 grid slot，不允许由 tag 文案撑开导致上下错位。

### Dense Text Cells

- 长文本列使用单行或两行截断，并配 Tooltip 或旧详情抽屉查看完整内容。
- 主体对象列使用 `EntityCell`: 主值 + metadata，不在页面内散落 `<span>` 组合。
- 空值使用 `EmptyValue`，同一语义只允许一种文案。

### Grouped Headers

分组表头必须保留业务分组和视觉分隔，例如“进项发票 / 支付状态 / OA / 流水”。HeroUI Table 迁移时可以用 `Table.Column` 的 `colSpan` 能力或受控 header rows；如果 HeroUI 当前 API 不满足复杂分组表头，优先用语义 table + project classes 封装在 FinanceTable 内，不要在业务页面直接拼一套私有 table 体系。

## Session Replacement Strategy

`useMuiDataGridPageSession` 不能作为 HeroUI Table 的长期 hook。后续应新增 `useFinanceTableSession` 或等价 table session primitive，保留用户能感知的状态：

- page/pageSize。
- sort descriptor，仅限旧页面有可见排序时。
- row selection，仅限旧页面有选择行为时。
- horizontal/vertical scroll restoration。
- column widths/order/visibility，仅限旧页面提供可见列调整或当前业务强依赖稳定列宽时。

不需要迁移：

- MUI DataGrid 内部 filter model，除非旧页面有用户可见 filter panel。
- MUI apiRef imperative calls，除非它们对应可见 scroll/focus/restore 行为。
- MUI column menu、density selector、export toolbar 等未在旧 UI 暴露的能力。

## Suggested Migration Order

1. `P017-phase-5-table-characterization-tests`: 改写表格对齐测试，新增 FinanceTable/Finance cell contract characterization tests。允许先失败，证明缺口存在。
2. `P018-phase-5-finance-table-primitives`: 新增 `FinanceTable`、`FinanceTablePagination`、`TableCellStack`、`AmountCell`、`DirectionTag`/`FinanceTag` bridge、`EmptyValue` 等 primitives 和 CSS token classes，让 P017 tests 通过。
3. `P019-phase-5-table-session-primitive`: 新增 `useFinanceTableSession`，覆盖 page/pageSize/sort/selection/scroll restore。不要迁业务 DataGrid 页面。
4. 低风险 operational table: `AppHealthOperationsPage` 或单一设置内表格，验证 HeroUI Table 形态。
5. 中风险 MUI Table: `BankDetailsPage` 或 `InputInvoiceUsageTable` 单模块迁移。
6. 高风险 dense grouped tables: `OutputInvoiceCollectionsTable`、批量/ETC/待找发票等按模块 discovery 逐个迁移。
7. DataGrid-heavy modules: `CostStatisticsTable`、`ImportWorkflowPage`、settings DataGrid，在 session primitive 验证后逐个迁移。

## Testing Strategy

必须从 MUI class/theme/source 断言迁移为用户可观察行为和 design-token/role 断言：

- Table role/name: `getByRole("table", { name: ... })` 或 HeroUI 对应语义。
- Header text、row text、操作按钮、分页 summary、page size 控件。
- 金额列右对齐、tabular nums、空值和长文本截断 class。
- 状态/方向 tag 文案和 tone data attribute。
- 旧右侧抽屉仍从旧入口打开，且 placement 仍为 right。
- loading/empty/error/permission/stale 状态。
- 搜索、筛选、排序、分页、选择、行点击和导出/确认入口。

需要逐步替换的现有测试：

- `web/src/test/TableAlignmentStyles.test.ts`: 从 MUI/DataGrid 全局居中改为 FinanceTable column roles。
- `web/src/test/BankDetailsPage.test.tsx`: 不再断言源码含 `<Table aria-label="交易流水"` 或无 DataGrid；改为行为和 table semantics。
- `web/src/test/InputInvoiceUsagePage.test.tsx`: 不再描述 dense MUI Table；改为分组表头、详情抽屉、分页和金额/状态行为。
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx`: 不再描述 MUI Table；改为 grouped table semantics 和旧操作入口。
- `web/src/test/CostStatisticsPage.test.tsx` 与 `useMuiDataGridPageSession.test.tsx`: 在 table session primitive 到位后迁移。

## Risks

- HeroUI Table API 与复杂 `colgroup`/多行分组表头可能不完全等价。应把兼容层封装在 FinanceTable 内，业务页面不直接发散。
- DataGrid session hook 当前承载 scroll restore 和多个 model；替换时必须用 tests 锁定用户能感知的状态。
- 旧 CSS 有大量 MUI/DataGrid class overrides；迁移后需要删除或隔离，避免影响 HeroUI Table。
- 页面较多且表格密度高，不能在一个 prompt 中迁多个业务模块。
- Workbench 内部也有 table-like CSS，但冻结；全局 CSS 调整不得破坏它。

## P017 Prompt Draft

```text
Prompt ID: P017-phase-5-table-characterization-tests
Phase: phase_5_table_system
Type: characterization tests
Scope: 只处理表格系统测试契约，不实现 FinanceTable primitives，不迁业务页面。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/test_migration_strategy.md、DESIGN.md、web/src/app/styles.css、web/src/test/TableAlignmentStyles.test.ts、web/src/components/cost-statistics/CostStatisticsTable.tsx、web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx 和 web/src/hooks/useMuiDataGridPageSession.ts。使用 HeroUI MCP Table/Chip/Tooltip/Pagination docs 核对 Table compound API、sorting、selection 和 footer pagination。

把 TableAlignmentStyles.test.ts 从 MUI/DataGrid/grid-table 全局居中断言改为 FinanceTable column role contract：amount/quantity right + tabular nums、date/status/direction/selection center、identity/account/description left、DirectionTag 固定槽位、EmptyValue 文案统一、HeroUI/Tailwind table tokens 存在。可以新增 web/src/test/FinanceTableContract.test.ts 或等价测试文件；不得修改业务页面、CSS 实现、依赖、后端、API、read model、worker 或关联台内部工作区。

运行 targeted Vitest，预期在 FinanceTable primitives 未实现前失败；再运行 git diff --check 和 git status。更新 refactor_ui_state.md、refactor_ui_prompt.md 和 phase_5_table_system.md，记录失败断言和下一条 P018 implementation prompt 建议。
```

## P017 Execution Notes

- Status: verified expected-fail。
- Changed file: `web/src/test/TableAlignmentStyles.test.ts`。
- Old assertion removed: MUI theme/DataGrid/grid-table global centering。
- New contract: FinanceTable shell, column role alignment, amount tabular nums/right alignment, DirectionTag fixed slot, EmptyValue muted style。
- Verification: `cd web && npx vitest run TableAlignmentStyles.test.ts`。
- Result: expected fail。
- Failure evidence:
  - Missing CSS block for `.finance-table`。
  - Missing CSS block for `.finance-table__cell[data-column-role="identity"]`。
  - Missing CSS block for `.finance-amount-cell`。

## P018 Prompt Draft

```text
Prompt ID: P018-phase-5-finance-table-primitives
Phase: phase_5_table_system
Type: extraction/refactor
Scope: 只实现 FinanceTable CSS contract 和共享 table cell primitives，让 P017 tests 通过；不迁业务页面。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/modules/phase_5_table_system.md、DESIGN.md、web/src/app/styles.css、web/src/test/TableAlignmentStyles.test.ts 和 web/src/components/common。使用 HeroUI MCP Table、Chip、Tooltip、Pagination docs 核对 API。只新增或修改共享表格 primitives 和 CSS：FinanceTable、FinanceTablePagination、TableCellStack、AmountCell、FinanceDirectionTag、FinanceStatusTag、EmptyValue 或等价命名；补齐 `.finance-table`、按 column role 的 `.finance-table__cell[data-column-role="..."]`、`.finance-amount-cell`、`.finance-direction-tag`、`.finance-empty-value` CSS contract。不得迁移业务页面、DataGrid 页面、后端、API、read model、worker 或关联台内部工作区。

运行 `cd web && npx vitest run TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx`、`cd web && npm run build`、MUI import grep、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，记录下一条 P019 table session primitive prompt。
```

## P018 Execution Notes

- Status: verified。
- Added file: `web/src/components/common/FinanceTable.tsx`。
- Updated CSS: `web/src/app/styles.css`。
- Updated tests: `web/src/test/TableAlignmentStyles.test.ts`。
- Added shared primitives:
  - `FinanceTable` / `FinanceTableColumn` / `FinanceTableCell` / `FinanceTablePagination`。
  - `TableCellStack` / `AmountCell`。
  - `FinanceDirectionTag` / `FinanceStatusTag` / `EmptyValue` / `TruncatedCellText`。
- CSS contract added:
  - `.finance-table` shell and scroll/content/footer classes。
  - `.finance-table__cell[data-column-role="..."]` alignment classes。
  - `.finance-amount-cell` tabular/right alignment and fixed direction slot。
  - `.finance-direction-tag` fixed height/min-width。
  - `.finance-empty-value` muted empty display。
- Verification:
  - `cd web && npx vitest run TableAlignmentStyles.test.ts`: passed。
  - `cd web && npx vitest run TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx`: passed, 15 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/' web/src/components/common; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。
- Not changed: business pages, DataGrid pages, backend, API, read model, worker, workbench internals。

## P019 Prompt Draft

```text
Prompt ID: P019-phase-5-table-session-primitive
Phase: phase_5_table_system
Type: characterization tests -> extraction/refactor
Scope: 新增 HeroUI table session primitive，替代 MUI DataGrid session 的用户可见状态；不迁业务页面。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/hooks/useMuiDataGridPageSession.ts、web/src/test/useMuiDataGridPageSession.test.tsx、web/src/contexts/PageSessionStateContext.tsx、web/src/contexts/pageSessionStorage.ts 和 web/src/components/common/FinanceTable.tsx。只新增 `useFinanceTableSession` 或等价 hook 及 tests，覆盖用户可见 table 状态：page/pageSize、sort descriptor、row selection、scroll position restore。不要迁移 CostStatistics、ImportWorkflow、settings DataGrid 或任何业务页面；不要删除 `useMuiDataGridPageSession`。

运行新 table session tests、`useMuiDataGridPageSession.test.tsx` 回归、P018 table/common/platform tests、build、MUI import grep、`git diff --check`、`git status --short --branch`。更新 state/prompt/module docs，记录下一条低风险 table pilot migration prompt。
```

## P019 Execution Notes

- Status: verified。
- Added hook: `web/src/hooks/useFinanceTableSession.ts`。
- Added tests: `web/src/test/useFinanceTableSession.test.tsx`。
- Session model:
  - 1-based `page` / `pageSize` for HeroUI Pagination。
  - `sortDescriptor` with `ascending` / `descending`。
  - `selectedRowIds` filtered by current valid row ids。
  - native scroll container `top` / `left` restore。
- Existing MUI hook retained: `useMuiDataGridPageSession` unchanged。
- Business pages not migrated。
- Verification:
  - `cd web && npx vitest run useFinanceTableSession.test.tsx`: passed, 4 tests。
  - `cd web && npx vitest run useFinanceTableSession.test.tsx useMuiDataGridPageSession.test.tsx TableAlignmentStyles.test.ts HeroUIPlatformSmoke.test.tsx CommonMuiComponents.test.tsx`: passed, 23 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/' web/src/hooks/useFinanceTableSession.ts web/src/test/useFinanceTableSession.test.tsx web/src/components/common/FinanceTable.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。

## P020 Prompt Draft

```text
Prompt ID: P020-phase-5-app-health-table-pilot-discovery
Phase: phase_5_table_system
Type: discovery/planning
Scope: 只做 AppHealthOperationsPage 表格 pilot discovery；不迁移页面实现。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/AppHealthOperationsPage.tsx、web/src/test/AppHealthOperationsPage.test.tsx、web/src/components/common/FinanceTable.tsx 和 web/src/hooks/useFinanceTableSession.ts。只做 AppHealthOperationsPage table pilot discovery/planning，记录旧页面表格清单、列角色、用户可见入口、loading/empty/error 状态、MUI imports、测试断言、应复用的 FinanceTable primitives 和下一条 P021 characterization/refactor prompt。不得迁移页面实现，不改后端/API/read model/worker/关联台。

更新 docs/refactor-ui/modules/phase_5_table_system.md、refactor_ui_state.md、refactor_ui_prompt.md。运行文档/key grep、git diff --check、git status。
```

## P020 Execution Notes

- Status: verified。
- Scope: AppHealthOperationsPage table pilot discovery only。
- Runtime code changed: no。
- Files read:
  - `web/src/pages/AppHealthOperationsPage.tsx`。
  - `web/src/test/AppHealthOperationsPage.test.tsx`。
  - `web/src/components/common/FinanceTable.tsx`。
  - `web/src/hooks/useFinanceTableSession.ts`。

### AppHealth Table Inventory

| Table | Component | Current UI | Columns | Column roles | Notes |
| --- | --- | --- | --- | --- | --- |
| Inventory sources | `InventorySourceRows` | MUI Table | 来源, 数量, 同步 | identity, quantity, date | Rendered three times for bank/invoice/OA blocks. |
| Request performance | `RequestPerformance` | MUI Table | 接口, 样本, API p95, API p99, DB p95, DB p99, SQL p95, 连接 p95 | identity/description, quantity, status/date-like metric | Performance cells carry `data-tone` and must preserve tone assertions. |
| Outbox | `OutboxTable` | MUI Table | Outbox, 值 | identity, quantity | `oldest_pending` displays seconds, others numbers. |
| Queue | `QueueTable` | MUI Table | RabbitMQ, queue, ready, unacked, consumer, DLQ | identity, description, quantity | Long queue names need truncation/wrap behavior. |
| Read Model | `ReadModelTable` | MUI Table | Read Model, 15m p95, 15m p99, 历史 p95, 15m 样本, stale, unavailable | identity, status metric, quantity | Reuses `PerformanceCell` and `sampleLabel` empty behavior. |
| Worker | `WorkerTable` | MUI Table | Worker, lag | identity, quantity/date metric | Has explicit empty row when no workers. |
| Performance cell | `PerformanceCell` | MUI TableCell + custom inline badge | p95/p99 metric cell | status | Must preserve `data-tone=green/yellow/red/unknown` on nearest cell or stable equivalent tested by `AppHealthOperationsPage.test.tsx`. |

### User-visible Entries

- Page route: `/operations/app-health`。
- Heading: `AppHealth 运维状态`。
- Refresh button: `aria-label="刷新"`; disabled/loading state when refresh in flight。
- Admin permission gate: non-admin sees warning and dashboard API is not fetched。
- Loading/empty: when payload absent and no error, page shows `正在加载。`。
- Error refresh: failed refresh keeps current dashboard visible and shows alert text。
- No row click, no pagination, no selection, no drawer, no dialog, no export。

### P021 Scope Recommendation

P021 should migrate only AppHealth table surfaces and related table metric cell styling:

- Replace MUI `Table`, `TableContainer`, `TableHead`, `TableBody`, `TableRow`, `TableCell` in AppHealth table components with `FinanceTable` primitives。
- Keep existing page-level MUI `Alert`、`Box`、`IconButton`、`Stack`、`Tooltip`、`Typography` for later page-module migration unless required by table extraction。
- Preserve section layout and refresh behavior。
- Preserve all current tests in `AppHealthOperationsPage.test.tsx` without weakening behavior assertions。
- Add or update table semantics assertions if FinanceTable changes accessible table names。
- Do not touch API, fetch mocks, read model, worker, session permissions, workbench internals。

## P021 Prompt Draft

```text
Prompt ID: P021-phase-5-app-health-table-pilot-refactor
Phase: phase_5_table_system
Type: characterization tests -> extraction/refactor
Scope: 只迁移 AppHealthOperationsPage 的表格 surfaces 到 FinanceTable primitives；不做整页 HeroUI 化。

读取 docs/refactor-ui/refactor_ui_state.md、docs/refactor-ui/refactor_ui_prompt.md、docs/refactor-ui/modules/phase_5_table_system.md、docs/refactor-ui/table_layout_system.md、docs/refactor-ui/test_migration_strategy.md、web/src/pages/AppHealthOperationsPage.tsx、web/src/test/AppHealthOperationsPage.test.tsx、web/src/components/common/FinanceTable.tsx。先补或调整 AppHealthOperationsPage.test.tsx 中表格语义/列入口断言，保留现有 admin gate、refresh failure、unknown metrics 和 data-tone 断言。然后只替换 AppHealth 的 MUI Table/TableContainer/TableHead/TableBody/TableRow/TableCell 为 FinanceTable primitives 和 table CSS classes；保留页面级 MUI Alert/Box/IconButton/Stack/Tooltip/Typography 到后续页面模块迁移。不得改后端/API/read model/worker/关联台。运行 AppHealthOperationsPage.test.tsx、TableAlignmentStyles.test.ts、CommonMuiComponents.test.tsx、build、AppHealth 表格 MUI import grep、git diff --check、git status。更新 state/prompt/module docs。
```

## P021 Execution Notes

- Status: verified。
- Changed runtime files:
  - `web/src/pages/AppHealthOperationsPage.tsx`。
  - `web/src/components/common/FinanceTable.tsx`。
- Changed tests:
  - `web/src/test/AppHealthOperationsPage.test.tsx`。
- AppHealth table surfaces migrated:
  - Inventory source tables。
  - Request performance table。
  - Outbox table。
  - Queue table。
  - Read Model table。
  - Worker table。
  - Performance metric cells。
- Test adjustment:
  - HeroUI Table exposes `role="grid"` through React Aria, not `role="table"`。
  - Tests now assert accessible grid names: `银行流水来源`、`发票来源`、`OA来源`、`请求性能`、`Outbox 状态`、`RabbitMQ 队列`、`Read Model 刷新`、`Worker 心跳`。
- Preserved:
  - Admin permission gate。
  - Refresh button behavior。
  - Refresh failure keeps existing dashboard visible。
  - Unknown metrics render as `--`。
  - `data-tone` on metric cells。
- Deferred:
  - Page-level MUI `Alert`、`Box`、`IconButton`、`Stack`、`Tooltip`、`Typography` remain for Phase 6 page-module migration。
- Verification:
  - `cd web && npx vitest run AppHealthOperationsPage.test.tsx`: failed then passed after role assertion changed from `table` to `grid`。
  - `cd web && npx vitest run AppHealthOperationsPage.test.tsx TableAlignmentStyles.test.ts CommonMuiComponents.test.tsx`: passed, 18 tests。
  - `cd web && npm run build`: passed with known HeroUI/Tailwind generated CSS minifier warnings and chunk size warning。
  - `if rg -n '@mui/material/(Table|TableBody|TableCell|TableContainer|TableHead|TableRow)' web/src/pages/AppHealthOperationsPage.tsx; then exit 1; else exit 0; fi`: passed。
  - `git diff --check`: passed。

## Phase 5 Closeout

Phase 5 table system is ready for MG-P021 after these completed slices:

- P016 discovery: table inventory and migration queue。
- P017 characterization: FinanceTable CSS/role tests。
- P018 primitives: FinanceTable, cell primitives, CSS contract。
- P019 session: `useFinanceTableSession` and tests。
- P020 pilot discovery: AppHealth table pilot。
- P021 pilot refactor: AppHealth table surfaces migrated。

After MG-P021 is pushed and verified, continue with `P022-phase-6-tax-offset-discovery`.
