# Prompt 54：关联台三栏 Sheet 化状态兼容与 QA

目标：在 sheet 化底座完成后，收口 `单条撑满 / 多条分行`、状态兼容和 QA，确保新样式在真实工作台交互中可用。

前提：

- 已完成：
  - `53-workbench-sheet-layout-foundation.md`

要求：

- 当某栏只有 1 条记录而其他栏有多条记录时，单条项要在视觉上撑满整组高度，接近 Excel 合并单元格
- 多条记录仍按当前顺序分行显示，但只保留 sheet 风格的轻量分隔
- 空栏要融入同一组背景，不再像独立空卡片
- hover、selected、related、search highlight 要与新背景体系兼容
- action column 继续保留，但视觉上要属于整行，不再像卡片尾块
- `已配对 / 未配对` 两区行为和样式必须一致

建议文件：

- `web/src/app/styles.css`
- `web/src/components/workbench/CandidateGroupCell.tsx`
- `web/src/components/workbench/WorkbenchRecordCard.tsx`
- `web/src/test/CandidateGroupGrid.test.tsx`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/WorkbenchColumns.test.tsx`

验证：

- 跑相关前端测试
- 跑前端 build

禁止项：

- 不要改 tag、列内容和 action 语义
- 不要改后端 contract
- 不要引入新的视觉语义颜色体系
