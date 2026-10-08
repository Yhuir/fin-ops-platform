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

## 设置页面范围

设置页提供银行账户、OA 导入设置、OA 申请人凭据、访问账户和数据重置，默认进入银行账户。通用设置写接口只接受银行账户映射、工作台列布局、OA 导入起始日期与导入选项；其他字段明确拒绝。待找发票分类规则仅通过待找发票模块的专用规则接口修改，保存通用设置不覆盖这些规则。项目目录、单据项目归属和历史关联由原业务模块继续维护，不由设置页面管理。

设置页保存操作统一位于标题右侧。银行账户与 OA 导入设置共用“保存设置”，提交两处草稿；OA 申请人凭据仅提交当前凭据表单；访问账户提交全部已修改账户，取消仅撤销权限草稿。数据重置没有通用保存操作。保存期间禁用对应编辑区域，结果以可关闭浮层反馈，不挤压表单。

## OA 全量搜索导入

手动搜索通过独立只读源查询读取 OA Mongo，按申请日期、关键词、表单类型和流程状态分页，不受自动导入起始日期限制。普通业务页面仍查询 PostgreSQL。搜索不下载附件、不运行 OCR、不写业务事实；当前页附件统计批量读取当前版本识别结果；未解析、部分完成、失败和已完成分别展示。发票按身份去重，附件按文件计数；待解析、下载/解析失败、不支持格式与解析后非发票分别统计，不能用附件总数减发票数推算。

源库连接或查询失败明确返回 `oa_search_unavailable`，不回退本地数据、不返回成功空结果。已完成与进行中均可搜索，进行中不能导入。选中的稳定 OA 身份交给现有 `oa_manual_import.create` 任务，worker 重读源记录并使用现行附件解析器完成准备、校验流程状态，再把 OA、配置允许的发票入池与归属、手动保留标记、匹配失效范围和完成回执在同一事务提交。附件准备按已有预算分段继续，复用已解析缓存，不消耗失败重试次数；解析失败的 OA 返回明确逐条原因，不登记为成功。有效手动导入记录不受自动同步历史日期清理影响。

未导入 OA 的附件操作使用 `prepare-attachments` 后台预览，只写识别缓存，不登记正式 OA、发票或导入标记；已导入 OA 使用正式附件刷新。两种操作共用任务状态查询，完成后精确重读所选 OA，搜索、整单和明细采用同一统计函数。

搜索连接池复用，请求内身份与附件数据独立，计数和两种表单的分页由同一次源端聚合产生。相关实现：`oa_manual_search_source.py`、`oa_manual_import_service.py`、`mongo_oa_adapter.py`；验证入口：`tests.test_oa_manual_search_source`、`tests.test_import_direct_queue_postgres_integration`、`web/e2e/production-oa-manual-search.spec.ts`（显式生产只读模式）。
