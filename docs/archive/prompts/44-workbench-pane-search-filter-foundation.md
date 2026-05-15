# Prompt 44：关联台三栏局部搜索 / 筛选 / 排序底座

目标：先建立前端状态模型与列裁剪底座，为后续三栏实时搜索、列筛选和按组排序做好基础。

前提：

- 阅读：
  - `docs/product/银企核销需求.md`
  - `docs/superpowers/specs/2026-04-08-workbench-pane-search-filter-sort-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-pane-search-filter-sort.md`
- 已完成：
  - `43-workbench-read-model-ui-perf-and-qa.md`

要求：

- 不新增后端接口
- 先在前端建立 `paired/open` 两套局部搜索、筛选、排序状态
- 先完成列裁剪：
  - OA 去掉 `金额`、`申请事由`
  - 银行流水去掉 `备注`
  - 发票去掉 `金额/税率/税额`、`价税合计`
- 抽出 `displayGroups` helper，为后续“当前栏驱动、整组联动”做准备

建议文件：

- `web/src/features/workbench/tableConfig.ts`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/features/workbench/groupDisplayModel.ts`
- `web/src/test/WorkbenchColumns.test.tsx`
- `web/src/test/CandidateGroupGrid.test.tsx`

验证：

- 跑相关前端测试
- 跑前端 build
