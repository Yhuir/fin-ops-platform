# 待找发票模块边界与 I/O

日期：2026-07-05

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：待找发票页面读取 `pending_invoice` scoped read model，规则保存和关联变更触发精确 scope refresh。
- 当前结论：rows、filter-options、export-preview 和 export 只允许通过 `PendingInvoiceReadModelService` freshness gate 读取 `pending_invoice` read model；候选、详情和导出格式化只接受明确输入 rows 或 scoped id，不再暴露同步全量 rows 直查入口。
- 旧代码删除结果：`Application._handle_api_pending_invoice_rows` 兼容入口、`PendingInvoiceQueryService.list_rows`、旧同步 `filter_options`、旧同步 `export_preview/export` 和旧 rows-only filter/sort helper 已删除；tests 不再引用旧 handler 或旧 query-service rows API。

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
| 关联台关系分发 | `WorkbenchRelationReadFacade` / `workbench_relation` read model | 待找发票只按银行流水 row id 读取 `linked_oa`、`linked_input_invoices`、`linked_output_invoices`、`group_ids` 等 relation distribution；不得自行从发票附件、OA payload 或关联台 raw payload 反推 OA。若 `workbench_relation` non-fresh，必须保持 refreshing/stale 状态而不是伪装 fresh。 |
| Worker 关系源端快路径 | `WorkbenchRelationReadModelRepositoryPort` | `search-pending` / `pending-invoice` projection 可通过 `list_active_workbench_relation_source_rows(...)` / `workbench_relation_source_summary_from_source(...)` 读取 active relation source rows/source summary，构造待找发票 relation context 与 source-version proof；API expected-source gate 必须按当前 pending invoice rows 命中的月份和 row id 调同一个 source summary，不能再拿 `read_model.workbench_relation_scopes.source_versions` 和 source-fast-path 写入值比较；SQL owner 仍归 workbench-relations repository，下游不得直接读 relation 表，也不得把源端快路径用于页面 fresh payload 或关系写状态机。 |
| 导入/运行时派生范围 | `PendingInvoiceScopePlanner` | 从 `cost_statistics` 与 `bank_detail` 月份 scope 合并生成 `expense:all:<YYYY-MM>`、`income:all:<YYYY-MM>`、`income:cash_income:<YYYY-MM>`；没有可识别月份时只返回三类父 scope，不写 bare `all` |
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
| Scope planning | `backend/src/fin_ops_platform/services/pending_invoice_scope_planner.py` |
| Repository / SQL | `pending_invoice_read_model_repository.py`、`search_pending_sql_projection.py`、`invoice_lifecycle_sql_projection.py` |
| Tests | `tests/test_pending_invoice*.py`、`web/src/test/PendingInvoices*.test.*`、`web/e2e/pending-invoices-*.spec.ts` |

## 依赖方向

- 允许依赖：invoice lifecycle policy/read facade、search projection、workbench relation read facade。
- 必须通过：PendingInvoiceReadModelService and rules application service。
- 禁止绕过：bare all refresh；页面自行合成 invoice status。

## 测试与验证

- `tests/test_pending_invoice_service.py`
- `tests/test_pending_invoice_api.py`
- `tests/test_import_processing_service.py`
- `web/e2e/pending-invoices-fanout.spec.ts`
- `web/e2e/pending-invoices-filter-sort-flow.spec.ts`

## 当前缺口和删除条件

- 修改规则或 scope policy 时必须同步 manifest/scope tests。
- 已删除旧路径后仍需保持覆盖：expense/income、规则保存、关联、导出和 fan-out。

## Canonical facts ownership

- Owned facts: `app.pending_invoice_manual_invoice_commands`。
- Shared facts: `app.invoices` 由 canonical invoice pool owner 管理；关系事实由 `workbench-relations` owner 管理。
- Allowed writes: pending invoice manual invoice command service、pending invoice application boundary。
- Allowed reads: `PendingInvoiceReadModelService`、transaction-scoped pending invoice query/detail/candidate services、manual command repository/read ports。
- Downstream outputs: pending_invoice、invoice_lifecycle、search、workbench_relation dirty scopes 或 owner producer 输出。
- Forbidden paths: pending invoice 页面或 service 不得直接创建第二发票池、直接写 relation facts 或绕过 command 状态机。
- Old code deletion: manual invoice command snapshot fallback、direct invoice/relation write fallback、bare all refresh、旧 API handler 和同步 rows/filter/export 直查路径已关闭；migration/audit/rollback 工具保留不算污染。
