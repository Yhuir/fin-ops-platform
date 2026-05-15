# Prompt 45：关联台三栏局部搜索与多选筛选交互

目标：完成 `已配对 / 未配对` 两个区域内三栏的实时搜索和列级多选筛选，并按“当前栏驱动、整组联动”显示结果。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-08-workbench-pane-search-filter-sort-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-pane-search-filter-sort.md`
- 已完成：
  - `44-workbench-pane-search-filter-foundation.md`

要求：

- 每个 pane header 增加搜索 icon
- 点击后展开一个小搜索框
- 无确认按钮，输入即实时生效
- 每个 zone 内一次只允许一个搜索框打开
- 每个列名右侧增加筛选下拉按钮
- 筛选支持：
  - 多选
  - 全选
  - 清空
- 搜索和筛选生效后：
  - 当前栏只显示命中的项
  - 其他两栏显示这些命中项所属 group 的全部相关项

建议文件：

- `web/src/components/workbench/WorkbenchZone.tsx`
- `web/src/components/workbench/ResizableTriPane.tsx`
- `web/src/components/workbench/CandidateGroupGrid.tsx`
- `web/src/components/workbench/WorkbenchPaneSearch.tsx`
- `web/src/components/workbench/WorkbenchColumnFilterMenu.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/test/WorkbenchPaneFilter.test.tsx`
- `web/src/test/WorkbenchSelection.test.tsx`

验证：

- 跑相关前端测试
- 跑前端 build
