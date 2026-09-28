# 系统状态

入口：`/operations/app-health`。

汇总运行健康、任务、请求性能和导入事实；管理员编排只读 System Audit。

## 边界与 I/O

输入：session/OA 同步状态、registry/heartbeat、PostgreSQL 队列、import_jobs、matching scopes 和请求计时。输出：app-health、dashboard、page-audit、health/ready 与 metrics 的有界报告。

## 当前业务约定

- 四个 worker 和各任务状态分别统计，缺必要证据显示 unavailable，不伪造健康。
- import prepare、待确认和 commit 使用同一任务；文件输入失败保留可见，不冒充成功，也不等同通用 outbox 死信。
- System Audit 在调用方拥有的只读快照执行固定 page proof，GET 不修复或写入。
- 现金事实、金额、项目和查询条件不进入本模块；全局技术计数不包含现金业务明细。
- 导入任务处理动作由 import owner 执行；已读、明确结束、失败和成功分别表达。
- 运维状态轮询只刷新状态面，不能成为跨页面业务刷新总线。

## 依赖方向

[后台任务](../runtime-workers/README.md)、[权限与审计](../permissions-and-audit/README.md)、[银行流水导入](../imports-bank-transactions/README.md)、[发票导入](../imports-invoices/README.md)、[ETC 发票导入](../imports-etc-invoices/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/AppHealthOperationsPage.tsx](../../../web/src/pages/AppHealthOperationsPage.tsx)
- [web/src/contexts/AppHealthStatusContext.tsx](../../../web/src/contexts/AppHealthStatusContext.tsx)
- [web/src/components/shell/AppStatusIndicator.tsx](../../../web/src/components/shell/AppStatusIndicator.tsx)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [backend/src/fin_ops_platform/services/app_health_service.py](../../../backend/src/fin_ops_platform/services/app_health_service.py)
- [backend/src/fin_ops_platform/services/app_health_alert_service.py](../../../backend/src/fin_ops_platform/services/app_health_alert_service.py)
- [backend/src/fin_ops_platform/services/app_status_overview_service.py](../../../backend/src/fin_ops_platform/services/app_status_overview_service.py)
- [backend/src/fin_ops_platform/services/runtime_monitoring.py](../../../backend/src/fin_ops_platform/services/runtime_monitoring.py)
- [backend/src/fin_ops_platform/services/external_control_evidence.py](../../../backend/src/fin_ops_platform/services/external_control_evidence.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/external_control_evidence.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/external_control_evidence.py)
- [tests/test_app_health_api.py](../../../tests/test_app_health_api.py)
- [tests/test_app_health_service.py](../../../tests/test_app_health_service.py)
- [tests/test_app_status_overview_service.py](../../../tests/test_app_status_overview_service.py)
- [tests/test_audit_app_health_system.py](../../../tests/test_audit_app_health_system.py)
- [web/src/test/AppHealthOperationsPage.test.tsx](../../../web/src/test/AppHealthOperationsPage.test.tsx)
- [tests/test_runtime_monitoring.py](../../../tests/test_runtime_monitoring.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。
