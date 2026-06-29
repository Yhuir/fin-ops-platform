# 销项发票收款情况模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：销项发票收款情况通过 `output_invoice_collection` read model 查询；收款/红冲/生命周期变更产生 scoped refresh。
- 当前缺口：与 invoice lifecycle、workbench relation、receipt service 关联紧密，旧路径删除需要多模块回归。
- 旧代码删除条件：旧 service 直读路径不再参与页面 API，fresh gate tests 覆盖。

## 职责边界

### 负责

- 销项发票收款情况页面、明细、收款状态、红冲关系和导出。
- `output_invoice_collection` read model。
- 与 invoice usage collection worker 的 scoped projection。
- 生命周期状态、提醒、收据创建/作废/重开等写操作返回统一 write target envelope，页面优先等待 `operation_barrier_targets`。

### 不负责

- 不拥有进项发票使用业务。
- 不直接维护关联台关系事实源。
- 不绕过 invoice lifecycle policy 更新发票状态。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/筛选 | `OutputInvoiceCollectionsPage.tsx`、`features/outputInvoiceCollections/api.ts` | 进入 read model service/fresh gate |
| 收款/状态写入 | output invoice collection services | 触发 lifecycle 和 read model dirty scope |
| 写后 target envelope | `output_invoice_collection_freshness_metadata(...)` | 按发票所属月份返回 `output_invoice_collection` 的 affected/read-model scope 和 operation barrier target |
| Refresh scope | `output_invoice_collection` manifest | month or `all`；`all` 是 fan-out command |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 收款 rows/details | 前端页面 | fresh/status 可见 |
| lifecycle/status result | API | 写后可恢复、可审计 |
| operation barrier targets | 前端页面 | lifecycle/receipt 写成功后用服务端返回 targets 等待 fresh；缺省时才回退当前查询月份 |
| Dirty scope | runtime queue | `output_invoice_collection.read_model.refresh` |

## 持久化与投影

- Read model：`output_invoice_collection`
- Projection：`scoped_incremental`
- Worker：`invoice-usage-collection`
- Query owner：`OutputInvoiceCollectionService`
- Repository owner：`OutputInvoiceCollectionReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/OutputInvoiceCollectionsPage.tsx` |
| Frontend feature/components | `web/src/features/outputInvoiceCollections/*`、`web/src/components/outputInvoiceCollections/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py` |
| Backend service | `output_invoice_collection_service.py`、`output_invoice_collection_lifecycle_service.py`、`output_invoice_collection_receipt_service.py`、`output_invoice_collection_status_service.py`、`output_invoice_collection_read_model_*` |
| Repository / SQL | `postgres_repositories/output_invoice_collection.py`、`invoice_usage_collection_sql_projection.py` |
| Tests | `tests/test_output_invoice_collection*.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-*.spec.ts` |

## 依赖方向

- 允许依赖：invoice lifecycle policy, invoice usage collection projection, workbench relation read facade。
- 必须通过：OutputInvoiceCollectionService/lifecycle service。
- 禁止绕过：直接改 lifecycle 状态；页面自行补齐 stale 明细。

## 测试与验证

- `tests/test_output_invoice_collection_api.py`
- `tests/test_output_invoice_collection_lifecycle.py`
- `tests/test_output_invoice_collection_read_model_fresh_gate_service.py`
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx` 覆盖页面等待 operation barrier 行为。
- `web/e2e/output-invoice-collections-flow.spec.ts`

## 当前缺口和删除条件

- 红冲 fan-out 和撤回恢复必须在删除旧路径前覆盖。

## Canonical facts ownership

- Owned facts: `app.output_invoice_collection_status_overrides`、`app.output_invoice_collection_reminders`、`app.output_invoice_collection_red_relations`、`app.output_invoice_receipt_settings`、`app.output_invoice_receipt_number_counters`、`app.output_invoice_receipts`、`app.output_invoice_receipt_events`。
- Allowed writes: output invoice collection lifecycle services、receipt services、reminder/red relation services。
- Allowed reads: output collection application/query services、receipt query ports。
- Downstream outputs: output_invoice_collection、invoice_lifecycle、workbench_relation dirty scopes 或 owner producer 输出。
- Forbidden paths: route overlay 不得伪造 fresh 或直接写生命周期表；read model payload 不得反向成为收款事实。
- Old code deletion: 旧 route overlay、snapshot 收款状态 fallback 和直接 SQL 写 lifecycle facts 路径必须删除；migration/audit/rollback 工具保留不算 closure。
