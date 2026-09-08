# App Health Operations 模块边界与 I/O

日期：2026-08-15

## 职责

- 现金不在 page audit registry 或按接口页面耗时记录中；不得查询 `cash.*`、返回现金项目/金额/ID/查询条件。全局 HTTP 并发/错误计数可保留，技术日志现金路径统一脱敏为 `/api/cash`。现金性能通过已授权的专用只读测量验证，不塞回系统状态页。

- 聚合 session、OA sync、background jobs、四个 required worker、PostgreSQL 通用 outbox、Workbench matching dirty scopes 和依赖状态。
- 展示 HTTP/DB request timing、import inventory、operation audit。
- 编排只读 canonical page proof / System Audit；前端只允许 App Health 发起固定 System Audit，业务页面不暴露 Audit 控件。
- Admin-only；不直接修改 business facts。

## 输入

| 输入 | Owner |
| --- | --- |
| Health/dependency state | app health services |
| Worker registry/heartbeat | runtime worker registry/repository |
| PostgreSQL queue metrics | runtime monitoring repository |
| Workbench matching scopes | `job.workbench_matching_dirty_scopes`；只读 status/last_error |
| API/DB timing | request metrics collector |
| Canonical audit | page audit repositories，一个 caller-owned read-only snapshot |

## 输出

- `/api/app-health`：bounded global status。
- `/api/operations/app-health-dashboard`：admin-only inventory/performance/runtime DTO。
- `/api/operations/app-health/page-audit`：后端 page proof dispatch 与前端唯一 System Audit 的 bounded report。
- `/health`、`/health/ready`、`/metrics`：liveness/readiness/Prometheus。

输出不包含旧 projection registry、scope/readiness 或 freshness summary。Queue 只显示 PostgreSQL 通用 event types，
缺少必要字段时必须标记 unavailable，不能伪造 queue healthy。

`workbench_matching.status=stale|rebuilding|error` 必须把 Workbench domain 标为 busy/yellow；failed scope 产生 critical alert 并携带 scope 与错误。该诊断不阻断全局写入，也不创建已退役的 `workbench_matching` BackgroundJob。

## 禁止边界

- 不 enqueue 修复，不写业务表，不清 queue/DLQ，不伪造 heartbeat。
- 不把 dashboard/Audit 作为业务页面事实来源。
- 不在 `/health/ready` 热路径执行无界 SQL 或外部管理接口查询。

## 验证

`tests/test_app_health_api.py`、`tests/test_app_health_service.py`、
`tests/test_app_status_overview_service.py`、`tests/test_audit_app_health_system.py`、
`web/src/test/AppHealthOperationsPage.test.tsx`。
