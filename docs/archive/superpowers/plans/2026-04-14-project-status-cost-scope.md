# Project Status Cost Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让设置页管理项目的 `进行中 / 已完成` 状态，并让成本统计页面可在 `进行中 / 所有项目` 范围间切换。

**Architecture:** 复用现有 `AppSettingsService` 的 `completed_project_ids` 和 `ProjectCostingService.list_projects()`，补齐本地项目新增 / 删除 / OA 项目同步能力。成本统计 API 增加 `project_scope=active|all`，由后端在统一成本条目过滤层应用，前端 trigger 只负责传参和刷新。

**Tech Stack:** Python services + in-process API server、Mongo-backed app state store、React、TypeScript、Vitest + Testing Library、pytest。

---

## File Map

### Backend

- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Modify: `backend/src/fin_ops_platform/services/project_costing.py`
- Modify: `backend/src/fin_ops_platform/services/integrations.py`
- Modify: `backend/src/fin_ops_platform/services/cost_statistics_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`

### Frontend

- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- Modify: `web/src/features/cost-statistics/types.ts`
- Modify: `web/src/features/cost-statistics/api.ts`
- Modify: `web/src/pages/CostStatisticsPage.tsx`
- Modify: `web/src/app/styles.css`

### Tests

- Modify: `tests/test_app_settings_service.py`
- Modify: `tests/test_workbench_settings_sync_api.py`
- Modify: `tests/test_cost_statistics_service.py`
- Modify: `tests/test_cost_statistics_api.py`
- Modify: `web/src/test/WorkbenchSelection.test.tsx`
- Modify: `web/src/test/CostStatisticsApi.test.ts`
- Modify: `web/src/test/CostStatisticsPage.test.tsx`
- Modify: `web/src/test/apiMock.ts`

### Docs

- Create: `docs/superpowers/specs/2026-04-14-project-status-cost-scope-design.md`
- Create: `docs/superpowers/plans/2026-04-14-project-status-cost-scope.md`
- Create: `prompts/55-project-status-settings-foundation.md`
- Create: `prompts/56-cost-statistics-project-scope-backend.md`
- Create: `prompts/57-cost-statistics-project-scope-ui-and-qa.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`

---

## Task 1: 设置页项目状态管理后端基础

- [ ] 写失败测试：settings payload 返回 OA 项目 + 手动项目，并包含 `source`、`project_status`
- [ ] 写失败测试：用户能新增本地项目，项目默认 `进行中`
- [ ] 写失败测试：用户能删除本地项目或本地项目覆盖，但不会触碰 OA 源项目
- [ ] 写失败测试：用户能触发 OA 项目同步，失败时返回清晰错误且不破坏现有设置
- [ ] 扩展 `ApplicationStateStore` 的 app settings 归一化和保存字段
- [ ] 扩展 `AppSettingsService` 的项目状态读写方法
- [ ] 如现有 `ProjectCostingService` 缺少删除本地项目能力，补一个只删除 app 本地项目的方法
- [ ] 在 `server.py` 增加最小项目管理 endpoint 或安全扩展现有 settings endpoint
- [ ] 明确禁止任何实现写入或删除 `form_data_db`
- [ ] 跑相关后端测试

## Task 2: 成本统计项目范围后端过滤

- [ ] 写失败测试：`GET /api/cost-statistics/explorer` 未传 `project_scope` 时只返回 `进行中`
- [ ] 写失败测试：`project_scope=all` 返回 `进行中 + 已完成`
- [ ] 写失败测试：非法 `project_scope` 返回固定错误
- [ ] 写失败测试：导出预览和导出结果使用同一个 `project_scope`
- [ ] 在 `CostStatisticsService` 增加集中式项目范围过滤，避免各视图重复实现
- [ ] 对无 project id 但有 project name 的成本条目增加 fallback 判断
- [ ] 对未登记项目默认按 `进行中` 处理
- [ ] 更新成本统计 API handler 解析并传递 `project_scope`
- [ ] 跑成本统计后端相关测试

## Task 3: 设置页项目状态管理 UI

- [ ] 写失败前端测试：设置页能展示 `进行中 / 已完成` 两栏项目
- [ ] 写失败前端测试：新增项目成功后出现在 `进行中`
- [ ] 写失败前端测试：标记完成 / 移回进行中会更新设置
- [ ] 写失败前端测试：删除项目前有确认文案，且文案说明不会删除 OA 源项目
- [ ] 写失败前端测试：点击 `从 OA 拉取项目` 会调用后端 sync action 并刷新列表
- [ ] 更新 `web/src/features/workbench/api.ts` 的 settings 类型和请求方法
- [ ] 在 `WorkbenchSettingsModal` 补齐新增、删除、同步和状态切换交互
- [ ] 保持设置页现有树状两栏风格，不新增花哨视觉
- [ ] 更新 `web/src/test/apiMock.ts`
- [ ] 跑设置页相关前端测试

## Task 4: 成本统计范围 trigger 与端到端 QA

- [ ] 写失败前端测试：成本统计页面默认请求带 `project_scope=active` 或等效默认范围
- [ ] 写失败前端测试：用户切换到 `所有项目` 后 explorer、summary、导出预览、导出请求都带 `project_scope=all`
- [ ] 写失败前端测试：用户切回 `进行中` 后重新拉取当前视图数据
- [ ] 在 `CostStatisticsPage` 的 view switcher 右侧加入范围 trigger
- [ ] 更新 `web/src/features/cost-statistics/api.ts` 的请求参数和 export query builder
- [ ] 更新类型定义和 mock 数据，让完成项目能在测试中被过滤
- [ ] 跑成本统计前端测试
- [ ] 跑前端 build
- [ ] 跑后端相关回归测试
