# 待找发票模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：待找发票页面读取 `pending_invoice` scoped read model，规则保存和关联变更触发精确 scope refresh。
- 当前缺口：pending invoice 同时依赖 search、invoice lifecycle、workbench relation，变更时必须同时核验 fan-out。
- 旧代码删除条件：旧 API 直查路径不再被前端或 tests 引用。

## 职责边界

### 负责

- 待找发票列表、规则、筛选、导出和发票关联入口。
- `pending_invoice` read model 的 direction/filter/month scope。
- 与 search/invoice lifecycle 的投影联动。

### 不负责

- 不拥有发票生命周期源事实。
- 不直接维护关联台关系事实源。
- 不接受 bare `all` scope 重建。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面筛选、方向、规则操作 | `PendingInvoicesPage.tsx`、`features/pendingInvoices/api.ts` | scope 必须落到 direction/filter/month |
| 关联/规则写入 | pending invoice services | 写后触发 pending_invoice/search/invoice_lifecycle 相关 scope |
| Refresh scope | `pending_invoice` manifest | `direction:filter_group[:YYYY-MM]`；bare `all` forbidden |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 待找发票 rows/summary | 前端页面 | fresh/status 可见；缺少/未知 read model status 保持 refreshing/non-fresh |
| 规则保存结果 | API | 持久化规则并触发刷新 |
| 发票关联/收入状态写结果 | API/frontend | 返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| Dirty scope | runtime queue | 不允许无界全量 |

## 持久化与投影

- Read model：`pending_invoice`
- Projection：`scoped_incremental`
- Worker：`pending-invoice`，辅助 `search-pending`
- Query owner：`PendingInvoiceReadModelService`
- Repository owner：`PendingInvoiceReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/PendingInvoicesPage.tsx` |
| Frontend feature/components | `web/src/features/pendingInvoices/*`、`web/src/components/pendingInvoices/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_pending_invoices.py` |
| Backend service | `pending_invoice_service.py`、`pending_invoice_read_model_service.py`、`pending_invoice_rules_application_service.py`、`pending_invoice_lifecycle_service.py`、`pending_invoice_status.py` |
| Repository / SQL | `pending_invoice_read_model_repository.py`、`search_pending_sql_projection.py`、`invoice_lifecycle_sql_projection.py` |
| Tests | `tests/test_pending_invoice*.py`、`web/src/test/PendingInvoices*.test.*`、`web/e2e/pending-invoices-*.spec.ts` |

## 依赖方向

- 允许依赖：invoice lifecycle policy/read facade、search projection、workbench relation read facade。
- 必须通过：PendingInvoiceReadModelService and rules application service。
- 禁止绕过：bare all refresh；页面自行合成 invoice status。

## 测试与验证

- `tests/test_pending_invoice_service.py`
- `tests/test_pending_invoice_api.py`
- `web/e2e/pending-invoices-fanout.spec.ts`
- `web/e2e/pending-invoices-filter-sort-flow.spec.ts`

## 当前缺口和删除条件

- 修改规则或 scope policy 时必须同步 manifest/scope tests。
- 删除旧路径前必须覆盖 expense/income、规则保存、关联、导出和 fan-out。
