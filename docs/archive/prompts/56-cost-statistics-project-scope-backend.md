# Prompt 56：成本统计项目范围后端过滤

目标：让成本统计后端支持 `进行中 / 所有项目` 范围过滤，默认只统计设置页中标记为 `进行中` 的项目。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-project-status-cost-scope-design.md`
  - `docs/superpowers/plans/2026-04-14-project-status-cost-scope.md`
- 已完成：
  - `55-project-status-settings-foundation.md`

要求：

- 成本统计 API 增加 `project_scope=active|all`
- 未传 `project_scope` 时默认 `active`
- `active` 只包含设置页项目状态为 `进行中` 的成本条目
- `all` 保持原有所有项目口径
- 非法 `project_scope` 必须有固定错误口径，不要静默忽略
- 项目状态判断必须来自设置页项目状态管理，不要在成本统计页面或统计服务里重新推断
- 无 project id 但有 project name 的条目要按项目名称 fallback 判断
- 未登记项目默认按 `进行中` 处理
- 月份汇总、explorer、项目视图、银行视图、费用类型视图、导出预览、导出文件必须使用同一个过滤口径

建议文件：

- `backend/src/fin_ops_platform/services/cost_statistics_service.py`
- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_cost_statistics_service.py`
- `tests/test_cost_statistics_api.py`

验证：

- 跑成本统计 service/API 后端测试
- 覆盖 `active`、`all`、非法 scope、未登记项目 fallback、导出口径一致性

禁止项：

- 不要改动 `form_data_db`
- 不要写入、删除或迁移 `form_data_db.form_data`
- 不要改变成本统计既有入账口径，只增加项目状态范围过滤
- 不要在本 prompt 中改设置页 UI
