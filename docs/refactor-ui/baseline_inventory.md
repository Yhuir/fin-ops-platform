# UI 基线清单

本文档记录 `refactor-ui` 分支迁移前的前端 UI 事实。后续每个 Micro-JIT prompt 必须先读本文，再读当前模块代码和测试。

Last updated: 2026-06-07

## 迁移口径

- 本次是 UI 平台迁移，不是交互重设计。
- 目标是让用户在功能体感上认为新旧 UI 是同一个产品：同一个入口、同一个操作语义、同一个反馈节奏。
- 如果旧 UI 是右侧抽屉，新 UI 也必须是右侧抽屉；如果旧 UI 是弹窗，新 UI 也必须是弹窗；如果旧 UI 是菜单、Popover、确认框、表格行操作或顶部工具栏，新 UI 必须保留同类交互形态和同等信息层级。
- 允许视觉风格、颜色、字体、间距、组件实现和 CSS 类名变化；不允许改变用户完成任务的路径。
- 后端、API contract、read model、worker、权限语义、业务状态机不改。
- `ReconciliationWorkbenchPage` 和 `web/src/components/workbench/*` 内部冻结；App Shell 会迁移并包住关联台。

## 采集命令

```bash
rg -l "@mui|MuiDataGrid|muiTheme|useMuiDataGrid|\\.Mui" web/src | sort
rg -l "@mui|MuiDataGrid|muiTheme|useMuiDataGrid|\\.Mui" web/src | rg -v "web/src/(pages/ReconciliationWorkbenchPage\\.tsx|components/workbench/)" | wc -l
rg -n "@mui|MuiDataGrid|muiTheme|useMuiDataGrid|\\.Mui" web/src --glob '*.{test,spec}.{ts,tsx}'
rg -n "MuiDataGrid|MuiTableCell|month-picker-mui|\\.Mui" web/src/app/styles.css
```

## 当前技术栈快照

`web/package.json` 当前仍是 React 18 + MUI 平台：

| 类型 | 当前事实 | 迁移目标 |
| --- | --- | --- |
| React | `react@18.3.1`, `react-dom@18.3.1`, `react-is@18.3.1` | React 19 |
| UI | `@mui/material`, `@mui/icons-material`, `@mui/x-data-grid`, `@mui/x-date-pickers`, `@emotion/*` | HeroUI v3 + Tailwind CSS v4 |
| Date | `dayjs` + MUI X LocalizationProvider | 保留 `YYYY-MM` 业务契约，移除非关联台 MUI X picker |
| Table | MUI Table、MUI X DataGrid、原生 table 混用 | HeroUI Table + `FinanceTable` |
| CSS | 单一 `web/src/app/styles.css`，包含 App Shell、普通页面、MUI selector、关联台样式 | Tailwind/HeroUI entry + 产品 primitives + workbench legacy containment |
| Icons | `@mui/icons-material` | 非关联台迁到项目 icon primitive，优先 `lucide-react` |

## MUI 命中规模

- 全 `web/src` 命中 `@mui|MuiDataGrid|muiTheme|useMuiDataGrid|.Mui` 的文件数：95。
- 排除 `ReconciliationWorkbenchPage` 与 `web/src/components/workbench/*` 后仍命中：92。
- 直接属于冻结关联台内部的 MUI 命中文件：3。
- 结论：迁移不能按“换几个页面样式”处理，必须按平台栈、primitives、shell、表格系统、页面模块、MUI containment 的顺序推进。

## 完整 MUI 命中文件清单

