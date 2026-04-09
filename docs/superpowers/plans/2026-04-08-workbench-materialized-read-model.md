# Workbench Pair Relations + Read Model Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 在 `pair relations` 轻量写模型基础上，引入 `workbench read model` 物化快照，让 `确认关联 / 取消配对` 更快，同时显著降低关联台整页 load 成本。

**Architecture:** 三层状态：
- `workbench_pair_relations`
- `workbench_row_overrides`
- `workbench_read_models`

**Tech Stack:** Python backend、Mongo state store、现有 live workbench / grouped workbench 双层模型、React 前端局部更新与后台静默刷新。

---

## File Map

### Backend

- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Create: `backend/src/fin_ops_platform/services/workbench_read_model_service.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- Modify: `backend/src/fin_ops_platform/services/live_workbench_service.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_query_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Create or modify: `tests/test_workbench_read_model_service.py`
- Create or modify: `tests/test_state_store.py`
- Create or modify: `tests/test_workbench_v2_api.py`

### Frontend

- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/features/workbench/api.ts`
- Create or modify: `web/src/test/WorkbenchSelection.test.tsx`

### Docs

- Modify: `docs/product/银企核销需求.md`
- Create: `docs/superpowers/specs/2026-04-08-workbench-materialized-read-model-design.md`
- Create: `docs/superpowers/plans/2026-04-08-workbench-materialized-read-model.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`
- Modify: `README.md`

---

## Task 1: 建立 workbench read model 持久化底座

- [ ] 写失败测试：支持按 `scope=all|YYYY-MM` 保存、读取、删除 read model
- [ ] 在 `state_store.py` 增加 `workbench_read_models` 集合
- [ ] 新增 `WorkbenchReadModelService`
- [ ] 跑针对性后端测试

## Task 2: 动作改成写模型 + 增量读模型更新

- [ ] 写失败测试：`confirm-link` 只改 pair relation 并修补 read model
- [ ] 写失败测试：`cancel-link` 只改 pair relation 并修补 read model
- [ ] 页面加载优先读 read model，缺失时才回退实时重建
- [ ] 跑针对性后端测试

## Task 3: 前端局部更新、静默刷新与性能 QA

- [ ] 写失败测试：动作成功后立即局部更新，不等待整页重载
- [ ] 保持后台静默刷新兜底
- [ ] 跑后端全量 tests
- [ ] 跑前端全量 tests
- [ ] 跑前端 build
