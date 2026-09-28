# 设置

入口：`/settings`。

拥有平台设置、配置版本、页面 ACL、OA 凭据及数据重置控制面；业务模块消费其明确配置端口。

## 边界与 I/O

输入：普通设置、独立 family 的 expected_version、管理员完整 accounts[{username,page_keys}]、受信 session。输出：配置、版本、允许页面集合、非敏感选项与显式后台任务。

## 当前业务约定

- YNSYLP005 是固定管理员；普通账号仅按页面集合授权，缺席或空集合拒绝。权限 evaluator 属于 permissions-and-audit。
- 普通 settings API 不接受 ACL 字段；专用 ACL GET/PUT 仅管理员可用。用户名规范化保留真实拼写，重复/未知 page key 拒绝。
- 配置、CAS 和 durable audit 同事务；语义 no-op 不递增版本或触发外部写入。OA 成员同步失败明确返回，不能伪报成功。
- 成本标签、批量账务选择、银行要求、支付规则与预填配置各有 family 及版本，调用者不访问服务私有 snapshot。
- OA 预填配置可由获权用户只读，管理员编辑；命令批次冻结当时配置。
- 数据重置委托专门安全服务及 settings-maintenance，普通保存不触发跨页查询。

## 依赖方向

[权限与审计](../permissions-and-audit/README.md)、[OA 集成](../oa-integration/README.md)、[数据安全与重置](../data-safety-reset/README.md)、[后台任务](../runtime-workers/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/SettingsPage.tsx](../../../web/src/pages/SettingsPage.tsx)
- [web/src/features/workbench/api.ts](../../../web/src/features/workbench/api.ts)
- [backend/src/fin_ops_platform/app/routes_settings.py](../../../backend/src/fin_ops_platform/app/routes_settings.py)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [backend/src/fin_ops_platform/services/settings_data_reset_job.py](../../../backend/src/fin_ops_platform/services/settings_data_reset_job.py)
- [backend/src/fin_ops_platform/services/runtime_worker_handlers.py](../../../backend/src/fin_ops_platform/services/runtime_worker_handlers.py)
- [backend/src/fin_ops_platform/services/app_settings_service.py](../../../backend/src/fin_ops_platform/services/app_settings_service.py)
- [backend/src/fin_ops_platform/services/settings_data_reset_service.py](../../../backend/src/fin_ops_platform/services/settings_data_reset_service.py)
- [backend/src/fin_ops_platform/services/oa_applicant_credentials.py](../../../backend/src/fin_ops_platform/services/oa_applicant_credentials.py)
- [backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py](../../../backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py)
- [tests/test_app_settings_service.py](../../../tests/test_app_settings_service.py)
- [tests/test_workbench_settings_sync_api.py](../../../tests/test_workbench_settings_sync_api.py)
- [tests/test_oa_role_sync_service.py](../../../tests/test_oa_role_sync_service.py)
- [tests/test_permissions_write_entry_inventory.py](../../../tests/test_permissions_write_entry_inventory.py)
- [tests/test_settings_data_reset_service.py](../../../tests/test_settings_data_reset_service.py)
- [web/e2e/permissions-role-matrix.spec.ts](../../../web/e2e/permissions-role-matrix.spec.ts)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
