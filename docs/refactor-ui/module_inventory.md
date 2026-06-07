# UI 模块迁移队列

本文档记录后续 UI 迁移的模块顺序、切片边界和验收重点。执行者每次只能选择一个模块或一个明确切片，不能并行推进多个业务模块。

Last updated: 2026-06-08

## 总体顺序

1. `platform-stack`
2. `design-tokens-css-entry`
3. `shared-primitives`
4. `app-shell`
5. `month-date-session`
6. `finance-table-system`
7. `page-modules`
8. `mui-containment`
9. `full-verification`
10. `closeout`

原因：如果先迁页面，会把 MUI provider、MUI theme、DataGrid session、图标、全局 CSS 和测试断言的风险分散到多个业务模块，后续难以收口。

## 行为等价硬约束

迁移前必须写旧 UI 入口表。迁移后必须逐项对照：

| 旧 UI | 新 UI 必须 |
| --- | --- |
| 左侧菜单 | 仍是左侧菜单，保留分组、顺序、active、折叠、移动端打开方式。 |
| 顶部栏 | 仍是顶部栏，只在旧逻辑显示的场景显示。 |
| 右侧抽屉 | 仍是右侧抽屉，不改弹窗、不改页面内卡片、不改新路由。 |
| 弹窗 | 仍是弹窗，不改抽屉。 |
| Popover/Menu | 仍从原触发器打开同类浮层。 |
| 表格 | 仍是表格，不改成卡片列表，除非旧页面本来就是卡片。 |
| 行点击详情 | 仍从行点击或旧按钮进入同一详情形态。 |
| 导入/导出/刷新/确认按钮 | 旧位置和信息层级保持等价。 |
| 权限禁用 | 仍禁用或隐藏在旧语义下，并保留原因提示。 |

## 阶段切片

| Slice | Phase | 目标 | MG 边界 |
| --- | --- | --- | --- |
| `platform-stack` | `phase_2_platform_stack` | React 19、HeroUI、Tailwind、Vite、CSS import | build + shell smoke |
| `design-tokens-css-entry` | `phase_1_docs_and_tokens` | Ledger Calm CSS variables、Tailwind theme bridge | token tests + no default-theme drift |
| `shared-primitives` | `phase_3_primitives` | Button、Tag、StatePanel、Dialog、Drawer、Toolbar、Tooltip、Icon primitive | primitive tests |
| `app-shell` | `phase_4_shell` | Sidebar、TopBar、StatusIndicator、page body | route/sidebar/workbench wrapper smoke |
| `month-date-session` | `phase_3_primitives` | MonthPicker、formatters、table session primitive | MonthPicker/session tests |
| `finance-table-system` | `phase_5_table_system` | FinanceTable、cell primitives、pagination、loading/empty/error | table role/alignment tests |
| `mui-containment` | `phase_7_mui_containment` | 清除非关联台 MUI import，隔离关联台 legacy | `rg` 清单只剩允许项 |

## 页面模块队列

