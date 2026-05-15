# Prompt 10：实现三栏二维工作台与完整拖拽

目标：把主工作台做成上下两区、三栏对齐的 Excel 风格布局，并支持完整拖拽和收起。

前提：

- `09-workbench-v2-web-foundation.md` 已完成

要求：

- 页面分成两个 zone：
  - 已配对
  - 未配对
- 每个 zone 内固定三栏：
  - OA
  - 银行流水
  - 进项 / 销项发票
- 两条竖向 splitter 必须支持完整拖动
- 任意一栏都可以拖到 0 宽，视为收起
- 收起后可通过再次拖拽或顶部按钮恢复
- 上下两区必须共享同一套宽度状态
- 各栏内容可独立滚动，表头固定

建议文件：

- `web/src/components/workbench/ResizableTriPane.tsx`
- `web/src/components/workbench/WorkbenchZone.tsx`
- `web/src/components/workbench/PaneTable.tsx`
- `web/src/hooks/useResizablePanes.ts`

限制：

- 不引入 AG Grid、Handsontable 这类重型表格库
- 优先用语义化 table + CSS Grid + Pointer Events

交付要求：

- splitter 拖动流畅
- 可以切到只看一栏、两栏、三栏
- 三栏变化同时作用于上下两区

验证：

- 组件测试覆盖拖拽和收起
- 手工验证 splitter 能拖到 0
