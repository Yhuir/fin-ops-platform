# Prompt 48：关联台列顺序渲染与拖拽 UI

目标：让三栏表头、内容行、底部滚动轨道都按保存好的列顺序渲染，并加入列拖拽重排 UI。

前提：

- 已完成：
  - `47-workbench-column-layout-foundation.md`

要求：

- 三栏每个 pane 共用一套列顺序
- 表头 / 内容 / 底部轨道必须严格同序
- 拖拽只改顺序，不改列宽
- 拖拽过程本地即时预览

建议文件：

- `web/src/features/workbench/tableConfig.ts`
- `web/src/features/workbench/columnLayout.ts`
- `web/src/components/workbench/CandidateGroupGrid.tsx`
- `web/src/components/workbench/WorkbenchRecordCard.tsx`
- `web/src/app/styles.css`
- `web/src/test/WorkbenchColumnLayout.test.ts`

验证：

- 跑相关前端测试
- 跑前端 build
