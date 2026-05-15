# Workbench Pair Relations Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 把关联台 `确认关联 / 取消配对` 重构成“pair relations 轻量写模型 + 前端成功后立即局部更新”的稳定路径，显著降低动作耗时。

**Architecture:** 新增独立 `workbench_pair_relations` 持久化层承载配对关系；`workbench_row_overrides` 继续只承载忽略、异常和备注等非配对覆盖；读取模型统一叠加两层状态。

**Tech Stack:** Python backend、Mongo state store、现有 live workbench / grouped workbench 双层模型、React 前端局部更新与后台静默刷新。

---

## File Map

### Backend

- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_override_service.py`
- Create: `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- Modify: `backend/src/fin_ops_platform/services/live_workbench_service.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Create or modify: `tests/test_workbench_pair_relation_service.py`
- Create or modify: `tests/test_workbench_v2_api.py`
- Create or modify: `tests/test_live_workbench_service.py`
- Create or modify: `tests/test_state_store.py`

### Frontend

- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/features/workbench/api.ts`
- Create or modify: `web/src/test/WorkbenchSelection.test.tsx`

### Docs

- Modify: `docs/product/银企核销需求.md`
- Create: `docs/superpowers/specs/2026-04-08-workbench-pair-relations-design.md`
- Create: `docs/superpowers/plans/2026-04-08-workbench-pair-relations.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`
- Modify: `README.md`

---

## Task 1: 建立 pair relations 持久化底座

- [ ] 写失败测试：支持保存、查询、取消 `pair relations`
- [ ] 在 `state_store.py` 增加 `workbench_pair_relations` 集合
- [ ] 新增 `WorkbenchPairRelationService`
- [ ] 定义 relation 文档结构：
  - `case_id`
  - `row_ids`
  - `row_types`
  - `status`
  - `relation_mode`
  - `created_by`
  - `created_at`
  - `updated_at`
- [ ] 跑针对性后端测试

## Task 2: 用 pair relations 重写确认关联 / 取消配对

- [ ] 写失败测试：`confirm-link` 只写 pair relation，不再通过 row override 记录配对关系
- [ ] 写失败测试：`cancel-link` 直接按 `row_id -> case_id -> pair relation` 取消
- [ ] 调整 server live workbench 动作入口
- [ ] 保留 override 只处理忽略、异常、备注覆盖
- [ ] 跑针对性后端测试

## Task 3: 统一工作台读取模型

- [ ] 写失败测试：工作台加载会叠加 `active pair relations`
- [ ] 自动工资匹配落入 `pair relations`
- [ ] 自动内部往来款落入 `pair relations`
- [ ] grouped payload 仍输出正确的 `paired/open`
- [ ] 跑针对性后端测试

## Task 4: 前端动作与局部更新收口

- [ ] 写失败测试：确认关联 / 取消配对成功后立即局部更新，不等整页刷新
- [ ] 保持当前前端后台静默刷新兜底
- [ ] 如果 API 返回改动，更新前端契约
- [ ] 跑针对性前端测试

## Task 5: 全量 QA 与迁移说明

- [ ] 记录旧 override pairing 与新 pair relations 的职责边界
- [ ] 补 migration / compatibility 说明
- [ ] 跑后端全量 tests
- [ ] 跑前端全量 tests
- [ ] 跑前端 build
