# Prompt 11：实现行选中、高亮联动与详情抽屉

目标：实现工作台核心交互口径，确保“点击行只选中，详情只通过详情按钮打开”。

前提：

- `10-workbench-v2-layout-and-resize.md` 已完成

要求：

- 点击任意行：
  - 只更新选中状态
  - 高亮同 `case_id` 的候选行
  - 不自动打开详情抽屉
- 每行保留 `详情` 按钮
- 点击 `详情` 按钮才打开右侧抽屉
- 抽屉根据行类型展示：
  - OA 详情
  - 银行流水详情
  - 发票详情
- 主表只保留直接字段，详情字段全部进抽屉

建议文件：

- `web/src/components/workbench/PaneTable.tsx`
- `web/src/components/workbench/RowActions.tsx`
- `web/src/components/workbench/DetailDrawer.tsx`
- `web/src/hooks/useWorkbenchSelection.ts`

交付要求：

- 行选中态和候选联动态都有清晰视觉差异
- 事件冒泡处理正确
- 抽屉可关闭，可切换不同记录

验证：

- 为“点击行不弹详情”写测试
- 为“点击详情按钮打开抽屉”写测试
