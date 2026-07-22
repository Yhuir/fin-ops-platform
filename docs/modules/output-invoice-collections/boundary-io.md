# 销项发票收款情况模块边界与 I/O

日期：2026-07-22

## 模块化状态

- 状态：closed-local
- 当前边界可信度：high
- 目标边界：销项发票收款情况通过 `output_invoice_collection` read model 查询；linked relation 下多张销项发票先归并为一条收款行，成员发票按净额汇总且负数/红字发票必须保留在 relation summaries；收款/红冲/收据写入只提交 canonical lifecycle facts，页面访问时再收敛 scoped projection。
- 当前本地 I/O 缺口：无已知 route/service/repository/read model 边界污染。剩余风险是生产 PostgreSQL 大数据、真实 worker drain 和 staging smoke，不属于本地模块化缺口。
- 旧代码删除条件：生产页面 API 的 read-model 编排已移入 `OutputInvoiceCollectionReadApplicationService`；旧 service 直读路径只作为 legacy/local compat-only，不参与生产页面 API fresh 结果；fresh gate 和架构守卫测试覆盖。

## 职责边界

### 负责

- 销项发票收款情况页面、明细、收款状态、红冲关系和导出。
- `output_invoice_collection` read model。
- linked `workbench_relation` 中多张销项发票到单条收款行的投影归并规则。
- 与 invoice usage collection worker 的 scoped projection。
- 生命周期状态、提醒、红蓝票关系、收据创建/作废/重开和收据编号设置均走 module-owned command/repository；普通写返回 scope hints 和空 freshness/barrier targets，当前可见页立即正常 GET。

### 不负责

