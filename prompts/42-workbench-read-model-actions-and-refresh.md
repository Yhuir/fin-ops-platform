# Prompt 42：关联台动作与 Read Model 增量刷新

目标：把 `确认关联 / 取消配对` 改成“只写 pair relations + 增量修补 read model”，并让页面加载优先读 read model。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-08-workbench-materialized-read-model-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-materialized-read-model.md`
  - 已完成 `41-workbench-read-model-foundation.md`

要求：

- `confirm-link` 只改 pair relation，不再依赖整页重建
- `cancel-link` 只改 pair relation，不再依赖整页重建
- 动作成功后，同步修补受影响 scope 的 read model
- `/api/workbench` 优先读取 read model，缺失时才回退实时重建

建议文件：

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_query_service.py`
- `backend/src/fin_ops_platform/services/live_workbench_service.py`
- `tests/test_workbench_v2_api.py`

验证：

- 增加 unittest
- 跑相关后端测试
