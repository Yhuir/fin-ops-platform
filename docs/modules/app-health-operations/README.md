# 系统状态

入口：`/operations/app-health`。

管理员页面只展示“数据”和“最近导入记录”，导入历史通过右侧抽屉查询。全局状态、技术监控与只读 System Audit 保留各自服务和 API。

## 边界与 I/O

输入：session/OA 同步状态、registry/heartbeat、PostgreSQL 队列、import_jobs、matching scopes 和请求计时。输出：app-health、dashboard、page-audit、health/ready 与 metrics 的有界报告。

## 当前业务约定

- 四个 worker 和各任务状态分别统计，缺必要证据显示 unavailable，不伪造健康。
- import prepare、待确认和 commit 使用同一任务；文件输入失败保留可见，不冒充成功，也不等同通用 outbox 死信。
- System Audit 在调用方拥有的只读快照执行固定 page proof，GET 不修复或写入。
- 现金事实、金额、项目和查询条件不进入本模块；全局技术计数不包含现金业务明细。
- 导入任务处理动作由 import owner 执行；已读、明确结束、失败和成功分别表达。
- 导入活动查询在数量限制前排除完全成功与取消任务，保留部分成功；共享列表和详情将成功任务中的 `partial_success` 结果如实显示为部分完成，不改写执行状态。历史结果仍可按任务编号查询，GET 不确认已读或删除记录。
- 发票按类型（进项、销项）和导入方式（手工导入、OA 解析新增入池）分别分组，各组数量之和应与发票总数相同。OA 解析新增使用 `supplementary_count`，不把匹配到的手工发票重复计入；缺失统计显示“—”，不把未知当作零。OA 展示已完成和进行中记录，不混入明细数。
- dashboard 每次读取当前事实，不使用进程内旧快照缓存。页面在可见且激活时每 10 秒串行刷新，隐藏时暂停；手动刷新、任务处理和撤回完成后立即读取。运维状态轮询不能成为跨页面业务刷新总线。
- `GET /api/operations/import-history` 支持 `page`、`page_size`（1–100）、`batch_type`、`status`、`search`、`start_date`、`end_date`。日期按上海时区自然日，结束日期包含当天。筛选后的计数与分页行在同一 SQL 快照读取，独占创建数仅计算当前页。
- `GET /api/operations/import-history/{batch_id}` 返回真实批次详情，不用列表行代替详情。历史显示状态由 repository 统一分类；任务执行成功但结果部分成功的批次显示“部分完成”，不改写原任务状态。
- 历史抽屉保留类型、状态、日期、文件名筛选及 50/100 条分页，列表与详情使用同一抽屉，查看任务切换到既有共享任务抽屉。撤回操作仍由银行导入 owner 校验、事务执行与审计。

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
