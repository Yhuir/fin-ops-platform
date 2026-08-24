# Finance Table System 模块维护入口

- Module key: `finance-table-system`
- 类型: 资源模块
- Route: `N/A`
- Page key: `N/A`

## 修改前必读

- `docs/app-architecture/pages.md`
- `docs/modules/app-shell-navigation/README.md`
- `docs/refactor-ui/table_layout_system.md`
- `docs/refactor-ui/test_migration_strategy.md`

## 代码入口

- `web/src/components/common/FinanceTable.tsx`：HeroUI Table 外壳、自然/受限滚动模式、列/行/单元格 primitive、分页、金额/方向/状态/空值/截断文本 primitive。
- `web/src/hooks/useFinanceTableSession.ts`：表格分页、排序、选择、滚动位置的轻量 session hook。
- `web/src/components/*Table*`、`web/src/pages/*Page.tsx`：页面级业务表格、筛选、排序、分页、导出、详情 drawer/dialog。
- `web/src/app/styles.css`：共享表格 token、列角色对齐、行高、tag 高度和 motion contract。
- `docs/refactor-ui/table_layout_system.md`：表格排版事实源。

## 当前边界

- 共享 `FinanceTable` 只提供 presentation primitives，不拥有业务查询、read model freshness、导出 API、权限或业务状态。
- 页面级表格仍由各页面维护自己的筛选、排序、分页、search、drawer/dialog、导出和 loading/error/stale 状态；共享表格不强行抽象这些业务差异。
- 表格 session 只保存轻量 UI 状态，不保存 read model payload、rows、业务事实、权限事实、loading/error/toast 或失败中的提交。
- `useFinanceTableSession` 当前主要由专项测试覆盖；并非所有页面都已统一接入该 hook。已经接入或自行实现 session 的页面必须在页面模块测试中保护恢复语义。
- 列对齐由 `columnRole` 决定：金额/数量右对齐，日期/状态/方向/选择居中，主体/账户/说明左对齐。禁止全局把所有 cell 居中。
- 页面需要固定表格高度时使用 `scrollMode="contained"`，并由页面外壳提供有界高度；滚动、sticky 表头和 overscroll 隔离由共享 `FinanceTable` 负责，同一双栏/三栏中的各表格互不带动。
- 需要分页的页面把 HeroUI 页容量选择器与 `FinanceTablePagination` 放进同一个表格 footer；不得在表格外再维护第二个原生 select/button 分页块。
- 非关联台生产表格必须使用共享 `FinanceTable`。关联台 `PaneTable` 与详情表是当前唯一冻结例外，其独立高性能滚动合同由 Workbench 模块负责。
- 表格 migration 不能删除旧页面的导出、确认、刷新、筛选、选择、右侧详情抽屉或现有分页语义。
- 页面需要允许复制业务文本时，显式启用 `FinanceTable selectableText`。共享层负责原生鼠标拖选，并隔离 HeroUI grid cell 的焦点接管；按钮、链接、输入框和复选框仍保持原交互，不纳入拖选目标。

## 主要使用点

| 使用点 | 说明 |
| --- | --- |
| `BankDetailsPage` | 银行流水表使用共享 `FinanceTable` primitives；分页、导出、标签筛选在页面维护。 |
| `TaxTable` / `CertifiedInvoiceImportModal` | 税金抵扣和认证导入预览使用共享 primitive。 |
| `ImportWorkflowPage` | 导入预览表使用共享 primitive 和状态 tag。 |
| `AppHealthOperationsPage` | runtime dashboard 多个只读表使用共享 primitive。 |
| `InputInvoiceUsageTable`、`PendingInvoicesTable`、`OaPendingPaymentsTable`、`OutputInvoiceCollectionsTable`、`TurnoverLedgerGroupedTable`、`CostStatisticsTable` | 业务表格多为页面/模块专属 table wrapper，需由对应页面测试覆盖。 |

## 测试入口

- `web/src/test/FinanceTable.test.tsx`
- `web/src/test/TableLayoutTokens.test.ts`
- `web/src/test/TableAlignmentStyles.test.ts`
- `web/src/test/FinanceTableMigration.test.ts`
- `web/src/test/useFinanceTableSession.test.tsx`
- `web/src/test/MuiContainment.test.ts`
- `web/src/test/CommonPlatformComponents.test.tsx`
- `web/e2e/finance-table-text-selection.spec.ts`
- 页面级表格测试：`BankDetailsPage.test.tsx`、`TaxOffsetPage.test.tsx`、`InputInvoiceUsagePage.test.tsx`、`PendingInvoicesPage.test.tsx`、`OutputInvoiceCollectionsPage.test.tsx`、`OaPendingPaymentsPage.test.tsx`、`CostStatisticsPage.test.tsx`、`TurnoverLedgerPage.test.tsx`、`AppHealthOperationsPage.test.tsx`、`ImportCenterPage.test.tsx`。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护 Finance Table System 的 Spec-first Browser E2E 合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/Vitest/页面级证据的覆盖矩阵和外部风险。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