- 不拥有进项发票使用业务。
- 不直接维护关联台关系事实源。
- 不绕过 invoice lifecycle policy 更新发票状态。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/筛选 | `OutputInvoiceCollectionsPage.tsx`、`features/outputInvoiceCollections/api.ts` | 进入 read model service/fresh gate |
| 统一关系事实 | `workbench_relation` read facade | 只有 `relationStatus="linked"` 的 typed rows 可驱动 OA/流水/销项发票 relation summaries；多张销项发票 relation 归并为一条收款行 |
| 收款/状态写入 | output invoice collection services | 同一事务写 status/reminder/red relation/receipt/counter/audit/idempotency facts，不写 read-model dirty/outbox；收据编号设置是直接配置保存且始终零 read-model job |
| 写后 scope hints | `output_invoice_collection_freshness_metadata(...)` | 按发票所属月份返回 affected/read-model scope hints；`freshness_targets=[]`、`operation_barrier_targets=[]`，未知月份不回退 `all` |
| Refresh scope | `output_invoice_collection` manifest | month or `all`；`all` 是 fan-out command。显式运维 `force_refresh=true` 必须传播到 month shard 并绕过 unchanged fast path，重新生成目标 scope rows；不得改收款、收据或 relation facts |
| Relation upstream freshness | `workbench_relation` month scope | projection 在读取 relation source versions、执行 unchanged-scope 判断或写 rows 前必须先通过 fresh gate；non-fresh 交 worker defer。当前 input/output 页面共用月份 relation source-version proof，因此任一发票 relation 改变都刷新本 scope；若关系不含销项发票，rows 必须作为 isolation baseline 保持不变 |
| OA projection source version | OA projection sync worker | `workbench_relation_source_versions.oa_projection_updated_at` 是本 read model 的完整性合同；OA projection 更新受影响月份时必须经正式 refresh gateway 同时置脏本 scope，不能让 queue drained 后仍保留旧 embedded relation versions |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 收款 rows/details/statistics | 前端页面 | fresh/status 可见；linked 多销项发票 relation 输出单条 row，`invoiceRelations.summaries` 包含全部成员发票，`invoiceRelations.totalWithTax` 为成员净额。主 rows 响应的 `statistics` 从完整 `output_invoice_collection` 投影按唯一发票成员 ID 计算发票、OA/收入流水关联、收款及补集、红字和已开收据；忽略当前 keyword/filter/month/sort/page。`pagination.total` 仍是表格行数/配对组行数；任一 child scope non-fresh 时统计不可用，合法 fresh 空集才返回零。 |
| 页面 Audit icon | AppHealth operations audit API | admin-only；active canonical 销项发票（含 collapsed members）是 independent expected-set，成员/金额/scope 与共享 relation 的受影响月份双向 edge 必须在同一只读一致性快照中相等；relation source-version 仅有全局 `workbench_pair_relations_updated_at` 前进时，只有该时间点之后的 relation 与本月 canonical/PostgreSQL/OA source-link 发票 identity 相交才判为本页 mismatch，纯银行关系变化不得污染本页 integrity；其它版本差异仍 fail closed。此规则只收窄只读 Audit 分类，页面 fresh gate 仍按完整 source-version 合同按访问触发刷新，精确化由 Phase 27 负责；只有结构化 integrity=pass、freshness=fresh、queue=drained 且 database snapshot 已启用才显示成功，unknown/live-query 不得伪装 fresh，问题数显示为 sample |
| lifecycle/status result | API | 写后可恢复、可审计 |
| 写后页面收敛 | 前端页面 | lifecycle/receipt/关系/设置写成功后不调用 operation barrier；仅当前 active 页面重跑 rows GET。GET 返回 non-fresh 时再按服务端精确 targets 进入访问时 freshness 等待，不能把旧 rows 当 fresh |
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
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx` 覆盖每个可写 Drawer 普通保存零 operation barrier、当前页重新加载，以及访问 GET non-fresh 时的严格状态。
- `web/e2e/output-invoice-collections-flow.spec.ts`
- `tests/test_output_invoice_collection_service.py::OutputInvoiceCollectionQueryServiceTests.test_multi_output_relation_emits_single_net_collection_row` 覆盖 linked 多销项发票 relation 只输出一条净额收款行，且负数发票进入 summaries。
- `tests/test_audit_output_invoice_collection_read_model_tool.py` 覆盖销项收款真实库只读审计 invariant。

## 当前缺口和删除条件

- 红冲确认/撤回、状态/提醒、收据创建/作废/重开和编号设置的 canonical recovery 与普通写零 fan-out 必须持续覆盖。
- 已删除标题计数的 `page_size=1` 二次请求；标题统计只能消费 rows 主响应，禁止恢复独立 title-total I/O。
- `output_invoice_collection_statistics_schema_version` 负责生产旧 scope 的统计元数据回填；source version 相同但缺少合法统计元数据时也必须重建，不能走 unchanged skip。批量导出的所有分页均传 `include_statistics=false`，不重复读取、校验或透传页面标题统计；每一页仍执行 rows freshness、schema 和 source-version gate。

## Canonical facts ownership

- Owned facts: `app.output_invoice_collection_status_overrides`、`app.output_invoice_collection_reminders`、`app.output_invoice_collection_red_relations`、`app.output_invoice_receipt_settings`、`app.output_invoice_receipt_number_counters`、`app.output_invoice_receipts`、`app.output_invoice_receipt_events`。
- Allowed writes: output invoice collection lifecycle services、receipt services、reminder/red relation services。
- Allowed reads: output collection application/query services、receipt query ports。
- Downstream outputs: lifecycle/receipt/relation owner facts与受影响月份 hints；output-invoice-collection、invoice-lifecycle、workbench-relation dirty scope 由对应访问 owner输出。
- Forbidden paths: route overlay 不得伪造 fresh 或直接写生命周期表；read model payload 不得反向成为收款事实。
- Old code deletion: 旧 route overlay、snapshot 收款状态 fallback 和直接 SQL 写 lifecycle facts 路径必须删除；migration/audit/rollback 工具保留不算 closure。
