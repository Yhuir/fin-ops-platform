# 数据安全与重置

入口：`设置控制面`。

拥有限定业务范围的数据重置和恢复凭据校验，不接收任意表或 SQL。

## 边界与 I/O

输入：管理员 session、当前 OA 密码复核、reason、精确影响 fingerprint、一次性 recovery receipt 和幂等键。输出：job、精确计数、审计及必要领域任务。

## 当前业务约定

- API 原子消费 receipt、创建任务/outbox 与审计；settings-maintenance 执行实际清理。
- worker 锁定目标后重算范围，未知、漂移或活动任务在删除前拒绝。
- 通过对应 owner 操作明确登记的业务表，现金不属于普通 reset 范围。
- 恢复点须验证可恢复性并绑定本次范围；主数据库本体不删除，已有平台备份不作为任务临时文件清理。
- 任务完成后页面正常查询当前事实；不在 HTTP 请求内运行大规模删除。

## 依赖方向

[设置](../settings/README.md)、[权限与审计](../permissions-and-audit/README.md)、[后台任务](../runtime-workers/README.md)、[现金账](../cash/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [backend/src/fin_ops_platform/services/settings_data_reset_service.py](../../../backend/src/fin_ops_platform/services/settings_data_reset_service.py)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [web/src/pages/SettingsPage.tsx](../../../web/src/pages/SettingsPage.tsx)
- [web/src/components/settings/SettingsDataResetDialogs.tsx](../../../web/src/components/settings/SettingsDataResetDialogs.tsx)
- [web/src/components/shell/AppStatusIndicator.tsx](../../../web/src/components/shell/AppStatusIndicator.tsx)
- [web/src/pages/AppHealthOperationsPage.tsx](../../../web/src/pages/AppHealthOperationsPage.tsx)
- [tests/test_oa_identity_service.py](../../../tests/test_oa_identity_service.py)
- [tests/test_app_health_api.py](../../../tests/test_app_health_api.py)
- [tests/test_settings_data_reset_service.py](../../../tests/test_settings_data_reset_service.py)
- [tests/test_postgres_state_store.py](../../../tests/test_postgres_state_store.py)
- [tests/test_postgres_state_store_integration.py](../../../tests/test_postgres_state_store_integration.py)
- [tests/test_mongo_oa_adapter.py](../../../tests/test_mongo_oa_adapter.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
