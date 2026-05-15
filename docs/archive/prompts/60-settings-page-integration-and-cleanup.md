# Prompt 60：设置页页面化联调、测试与清理

目标：完成设置页页面化后的联调收口，清理关联台遗留逻辑，并补齐回归测试和文档索引。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-settings-page-route-and-tree-design.md`
  - `docs/superpowers/plans/2026-04-14-settings-page-route-and-tree.md`
- 已完成：
  - `58-settings-page-route-and-state-foundation.md`
  - `59-settings-page-sections-and-tree-ui.md`

要求：

- 清理关联台中旧设置弹窗相关遗留逻辑
- 验证设置页保存、项目同步、权限控制、数据重置回归正常
- 把相关测试全部切换到页面语义
- 更新 prompt 索引与相关文档引用
- 再次明确实现过程中禁止改动 `form_data_db`

建议文件：

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/pages/SettingsPage.tsx`
- `web/src/test/App.test.tsx`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/SettingsPage.test.tsx`
- `prompts/README.md`

验证：

- 跑设置页相关前端测试
- 跑路由相关前端测试
- 跑前端 build
- 跑 `git diff --check`

禁止项：

- 不要改动 `form_data_db`
- 不要写入、删除或迁移 `form_data_db.form_data`
- 不要再引入设置弹窗作为双入口
