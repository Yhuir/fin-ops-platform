# Workbench Column Layout Drag Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 为关联台三栏建立列顺序持久化与拖拽重排能力，保证表头、内容、底部滚动轨道始终对齐。

**Architecture:** 列顺序作为 `workbench settings` 的一部分持久化。前端按每个 pane 的保存顺序渲染，拖拽只改变顺序，不改变单列宽度。

**Tech Stack:** Python backend app settings service、React、TypeScript、现有 workbench settings API、Vitest、unittest。

---

## File Map

### Backend

- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `tests/test_app_settings_service.py`

### Frontend

- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/features/workbench/tableConfig.ts`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- Modify: `web/src/components/workbench/CandidateGroupGrid.tsx`
- Modify: `web/src/components/workbench/WorkbenchRecordCard.tsx`
- Modify: `web/src/app/styles.css`
- Create or modify: `web/src/features/workbench/columnLayout.ts`

### Tests

- Modify: `web/src/test/apiMock.ts`
- Modify: `web/src/test/WorkbenchColumns.test.tsx`
- Create or modify: `web/src/test/WorkbenchColumnLayout.test.ts`

### Docs

- Modify: `docs/product/银企核销需求.md`
- Create: `docs/superpowers/specs/2026-04-08-workbench-column-layout-drag-design.md`
- Create: `docs/superpowers/plans/2026-04-08-workbench-column-layout-drag.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`

---

## Task 1: 设置持久化底座

- [ ] 为 settings 新增 `workbench_column_layouts`
- [ ] 规范化默认顺序、忽略未知列、补齐缺失列
- [ ] 前端 settings 类型与 API 同步
- [ ] 跑后端 settings 测试与前端 build

## Task 2: 前端按保存顺序渲染

- [ ] 抽出 pane column order helper
- [ ] 表头、内容、底部轨道统一使用同一顺序
- [ ] 写测试锁住“表头/内容顺序一致”
- [ ] 跑相关前端测试

## Task 3: 列拖拽 UI 与保存

- [ ] 为每个 pane 的列头加拖拽重排
- [ ] 本地即时预览顺序
- [ ] 保存设置时写回 column layouts
- [ ] 刷新后恢复顺序
- [ ] 跑前端 tests、build 和后端 tests