```text
web/src/app/App.tsx
web/src/app/MuiProviders.tsx
web/src/app/muiTheme.ts
web/src/app/pageRegistry.tsx
web/src/app/styles.css
web/src/components/MonthPicker.tsx
web/src/components/common/AppDialog.tsx
web/src/components/common/AppDrawer.tsx
web/src/components/common/ConfirmActionDialog.tsx
web/src/components/common/FileDropzone.tsx
web/src/components/common/PageScaffold.tsx
web/src/components/common/PageToolbar.tsx
web/src/components/common/PermissionNotice.tsx
web/src/components/common/StatePanel.tsx
web/src/components/cost-statistics/CostStatisticsTable.tsx
web/src/components/imports/ImportWorkflowPage.tsx
web/src/components/inputInvoiceUsage/ExpandableCellText.tsx
web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx
web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx
web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx
web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx
web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx
web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx
web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx
web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx
web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx
web/src/components/outputInvoiceCollections/ExpandableCellText.tsx
web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx
web/src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx
web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx
web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx
web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx
web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx
web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx
web/src/components/pendingInvoices/ManualInvoiceDialog.tsx
web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx
web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx
web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx
web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx
web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx
web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx
web/src/components/pendingInvoices/PendingInvoicesTable.tsx
web/src/components/settings/OaManualSearchImportTable.tsx
web/src/components/settings/SettingsAccessAccountsSection.tsx
web/src/components/settings/SettingsBankAccountsSection.tsx
web/src/components/settings/SettingsDataResetSection.tsx
web/src/components/settings/SettingsOaInvoiceOffsetSection.tsx
web/src/components/settings/SettingsOaRetentionSection.tsx
web/src/components/settings/SettingsPageContent.tsx
web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx
web/src/components/settings/SettingsProjectsSection.tsx
web/src/components/settings/SettingsTreeNav.tsx
web/src/components/settings/settingsDesign.ts
web/src/components/shell/AppSidebar.tsx
web/src/components/shell/AppStatusIndicator.tsx
web/src/components/shell/AppTopBar.tsx
web/src/components/tax/CertifiedInvoiceImportModal.tsx
web/src/components/tax/CertifiedResultsDrawer.tsx
web/src/components/tax/TaxResultPanel.tsx
web/src/components/tax/TaxSummaryCards.tsx
web/src/components/tax/TaxTable.tsx
web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx
web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx
web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx
web/src/components/workbench/WorkbenchPaneSearch.tsx
web/src/components/workbench/WorkbenchRecordCard.tsx
web/src/components/workbench/WorkbenchZone.tsx
web/src/features/bankDetails/AutoTagRulesDrawer.tsx
web/src/features/bankDetails/BankCategoryTag.tsx
web/src/hooks/useMuiDataGridPageSession.ts
web/src/pages/AppHealthOperationsPage.tsx
web/src/pages/BankDetailsPage.tsx
web/src/pages/BatchAccountingPage.tsx
web/src/pages/CostStatisticsPage.tsx
web/src/pages/EtcTicketManagementPage.tsx
web/src/pages/InputInvoiceUsagePage.tsx
web/src/pages/NoOaBankBatchPage.tsx
web/src/pages/OaPendingPaymentsPage.tsx
web/src/pages/OutputInvoiceCollectionsPage.tsx
web/src/pages/PendingInvoicesPage.tsx
web/src/pages/SettingsPage.tsx
web/src/pages/TaxOffsetPage.tsx
web/src/pages/TurnoverLedgerPage.tsx
web/src/test/App.test.tsx
web/src/test/AppStatusIndicator.test.tsx
web/src/test/AutoTagRulesDrawer.test.tsx
web/src/test/BankDetailsPage.test.tsx
web/src/test/InputInvoiceUsagePage.test.tsx
web/src/test/MonthPicker.test.tsx
web/src/test/OaPendingPaymentsPage.test.tsx
web/src/test/OutputInvoiceCollectionsPage.test.tsx
web/src/test/SettingsOaManualSearchImportTable.test.tsx
web/src/test/TableAlignmentStyles.test.ts
web/src/test/TaxOffsetPage.test.tsx
web/src/test/useMuiDataGridPageSession.test.tsx
```

## 平台和 Shell 文件

