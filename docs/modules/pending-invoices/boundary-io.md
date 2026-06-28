# 待找发票模块边界与 I/O

日期：2026-06-27

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：待找发票页面直接读取 rows/rules/filter/export API DTO，规则保存和关联变更成功后直接重读 rows；页面 API 不返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_key(s)` 或 `refresh_enqueued`。
- 当前缺口：pending invoice 页面、worker、projection、repository port 和 active storage 调用点已清零；历史 PostgreSQL migrations 仍包含旧表创建/变更记录，后续若做 fresh-schema baseline 再另行清理。
- 旧代码删除条件：已满足当前运行面；不得重新引入 pending-invoice read model、freshness gate、refresh worker 或 operation barrier target。

## 职责边界

### 负责

- 待找发票列表、规则、筛选、导出和发票关联入口。
- 待找发票 direct rows/rules/filter/export 页面合同。
- 与 invoice lifecycle 的 direct query 联动。

### 不负责

- 不拥有发票生命周期源事实。
- 不直接维护关联台关系事实源。
- 不接受 bare `all` scope 重建。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面筛选、方向、规则操作 | `PendingInvoicesPage.tsx`、`features/pendingInvoices/api.ts` | scope 必须落到 direction/filter/month |
| 关联/规则写入 | pending invoice services | 写后返回业务结果、影响月份/scope，并由页面直接重读 rows；不触发 pending-invoice read model refresh |
| Direct rows scope | `PendingInvoiceQueryService` | `direction/filter/date/page` 页面查询参数；不接受 read model scope 作为事实源 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 待找发票 rows/summary | 前端页面 | direct payload；API 不返回页面级 read model freshness 字段 |
| 规则保存结果 | API | 持久化规则并返回 affected diagnostics；页面成功后 direct refetch rows |
| 发票关联/收入状态写结果 | API/frontend | 返回业务写入结果、`affected_months` 和 `affected_scope_keys`；不返回 `read_model_scope_keys`，前端成功后直接重读 rows |
| Lifecycle source rows | `invoice_lifecycle_sql_projection.py` | 通过 direct `PendingInvoiceQueryService` 分页读取 expense/income rows 后映射 lifecycle 行 |

## 持久化与投影

- Read model：无当前运行面；旧 `pending_invoice` 只存在于历史 migrations/归档文档
- Projection：无 pending-invoice SQL projection
- Worker：无 pending-invoice worker
- Query owner：`PendingInvoiceQueryService`
- Repository owner：无 pending-invoice read-model repository port

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/PendingInvoicesPage.tsx` |
| Frontend feature/components | `web/src/features/pendingInvoices/*`、`web/src/components/pendingInvoices/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_pending_invoices.py` |
| Backend service | `pending_invoice_service.py`、`pending_invoice_rules_application_service.py`、`pending_invoice_lifecycle_service.py`、`pending_invoice_status.py` |
| Repository / SQL | `invoice_lifecycle_sql_projection.py`（通过 direct pending query 读取源 rows）；无 pending-invoice SQL projection/repository |
| Tests | `tests/test_pending_invoice*.py`、`web/src/test/PendingInvoices*.test.*`、`web/e2e/pending-invoices-*.spec.ts` |

## 依赖方向

- 允许依赖：invoice lifecycle policy/read facade、workbench relation read facade。
- 必须通过：`PendingInvoiceQueryService` 和 rules application service；`PendingInvoiceReadModelService` 已删除，页面 route 不返回迁移期 read model freshness 字段。
- 禁止绕过：重新引入 pending-invoice read model refresh；页面自行合成 invoice status。

## 测试与验证

- `tests/test_pending_invoice_service.py`
- `tests/test_pending_invoice_api.py`
- `web/e2e/pending-invoices-fanout.spec.ts`
- `web/e2e/pending-invoices-filter-sort-flow.spec.ts`

## 当前缺口和删除条件

- 修改规则、direct rows scope 或 lifecycle 映射时必须同步 API/service/lifecycle tests。
- 继续删除历史 migrations 或 fresh-schema baseline 前，必须单独评估数据库升级兼容性。
- 必须保留当前页面 API “无 freshness 字段”的回归测试。
