# 销项发票收款情况模块边界与 I/O

日期：2026-07-07

## 模块化状态

- 状态：closed-local
- 当前边界可信度：high
- 目标边界：销项发票收款情况通过 `output_invoice_collection` read model 查询；linked relation 下多张销项发票先归并为一条收款行，成员发票按净额汇总且负数/红字发票必须保留在 relation summaries；收款/红冲/生命周期变更产生 scoped refresh。
- 当前本地 I/O 缺口：无已知 route/service/repository/read model 边界污染。剩余风险是生产 PostgreSQL 大数据、真实 worker drain 和 staging smoke，不属于本地模块化缺口。
- 旧代码删除条件：生产页面 API 的 read-model 编排已移入 `OutputInvoiceCollectionReadApplicationService`；旧 service 直读路径只作为 legacy/local compat-only，不参与生产页面 API fresh 结果；fresh gate 和架构守卫测试覆盖。

## 职责边界

### 负责

- 销项发票收款情况页面、明细、收款状态、红冲关系和导出。
- `output_invoice_collection` read model。
- linked `workbench_relation` 中多张销项发票到单条收款行的投影归并规则。
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
| 统一关系事实 | `workbench_relation` read facade | 只有 `relationStatus="linked"` 的 typed rows 可驱动 OA/流水/销项发票 relation summaries；多张销项发票 relation 归并为一条收款行 |
| 收款/状态写入 | output invoice collection services | 触发 lifecycle 和 read model dirty scope |
| 写后 target envelope | `output_invoice_collection_freshness_metadata(...)` | 按发票所属月份返回 `output_invoice_collection` 的 affected/read-model scope 和 operation barrier target |
| Refresh scope | `output_invoice_collection` manifest | month or `all`；`all` 是 fan-out command |
| Relation upstream freshness | `workbench_relation` month scope | projection 在读取 relation source versions、执行 unchanged-scope 判断或写 rows 前必须先通过 fresh gate；non-fresh 交 worker defer。当前 input/output 页面共用月份 relation source-version proof，因此任一发票 relation 改变都刷新本 scope；若关系不含销项发票，rows 必须作为 isolation baseline 保持不变 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 收款 rows/details | 前端页面 | fresh/status 可见；linked 多销项发票 relation 输出单条 row，`invoiceRelations.summaries` 包含全部成员发票，`invoiceRelations.totalWithTax` 为成员净额；rows summary 的 `invoiceCount` 按唯一销项发票 ID 统计并驱动标题右侧 `销项票 N`，`pagination.total` 仍是表格行数/配对组行数；标题统计表示全量销项票数，不随当前 keyword/filter/month/sort 的表格筛选结果变化 |
| 页面 Audit icon | AppHealth operations audit API | admin-only；active canonical 销项发票（含 collapsed members）是 independent expected-set，成员/金额/scope 与共享 relation 的受影响月份双向 edge 必须在同一只读一致性快照中相等；只有结构化 integrity=pass、freshness=fresh、queue=drained 且 database snapshot 已启用才显示成功，unknown/live-query 不得伪装 fresh，问题数显示为 sample |
| lifecycle/status result | API | 写后可恢复、可审计 |
| operation barrier targets | 前端页面 | lifecycle/receipt 写成功后用服务端返回 targets 等待 fresh；缺省时才回退当前查询月份 |
| Dirty scope | runtime queue | `output_invoice_collection.read_model.refresh` |

## 持久化与投影

- Read model：`output_invoice_collection`
- Projection：`scoped_incremental`
- Worker：`invoice-usage-collection`
- Query owner：`OutputInvoiceCollectionReadApplicationService`
- Repository owner：`OutputInvoiceCollectionReadModelRepositoryPort`
- Source version：改变 row ownership、relation grouping、金额口径或 relation summaries 字段时必须 bump `OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION`，防止旧投影被 freshness gate 当作 fresh。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/OutputInvoiceCollectionsPage.tsx` |
| Frontend feature/components | `web/src/features/outputInvoiceCollections/*`、`web/src/components/outputInvoiceCollections/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py` |
| Backend service | `output_invoice_collection_read_application_service.py`、`output_invoice_collection_service.py`、`output_invoice_collection_lifecycle_service.py`、`output_invoice_collection_receipt_service.py`、`output_invoice_collection_status_service.py`、`output_invoice_collection_read_model_*` |
| Repository / SQL | `postgres_repositories/output_invoice_collection.py`、`invoice_usage_collection_sql_projection.py` |
| Tests | `tests/test_output_invoice_collection*.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-*.spec.ts` |

## 依赖方向

- 允许依赖：invoice lifecycle policy, invoice usage collection projection, workbench relation read facade。
- 必须通过：页面读路径走 `OutputInvoiceCollectionReadApplicationService`；业务规则和 legacy/local 组行走 `OutputInvoiceCollectionService`；写路径走 lifecycle/receipt service。
- 禁止绕过：直接改 lifecycle 状态；页面自行补齐 stale 明细。

## 测试与验证

- `tests/test_output_invoice_collection_api.py`
- `tests/test_output_invoice_collection_read_application_service.py`
- `tests/test_output_invoice_collection_lifecycle.py`
- `tests/test_output_invoice_collection_read_model_fresh_gate_service.py`
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx` 覆盖页面等待 operation barrier 行为。
- `web/e2e/output-invoice-collections-flow.spec.ts`
- `tests/test_output_invoice_collection_service.py::OutputInvoiceCollectionQueryServiceTests.test_multi_output_relation_emits_single_net_collection_row` 覆盖 linked 多销项发票 relation 只输出一条净额收款行，且负数发票进入 summaries。
- `tests/test_audit_output_invoice_collection_read_model_tool.py` 覆盖销项收款真实库只读审计 invariant。

## 当前缺口和删除条件

- 红冲 fan-out 和撤回恢复必须在删除旧路径前覆盖。

## Canonical facts ownership

- Owned facts: `app.output_invoice_collection_status_overrides`、`app.output_invoice_collection_reminders`、`app.output_invoice_collection_red_relations`、`app.output_invoice_receipt_settings`、`app.output_invoice_receipt_number_counters`、`app.output_invoice_receipts`、`app.output_invoice_receipt_events`。
- Allowed writes: output invoice collection lifecycle services、receipt services、reminder/red relation services。
- Allowed reads: output collection application/query services、receipt query ports。
- Downstream outputs: output_invoice_collection、invoice_lifecycle、workbench_relation dirty scopes 或 owner producer 输出。
- Forbidden paths: route overlay 不得伪造 fresh 或直接写生命周期表；read model payload 不得反向成为收款事实。
- Old code deletion: 旧 route overlay、snapshot 收款状态 fallback 和直接 SQL 写 lifecycle facts 路径必须删除；migration/audit/rollback 工具保留不算 closure。
