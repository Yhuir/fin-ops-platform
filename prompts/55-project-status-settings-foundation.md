# Prompt 55：项目状态管理设置后端基础

目标：补齐设置页 `项目状态管理` 的后端基础，让项目能从 OA 项目管理拉取，也能在 app 内新增、删除和切换 `进行中 / 已完成`。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-project-status-cost-scope-design.md`
  - `docs/superpowers/plans/2026-04-14-project-status-cost-scope.md`
- 已完成：
  - `54-workbench-sheet-layout-states-and-qa.md`

要求：

- 复用现有 `AppSettingsService`、`ApplicationStateStore`、`ProjectCostingService` 和 integration/project sync 能力
- settings payload 中的项目列表要能区分 `进行中 / 已完成`
- 项目来源要能区分 `oa` 和 `manual`
- 手动新增项目默认进入 `进行中`
- 删除项目只删除 app 本地项目或本地状态覆盖，不删除 OA 源项目，不删除历史 OA / 发票 / 银行流水 / pair 数据
- OA 项目同步必须走现有 integration/service 层，不得直接改 OA 源库
- 如果 OA 同步失败，返回清晰错误，且不能破坏已保存 settings
- 未登记项目后续在成本统计中默认按 `进行中` 处理，相关 helper 可以在本 prompt 里先补好

建议文件：

- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/project_costing.py`
- `backend/src/fin_ops_platform/services/integrations.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_app_settings_service.py`
- `tests/test_workbench_settings_sync_api.py`

验证：

- 跑相关 settings 后端测试
- 如新增 API endpoint，补 server/API 测试

禁止项：

- 不要改动 `form_data_db`
- 不要写入、删除或迁移 `form_data_db.form_data`
- 不要删除 OA 源系统项目
- 不要把删除项目做成清理历史成本数据
- 不要顺手改成本统计 UI，本 prompt 只做后端设置基础
