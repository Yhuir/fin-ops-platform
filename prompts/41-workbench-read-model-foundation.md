# Prompt 41：关联台 Read Model 后端底座

目标：为关联台新增独立的 `workbench_read_models` 持久化层，用来缓存已经组装好的关联台快照，为后续动作提速和页面快速加载做基础。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-08-workbench-materialized-read-model-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-materialized-read-model.md`

要求：

- 在 Mongo state store 中新增 `workbench_read_models`
- 新增 `WorkbenchReadModelService`
- 支持：
  - 按 `scope=all|YYYY-MM` 保存 read model
  - 按 `scope` 查询 read model
  - 删除某个 `scope` 的 read model
- read model 文档至少包含：
  - `scope_key`
  - `scope_type`
  - `generated_at`
  - `payload`

建议文件：

- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/workbench_read_model_service.py`
- `tests/test_workbench_read_model_service.py`
- `tests/test_state_store.py`

交付要求：

- read model 可持久化、可按 scope 检索
- 不影响现有 imports / matching / overrides 的存储逻辑

验证：

- 增加 unittest
- 跑相关后端测试
