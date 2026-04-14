# Prompt 50：设置页数据重置后端底座

目标：为关联台设置页新增一套独立的高风险数据管理动作后端底座，支持：

- `清除所有银行流水数据`
- `清除所有发票（进销）数据`
- `清除所有 OA 数据并重新写入`

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-14-settings-data-reset-tools-design.md`
  - `docs/superpowers/plans/2026-04-14-settings-data-reset-tools.md`

要求：

- 新增独立 service 负责数据重置动作
- 建立固定白名单集合组，不允许前端传任意 collection 名
- 明确禁止操作：
  - `form_data_db.form_data`
  - `app_settings`
  - 所有 `*_meta`
- reset API 必须要求一次性的 `oa_password`，并校验该密码属于当前 OA session 用户
- `oa_password` 不能落库、不能写日志、不能出现在审计明文、异常堆栈或 API 响应中
- 未提供或校验失败时，不允许执行任何清理、缓存失效或 OA 重建动作
- 支持三类 reset action 的后端入口与返回摘要

建议文件：

- `backend/src/fin_ops_platform/services/settings_data_reset_service.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_settings_data_reset_service.py`
- `tests/test_workbench_v2_api.py`

交付要求：

- 能按固定集合组执行清理
- 返回 `action / status / deleted_counts / message`
- 所有危险动作均有权限校验和当前 OA 用户密码复核

验证：

- 增加 unittest
- 覆盖密码缺失 / 密码错误时不会删除集合、不会触发重建
- 覆盖响应和日志中不包含 `oa_password`
- 跑相关后端测试
