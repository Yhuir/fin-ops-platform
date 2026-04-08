# Prompt 38：关联台 Pair Relations 后端底座

目标：为关联台新增独立的 `pair relations` 持久化层，用来承载“已配对关系”，替代当前把配对关系混在 row override 里的做法。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-08-workbench-pair-relations-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-pair-relations.md`

要求：

- 在 Mongo state store 中新增 `workbench_pair_relations`
- 新增 `WorkbenchPairRelationService`
- 支持：
  - 创建 active pair relation
  - 按 `case_id` 查询
  - 按 `row_id` 查询所属 active pair relation
  - 取消 / 失效化 pair relation
- relation 文档至少包含：
  - `case_id`
  - `row_ids`
  - `row_types`
  - `status`
  - `relation_mode`
  - `created_by`
  - `created_at`
  - `updated_at`

建议文件：

- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `tests/test_workbench_pair_relation_service.py`
- `tests/test_state_store.py`

交付要求：

- pair relation 可持久化、可按 row / case 检索
- 取消只影响 relation 本身，不影响其他 override 状态

验证：

- 增加 unittest
- 跑相关后端测试

