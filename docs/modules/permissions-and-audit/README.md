# 权限与审计

入口：`公共请求边界`。

OA 负责证明身份，App 根据当前 Settings 页面 ACL 决定访问；审计固定服务端 actor 与请求身份。

## 边界与 I/O

输入：真实 OA token/session、同版本 ACL snapshot、精确 route 与 action。输出：allowed/allowed_page_keys/can_admin_access、授权决定和审计上下文。

## 当前业务约定

- 固定管理员 YNSYLP005；其他用户仅获明确 page_keys。OA roles/menu 和环境名单不构成 App grant。
- 受保护请求在 body 解析和业务执行前校验；未知路由、缺配置或 provider 失败拒绝。纯查询 POST 与 mutation 依明确路由策略区分。
- 同次判断最多读取一次 ACL snapshot，撤权下一请求生效；服务不自行读取 cookie/header。
- 客户端 actor/createdBy 不可信；审计身份和 request ID 来自请求边界。业务状态合法性由各领域 service 判断。
- 现金需要同样授权，但现金正文不进入全局历史、System Audit 或普通任务指标；ACL 修改的安全审计保留。
- 三类已登记导入任务共享权限与私人草稿 owner 校验分别处理，不扩张设置、现金或其他任务权限。
- 令牌、密码、完整附件和原始敏感 payload 不进入文档、日志或未经授权的响应。

## 依赖方向

[设置](../settings/README.md)、[OA 集成](../oa-integration/README.md)、[操作历史](../operation-history/README.md)、[现金账](../cash/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [backend/src/fin_ops_platform/app/auth.py](../../../backend/src/fin_ops_platform/app/auth.py)
- [backend/src/fin_ops_platform/services/access_control_service.py](../../../backend/src/fin_ops_platform/services/access_control_service.py)
- [backend/src/fin_ops_platform/services/audit.py](../../../backend/src/fin_ops_platform/services/audit.py)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [web/src/features/session/api.ts](../../../web/src/features/session/api.ts)
- [web/src/contexts/SessionContext.tsx](../../../web/src/contexts/SessionContext.tsx)
- [web/src/components/auth/SessionGate.tsx](../../../web/src/components/auth/SessionGate.tsx)
- [web/src/contexts/AppHealthStatusContext.tsx](../../../web/src/contexts/AppHealthStatusContext.tsx)
- [backend/src/fin_ops_platform/app/route_access_policy.py](../../../backend/src/fin_ops_platform/app/route_access_policy.py)
- [backend/src/fin_ops_platform/services/page_audit_registry.py](../../../backend/src/fin_ops_platform/services/page_audit_registry.py)
- [tests/test_auth_guard.py](../../../tests/test_auth_guard.py)
- [tests/test_permissions_write_entry_inventory.py](../../../tests/test_permissions_write_entry_inventory.py)
- [web/e2e/permissions-role-matrix.spec.ts](../../../web/e2e/permissions-role-matrix.spec.ts)
- [tests/test_audit_service.py](../../../tests/test_audit_service.py)
- [tests/app_test_support.py](../../../tests/app_test_support.py)
- [tests/test_turnover_suggestion_retirement_postgres.py](../../../tests/test_turnover_suggestion_retirement_postgres.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