| 文件 | 分类 | 风险 | 迁移说明 |
| --- | --- | --- | --- |
| `web/src/app/App.tsx` | 非关联台平台入口 | high | 依赖 MUI `Box`、`Alert`、`useTheme`、`useMediaQuery` 和 `MuiProviders`；迁移时必须保留 provider 顺序、路由、keep alive、OA embedded、后台任务提示。 |
| `web/src/app/MuiProviders.tsx` | 非关联台平台入口 | high | 当前注入 MUI theme、MUI X date locale、CssBaseline；迁移时改为 UI/CSS entry，不再用非关联台 MUI provider。 |
| `web/src/app/muiTheme.ts` | 非关联台平台入口 | high | 当前包含 MUI TableCell 全局居中和 MUI locale；迁移时废弃非关联台主题，但关联台 legacy 若仍需 MUI theme，必须隔离。 |
| `web/src/app/pageRegistry.tsx` | App Shell 导航 | high | 侧栏图标来自 `@mui/icons-material`，必须迁到项目 icon primitive，保持页面顺序、label、path、active 语义。 |
| `web/src/app/styles.css` | 全局 CSS | high | 包含 MUI selector、普通页面样式和关联台样式；必须先 containment，再清理非关联台 `.Mui*`。 |
| `web/src/components/shell/AppSidebar.tsx` | App Shell | high | MUI Drawer/List/Collapse/IconButton/Tooltip；迁移后仍保持左侧菜单、折叠、移动端抽屉、OA embedded 默认折叠。 |
| `web/src/components/shell/AppTopBar.tsx` | App Shell | medium | MUI AppBar/Toolbar；迁移后保留紧凑屏顶部栏和打开菜单按钮。 |
| `web/src/components/shell/AppStatusIndicator.tsx` | App Shell 状态 | high | MUI Popper/Chip/Progress；迁移后保留健康状态、hover/focus/click popover、状态文本和颜色语义。 |

## 共享组件文件

| 文件 | 风险 | 迁移说明 |
| --- | --- | --- |
| `web/src/components/common/AppDialog.tsx` | high | 旧弹窗仍应是弹窗，不改为抽屉或页面内卡片。 |
| `web/src/components/common/AppDrawer.tsx` | high | 旧右侧抽屉迁移后仍必须从右侧进入，宽度、header/body/footer、关闭语义保持。 |
| `web/src/components/common/ConfirmActionDialog.tsx` | high | 破坏性/重要操作仍需确认、loading、防重复提交。 |
| `web/src/components/common/FileDropzone.tsx` | medium | 保留 drop/click 上传入口和可访问 button 语义。 |
| `web/src/components/common/PageScaffold.tsx` | high | 页面标题、说明、主操作位置不能重排成 landing/marketing 风格。 |
| `web/src/components/common/PageToolbar.tsx` | high | 筛选、刷新、导出、批量动作的位置和层级必须保持。 |
| `web/src/components/common/PermissionNotice.tsx` | medium | 权限提示不能被隐藏；禁用原因要可读。 |
| `web/src/components/common/StatePanel.tsx` | high | loading/empty/error/stale/permission/unavailable 统一迁移。 |
| `web/src/components/MonthPicker.tsx` | high | MUI X 月份选择器；必须保留 `YYYY-MM` 输入输出、`formatMonthLabel`、inline 和普通模式。 |

## 表格和数据密集文件

| 文件 | 分类 | 风险 | 迁移说明 |
| --- | --- | --- | --- |
| `web/src/components/cost-statistics/CostStatisticsTable.tsx` | 非关联台 DataGrid | high | DataGrid + scroll session；需先设计 HeroUI Table session 替代。 |
| `web/src/components/imports/ImportWorkflowPage.tsx` | 非关联台 DataGrid | high | 多个 preview/detail grid session；迁移前必须锁定导入预览、确认、错误、刷新行为。 |
| `web/src/hooks/useMuiDataGridPageSession.ts` | 非关联台 DataGrid session | high | 保存分页、排序、筛选、选择、列宽、列顺序、滚动；需替换为 table session primitive 或删除已无用户入口的状态。 |
| `web/src/components/settings/SettingsBankAccountsSection.tsx` | 非关联台 DataGrid | high | 设置页银行账户表格和滚动/session。 |
| `web/src/components/settings/OaManualSearchImportTable.tsx` | 非关联台表格 | high | 设置页导入表格；需保留非 DataGrid 验收。 |
| `web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx` | 非关联台表格 | high | 发票使用状态、tag、详情入口和批量/导出入口。 |
| `web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx` | 非关联台表格 | high | OA 待付款核对列表。 |
| `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx` | 非关联台表格 | high | 销项收款状态、回款/红票/预览入口。 |
| `web/src/components/pendingInvoices/PendingInvoicesTable.tsx` | 非关联台表格 | high | 待找发票关系、规则、抽屉入口。 |
| `web/src/components/tax/TaxTable.tsx` | 非关联台表格 | medium | 税金抵扣表格。 |
| `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx` | 非关联台表格 | high | 左右双栏台账、选择、展开、操作列。 |
| `web/src/pages/BankDetailsPage.tsx` | 非关联台表格/筛选 | high | MUI Table、Pagination、Menu/Popover、DatePicker、规则抽屉。 |
| `web/src/pages/BatchAccountingPage.tsx` | 非关联台表格/弹窗 | high | MUI Table、撤回 Dialog、筛选、选择。 |

