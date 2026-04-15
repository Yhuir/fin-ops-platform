# Prompt 53：关联台三栏 Sheet 化样式底座

目标：把 `已配对 / 未配对` 两个区域中的三栏候选项，从当前 `block / card stack` 风格改成更接近 Excel / sheet 的样式底座。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-workbench-sheet-layout-design.md`
  - `docs/superpowers/plans/2026-04-14-workbench-sheet-layout.md`
- 已完成：
  - `49-workbench-column-layout-save-and-qa.md`

要求：

- 只改样式表达，不改后端接口、不改 grouped payload
- 不改现有列定义
- 不改现有 tag 文案、颜色和出现位置
- 不改现有按钮、动作和业务逻辑
- 每个候选组需要表现为统一的 `sheet band`
- 三栏之间只保留轻量竖向分隔
- 每栏内多条记录之间只保留轻量横向分隔
- 去掉 record 级厚边框、圆角卡片感和浮起 hover

建议文件：

- `web/src/app/styles.css`
- `web/src/components/workbench/CandidateGroupGrid.tsx`
- `web/src/components/workbench/CandidateGroupCell.tsx`
- `web/src/components/workbench/WorkbenchRecordCard.tsx`
- `web/src/test/CandidateGroupGrid.test.tsx`

验证：

- 跑相关前端测试
- 跑前端 build

禁止项：

- 不要改后端
- 不要改列和数据
- 不要把三栏重写成真正的 table
- 不要顺手改搜索、筛选、排序、详情逻辑
