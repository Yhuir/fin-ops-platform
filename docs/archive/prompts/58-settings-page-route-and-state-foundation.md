# Prompt 58：设置页路由与状态底座

目标：把“关联台设置”从弹窗迁移为独立页面 `/settings`，先打通路由、页面容器和状态承载，不要求本阶段完成所有 section 组件拆分。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-settings-page-route-and-tree-design.md`
  - `docs/superpowers/plans/2026-04-14-settings-page-route-and-tree.md`
- 已完成：
  - `57-cost-statistics-project-scope-ui-and-qa.md`

要求：

- 新增 `/settings` 路由
- 新增 `SettingsPage`
- 顶部 `设置` 按钮改为进入 `/settings`
- 主导航加入 `设置`
- 把设置页的加载 / 保存 / 项目同步 / 数据重置动作迁移到页面级容器
- 关联台页不再持有设置弹窗开关状态
- 允许暂时复用现有设置编辑体，但必须以页面而不是 modal 承载

建议文件：

- `web/src/pages/SettingsPage.tsx`
- `web/src/app/router.tsx`
- `web/src/app/App.tsx`
- `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/test/App.test.tsx`
- `web/src/test/WorkbenchSelection.test.tsx`

验证：

- 跑 `App` 路由相关测试
- 跑设置页相关前端测试
- 跑前端 build

禁止项：

- 不要改动 `form_data_db`
- 不要写入、删除或迁移 `form_data_db.form_data`
- 不要在本 prompt 里重做设置页所有 section UI
- 不要顺手改动设置业务规则
