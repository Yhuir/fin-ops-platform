# Prompt 39：关联台确认关联 / 取消配对动作改造与读取模型接入

目标：让 `确认关联 / 取消配对` 只改 `pair relations`，并让工作台读取时叠加 active pair relations 生成 `paired/open`。

前提：

- Prompt 38 已完成
- 阅读：
  - `docs/superpowers/specs/2026-04-08-workbench-pair-relations-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-pair-relations.md`

要求：

- 改造 `POST /api/workbench/actions/confirm-link`
  - 只写 pair relation
  - 不再通过 row override 存配对关系
- 改造 `POST /api/workbench/actions/cancel-link`
  - 直接按 `row_id -> case_id -> pair relation` 取消
- 工作台读取模型需要：
  - 先取原始 OA / 银行流水 / 发票
  - 再叠加 active pair relations
  - 再叠加 overrides
  - 最后走 grouped payload
- 自动工资匹配和自动内部往来款也要统一进入 pair relations 或在读模型层统一投影成同一结构

建议文件：

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/live_workbench_service.py`
- `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
- `backend/src/fin_ops_platform/services/workbench_override_service.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_live_workbench_service.py`

交付要求：

- `确认关联 / 取消配对` 的动作返回结构保持兼容
- 配对关系真相源切换到 pair relations
- `paired/open` 分组结果不回归

验证：

- 增加 unittest
- 跑相关后端测试

