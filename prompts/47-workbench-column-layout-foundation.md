# Prompt 47：关联台列顺序持久化底座

目标：先把三栏列顺序作为 `workbench settings` 的一部分持久化，建立默认顺序、设置接口和前端类型映射。

前提：

- 阅读：
  - `银企核销需求.md`
  - `docs/superpowers/specs/2026-04-08-workbench-column-layout-drag-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-column-layout-drag.md`
- 已完成：
  - `46-workbench-pane-sort-and-qa.md`

要求：

- settings 新增 `workbench_column_layouts`
- 后端要：
  - 补默认顺序
  - 忽略未知列
  - 补齐缺失列
- 前端要：
  - settings 类型与 API 映射支持 column layouts
  - 保存设置时透传该字段
- 这一阶段先不做拖拽 UI

建议文件：

- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_app_settings_service.py`
- `web/src/features/workbench/types.ts`
- `web/src/features/workbench/api.ts`
- `web/src/test/apiMock.ts`

验证：

- 跑相关后端 tests
- 跑相关前端 tests
- 跑前端 build
