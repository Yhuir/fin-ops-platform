# 操作历史

`operation-history` 是 005 管理员专用的只读审计页面，路由为 `/operations/history`。它只展示功能上线覆盖点之后持久化在 PostgreSQL `audit.events` 的操作，不补录历史。

代码入口：

- 后端：`services/audit.py`、`services/operation_history_semantics.py`、`services/operations_audit_service.py`、`postgres_repositories/operations_audit.py`、`app/server.py`。
- 前端：`pages/OperationHistoryPage.tsx`、`features/operationHistory/api.ts`。
- 数据库：`postgres/migrations/0138_operation_audit_and_financial_fact_guard.sql`、`0142_operation_history_logical_operations.sql`。

修改前同时读取 `boundary-io.md`、`tests.md` 与 `../permissions-and-audit/boundary-io.md`。