| 顺序 | 模块 | 路径 | 主要文件 | 风险 | 主要交互 |
| --- | --- | --- | --- | --- | --- |
| 1 | 税金抵扣 | `/tax-offset` | `TaxOffsetPage.tsx`, `components/tax/*` | medium | 月份选择、表格、认证导入弹窗、右侧认证结果工作区。Discovery: `docs/refactor-ui/modules/tax-offset.md`. |
| 2 | 系统状态 | `/operations/app-health` | `AppHealthOperationsPage.tsx`, `features/appHealth/*` | medium | 状态面板、刷新、健康/worker 信息。Discovery: `docs/refactor-ui/modules/app-health.md`. |
| 3 | 导入页族 | `/imports/*` | `components/imports/ImportWorkflowPage.tsx`, import pages | high | 上传、预览表格、确认、进度、错误、详情预览。Premium discovery: `docs/refactor-ui/modules/phase_6_import_pages.md`. |
| 4 | 成本统计 | `/cost-statistics` | `CostStatisticsPage.tsx`, `components/cost-statistics/*` | high | DataGrid、月份/范围、详情弹窗、导出弹窗。 |
| 5 | 银行明细 | `/bank-details` | `BankDetailsPage.tsx`, `features/bankDetails/*` | high | 表格、分页、日期筛选、导出菜单、自动标签规则右侧抽屉。 |
| 6 | 待找发票 | `/pending-invoices` | `PendingInvoicesPage.tsx`, `components/pendingInvoices/*` | high | 表格、详情/关系/规则/导出/发票选择右侧抽屉、手工发票弹窗。 |
| 7 | 进项发票使用 | `/input-invoice-usage` | `InputInvoiceUsagePage.tsx`, `components/inputInvoiceUsage/*` | high | 表格、筛选菜单、详情/导出/规则/OA 反查右侧抽屉。 |
| 8 | OA 待付款核对 | `/oa-pending-payments` | `OaPendingPaymentsPage.tsx`, `components/oaPendingPayments/*` | high | 表格、状态、筛选、异常反馈。Premium discovery: `docs/refactor-ui/modules/phase_6_oa_pending_payments.md`. |
| 9 | 销项发票收款 | `/output-invoice-collections` | `OutputInvoiceCollectionsPage.tsx`, `components/outputInvoiceCollections/*` | high | 表格、详情/回款/红票/预览/设置/历史右侧抽屉。Premium discovery: `docs/refactor-ui/modules/phase_6_output_invoice_collections.md`. |
| 10 | 免OA流水批量处理 | `/no-oa-bank-batches` | `NoOaBankBatchPage.tsx`, `features/noOaBankBatches/*` | high | 批量选择、确认、状态反馈。Premium discovery: `docs/refactor-ui/modules/phase_6_no_oa_bank_batches.md`. |
| 11 | 批量账务 | `/batch-accounting` | `BatchAccountingPage.tsx`, `features/batchAccounting/*` | high | 表格、搜索、选择、撤回弹窗、Snackbar。 |
| 12 | 外部往来款管理 | `/turnover-ledger` | `TurnoverLedgerPage.tsx`, `components/turnoverLedger/*` | high | 左右双栏表格、选择、展开、补充信息右侧抽屉、导出弹窗。 |
| 13 | ETC 票据管理 | `/etc-tickets` | `EtcTicketManagementPage.tsx`, `features/etc/*` | high | 导入、表格、对账、确认、空/错误状态。 |
| 14 | 设置 | `/settings` | `SettingsPage.tsx`, `components/settings/*` | high | 左侧设置导航、多个设置 section、DataGrid、导入表格、权限提示。 |

## 关联台边界模块

| 模块 | 范围 | 本次动作 |
| --- | --- | --- |
| 关联台 App Shell wrapper | `/`, `ReconciliationWorkbenchPage` 外层 | 新 App Shell 包住页面，route、keepAlive、sidebar label 保留。 |
| 关联台内部工作区 | `ReconciliationWorkbenchPage` 和 `web/src/components/workbench/*` | 冻结，不迁 HeroUI，不改行交互、三栏结构、内部弹窗和专用 CSS。 |
| 关联台 legacy MUI | direct workbench MUI files | 只允许 containment，不做视觉重构。 |

## 每个页面模块文档模板

页面迁移前，在本文件或模块专项文档追加：

```markdown
## <module> discovery

- Prompt ID:
- 旧页面文件:
- 旧测试:
- API/read model contract:
- 用户可见入口:
- 表格:
- 右侧抽屉:
- 弹窗:
- 菜单/Popover:
- loading/empty/error/stale/permission:
- characterization tests:
- 不改范围:
- 验证命令:
```

如果模块只需要一个 discovery 记录，可以直接写在本文档后续章节。只有当模块会连续执行多个 prompt、需要保留复杂旧入口对照、右侧抽屉/弹窗矩阵、表格列角色、API/read model 风险或测试迁移策略时，才新建 `docs/refactor-ui/modules/<module>.md`。不为一次性临时分析新建 md。

## 页面 MG 验收

每个页面模块到 MG 前必须满足：

- 旧入口逐项对照完成。
- 旧右侧抽屉仍为右侧抽屉。
- 旧弹窗仍为弹窗。
- 表格列角色写入模块记录。
- 相关 MUI class 测试已转成行为/primitive 测试。
- 当前模块非关联台无新增 `@mui/*`。
- 后端/API/read model/worker diff 为空。
- 相关测试和浏览器 smoke 已记录。

## 下一条 prompt 生成规则

- 从 `refactor_ui_state.md` 读取当前 phase 和 queue。
- 每个 phase 可以包含多个执行 prompt；不要把 phase 当成单条 prompt。
- 从本文选择一个 pending slice。
- 先生成 discovery/planning prompt，不直接写实现 prompt。
- 下一条 prompt 必须结合上一条 prompt 或 MG 的完成情况、验证结果、当前 diff 和模块文档单独分析生成。
- 同一模块的 prompt 可以连续执行，但必须保持 discovery -> characterization tests -> extraction/refactor -> verification -> MG。
- 如果发现模块风险高于预估，先更新本文，再拆更小切片。
