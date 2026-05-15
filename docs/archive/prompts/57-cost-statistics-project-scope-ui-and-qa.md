# Prompt 57：项目状态设置 UI 与成本统计范围切换 QA

目标：补齐设置页 `项目状态管理` 的前端交互，并在成本统计页面加入 `进行中 / 所有项目` 范围 trigger，完成端到端 QA。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-project-status-cost-scope-design.md`
  - `docs/superpowers/plans/2026-04-14-project-status-cost-scope.md`
- 已完成：
  - `55-project-status-settings-foundation.md`
  - `56-cost-statistics-project-scope-backend.md`

要求：

- 设置页 `项目状态管理` 保持现有树状两栏风格，不引入花哨设计
- 设置页支持：
  - 从 OA 拉取项目
  - 新增本地项目
  - 删除本地项目或本地状态覆盖
  - `标记完成`
  - `移回进行中`
- 删除项目前要有确认文案，明确不会删除 OA 源项目和历史数据
- 成本统计页面在 `按时间 / 按项目 / 按银行 / 按费用类型` 右侧增加范围 trigger
- trigger 默认显示 `进行中`
- 用户可以切换到 `所有项目`，再次选择可回到 `进行中`
- 切换范围后，当前成本统计视图、下钻、导出预览和导出请求都要带正确 `project_scope`
- 前端 mock 和测试要包含一个已完成项目，确保过滤不是假通过

建议文件：

- `web/src/features/workbench/api.ts`
- `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- `web/src/features/cost-statistics/types.ts`
- `web/src/features/cost-statistics/api.ts`
- `web/src/pages/CostStatisticsPage.tsx`
- `web/src/app/styles.css`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/CostStatisticsApi.test.ts`
- `web/src/test/CostStatisticsPage.test.tsx`
- `web/src/test/apiMock.ts`

验证：

- 跑设置页相关前端测试
- 跑成本统计前端测试
- 跑前端 build
- 如后端改动被触发，补跑 prompt 56 的后端测试

禁止项：

- 不要改动 `form_data_db`
- 不要写入、删除或迁移 `form_data_db.form_data`
- 不要重做成本统计页面整体布局
- 不要改变成本统计既有入账口径
- 不要把项目删除做成清理历史数据
