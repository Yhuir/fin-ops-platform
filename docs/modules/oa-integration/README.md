# OA 集成

入口：`外部系统适配边界`。

提供身份、Mongo 来源同步、支付状态及角色适配、附件识别和申请人凭据能力。

## 边界与 I/O

输入：受信 token、Settings ACL/预填、同步 scope、精确 OA IDs 和来源附件。输出：身份、PostgreSQL OA/准入/附件事实、支付状态同步结果、非敏感申请人及窄项目目录。

## 当前业务约定

- OA Mongo 财务源只读；worker 一次读取范围内来源，输出 completed 与 admission 视图。任何必需来源读取失败不提交部分权威集合。
- 仅完整 all 权威快照能证明源消失；清理 active 成员与本地快照后，通过精确事件复核并删除对应外部支付状态，month/retention 不证明源删除。
- 支付状态由当前 active outflow 收敛；MySQL 写回由专用 adapter 执行，不向 Mongo 写业务。
- 附件解析以当前强身份和来源桥接统一发票池，避免重复发票及跨 OA 弱指纹猜测；API 不运行全量同步/OCR。
- OA 角色同步只消费当前 page ACL：有页面的普通用户对应 finops_app_user，固定管理员对应 finops_admin；菜单不是权限事实源。
- ETC/反提外部创建使用冻结配置、持久请求身份与显式未知结果恢复；凭据只经 owner 使用，不返回密码。
- 现金项目与成本项目目录通过各自窄只读端口，不能把外部元数据通道扩张为页面财务源。

## 依赖方向

[设置](../settings/README.md)、[权限与审计](../permissions-and-audit/README.md)、[后台任务](../runtime-workers/README.md)、[进项发票使用](../input-invoice-usage/README.md)、[ETC 票据](../etc-tickets/README.md)、[现金账](../cash/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [backend/src/fin_ops_platform/app/auth.py](../../../backend/src/fin_ops_platform/app/auth.py)
- [backend/src/fin_ops_platform/services/oa_identity_service.py](../../../backend/src/fin_ops_platform/services/oa_identity_service.py)
- [web/src/features/session/api.ts](../../../web/src/features/session/api.ts)
- [backend/src/fin_ops_platform/services/oa_role_sync_service.py](../../../backend/src/fin_ops_platform/services/oa_role_sync_service.py)
- [backend/src/fin_ops_platform/tools/settings_access_control_preflight.py](../../../backend/src/fin_ops_platform/tools/settings_access_control_preflight.py)
- [backend/src/fin_ops_platform/services/mongo_oa_adapter.py](../../../backend/src/fin_ops_platform/services/mongo_oa_adapter.py)
- [backend/src/fin_ops_platform/services/cash_oa_projects.py](../../../backend/src/fin_ops_platform/services/cash_oa_projects.py)
- [backend/src/fin_ops_platform/services/oa_projection_sync.py](../../../backend/src/fin_ops_platform/services/oa_projection_sync.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py)
- [backend/src/fin_ops_platform/app/worker.py](../../../backend/src/fin_ops_platform/app/worker.py)
- [tests/test_mongo_oa_adapter.py](../../../tests/test_mongo_oa_adapter.py)
- [tests/test_session_api.py](../../../tests/test_session_api.py)
- [tests/test_oa_projection_sync_service.py](../../../tests/test_oa_projection_sync_service.py)
- [tests/test_oa_attachment_invoice_service.py](../../../tests/test_oa_attachment_invoice_service.py)
- [tests/test_oa_attachment_invoice_promotion_service.py](../../../tests/test_oa_attachment_invoice_promotion_service.py)
- [tests/test_oa_attachment_invoice_promotion_tool.py](../../../tests/test_oa_attachment_invoice_promotion_tool.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
