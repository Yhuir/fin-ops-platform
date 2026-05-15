# Prompt 49：关联台列顺序保存与 QA

目标：把拖拽后的列顺序真正保存到 settings，并在刷新和重新登录后恢复。

前提：

- 已完成：
  - `48-workbench-column-layout-rendering-and-drag-ui.md`

要求：

- 保存设置时写回 `workbench_column_layouts`
- 刷新后恢复
- 下次登录后恢复
- 和现有搜索、筛选、排序、放大、选择、详情交互兼容

建议文件：

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- `web/src/test/apiMock.ts`
- `web/src/test/WorkbenchColumnLayout.test.ts`
- `web/src/test/WorkbenchSelection.test.tsx`

验证：

- 跑前端全量 tests
- 跑前端 build
- 跑后端相关 tests