## 右侧抽屉和弹窗文件

以下文件迁移时必须保持原交互形态。文件名含 `Drawer` 的旧 UI 默认视为右侧抽屉，除非代码证明不是右侧；迁移后不得改成 Modal、页面内展开区或新路由。

| 文件 | 旧形态 | 迁移硬约束 |
| --- | --- | --- |
| `web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx` | 右侧抽屉 | 仍为右侧详情抽屉。 |
| `web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx` | 右侧抽屉 | 仍为右侧导出抽屉。 |
| `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx` | 右侧抽屉 | 仍为右侧工作区抽屉，不改主页面布局。 |
| `web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx` | 右侧抽屉 | 仍为右侧规则抽屉。 |
| `web/src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx` | 右侧抽屉 | 仍为右侧提醒抽屉。 |
| `web/src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx` | 右侧抽屉 | 仍为右侧规则抽屉。 |
| `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx` | 右侧抽屉 | 仍为右侧详情抽屉。 |
| `web/src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx` | 右侧抽屉 | 仍为右侧历史抽屉。 |
| `web/src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx` | 右侧抽屉 | 仍为右侧预览抽屉。 |
| `web/src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx` | 右侧抽屉 | 仍为右侧设置抽屉。 |
| `web/src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx` | 右侧抽屉 | 仍为右侧红票关系抽屉。 |
| `web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx` | 右侧抽屉 | 仍为右侧详情抽屉。 |
| `web/src/components/pendingInvoices/PendingInvoiceDrawerFrame.tsx` | 右侧抽屉框架 | 仍作为右侧抽屉 frame primitive。 |
| `web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx` | 右侧抽屉 | 仍为右侧导出抽屉。 |
| `web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx` | 右侧抽屉 | 仍为右侧发票选择抽屉。 |
| `web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx` | 右侧抽屉 | 仍为右侧关系抽屉。 |
| `web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx` | 右侧抽屉 | 仍为右侧规则抽屉。 |
| `web/src/components/tax/CertifiedResultsDrawer.tsx` | 右侧抽屉 | 仍为右侧认证结果抽屉。 |
| `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx` | 右侧抽屉 | 仍为右侧补充信息抽屉。 |
| `web/src/features/bankDetails/AutoTagRulesDrawer.tsx` | 右侧抽屉 | 仍为右侧自动标签规则抽屉。 |
| `web/src/components/pendingInvoices/ManualInvoiceDialog.tsx` | 弹窗 | 仍为弹窗。 |
| `web/src/components/tax/CertifiedInvoiceImportModal.tsx` | 弹窗 | 仍为弹窗。 |
| `web/src/components/turnoverLedger/TurnoverLedgerExportDialog.tsx` | 弹窗 | 仍为弹窗。 |
| `web/src/pages/BatchAccountingPage.tsx` | 弹窗 | 撤回关联仍为确认弹窗。 |

## 页面清单

页面事实来自 `web/src/app/pageRegistry.tsx`。

| 路径 | 页面 | pageKey | 迁移状态 | 风险 |
| --- | --- | --- | --- | --- |
| `/` | 关联台 | `reconciliation-workbench` | App Shell 迁移，内部冻结 | high |
| `/tax-offset` | 税金抵扣 | `tax-offset` | 待迁移 | medium |
| `/cost-statistics` | 成本统计 | `cost-statistics` | 待迁移 | high |
| `/bank-details` | 银行明细 | `bank-details` | 待迁移 | high |
| `/pending-invoices` | 待找发票 | `pending-invoices` | 待迁移 | high |
| `/input-invoice-usage` | 进项发票使用情况 | `input-invoice-usage` | 待迁移 | high |
| `/oa-pending-payments` | OA待付款核对 | `oa-pending-payments` | 待迁移 | high |
| `/output-invoice-collections` | 销项发票收款情况 | `output-invoice-collections` | 待迁移 | high |
| `/no-oa-bank-batches` | 免OA流水批量处理 | `no-oa-bank-batches` | 待迁移 | high |
| `/batch-accounting` | 批量账务 | `batch-accounting` | 待迁移 | high |
| `/turnover-ledger` | 外部往来款管理 | `turnover-ledger` | 待迁移 | high |
| `/etc-tickets` | ETC票据管理 | `etc-tickets` | 待迁移 | high |
| `/settings` | 设置 | `settings` | 待迁移 | high |
| `/operations/app-health` | 系统状态 | `app-health-operations` | 待迁移 | medium |
| `/imports/bank-transactions` | 银行流水导入 | `imports.bank-transactions` | 待迁移 | high |
| `/imports/invoices` | 发票导入 | `imports.invoices` | 待迁移 | high |
| `/imports/etc-invoices` | ETC发票导入 | `imports.etc-invoices` | 待迁移 | high |

