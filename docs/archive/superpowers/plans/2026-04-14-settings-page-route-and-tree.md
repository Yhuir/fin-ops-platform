# Settings Page Route And Tree Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 把“关联台设置”从弹窗迁移到独立页面 `/settings`，并逐步重构为树状两栏模块化设置页。

**Architecture:** 先以 `SettingsPage` 承接 settings API 的页面级加载、保存、项目同步和数据重置，再在第二阶段把现有大组件拆成左栏树导航和多个 section 组件，最后清理关联台中的 modal 遗留逻辑并完成回归验证。

**Tech Stack:** React、TypeScript、React Router、现有 `fetchWorkbenchSettings/saveWorkbenchSettings` API、Vitest + Testing Library。

---

## File Map

### Frontend

- Create: `web/src/pages/SettingsPage.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- Create or modify: `web/src/components/settings/*`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/app/styles.css`

### Tests

- Modify: `web/src/test/App.test.tsx`
- Modify: `web/src/test/WorkbenchSelection.test.tsx`
- Create or modify: `web/src/test/SettingsPage.test.tsx`

### Docs

- Create: `docs/superpowers/specs/2026-04-14-settings-page-route-and-tree-design.md`
- Create: `docs/superpowers/plans/2026-04-14-settings-page-route-and-tree.md`
- Create: `prompts/58-settings-page-route-and-state-foundation.md`
- Create: `prompts/59-settings-page-sections-and-tree-ui.md`
- Create: `prompts/60-settings-page-integration-and-cleanup.md`
- Modify: `prompts/README.md`

---

## Task 1: `/settings` 页面与路由底座

- [x] 写失败测试：`/settings` 能直接渲染设置页
- [x] 写失败测试：从顶部入口能进入 `/settings`
- [x] 新增 `SettingsPage`
- [x] 新增 `/settings` 路由
- [x] 主导航加入 `设置`
- [x] 顶部 `设置` 按钮改为路由跳转
- [x] 把设置页加载 / 保存 / 项目同步 / 数据重置动作迁移到页面容器
- [x] 明确禁止改动 `form_data_db`
- [x] 跑前端相关测试

## Task 2: 树状两栏与 section 模块化

- [x] 写失败测试：设置页左栏树和右栏内容区稳定存在
- [x] 抽出 `SettingsTreeNav`
- [x] 抽出 `SettingsPageHeader`
- [x] 拆分项目、银行、保OA、冲账规则、访问账户、数据重置 section
- [x] 保持现有 API 语义，不在本任务改动业务规则
- [x] 跑设置页相关前端测试

## Task 3: 联调与清理

- [x] 清理关联台里的设置 modal 入口与遗留状态
- [x] 更新设置相关交互测试到页面语义
- [x] 验证权限、保存、项目同步、数据重置仍可用
- [x] 更新 prompt 索引和文档引用
- [x] 跑前端 build
- [x] 跑 `git diff --check`
