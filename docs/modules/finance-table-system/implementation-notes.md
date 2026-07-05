# Finance Table System 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 共享 `FinanceTable` 保持 presentation primitive，不上提页面业务查询、导出、read model freshness 或权限判断。
- 页面级表格 wrapper 可继续保留 domain-specific 结构；迁移时必须先补 characterization/regression test 保护旧筛选、排序、分页、导出和详情入口。
- `useFinanceTableSession` 只保存轻量表格 UI state；当前未强制所有页面使用。未接入该 hook 的页面必须在页面模块里保护自己的 session/query state。
- 共享 primitive 的低层 contract 由 `FinanceTable.test.tsx`、CSS token/style tests 保护；页面表格行为由具体页面测试保护。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-07-05 - Finance Table System边界close与旧DataGrid残留防回归

- 目标：完成 Finance Table System 模块边界与 I/O close，确认共享表格不承载业务 I/O，并移除活跃测试中的旧 MUI 命名残留。
- 影响范围：`CommonMuiComponents.test.tsx` 改名为 `CommonPlatformComponents.test.tsx`、`MuiContainment.test.ts`、本模块 README/boundary/state/tests 和测试迁移策略文档。
- 关键决策：不迁移所有页面表格 wrapper；页面 wrapper 的筛选、排序、分页、导出、read model freshness 和 drawer/dialog 继续归页面模块。运行时代码中旧 MUI/DataGrid/provider/theme 和 `useMuiDataGridPageSession` 已不存在，本轮用最小 guard 防回归，并把 boundary 状态改为 close。
- 文档影响：更新本模块 `README.md`、`boundary-io.md`、`state-machine.md`、`tests.md` 和 `docs/refactor-ui/test_migration_strategy.md`。
- 测试覆盖：`MuiContainment.test.ts` 新增旧 `useMuiDataGridPageSession` hook/test 不存在断言；`CommonPlatformComponents.test.tsx` 保留 StatePanel、AppDialog/AppDrawer、ConfirmActionDialog、FileDropzone、PageScaffold/PageToolbar 等 common primitive 行为覆盖。
- 验证命令：见本轮最终执行记录。
- 未测风险：未跑完整页面级表格矩阵和真实 Chromium finance-table-system e2e；本轮没有改页面表格 runtime，页面级风险仍由对应模块测试和发布 smoke 承担。

## 2026-06-19 - 共享 column filter 小屏定位修复

- 目标：修复共享 `WorkbenchColumnFilterMenu` 在 tax-offset 390px 窄屏场景下可能把选项渲染到 viewport 外，导致筛选项无法真实点击的问题。
- 影响范围：`web/src/components/workbench/WorkbenchColumnFilterMenu.tsx`、`web/src/app/styles.css`、tax-offset 大表 Browser smoke。
- 关键决策：保持 filter menu 作为共享 UI primitive；不在测试里使用 force click。popover 根据按钮上下可用空间选择展开方向，并限制整体高度，option list 在内部滚动。
- 文档影响：更新本模块 implementation notes；页面级覆盖仍归 tax-offset 和 workbench 模块。
- 测试覆盖：`web/e2e/tax-offset-flow.spec.ts`、`web/e2e/workbench-large-scroll-flow.spec.ts`、`web/src/test/WorkbenchPaneFilter.test.ts`、`web/src/test/TaxOffsetPage.test.tsx`。
- 验证命令：`cd web && npx playwright test e2e/tax-offset-flow.spec.ts --project=chromium -g "keeps large tax tables searchable, sortable, filterable, and horizontally scrollable on narrow screens"`；`cd web && npx playwright test e2e/workbench-large-scroll-flow.spec.ts --project=chromium`；`cd web && npm test -- --run src/test/WorkbenchPaneFilter.test.ts src/test/TaxOffsetPage.test.tsx`；`cd web && npm run e2e:smoke`，完整 smoke 147/147 passed。
- 未测风险：真实生产超大表格、触摸滚动、浏览器缩放和更多页面 wrapper 的长选项组合仍需后续 smoke。

## 2026-06-19 - Spec-first E2E 合同与覆盖矩阵补齐

- 目标：把 `finance-table-system` 从共享表格 partial 状态推进到本地 Spec-first covered，明确共享 primitive 与页面 wrapper 的测试责任边界。
- 影响范围：新增 `e2e-spec.md`、`e2e-coverage.md`，更新本模块 README 和全局 Spec-first/testing closure 状态。
- 关键决策：共享 `FinanceTable` 仍只提供 presentation primitive；页面级筛选、排序、分页、导出、read model freshness、权限和详情 drawer/dialog 继续归对应页面模块覆盖，不上提成错误的全局业务抽象。
- 文档影响：新增 Spec ID `FIN-TABLE-E2E-001..010`，并把真实生产大数据滚动、浏览器下载保存、代理 header 和真实 XLSX 打开结果明确保留为 `external-risk`。
- 测试覆盖：映射到 `FinanceTable`、table token/alignment、table session、页面级 Vitest，以及 `finance-table-system-flow`、银行明细/关联台/成本统计等代表性真实 Chromium 表格 smoke。
- 验证命令：
  - `bash scripts/verify.sh docs`
  - `git diff --check -- docs/modules/finance-table-system docs/dev/spec-first-e2e-inventory.md docs/dev/testing-closure-state.md`
- 未测风险：未新增 Playwright；本轮是 Spec-first 文档闭环和现有证据映射。真实生产大数据、下载保存和新增 wrapper 自动发现仍需后续 staging/runtime 或工具化 gate。
- 后续事项：新增或迁移业务表格 wrapper 时，先登记到本模块和目标页面模块，再补页面级筛选/排序/导出/状态测试。

## 2026-06-11 - Finance Table System 首轮测试闭环

- 目标：完成共享表格系统 CodeGraph 审计、测试矩阵、状态机、实施记录和共享 primitive 回归测试补强。
- 影响范围：`FinanceTable.tsx`、`useFinanceTableSession.ts`、`PageSessionStateContext`、表格 token/style tests，以及银行明细、税金、进项使用、待找发票、销项收款、OA 待付款、成本、往来款、导入预览、App Health 等页面表格。
- 关键决策：不重构业务页面表格；先补共享 primitive 低层测试，并把页面级表格行为继续归属到对应页面模块。
- 文档影响：补齐本模块 `README.md`、`tests.md`、`state-machine.md` 和全局 dependency map。
- 测试覆盖：
  - 新增 `web/src/test/FinanceTable.test.tsx`，覆盖 `FinanceTablePagination` clamp/summary/disabled/callback，以及 `TableCellStack`、`AmountCell`、`FinanceDirectionTag`、`FinanceStatusTag`、`EmptyValue` 的稳定 class/data contract。
- 验证命令：
  - `cd web && npm test -- --run src/test/FinanceTable.test.tsx`
- 未测风险：真实大数据浏览器滚动、超宽列、浏览器下载保存行为；页面级 wrapper 未全部统一到共享 `FinanceTable`，需由页面模块持续保护。
- 后续事项：任何页面表格迁移必须按 `docs/refactor-ui/table_layout_system.md` 的 checklist 先列旧功能入口并补旧行为回归。
