# Prompt 46：关联台三栏按组时间排序与 QA

目标：在局部搜索/筛选基础上，完成银行流水和进销项发票的按组时间排序，并收口双区一致性与 QA。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-08-workbench-pane-search-filter-sort-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-pane-search-filter-sort.md`
- 已完成：
  - `45-workbench-pane-search-filter-ui.md`

要求：

- `银行流水` 增加按时间升序 / 降序切换
- `进销项发票` 在 `开票日期` 后增加按时间升序 / 降序切换
- 排序按 group 生效，而不是只改当前栏局部顺序
- `已配对 / 未配对` 两个区域行为一致
- 保持三栏切换、放大、选择、详情等既有交互不回退

建议文件：

- `web/src/features/workbench/groupDisplayModel.ts`
- `web/src/components/workbench/CandidateGroupGrid.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/test/WorkbenchPaneFilter.test.tsx`
- `web/src/test/CandidateGroupGrid.test.tsx`
- `web/src/test/WorkbenchSelection.test.tsx`

验证：

- 跑前端全量 tests
- 跑前端 build