## MUI 相关测试清单

这些测试不能直接删除。迁移前应先把它们改成用户可见行为、语义、角色、设计 token 或 primitive 合约测试。

| 测试文件 | 当前 MUI 依赖 | 迁移方向 |
| --- | --- | --- |
| `web/src/test/App.test.tsx` | MUI icon component identity | 改为 route label、icon key、可访问名称、侧栏顺序。 |
| `web/src/test/AppStatusIndicator.test.tsx` | `.MuiPopover-root` absence | 改为状态 popover role、打开/关闭行为。 |
| `web/src/test/AutoTagRulesDrawer.test.tsx` | `.MuiTableCell-root`、`.MuiButton-root`、`.MuiInput-root` CSS regex | 改为右侧抽屉结构、规则行换行、按钮高度 token、字段交互。 |
| `web/src/test/BankDetailsPage.test.tsx` | MUI pagination/button/list CSS regex | 改为分页位置、筛选层级、导出菜单、规则抽屉行为。 |
| `web/src/test/InputInvoiceUsagePage.test.tsx` | `.MuiDataGrid-root` absence、`.MuiChip-root` | 改为 HeroUI/FinanceTag primitive 或可见 tag 文本语义。 |
| `web/src/test/MonthPicker.test.tsx` | MUI X month field class | 改为 `YYYY-MM` 输出、年份/月选择、inline/普通模式、aria label。 |
| `web/src/test/OaPendingPaymentsPage.test.tsx` | `.MuiDataGrid-root` absence | 保留非 DataGrid 约束，改为 FinanceTable/HeroUI Table frame。 |
| `web/src/test/OutputInvoiceCollectionsPage.test.tsx` | `.MuiDataGrid-root` absence | 保留非 DataGrid 约束，改为 FinanceTable/HeroUI Table frame。 |
| `web/src/test/SettingsOaManualSearchImportTable.test.tsx` | `.MuiDataGrid-root` absence | 保留非 DataGrid 约束，改为表格语义。 |
| `web/src/test/TableAlignmentStyles.test.ts` | `muiTheme` 和 `.MuiDataGrid` 全局居中 | 删除旧主题断言，改为 table column role 对齐 token。 |
| `web/src/test/TaxOffsetPage.test.tsx` | `.MuiDialog-root` | 改为 dialog role/name、confirm/cancel 行为。 |
| `web/src/test/useMuiDataGridPageSession.test.tsx` | MUI X types、`.MuiDataGrid-virtualScroller` | 改为通用 table session hook 或删除不再需要的 MUI-only session。 |

## 直接冻结的关联台 MUI 文件

这些文件在本次迁移中不作为重构目标，只能在必要时为 App Shell/provider/CSS containment 做最小兼容调整。

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/components/workbench/WorkbenchPaneSearch.tsx`
- `web/src/components/workbench/WorkbenchRecordCard.tsx`
- `web/src/components/workbench/WorkbenchZone.tsx`

`web/src/components/workbench/WorkbenchPaneTimeFilter.tsx` 只引用 `formatMonthLabel`，不是 MUI 组件迁移目标；迁移 `MonthPicker` 时必须保持该 pure formatter 可用。

## 基线验收

`phase_0_baseline` 只有在以下事项都完成后才能标记 completed：

- 本文档记录 MUI 命中范围、页面清单、测试清单、右侧抽屉/弹窗形态清单。
- `platform_stack_migration.md` 记录 React 19 + HeroUI v3 + Tailwind v4 的安装和回滚。
- `test_migration_strategy.md` 记录 MUI 测试迁移策略。
- `module_inventory.md` 记录后续模块队列。
- `refactor_ui_state.md` 和 `refactor_ui_prompt.md` 记录本次补齐 prompt。
